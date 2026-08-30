# Cursor work brief — projectx-trader (2026-08-30)

**This repo is safe for an autonomous agent. The trading bot repo is not.**
`CLAUDE_CODE_FINAL (1)/` runs a live futures account and carries a `.cursorignore` that hard-excludes
`bot/`, `.env`, `live_logs/`, `tools/sim/` and the process machinery. Do not work there. Everything
below is in **this** repo, which touches no live account and no money.

## Context you need

`projectx-trader` is a Python client + bot framework for ProjectX-powered prop-firm futures
platforms (TopstepX and others). Currently **v0.4**: client, live runtime (`BarFeed`/`run_live`/CLI),
supervisor with auto-restart and kill-switch, CSV backtesting, examples, issue templates. Not yet
published.

**The thing that changed and nobody has reacted to:** a package called **`project-x-py`** exists on
PyPI (v1.0.5) — "a high-performance Python client for the TopStepX ProjectX Gateway API ... for
institutional traders and quantitative analysts", with historical data, real-time streaming,
technical analysis and market-microstructure tools. There is also an MCP server for the TopstepX API
with SignalR realtime support.

So this project has prior art it has never been compared against. Publishing without that comparison
is how you launch a duplicate.

## Task 1 — Prior-art assessment (do this first, it may change everything else)

Produce `docs/PRIOR_ART.md` answering, with evidence rather than impressions:

* What does `project-x-py` actually cover? Install it, read its API surface, list its modules.
* Feature-by-feature against `pxtrader`: client, auth, streaming, orders, bars, backtest, supervisor.
* Where does `pxtrader` genuinely differ? Candidate answer to TEST, not assume: `project-x-py` looks
  like a *client library*, `pxtrader` is a *bot framework* (runtime, supervisor, kill-switch,
  restart-recovery). If that holds, the differentiator is operational safety, not API coverage.
* **The honest recommendation, including "wrap it instead".** If `project-x-py` is a better client,
  the right move may be to depend on it and keep only the framework layer. Say so if it is true.

**Deliverable: a recommendation with a reason, not a feature table.** If the conclusion is "do not
publish, contribute upstream instead", that is a valid and useful outcome.

## Task 2 — Harden what makes this different

Whatever Task 1 concludes, the supervisor/kill-switch layer is the part with real-world scars behind
it. Port the lessons — these are all things that bit the private bot in the last week:

1. **A pause flag must be checked before any spawn, not only while idle.** The private bot's watchdog
   checked its flag only inside a `while not within_rth()` wait loop, so a watchdog launched *during*
   the window spawned without ever reading it, and a bot traded a full session that was supposed to
   be paused.
2. **A kill switch must be scoped to live execution.** The same bot's `HALT_TRADING` file was checked
   unconditionally, including in backtest replay — which silently zeroed every simulation in the repo
   and reported "no trades" as if it were a result.
3. **A process you cannot read is not a process that is absent.** Enumerating bot children via
   `psutil` and letting `AccessDenied` fall into a bare `except: continue` made an elevated child
   invisible. Fail CLOSED: count what you cannot identify.
4. **Stopping means supervisor first, then child, then VERIFY.** Kill the child alone and the
   supervisor respawns it with a new PID, so the verification pass finds nothing and reports success.

Each of these deserves a test that fails without the fix. Mutation-check them: comment out the fix,
confirm the test goes red, restore.

## Task 3 — Publishing readiness (only if Task 1 says publish)

`pyproject.toml` metadata, README quickstart that actually runs from a clean venv, CI on push, and a
CHANGELOG. Do not publish to PyPI — prepare the release and stop.

## Rules

* **Never edit the bot repo.** Not one file.
* No live credentials. Tests must run offline with no account.
* Small commits with reasons in the message, not just what changed.
* If a task turns out to be a bad idea, say so and stop rather than completing it.
