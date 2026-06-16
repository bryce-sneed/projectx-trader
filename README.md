# pxtrader

**A Python client and automation framework for ProjectX-powered prop-firm futures platforms** — TopstepX today, any ProjectX gateway tomorrow.

> ⚠️ **Alpha (v0.3).** REST client + a `Strategy` framework (offline backtester, reliability-first live engine, hands-free runtime with restart-recovery). A watchdog/kill-switch and richer order tooling follow on the roadmap. Built and maintained by [NQBryce](https://github.com/bryce-sneed) — an engineer who runs a live automated futures system on this exact API every trading day.

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

**REST client**
- 🔑 Auth: username/password login → bearer token, attached to every request.
- 📈 Market data: historical + live OHLC bars (clean `Bar` objects), contract search.
- 🧾 Orders: market / limit / stop placement and cancel, gateway order-type codes handled for you.
- 👤 Accounts: list accounts, open positions, order history.
- 🔌 Swappable firm config — the same client works across ProjectX firms, not hardcoded to one.
- 🔐 **SSL verification on by default** (secrets only in `.env`) — the hardening a public client should ship with.

**Strategy framework**
- 🤖 `Strategy` interface — receive bars + position state, return a `Signal` (side + stop + target + time-exit).
- 🧪 `Backtester` — run any strategy over historical bars with **no broker**, conservative adverse-first exits, full stats (P&L, win%, profit factor, max drawdown). The *same* `Strategy` runs live unchanged.
- 🛡️ `LiveBot` — fill confirmation (polls the position, never assumes), reconciliation (self-heals against the broker's truth), broker-side protective stop, verify-before-close.
- 🔁 **Hands-free runtime** — `BarFeed` + `run_live` drive the bot on closing bars, with **warmup** (build indicator state without trading) and **restart-recovery** (adopt an existing position so a restart never double-enters). One-command CLI: `python -m pxtrader.runtime …`.
- 📊 **Backtest on real data** in one call: `backtest_symbol(client, strategy, "MNQ", days=30)`.

**On the roadmap**
- 🧰 Bracket modify (SL/TP) + true OCO, fill & filled-trade sync.
- 🦺 Watchdog auto-restart + kill switch.

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

## Write & backtest a strategy

`pxtrader` ships **no trading edge** — you bring it. A strategy is a thin contract: receive bars + position state, return a `Signal`. The same strategy backtests offline and runs live unchanged.

```python
from pxtrader import Strategy, Signal, Side, Backtester

class Breakout(Strategy):
    def on_bar(self, ctx):
        closes = ctx.closes(20)
        if len(closes) < 20:
            return None
        if ctx.bar.close > max(closes[:-1]):           # 20-bar high breakout
            return Signal(Side.BUY, stop=min(closes), target=ctx.bar.close + 50)
        return None

# Backtest offline — no broker, no API key:
result = Backtester(point_value=2.0, commission=1.24).run(Breakout(), bars)
print(result.summary())   # trades=…  net=$…  win%=…  PF=…  maxDD=$…

# Run it live (test on a SIM account first):
# from pxtrader import ProjectXClient, LiveBot
# px = ProjectXClient().connect()
# bot = LiveBot(px, Breakout(), symbol_id="<contract id>", size=1)
# bot.step(latest_closed_bar)   # call when each bar closes
```

Try it now with zero setup: `python examples/02_backtest.py` (the ORB demo on synthetic data).
Your edge stays yours — see [`docs/FRAMEWORK_VS_EDGE.md`](docs/FRAMEWORK_VS_EDGE.md).

## Supported firms

Any platform on the **ProjectX** gateway. `topstepx` ships as the default preset; adding another firm is a few lines in `pxtrader/config.py`. PRs welcome.

## Disclaimer

Trading futures carries substantial risk of loss and is not suitable for everyone. This software is provided "as is", without warranty of any kind. Nothing here is financial advice. You are solely responsible for any orders it places on your account. Test on a simulated/practice account first.

## License

MIT © 2026 Bryce Sneed
