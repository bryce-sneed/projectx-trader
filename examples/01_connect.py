"""
Connect, list accounts, and pull recent bars.

Setup:
    cp .env.example .env   # fill in PROJECTX_USERNAME / PROJECTX_PASSWORD
    pip install -e .
    python examples/01_connect.py

Reads credentials from the environment. On Windows you can `set` them, or load a .env with
python-dotenv. This script only READS — it never places an order.
"""
import os
import time

from pxtrader import ProjectXClient


def main() -> None:
    if not os.environ.get("PROJECTX_USERNAME"):
        raise SystemExit("Set PROJECTX_USERNAME / PROJECTX_PASSWORD first (see .env.example).")

    px = ProjectXClient().connect()
    print("authenticated:", bool(px.token))

    accounts = px.list_accounts()
    print(f"\n{len(accounts)} account(s):")
    for a in accounts:
        kind = "SIM" if a.is_simulated else "LIVE"
        print(f"  [{kind}] {a.account_id}  {a.name}  ${a.balance:,.2f}")

    positions = px.open_positions()
    print(f"\nopen positions: {len(positions)}")

    now = int(time.time())
    bars = px.bars("MNQ", resolution=1, countback=20, start=now - 3600, end=now)
    if bars:
        last = bars[-1]
        print(f"\nMNQ last 1m bar @ {last.timestamp:%H:%M}: "
              f"O={last.open} H={last.high} L={last.low} C={last.close} V={last.volume}")

    px.close()


if __name__ == "__main__":
    main()
