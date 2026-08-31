"""
Risk-state tests — four production incidents, each named for the history.

Mutation-check with cold cache:

    find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; python -B -m pytest tests/test_riskstate.py -v
"""
import os
from pathlib import Path

import pytest

from pxtrader.riskstate import (
    FeatureConfig,
    LimitOk,
    LimitUnavailable,
    RiskLockRegistry,
    broker_headroom_from_reading,
    feature_may_run,
    headroom_from_ledger_file,
    limit_from_reading,
    poller_may_clear_on_flat,
    read_feature_config,
    size_contracts,
)


def test_empty_ledger_does_not_report_full_allowance(tmp_path: Path):
    """Empty day-ledger file must not publish the full trail allowance as headroom."""
    ledger = tmp_path / "day_ledger.csv"
    ledger.write_text("", encoding="utf-8")

    result = headroom_from_ledger_file(ledger, trail_allowance=2000.0)

    assert isinstance(result, LimitUnavailable)
    assert "empty" in result.reason
    assert not isinstance(result, LimitOk)


def test_sentinel_headroom_does_not_size_as_unlimited():
    """Broker sentinel 9999 must not flow through to contract sizing as unlimited headroom."""
    raw = broker_headroom_from_reading(9999.0)
    assert isinstance(raw, LimitUnavailable)

    sized = size_contracts(raw, rule_max=2, dollars_per_contract=500.0)
    assert isinstance(sized, LimitUnavailable)
    assert not isinstance(sized, LimitOk)


def test_deleted_config_line_is_unconfigured_not_enabled():
    """A deleted config key is unconfigured — not disabled, and certainly not enabled."""
    config = {"other_feature": "enabled"}

    state = read_feature_config(config, "daily_loss_cap")

    assert state is FeatureConfig.UNCONFIGURED
    assert not feature_may_run(state)


def test_flat_account_does_not_clear_risk_rule_lock():
    """Position poller must not clear a circuit breaker the risk rule locked — flat or not."""
    registry = RiskLockRegistry()
    assert registry.acquire("risk_rule", "realised P&L circuit breaker") is True

    assert poller_may_clear_on_flat(registry, poller="position_poller", account_flat=True) is False
    assert registry.is_locked() is True

    assert registry.release("position_poller") is False
    assert registry.acquire("position_poller", "takeover attempt") is False
    assert registry.current().authority == "risk_rule"
    assert registry.release("risk_rule") is True
    assert registry.is_locked() is False


def test_large_headroom_is_not_rejected_by_universal_limit_type():
    """Limit is account-size agnostic — only the broker boundary knows magic sentinels."""
    result = limit_from_reading(12_000.0, context="ledger headroom")
    assert isinstance(result, LimitOk)
    assert result.value == pytest.approx(12_000.0)


def test_stale_ledger_does_not_report_valid_headroom(tmp_path: Path):
    """A ledger untouched longer than max_age is unavailable, not a stale limit."""
    ledger = tmp_path / "day_ledger.csv"
    ledger.write_text("peak_equity,running_equity\n50000,49000\n", encoding="utf-8")
    old = 1_000.0
    os.utime(ledger, (old, old))

    result = headroom_from_ledger_file(
        ledger,
        trail_allowance=2000.0,
        now=lambda: old + 30 * 86_400,
        max_age_seconds=86_400,
    )

    assert isinstance(result, LimitUnavailable)
    assert "stale" in result.reason


def test_malformed_last_ledger_row_not_silently_skipped(tmp_path: Path):
    """A corrupt final row must not fall back to an older row as current equity."""
    ledger = tmp_path / "day_ledger.csv"
    ledger.write_text(
        "peak_equity,running_equity\n"
        "50000,48500\n"
        "50000,47000,100,extra\n",
        encoding="utf-8",
    )
    fresh = 2_000_000.0
    os.utime(ledger, (fresh, fresh))

    result = headroom_from_ledger_file(
        ledger,
        trail_allowance=2000.0,
        now=lambda: fresh,
        max_age_seconds=86_400,
    )

    assert isinstance(result, LimitUnavailable)
    assert "malformed" in result.reason


def test_garbage_float_in_ledger_returns_unavailable_not_raises(tmp_path: Path):
    ledger = tmp_path / "day_ledger.csv"
    ledger.write_text("peak_equity,running_equity\n50000,not_a_number\n", encoding="utf-8")
    fresh = 2_000_000.0
    os.utime(ledger, (fresh, fresh))

    result = headroom_from_ledger_file(ledger, now=lambda: fresh, max_age_seconds=86_400)

    assert isinstance(result, LimitUnavailable)
    assert "non-numeric" in result.reason


def test_valid_ledger_reports_real_headroom(tmp_path: Path):
    ledger = tmp_path / "day_ledger.csv"
    ledger.write_text("peak_equity,running_equity\n10000,9850\n", encoding="utf-8")
    fresh = 2_000_000.0
    os.utime(ledger, (fresh, fresh))

    result = headroom_from_ledger_file(
        ledger,
        trail_allowance=2000.0,
        now=lambda: fresh,
        max_age_seconds=86_400,
    )

    assert isinstance(result, LimitOk)
    assert result.value == pytest.approx(1850.0)
