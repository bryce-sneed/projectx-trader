# Examples

| File | What it shows | Needs credentials? |
|---|---|---|
| `strategy_orb.py` | A demo `Strategy` (opening-range breakout) — public-domain, **not an edge**. | no |
| `01_connect.py` | Connect, list accounts, pull recent bars (read-only). | yes |
| `02_backtest.py` | Backtest the ORB on synthetic data + ASCII equity curve. **Runs with zero setup.** | no |
| `03_backtest_real_data.py` | Backtest the ORB on real bars pulled from your firm. | yes |

Start with **`python examples/02_backtest.py`** — it needs nothing but the package installed.

```bash
pip install -e .
python examples/02_backtest.py
```

To run a strategy live (test on a SIM account first):

```bash
python -m pxtrader.runtime \
  --strategy examples.strategy_orb:OpeningRangeBreakout \
  --symbol MNQ --symbol-id F.US.MNQ --size 1
```

Wrap it in `pxtrader.supervise(...)` with a `KillSwitch` for auto-restart + a `touch HALT` stop.
