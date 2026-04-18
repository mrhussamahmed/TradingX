from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    AlertDrillRecord,
    ClosedTradeRecord,
    EvaluationEvidencePack,
    ExecutionLifecycleRecord,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    GateAssessment,
    MarketAutomationRunRecord,
    OperatorAlert,
    RecoveryDrillRecord,
    ReplaySlippageRecord,
    ReplaySlippageSummary,
    ServiceCycleSnapshot,
    ServiceSymbolResult,
    TradeIntent,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
)


def test_persistence_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.persistence")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_filesystem_artifact_store_exposes_market_day_schedule_writer(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)

    assert hasattr(store, "write_market_day_schedule_record")


def test_filesystem_artifact_store_writes_trade_intent_json(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    intent = TradeIntent(
        intent_id="intent-1",
        candidate_id="trend-following-v1",
        symbol="SPY",
        side="buy",
        quantity=Decimal("1"),
        reason_code="trend_breakout",
        generated_at_utc=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
    )

    path = store.write_trade_intent(intent)

    assert path == tmp_path / "trade_intents" / "intent-1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "SPY"
    assert payload["generated_at_utc"] == "2026-04-17T18:00:00+00:00"


def test_filesystem_artifact_store_separates_alert_and_gate_artifacts(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)

    alert_path = store.write_operator_alert(
        OperatorAlert(
            alert_id="alert-1",
            severity="critical",
            category="risk",
            summary="Blocked trade",
            evidence_refs=("artifacts/trade_intents/intent-1.json",),
            delivery_targets=("telegram",),
            sent_at_utc=timestamp,
        )
    )
    gate_path = store.write_gate_assessment(
        GateAssessment(
            gate_id="0.5",
            status="pass",
            evidence_refs=("artifacts/smoke/spy.json",),
            decision_summary="Walking skeleton passed.",
            recorded_at_utc=timestamp,
        )
    )

    assert alert_path == tmp_path / "operator_alerts" / "alert-1.json"
    assert gate_path == tmp_path / "gate_assessments" / "gate-0.5.json"


def test_filesystem_artifact_store_builds_operator_evidence_report(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    store.write_trade_intent(
        TradeIntent(
            intent_id="intent-1",
            candidate_id="trend-following-v1",
            symbol="SPY",
            side="buy",
            quantity=Decimal("1"),
            reason_code="trend_breakout",
            generated_at_utc=timestamp,
        )
    )
    store.write_operator_alert(
        OperatorAlert(
            alert_id="alert-1",
            severity="warning",
            category="risk",
            summary="Blocked trade",
            evidence_refs=("artifacts/trade_intents/intent-1.json",),
            delivery_targets=("telegram",),
            sent_at_utc=timestamp,
        )
    )

    report = store.build_operator_evidence_report()

    assert report["counts"]["trade_intents"] == 1
    assert report["counts"]["operator_alerts"] == 1
    assert "alert-1.json" in report["latest_artifacts"]["operator_alerts"]


def test_filesystem_artifact_store_writes_service_cycle_and_builds_richer_summary(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            cycle_status="executed",
            symbols=("SPY", "QQQ"),
            symbol_results=(
                ServiceSymbolResult(
                    symbol="SPY",
                    terminal_state="reconciled_trade",
                    reason_code="baseline_long_entry",
                    recovered=False,
                ),
                ServiceSymbolResult(
                    symbol="QQQ",
                    terminal_state="blocked_trade",
                    reason_code="liquidity_filter",
                    recovered=False,
                ),
            ),
            blocked_trade_count=1,
            reconciliation_failure_count=0,
            open_position_symbols=("SPY",),
            cash=Decimal("10025.00"),
            equity=Decimal("10030.00"),
            buying_power=Decimal("20030.00"),
        )
    )
    store.write_evaluation_evidence(
        EvaluationEvidencePack(
            evidence_pack_id="evaluation-1",
            candidate_id="trend-following-v1",
            window_start_utc=timestamp,
            window_end_utc=timestamp,
            benchmark_metrics={"sharpe": Decimal("1.0")},
            candidate_metrics={"sharpe": Decimal("1.2")},
            adversarial_checks=("adv_check",),
            recommendation="keep",
            assumptions=(),
        )
    )

    report = store.build_operator_evidence_report()

    assert report["counts"]["service_cycles"] == 1
    assert report["summary"]["blocked_trade_count"] == 1
    assert report["summary"]["latest_open_positions"] == ["SPY"]
    assert report["summary"]["latest_cash"] == "10025.00"
    assert report["summary"]["latest_equity"] == "10030.00"
    assert report["summary"]["evaluation_recommendations"] == {"keep": 1}


def test_filesystem_artifact_store_writes_validation_report_and_summarizes_gate_status(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)

    report_path = store.write_validation_report(
        ValidationReport(
            report_id="gate-1-20260417",
            gate_id="1",
            generated_at_utc=timestamp,
            status="pass",
            benchmark_symbol="SPY",
            window_start_utc=timestamp,
            window_end_utc=timestamp,
            candidate_results=(
                ValidationCandidateResult(
                    candidate_id="trend-following-v1",
                    gate_id="1",
                    status="pass",
                    evidence_pack_id="evaluation-1",
                    criteria=(
                        ValidationCriterionResult(
                            criterion_id="benchmark_edge",
                            passed=True,
                            threshold="Sharpe >= 1.0 and >= 1.3x SPY Sharpe",
                            details="Sharpe edge satisfied.",
                        ),
                    ),
                    summary="All Gate 1 criteria satisfied.",
                ),
            ),
            summary="Gate 1 passed for trend-following-v1.",
            assumptions=("benchmark series declared dividend-adjusted",),
            evidence_refs=("evaluation_evidence/evaluation-1.json",),
        )
    )
    store.write_gate_assessment(
        GateAssessment(
            gate_id="1",
            status="pass",
            evidence_refs=(str(report_path),),
            decision_summary="Gate 1 passed for one mandatory candidate.",
            recorded_at_utc=timestamp,
        )
    )

    report = store.build_operator_evidence_report()

    assert report_path == tmp_path / "validation_reports" / "gate-1-20260417.json"
    assert report["counts"]["validation_reports"] == 1
    assert report["summary"]["latest_gate_statuses"] == {"1": "pass"}


def test_filesystem_artifact_store_writes_gate3_artifacts_and_summarizes_them(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 18, 8, 0, tzinfo=UTC)

    execution_path = store.write_execution_lifecycle_record(
        ExecutionLifecycleRecord(
            execution_id="execution-1",
            intent_id="intent-1",
            symbol="SPY",
            side="buy",
            reason_code="baseline_long_entry",
            reference_price=Decimal("500.00"),
            fill_price=Decimal("500.25"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("5"),
            submitted_at_utc=timestamp,
            filled_at_utc=timestamp,
            recovered=False,
        )
    )
    closed_trade_path = store.write_closed_trade_record(
        ClosedTradeRecord(
            trade_id="trade-1",
            symbol="SPY",
            entry_intent_id="intent-1",
            exit_intent_id="intent-2",
            opened_at_utc=timestamp,
            closed_at_utc=timestamp,
            quantity=Decimal("1"),
            entry_price=Decimal("500.25"),
            exit_price=Decimal("505.25"),
            gross_pnl=Decimal("5.00"),
            return_pct=Decimal("0.01"),
            outcome="win",
            holding_period_seconds=300,
        )
    )
    recovery_path = store.write_recovery_drill_record(
        RecoveryDrillRecord(
            drill_id="recovery-1",
            symbol="SPY",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            status="completed",
            summary="Recovered reconciliation.",
            evidence_refs=("artifacts/paper_loop/recovery_drills/recovery-1.json",),
        )
    )
    alert_path = store.write_alert_drill_record(
        AlertDrillRecord(
            drill_id="alert-1",
            channel="smtp",
            recorded_at_utc=timestamp,
            status="completed",
            summary="SMTP delivered.",
            evidence_refs=("artifacts/paper_loop/alert_drills/alert-1.json",),
        )
    )
    report_path = store.write_gate3_readiness_report(
        Gate3ReadinessReport(
            report_id="gate3-1",
            generated_at_utc=timestamp,
            status="pending",
            closed_trade_count=1,
            calendar_days_observed=1,
            criteria=(),
            summary="Gate 3 pending.",
            required_operator_action="Collect more paper evidence.",
            evidence_refs=(str(closed_trade_path),),
        )
    )
    package_path = store.write_gate3_promotion_package(
        Gate3PromotionPackage(
            package_id="gate3-package-1",
            generated_at_utc=timestamp,
            status="pending",
            headline="Gate 3 not ready.",
            decision_summary="More evidence required.",
            criteria_statuses={"duration_or_trade_count": "pending"},
            evidence_refs=(str(report_path),),
        )
    )

    report = store.build_operator_evidence_report()

    assert execution_path == tmp_path / "execution_lifecycles" / "execution-1.json"
    assert closed_trade_path == tmp_path / "closed_trades" / "trade-1.json"
    assert recovery_path == tmp_path / "recovery_drills" / "recovery-1.json"
    assert alert_path == tmp_path / "alert_drills" / "alert-1.json"
    assert report_path == tmp_path / "gate3_reports" / "gate3-1.json"
    assert package_path == tmp_path / "gate3_packages" / "gate3-package-1.json"
    assert report["counts"]["execution_lifecycles"] == 1
    assert report["counts"]["closed_trades"] == 1
    assert report["counts"]["recovery_drills"] == 1
    assert report["counts"]["alert_drills"] == 1
    assert report["counts"]["gate3_reports"] == 1
    assert report["counts"]["gate3_packages"] == 1


def test_filesystem_artifact_store_writes_replay_slippage_artifacts(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 18, 8, 30, tzinfo=UTC)

    record_path = store.write_replay_slippage_record(
        ReplaySlippageRecord(
            replay_id="replay-execution-1",
            execution_id="execution-1",
            intent_id="intent-1",
            symbol="SPY",
            side="buy",
            filled_qty=Decimal("1"),
            reference_price=Decimal("500.00"),
            paper_fill_price=Decimal("500.25"),
            paper_slippage_bps=Decimal("5.0"),
            simulated_fill_price=Decimal("500.40"),
            simulated_slippage_bps=Decimal("8.0"),
            divergence_ratio=Decimal("1.6"),
            quoted_spread_bps=Decimal("8.0"),
            participation_rate=Decimal("0.000001"),
            generated_at_utc=timestamp,
        )
    )
    summary_path = store.write_replay_slippage_summary(
        ReplaySlippageSummary(
            summary_id="replay-summary-1",
            matched_execution_count=1,
            paper_mean_absolute_slippage_bps=Decimal("5.0"),
            replay_mean_absolute_slippage_bps=Decimal("8.0"),
            divergence_ratio=Decimal("1.6"),
            status="pass",
            details="Replay divergence is within the bound.",
            generated_at_utc=timestamp,
        )
    )

    report = store.build_operator_evidence_report()

    assert (
        record_path == tmp_path / "replay_slippage_records" / "replay-execution-1.json"
    )
    assert (
        summary_path == tmp_path / "replay_slippage_summaries" / "replay-summary-1.json"
    )
    assert report["counts"]["replay_slippage_records"] == 1
    assert report["counts"]["replay_slippage_summaries"] == 1


def test_filesystem_artifact_store_writes_market_automation_run_artifacts(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 18, 17, 0, tzinfo=UTC)

    run_path = store.write_market_automation_run_record(
        MarketAutomationRunRecord(
            run_id="automation-1",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            trading_day="2026-04-18",
            status="completed",
            heartbeat_count=2,
            preopen_session_id="session-preopen-1",
            heartbeat_session_ids=("session-heartbeat-1", "session-heartbeat-2"),
            close_session_id="session-close-1",
            latest_replay_summary_id="replay-summary-1",
            latest_gate3_report_id="gate3-1",
            latest_gate3_package_id="gate3-package-1",
            summary="Automation completed with fresh evidence.",
            evidence_refs=(
                "artifacts/operator_platform/market_automation_runs/automation-1.json",
            ),
        )
    )

    report = store.build_operator_evidence_report()

    assert run_path == tmp_path / "market_automation_runs" / "automation-1.json"
    assert report["counts"]["market_automation_runs"] == 1
