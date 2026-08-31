# Proposals — safety patterns for the live path

**Date:** 2026-08-31  
**Status:** Recommendation only. Nothing here is approved for application.  
**Author context:** Written by the Cursor agent in `projectx-trader`. The live bot codebase is **not visible** (`.cursorignore` is deliberate). Every claim below is phrased as **what to check**, not what is wrong.

**Account constraint:** The live system trades a funded account with very little drawdown room (~$863 at time of writing). Maintenance has caused incidents as often as logic bugs (eight-day enabled feature, empty ledger headroom). A port that fixes a rare defect but introduces a common false halt is a net loss.

---

## Summary ranking (if this were my account)

| Priority | Module | Verdict | First step |
|---|---|---|---|
| 1 | `provenance` | **Propose it** (read-only tooling first) | Pre-market check: deployed file vs running snapshot |
| 2 | `riskstate` | **Propose it** (audit, then shadow) | Verify day-ledger empty/sentinel paths before any sizing change |
| 3 | `watchdog` (supervision) | **Keep it here** | Gap-audit live restart/stop scripts against incident checklist |
| 4 | `reference` | **Keep it here** | Design reference for VA/PDH/VWAP audit — do not wire to order path yet |

**Would not touch at all (until operator is well and market is closed):**
- Replacing or rewriting live process supervision during RTH
- Wiring `reference.gate_reference_set` directly into live entry without shadow logging first
- Any change that sizes or blocks orders automatically on the first deploy of new gates

---

## 1. Supervision (`pxtrader/watchdog.py` + `supervisor.py`)

### Verdict: **Keep it here**

### Why

`docs/FRAMEWORK_VS_EDGE.md` lists live sources for watchdog auto-restart and kill switch (`tools/run_bot_with_restart.py`, `emergency_stop.py`) as existing private machinery — **not** as unported greenfield. The incidents that motivated `watchdog.py` (pause-before-spawn, scoped halt, fail-closed PID count, supervisor-first stop) already bit the **live** system. This repo captured the lessons as tested patterns; it does not prove the live bot still lacks them.

`supervise()` in `supervisor.py` is snippet-tier in-process restart (~77 LOC). README now labels it accurately. It is not ops safety and should not be proposed as a live replacement for subprocess supervision.

### What to check in the live bot (not claims — a checklist)

1. **Pause-before-spawn:** Is a pause/halt flag read immediately before spawning the child, not only inside a pre-window wait loop?
2. **Scoped halt:** Does `HALT` / kill-switch apply only to live execution, never backtest/replay/sim paths?
3. **PID enumeration:** On `AccessDenied` from `psutil`, does enumeration fail closed (count as present) rather than skip?
4. **Stop order:** Does emergency stop kill the supervisor before the child, then verify — not child-only?
5. **Lock authority:** Can a poller clear a lock held by another authority, or `acquire` overwrite an existing lock?

### Port failure modes (if someone ports anyway)

- Wrong stop sequence during an emergency → child respawns under new PID; operator believes bot is dead while it trades.
- Over-aggressive pause → bot never spawns on a day it should run (missed session).
- PID false positives → spurious alerts or destructive kill of unrelated processes.
- Touching process machinery during market hours → accidental restart mid-trade.

### Realistic port path

Run the checklist against live `run_bot_with_restart` / `emergency_stop` **read-only** first. Port only a named gap, one incident at a time, outside RTH, with a rollback plan. Do not drop in `pxtrader/watchdog.py` wholesale — APIs differ.

---

## 2. Risk state (`pxtrader/riskstate.py`)

### Verdict: **Propose it**

### Why

This module addresses the most expensive incident cited in development: **empty day-ledger → reported full drawdown allowance → sized into near-death**. That is an account-survival defect class, not a polish item. The patterns (empty/stale/corrupt ledger → unavailable; broker sentinel at integration boundary; `FeatureConfig` tri-state; authority-scoped locks) map directly to incidents described in conversation.

`riskstate` is library-only here — not wired to `run_live`. Proposing it means **auditing the live ledger/sizer/config path against these tests**, not copying the file.

### What to check in the live bot

1. **Empty ledger:** What does `headroom` / drawdown-room return when the day-ledger file exists but is empty or has zero baseline? Is it unavailable, or does it compute a permissive number?
2. **Sentinel values:** Is broker unknown (e.g. `9999`) rejected at the broker-read boundary, not in a universal limit type that rejects legitimate large accounts?
3. **Stale ledger:** Is there a freshness check (mtime or embedded timestamp) vs process load time?
4. **Malformed last row:** Can a bad final line silently fall back to an older row?
5. **Deleted config key:** Is a missing key `UNCONFIGURED` (must not run), not default-enabled?
6. **Circuit breaker lock:** Can a flat-account poller clear a lock held by `risk_rule`? Can `acquire` steal a lock?

### Port failure modes

