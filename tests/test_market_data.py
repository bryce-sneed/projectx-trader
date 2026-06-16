"""
Contract-resolution tests (offline) — the id-extraction logic and details->search fallback.

    pytest tests/test_market_data.py -v
"""
from pxtrader.market_data import MarketDataClient, _extract_contract_id


def test_extract_from_flat_dict():
    assert _extract_contract_id({"symbolId": "F.US.MNQ"}) == "F.US.MNQ"
    assert _extract_contract_id({"contractId": 12345}) == "12345"


def test_extract_from_nested_and_list():
    assert _extract_contract_id({"contracts": [{"id": "X1"}]}) == "X1"
    assert _extract_contract_id([{"foo": 1, "symbolId": "Y2"}]) == "Y2"


def test_extract_returns_none_when_absent():
    assert _extract_contract_id({"name": "nope", "price": 1.0}) is None
    assert _extract_contract_id(None) is None


def test_resolve_prefers_details():
    md = MarketDataClient.__new__(MarketDataClient)   # bypass __init__ (no auth needed)
    md.symbol_details = lambda s: {"symbolId": "F.US.MNQ"}
    md.search_contracts = lambda s: []
    assert md.resolve_contract("MNQ") == "F.US.MNQ"


def test_resolve_falls_back_to_search_on_error():
    md = MarketDataClient.__new__(MarketDataClient)

    def boom(_s):
        raise RuntimeError("no details endpoint")

    md.symbol_details = boom
    md.search_contracts = lambda s: [{"contractId": "C9"}]
    assert md.resolve_contract("MNQ") == "C9"


def test_resolve_raises_when_unresolvable():
    md = MarketDataClient.__new__(MarketDataClient)
    md.symbol_details = lambda s: {}
    md.search_contracts = lambda s: []
    try:
        md.resolve_contract("ZZZ")
        assert False, "expected ValueError"
    except ValueError:
        pass
