"""
ProjectXClient — the one object most users touch.

Ties auth + market data + orders + accounts together and exposes friendly helpers. Credentials
come from arguments or the environment (``PROJECTX_USERNAME`` / ``PROJECTX_PASSWORD`` /
``PROJECTX_ACCOUNT_ID`` / ``PROJECTX_FIRM``). The sub-clients remain accessible for lower-level work.
"""
from __future__ import annotations

import os
from typing import List, Optional

from .accounts import AccountClient
from .auth import AuthClient
from .config import FirmConfig
from .market_data import MarketDataClient
from .models import Account, Bar, Side
from .orders import OrderClient, OrderRequest, OrderResult

# Gateway integer order-type codes (3 is rejected by the gateway).
_ORDER_TYPE = {"LIMIT": 1, "MARKET": 2, "STOP": 4}


class ProjectXClient:
    """High-level client for a ProjectX-powered prop-firm account.

    Example:
        >>> px = ProjectXClient()           # creds from env
        >>> px.connect()
        >>> for a in px.list_accounts():
        ...     print(a.account_id, a.name, a.balance)
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        firm: FirmConfig | str | None = None,
        account_id: Optional[int] = None,
        verify: bool = True,
    ):
        self._username = username or os.environ.get("PROJECTX_USERNAME")
        self._password = password or os.environ.get("PROJECTX_PASSWORD")
        env_acct = os.environ.get("PROJECTX_ACCOUNT_ID")
        self.account_id = account_id or (int(env_acct) if env_acct else None)

        self.auth = AuthClient(firm, verify=verify)
        self.market_data = MarketDataClient(self.auth)
        self.accounts = AccountClient(self.auth)
        self._orders = OrderClient(self.auth)

    # ── Session ────────────────────────────────────────────────────────────
    def connect(self) -> "ProjectXClient":
        """Authenticate using the configured credentials. Returns self for chaining."""
        if not self._username or not self._password:
            raise ValueError(
                "Missing credentials. Pass username/password or set "
                "PROJECTX_USERNAME / PROJECTX_PASSWORD."
            )
        resp = self.auth.login(self._username, self._password)
        if not resp.success or not resp.token:
            raise RuntimeError("login failed — check credentials and firm preset")
        return self

    @property
    def token(self) -> Optional[str]:
        return self.auth.token

    # ── Accounts / positions ───────────────────────────────────────────────
    def list_accounts(self) -> List[Account]:
        return self.accounts.list_accounts()

    def open_positions(self, account_id: Optional[int] = None):
        """Raw open-position dicts for the account (defaults to the configured account)."""
        positions = self.accounts.positions()
        acct = account_id or self.account_id
        if acct is None:
            return positions
        return [p for p in positions if p.get("accountId") in (None, acct)]

    # ── Market data ────────────────────────────────────────────────────────
    def bars(
        self, symbol: str, *, resolution: int, countback: int, start: int, end: int,
        session_id: str = "extended", live: bool = False,
    ) -> List[Bar]:
        return self.market_data.fetch_bars(
            symbol, resolution=resolution, countback=countback,
            start=start, end=end, session_id=session_id, live=live,
        )

    # ── Orders ─────────────────────────────────────────────────────────────
    def _place(
        self, symbol_id: str, side: Side, quantity: int, type_name: str,
        *, limit_price=None, stop_price=None, account_id=None, tag="",
    ) -> OrderResult:
        acct = account_id or self.account_id
        if acct is None:
            raise ValueError("no account_id (pass one or set PROJECTX_ACCOUNT_ID)")
        size = quantity if side is Side.BUY else -quantity
        req = OrderRequest(
            accountId=int(acct), symbolId=symbol_id, type=_ORDER_TYPE[type_name],
            positionSize=size, limitPrice=limit_price, stopPrice=stop_price,
        )
        if tag:
            req.customTag = tag  # otherwise OrderRequest auto-generates a uuid tag
        return self._orders.place(req)

    def place_market_order(self, symbol_id: str, side: Side, quantity: int,
                           *, account_id: Optional[int] = None, tag: str = "") -> OrderResult:
        return self._place(symbol_id, side, quantity, "MARKET", account_id=account_id, tag=tag)

    def place_limit_order(self, symbol_id: str, side: Side, quantity: int, limit_price: float,
                          *, account_id: Optional[int] = None, tag: str = "") -> OrderResult:
        return self._place(symbol_id, side, quantity, "LIMIT",
                           limit_price=limit_price, account_id=account_id, tag=tag)

    def place_stop_order(self, symbol_id: str, side: Side, quantity: int, stop_price: float,
                         *, account_id: Optional[int] = None, tag: str = "") -> OrderResult:
        return self._place(symbol_id, side, quantity, "STOP",
                           stop_price=stop_price, account_id=account_id, tag=tag)

    def cancel_order(self, order_id: int, account_id: Optional[int] = None):
        acct = account_id or self.account_id
        if acct is None:
            raise ValueError("no account_id (pass one or set PROJECTX_ACCOUNT_ID)")
        return self._orders.cancel(int(acct), order_id)

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.auth.session.close()
