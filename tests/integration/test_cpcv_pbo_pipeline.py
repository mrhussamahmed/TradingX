from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd

from tradingx.controller import GateValidationController
from tradingx.pbo import cohort_window_id_for
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    BenchmarkStackPayload,
    CPCVTrialRecord,
    OperatingConstraintBudget,
)


def _ohlcv_frame(*, periods: int) -> pd.DataFrame:
    index = pd.date_range("2023-01-03", periods=periods, freq="B", tz="UTC")
    close_series = pd.Series(
        [100.0 + (index_value * 0.25) for index_value in range(periods)],
        index=index,
        dtype=float,
    )
    return pd.DataFrame(
        {
            "open": close_series,
            "high": close_series * 1.01,
            "low": close_series * 0.99,
            "close": close_series,
            "bid": close_series - 0.05,
            "ask": close_series + 0.05,
            "volume": 1_000_000.0,
        },
        index=index,
    )


class FakeHistoricalMarketDataGateway:
    def __init__(self, *, periods: int = 200) -> None:
        self._bars_by_symbol = {
            "SPY": _ohlcv_frame(periods=periods),
            "QQQ": _ohlcv_frame(periods=periods),
        }

    def get_daily_bar_history(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
        feed: str = "iex",
        adjustment: str = "dividend",
    ) -> pd.DataFrame:
        del start_utc, end_utc, feed, adjustment
        return self._bars_by_symbol[symbol].copy()


def _benchmark_stack_payload(*, periods: int) -> BenchmarkStackPayload:
    return BenchmarkStackPayload(
        hurdle_returns=tuple(Decimal("0.0002") for _ in range(periods)),
        opportunity_cost_returns=tuple(Decimal("0.0004") for _ in range(periods)),
        opportunity_cost_weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal("0.15"),
            max_drawdown_halt=Decimal("0.25"),
            cdar_threshold=Decimal("0.12"),
            cdar_confidence=Decimal("0.95"),
        ),
    )


def _synthetic_record(
    *,
    cohort_window_id: str,
    strategy_config_id: str,
    cpcv_path_id: str,
    out_of_sample_sharpe: Decimal,
    recorded_at_utc: datetime,
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
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 6, 19, tzinfo=UTC),
        train_indices=(0, 1),
        test_indices=(2, 3),
        in_sample_sharpe=Decimal("0.0"),
        out_of_sample_sharpe=out_of_sample_sharpe,
        in_sample_n_trades=1,
        out_of_sample_n_trades=1,
        git_sha="seeded",
        recorded_at_utc=recorded_at_utc,
    )


def _criterion_status(candidate_result, criterion_id: str) -> str:  # type: ignore[no-untyped-def]
    criterion = next(
        entry
        for entry in candidate_result.criteria
        if entry.criterion_id == criterion_id
    )
    return criterion.status or ("pass" if criterion.passed else "fail")


def test_cpcv_pipeline_activates_pbo_and_writes_one_report_per_run(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    window_start_utc = datetime(2023, 1, 3, tzinfo=UTC)
    window_end_utc = datetime(2023, 6, 19, tzinfo=UTC)
    current_cohort_window_id = cohort_window_id_for(
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
    )
    mature_window_start_utc = datetime(2022, 1, 3, tzinfo=UTC)
    mature_window_end_utc = datetime(2022, 6, 20, tzinfo=UTC)
    mature_cohort_window_id = cohort_window_id_for(
        window_start_utc=mature_window_start_utc,
        window_end_utc=mature_window_end_utc,
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
    )
    seeded_rng = random.Random(2026)
    mature_recorded_at_utc = datetime.now(UTC) - timedelta(days=200)
    current_recorded_at_utc = datetime.now(UTC) - timedelta(days=1)
    for strategy_index in range(50):
        strategy_config_id = f"mature-{strategy_index:02d}::cfg-{strategy_index:02d}"
        for path_index in range(45):
            store.write_cpcv_trial_record(
                _synthetic_record(
                    cohort_window_id=mature_cohort_window_id,
                    strategy_config_id=strategy_config_id,
                    cpcv_path_id=f"path-{path_index:04d}",
                    out_of_sample_sharpe=Decimal(str(seeded_rng.gauss(0.0, 1.0))),
                    recorded_at_utc=mature_recorded_at_utc,
                )
            )
    for strategy_index in range(60):
        strategy_config_id = f"synthetic-{strategy_index:02d}::cfg-{strategy_index:02d}"
        for path_index in range(45):
            store.write_cpcv_trial_record(
                _synthetic_record(
                    cohort_window_id=current_cohort_window_id,
                    strategy_config_id=strategy_config_id,
                    cpcv_path_id=f"path-{path_index:04d}",
                    out_of_sample_sharpe=Decimal(str(seeded_rng.gauss(0.0, 1.0))),
                    recorded_at_utc=current_recorded_at_utc,
                )
            )

    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )
    result = controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        universe=("SPY", "QQQ"),
    )
    rerun_result = controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        universe=("SPY", "QQQ"),
    )

    records = store.list_cpcv_trial_records(cohort_window_id=current_cohort_window_id)
    summaries = store.list_cpcv_cohort_windows()
    pbo_reports = sorted((tmp_path / "pbo_reports").glob("*.json"))

    assert result.report.gate_id == "1"
    assert rerun_result.report.gate_id == "1"
    assert len(records) == 2790
    assert summaries[-1].cohort_window_id == current_cohort_window_id
    assert summaries[-1].strategy_config_count >= 62
    assert len(pbo_reports) == 2
    assert pbo_reports[0].name != pbo_reports[1].name
    assert all(
        _criterion_status(candidate_result, "pbo_overfitting") in {"pass", "fail"}
        for candidate_result in result.report.candidate_results
    )
    assert all(
        _criterion_status(candidate_result, "pbo_overfitting") in {"pass", "fail"}
        for candidate_result in rerun_result.report.candidate_results
    )
