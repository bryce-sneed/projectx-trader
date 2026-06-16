"""
Runtime tests — BarFeed closed-bar logic, warmup (no trading), and restart-recovery. No network.

    pytest tests/test_runtime.py -v
"""
from datetime import datetime, timezone

from pxtrader.live import LiveBot
from pxtrader.models import Bar, Side
from pxtrader.orders import OrderResult
from pxtrader.runtime import BarFeed
from pxtrader.strategy import Signal, Strategy


def _bar(i: int, close: float = 100.0) -> Bar:
    return Bar(timestamp=datetime(2026, 6, 15, 9, 30 + i, tzinfo=timezone.utc),
               open=close, high=close, low=close, close=close)


class _FakeData:
    def __init__(self):
        self.bars_list = []

    def bars(self, symbol, *, resolution, countback, start, end):
        return list(self.bars_list)


class _FakeClient:
    def __init__(self, start_pos=None):
        self.account_id = 1
        self._pos = start_pos
        self.calls = []

    def open_positions(self, account_id=None):
        return [self._pos] if self._pos else []

    def place_market_order(self, symbol_id, side, size, account_id=None, tag=""):
        self.calls.append(("market", tag))
        return OrderResult(order_id=1)

    def place_stop_order(self, symbol_id, side, size, stop_price, account_id=None, tag=""):
        self.calls.append(("stop", stop_price, tag))
        return OrderResult(order_id=222)

    def cancel_order(self, order_id, account_id=None):
        self.calls.append(("cancel", order_id))
        return {}


class _SignalEvery(Strategy):
    def __init__(self):
        self.calls = 0

    def on_bar(self, ctx):
        self.calls += 1
        return Signal(Side.BUY, stop=90.0)


def test_feed_initial_history_excludes_forming_bar():
    d = _FakeData(); d.bars_list = [_bar(0), _bar(1), _bar(2)]
    hist = BarFeed(d, "MNQ").initial_history()
    assert [b.timestamp for b in hist] == [_bar(0).timestamp, _bar(1).timestamp]


def test_feed_poll_yields_only_new_closed_bars():
    d = _FakeData(); d.bars_list = [_bar(0), _bar(1), _bar(2)]
    feed = BarFeed(d, "MNQ"); feed.initial_history()       # b0,b1 seen; b2 forming
    d.bars_list = [_bar(0), _bar(1), _bar(2), _bar(3)]      # b2 closed, b3 forming
    assert [b.timestamp for b in feed.poll()] == [_bar(2).timestamp]
    assert feed.poll() == []                               # nothing newer
    d.bars_list.append(_bar(4))
    assert [b.timestamp for b in feed.poll()] == [_bar(3).timestamp]


def test_warmup_builds_state_without_trading():
    c = _FakeClient(); strat = _SignalEvery()
    bot = LiveBot(c, strat, "MNQ", logger=lambda m: None)
    bot.warmup([_bar(0), _bar(1), _bar(2)])
    assert strat.calls == 3 and len(bot.history) == 3
    assert bot.active is None
    assert not any(x[0] == "market" for x in c.calls)      # zero orders during warmup


def test_recover_adopts_position_and_places_stop():
    c = _FakeClient(start_pos={"symbolId": "MNQ", "size": 2, "avg_price": 100.0})
    bot = LiveBot(c, _SignalEvery(), "MNQ", logger=lambda m: None)
    bot.recover(stop_points=25.0)
    assert bot.active is not None and bot.active.side is Side.BUY and bot.active.size == 2
    assert bot.active.entry_price == 100.0
    assert ("stop", 75.0, "recovery-stop") in c.calls      # 100 - 25 for a long


def test_recover_noop_when_flat():
    bot = LiveBot(_FakeClient(), _SignalEvery(), "MNQ", logger=lambda m: None)
    bot.recover()
    assert bot.active is None
