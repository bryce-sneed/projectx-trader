# Contributing to pxtrader

Thanks for your interest — this is a young project and good PRs move it fast.

## Ground rules
- **No strategies / no alpha.** This is a *framework*. PRs add infrastructure (broker coverage,
  reliability, backtest features, docs), not trading edges. See [`docs/FRAMEWORK_VS_EDGE.md`](docs/FRAMEWORK_VS_EDGE.md).
- **No secrets, ever.** Credentials come from `.env` (gitignored). Never commit a token, account id,
  or real `.env`.
- **Keep it dependency-light.** Standard library + `requests`. Discuss before adding a dependency.

## Dev setup
```bash
git clone https://github.com/bryce-sneed/projectx-trader.git
cd projectx-trader
pip install -e ".[dev]"
pytest            # all tests run offline, no broker/network
```

## What makes a good PR
- A focused change with a clear title (`feat:`, `fix:`, `docs:`, `chore:`).
- **Tests for new logic**, runnable offline (use a fake client — see `tests/test_live.py`).
- For broker-coverage PRs, note the firm/endpoint you verified against (response shapes vary).
- Run `ruff check .` and `pytest` before opening.

## Good first issues
- Add a firm preset to `pxtrader/config.py` (and confirm the endpoints work).
- Bracket SL/TP modify + true OCO (`linkedOrderId`).
- A watchdog/auto-restart wrapper around `run_live`.
- More worked example strategies (public-domain only).

## Adding a firm
Most ProjectX-powered firms share the API shape under different hostnames. Add a `FirmConfig` to
`PRESETS` in `config.py`, then test auth + a bar fetch + a SIM order. PRs welcome.

By contributing you agree your work is released under the project's MIT License.
