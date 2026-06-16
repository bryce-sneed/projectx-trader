"""
CSV loader tests — column aliasing, ISO + epoch timestamps, sorting, bad-row skipping, e2e.

    pytest tests/test_data.py -v
"""
from pxtrader import backtest_csv, load_csv_bars
from pxtrader.models import Side
from pxtrader.strategy import Signal, Strategy


def _write(tmp_path, text):
    p = tmp_path / "bars.csv"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_standard_columns_iso(tmp_path):
    path = _write(tmp_path,
        "timestamp,open,high,low,close,volume\n"
        "2026-06-15T09:30:00+00:00,100,101,99,100.5,120\n"
        "2026-06-15T09:31:00+00:00,100.5,102,100,101.5,90\n")
    bars = load_csv_bars(path)
    assert len(bars) == 2
    assert bars[0].open == 100 and bars[0].close == 100.5 and bars[0].volume == 120
    assert bars[1].high == 102


def test_aliased_columns_and_epoch(tmp_path):
    # date/o/h/l/c/v aliases + epoch-seconds timestamps
    path = _write(tmp_path,
        "date,o,h,l,c,v\n"
        "1781000000,100,101,99,100,5\n"
        "1781000060,100,102,100,101,6\n")
    bars = load_csv_bars(path)
    assert len(bars) == 2 and bars[0].close == 100 and bars[1].close == 101


def test_sorted_oldest_first(tmp_path):
    path = _write(tmp_path,
        "t,o,h,l,c\n"
        "1781000120,3,3,3,3\n"
        "1781000000,1,1,1,1\n"
        "1781000060,2,2,2,2\n")
    closes = [b.close for b in load_csv_bars(path)]
    assert closes == [1, 2, 3]


def test_bad_rows_skipped(tmp_path):
    path = _write(tmp_path,
        "timestamp,open,high,low,close\n"
        "2026-06-15T09:30:00Z,100,101,99,100\n"
        "2026-06-15T09:31:00Z,,,,\n"          # empty OHLC -> skipped
        "garbage,1,2,0,1\n"                    # unparseable ts -> skipped
        "2026-06-15T09:32:00Z,100,103,100,102\n")
    bars = load_csv_bars(path)
    assert len(bars) == 2 and bars[-1].close == 102


class _BuyOnce(Strategy):
    def __init__(self):
        self.fired = False

    def on_bar(self, ctx):
        if self.fired:
            return None
        self.fired = True
        return Signal(Side.BUY, stop=98.0, target=103.0)


def test_backtest_csv_end_to_end(tmp_path):
    path = _write(tmp_path,
        "timestamp,open,high,low,close\n"
        "2026-06-15T09:30:00Z,100,100,100,100\n"
        "2026-06-15T09:31:00Z,101,104,100,103\n")   # hits target 103
    r = backtest_csv(_BuyOnce(), path, point_value=2.0)
    assert r.n == 1 and r.trades[0].reason == "target"
