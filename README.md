# pxtrader

**A Python client and automation framework for ProjectX-powered prop-firm futures platforms** — TopstepX today, any ProjectX gateway tomorrow.

> ⚠️ **Alpha (v0.1).** The API client foundation is landing first; the live bot loop and backtest harness follow on the roadmap below. Built and maintained by [NQBryce](https://github.com/bryce-sneed) — an engineer who runs a live automated futures system on this exact API every trading day.

---

## Why this exists

Prop-firm futures trading has exploded, but the tooling is rough. Most people who want to automate a TopstepX/ProjectX account end up hand-rolling a fragile HTTP client, then hit the wall that quietly kills most trading bots:

- the bot *thinks* it's filled but the order is still working,
- a reconnect leaves order state and position state disagreeing,
- a restart orphans a protective stop and leaves a position naked,
- and the backtest that looked great doesn't match what happens live.

`pxtrader` is the infrastructure for that hard part — a clean, typed client and a reliability-first execution layer — so you can spend your time on your edge instead of on plumbing.

**This is a framework, not a strategy.** It ships zero alpha. You bring the strategy; it handles auth, market data, order execution, position reconciliation, and staying alive.

## Features

**v0.1 (now) — REST client**
- 🔑 Auth: username/password login → bearer token, attached to every request.
- 📈 Market data: historical + live OHLC bars (returned as clean `Bar` objects), contract search.
- 🧾 Orders: market / limit / stop placement and cancel, with the gateway's order-type codes handled for you.
- 👤 Accounts: list accounts, open positions, order history.
- 🔌 Swappable firm config — the same client works across ProjectX firms, not hardcoded to one.
- 🔐 **SSL verification on by default** (and secrets only in `.env`) — the kind of hardening a public client should ship with.

**On the roadmap**
- 🧰 Bracket (stop+target) management, contract/tick resolution, fill & filled-trade sync.
- 🛡️ Reliability layer: fast fill confirmation, order/position reconciliation, restart-recovery, watchdog auto-restart, kill switch.
- 🧪 Backtest harness: run a strategy over 1-minute history with the *same* engine that trades it live (no drifted re-implementation).
- 🤖 `Strategy` interface + a worked example strategy.

## Install

```bash
git clone https://github.com/bryce-sneed/projectx-trader.git
cd projectx-trader
pip install -e .
cp .env.example .env   # then fill in your credentials
```

## Quickstart

```python
from pxtrader import ProjectXClient, Side

# Credentials from env (PROJECTX_USERNAME / PROJECTX_PASSWORD / PROJECTX_FIRM), or pass them in.
px = ProjectXClient().connect()

# Accounts + positions
for a in px.list_accounts():
    print(a.account_id, a.name, f"${a.balance:,.2f}", "sim" if a.is_simulated else "live")
print("open positions:", px.open_positions())

# Market data — recent 1-minute bars
import time
now = int(time.time())
bars = px.bars("MNQ", resolution=1, countback=50, start=now - 3600, end=now)
print(bars[-1].close)

# Place a stop order (resolve the contract's symbol_id first)
details = px.market_data.symbol_details("MNQ")
# px.place_market_order(symbol_id=<id>, side=Side.BUY, quantity=1)   # do this on a SIM account first!
```

> Always test on a simulated/practice account before going anywhere near a live one.

## Bring your own strategy

`pxtrader` deliberately contains **no trading strategies**. The forthcoming `Strategy` interface is a thin contract — you receive bars and account state, you return order intents; the framework executes and manages them reliably. Your edge stays yours.

## Supported firms

Any platform on the **ProjectX** gateway. `topstepx` ships as the default preset; adding another firm is a few lines in `pxtrader/config.py`. PRs welcome.

## Disclaimer

Trading futures carries substantial risk of loss and is not suitable for everyone. This software is provided "as is", without warranty of any kind. Nothing here is financial advice. You are solely responsible for any orders it places on your account. Test on a simulated/practice account first.

## License

MIT © 2026 Bryce Sneed
