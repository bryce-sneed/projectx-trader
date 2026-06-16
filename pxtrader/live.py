"""
Live bot engine — drive a Strategy against a real ProjectX account, reliably.

Same Strategy + Signal as the backtester, so a strategy you validated offline runs live unchanged.
The engine's value is the execution discipline that quietly kills naive bots:

  - **fill confirmation** — after an entry it POLLS the position until it actually appears
    (fast-poll), never assuming a market order filled;
  - **reconciliation** — every bar it checks the broker's real position against its own state and
    self-heals (broker flat but we think we're in -> clear; unmanaged broker position -> don't pile on);
  - **protective stop at the broker** as a disconnect/gap backstop, with target + time-exit managed
    in-loop and a verify-before-close guard so a redundant exit never opens the opposite side.

Alpha: you own the bar feed + scheduling — call ``step(bar)`` when a bar closes. Test on a
SIMULATED account first.
"""
from __future__ import annotations

import time as _time
from dataclasses import dataclass
from datetime import time as dtime
from typing import Callable, List, Optional

from .client import ProjectXClient
from .models import Bar, Side
from .strategy import Context, Signal, Strategy


@dataclass
class _Active:
    side: Side
    entry_price: float
    stop: Optional[float]
    target: Optional[float]
    time_exit: Optional[dtime]
    size: int
    stop_order_id: Optional[int] = None
    tag: str = ""


class LiveBot:
    def __init__(self, client: ProjectXClient, strategy: Strategy, symbol_id: str, *,
                 size: int = 1, account_id: Optional[int] = None,
                 fill_timeout: float = 5.0, poll_interval: float = 0.3,
                 logger: Optional[Callable[[str], None]] = None):
        self.client = client
        self.strategy = strategy
        self.symbol_id = symbol_id
        self.size = size
        self.account_id = account_id if account_id is not None else client.account_id
        self.fill_timeout = fill_timeout
        self.poll_interval = poll_interval
        self.log = logger or (lambda m: print(f"[LiveBot] {m}"))
        self.history: List[Bar] = []
        self.active: Optional[_Active] = None
        self._started = False

    # ── reliability helpers ──────────────────────────────────────────────────
    def _broker_position(self):
        """The account's live open position for our symbol, or None (reconciliation source)."""
        for p in self.client.open_positions(self.account_id):
            size = p.get("size") or p.get("positionSize") or 0
            sym = f"{p.get('symbolId', '')}{p.get('symbol_name', '')}{p.get('symbolName', '')}"
            if size and self.symbol_id in str(sym):
                return p
        return None

    def _confirm_fill(self):
        """Poll the position after an entry until it appears, or give up at the timeout."""
        deadline = _time.time() + self.fill_timeout
        while _time.time() < deadline:
            pos = self._broker_position()
            if pos:
                return pos
            _time.sleep(self.poll_interval)
        return None

    # ── per-bar processing ───────────────────────────────────────────────────
    def step(self, bar: Bar) -> None:
        """Process one freshly-closed bar."""
        if not self._started:
            self.strategy.on_start()
            self._started = True
        self.history.append(bar)

        broker_pos = self._broker_position()

        # reconcile: our state vs the broker's truth
        if self.active and not broker_pos:
            self.log("broker is flat (stop/target filled) -> clearing local position")
            self._cancel_stop()
            self.active = None
        if self.active:
            self._manage_exit(bar)
            return
        if broker_pos:
            self.log("broker shows an unmanaged position -> not entering on top of it")
            return

        sig = self.strategy.on_bar(Context(bars=self.history, in_position=False))
        if sig is not None:
            self._enter(bar, sig)

    def _enter(self, bar: Bar, sig: Signal) -> None:
        self.log(f"entry signal {sig.side.value} {self.size} ~{bar.close}")
        self.client.place_market_order(self.symbol_id, sig.side, self.size,
                                       account_id=self.account_id, tag=sig.tag)
        pos = self._confirm_fill()
        if not pos:
            self.log("FILL NOT CONFIRMED within timeout -> flattening to be safe")
            self._flatten(sig.side)
            return
        fill = float(pos.get("avg_price") or pos.get("averagePrice") or bar.close)
        stop_id = None
        try:
            r = self.client.place_stop_order(self.symbol_id, sig.side.opposite, self.size,
                                             sig.stop, account_id=self.account_id, tag="stop")
            stop_id = getattr(r, "order_id", None)
        except Exception as e:  # pragma: no cover - broker-specific
            self.log(f"protective stop failed ({e}) -> managing exit in-loop only")
        self.active = _Active(sig.side, fill, sig.stop, sig.target, sig.time_exit,
                              self.size, stop_id, sig.tag)
        self.log(f"in {sig.side.value} @ {fill} | stop {sig.stop} target {sig.target}")

    def _manage_exit(self, bar: Bar) -> None:
        a = self.active
        is_long = a.side is Side.BUY
        hit_target = a.target is not None and (
            (is_long and bar.high >= a.target) or (not is_long and bar.low <= a.target))
        hit_time = a.time_exit is not None and bar.timestamp.time() >= a.time_exit
        if hit_target or hit_time:
            self.log(f"exit ({'target' if hit_target else 'time'}) -> closing")
            self._flatten(a.side)
            self._cancel_stop()
            self.active = None

    def _flatten(self, side: Side) -> None:
        # verify-before-close: never market-close a flat account (would open the opposite side)
        if self._broker_position():
            self.client.place_market_order(self.symbol_id, side.opposite, self.size,
                                           account_id=self.account_id, tag="exit")

    def _cancel_stop(self) -> None:
        if self.active and self.active.stop_order_id is not None:
            try:
                self.client.cancel_order(self.active.stop_order_id, self.account_id)
            except Exception:  # pragma: no cover
                pass

    # ── startup ──────────────────────────────────────────────────────────────
    def warmup(self, bars: List[Bar]) -> None:
        """Replay historical CLOSED bars so the strategy builds its state (indicators, ranges)
        WITHOUT placing any orders — signals during warmup are discarded."""
        if not self._started:
            self.strategy.on_start()
            self._started = True
        for bar in bars:
            self.history.append(bar)
            self.strategy.on_bar(Context(bars=self.history,
                                         in_position=self.active is not None, position=None))
        self.log(f"warmed up on {len(bars)} bars")

    def recover(self, stop_points: Optional[float] = None) -> None:
        """Adopt an existing broker position on startup so a restart never loses track of it.

        The original stop/target intent can't survive a restart. Pass ``stop_points`` to place a
        fresh protective stop at entry +/- that distance; otherwise a loud warning is logged and you
        should confirm a broker stop is already in place.
        """
        if self.active is not None:
            return
        pos = self._broker_position()
        if not pos:
            return
        size = int(pos.get("size") or pos.get("positionSize") or 0)
        if size == 0:
            return
        side = Side.BUY if size > 0 else Side.SELL
        entry = float(pos.get("avg_price") or pos.get("averagePrice") or 0.0)
        stop, stop_id = None, None
        if stop_points:
            stop = entry - stop_points if side is Side.BUY else entry + stop_points
            try:
                r = self.client.place_stop_order(self.symbol_id, side.opposite, abs(size), stop,
                                                 account_id=self.account_id, tag="recovery-stop")
                stop_id = getattr(r, "order_id", None)
            except Exception as e:  # pragma: no cover
                self.log(f"recovery stop failed ({e})")
        else:
            self.log("WARNING: recovered a position with NO known stop -- verify a broker stop exists")
        self.active = _Active(side, entry, stop, None, None, abs(size), stop_id, "recovered")
        self.log(f"recovered {side.value} {abs(size)} @ {entry}")
