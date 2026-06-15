"""
Order placement against the gateway's user API.

``OrderRequest`` mirrors the gateway's wire format (its field names and integer ``type`` codes);
the high-level ``ProjectXClient`` exposes friendlier market/limit/stop + bracket helpers on top.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

import requests

from .auth import AuthClient


@dataclass
class OrderRequest:
    """Wire-format order payload. ``type`` is the gateway's integer order-type code."""
    accountId: int
    symbolId: str
    type: int
    positionSize: int               # signed: + buy, - sell
    limitPrice: Optional[float] = None
    stopPrice: Optional[float] = None
    timeType: int = 0
    trailDistance: Optional[float] = None
    customTag: str = field(default_factory=lambda: str(uuid.uuid4()))
    linkedOrderId: Optional[int] = None   # for OCO bracket legs

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if data.get("timeType") is None:
            data["timeType"] = 0
        if data.get("linkedOrderId") is None:
            data.pop("linkedOrderId", None)
        return data


@dataclass
class OrderResult:
    """Normalized gateway response to an order request."""
    result: Optional[int] = None
    order_id: Optional[int] = None
    executed_price: Optional[float] = None
    position_disposition: Optional[int] = None
    error_message: Optional[str] = None

    @classmethod
    def from_payload(cls, p: Dict[str, Any]) -> "OrderResult":
        return cls(
            result=p.get("result"),
            order_id=p.get("orderId"),
            executed_price=p.get("executedPrice"),
            position_disposition=p.get("positionDisposition"),
            error_message=p.get("errorMessage"),
        )


class OrderError(RuntimeError):
    """Raised when the gateway rejects an order."""


class OrderClient:
    """Places and cancels orders via the user API."""

    def __init__(self, auth: AuthClient):
        self._auth = auth
        self._base = auth.firm.user_api

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        url = f"{self._base.rstrip('/')}/{path.lstrip('/')}"
        resp = self._auth.request("POST", url, json_body=payload)
        if resp.status_code != 200:
            # The gateway often returns a JSON body with errorMessage on failures.
            try:
                body = resp.json()
                msg = body.get("errorMessage") if isinstance(body, dict) else str(body)
            except ValueError:
                msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
            raise OrderError(f"{resp.status_code}: {msg or 'request failed'} ({url})")
        return resp.json()

    def place(self, order: OrderRequest) -> OrderResult:
        """Submit an order. Raises ``OrderError`` if the gateway reports a failure."""
        payload = self._post("/Order", order.to_dict())
        if not isinstance(payload, dict):
            raise OrderError("unexpected /Order response payload")
        result = OrderResult.from_payload(payload)
        # The gateway can echo an orderId even on failure; result code >=2 or an errorMessage = reject.
        if result.error_message or (result.result is not None and result.result >= 2):
            raise OrderError(result.error_message or f"order rejected (result={result.result})")
        return result

    def cancel(self, account_id: int, order_id: int) -> Any:
        """Cancel a working order."""
        return self._post("/Order/cancel", {"accountId": account_id, "orderId": order_id})
