from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tradingx.drift.reference import (
    FeatureDistribution,
    build_reference_distribution_snapshot,
    load_reference_distribution_snapshot,
    write_reference_distribution_snapshot,
)


def test_feature_distribution_bin_proportions_sum_to_one() -> None:
    distribution = FeatureDistribution(
        feature_name="foo",
        bin_edges=(Decimal("0"), Decimal("0.5"), Decimal("1.0")),
        bin_proportions=(Decimal("0.4"), Decimal("0.6")),
        observation_count=100,
    )
    assert sum(distribution.bin_proportions, Decimal("0")) == Decimal("1.0")


def test_build_snapshot_produces_deterministic_bins_for_canned_samples() -> None:
    snapshot = build_reference_distribution_snapshot(
        reference_snapshot_id="ref-1",
        blueprint_id="bp",
        feature_samples_by_name={
            "foo": pd.Series([float(index) / 100.0 for index in range(100)])
        },
        signal_samples_by_sleeve_id={
            "trend-following-v1": pd.Series([-1.0] * 50 + [1.0] * 50)
        },
        reference_window_start_utc=datetime(2024, 1, 1, tzinfo=UTC),
        reference_window_end_utc=datetime(2025, 1, 1, tzinfo=UTC),
        n_bins=10,
        generated_at_utc=datetime(2025, 1, 1, tzinfo=UTC),
    )
    feature = snapshot.feature_distributions[0]
    assert snapshot.reference_snapshot_id == "ref-1"
    assert feature.feature_name == "foo"
    assert len(feature.bin_edges) == 11
    assert len(feature.bin_proportions) == 10
    assert abs(sum(feature.bin_proportions, Decimal("0")) - Decimal("1.0")) < Decimal(
        "0.0001"
    )
    assert feature.observation_count == 100


def test_build_signal_distribution_preserves_raw_samples() -> None:
    snapshot = build_reference_distribution_snapshot(
        reference_snapshot_id="ref-sig",
        blueprint_id="bp",
        feature_samples_by_name={},
        signal_samples_by_sleeve_id={"sleeve-x": pd.Series([1.0, 2.0, 3.0])},
        reference_window_start_utc=datetime(2024, 1, 1, tzinfo=UTC),
        reference_window_end_utc=datetime(2025, 1, 1, tzinfo=UTC),
        generated_at_utc=datetime(2025, 1, 1, tzinfo=UTC),
    )
    signal = snapshot.signal_distributions[0]
    assert signal.sleeve_id == "sleeve-x"
    assert signal.observation_count == 3
    assert signal.observed_samples == (
        Decimal("1.0"),
        Decimal("2.0"),
        Decimal("3.0"),
    )


def test_snapshot_roundtrip(tmp_path: Path) -> None:
    snapshot = build_reference_distribution_snapshot(
        reference_snapshot_id="ref-rt",
        blueprint_id="bp-rt",
        feature_samples_by_name={"foo": pd.Series([1.0, 2.0, 3.0, 4.0])},
        signal_samples_by_sleeve_id={"sleeve": pd.Series([0.1, 0.2])},
        reference_window_start_utc=datetime(2024, 1, 1, tzinfo=UTC),
        reference_window_end_utc=datetime(2024, 6, 1, tzinfo=UTC),
        n_bins=4,
        generated_at_utc=datetime(2024, 6, 1, tzinfo=UTC),
    )
    path = tmp_path / "ref.json"
    write_reference_distribution_snapshot(path, snapshot)
    assert load_reference_distribution_snapshot(path) == snapshot


def test_load_missing_snapshot_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_reference_distribution_snapshot(tmp_path / "missing.json")
