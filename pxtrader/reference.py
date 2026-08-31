"""
Reference data — session-scoped market structure that fails closed when stale.

Freshness is measured in TRADING SESSIONS, not wall-clock seconds. Each field declares its own
provenance rule: prior-completed-session references (value area, prior day high) vs
current-live-session references (VWAP, opening range). A ``ReferenceSet`` is coherent when
every field satisfies its own rule at the same ``now`` — mixed provenance is expected, mixed
obligations violated is not.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Callable, Optional, Tuple, Union


class FieldProvenance(Enum):
    """How a field's session is chosen relative to ``now``."""

    PRIOR_COMPLETED_SESSION = "prior_completed_session"
    CURRENT_LIVE_SESSION = "current_live_session"


@dataclass(frozen=True)
class SessionId:
    """Identity of a futures RTH session (trading calendar day)."""

    trading_day: date


@dataclass(frozen=True)
class ReferenceField:
    name: str
    value: float
    session: SessionId
    provenance: FieldProvenance


@dataclass(frozen=True)
class ReferenceSet:
    """Market-structure inputs — fields may mix provenance kinds at the same ``now``."""

    fields: Tuple[ReferenceField, ...]


@dataclass(frozen=True)
class ReferenceOk:
    as_of: datetime


@dataclass(frozen=True)
class ReferenceUnavailable:
    reason: str


ReferenceGate = Union[ReferenceOk, ReferenceUnavailable]


def prior_trading_day(day: date) -> date:
    """Previous weekday (weekends skipped)."""
    d = day - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def required_session_for_provenance(
    provenance: FieldProvenance,
    now: datetime,
    *,
    rth_open: time = time(9, 30),
) -> Optional[SessionId]:
    """Session a field of ``provenance`` must carry to be valid at ``now``."""
    today = now.date()
    local_time = now.timetz().replace(tzinfo=None) if now.tzinfo else now.time()

    if provenance is FieldProvenance.CURRENT_LIVE_SESSION:
        if local_time < rth_open:
            return None
        return SessionId(trading_day=today)

    if provenance is FieldProvenance.PRIOR_COMPLETED_SESSION:
        return SessionId(trading_day=prior_trading_day(today))

    raise ValueError(f"unknown provenance: {provenance}")


def gate_reference_set(
    refset: ReferenceSet,
    now: datetime,
    *,
    rth_open: time = time(9, 30),
    required_session: Optional[Callable[[FieldProvenance, datetime], Optional[SessionId]]] = None,
) -> ReferenceGate:
    """Return whether every field satisfies its provenance rule at ``now``."""
    if not refset.fields:
        return ReferenceUnavailable("reference: empty set")

    session_fn = required_session or (
        lambda prov, ts: required_session_for_provenance(prov, ts, rth_open=rth_open)
    )

    for field in refset.fields:
        needed = session_fn(field.provenance, now)
        if needed is None:
            return ReferenceUnavailable(f"reference: {field.name} has no live session yet at {now}")
        if field.session.trading_day != needed.trading_day:
            return ReferenceUnavailable(
                f"reference: {field.name} stale "
                f"({field.provenance.value}, have {field.session.trading_day}, need {needed.trading_day})"
            )
    return ReferenceOk(as_of=now)
