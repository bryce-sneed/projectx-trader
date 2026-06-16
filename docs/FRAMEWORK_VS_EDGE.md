# Framework vs. Edge — extraction & sanitization boundary

This project is extracted from a private, live trading system. The single rule governing what
may enter this repo:

> **Ship the infrastructure. Never ship the alpha.**

Generic execution/reliability/data plumbing is portable. Anything that encodes *what or when to
trade* — strategies, parameters, regime logic, thresholds, research — stays private. This file is
the checklist every port is reviewed against.

## ✅ Framework — portable (in scope)

| Component | Source (private) | Status |
|---|---|---|
| Firm/endpoint config | hardcoded URLs | ✅ ported → `config.py` (parameterized) |
| Core models (Bar/Order/Position/Fill/Bracket) | `common_models.py` | ✅ ported → `models.py` (genericized) |
| Auth / token / headers | `broker/login.py`, `broker/header_manager.py` | ✅ ported → `auth.py` (SSL-verify now default-on) |
| Market data (historical + live bars) | `broker/data.py` | ✅ ported → `market_data.py` (returns `Bar`) |
| Orders: place + cancel | `broker/place_order.py` | ✅ ported → `orders.py` |
| Orders: modify brackets (SL/TP) | `broker/qq_broker.py` | ⏳ next |
| Accounts / positions / order history | `broker/user.py` | ✅ ported → `accounts.py` |
| Unified client (core flow) | `broker/qq_broker.py` | ✅ ported → `client.py` (`ProjectXClient`) |
| Contract/tick resolution, fills, filled-trade sync | `broker/qq_broker.py` | ⏳ next |
| `Strategy` interface + throwaway example | (new) | ✅ `strategy.py` + `examples/strategy_orb.py` (ORB demo, public-domain) |
| Backtest harness | (new, generic) | ✅ `backtest.py` (adverse-first exits, full stats) |
| Reliability: fast fill confirm + reconciliation | runner internals (re-implemented generic) | ✅ `live.py` `LiveBot` |
| Reliability: restart-recovery, watchdog, kill switch | `tools/run_bot_with_restart.py`, etc. | ⏳ later |

## ⛔ Edge — never ported (out of scope, stays private)

- The strategy implementations (entry/exit logic of every live strategy).
- All strategy parameters: stop/target multipliers, time windows, filters, regime maps,
  volatility thresholds, sizing rules, the disabled-strategy lineup.
- Any research, backtests, optimization output, or `tools/sim/*`.
- Account IDs, balances, combine state, live logs, P&L.

## Sanitization checklist (run on every ported file)

1. **Secrets:** no credentials, tokens, API keys, account IDs, usernames. Creds come only from
   env/constructor.
2. **Internal names:** rename `QQ*` / `PXTrader` / personal references to clean public names.
3. **Hardcoded firm specifics:** move firm URLs/hostnames into `config.py` presets.
4. **Edge leakage:** no strategy logic, parameter, or threshold rides along inside an otherwise
   generic file. When in doubt, leave it out.
5. **Final gate:** run the `opensource-sanitizer` scan before any public push.

## Naming

Working name `pxtrader` / repo `projectx-trader` is **provisional** — confirm the public name
(and a quick trademark sanity check on "ProjectX"/firm names) before the repo is made public.
