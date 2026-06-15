"""
Accounts, positions, and order history via the user API.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .auth import AuthClient
from .models import Account


def _account_from_payload(p: Dict[str, Any]) -> Account:
    name = p.get("accountName") or ""
    status = p.get("status")
    return Account(
        account_id=p.get("accountId"),
        name=name,
        balance=float(p.get("balance") or 0.0),
        # Practice/sim accounts are conventionally prefixed; treat unknown status as tradable.
        can_trade=status in (None, 0, 1),
        is_simulated="PRAC" in name.upper() or "SIM" in name.upper(),
    )


class AccountClient:
    """Reads accounts, positions, and order/trade history."""

    def __init__(self, auth: AuthClient):
        self._auth = auth
        self._base = auth.firm.user_api
        self.user_id: Optional[int] = None

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._base.rstrip('/')}/{path.lstrip('/')}"
        resp = self._auth.request("GET", url, params=params)
        resp.raise_for_status()
        return resp.json()

    def list_accounts(self) -> List[Account]:
        """GET /TradingAccount — also caches ``user_id`` for position lookups."""
        raw = self._get("/TradingAccount")
        if not isinstance(raw, list):
            raise ValueError("expected a list from /TradingAccount")
        if self.user_id is None:
            self.user_id = next((a.get("userId") for a in raw if a.get("userId") is not None), None)
        return [_account_from_payload(a) for a in raw]

    def positions(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """GET /Position/all/user/{user_id} — raw position dicts."""
        uid = user_id or self.user_id
        if uid is None:
            # Populate user_id by listing accounts first.
            self.list_accounts()
            uid = self.user_id
        if uid is None:
            raise ValueError("could not determine user_id; call list_accounts() first")
        raw = self._get(f"/Position/all/user/{uid}")
        return raw if isinstance(raw, list) else []

    def order_history(self, account_id: int) -> List[Dict[str, Any]]:
        """GET /Order?accountId=<id> — raw order/trade dicts."""
        raw = self._get("/Order", params={"accountId": account_id})
        return raw if isinstance(raw, list) else []

    def contracts(self) -> List[Dict[str, Any]]:
        """GET /UserContract/all."""
        raw = self._get("/UserContract/all")
        return raw if isinstance(raw, list) else []
