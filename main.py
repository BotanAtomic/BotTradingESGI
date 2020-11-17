import os
import threading
from io import UnsupportedOperation

from binance.client import Client
from binance.enums import *
from binance.websockets import BinanceSocketManager
import pandas as pd
import numpy as np
from datetime import datetime

from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import json

from const import *
from logger import Logger
from server import HttpServer


def is_crossing_down(df, first_key, second_key):
    return df[first_key].iloc[-1] < df[second_key].iloc[-1] \
           and df[first_key].iloc[-2] >= df[second_key].iloc[-2]


def is_crossing_up(df, first_key, second_key):
    return df[first_key].iloc[-1] > df[second_key].iloc[-1] \
           and df[first_key].iloc[-2] <= df[second_key].iloc[-2]


def save_order(order, filename):
    json.dump(order, open(filename, 'w'))


def read_order(filename):
    if os.path.exists(filename):
        try:
            return json.load(open(filename, 'w'))
        except UnsupportedOperation:
            return None
    return None


order_filename = "last_order.json"


class BinanceBot:

    def __init__(self, api_key, api_secret, symbol, interval, logger):
        self.client: Client = Client(api_key, api_secret)
        self.websocket: BinanceSocketManager = BinanceSocketManager(self.client)
        self.symbol = symbol
        self.interval = interval
        self.trend = SIDEWAYS
        self.logger = logger
        self.data: pd.DataFrame = pd.DataFrame()
        self.websocket.start()
        self.balance = 10
        self.lastOrder = read_order(order_filename)

    def start(self):
        self.logger.init_log(F"starting bot {self.symbol} with TF: {self.interval}")
        self.update_account_balance()
        self.cancel_open_orders()
        self.initialize_candles()
        self.start_websocket()

    def cancel_open_orders(self):
        open_orders = self.client.get_open_orders(symbol=self.symbol)
        for order in open_orders:
            save_order(order, order_filename)
            self.client.cancel_order(symbol=self.symbol, orderId=order['orderId'])
        if len(open_orders) > 0:
            self.logger.init_log(F"cancel {len(open_orders)} open orders")

    def on_update(self):
        try:
            if is_crossing_up(self.data, "ema_8", "ema_21") \
                    and self.lastOrder is None and self.trend is not BEARISH:
                self.lastOrder = self.client.create_order(symbol=self.symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET,
                                                          quoteOrderQty=self.balance,
                                                          newOrderRespType=ORDER_RESP_TYPE_RESULT)
                save_order(self.lastOrder, order_filename)
                self.logger.buy_log(self.lastOrder['price'], self.lastOrder['executedQty'])
            elif is_crossing_down(self.data, "ema_8", "ema_21") \
                    and self.lastOrder is not None and self.trend is not BULLISH:
                sell_order = self.client.create_order(symbol=self.symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET,
                                                      quantity=self.lastOrder['executedQty'],
                                                      newOrderRespType=ORDER_RESP_TYPE_RESULT)
                lastBalance = self.balance
                self.lastOrder = None
                self.update_account_balance()
                pnl = self.balance - lastBalance
                self.logger.sell_log(sell_order['sell_order'], pnl, self.balance)

        except Exception as e:
            print("Error: ", e)

    def update_account_balance(self):
        self.balance = self.client.get_asset_balance("USDT")['free']

    def define_trend(self):
        last_trend = self.trend
        trend_line = self.data["ema_55"].iloc[-1].item()
        current_price = self.data["close"].iloc[-1].item()
        percent = ((abs(trend_line - current_price) / current_price) * 100)
        if percent < 0.3:
            self.trend = SIDEWAYS
        elif trend_line > current_price:
            self.trend = BEARISH
        else:
            self.trend = BULLISH

        if last_trend is not self.trend:
            self.logger.trend_log(last_trend, self.trend)

    def initialize_candles(self):
        dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        candles = self.client.get_klines(symbol=self.symbol, interval=self.interval, limit=100)
        for candle in candles:
            dates.append(candle[0])
            opens.append(candle[1])
            highs.append(candle[2])
            lows.append(candle[3])
            closes.append(candle[4])
            volumes.append(candle[5])

        self.data['date'] = dates
        self.data['open'] = np.array(opens).astype(np.float)
        self.data['high'] = np.array(highs).astype(np.float)
        self.data['low'] = np.array(lows).astype(np.float)
        self.data['close'] = np.array(closes).astype(np.float)
        self.data['volume'] = np.array(volumes).astype(np.float)
        self.calculate_ta()
        self.logger.init_log(F"loaded {len(self.data)} candles")
        self.define_trend()

    def calculate_ta(self):
        self.data['rsi'] = RSIIndicator(close=self.data["close"], n=14).rsi()
        self.data["ema_8"] = EMAIndicator(close=self.data["close"], n=8).ema_indicator()
        self.data["ema_21"] = EMAIndicator(close=self.data["close"], n=21).ema_indicator()
        self.data["ema_55"] = EMAIndicator(close=self.data["close"], n=55).ema_indicator()

    def kline_callback(self, msg):
        if msg['k']['x']:
            df = pd.DataFrame()
            df['date'] = [msg['k']['T']]
            df['open'] = np.array([msg['k']['o']]).astype(np.float)
            df['high'] = np.array([msg['k']['h']]).astype(np.float)
            df['low'] = np.array([msg['k']['l']]).astype(np.float)
            df['close'] = np.array([msg['k']['c']]).astype(np.float)
            df['volume'] = np.array([msg['k']['v']]).astype(np.float)
            self.data = self.data.append(df, ignore_index=True)
            self.calculate_ta()
            self.define_trend()
            self.on_update()

    def start_websocket(self):
        self.websocket.start_kline_socket(self.symbol, self.kline_callback, self.interval)


if __name__ == '__main__':
    global_logger = Logger()
    http_server = HttpServer(global_logger)

    threading.Thread(target=http_server.start, args=()).start()

    bot = BinanceBot(
        os.getenv("BINANCE_KEY"),
        os.getenv("BINANCE_SECRET"),
        "ETHUSDT",
        KLINE_INTERVAL_15MINUTE,
        global_logger
    )

    bot.start()
