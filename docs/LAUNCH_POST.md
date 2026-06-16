# Launch post drafts (post whenever you're ready — these are for you to send, not auto-posted)

Honest, no hype. Lead with the gap it fills. Link: https://github.com/bryce-sneed/projectx-trader

---

## r/algotrading (or r/Daytrading / prop-firm Discords)

**Title:** I open-sourced a Python framework for automating ProjectX/TopstepX prop accounts (bring your own strategy)

**Body:**
I run an automated futures bot on a TopStep account, and the most painful part was never the
strategy — it was the plumbing: a TopstepX/ProjectX API client, order execution that actually
matches the backtest, fill confirmation, position reconciliation, surviving restarts. Crypto has
freqtrade/nautilus for this; prop-firm futures has basically nothing.

So I pulled the *infrastructure* out of my own system and open-sourced it (MIT). It ships **no
strategy** — you bring that. What it gives you:

- A clean, typed **ProjectX/TopstepX REST client** (auth, bars, orders, accounts) that works across
  ProjectX firms, not hardcoded to one.
- A `Strategy` interface + an **offline backtester** (no broker needed) with conservative
  adverse-first exits and real stats.
- A reliability-first **live engine**: fill confirmation (polls the position, never assumes),
  reconciliation, broker-side protective stop, restart-recovery, hands-free run loop.
- The *same* strategy runs backtest and live unchanged.

`pip install -e .`, write a `Strategy`, `python examples/02_backtest.py` to see it work with zero
setup. Alpha and early — feedback, issues, and firm presets very welcome.

Repo: https://github.com/bryce-sneed/projectx-trader

*(Not financial advice; test on a SIM account first.)*

---

## X / Twitter (thread)

1/ Prop-firm futures trading exploded but the tooling is rough. Crypto has freqtrade; ProjectX/
TopstepX has ~nothing. So I open-sourced the framework I built for my own bot. MIT, bring your own
strategy 🧵 https://github.com/bryce-sneed/projectx-trader

2/ It's the *hard* part, not the alpha: a typed ProjectX/TopstepX API client + order execution that
matches your backtest. Fill confirmation, position reconciliation, restart-recovery — the stuff that
quietly blows up naive bots.

3/ Write one `Strategy` class → backtest it offline (no broker) → run it live unchanged. Same code,
same exit logic. `python examples/02_backtest.py` runs with zero setup.

4/ Ships zero trading edge — that stays yours. This is infrastructure. Early/alpha, MIT licensed,
PRs + firm presets welcome. ⭐ if it's useful.

---

## Show HN

**Title:** Show HN: pxtrader – open-source Python framework for ProjectX/TopstepX prop-firm bots

**Body:** I automate a TopStep futures account and the painful part was always the execution
plumbing, not the strategy. Open-sourced the infrastructure from my own bot (MIT): a typed
ProjectX/TopstepX client, a `Strategy` interface, an offline backtester, and a reliability-first
live engine (fill confirmation, reconciliation, restart-recovery). Ships no edge — bring your own.
Alpha. Feedback welcome.

---

### Posting notes
- Lead with the gap ("freqtrade for prop futures"), not features.
- Be upfront it's alpha + ships no strategy — sets honest expectations, avoids "where's the money printer" replies.
- Engage every early comment/issue fast — first impressions seed the repo.
- Best windows: weekday US mornings for r/algotrading; don't post all three the same hour.
