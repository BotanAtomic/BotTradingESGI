import os

from binance.client import Client
from binance.enums import *
from binance.websockets import BinanceSocketManager
import pandas as pd
import numpy as np

from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

TREND_RANGE = 0
TREND_BULLISH = 1
TREND_BEARISH = 2

TRENDS_NAME = ["RANGE", "BULLISH", "BEARISH"]


class BinanceBot:

    def __init__(self, api_key, api_secret, coin, interval):
        self.client: Client = Client(api_key, api_secret)
        self.websocket = BinanceSocketManager(self.client)
        self.coin = coin
        self.interval = interval
        self.trend = TREND_RANGE
        self.data = pd.DataFrame()

    def start(self):
        print(F"Initializing bot on {self.coin} with TF: {self.interval}")
        self.initialize_candles()

    def define_trend(self):
        trend_line = self.data.tail(1)["ema_55"].item()
        current_price = self.data.tail(1)["close"].item()
        if ((abs(trend_line - current_price)/current_price) * 100) < 1.5:
            self.trend = TREND_RANGE
        elif trend_line > current_price:
            self.trend = TREND_BEARISH
        else:
            self.trend = TREND_BULLISH
        print(F"Current trend is : {TRENDS_NAME[self.trend]}")

    def initialize_candles(self):
        dates, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        candles = self.client.get_klines(symbol=self.coin, interval=self.interval)
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
        self.data['rsi'] = RSIIndicator(close=self.data["close"], n=14).rsi()
        self.data["ema_9"] = EMAIndicator(close=self.data["close"], n=8).ema_indicator()
        self.data["ema_21"] = EMAIndicator(close=self.data["close"], n=21).ema_indicator()
        self.data["ema_55"] = EMAIndicator(close=self.data["close"], n=55).ema_indicator()
        print(F"Successfully loaded {len(self.data)} candles")
        self.define_trend()


if __name__ == '__main__':
    bot = BinanceBot(
        os.getenv("BINANCE_KEY"),
        os.getenv("BINANCE_SECRET"),
        "ETHUSDT",
        KLINE_INTERVAL_15MINUTE
    )

    bot.start()
