import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import UnsupportedOperation

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

RANGE = 0
BULLISH = 1
BEARISH = 2

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
    if os.path.exists(filename):
        try:
            return json.load(open(filename, 'w'))
        except UnsupportedOperation:
            return None
    return None


order_filename = "last_order.json"


class BinanceBot:

    def __init__(self, api_key, api_secret, symbol, interval):
        self.client: Client = Client(api_key, api_secret)
        self.websocket: BinanceSocketManager = BinanceSocketManager(self.client)
        self.symbol = symbol
        self.interval = interval
        self.trend = RANGE
        self.data: pd.DataFrame = pd.DataFrame()
        self.websocket.start()
        self.balance = 10
        self.lastOrder = read_order(order_filename)

    def start(self):
        print(F"[{datetime.now()}]: initializing bot on {self.symbol} with TF: {self.interval}, "
              F"last order: {self.lastOrder} \n")
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
            print(F"Cancel {len(open_orders)} orders")

    def on_update(self):
        try:
            if is_crossing_up(self.data, "ema_8", "ema_21") \
                    and self.lastOrder is None and self.trend is not BEARISH:
                self.lastOrder = self.client.create_order(symbol=self.symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET,
                                                          quoteOrderQty=self.balance,
                                                          newOrderRespType=ORDER_RESP_TYPE_RESULT)
                save_order(self.lastOrder, order_filename)
                print(F"{datetime.now()} BUY: {self.lastOrder}")
            elif is_crossing_down(self.data, "ema_8", "ema_21") \
                    and self.lastOrder is not None and self.trend is not BULLISH:
                self.client.create_order(symbol=self.symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET,
                                         quantity=self.lastOrder['executedQty'])
                lastBalance = self.balance
                self.lastOrder = None
                self.update_account_balance()
                print(F"[{datetime.now()}] SELL, P&L: {self.balance - lastBalance}$")

        except Exception as e:
            print("Error: ", e)

    def update_account_balance(self):
        self.balance = self.client.get_asset_balance("USDT")['free']
        print(F"Account balance: {self.balance}$")

    def define_trend(self):
        last_trend = self.trend
        trend_line = self.data["ema_55"].iloc[-1].item()
        current_price = self.data["close"].iloc[-1].item()
        percent = ((abs(trend_line - current_price) / current_price) * 100)
        if percent < 0.3:
            self.trend = RANGE
        elif trend_line > current_price:
            self.trend = BEARISH
        else:
            self.trend = BULLISH

        if last_trend is not self.trend:
            print(F"Trend change : {TRENDS_NAME[self.trend]}")

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


def run_server(name):
    print(F"Starting web server on thread {name}")
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, BaseHTTPRequestHandler)
    httpd.serve_forever()


if __name__ == '__main__':
    threading.Thread(target=run_server, args=(1,)).start()

    bot = BinanceBot(
        os.getenv("BINANCE_KEY"),
        os.getenv("BINANCE_SECRET"),
        "ETHUSDT",
        KLINE_INTERVAL_15MINUTE
    )

    bot.start()
