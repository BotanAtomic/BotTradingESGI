from datetime import datetime
from const import *


def wrap_html_color(message, color):
    return F"<span style=\"color:{color}\">{message}</span>"


class Logger:
    logs = []

    def log(self, type, message):
        message = F"<b>[{datetime.now().strftime('%Y/%m/%d %H:%M')} - {type.upper()}]</b>: {message}"
        self.logs.append(message)

    def buy_log(self, entry_price, position_size):
        self.log("trade", F"{wrap_html_color('BUY', 'green')} at <b><i>{entry_price}$</i></b>, position size: <b>"
                          F"{position_size}</b>")

    def sell_log(self, close_price, pnl, current_balance):
        self.log("trade", F"{wrap_html_color('SELL', 'red')} at <b><i>{close_price}$</i></b>,"
                          F" P&L: <b>{wrap_html_color(F'{pnl}$', 'green' if pnl > 0 else 'red')}</b>"
                          F" current balance: <b>{current_balance}$</b>")

    def trend_log(self, last_trend, trend):
        self.log("event", f"trend change detected: "
                          f"<b>{wrap_html_color(TREND_NAMES[last_trend], TREND_COLORS[last_trend])} -> "
                          f"{wrap_html_color(TREND_NAMES[trend], TREND_COLORS[trend])}</b>")

    def init_log(self, message):
        self.log("initialization", message)

    def get_logs(self):
        return self.logs
