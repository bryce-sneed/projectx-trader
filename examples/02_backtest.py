"""
Backtest the example ORB strategy on synthetic bars — runnable with ZERO setup (no broker, no data).

    python examples/02_backtest.py

Swap the synthetic bars for real ones (e.g. ProjectXClient().bars(...) or your own CSV) and the
same Backtester + Strategy run unchanged.
"""
import os
import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples.strategy_orb import OpeningRangeBreakout   # noqa: E402
from pxtrader.backtest import Backtester                  # noqa: E402
from pxtrader.models import Bar                           # noqa: E402


def synth_day(day: int, start: float, n: int = 120, drift: float = 0.0, seed: int = 0):
    rnd = random.Random(seed)
    bars, price = [], start
    t0 = datetime(2026, 6, day, 9, 30, tzinfo=timezone.utc)
    for i in range(n):
        o = price
        c = o + rnd.uniform(-3, 3) + drift
        h = max(o, c) + rnd.uniform(0, 2)
        lo = min(o, c) - rnd.uniform(0, 2)
        bars.append(Bar(timestamp=t0 + timedelta(minutes=i), open=o, high=h, low=lo,
                        close=c, volume=rnd.randint(50, 200)))
        price = c
    return bars


def main():
    bars = []
    for d in range(1, 11):                      # 10 synthetic sessions, alternating drift
        bars += synth_day(d, 20_000 + d * 5, drift=0.5 if d % 2 == 0 else -0.4, seed=d)

    result = Backtester(point_value=2.0, commission=1.24).run(
        OpeningRangeBreakout(or_bars=30, target_r=1.0), bars)

    print("ORB on 10 synthetic sessions @ 1 MNQ ($2/pt):")
    print("  " + result.summary())
    print("\n  equity curve:")
    print(result.equity_curve())


if __name__ == "__main__":
    main()
