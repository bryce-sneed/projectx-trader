"""
Config provenance — what a process actually loaded vs what is on disk.

The filesystem is the artifact everyone checks; it is not what the running process is using.
Compare DEPLOYED (file) against RUNNING (snapshot published at load time). Answers are
three-way — match, mismatch, or cannot-determine — never a boolean that collapses
unreachable with agrees.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional

from .riskstate import FeatureConfig, read_feature_config


@dataclass(frozen=True)
class RunningConfig:
    """Config a process published at load time — not read from memory on demand."""

    identity: str
    loaded_at: float
    values: Mapping[str, str]


@dataclass(frozen=True)
class DeployedConfig:
    """Config as read from disk at comparison time."""

    path: str
    mtime: float
    values: Mapping[str, str]


class ProvenanceVerdict(Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    CANNOT_DETERMINE = "cannot_determine"


@dataclass(frozen=True)
class ProvenanceResult:
    verdict: ProvenanceVerdict
    pending_reload: bool
    reason: str


def parse_env_text(text: str) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines (``#`` comments and blanks skipped)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def snapshot_at_load(
    identity: str,
    values: Mapping[str, str],
    *,
    loaded_at: float,
) -> RunningConfig:
    """Record what a process actually loaded when it started."""
    return RunningConfig(identity=identity, loaded_at=loaded_at, values=dict(values))


def read_deployed(path: Path | str) -> Optional[DeployedConfig]:
    """Read deployed config from disk. Returns ``None`` if unreadable."""
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
        mtime = config_path.stat().st_mtime
    except OSError:
        return None
    return DeployedConfig(path=str(config_path), mtime=mtime, values=parse_env_text(text))


def pending_reload(running: RunningConfig, deployed: DeployedConfig) -> bool:
    """True when the on-disk file is newer than the process load time."""
    return deployed.mtime > running.loaded_at


def compare_provenance(
    deployed: Optional[DeployedConfig],
    running: Optional[RunningConfig],
) -> ProvenanceResult:
    """Compare deployed file against running snapshot. Never conflates unreachable with match."""
    if running is None:
        return ProvenanceResult(
            ProvenanceVerdict.CANNOT_DETERMINE,
            pending_reload=False,
            reason="running config unavailable",
        )
    if deployed is None:
        return ProvenanceResult(
            ProvenanceVerdict.CANNOT_DETERMINE,
            pending_reload=False,
            reason="deployed config unreadable",
        )

    is_pending = pending_reload(running, deployed)
    if running.values == deployed.values:
        if is_pending:
            return ProvenanceResult(
                ProvenanceVerdict.MISMATCH,
                pending_reload=True,
                reason="deployed file changed after process load; running config not reloaded",
            )
        return ProvenanceResult(
            ProvenanceVerdict.MATCH,
            pending_reload=False,
            reason="deployed matches running",
        )

    return ProvenanceResult(
        ProvenanceVerdict.MISMATCH,
        pending_reload=is_pending,
        reason="deployed values differ from running",
    )


def deployed_feature_state(deployed: DeployedConfig, key: str) -> FeatureConfig:
    """Feature flag from deployed file — missing key is unconfigured, not disabled."""
    return read_feature_config(deployed.values, key)
