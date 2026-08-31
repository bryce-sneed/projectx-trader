# Prior art: `project-x-py` vs `pxtrader`

Assessment date: 2026-08-30. Package inspected: `project-x-py==1.0.5` (installed from PyPI).

## Read this first

**This repo is for private use, not PyPI publication.** Do not publish `pxtrader` as a ProjectX client — [`project-x-py`](https://pypi.org/project/project-x-py/) is the better maintained option for gateway I/O.

**The blocker on "depend on them + keep our framework":** incompatible auth/API surfaces. `pxtrader`: password `/Login` on `userapi` + `chartapi`. `project-x-py`: API-key `/Auth/loginKey` on `api.topstepx.com`. `FirmConfig` cannot layer on top without a full adapter rewrite; multi-firm is not preserved by swapping clients.

**Only non-commodity piece:** `LiveBot` (~192 LOC) — fill confirm, reconciliation, recovery. Supervisor/backtest/strategy are snippet- or commodity-tier as shipped.

## TL;DR

**Do not publish `pxtrader` as a competing client.** `project-x-py` is a richer, maintained TopStepX client (SignalR realtime, order manager, 50+ indicators, portfolio utils).

**The framework layer is real but thin (~650 LOC)** and mostly not differentiated enough to justify a separate package today:

| Layer | LOC | Verdict |
|---|---|---|
| `supervisor.py` + `KillSwitch` | 77 | Snippet-tier — an afternoon's work |
| `runtime.py` (`BarFeed`, `run_live`) | 110 | Useful but REST-poll based; inferior to their streaming |
| `live.py` (`LiveBot`) | 192 | Best pxtrader-only piece (fill confirm, reconciliation, recovery) |
| `backtest.py` + `strategy.py` | 268 | Standard harness; not unique |
| REST client (`auth`/`orders`/`market_data`/…) | ~800+ | Duplicate; different API surface than `project-x-py` |

**Honest recommendation:** depend on `project-x-py` for gateway I/O if you stay on TopStepX's `api.topstepx.com` API path; keep `LiveBot` + backtest harness privately or contribute upstream. Do not publish either the client or the current supervisor as a product.

---

## What `project-x-py` covers

Installed package root: 12 modules + `indicators/` subpackage.

| Module | Role |
|---|---|
| `client.py` | REST client (`ProjectX`): auth, accounts, instruments, bars/ticks, positions, trades |
| `order_manager.py` | Market/limit/stop/bracket/trailing orders, callbacks |
| `position_manager.py` | Position tracking |
| `realtime.py` | SignalR user + market hubs (quotes, trades, order updates) |
| `realtime_data_manager.py` | Streaming bar/tick aggregation |
| `orderbook.py` | L2 order book / microstructure |
| `config.py` | `ProjectXConfig`, env-var overrides, config file |
| `models.py` | Dataclasses for accounts, orders, positions, config |
| `indicators/` | 50+ polars-based TA functions |
| `utils.py` | Portfolio metrics, rate limiting, helpers |

Defaults are TopStepX-branded but `ProjectXConfig` fields and `PROJECTX_*` env vars allow URL overrides.

---

## Feature comparison

| Area | `project-x-py` | `pxtrader` |
|---|---|---|
| Auth | API key → `/Auth/loginKey` on `api.topstepx.com` | Password → `/Login` on `userapi.<firm>` |
| Market data | REST + SignalR streaming + orderbook | REST poll on `chartapi.<firm>` |
| Orders | Full order manager (bracket, trailing, modify) | Market + stop + cancel |
| Resilience | HTTP retry (urllib3), auth retry, SignalR auto-reconnect, `force_reconnect` | Transient poll errors swallowed in `run_live`; in-process crash restart via `supervise` |
| Process supervisor | **None** | `supervise()` + file `KillSwitch` |
| Strategy / backtest | **None** | `Strategy` / `Backtester` / CSV helpers |
| Multi-firm | Env-var URL overrides (defaults TopStepX) | `FirmConfig` presets (`user_api` / `chart_api` / `web`) |
| TA / portfolio | Built-in | None |

---

## Question 1: Is `supervise()` + `KillSwitch` better than an afternoon snippet?

**No — it *is* the snippet.**

`supervisor.py` is 77 lines. Core logic:

- `KillSwitch`: file exists → stop (15 lines).
- `supervise`: call `run_fn(should_stop)`; on exception, backoff + restart up to `max_restarts` in a rolling window; check kill-switch before start and during backoff.

This is **in-process** restart (re-call the function), not subprocess supervision. No PID tracking, no pause-before-spawn, no scoped kill-switch (backtest vs live), no "supervisor first then child then verify" stop sequence.

`docs/FRAMEWORK_VS_EDGE.md` still marks the real watchdog patterns from the private bot as "⏳ later". The scars in `CURSOR_BRIEF.md` Task 2 are **not ported**.

`project-x-py` does not replace this either — it has zero process-level supervision. But that also means our supervisor is not a differentiator; it's the easy half.

---

## Question 2: Does `project-x-py` already do supervisor-style work?

**Connection resilience: yes. Process supervision: no.**

Verified in source:

| Mechanism | Where | Scope |
|---|---|---|
| urllib3 `Retry` on HTTP session | `client.py` | Transient HTTP failures |
| `_authenticate_with_retry` | `client.py` | 503 on login |
| SignalR `.with_automatic_reconnect()` | `realtime.py` | WebSocket drop |
| `force_reconnect` (3 attempts, exponential backoff) | `realtime.py` | Manual hub reconnect |
| Historical data load retry (3×, 2s delay) | `realtime_data_manager.py` | Bar fetch |
| `refresh_token_and_reconnect` | `realtime.py` | JWT expiry |

No `supervise`, `KillSwitch`, subprocess, or watchdog anywhere in the package. Their retry story is **"keep the connection alive"**, not **"keep the bot process alive after an unhandled exception"**.

These are complementary, not overlapping — but our supervisor is the trivial half.

---

## Question 3: What breaks if you depend on them? Multi-firm specifically.

**Claude's bet is half right.** Multi-firm is not cleanly layerable on `project-x-py`, but the failure mode is worse than "TopStepX hardcoded" — the two clients target **different API surfaces**.

### Verified URL abstraction test

```python
# pxtrader — PASS: all three bases propagate to sub-clients
FirmConfig(name="fake", user_api="https://userapi.fake.com",
           chart_api="https://chartapi.fake.com", web="https://fake.com")
# AuthClient._url("/Login") → userapi.fake.com
# MarketDataClient._base → chartapi.fake.com

# project-x-py — PARTIAL: REST configurable via ProjectXConfig
ProjectXConfig(api_url="https://api.fake.com/api",
               user_hub_url="https://rtc.fake.com/hubs/user", ...)
# BUT ProjectXRealtimeClient.refresh_token_and_reconnect() hardcodes
# "https://rtc.topstepx.com/hubs/{user,market}" — ignores custom hubs
```

### API surface mismatch (blocks naive "swap the client")

| | `pxtrader` | `project-x-py` |
|---|---|---|
| Login | `POST userapi.*/Login` (password) | `POST api.*/Auth/loginKey` (API key) |
| Bars | `chartapi.*` | `api.*/History/retrieveBars` |
| Orders | `userapi.*` | `api.*/Order/place` |

These are not the same hostname split with different paths — they are different integration paths. Adapting `LiveBot` to `project-x-py` requires rewriting the client boundary, not dropping in `FirmConfig`.

### Multi-firm reality check

- **`pxtrader`**: `FirmConfig` abstraction is sound and tested, but `PRESETS` contains only `topstepx`. Multi-firm is aspirational — no second firm preset exists.
- **`project-x-py`**: REST URLs overridable via config/env; realtime token refresh breaks custom hub URLs; docs/examples assume TopStepX throughout.

**Conclusion:** depending on `project-x-py` does not quietly preserve multi-firm. It locks you to their API path (API-key auth, single `api_url`, SignalR hubs). Your `FirmConfig` (password auth, `userapi`/`chartapi` split) cannot be layered on top without an adapter — and the one firm preset you have is TopStepX anyway.

---

## What is actually worth keeping?

**`LiveBot`** (~192 LOC) is the only framework piece with non-obvious behavior:

- Poll until fill confirmed (don't assume market orders filled).
- Per-bar broker reconciliation (flat when you think you're in → clear; unmanaged position → don't pile on).
- Protective stop at broker + verify-before-close on exit.
- Warmup (replay history without orders) + restart recovery.

**`Backtester` + `Strategy`** are fine but generic — many quant frameworks have this.

**`supervise` + `KillSwitch`** — publishable only after porting the real watchdog lessons (pause-before-spawn, scoped halt, fail-closed PID enumeration, supervisor-first stop). As shipped: cookbook material.

---

## Recommendation

1. **Do not publish `pxtrader` to PyPI** as a client library. `project-x-py` wins on API coverage, realtime, and maintenance.
2. **Do not publish the framework layer as-is.** Too thin; supervisor is a snippet; backtest/strategy is commodity.
3. **If continuing development privately:**
   - Use `project-x-py` for TopStepX I/O **or** keep `pxtrader` client for the `userapi`/`chartapi` path your private bot uses — they are not drop-in interchangeable.
   - Port `LiveBot` reliability patterns onto whichever client you standardize on.
   - Port the *real* supervisor hardening from the private bot before claiming operational safety as a differentiator.
4. **If contributing upstream:** multi-firm URL presets, fix `refresh_token_and_reconnect` hub hardcoding, and a minimal strategy/backtest example would be more valuable than a competing package.

---

## Verification

- `project-x-py==1.0.5` installed and source-inspected (17 modules).
- Multi-firm URL propagation tested programmatically (pxtrader PASS; project-x-py REST PASS / realtime refresh FAIL on custom hubs).
- `pytest`: **42 passed** (0.18s).
