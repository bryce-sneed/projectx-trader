"""
The Strategy contract.

Subclass ``Strategy`` and implement ``on_bar``. Each closed bar, you receive a ``Context``
(bar history + whether you're in a position) and return a ``Signal`` to enter, or ``None`` to
do nothing. The stop/target/time-exit you put on the Signal are honored identically in backtest
and live, so a strategy that backtests well runs live unchanged.

This file contains NO trading edge — bring your own. See ``examples/strategy_orb.py`` for a
throwaway opening-range-breakout demo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dtime
from typing import List, Optional

from .models import Bar, Position, Side


@dataclass
class Signal:
    """A strategy's intent to open a position, with its protective bracket.

    The framework enters at the signal bar's close, then manages the exit by these levels
    (stop checked adverse-first, then target, then the optional intraday time-exit).
    """
    side: Side
    stop: float
    target: Optional[float] = None
    time_exit: Optional[dtime] = None   # exit at/after this time-of-day if still open
    size: int = 1
    tag: str = ""


@dataclass
class Context:
    """What a strategy sees on a bar: history (newest last) and current position state."""
    bars: List[Bar]
    in_position: bool = False
    position: Optional[Position] = None

    @property
    def bar(self) -> Bar:
        """The bar that just closed."""
        return self.bars[-1]

    def closes(self, n: Optional[int] = None) -> List[float]:
        """Last ``n`` closes (all if n is None) — convenience for indicators."""
        seq = [b.close for b in self.bars]
        return seq[-n:] if n else seq


class Strategy:
    """Base class. Override ``on_bar`` (required) and optionally ``on_start``."""
    name: str = "strategy"

    def on_start(self) -> None:
        """Called once before the first bar. Optional."""

    def on_bar(self, ctx: Context) -> Optional[Signal]:
        """Return a Signal to enter (when flat), or None. Called on every closed bar."""
        raise NotImplementedError("implement on_bar in your Strategy subclass")
