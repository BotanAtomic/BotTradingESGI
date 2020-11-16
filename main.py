import os

from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException
from binance.websockets import BinanceSocketManager
import pandas as pd
import numpy as np
from datetime import datetime

from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import json

TREND_RANGE = 0
TREND_BULLISH = 1
TREND_BEARISH = 2

TRENDS_NAME = ["RANGE", "BULLISH", "BEARISH"]


def is_crossing_down(df, first_key, second_key):
    return df[first_key].iloc[-1] < df[second_key].iloc[-1] \
           and df[first_key].iloc[-2] >= df[second_key].iloc[-2]


def is_crossing_up(df, first_key, second_key):
    return df[first_key].iloc[-1] > df[second_key].iloc[-1] \
           and df[first_key].iloc[-2] <= df[second_key].iloc[-2]


def save_order(order, filename):
    json.dump(order, open(filename, 'w'))


def read_order(filename):
    return json.load(open(filename, 'w'))


order_filename = "last_order.json"


class BinanceBot:

    def __init__(self, api_key, api_secret, symbol, interval):
        self.client: Client = Client(api_key, api_secret)
        self.websocket: BinanceSocketManager = BinanceSocketManager(self.client)
        self.symbol = symbol
        self.interval = interval
        self.trend = TREND_RANGE
        self.data: pd.DataFrame = pd.DataFrame()
        self.websocket.start()
        self.quantity = 10
        self.lastOrder = read_order(order_filename)

    def start(self):
        print(F"Initializing bot on {self.symbol} with TF: {self.interval} [{datetime.now()}]\n")
        self.update_account_balance()
        self.cancel_open_orders()
        self.initialize_candles()
        self.start_websocket()

    def cancel_open_orders(self):
        open_orders = self.client.get_open_orders(symbol=self.symbol)
        for order in open_orders:
            self.client.cancel_order(symbol=self.symbol, clientId=order['clientId'])
        if len(open_orders) > 0:
            print(F"Cancel {len(open_orders)} orders")

    def on_update(self):
        try:
            if is_crossing_up(self.data, "ema_8", "ema_21"):
                self.lastOrder = self.client.create_order(symbol=self.symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET,
                                                          quoteOrderQty=self.quantity,
                                                          newOrderRespType=ORDER_RESP_TYPE_FULL)
                save_order(self.lastOrder, order_filename)
                print(F"{datetime.now()}: buying {self.lastOrder}")
            elif is_crossing_down(self.data, "ema_8", "ema_21") and self.lastOrder is not None:
                sell_order = self.client.create_order(symbol=self.symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET,
                                                      quantity=self.lastOrder.executedQty)
                print(F"{datetime.now()} selling position {sell_order}")
                self.lastOrder = None
                self.update_account_balance()
        except BinanceAPIException as e:
            print("Error: ", e)

    def update_account_balance(self):
        self.quantity = self.client.get_asset_balance("USDT")['free']
        print(F"Account balance: {self.quantity}$")

    def define_trend(self):
        trend_line = self.data["ema_55"].iloc[-1].item()
        current_price = self.data["close"].iloc[-1].item()
        percent = ((abs(trend_line - current_price) / current_price) * 100)
        if percent < 0.3:
            self.trend = TREND_RANGE
        elif trend_line > current_price:
            self.trend = TREND_BEARISH
        else:
            self.trend = TREND_BULLISH
        print(F"Current trend is : {TRENDS_NAME[self.trend]} [{trend_line}, {current_price}, {percent}]")

    def initialize_candles(self):
        dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        candles = self.client.get_klines(symbol=self.symbol, interval=self.interval, limit=56)
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
        print(F"Successfully loaded {len(self.data)} candles")
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
    bot = BinanceBot(
        os.getenv("BINANCE_KEY"),
        os.getenv("BINANCE_SECRET"),
        "ETHUSDT",
        KLINE_INTERVAL_1MINUTE
    )

    bot.start()
