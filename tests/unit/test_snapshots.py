from __future__ import annotations

import importlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import types

from tradingx.snapshots import (
    CandidateIntentSnapshot,
    ContentAddressedSnapshotStore,
    DecisionSnapshotV1,
)


def _build_snapshot(*, dry_run: bool) -> DecisionSnapshotV1:
    return DecisionSnapshotV1(
        schema_version=1,
        timestamp_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        cycle_correlation_id="cycle-1",
        session_snapshot_id="session-1",
        universe_snapshot_id="universe-1",
        policy_snapshot_id="policy-1",
        model_snapshot_id="model-1",
        strategy_version="baseline-long-only-v1",
        strategy_config_hash="strategy-config-hash",
        git_sha="abc1234",
        dry_run=dry_run,
        market_data_window_hash="market-window-hash",
        feature_snapshot_id="feature-1",
        session_start_equity=Decimal("100000"),
        candidate_intents=(
            CandidateIntentSnapshot(
                symbol="SPY",
                selected=True,
                terminal_reason="selected_for_entry",
                base_score=Decimal("0.9"),
                final_score=Decimal("0.75"),
                eligibility="eligible",
                risk_status="approved",
            ),
            CandidateIntentSnapshot(
                symbol="QQQ",
                selected=False,
                terminal_reason="below_threshold",
                base_score=Decimal("0.7"),
                final_score=Decimal("0.45"),
                eligibility="eligible",
                risk_status="not_evaluated",
            ),
        ),
        final_action="buy",
        risk_verdict_id="risk-1",
    )


def test_decision_snapshot_store_is_content_addressed(tmp_path: Path) -> None:
    store = ContentAddressedSnapshotStore(tmp_path)
    snapshot = _build_snapshot(dry_run=True)

    first_path = store.write_decision_snapshot(snapshot)
    second_path = store.write_decision_snapshot(snapshot)

    assert first_path == second_path
    assert first_path.parent == tmp_path
    assert first_path.suffix == ".json"
    payload = json.loads(first_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["dry_run"] is True
    assert payload["git_sha"] == "abc1234"
    assert payload["strategy_config_hash"] == "strategy-config-hash"
    assert payload["session_start_equity"] == "100000"


def test_decision_snapshot_id_changes_when_dry_run_changes(tmp_path: Path) -> None:
    store = ContentAddressedSnapshotStore(tmp_path)

    dry_run_path = store.write_decision_snapshot(_build_snapshot(dry_run=True))
    live_path = store.write_decision_snapshot(_build_snapshot(dry_run=False))

    assert dry_run_path != live_path


def test_decision_snapshot_store_uses_atomic_replace(tmp_path: Path, monkeypatch) -> None:
    module = importlib.import_module("tradingx.snapshots")
    replace_calls: list[tuple[str, str]] = []

    def recording_replace(source, target) -> None:
        replace_calls.append((os.fspath(source), os.fspath(target)))
        os.replace(source, target)

    monkeypatch.setattr(
        module,
        "os",
        types.SimpleNamespace(replace=recording_replace, fsync=os.fsync),
    )

    store = module.ContentAddressedSnapshotStore(tmp_path)
    store.write_decision_snapshot(_build_snapshot(dry_run=True))

    assert replace_calls
