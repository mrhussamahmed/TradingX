from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

import tradingx.controller as controller_module
from tradingx.controller import GateValidationController
from tradingx.pbo import (
    InsufficientCPCVCohortError,
    MixedCohortWindowError,
    cohort_window_id_for,
)
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    BenchmarkStackPayload,
    CPCVTrialRecord,
    OperatingConstraintBudget,
    PBOReport,
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


class FakeHistoricalMarketDataGateway:
    def __init__(self, *, periods: int = 200) -> None:
        self.requested_symbols: list[str] = []
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
        self.requested_symbols.append(symbol)
        return self._bars_by_symbol[symbol].copy()


def _synthetic_record(
    *,
    cohort_window_id: str,
    strategy_config_id: str,
    cpcv_path_id: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
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
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        train_indices=(0, 1),
        test_indices=(2, 3),
        in_sample_sharpe=Decimal("0.0"),
        out_of_sample_sharpe=Decimal("0.0"),
        in_sample_n_trades=1,
        out_of_sample_n_trades=1,
        git_sha="seeded",
        recorded_at_utc=recorded_at_utc,
    )


def _seed_cohort(
    *,
    store: FilesystemArtifactStore,
    cohort_window_id: str,
    strategy_count: int,
    window_start_utc: datetime,
    window_end_utc: datetime,
    recorded_at_utc: datetime,
) -> None:
    for strategy_index in range(strategy_count):
        strategy_config_id = f"synthetic-{strategy_index:02d}::cfg-{strategy_index:02d}"
        for path_index in range(45):
            store.write_cpcv_trial_record(
                _synthetic_record(
                    cohort_window_id=cohort_window_id,
                    strategy_config_id=strategy_config_id,
                    cpcv_path_id=f"path-{path_index:04d}",
                    window_start_utc=window_start_utc,
                    window_end_utc=window_end_utc,
                    recorded_at_utc=recorded_at_utc,
                )
            )


def test_gate_validation_controller_writes_cpcv_trials_for_gate_1(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )

    result = controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 6, 19, tzinfo=UTC),
        universe=("SPY", "QQQ"),
    )

    evidence_report = store.build_operator_evidence_report()

    assert result.report.gate_id == "1"
    assert evidence_report["counts"]["cpcv_trials"] == 90
    assert evidence_report["counts"]["pbo_reports"] == 0


def test_gate_validation_controller_unreleased_context_writes_no_metric_artifacts(
    tmp_path,
) -> None:
    from tradingx.experiments import MetricVisibilityContext

    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )

    result = controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 6, 19, tzinfo=UTC),
        universe=("SPY", "QQQ"),
        metric_visibility_context=MetricVisibilityContext(
            experiment_id="exp-001",
            run_id="run-001",
            promotion_decision_scope="scope-prod-001",
            promotion_valid=True,
            metric_vault_release_status="pending",
            metric_release_token_ref="",
        ),
    )

    encoded = json.dumps(
        store.list_artifact_payloads("validation_reports")
        + store.list_artifact_payloads("gate_assessments"),
        sort_keys=True,
    )
    assert result.report.promotion_valid is False
    assert "trial_lineage_contaminated" in result.report.blocker_codes
    assert "candidate_metrics" not in encoded
    assert store.build_operator_evidence_report()["counts"]["cpcv_trials"] == 0


def test_gate_validation_controller_does_not_write_cpcv_trials_for_gate_2(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )

    controller.generate_gate_report(
        gate_id="2",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 6, 19, tzinfo=UTC),
        universe=("SPY", "QQQ"),
    )

    evidence_report = store.build_operator_evidence_report()

    assert evidence_report["counts"]["cpcv_trials"] == 0


def test_gate_validation_controller_logs_and_continues_when_cpcv_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )

    def _boom(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise RuntimeError("boom")

    import tradingx.controller as controller_module

    monkeypatch.setattr(controller_module, "_run_cpcv_for_candidate", _boom)
    caplog.set_level("ERROR")

    result = controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 6, 19, tzinfo=UTC),
        universe=("SPY", "QQQ"),
    )

    assert result.report.gate_id == "1"
    assert store.build_operator_evidence_report()["counts"]["cpcv_trials"] == 0
    assert any("cpcv_run_failed" in record.message for record in caplog.records)


def test_gate_validation_controller_writes_pbo_report_when_activation_ready(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )
    window_start_utc = datetime(2023, 1, 3, tzinfo=UTC)
    window_end_utc = datetime(2023, 6, 19, tzinfo=UTC)
    current_cohort_window_id = cohort_window_id_for(
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
    )
    _seed_cohort(
        store=store,
        cohort_window_id=current_cohort_window_id,
        strategy_count=50,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        recorded_at_utc=datetime.now(UTC) - timedelta(days=5),
    )
    _seed_cohort(
        store=store,
        cohort_window_id="cohort-mature",
        strategy_count=1,
        window_start_utc=datetime(2022, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2022, 6, 20, tzinfo=UTC),
        recorded_at_utc=datetime.now(UTC) - timedelta(days=200),
    )

    def _fake_compute_pbo(**kwargs):  # type: ignore[no-untyped-def]
        records = kwargs["cpcv_records"]
        assert len(records) >= 2250
        return PBOReport(
            report_id="pbo-gate1-run-1",
            evaluation_id="gate1-run-1",
            cohort_window_id=current_cohort_window_id,
            cohort_size=52,
            n_paths=45,
            n_splits_sampled=10_000,
            pbo_value=Decimal("0.18"),
            logit_distribution_percentiles=((Decimal("50"), Decimal("0.0")),),
            cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
            metric_name="lo_adjusted_sharpe",
            random_seed=2026,
            generated_at_utc=datetime.now(UTC),
        )

    monkeypatch.setattr(controller_module, "compute_pbo", _fake_compute_pbo)

    controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        universe=("SPY", "QQQ"),
    )

    evidence_report = store.build_operator_evidence_report()
    assert evidence_report["counts"]["pbo_reports"] == 1


