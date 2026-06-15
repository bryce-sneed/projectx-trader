"""
Offline unit tests — no network. Validate config, models, and order mapping.

    pip install -e ".[dev]"
    pytest
"""
import pytest

from pxtrader import Side, get_firm
from pxtrader.client import _ORDER_TYPE, ProjectXClient
from pxtrader.orders import OrderRequest


def test_firm_presets_and_unknown_guard():
    assert get_firm("topstepx").user_api.startswith("https://")
    with pytest.raises(KeyError):
        get_firm("not-a-firm")


def test_order_type_codes():
    # Gateway codes: 1=LIMIT, 2=MARKET, 4=STOP (3 is rejected by the gateway).
    assert _ORDER_TYPE == {"LIMIT": 1, "MARKET": 2, "STOP": 4}


def test_side_opposite():
    assert Side.BUY.opposite is Side.SELL
    assert Side.SELL.opposite is Side.BUY


def test_order_request_serialization():
    req = OrderRequest(accountId=1, symbolId="F.US.MNQ", type=2, positionSize=3, stopPrice=20950.0)
    d = req.to_dict()
    assert d["type"] == 2 and d["positionSize"] == 3
    assert d["timeType"] == 0            # required field always present
    assert "linkedOrderId" not in d      # dropped when None
    assert d["customTag"]                # auto-generated uuid tag


def test_buy_sells_signed_size(monkeypatch):
    # BUY -> positive size, SELL -> negative size, without hitting the network.
    px = ProjectXClient(username="u", password="p", firm="topstepx", account_id=42)
    captured = {}

    def fake_place(req: OrderRequest):
        captured["size"] = req.positionSize
        captured["type"] = req.type
        return None

    monkeypatch.setattr(px._orders, "place", fake_place)

    px.place_market_order("F.US.MNQ", Side.BUY, 2)
    assert captured == {"size": 2, "type": 2}

    px.place_stop_order("F.US.MNQ", Side.SELL, 3, stop_price=21000.0)
    assert captured["size"] == -3 and captured["type"] == 4


def test_missing_account_id_raises():
    px = ProjectXClient(username="u", password="p", firm="topstepx")  # no account_id
    with pytest.raises(ValueError):
        px.place_market_order("F.US.MNQ", Side.BUY, 1)
