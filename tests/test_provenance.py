"""
Config provenance tests — deployed vs running, not filesystem wishful thinking.

Mutation-check with cold cache:

    find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; python -B -m pytest tests/test_provenance.py -v
"""
import os
from pathlib import Path

import pytest

from pxtrader.provenance import (
    DeployedConfig,
    ProvenanceVerdict,
    compare_provenance,
    deployed_feature_state,
    read_deployed,
    snapshot_at_load,
)
from pxtrader.riskstate import FeatureConfig


def _write_env(path: Path, text: str, *, mtime: float) -> DeployedConfig:
    path.write_text(text, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    deployed = read_deployed(path)
    assert deployed is not None
    return deployed


def test_env_edited_after_process_start_is_detected_as_pending(tmp_path: Path):
    """Editing .env after load changes mtime — running snapshot is stale even if values match."""
    env = tmp_path / ".env"
    running = snapshot_at_load(
        "bot-1",
        {"FEATURE": "enabled"},
        loaded_at=1_000.0,
    )
    deployed = _write_env(env, "FEATURE=enabled\n", mtime=2_000.0)

    result = compare_provenance(deployed, running)

    assert result.verdict is ProvenanceVerdict.MISMATCH
    assert result.pending_reload is True
    assert "not reloaded" in result.reason


def test_deleted_key_does_not_read_as_disabled(tmp_path: Path):
    """A deleted config line is unconfigured on disk — not disabled, and running may still be enabled."""
    env = tmp_path / "features.env"
    deployed = _write_env(env, "OTHER=enabled\n", mtime=1_000.0)

    assert deployed_feature_state(deployed, "DAILY_LOSS_CAP") is FeatureConfig.UNCONFIGURED

    running = snapshot_at_load(
        "bot-1",
        {"OTHER": "enabled", "DAILY_LOSS_CAP": "enabled"},
        loaded_at=1_000.0,
    )
    result = compare_provenance(deployed, running)
    assert result.verdict is ProvenanceVerdict.MISMATCH


def test_unreachable_process_is_not_reported_as_matching(tmp_path: Path):
    env = tmp_path / ".env"
    deployed = _write_env(env, "FEATURE=enabled\n", mtime=1_000.0)

    result = compare_provenance(deployed, running=None)

    assert result.verdict is ProvenanceVerdict.CANNOT_DETERMINE
    assert result.verdict is not ProvenanceVerdict.MATCH


def test_matching_deployed_and_running_reports_match(tmp_path: Path):
    """Accept-path: identical config loaded after last file edit is a match, not perpetual mismatch."""
    env = tmp_path / ".env"
    deployed = _write_env(env, "FEATURE=enabled\n", mtime=1_000.0)
    running = snapshot_at_load("bot-1", deployed.values, loaded_at=2_000.0)

    result = compare_provenance(deployed, running)

    assert result.verdict is ProvenanceVerdict.MATCH
    assert result.pending_reload is False


def test_value_mismatch_detected_when_running_differs(tmp_path: Path):
    env = tmp_path / ".env"
    deployed = _write_env(env, "SIZE=2\n", mtime=1_000.0)
    running = snapshot_at_load("bot-1", {"SIZE": "3"}, loaded_at=2_000.0)

    result = compare_provenance(deployed, running)

    assert result.verdict is ProvenanceVerdict.MISMATCH
    assert "differ" in result.reason
