"""
LiveBot reliability tests with a fake client (no network).

Covers the execution discipline that matters: fill confirmation, protective-stop placement,
target exit + verify-before-close, broker-flat reconciliation, the unmanaged-position guard,
and the unconfirmed-fill safety flatten.

    pytest tests/test_live.py -v
"""
from datetime import datetime, time as dtime, timezone

from pxtrader.live import LiveBot
from pxtrader.models import Bar, Side
from pxtrader.orders import OrderResult
from pxtrader.strategy import Signal, Strategy


def _bar(close, high=None, low=None, hh=9, mm=30):
    return Bar(timestamp=datetime(2026, 6, 15, hh, mm, tzinfo=timezone.utc),
               open=close, high=high if high is not None else close,
               low=low if low is not None else close, close=close)


class _FakeClient:
    def __init__(self, confirm_fills=True, start_pos=None):
        self.account_id = 1
        self.confirm_fills = confirm_fills
        self._pos = start_pos
        self.calls = []

    def open_positions(self, account_id=None):
        return [self._pos] if self._pos else []

    def place_market_order(self, symbol_id, side, size, account_id=None, tag=""):
        self.calls.append(("market", side, size, tag))
        if tag == "exit":
            self._pos = None
        elif self.confirm_fills:
            self._pos = {"symbolId": symbol_id,
                         "size": size if side is Side.BUY else -size, "avg_price": 100.0}
        return OrderResult(order_id=111, result=0)

    def place_stop_order(self, symbol_id, side, size, stop_price, account_id=None, tag=""):
        self.calls.append(("stop", side, stop_price))
        return OrderResult(order_id=222, result=0)

    def cancel_order(self, order_id, account_id=None):
        self.calls.append(("cancel", order_id))
        return {}


class _BuyOnce(Strategy):
    def __init__(self):
        self.fired = False

    def on_bar(self, ctx):
        if self.fired:
            return None
        self.fired = True
        return Signal(Side.BUY, stop=95.0, target=110.0, time_exit=dtime(15, 55))


def _bot(client, **kw):
    return LiveBot(client, _BuyOnce(), "MNQ", size=2, logger=lambda m: None, **kw)


def test_entry_confirms_fill_and_places_protective_stop():
    c = _FakeClient()
    bot = _bot(c)
    bot.step(_bar(100))
    assert bot.active is not None and bot.active.side is Side.BUY
    assert ("stop", Side.SELL, 95.0) in c.calls       # stop on the opposite side
    assert bot.active.stop_order_id == 222


def test_target_exit_flattens_and_cancels_stop():
    c = _FakeClient()
    bot = _bot(c)
    bot.step(_bar(100))                                # enter
    bot.step(_bar(109, high=111, low=108))            # target 110 hit
    assert bot.active is None
    assert ("market", Side.SELL, 2, "exit") in c.calls
    assert ("cancel", 222) in c.calls


def test_reconcile_clears_when_broker_flat():
    c = _FakeClient()
    bot = _bot(c)
    bot.step(_bar(100))                                # enter
    c._pos = None                                      # broker stop filled out-of-band
    bot.step(_bar(101))
    assert bot.active is None
    assert ("cancel", 222) in c.calls
    # no redundant exit order was sent (broker was already flat)
    assert ("market", Side.SELL, 2, "exit") not in c.calls


def test_no_entry_on_unmanaged_broker_position():
    c = _FakeClient(start_pos={"symbolId": "MNQ", "size": 1, "avg_price": 100.0})
    bot = _bot(c)
    bot.step(_bar(100))
    assert bot.active is None
    assert not any(t == "market" and tag != "exit" for (t, _s, _n, tag) in
                   [(c[0], None, None, c[3]) for c in c.calls if c[0] == "market"])


def test_unconfirmed_fill_stays_flat():
    c = _FakeClient(confirm_fills=False)
    bot = _bot(c, fill_timeout=0.0)
    bot.step(_bar(100))
    assert bot.active is None                          # never marked in-position
    assert ("market", Side.BUY, 2, "") in c.calls     # entry was attempted...
    assert ("market", Side.SELL, 2, "exit") not in c.calls  # ...but no phantom flatten (was flat)
