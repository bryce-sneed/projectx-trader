"""
Backtest harness — run a Strategy over historical bars, no broker required.

The strategy returns Signals; the harness enters at the signal bar's close and manages the exit
with the SAME bracket levels a live bot would place: stop is checked adverse-first (the
conservative intrabar assumption), then target, then the optional time-exit. One position at a
time (re-entry only after the prior trade closes), mirroring real serialized execution.

    from pxtrader.backtest import Backtester
    result = Backtester(point_value=2.0, commission=1.24).run(my_strategy, bars)
    print(result.summary())
"""
from __future__ import annotations

import statistics as st
import time as _time
from dataclasses import dataclass, field
from typing import List, Optional

from .models import Bar, Side
from .strategy import Context, Signal, Strategy


@dataclass
class ClosedTrade:
    side: Side
    entry_price: float
    exit_price: float
    entry_time: object
    exit_time: object
    size: int
    pnl: float
    reason: str
    tag: str = ""


@dataclass
class BacktestResult:
    trades: List[ClosedTrade] = field(default_factory=list)
    point_value: float = 1.0

    @property
    def n(self) -> int:
        return len(self.trades)

    @property
    def net_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def wins(self) -> List[float]:
        return [t.pnl for t in self.trades if t.pnl > 0]

    @property
    def win_rate(self) -> float:
        return len(self.wins) / self.n * 100 if self.n else 0.0

    @property
    def profit_factor(self) -> float:
        gross_win = sum(p for p in (t.pnl for t in self.trades) if p > 0)
        gross_loss = -sum(p for p in (t.pnl for t in self.trades) if p < 0)
        return (gross_win / gross_loss) if gross_loss else float("inf")

    @property
    def max_drawdown(self) -> float:
        cum = peak = mdd = 0.0
        for t in self.trades:
            cum += t.pnl
            peak = max(peak, cum)
            mdd = min(mdd, cum - peak)
        return mdd

    def summary(self) -> str:
        if not self.n:
            return "no trades"
        pnls = [t.pnl for t in self.trades]
        return (
            f"trades={self.n}  net=${self.net_pnl:,.2f}  win%={self.win_rate:.0f}  "
            f"avg=${st.mean(pnls):,.2f}  PF={self.profit_factor:.2f}  maxDD=${self.max_drawdown:,.2f}"
        )

    def equity_curve(self, height: int = 8, width: int = 60) -> str:
        """A small ASCII cumulative-equity chart for quick terminal feedback (ASCII-only)."""
        if not self.trades:
            return "(no trades)"
        cum, s = [], 0.0
        for t in self.trades:
            s += t.pnl
            cum.append(s)
        n = len(cum)
        pts = ([cum[round(i * (n - 1) / (width - 1))] for i in range(width)]
               if n > 1 else cum * width)
        hi, lo = max(pts + [0.0]), min(pts + [0.0])
        rng = (hi - lo) or 1.0
        rows = []
        for r in range(height):
            level = hi - (r + 0.5) * rng / height
            rows.append(f"{level:8.0f} |" + "".join("*" if p >= level else " " for p in pts))
        rows.append(f"{'':8} +" + "-" * len(pts))
        return "\n".join(rows)


@dataclass
class _Open:
    side: Side
    entry_price: float
    entry_time: object
    stop: float
    target: Optional[float]
    time_exit: object
    size: int
    tag: str


class Backtester:
    """Event-driven, one-position-at-a-time backtest."""

    def __init__(self, point_value: float = 1.0, commission: float = 0.0):
        self.point_value = point_value
        self.commission = commission

    def _check_exit(self, pos: _Open, bar: Bar):
        """Return (exit_price, reason) or (None, None). Stop is adverse-first (conservative)."""
        is_long = pos.side is Side.BUY
        if (is_long and bar.low <= pos.stop) or (not is_long and bar.high >= pos.stop):
            return pos.stop, "stop"
        if pos.target is not None and (
            (is_long and bar.high >= pos.target) or (not is_long and bar.low <= pos.target)
        ):
            return pos.target, "target"
        if pos.time_exit is not None and bar.timestamp.time() >= pos.time_exit:
            return bar.close, "time"
        return None, None

    def _pnl(self, side: Side, entry: float, exit_: float, size: int) -> float:
        pts = (exit_ - entry) if side is Side.BUY else (entry - exit_)
        return pts * self.point_value * size - self.commission * size

    def run(self, strategy: Strategy, bars: List[Bar]) -> BacktestResult:
        strategy.on_start()
        result = BacktestResult(point_value=self.point_value)
        history: List[Bar] = []
        pos: Optional[_Open] = None
        entry_idx = -1

        for i, bar in enumerate(bars):
            history.append(bar)

            # manage an open position on bars AFTER the entry bar
            if pos is not None and i > entry_idx:
                exit_price, reason = self._check_exit(pos, bar)
                if exit_price is not None:
                    result.trades.append(ClosedTrade(
                        side=pos.side, entry_price=pos.entry_price, exit_price=exit_price,
                        entry_time=pos.entry_time, exit_time=bar.timestamp, size=pos.size,
                        pnl=self._pnl(pos.side, pos.entry_price, exit_price, pos.size),
                        reason=reason, tag=pos.tag,
                    ))
                    pos = None

            # look for a new entry only when flat
            if pos is None:
                sig = strategy.on_bar(Context(bars=history, in_position=False, position=None))
                if sig is not None:
                    pos = _Open(side=sig.side, entry_price=bar.close, entry_time=bar.timestamp,
                                stop=sig.stop, target=sig.target, time_exit=sig.time_exit,
                                size=sig.size, tag=sig.tag)
                    entry_idx = i

        # close anything still open at the last bar
        if pos is not None and bars:
            last = bars[-1]
            result.trades.append(ClosedTrade(
                side=pos.side, entry_price=pos.entry_price, exit_price=last.close,
                entry_time=pos.entry_time, exit_time=last.timestamp, size=pos.size,
                pnl=self._pnl(pos.side, pos.entry_price, last.close, pos.size),
                reason="eod", tag=pos.tag,
            ))
        return result


def backtest_symbol(client, strategy: Strategy, symbol: str, *, resolution: int = 1,
                    days: int = 30, point_value: float = 1.0, commission: float = 0.0) -> BacktestResult:
    """Convenience: fetch recent real bars for ``symbol`` via the client and backtest ``strategy``.

        from pxtrader import ProjectXClient, backtest_symbol
        r = backtest_symbol(ProjectXClient().connect(), MyStrategy(), "MNQ", days=30, point_value=2.0)
    """
    now = int(_time.time())
    start = now - days * 86_400
    bars = client.bars(symbol, resolution=resolution, countback=days * 24 * 60 // resolution,
                       start=start, end=now)
    return Backtester(point_value=point_value, commission=commission).run(strategy, bars)
