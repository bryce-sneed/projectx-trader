"""
Live runtime — a bar feed + run loop that drive a LiveBot hands-free.

The gateway's most recent bar is still forming, so the feed holds it back until a newer bar
confirms it closed; each poll yields only never-seen-before CLOSED bars. ``run_live`` warms the
strategy on history, recovers any existing position, then loops: poll -> step -> sleep.

    python -m pxtrader.runtime --strategy examples.strategy_orb:OpeningRangeBreakout \
        --symbol MNQ --symbol-id F.US.MNQ --size 1
"""
from __future__ import annotations

import time as _time
from typing import Callable, List, Optional

from .client import ProjectXClient
from .live import LiveBot
from .models import Bar
from .strategy import Strategy


class BarFeed:
    """Polls one symbol's bars and yields the ones that have closed since the last poll."""

    def __init__(self, client, symbol: str, *, resolution: int = 1, lookback: int = 60):
        self.client = client
        self.symbol = symbol
        self.resolution = resolution
        self.lookback = lookback
        self._last_ts = None

    def _fetch(self) -> List[Bar]:
        now = int(_time.time())
        span = self.resolution * 60 * (self.lookback + 5)
        bars = self.client.bars(self.symbol, resolution=self.resolution,
                                countback=self.lookback, start=now - span, end=now)
        return sorted(bars, key=lambda b: b.timestamp)

    def initial_history(self) -> List[Bar]:
        """Currently-closed bars for warmup. Marks them seen so they don't replay as live."""
        bars = self._fetch()
        closed = bars[:-1] if bars else []
        if closed:
            self._last_ts = closed[-1].timestamp
        return closed

    def poll(self) -> List[Bar]:
        """Bars closed since the last poll (the still-forming final bar is always excluded)."""
        bars = self._fetch()
        closed = bars[:-1] if bars else []
        new = [b for b in closed if self._last_ts is None or b.timestamp > self._last_ts]
        if new:
            self._last_ts = new[-1].timestamp
        return new


def run_live(client, strategy: Strategy, *, symbol: str, symbol_id: str, size: int = 1,
             resolution: int = 1, poll_seconds: float = 5.0, account_id: Optional[int] = None,
             lookback: int = 60, recovery_stop_points: Optional[float] = None,
             should_stop: Optional[Callable[[], bool]] = None,
             logger: Optional[Callable[[str], None]] = None) -> LiveBot:
    """Wire client + strategy + feed and run hands-free until ``should_stop()`` is true.

    Test on a SIMULATED account first. ``symbol`` feeds market data; ``symbol_id`` is the
    contract id orders are placed against (resolve it via ``client.market_data.symbol_details``).
    """
    log = logger or (lambda m: print(f"[runtime] {m}"))
    bot = LiveBot(client, strategy, symbol_id=symbol_id, size=size,
                  account_id=account_id, logger=logger)
    feed = BarFeed(client, symbol, resolution=resolution, lookback=lookback)

    bot.warmup(feed.initial_history())
    bot.recover(stop_points=recovery_stop_points)
    log(f"live: strategy={strategy.name} symbol={symbol} size={size} poll={poll_seconds}s")

    while not (should_stop and should_stop()):
        try:
            for bar in feed.poll():
                bot.step(bar)
        except Exception as e:  # keep the loop alive through transient gateway hiccups
            log(f"poll error: {e}")
        _time.sleep(poll_seconds)
    log("stopped")
    return bot


def _main() -> None:  # pragma: no cover - CLI wiring
    import argparse
    import importlib

    p = argparse.ArgumentParser(description="Run a pxtrader strategy live.")
    p.add_argument("--strategy", required=True,
                   help="module:Class, e.g. examples.strategy_orb:OpeningRangeBreakout")
    p.add_argument("--symbol", required=True, help="market-data symbol, e.g. MNQ")
    p.add_argument("--symbol-id", required=True, help="order contract id, e.g. F.US.MNQ")
    p.add_argument("--size", type=int, default=1)
    p.add_argument("--resolution", type=int, default=1)
    p.add_argument("--poll-seconds", type=float, default=5.0)
    p.add_argument("--firm", default=None)
    args = p.parse_args()

    mod_name, cls_name = args.strategy.split(":")
    strat_cls = getattr(importlib.import_module(mod_name), cls_name)
    client = ProjectXClient(firm=args.firm).connect()
    run_live(client, strat_cls(), symbol=args.symbol, symbol_id=args.symbol_id,
             size=args.size, resolution=args.resolution, poll_seconds=args.poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    _main()
