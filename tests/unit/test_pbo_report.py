from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import CPCVCohortWindowSummary, PBOReport


def _report() -> PBOReport:
    return PBOReport(
        report_id="pbo-eval-abc123",
        evaluation_id="eval-abc123",
        cohort_window_id="cohort-a1b2c3d4e5f60718",
        cohort_size=55,
        n_paths=45,
        n_splits_sampled=10_000,
        pbo_value=Decimal("0.18"),
        logit_distribution_percentiles=(
            (Decimal("5"), Decimal("-2.1")),
            (Decimal("25"), Decimal("-0.8")),
            (Decimal("50"), Decimal("0.3")),
            (Decimal("75"), Decimal("1.4")),
            (Decimal("95"), Decimal("3.2")),
        ),
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
        metric_name="lo_adjusted_sharpe",
        random_seed=2026,
        generated_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
    )


def test_pbo_report_is_frozen() -> None:
    report = _report()

    with pytest.raises(dataclasses.FrozenInstanceError):
        report.pbo_value = Decimal("0.50")  # type: ignore[misc]


def test_write_and_load_pbo_report_roundtrip(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    report = _report()

    written_path = store.write_pbo_report(report)
    loaded = store.load_pbo_report_by_evaluation_id(evaluation_id=report.evaluation_id)

    assert written_path.parent.name == "pbo_reports"
    assert loaded == report


def test_load_pbo_report_returns_none_when_missing(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)

    assert store.load_pbo_report_by_evaluation_id(evaluation_id="nope") is None


def test_cpcv_cohort_window_summary_is_frozen() -> None:
    summary = CPCVCohortWindowSummary(
        cohort_window_id="cohort-test",
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
        window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
        earliest_recorded_at_utc=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
        latest_recorded_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
        record_count=45,
        strategy_config_count=1,
        path_count=45,
        git_shas=frozenset({"abc123"}),
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.record_count = 0  # type: ignore[misc]


def test_types_all_exports_both() -> None:
    from tradingx import types as tradingx_types

    assert "PBOReport" in tradingx_types.__all__
    assert "CPCVCohortWindowSummary" in tradingx_types.__all__
