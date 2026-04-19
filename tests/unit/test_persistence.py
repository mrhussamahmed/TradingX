from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.runtime_portfolio import RuntimePortfolioPlan, RuntimePortfolioTrade
from tradingx.types import (
    AlertDrillRecord,
    ApprovedWeightSnapshot,
    BotRuntimeState,
    ClosedTradeRecord,
    EvaluationEvidencePack,
    ExecutionLifecycleRecord,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    GateAssessment,
    HistoricalWarmupRecord,
    MarketAutomationRunRecord,
    MarketSnapshot,
    OperatorAlert,
    OpportunityScore,
    OpportunitySelectionRecord,
    RecoveryDrillRecord,
    ReplaySlippageRecord,
    ReplaySlippageSummary,
    ServiceCycleSnapshot,
    ServiceSymbolResult,
    StrategyActivationRecord,
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


def test_filesystem_artifact_store_writes_local_trading_appliance_artifacts(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)

    runtime_path = store.write_runtime_host_state(
        BotRuntimeState(
            status="trading_ready",
            status_reason="Runtime boot complete.",
            active_symbols=("SPY", "QQQ"),
            started_at_utc=timestamp,
            updated_at_utc=timestamp,
            last_error="",
            active_strategy_id="baseline-long-only-v1",
            active_model_snapshot_id="snapshot-1",
            latest_selection_id="selection-1",
        )
    )
    warmup_path = store.write_historical_warmup_record(
        HistoricalWarmupRecord(
            warmup_id="warmup-1",
            generated_at_utc=timestamp,
            benchmark_symbol="SPY",
            symbols=("SPY", "QQQ"),
            window_start_utc=timestamp,
            window_end_utc=timestamp,
            required_bar_count=30,
            symbols_ready=("SPY", "QQQ"),
            symbols_blocked={},
            return_summary={"SPY": {"cumulative_return": Decimal("0.02")}},
        )
    )
    activation_path = store.write_strategy_activation_record(
        StrategyActivationRecord(
            activation_id="activation-1",
            strategy_id="baseline-long-only-v1",
            strategy_version="1.0.0",
            approved_symbols=("SPY", "QQQ"),
            deploy_threshold=Decimal("0.5"),
            allow_fallback_weights=True,
            status="approved",
            activated_at_utc=timestamp,
            notes="Baseline activation.",
        )
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-1",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=timestamp,
        minimum_supporting_trades=5,
        weights={"signal": Decimal("1.0")},
    )
    snapshot_path = store.write_model_weight_snapshot(snapshot)
    selection_path = store.write_opportunity_selection_record(
        OpportunitySelectionRecord(
            selection_id="selection-1",
            generated_at_utc=timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="snapshot-1",
            symbols_considered=("SPY", "QQQ"),
            ranked_opportunities=(
                OpportunityScore(
                    symbol="SPY",
                    base_signal=Decimal("1.0"),
                    regime_weight=Decimal("1.0"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.0"),
                    spread_penalty=Decimal("0.1"),
                    volatility_penalty=Decimal("0.1"),
                    portfolio_overlap_penalty=Decimal("0.0"),
                    execution_cost_penalty=Decimal("0.0"),
                    final_score=Decimal("0.8"),
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="SPY",
            decision="selected",
            decision_reason="Top ranked.",
        )
    )

    assert runtime_path == tmp_path / "runtime_host" / "state.json"
    assert warmup_path == tmp_path / "historical_warmups" / "warmup-1.json"
    assert activation_path == tmp_path / "strategy_activations" / "activation-1.json"
    assert snapshot_path == tmp_path / "model_weight_snapshots" / "snapshot-1.json"
    assert selection_path == tmp_path / "opportunity_selections" / "selection-1.json"


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


def test_filesystem_artifact_store_round_trips_runtime_portfolio_plan(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 19, 13, 30, tzinfo=UTC)
    plan = RuntimePortfolioPlan(
        plan_id="runtime-plan-1",
        generated_at_utc=timestamp,
        strategy_id="trend-following-v1",
        universe_snapshot_id="universe-qqq-spy",
        benchmark_symbol="SPY",
        crash_overlay_active=False,
        symbols_considered=("SPY", "QQQ"),
        current_weights={"SPY": Decimal("0.10"), "QQQ": Decimal("0.00")},
        target_weights={"SPY": Decimal("0.05"), "QQQ": Decimal("0.15")},
        trade_intents=(
            TradeIntent(
                intent_id="intent-1",
                candidate_id="trend-following-v1",
                symbol="QQQ",
                side="buy",
                quantity=Decimal("15"),
                reason_code="target_weight_entry",
                generated_at_utc=timestamp,
            ),
        ),
        planned_trades=(
            RuntimePortfolioTrade(
                symbol="QQQ",
                side="buy",
                reason_code="target_weight_entry",
                last_trade_price=Decimal("100"),
                current_weight=Decimal("0"),
                target_weight=Decimal("0.15"),
                current_quantity=Decimal("0"),
                target_quantity=Decimal("15"),
                delta_quantity=Decimal("15"),
                no_trade_band_applied=False,
            ),
        ),
        market_snapshots={
            "QQQ": MarketSnapshot(
                symbol="QQQ",
                last_trade_price=Decimal("100"),
                bid_price=Decimal("99.95"),
                ask_price=Decimal("100.05"),
                average_daily_volume_30d=Decimal("1500000"),
                timestamp=timestamp,
            )
        },
    )

    store.write_runtime_portfolio_plan(plan)
    loaded = store.read_runtime_portfolio_plan("runtime-plan-1")

    assert loaded == plan


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
