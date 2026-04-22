from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import CPCVTrialRecord


def _record(
    *,
    cohort_window_id: str,
    strategy_config_id: str,
    cpcv_path_id: str,
    recorded_at_utc: datetime,
    git_sha: str = "abc123",
) -> CPCVTrialRecord:
    candidate_id, _, config_fingerprint = strategy_config_id.partition("::")
    return CPCVTrialRecord(
        trial_id=f"cpcv-{cohort_window_id}-{strategy_config_id}-{cpcv_path_id}",
        cohort_window_id=cohort_window_id,
        candidate_id=candidate_id,
        config_fingerprint=config_fingerprint,
        strategy_config_id=strategy_config_id,
        cpcv_path_id=cpcv_path_id,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
        window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
        train_indices=(0, 1, 2),
        test_indices=(3, 4, 5),
        in_sample_sharpe=Decimal("1.0"),
        out_of_sample_sharpe=Decimal("0.8"),
        in_sample_n_trades=10,
        out_of_sample_n_trades=3,
        git_sha=git_sha,
        recorded_at_utc=recorded_at_utc,
    )


def test_list_cpcv_trial_records_filters_to_cohort_window(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    now = datetime(2026, 4, 22, 13, 0, tzinfo=UTC)
    for cohort in ("cohort-aaaa", "cohort-bbbb"):
        for path_index in range(2):
            store.write_cpcv_trial_record(
                _record(
                    cohort_window_id=cohort,
                    strategy_config_id="trend::cfg1",
                    cpcv_path_id=f"path-{path_index}",
                    recorded_at_utc=now,
                )
            )

    records = store.list_cpcv_trial_records(cohort_window_id="cohort-aaaa")

    assert len(records) == 2
    assert all(record.cohort_window_id == "cohort-aaaa" for record in records)


def test_list_cpcv_cohort_windows_aggregates_metadata(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    earliest = datetime(2026, 4, 22, 10, 0, tzinfo=UTC)
    latest = datetime(2026, 4, 22, 13, 0, tzinfo=UTC)
    for strategy in ("trend::cfg1", "trend::cfg2", "vol::cfg1"):
        for path_index in range(3):
            store.write_cpcv_trial_record(
                _record(
                    cohort_window_id="cohort-one",
                    strategy_config_id=strategy,
                    cpcv_path_id=f"path-{path_index}",
                    recorded_at_utc=earliest if path_index == 0 else latest,
                    git_sha="abc123" if strategy != "vol::cfg1" else "def456",
                )
            )
    store.write_cpcv_trial_record(
        _record(
            cohort_window_id="cohort-two",
            strategy_config_id="trend::cfg1",
            cpcv_path_id="path-0",
            recorded_at_utc=latest,
        )
    )

    summaries = store.list_cpcv_cohort_windows()
    by_id = {summary.cohort_window_id: summary for summary in summaries}

    assert len(summaries) == 2
    assert by_id["cohort-one"].record_count == 9
    assert by_id["cohort-one"].strategy_config_count == 3
    assert by_id["cohort-one"].path_count == 3
    assert by_id["cohort-one"].earliest_recorded_at_utc == earliest
    assert by_id["cohort-one"].latest_recorded_at_utc == latest
    assert by_id["cohort-one"].git_shas == frozenset({"abc123", "def456"})
    assert by_id["cohort-two"].record_count == 1


def test_list_cpcv_cohort_windows_orders_by_earliest_ascending(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_cpcv_trial_record(
        _record(
            cohort_window_id="cohort-new",
            strategy_config_id="trend::cfg1",
            cpcv_path_id="path-0",
            recorded_at_utc=datetime(2026, 6, 1, tzinfo=UTC),
        )
    )
    store.write_cpcv_trial_record(
        _record(
            cohort_window_id="cohort-old",
            strategy_config_id="trend::cfg1",
            cpcv_path_id="path-0",
            recorded_at_utc=datetime(2025, 10, 1, tzinfo=UTC),
        )
    )

    summaries = store.list_cpcv_cohort_windows()

    assert summaries[0].cohort_window_id == "cohort-old"
    assert summaries[1].cohort_window_id == "cohort-new"


def test_list_cpcv_cohort_windows_empty_store_returns_empty(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)

    assert store.list_cpcv_cohort_windows() == ()
