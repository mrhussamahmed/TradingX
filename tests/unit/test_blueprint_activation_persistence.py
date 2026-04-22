from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import BlueprintActivationRecord, BlueprintSleeveBinding


def _record(activation_id: str = "act-1") -> BlueprintActivationRecord:
    return BlueprintActivationRecord(
        activation_id=activation_id,
        blueprint_id="bp-default-v1",
        sleeve_activation_bindings=(
            BlueprintSleeveBinding(
                sleeve_id="trend-following-v1",
                strategy_id="trend-following-v1",
                captured_snapshot_id="snap-trend-v1-2026-04-22",
            ),
            BlueprintSleeveBinding(
                sleeve_id="vol-target-v1",
                strategy_id="vol-target-v1",
                captured_snapshot_id="snap-vol-v1-2026-04-22",
            ),
        ),
        status="active",
        approved_at_utc=datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
        approved_by="operator:hussam",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-default-v1.yaml"),
    )


def test_blueprint_activation_record_roundtrip(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    record = _record()
    path = store.write_blueprint_activation_record(record)
    assert path.exists()
    loaded = store.load_blueprint_activation_record(activation_id=record.activation_id)
    assert loaded == record


def test_list_blueprint_activation_records_returns_all(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_blueprint_activation_record(_record("act-a"))
    store.write_blueprint_activation_record(_record("act-b"))
    records = store.list_blueprint_activation_records()
    ids = {record.activation_id for record in records}
    assert ids == {"act-a", "act-b"}


def test_missing_blueprint_activation_record_returns_none(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    assert store.load_blueprint_activation_record(activation_id="nope") is None
