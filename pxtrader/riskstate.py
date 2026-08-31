"""
Risk state — limits, configuration, and locks that fail closed by construction.

A risk-limiting input that is missing, stale, unknown, or sentinel must never be interpreted as
permission. Callers receive ``Limit`` (value or unavailable), ``FeatureConfig`` (explicit states),
and ``RiskLockRegistry`` (authority-scoped locks) — never a raw float that silently means unlimited.
"""
from __future__ import annotations

import math
import time as _time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping, Optional, Union


@dataclass(frozen=True)
class LimitOk:
    """A verified, finite risk limit suitable for downstream sizing."""

    value: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError(f"limit must be finite, got {self.value!r}")


@dataclass(frozen=True)
class LimitUnavailable:
    """Risk limit cannot be trusted — callers must halt or refuse to size."""

    reason: str


Limit = Union[LimitOk, LimitUnavailable]


def limit_from_reading(raw: Optional[float], *, context: str) -> Limit:
    """Translate a raw numeric reading into ``Limit``. Missing/non-finite → unavailable."""
    if raw is None:
        return LimitUnavailable(f"{context}: missing")
    if not math.isfinite(raw):
        return LimitUnavailable(f"{context}: non-finite ({raw!r})")
    return LimitOk(raw)


def broker_headroom_from_reading(
    raw: Optional[float],
    *,
    unknown_sentinel: float = 9999.0,
    context: str = "broker headroom",
) -> Limit:
    """Broker-boundary reader — rejects integration-specific unknown sentinels before ``Limit``."""
    if raw is not None and raw == unknown_sentinel:
        return LimitUnavailable(f"{context}: broker unknown sentinel ({raw})")
    return limit_from_reading(raw, context=context)


@dataclass(frozen=True)
class LedgerSnapshot:
    peak_equity: float
    running_equity: float
    as_of: Optional[float] = None


def parse_ledger_text(text: str) -> tuple[Optional[list[LedgerSnapshot]], Optional[LimitUnavailable]]:
    """Parse ledger rows. Any malformed data row is unavailable — never silently skipped."""
    rows: list[LedgerSnapshot] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("peak"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) not in (2, 3):
            return None, LimitUnavailable(f"ledger: malformed row ({line!r})")
        try:
            peak = float(parts[0])
            running = float(parts[1])
            as_of = float(parts[2]) if len(parts) == 3 else None
        except ValueError:
            return None, LimitUnavailable(f"ledger: non-numeric row ({line!r})")
        if not math.isfinite(peak) or not math.isfinite(running):
            return None, LimitUnavailable(f"ledger: non-finite row ({line!r})")
        if as_of is not None and not math.isfinite(as_of):
            return None, LimitUnavailable(f"ledger: non-finite as_of ({line!r})")
        rows.append(LedgerSnapshot(peak_equity=peak, running_equity=running, as_of=as_of))
    return rows, None


def _ledger_as_of_epoch(rows: list[LedgerSnapshot], ledger_path: Path) -> Optional[float]:
    if rows and rows[-1].as_of is not None:
        return rows[-1].as_of
    try:
        return ledger_path.stat().st_mtime
    except OSError:
        return None


def headroom_from_ledger_file(
    path: Path | str,
    *,
    trail_allowance: float = 2000.0,
    now: Callable[[], float] = _time.time,
    max_age_seconds: float = 86_400.0,
) -> Limit:
    """Drawdown headroom from a day-ledger file. Empty, stale, or corrupt ledgers are unavailable."""
    ledger_path = Path(path)
    if not ledger_path.exists():
        return LimitUnavailable("ledger: file missing")

    text = ledger_path.read_text(encoding="utf-8")
    if not text.strip():
        return LimitUnavailable("ledger: empty file")

    rows, parse_error = parse_ledger_text(text)
    if parse_error is not None:
        return parse_error
    assert rows is not None
    if not rows:
        return LimitUnavailable("ledger: no parseable entries")

    as_of = _ledger_as_of_epoch(rows, ledger_path)
    if as_of is not None and now() - as_of > max_age_seconds:
        return LimitUnavailable("ledger: stale")

    peak = max(row.peak_equity for row in rows)
    running = rows[-1].running_equity
    if peak == 0.0 and running == 0.0:
        return LimitUnavailable("ledger: zero baseline with no equity history")

    drawdown_used = peak - running
    return limit_from_reading(trail_allowance - drawdown_used, context="ledger headroom")


def size_contracts(
    headroom: Limit,
    *,
    rule_max: int,
    dollars_per_contract: float,
) -> Limit:
    """Contract count from headroom. Unavailable headroom never sizes — no silent unlimited."""
    if isinstance(headroom, LimitUnavailable):
        return headroom
    if dollars_per_contract <= 0:
        return LimitUnavailable("sizer: non-positive dollars_per_contract")
    contracts = int(headroom.value // dollars_per_contract)
    if contracts < 0:
        return LimitUnavailable("sizer: negative contract count")
    return LimitOk(float(min(contracts, rule_max)))


class FeatureConfig(Enum):
    """Explicit feature state — absence is its own state, not disabled and not enabled."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    UNCONFIGURED = "unconfigured"


def read_feature_config(config: Mapping[str, str], key: str) -> FeatureConfig:
    """Read a feature flag. A deleted/missing key is ``UNCONFIGURED``, never default-enabled."""
    if key not in config:
        return FeatureConfig.UNCONFIGURED
    token = config[key].strip().lower()
    if token in {"1", "true", "yes", "on", "enabled"}:
        return FeatureConfig.ENABLED
    if token in {"0", "false", "no", "off", "disabled"}:
        return FeatureConfig.DISABLED
    return FeatureConfig.UNCONFIGURED


def feature_may_run(state: FeatureConfig) -> bool:
    """Only an explicit ``ENABLED`` state permits execution."""
    return state is FeatureConfig.ENABLED


@dataclass(frozen=True)
class RiskLock:
    authority: str
    reason: str


class RiskLockRegistry:
    """A lock records why it was taken; only the locking authority may release it."""

    def __init__(self) -> None:
        self._lock: Optional[RiskLock] = None

    def current(self) -> Optional[RiskLock]:
        return self._lock

    def acquire(self, authority: str, reason: str) -> bool:
        if self._lock is not None:
            return False
        self._lock = RiskLock(authority=authority, reason=reason)
        return True

    def release(self, authority: str) -> bool:
        if self._lock is None or self._lock.authority != authority:
            return False
        self._lock = None
        return True

    def is_locked(self) -> bool:
        return self._lock is not None


def poller_may_clear_on_flat(registry: RiskLockRegistry, *, poller: str, account_flat: bool) -> bool:
    """Flat account does not clear a lock held by another authority (circuit-breaker incident)."""
    if not account_flat:
        return False
    lock = registry.current()
    if lock is None:
        return False
    if lock.authority != poller:
        return False
    return True
