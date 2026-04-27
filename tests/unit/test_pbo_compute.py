from __future__ import annotations

import random
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingx.pbo import (
    InsufficientCPCVCohortError,
    MixedCohortWindowError,
    compute_pbo,
)
from tradingx.types import CPCVTrialRecord


def _make_records(
    *,
    cohort_window_id: str,
    n_paths: int,
    strategy_ids: tuple[str, ...],
    oos_sharpe_by_strategy_path: dict[tuple[str, int], Decimal],
    is_sharpe_default: Decimal = Decimal("0.0"),
) -> tuple[CPCVTrialRecord, ...]:
    records: list[CPCVTrialRecord] = []
    for strategy in strategy_ids:
        candidate_id, _, config_fingerprint = strategy.partition("::")
        for path_index in range(n_paths):
            records.append(
                CPCVTrialRecord(
                    trial_id=f"cpcv-{cohort_window_id}-{strategy}-path-{path_index}",
                    cohort_window_id=cohort_window_id,
                    candidate_id=candidate_id,
                    config_fingerprint=config_fingerprint,
                    strategy_config_id=strategy,
                    cpcv_path_id=f"path-{path_index:04d}",
                    n_groups=10,
                    test_group_count=2,
                    embargo_days=5,
                    label_horizon=1,
                    window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
                    window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
                    train_indices=(0, 1),
                    test_indices=(2, 3),
                    in_sample_sharpe=is_sharpe_default,
                    out_of_sample_sharpe=oos_sharpe_by_strategy_path[
                        (strategy, path_index)
                    ],
                    in_sample_n_trades=1,
                    out_of_sample_n_trades=1,
                    git_sha="abc123",
                    recorded_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
                )
            )
    return tuple(records)


def test_iid_noise_cohort_gives_pbo_around_half() -> None:
    rng = random.Random(2026)
    strategies = tuple(f"cand::cfg{index}" for index in range(60))
    cells = {
        (strategy, path_index): Decimal(str(rng.gauss(0.0, 1.0)))
        for strategy in strategies
        for path_index in range(45)
    }

    report = compute_pbo(
        cpcv_records=_make_records(
            cohort_window_id="cohort-iid",
            n_paths=45,
            strategy_ids=strategies,
            oos_sharpe_by_strategy_path=cells,
        ),
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )

    assert Decimal("0.40") <= report.pbo_value <= Decimal("0.60")


def test_dominant_strategy_cohort_gives_pbo_near_zero() -> None:
    strategies = tuple(f"cand::cfg{index}" for index in range(60))
    cells = {("cand::cfg0", path_index): Decimal("5.0") for path_index in range(45)}
    for strategy_index in range(1, 60):
        for path_index in range(45):
            cells[(f"cand::cfg{strategy_index}", path_index)] = Decimal("0.0")

    report = compute_pbo(
        cpcv_records=_make_records(
            cohort_window_id="cohort-dominant",
            n_paths=45,
            strategy_ids=strategies,
            oos_sharpe_by_strategy_path=cells,
        ),
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )

    assert report.pbo_value <= Decimal("0.05")


