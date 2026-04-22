from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import SleeveDecompositionRecord, SleeveTargetWeights


def _record(decomposition_id: str = "decomp-1") -> SleeveDecompositionRecord:
    return SleeveDecompositionRecord(
        decomposition_id=decomposition_id,
        cycle_id="cycle-2026-04-22-1430",
        trading_day="2026-04-22",
        recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
        blueprint_activation_id="activation-x",
        per_sleeve_target_weights=(
            SleeveTargetWeights(
                sleeve_id="trend-following-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.4")),),
            ),
            SleeveTargetWeights(
                sleeve_id="vol-target-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.2")),),
            ),
        ),
    )


def test_sleeve_decomposition_record_roundtrip(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    record = _record()
    store.write_sleeve_decomposition_record(record)
    records = store.list_sleeve_decomposition_records(trading_day="2026-04-22")
    assert record in records


def test_list_sleeve_decomposition_filters_by_day(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    same_day = _record("decomp-a")
    different_day = SleeveDecompositionRecord(
        decomposition_id="decomp-b",
        cycle_id="cycle-2026-04-23-1430",
        trading_day="2026-04-23",
        recorded_at_utc=same_day.recorded_at_utc,
        blueprint_activation_id=same_day.blueprint_activation_id,
        per_sleeve_target_weights=same_day.per_sleeve_target_weights,
    )
    store.write_sleeve_decomposition_record(same_day)
    store.write_sleeve_decomposition_record(different_day)
    records = store.list_sleeve_decomposition_records(trading_day="2026-04-22")
    assert records == (same_day,)
