"""
Reference-data gate tests — per-field session provenance, not wall-clock age.

Mutation-check with cold cache:

    find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; python -B -m pytest tests/test_reference.py -v
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from pxtrader.reference import (
    FieldProvenance,
    ReferenceField,
    ReferenceOk,
    ReferenceSet,
    ReferenceUnavailable,
    SessionId,
    gate_reference_set,
    required_session_for_provenance,
)

ET = ZoneInfo("America/New_York")
FRIDAY = SessionId(date(2026, 8, 28))
MONDAY = SessionId(date(2026, 8, 31))
TUESDAY = SessionId(date(2026, 9, 1))


def test_prior_session_va_with_current_session_vwap_is_valid():
    """Friday VA + Monday VWAP at Monday 11:00 is correct mixed provenance, not a violation."""
    refset = ReferenceSet((
        ReferenceField("value_area_high", 21000.0, FRIDAY, FieldProvenance.PRIOR_COMPLETED_SESSION),
        ReferenceField("value_area_low", 20950.0, FRIDAY, FieldProvenance.PRIOR_COMPLETED_SESSION),
        ReferenceField("vwap", 20980.0, MONDAY, FieldProvenance.CURRENT_LIVE_SESSION),
    ))

    monday_midday = datetime(2026, 8, 31, 11, 0, tzinfo=ET)
    result = gate_reference_set(refset, monday_midday)

    assert isinstance(result, ReferenceOk)


def test_value_area_from_previous_session_is_valid_during_current_session():
    """At Monday 11:00 the authoritative VA is Friday's completed profile, not Monday's partial."""
    refset = ReferenceSet((
        ReferenceField("value_area_high", 21000.0, FRIDAY, FieldProvenance.PRIOR_COMPLETED_SESSION),
        ReferenceField("value_area_low", 20950.0, FRIDAY, FieldProvenance.PRIOR_COMPLETED_SESSION),
    ))

    monday_midday = datetime(2026, 8, 31, 11, 0, tzinfo=ET)
    assert isinstance(gate_reference_set(refset, monday_midday), ReferenceOk)


def test_partial_session_value_area_is_stale_during_rth():
    """Monday VA at Monday 11:00 is a partial-session artifact — prior-completed rule rejects it."""
    refset = ReferenceSet((
        ReferenceField("value_area_high", 21000.0, MONDAY, FieldProvenance.PRIOR_COMPLETED_SESSION),
    ))

    monday_midday = datetime(2026, 8, 31, 11, 0, tzinfo=ET)
    result = gate_reference_set(refset, monday_midday)

    assert isinstance(result, ReferenceUnavailable)
    assert "stale" in result.reason


def test_value_area_from_two_sessions_ago_is_stale():
    """Friday VA on Tuesday is two sessions back — stale under prior-completed rule."""
    refset = ReferenceSet((
        ReferenceField("value_area_high", 21000.0, FRIDAY, FieldProvenance.PRIOR_COMPLETED_SESSION),
    ))

    tuesday_midday = datetime(2026, 9, 1, 11, 0, tzinfo=ET)
    result = gate_reference_set(refset, tuesday_midday)

    assert isinstance(result, ReferenceUnavailable)
    assert "stale" in result.reason


def test_current_session_field_unavailable_before_rth_open():
    refset = ReferenceSet((
        ReferenceField("vwap", 20980.0, FRIDAY, FieldProvenance.CURRENT_LIVE_SESSION),
    ))

    monday_pre_open = datetime(2026, 8, 31, 9, 0, tzinfo=ET)
    result = gate_reference_set(refset, monday_pre_open)

    assert isinstance(result, ReferenceUnavailable)
    assert "no live session" in result.reason


def test_required_session_for_provenance_before_and_after_open():
    monday_pre = datetime(2026, 8, 31, 9, 0, tzinfo=ET)
    monday_mid = datetime(2026, 8, 31, 11, 0, tzinfo=ET)

    assert required_session_for_provenance(
        FieldProvenance.PRIOR_COMPLETED_SESSION, monday_pre,
    ).trading_day == date(2026, 8, 28)
    assert required_session_for_provenance(
        FieldProvenance.PRIOR_COMPLETED_SESSION, monday_mid,
    ).trading_day == date(2026, 8, 28)
    assert required_session_for_provenance(
        FieldProvenance.CURRENT_LIVE_SESSION, monday_mid,
    ).trading_day == date(2026, 8, 31)
    assert required_session_for_provenance(FieldProvenance.CURRENT_LIVE_SESSION, monday_pre) is None
