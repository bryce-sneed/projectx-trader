"""
Example strategy: Opening-Range Breakout (ORB).

A deliberately generic, public-domain demo of the Strategy interface — NOT a recommended edge,
just a clear teaching example. It builds the session's opening range (high/low of the first
``or_bars`` bars), then enters on the first close that breaks out, stops at the opposite end of
the range, and targets a multiple of the range width. One trade per day.

    from examples.strategy_orb import OpeningRangeBreakout
    from pxtrader.backtest import Backtester
    result = Backtester(point_value=2.0).run(OpeningRangeBreakout(), bars)
"""
from datetime import time as dtime

from pxtrader.models import Side
from pxtrader.strategy import Context, Signal, Strategy


class OpeningRangeBreakout(Strategy):
    name = "opening_range_breakout"

    def __init__(self, or_bars: int = 30, target_r: float = 1.0,
                 time_exit: dtime = dtime(15, 55)):
        self.or_bars = or_bars
        self.target_r = target_r
        self.time_exit = time_exit
        self._day = None
        self._or_high = 0.0
        self._or_low = 0.0
        self._bars_today = 0
        self._traded_today = False

    def on_bar(self, ctx: Context):
        bar = ctx.bar
        day = bar.timestamp.date()

        # new session -> reset the opening range
        if day != self._day:
            self._day = day
            self._or_high, self._or_low = bar.high, bar.low
            self._bars_today = 1
            self._traded_today = False
            return None

        self._bars_today += 1
        if self._bars_today <= self.or_bars:           # still forming the range
            self._or_high = max(self._or_high, bar.high)
            self._or_low = min(self._or_low, bar.low)
            return None

        if self._traded_today or ctx.in_position:
            return None

        rng = self._or_high - self._or_low
        if rng <= 0:
            return None

        if bar.close > self._or_high:
            self._traded_today = True
            return Signal(Side.BUY, stop=self._or_low,
                          target=bar.close + rng * self.target_r,
                          time_exit=self.time_exit, tag="ORB-long")
        if bar.close < self._or_low:
            self._traded_today = True
            return Signal(Side.SELL, stop=self._or_high,
                          target=bar.close - rng * self.target_r,
                          time_exit=self.time_exit, tag="ORB-short")
        return None