def test_gate_validation_controller_keeps_pbo_pending_without_mature_cohort(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )
    window_start_utc = datetime(2023, 1, 3, tzinfo=UTC)
    window_end_utc = datetime(2023, 6, 19, tzinfo=UTC)
    current_cohort_window_id = cohort_window_id_for(
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
    )
    _seed_cohort(
        store=store,
        cohort_window_id=current_cohort_window_id,
        strategy_count=50,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        recorded_at_utc=datetime.now(UTC) - timedelta(days=5),
    )

    def _boom(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise AssertionError("compute_pbo should not be called")

    monkeypatch.setattr(controller_module, "compute_pbo", _boom)
    caplog.set_level("INFO")

    controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        universe=("SPY", "QQQ"),
    )

    assert store.build_operator_evidence_report()["counts"]["pbo_reports"] == 0
    assert any("pbo_cohort_insufficient" in record.message for record in caplog.records)


def test_gate_validation_controller_keeps_pbo_pending_when_current_cohort_too_small(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )
    window_start_utc = datetime(2023, 1, 3, tzinfo=UTC)
    window_end_utc = datetime(2023, 6, 19, tzinfo=UTC)
    current_cohort_window_id = cohort_window_id_for(
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
    )
    _seed_cohort(
        store=store,
        cohort_window_id="cohort-mature",
        strategy_count=1,
        window_start_utc=datetime(2022, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2022, 6, 20, tzinfo=UTC),
        recorded_at_utc=datetime.now(UTC) - timedelta(days=200),
    )
    _seed_cohort(
        store=store,
        cohort_window_id=current_cohort_window_id,
        strategy_count=10,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        recorded_at_utc=datetime.now(UTC) - timedelta(days=5),
    )

    def _boom(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise AssertionError("compute_pbo should not be called")

    monkeypatch.setattr(controller_module, "compute_pbo", _boom)
    caplog.set_level("INFO")

    controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        universe=("SPY", "QQQ"),
    )

    assert store.build_operator_evidence_report()["counts"]["pbo_reports"] == 0
    assert any(
        "current_cohort_too_small" in record.message for record in caplog.records
    )


def test_gate_validation_controller_raises_on_mixed_cohort_integrity_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )
    window_start_utc = datetime(2023, 1, 3, tzinfo=UTC)
    window_end_utc = datetime(2023, 6, 19, tzinfo=UTC)
    current_cohort_window_id = cohort_window_id_for(
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
    )
    _seed_cohort(
        store=store,
        cohort_window_id=current_cohort_window_id,
        strategy_count=50,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        recorded_at_utc=datetime.now(UTC) - timedelta(days=5),
    )
    _seed_cohort(
        store=store,
        cohort_window_id="cohort-mature",
        strategy_count=1,
        window_start_utc=datetime(2022, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2022, 6, 20, tzinfo=UTC),
        recorded_at_utc=datetime.now(UTC) - timedelta(days=200),
    )

    def _raise_mixed(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise MixedCohortWindowError("broken cohort")

    monkeypatch.setattr(controller_module, "compute_pbo", _raise_mixed)

    with pytest.raises(MixedCohortWindowError):
        controller.generate_gate_report(
            gate_id="1",
            benchmark_stack_payload=_benchmark_stack_payload(periods=200),
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            universe=("SPY", "QQQ"),
        )

    assert store.build_operator_evidence_report()["counts"]["pbo_reports"] == 0


def test_gate_validation_controller_logs_and_skips_when_compute_pbo_is_insufficient(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )
    window_start_utc = datetime(2023, 1, 3, tzinfo=UTC)
    window_end_utc = datetime(2023, 6, 19, tzinfo=UTC)
    current_cohort_window_id = cohort_window_id_for(
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
    )
    _seed_cohort(
        store=store,
        cohort_window_id=current_cohort_window_id,
        strategy_count=50,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        recorded_at_utc=datetime.now(UTC) - timedelta(days=5),
    )
    _seed_cohort(
        store=store,
        cohort_window_id="cohort-mature",
        strategy_count=1,
        window_start_utc=datetime(2022, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2022, 6, 20, tzinfo=UTC),
        recorded_at_utc=datetime.now(UTC) - timedelta(days=200),
    )

    def _raise_insufficient(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise InsufficientCPCVCohortError("too small")

    monkeypatch.setattr(controller_module, "compute_pbo", _raise_insufficient)
    caplog.set_level("INFO")

    controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        universe=("SPY", "QQQ"),
    )

    assert store.build_operator_evidence_report()["counts"]["pbo_reports"] == 0
    assert any(
        "compute_pbo_insufficient" in record.message for record in caplog.records
    )
