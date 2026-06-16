"""
Load OHLC bars from a CSV file — backtest on your own data.

Forgiving about column names (timestamp/date/time, open/o, high/h, low/l, close/c, volume/v) and
timestamp formats (ISO-8601, or epoch seconds/millis). Returns bars sorted oldest-first, ready for
the Backtester.

    from pxtrader.data import load_csv_bars
    from pxtrader import Backtester
    bars = load_csv_bars("MNQ_1m.csv")
    print(Backtester(point_value=2.0).run(MyStrategy(), bars).summary())
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .models import Bar

_TS = ("timestamp", "datetime", "date", "time", "t")
_O = ("open", "o")
_H = ("high", "h")
_L = ("low", "l")
_C = ("close", "c")
_V = ("volume", "vol", "v")


def _pick(row: Dict[str, str], aliases) -> Optional[str]:
    for a in aliases:
        for k, v in row.items():
            if k is not None and k.strip().lower() == a:
                return v
    return None


def _parse_ts(v: str) -> datetime:
    v = str(v).strip()
    try:                                   # epoch seconds or millis?
        n = float(v)
        if n > 1_000_000:
            return datetime.fromtimestamp(n / 1000 if n > 1e11 else n, tz=timezone.utc)
    except ValueError:
        pass
    try:                                   # ISO-8601 (Z or offset)
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise ValueError(f"unparseable timestamp {v!r}") from e


def load_csv_bars(path: str) -> List[Bar]:
    """Parse a CSV of OHLC(V) bars into a sorted list of ``Bar``. Rows missing OHLC are skipped."""
    bars: List[Bar] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts, o, h, l, c = (_pick(row, _TS), _pick(row, _O), _pick(row, _H),
                              _pick(row, _L), _pick(row, _C))
            if None in (ts, o, h, l, c) or "" in (ts, o, h, l, c):
                continue
            v = _pick(row, _V)
            try:
                bars.append(Bar(timestamp=_parse_ts(ts), open=float(o), high=float(h),
                                low=float(l), close=float(c),
                                volume=int(float(v)) if v not in (None, "") else 0))
            except ValueError:
                continue
    bars.sort(key=lambda b: b.timestamp)
    return bars