def test_lucky_winner_cohort_elevates_pbo_above_zero() -> None:
    rng = random.Random(4242)
    strategies = tuple(f"cand::cfg{index}" for index in range(60))
    lucky_paths = set(rng.sample(range(45), 45 // 2))
    cells: dict[tuple[str, int], Decimal] = {}
    for strategy_index, strategy in enumerate(strategies):
        for path_index in range(45):
            if strategy_index == 0 and path_index in lucky_paths:
                cells[(strategy, path_index)] = Decimal("10.0")
            elif strategy_index == 0:
                cells[(strategy, path_index)] = Decimal("-5.0")
            else:
                cells[(strategy, path_index)] = Decimal(str(rng.gauss(0.0, 1.0)))

    report = compute_pbo(
        cpcv_records=_make_records(
            cohort_window_id="cohort-lucky",
            n_paths=45,
            strategy_ids=strategies,
            oos_sharpe_by_strategy_path=cells,
        ),
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )

    assert report.pbo_value >= Decimal("0.02")


def test_same_seed_gives_same_pbo_value() -> None:
    rng = random.Random(999)
    strategies = tuple(f"cand::cfg{index}" for index in range(60))
    cells = {
        (strategy, path_index): Decimal(str(rng.gauss(0.0, 1.0)))
        for strategy in strategies
        for path_index in range(45)
    }
    records = _make_records(
        cohort_window_id="cohort-seed",
        n_paths=45,
        strategy_ids=strategies,
        oos_sharpe_by_strategy_path=cells,
    )

    report_a = compute_pbo(
        cpcv_records=records,
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )
    report_b = compute_pbo(
        cpcv_records=records,
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )

    assert report_a.pbo_value == report_b.pbo_value
    assert report_a.evaluation_id == report_b.evaluation_id
    assert report_a.report_id == report_b.report_id


def test_mixed_cohort_window_raises() -> None:
    mixed = (
        *_make_records(
            cohort_window_id="cohort-a",
            n_paths=45,
            strategy_ids=("cand::cfg1",),
            oos_sharpe_by_strategy_path={
                ("cand::cfg1", path_index): Decimal("0.0") for path_index in range(45)
            },
        ),
        *_make_records(
            cohort_window_id="cohort-b",
            n_paths=45,
            strategy_ids=("cand::cfg1",),
            oos_sharpe_by_strategy_path={
                ("cand::cfg1", path_index): Decimal("0.0") for path_index in range(45)
            },
        ),
    )

    with pytest.raises(MixedCohortWindowError):
        compute_pbo(
            cpcv_records=mixed,
            min_cohort_size=1,
            min_paths=20,
            random_seed=2026,
        )


def test_insufficient_cohort_raises() -> None:
    strategies = tuple(f"cand::cfg{index}" for index in range(10))
    records = _make_records(
        cohort_window_id="cohort-small",
        n_paths=45,
        strategy_ids=strategies,
        oos_sharpe_by_strategy_path={
            (strategy, path_index): Decimal("0.0")
            for strategy in strategies
            for path_index in range(45)
        },
    )

    with pytest.raises(InsufficientCPCVCohortError):
        compute_pbo(
            cpcv_records=records,
            min_cohort_size=50,
            min_paths=20,
            random_seed=2026,
        )


def test_report_fields_populated() -> None:
    rng = random.Random(7)
    strategies = tuple(f"cand::cfg{index}" for index in range(60))
    report = compute_pbo(
        cpcv_records=_make_records(
            cohort_window_id="cohort-fields",
            n_paths=45,
            strategy_ids=strategies,
            oos_sharpe_by_strategy_path={
                (strategy, path_index): Decimal(str(rng.gauss(0.0, 1.0)))
                for strategy in strategies
                for path_index in range(45)
            },
        ),
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )

    assert report.cohort_window_id == "cohort-fields"
    assert report.cohort_size == 60
    assert report.n_paths == 45
    assert report.n_splits_sampled == 10_000
    assert report.metric_name == "lo_adjusted_sharpe"
    assert report.random_seed == 2026
    assert report.cpcv_config_fingerprint == "N=10,k=2,h=5,L=1"
    assert [float(pct) for pct, _ in report.logit_distribution_percentiles] == [
        5.0,
        25.0,
        50.0,
        75.0,
        95.0,
    ]


def test_full_cpcv_matrix_ref_is_threaded_into_report() -> None:
    rng = random.Random(11)
    strategies = tuple(f"cand::cfg{index}" for index in range(60))

    report = compute_pbo(
        cpcv_records=_make_records(
            cohort_window_id="cohort-matrix-ref",
            n_paths=45,
            strategy_ids=strategies,
            oos_sharpe_by_strategy_path={
                (strategy, path_index): Decimal(str(rng.gauss(0.0, 1.0)))
                for strategy in strategies
                for path_index in range(45)
            },
        ),
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
        full_cpcv_matrix_ref="cas://validation/full-cpcv-matrix.json",
    )

    assert report.full_cpcv_matrix_ref == "cas://validation/full-cpcv-matrix.json"
