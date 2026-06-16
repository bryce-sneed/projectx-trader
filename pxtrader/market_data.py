"""
Market data — historical and live bars, plus contract search.

Wraps the gateway's chart API and returns clean ``Bar`` objects. The gateway delivers OHLC
either as a list of bar dicts or as parallel series (``t``/``o``/``c``/``l``/``h``/``v``); both
shapes are handled here.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .auth import AuthClient
from .models import Bar


def _to_seconds(epoch: int) -> int:
    """Gateway expects epoch SECONDS; accept millis and downconvert (13 digits -> 10)."""
    return epoch // 1000 if epoch > 10_000_000_000 else epoch


def _bar_from_dict(d: Dict[str, Any]) -> Bar:
    ts = d.get("t")
    ts_s = ts / 1000.0 if ts and ts > 10_000_000_000 else ts
    return Bar(
        timestamp=datetime.fromtimestamp(ts_s, tz=timezone.utc) if ts_s else datetime.now(timezone.utc),
        open=d.get("o"), high=d.get("h"), low=d.get("l"), close=d.get("c"),
        volume=int(d.get("v") or 0),
    )


class MarketDataClient:
    """Reads historical/live bars and searches contracts via the chart API."""

    def __init__(self, auth: AuthClient):
        self._auth = auth
        self._base = auth.firm.chart_api

    def _get(self, path: str, params: Dict[str, Any]) -> Any:
        url = f"{self._base.rstrip('/')}/{path.lstrip('/')}"
        resp = self._auth.request("GET", url, params=params)
        resp.raise_for_status()
        return resp.json()

    def fetch_bars(
        self,
        symbol: str,
        *,
        resolution: int,
        countback: int,
        start: int,
        end: int,
        session_id: str = "extended",
        live: bool = False,
    ) -> List[Bar]:
        """Fetch OHLC bars. ``start``/``end`` are epoch seconds (millis accepted)."""
        params = {
            "Symbol": symbol,
            "Resolution": resolution,
            "Countback": countback,
            "From": _to_seconds(start),
            "To": _to_seconds(end),
            "SessionId": session_id,
            "Live": "true" if live else "false",
        }
        payload = self._get("/History", params)

        bars: Optional[List[Dict[str, Any]]] = None
        if isinstance(payload, list):
            bars = payload
        elif isinstance(payload, dict):
            if payload.get("bars") or payload.get("Bars"):
                bars = payload.get("bars") or payload.get("Bars")
            elif all(k in payload for k in ("t", "o", "c", "l", "h")):
                bars = _series_to_bars(payload)
        if bars is None:
            raise ValueError(
                f"Unexpected /History response: {json.dumps(payload)[:300]}"
            )
        return [_bar_from_dict(b) for b in bars]

    def search_contracts(self, query: str, *, limit: int = 30, exchange: str = "", live: bool = False) -> Any:
        """Search tradable contracts by symbol (e.g. 'MNQ', 'MES', 'GC')."""
        return self._get("/Search", {
            "query": query, "limit": limit, "exchange": exchange, "live": str(live).lower(),
        })

    def symbol_details(self, symbol: str) -> Any:
        """Resolve full contract details (incl. the symbolId orders need)."""
        return self._get("/Symbols", {"symbol": symbol})

    def resolve_contract(self, symbol: str) -> str:
        """Best-effort: map a symbol (e.g. 'MNQ') to the contract id orders are placed against.

        Tries symbol details then contract search and digs out the first id-like field. Response
        shapes vary by firm — if this can't find it, pass the contract id to orders directly.
        """
        for fetch in (lambda: self.symbol_details(symbol), lambda: self.search_contracts(symbol)):
            try:
                cid = _extract_contract_id(fetch())
            except Exception:
                cid = None
            if cid:
                return cid
        raise ValueError(f"could not resolve a contract id for {symbol!r} - pass symbol_id explicitly")


def _extract_contract_id(data: Any) -> Optional[str]:
    """Find the first plausible contract-id field in a (possibly nested) gateway response."""
    keys = ("symbolId", "contractId", "id", "symbol")
    if isinstance(data, dict):
        for k in keys:
            v = data.get(k)
            if isinstance(v, (str, int)) and str(v):
                return str(v)
        for v in data.values():
            found = _extract_contract_id(v)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _extract_contract_id(item)
            if found:
                return found
    return None


def _series_to_bars(p: Dict[str, Any]) -> List[Dict[str, Any]]:
    t = p.get("t") or []
    o, c, l, h = p.get("o") or [], p.get("c") or [], p.get("l") or [], p.get("h") or []
    v = p.get("v") or p.get("volume") or []
    out: List[Dict[str, Any]] = []
    for i in range(len(t)):
        out.append({
            "t": t[i],
            "o": o[i] if i < len(o) else None,
            "c": c[i] if i < len(c) else None,
            "l": l[i] if i < len(l) else None,
            "h": h[i] if i < len(h) else None,
            "v": v[i] if i < len(v) else None,
        })
    return out
