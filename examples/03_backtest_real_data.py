"""
Backtest the ORB demo on REAL bars pulled from your firm via the API.

    cp .env.example .env   # set PROJECTX_USERNAME / PROJECTX_PASSWORD
    python examples/03_backtest_real_data.py

Skips gracefully if no credentials are set. This is the same Backtester as the synthetic demo —
only the data source changed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples.strategy_orb import OpeningRangeBreakout   # noqa: E402
from pxtrader import ProjectXClient, backtest_symbol      # noqa: E402


def main():
    if not os.environ.get("PROJECTX_USERNAME"):
        print("No credentials set (see .env.example) -- skipping the real-data backtest.")
        return

    px = ProjectXClient().connect()
    # Resolve the order contract id once (handy if you go on to trade it live):
    try:
        print("resolved contract id:", px.market_data.resolve_contract("MNQ"))
    except Exception as e:
        print("contract resolve note:", e)

    result = backtest_symbol(px, OpeningRangeBreakout(or_bars=30), "MNQ",
                             resolution=1, days=20, point_value=2.0, commission=1.24)
    print("ORB on ~20 real sessions of MNQ:")
    print("  " + result.summary())
    px.close()


if __name__ == "__main__":
    main()
