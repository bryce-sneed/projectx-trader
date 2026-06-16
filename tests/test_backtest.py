"""
Backtest engine tests — exit logic (adverse-first stop, target, time), P&L math, and the ORB demo.

    pytest tests/test_backtest.py -v
"""
from datetime import datetime, time as dtime, timezone

from pxtrader.backtest import Backtester
from pxtrader.models import Bar, Side
from pxtrader.strategy import Context, Signal, Strategy


def _bar(close, high=None, low=None, op=None, hh=9, mm=30, day=1):
    ts = datetime(2026, 6, day, hh, mm, tzinfo=timezone.utc)
    return Bar(timestamp=ts, open=op if op is not None else close,
               high=high if high is not None else close,
               low=low if low is not None else close, close=close)


class _EnterOnce(Strategy):
    """Signals exactly once (first flat bar) so single-trade exits can be tested."""
    def __init__(self, side, stop, target=None, time_exit=None, size=1):
        self.side, self.stop, self.target, self.time_exit = side, stop, target, time_exit
        self.size = size
        self.fired = False

    def on_bar(self, ctx: Context):
        if self.fired:
            return None
        self.fired = True
        return Signal(self.side, stop=self.stop, target=self.target,
                      time_exit=self.time_exit, size=self.size)


def test_stop_exit_long():
    bars = [_bar(100, mm=30), _bar(100, high=101, low=94, mm=31)]  # bar1 hits stop 95
    r = Backtester(point_value=2.0).run(_EnterOnce(Side.BUY, stop=95, target=110), bars)
    assert r.n == 1 and r.trades[0].reason == "stop"
    assert r.trades[0].exit_price == 95 and r.trades[0].pnl == (95 - 100) * 2


def test_target_exit_long():
    bars = [_bar(100, mm=30), _bar(105, high=111, low=99, mm=31)]  # bar1 hits target 110
    r = Backtester(point_value=2.0).run(_EnterOnce(Side.BUY, stop=95, target=110), bars)
    assert r.n == 1 and r.trades[0].reason == "target"
    assert r.trades[0].pnl == (110 - 100) * 2


def test_adverse_first_when_stop_and_target_in_same_bar():
    # bar1 range spans BOTH stop(95) and target(110); conservative model takes the stop.
    bars = [_bar(100, mm=30), _bar(105, high=111, low=94, mm=31)]
    r = Backtester(point_value=2.0).run(_EnterOnce(Side.BUY, stop=95, target=110), bars)
    assert r.trades[0].reason == "stop" and r.trades[0].pnl == (95 - 100) * 2


def test_time_exit():
    bars = [_bar(100, mm=30), _bar(105, high=106, low=104, hh=15, mm=55)]
    r = Backtester(point_value=2.0).run(
        _EnterOnce(Side.BUY, stop=90, target=120, time_exit=dtime(15, 55)), bars)
    assert r.trades[0].reason == "time" and r.trades[0].exit_price == 105


def test_short_stop_and_pnl_with_commission_and_size():
    bars = [_bar(100, mm=30), _bar(100, high=106, low=99, mm=31)]  # short stop 105 hit
    r = Backtester(point_value=2.0, commission=1.24).run(
        _EnterOnce(Side.SELL, stop=105, target=80, size=3), bars)
    t = r.trades[0]
    assert t.reason == "stop"
    assert abs(t.pnl - ((100 - 105) * 2 * 3 - 1.24 * 3)) < 1e-9


def test_one_position_at_a_time():
    # _EnterOnce only fires once; even across many flat bars there is at most one trade.
    bars = [_bar(100, mm=30 + i) for i in range(5)]
    r = Backtester().run(_EnterOnce(Side.BUY, stop=90), bars)
    assert r.n == 1  # entered once, closed at EOD


def test_orb_long_breakout():
    from examples.strategy_orb import OpeningRangeBreakout
    # 3-bar opening range 100-102, then a breakout close above 102 -> long.
    bars = [_bar(101, high=102, low=100, mm=30),
            _bar(101, high=102, low=100, mm=31),
            _bar(101, high=102, low=100, mm=32),
            _bar(103, high=103, low=101, mm=33),   # breakout close > OR high
            _bar(105, high=106, low=104, mm=34)]
    r = Backtester(point_value=2.0).run(OpeningRangeBreakout(or_bars=3, target_r=1.0), bars)
    assert r.n == 1 and r.trades[0].side is Side.BUY


def test_equity_curve_renders_ascii():
    bars = [_bar(100, mm=30), _bar(105, high=111, low=99, mm=31)]
    r = Backtester(point_value=2.0).run(_EnterOnce(Side.BUY, stop=95, target=110), bars)
    curve = r.equity_curve(height=5)
    assert curve.count("\n") == 5 and curve.isascii()        # height rows + axis, ASCII only


def test_equity_curve_empty():
    assert Backtester().run(_EnterOnce(Side.BUY, stop=95), []).equity_curve() == "(no trades)"
