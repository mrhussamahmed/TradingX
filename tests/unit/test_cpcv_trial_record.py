from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import CPCVTrialRecord


def _record(
    *,
    cohort_window_id: str = "cohort-a1b2c3d4e5f60718",
    strategy_config_id: str = "trend-following-v1::cfg-abc123",
    cpcv_path_id: str = "path-0001",
) -> CPCVTrialRecord:
    return CPCVTrialRecord(
        trial_id=f"cpcv-{cohort_window_id}-{strategy_config_id}-{cpcv_path_id}",
        cohort_window_id=cohort_window_id,
        candidate_id="trend-following-v1",
        config_fingerprint="cfg-abc123",
        strategy_config_id=strategy_config_id,
        cpcv_path_id=cpcv_path_id,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
        window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
        train_indices=(0, 1, 2, 3, 4),
        test_indices=(5, 6, 7, 8, 9),
        in_sample_sharpe=Decimal("1.23"),
        out_of_sample_sharpe=Decimal("0.87"),
        in_sample_n_trades=42,
        out_of_sample_n_trades=9,
        git_sha="0123456789abcdef",
        recorded_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
    )


def test_cpcv_trial_record_is_frozen() -> None:
    record = _record()

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.candidate_id = "other"  # type: ignore[misc]


def test_write_and_list_cpcv_trial_record_roundtrip(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    record = _record()

    written_path = store.write_cpcv_trial_record(record)
    loaded = store.list_cpcv_trial_records(cohort_window_id=record.cohort_window_id)

    assert written_path.exists()
    assert written_path.parent.name == "cpcv_trials"
    assert written_path.name == (
        f"{record.cohort_window_id}__{record.strategy_config_id}"
        f"__{record.cpcv_path_id}.json"
    )
    assert loaded == (record,)


def test_two_records_same_strategy_different_window_do_not_collide(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    path_a = store.write_cpcv_trial_record(
        _record(cohort_window_id="cohort-aaaa1111bbbb2222")
    )
    path_b = store.write_cpcv_trial_record(
        _record(cohort_window_id="cohort-cccc3333dddd4444")
    )

    assert path_a != path_b
    assert path_a.exists()
    assert path_b.exists()


def test_record_import_comes_from_types_all() -> None:
    from tradingx import types as tradingx_types

    assert "CPCVTrialRecord" in tradingx_types.__all__