- **False unavailable:** Bot halts sizing on healthy days → missed trades (annoying, usually survivable).
- **False available:** Same class as the original incident → sized into death (unacceptable).
- **Stale too aggressive:** Ledger restamped every morning triggers perpetual unavailable until manually fixed.
- **Tri-state mis-wiring:** Operator deletes a key expecting disable; bot still runs because something checks `!= DISABLED` instead of `== ENABLED`.

### Realistic port path

1. **Read-only audit** — trace live day-ledger → headroom → position size with the four incident scenarios on paper.
2. **Shadow mode** — log what `riskstate` *would* return alongside live decisions without blocking.
3. **Gate one path** — e.g. block sizing only when ledger is empty, the exact original failure shape.
4. Never deploy a full replacement sizer on a Friday before a long weekend.

---

## 3. Reference data (`pxtrader/reference.py`)

### Verdict: **Keep it here**

### Why

The chasing-veto / stale value-area incident is real, but this module went through **two design failures** (global session rule → off switch; then per-field provenance rebuild). It is now correct in tests, but **wiring it to a live entry path is the highest-risk integration** of the four: wrong provenance tags or session calendar → blocks legitimate entries or admits stale ones silently.

We have **no visibility** into how the live bot tags VA, PDH, VWAP, or opening range. The module is a proven design reference, not a drop-in.

### What to check in the live bot

1. Before live entry, what session does each structural input claim (VA, PDH, VWAP, IB)?
2. Is Friday VA correctly treated as authoritative at Monday 11:00 RTH?
3. Is Monday partial VA rejected for prior-completed use cases?
4. Can PDH (prior session) and VWAP (current session) coexist without false "mixed session" errors?
5. Is there any gate at all, or only wall-clock age (wrong for Monday morning)?

### Port failure modes

- Off switch → bot never entries despite valid setup (we built this once; tests did not catch until accept-path audit).
- Wrong calendar → passes stale data every Monday pre-open (dead check failure mode).
- Entry-path integration → touches order path directly; any bug trades or does not trade real money.

### Realistic port path

Use `reference.py` and its tests as the **spec** when auditing live structure tagging. If gaps exist, port the **provenance rules** into live code natively — do not import `pxtrader.reference` into the order path on v1. Shadow-log gate verdicts before blocking.

---

## 4. Config provenance (`pxtrader/provenance.py`)

### Verdict: **Propose it**

### Why

Matches the operator's standing rule: **verify loaded, not just saved**. The three-way verdict (`MATCH` / `MISMATCH` / `CANNOT_DETERMINE`) directly addresses "I could not reach the process" ≠ "healthy." This is read-only comparison of declared state — no process memory access, no debugger.

Lowest-risk proposal because it can start as **operator tooling** (pre-market script) without changing the order path.

### What to check in the live bot

1. Does the child publish what it loaded at startup (identity + timestamp + values snapshot)?
2. If `.env` is edited after start, is that detectable before assuming the change took effect?
3. Is unreachable process reported as unknown, not match?
4. Are deleted keys unconfigured on disk while running process still holds old values?

### Port failure modes

- **False MISMATCH** → unnecessary restarts, operator churn.
- **False MATCH** → operator believes config deployed; process still on old values (original failure).
- **Snapshot not taken at load** → comparison is fiction; worse than no tool because it agrees.
- **Restart to "fix" mismatch** during RTH → incidental trade risk from respawn.

### Realistic port path

1. Add `snapshot_at_load` to live child startup — write once, never mutate.
2. Operator runs `compare_provenance` pre-market and after any `.env` edit.
3. Only after weeks of trustworthy MISMATCH/pending detection, consider blocking start when pending.

---

## What was exercise-only

| Piece | Notes |
|---|---|
| `supervise()` + exported kill-switch as "reliability layer" | Snippet-tier; demoted in README. Useful cookbook, not a proposal. |
| `pxtrader` REST client / `run_live` polling runtime | Prior-art verdict: not competitive with `project-x-py` for gateway I/O. |
| Test infrastructure (mutation-check, accept-path, inverted-refuse) | Meta-pattern for this repo; port the **discipline**, not the pytest files. |

---

## Suggested operator sequence (when ready)

1. **Morning, market closed, feeling well:** Run provenance comparison manually (deployed `.env` vs last known running snapshot). No code changes.
2. **Trace live ledger → headroom → size** against `test_empty_ledger_does_not_report_full_allowance` scenario on paper.
3. **Watchdog gap-audit** against five checklist items; file issues, do not patch live during audit.
4. **Reference audit** — document how live tags VA/PDH/VWAP; compare to `reference.py` rules.
5. **Shadow mode** for any gate before it blocks orders.

---

## Explicit non-actions

- No push to remote without operator decision on public/private scope.
- No application to live bot by agents (either Claude or Cursor) without operator approval.
- No port during RTH unless it is read-only logging.
