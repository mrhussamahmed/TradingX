from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

import tradingx.types as types_module
from tradingx.types import (
    AlertDrillRecord,
    ApprovedWeightSnapshot,
    BotRuntimeState,
    ClosedTradeRecord,
    CommandCenterSnapshot,
    ConfigProposal,
    DailySessionDigest,
    DashboardSnapshot,
    DocumentRecord,
    EvaluationEvidencePack,
    ExecutionLifecycleRecord,
    ExplorerRecord,
    Gate3CriterionSnapshot,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    GateAssessment,
    GateDecisionBrief,
    GateDecisionCandidateSummary,
    GateReportResult,
    HistoricalWarmupRecord,
    IncidentRecord,
    MarketAutomationRunRecord,
    MarketAutomationRunResult,
    MarketSessionRecord,
    OperatorAlert,
    OperatorTimelineEvent,
    OpportunityScore,
    OpportunitySelectionRecord,
    PortfolioState,
    ReconciliationSnapshot,
    RecoveryDrillRecord,
    RegimeSnapshot,
    ReplaySession,
    ResearchCandidateSummary,
    ResearchStudioSnapshot,
    RiskControlEvent,
    ServiceCycleSnapshot,
    ServiceRunResult,
    ServiceSymbolResult,
    SleeveContext,
    SleeveTrade,
    StrategyActivationRecord,
    StrategyCandidate,
    TradeIntent,
    TrialRecord,
    TrialStatistics,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
    WebActionResult,
    WebServiceState,
)


def test_regime_snapshot_is_frozen_dataclass() -> None:
    snapshot = RegimeSnapshot(
        observation_date=date(2026, 4, 21),
        regime="risk_on",
        above_sma_200=True,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("500.12"),
        spy_sma_200=Decimal("480.00"),
        vix_close=Decimal("15.2"),
        yield_curve_spread_bps=Decimal("35"),
    )

    assert dataclasses.is_dataclass(snapshot)
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.regime = "risk_off"  # type: ignore[misc]


def test_strategy_candidate_defaults_to_no_evidence_pack() -> None:
    candidate = StrategyCandidate(
        candidate_id="trend-following-v1",
        family="trend_following",
        benchmark_symbol="SPY",
        universe=("SPY", "QQQ"),
        parameter_set={"lookback_days": 20},
        status="proposed",
    )

    assert candidate.evidence_pack_id is None
    assert candidate.universe == ("SPY", "QQQ")
    assert candidate.sleeve_class_path is None


def test_sleeve_trade_is_frozen_dataclass() -> None:
    trade = SleeveTrade(
        sleeve_id="trend-following-v1",
        symbol="SPY",
        side="buy",
        target_weight_of_sleeve_budget=Decimal("0.6"),
        rationale="tsmom_long_vol_targeted",
        regime="risk_on",
    )

    assert dataclasses.is_dataclass(trade)
    with pytest.raises(dataclasses.FrozenInstanceError):
        trade.side = "sell"  # type: ignore[misc]


def test_sleeve_context_is_frozen_dataclass() -> None:
    regime_snapshot = RegimeSnapshot(
        observation_date=date(2026, 4, 21),
        regime="risk_on",
        above_sma_200=True,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=Decimal("15"),
        yield_curve_spread_bps=Decimal("35"),
    )
    ctx = SleeveContext(
        observation_date=date(2026, 4, 21),
        bars_by_symbol={"SPY": pd.DataFrame()},
        regime=regime_snapshot,
        current_weights_by_symbol={"SPY": Decimal("0.5")},
        sleeve_budget_equity=Decimal("100000"),
    )

    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.sleeve_budget_equity = Decimal("0")  # type: ignore[misc]


def test_sleeve_failure_reason_exposes_expected_constants() -> None:
    assert types_module.SleeveFailureReason.HALT_BY_OPERATOR == "halt_by_operator"
    assert types_module.SleeveFailureReason.DRIFT_ALARM_LIVE == "drift_alarm_live"
    assert (
        types_module.SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M
        == "sleeve_sharpe_below_threshold_6m"
    )
    assert types_module.SleeveFailureReason.REGIME_STRESSED == "regime_stressed"
    assert (
        types_module.SleeveFailureReason.INSUFFICIENT_HISTORY == "insufficient_history"
    )


def test_trial_record_is_frozen_dataclass() -> None:
    record = TrialRecord(
        trial_id="trial-1",
        candidate_id="trend-following-v1",
        family="trend_following",
        window_start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 12, 31, tzinfo=UTC),
        observed_sharpe_net_of_costs=Decimal("1.05"),
        observed_cagr_net_of_costs=Decimal("0.12"),
        observed_max_drawdown=Decimal("0.09"),
        observed_cdar_95=Decimal("0.06"),
        annualized_cost_drag_bps=Decimal("8.4"),
        passed=True,
        recorded_at_utc=datetime(2026, 12, 31, 23, tzinfo=UTC),
        git_sha="abc1234",
        config_fingerprint="deadbeef",
    )

    assert dataclasses.is_dataclass(record)

    with pytest.raises(dataclasses.FrozenInstanceError):
        record.passed = False  # type: ignore[misc]


def test_trial_statistics_shape() -> None:
    stats = TrialStatistics(
        n_trials=5,
        trial_sharpe_mean=0.8,
        trial_sharpe_variance=0.04,
    )

    assert stats.n_trials == 5
    assert stats.trial_sharpe_mean == 0.8
    assert stats.trial_sharpe_variance == 0.04


def test_evaluation_evidence_pack_has_dsr_and_north_star_fields() -> None:
    field_names = {field.name for field in dataclasses.fields(EvaluationEvidencePack)}

    assert "deflated_sharpe_ratio" in field_names
    assert "north_star_sharpe_met" in field_names
    assert "annualized_cost_drag_bps" in field_names
    assert "marginal_sharpe_delta" in field_names
    assert "marginal_calmar_delta" in field_names
    assert "marginal_cdar_delta" in field_names


def test_evaluation_evidence_pack_accepts_marginal_deltas() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    pack = EvaluationEvidencePack(
        evidence_pack_id="pack-1",
        candidate_id="c-1",
        window_start_utc=now,
        window_end_utc=now,
        benchmark_metrics={},
        candidate_metrics={},
        adversarial_checks=(),
        recommendation="",
        assumptions=(),
        marginal_sharpe_delta=Decimal("0.05"),
        marginal_calmar_delta=Decimal("0.03"),
        marginal_cdar_delta=Decimal("-0.01"),
    )

    assert pack.marginal_sharpe_delta == Decimal("0.05")
    assert pack.marginal_calmar_delta == Decimal("0.03")
    assert pack.marginal_cdar_delta == Decimal("-0.01")


def test_evaluation_evidence_pack_marginal_deltas_default_to_none() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    pack = EvaluationEvidencePack(
        evidence_pack_id="pack-1",
        candidate_id="c-1",
        window_start_utc=now,
        window_end_utc=now,
        benchmark_metrics={},
        candidate_metrics={},
        adversarial_checks=(),
        recommendation="",
        assumptions=(),
    )

    assert pack.marginal_sharpe_delta is None
    assert pack.marginal_calmar_delta is None
    assert pack.marginal_cdar_delta is None


def test_validation_candidate_result_accepts_marginal_deltas() -> None:
    result = ValidationCandidateResult(
        candidate_id="c-1",
        gate_id="1",
        status="pass",
        evidence_pack_id="pack-1",
        criteria=(),
        summary="",
        marginal_sharpe_delta=Decimal("0.05"),
        marginal_calmar_delta=Decimal("0.03"),
        marginal_cdar_delta=Decimal("-0.01"),
    )

    assert result.marginal_sharpe_delta == Decimal("0.05")
    assert result.marginal_calmar_delta == Decimal("0.03")
    assert result.marginal_cdar_delta == Decimal("-0.01")


def test_validation_candidate_result_marginal_deltas_default_to_none() -> None:
    result = ValidationCandidateResult(
        candidate_id="c-1",
        gate_id="1",
        status="pass",
        evidence_pack_id="pack-1",
        criteria=(),
        summary="",
    )

    assert result.marginal_sharpe_delta is None
    assert result.marginal_calmar_delta is None
    assert result.marginal_cdar_delta is None


def test_trade_intent_and_risk_control_event_capture_stage_one_fields() -> None:
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    intent = TradeIntent(
        intent_id="intent-1",
        candidate_id="trend-following-v1",
        symbol="SPY",
        side="buy",
        quantity=Decimal("1"),
        reason_code="trend_breakout",
        generated_at_utc=timestamp,
    )
    event = RiskControlEvent(
        event_id="event-1",
        intent_id=intent.intent_id,
        severity="warning",
        control_type="stale_data",
        blocked=True,
        recorded_at_utc=timestamp,
        operator_visible=True,
    )

    assert intent.quantity == Decimal("1")
    assert event.blocked is True
    assert event.operator_visible is True


def test_reconciliation_snapshot_and_operator_alert_hold_evidence_refs() -> None:
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    snapshot = ReconciliationSnapshot(
        reconciliation_id="recon-1",
        portfolio_state=PortfolioState(
            as_of_utc=timestamp,
            cash=Decimal("100000"),
            equity=Decimal("100100"),
            buying_power=Decimal("200000"),
            positions=(),
            open_orders=(),
        ),
        broker_state_age_seconds=30,
        differences=(),
        resolved=True,
    )
    alert = OperatorAlert(
        alert_id="alert-1",
        severity="critical",
        category="risk",
        summary="Stale state blocked a trade",
        evidence_refs=("artifacts/reconciliation/recon-1.json",),
        delivery_targets=("telegram", "smtp"),
        sent_at_utc=timestamp,
    )
    gate = GateAssessment(
        gate_id="0.5",
        status="pass",
        evidence_refs=("artifacts/smoke/spy.json",),
        decision_summary="Walking skeleton passed.",
        recorded_at_utc=timestamp,
    )

    assert snapshot.resolved is True
    assert alert.delivery_targets == ("telegram", "smtp")
    assert gate.evidence_refs == ("artifacts/smoke/spy.json",)


def test_service_cycle_and_run_result_capture_runtime_summary_fields() -> None:
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    cycle = ServiceCycleSnapshot(
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
        ),
        blocked_trade_count=0,
        reconciliation_failure_count=0,
        open_position_symbols=("SPY",),
        cash=Decimal("10000"),
        equity=Decimal("10010"),
        buying_power=Decimal("20010"),
    )
    result = ServiceRunResult(
        cycles_completed=1,
        last_cycle=cycle,
        artifact_paths=(Path("artifacts/service_cycles/cycle-1.json"),),
    )

    assert cycle.open_position_symbols == ("SPY",)
    assert result.cycles_completed == 1


def test_validation_report_and_gate_report_result_capture_gate_evidence() -> None:
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    report = ValidationReport(
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
                summary="All criteria satisfied.",
            ),
        ),
        summary="Gate 1 passed.",
        assumptions=("benchmark series declared dividend-adjusted",),
        evidence_refs=("artifacts/validation_reports/gate-1-20260417.json",),
    )
    gate_result = GateReportResult(
        report=report,
        gate_assessment=GateAssessment(
            gate_id="1",
            status="pass",
            evidence_refs=("artifacts/validation_reports/gate-1-20260417.json",),
            decision_summary="Gate 1 passed.",
            recorded_at_utc=timestamp,
        ),
        artifact_paths=(Path("artifacts/validation_reports/gate-1-20260417.json"),),
    )

    assert report.candidate_results[0].criteria[0].passed is True
    assert gate_result.gate_assessment.status == "pass"


def test_gate_decision_brief_captures_operator_ready_summary() -> None:
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    brief = GateDecisionBrief(
        gate_id="2",
        status="fail",
        decision_summary="Gate 2 failed under cost stress.",
        required_operator_action="Do not advance; address failed robustness criteria.",
        generated_at_utc=timestamp,
        evidence_refs=("validation_reports/gate-2-20260417.json",),
        candidate_summaries=(
            GateDecisionCandidateSummary(
                candidate_id="trend-following-v1",
                status="fail",
                failed_criteria=("cost_stress",),
                summary="2x cost stress made the strategy unprofitable.",
            ),
        ),
        latest_open_positions=("SPY",),
        latest_cash=Decimal("10000"),
        latest_equity=Decimal("9980"),
        blocked_trade_count=3,
        reconciliation_failure_count=1,
        latest_alert_summary="kill_switch blocked trade intent intent-1",
    )

    assert brief.candidate_summaries[0].failed_criteria == ("cost_stress",)
    assert brief.latest_open_positions == ("SPY",)
    assert brief.blocked_trade_count == 3


def test_web_types_capture_dashboard_documents_and_actions() -> None:
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    service_state = WebServiceState(
        status="running",
        active_symbols=("SPY", "QQQ"),
        interval_seconds=300,
        cycles_completed=4,
        started_at_utc=timestamp,
        last_completed_at_utc=timestamp,
        last_error="",
    )
    snapshot = DashboardSnapshot(
        generated_at_utc=timestamp,
        service_status=service_state,
        account_summary={
            "cash": "10025.00",
            "equity": "10030.00",
            "buying_power": "20030.00",
            "daily_pnl": "5.00",
        },
        positions=({"symbol": "SPY", "quantity": "1", "market_value": "101.00"},),
        alerts=("stale broker state blocked a trade",),
        gate_statuses={"1": "pass", "2": "pending"},
        recommendations={"promote_candidate": 1},
        document_summary={"session_count": 2, "latest_state": "Gate 3 pending."},
    )
    action = WebActionResult(
        action_id="action-1",
        action_type="paper_service_start",
        status="accepted",
        message="Paper service started locally.",
        evidence_refs=("artifacts/paper_loop/service_cycles/cycle-1.json",),
    )
    proposal = ConfigProposal(
        proposal_id="proposal-1",
        target_area="symbols",
        proposed_values={"TRADINGX_SYMBOL_UNIVERSE": ["SPY", "QQQ"]},
        diff_preview="+ TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ",
        output_path=Path("config/proposals/proposal-1.md"),
    )
    document = DocumentRecord(
        doc_id="SESS-2026-04-17-013",
        title="Session 013 handover",
        path=Path("docs/handover/SESSIONS/SESS-2026-04-17-013.md"),
        preview="Local web app planning approved.",
        kind="handover",
    )

    assert snapshot.service_status.status == "running"
    assert snapshot.positions[0]["symbol"] == "SPY"
    assert action.evidence_refs == ("artifacts/paper_loop/service_cycles/cycle-1.json",)
    assert proposal.output_path.name == "proposal-1.md"
    assert document.kind == "handover"


def test_local_trading_appliance_types_capture_runtime_activation_and_selection() -> (
    None
):
    timestamp = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
    warmup = HistoricalWarmupRecord(
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
    activation = StrategyActivationRecord(
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
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-1",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=timestamp,
        minimum_supporting_trades=5,
        weights={"signal": Decimal("1.0")},
    )
    selection = OpportunitySelectionRecord(
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
    runtime = BotRuntimeState(
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

    assert warmup.symbols_ready == ("SPY", "QQQ")
    assert activation.deploy_threshold == Decimal("0.5")
    assert snapshot.weights["signal"] == Decimal("1.0")
    assert selection.ranked_opportunities[0].symbol == "SPY"
    assert runtime.status == "trading_ready"


def test_operator_platform_types_capture_command_center_and_research_state() -> None:
    timestamp = datetime(2026, 4, 18, 9, 30, tzinfo=UTC)
    command_center = CommandCenterSnapshot(
        generated_at_utc=timestamp,
        service_status=WebServiceState(
            status="running",
            active_symbols=("SPY", "QQQ"),
            interval_seconds=300,
            cycles_completed=8,
            started_at_utc=timestamp,
            last_completed_at_utc=timestamp,
            last_error="",
        ),
        market_session_label="Regular session monitor",
        session_mode="intraday",
        account_summary={
            "cash": "10025.00",
            "equity": "10030.00",
            "buying_power": "20030.00",
            "daily_pnl": "5.00",
        },
        equity_curve=(
            {"label": "09:30", "value": "10000.00"},
            {"label": "10:00", "value": "10030.00"},
        ),
        exposure_breakdown=(
            {"symbol": "SPY", "value": "65"},
            {"symbol": "QQQ", "value": "35"},
        ),
        watchlist=({"symbol": "SPY", "status": "monitor"},),
        gate_statuses={"1": "pass", "2": "pending"},
        recommendations={"promote_candidate": 1},
        headline_incidents=({"incident_id": "incident-1", "severity": "warning"},),
    )
    research = ResearchStudioSnapshot(
        generated_at_utc=timestamp,
        gate_summaries=({"gate_id": "1", "status": "pass"},),
        candidate_summaries=(
            ResearchCandidateSummary(
                candidate_id="trend-following-v1",
                family="trend_following",
                recommendation="promote_candidate",
                benchmark_metrics={"sharpe": "1.0"},
                candidate_metrics={"sharpe": "1.4"},
                adversarial_checks=("fee_stress",),
                gate_statuses={"1": "pass"},
                summary="Candidate beat the benchmark on Sharpe.",
            ),
        ),
        decision_summary="Gate 1 passed for the leading candidate.",
    )

    assert command_center.market_session_label == "Regular session monitor"
    assert command_center.equity_curve[1]["value"] == "10030.00"
    assert research.candidate_summaries[0].candidate_id == "trend-following-v1"
    assert research.gate_summaries[0]["status"] == "pass"


def test_operator_platform_types_capture_incidents_replay_and_digests() -> None:
    timestamp = datetime(2026, 4, 18, 16, 0, tzinfo=UTC)
    event = OperatorTimelineEvent(
        event_id="event-1",
        event_type="operator_alert",
        symbol="SPY",
        severity="critical",
        headline="Kill switch active",
        details="A kill switch blocked a trade during the session.",
        occurred_at_utc=timestamp,
        artifact_path="artifacts/paper_loop/operator_alerts/alert-1.json",
        related_ids=("alert-1",),
    )
    incident = IncidentRecord(
        incident_id="incident-1",
        title="Kill switch active",
        severity="critical",
        status="acknowledged",
        category="risk",
        summary="Trading remained blocked until operator review.",
        first_seen_at_utc=timestamp,
        latest_seen_at_utc=timestamp,
        acknowledged_at_utc=timestamp,
        acknowledged_by="local-operator",
        related_event_ids=("event-1",),
        evidence_refs=("artifacts/paper_loop/operator_alerts/alert-1.json",),
        suggested_action="Review the kill switch cause before the next session.",
    )
    replay = ReplaySession(
        replay_id="replay-1",
        focus_type="symbol",
        focus_value="SPY",
        headline="SPY replay",
        events=(event,),
        summary="The replay captured a blocked trade and alert trail.",
    )
    digest = DailySessionDigest(
        digest_id="digest-1",
        generated_at_utc=timestamp,
        session_label="session_close",
        service_status="stopped",
        blocked_trade_count=1,
        reconciliation_failure_count=0,
        latest_positions=("SPY",),
        top_incidents=("incident-1",),
        recommended_actions=("Review kill switch origin.",),
        evidence_refs=("artifacts/operator_platform/daily_digests/digest-1.json",),
    )
    explorer = ExplorerRecord(
        record_id="record-1",
        category="validation_report",
        title="Gate 1 report",
        preview="Gate 1 passed with benchmark-relative edge.",
        path="artifacts/validation/validation_reports/gate-1.json",
        symbol="SPY",
        recorded_at_utc=timestamp,
    )

    assert incident.acknowledged_by == "local-operator"
    assert replay.events[0].event_type == "operator_alert"
    assert digest.top_incidents == ("incident-1",)
    assert explorer.category == "validation_report"


def test_gate3_types_capture_lifecycle_drills_and_readiness() -> None:
    timestamp = datetime(2026, 4, 18, 8, 0, tzinfo=UTC)
    execution = ExecutionLifecycleRecord(
        execution_id="execution-1",
        intent_id="intent-1",
        symbol="SPY",
        side="buy",
        reason_code="baseline_long_entry",
        reference_price=Decimal("500.00"),
        fill_price=Decimal("500.25"),
        filled_qty=Decimal("1"),
        slippage_bps=Decimal("5.0"),
        submitted_at_utc=timestamp,
        filled_at_utc=timestamp,
        recovered=False,
    )
    trade = ClosedTradeRecord(
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
    recovery = RecoveryDrillRecord(
        drill_id="recovery-1",
        symbol="SPY",
        started_at_utc=timestamp,
        completed_at_utc=timestamp,
        status="completed",
        summary="Recovered a pending reconciliation.",
        evidence_refs=("artifacts/paper_loop/recovery_drills/recovery-1.json",),
    )
    alert = AlertDrillRecord(
        drill_id="alert-1",
        channel="smtp",
        recorded_at_utc=timestamp,
        status="completed",
        summary="SMTP drill delivered successfully.",
        evidence_refs=("artifacts/paper_loop/alert_drills/alert-1.json",),
    )
    session = MarketSessionRecord(
        session_id="session-1",
        session_label="session_preopen",
        recorded_at_utc=timestamp,
        service_status="idle",
        blocked_trade_count=0,
        reconciliation_failure_count=0,
        open_positions=("SPY",),
        top_incidents=("incident-1",),
        recommended_actions=("Continue paper evidence collection.",),
        evidence_refs=("artifacts/operator_platform/market_sessions/session-1.json",),
    )
    report = Gate3ReadinessReport(
        report_id="gate3-1",
        generated_at_utc=timestamp,
        status="pending",
        closed_trade_count=1,
        calendar_days_observed=1,
        criteria=(
            Gate3CriterionSnapshot(
                criterion_id="duration_or_trade_count",
                status="pending",
                threshold="At least 180 calendar days or 100 closed trades",
                observed_value="1 trade / 1 day",
                details="Not enough paper history yet.",
                evidence_refs=("artifacts/paper_loop/closed_trades/trade-1.json",),
            ),
        ),
        summary="Gate 3 evidence is still incomplete.",
        required_operator_action="Continue paper trading and rerun Gate 3.",
        evidence_refs=("artifacts/validation/gate3_reports/gate3-1.json",),
    )
    package = Gate3PromotionPackage(
        package_id="gate3-package-1",
        generated_at_utc=timestamp,
        status="pending",
        headline="Gate 3 is not ready for promotion.",
        decision_summary="More paper evidence is required.",
        criteria_statuses={"duration_or_trade_count": "pending"},
        evidence_refs=("artifacts/validation/gate3_packages/gate3-package-1.json",),
    )

    assert execution.slippage_bps == Decimal("5.0")
    assert trade.outcome == "win"
    assert recovery.status == "completed"
    assert alert.channel == "smtp"
    assert session.session_label == "session_preopen"
    assert report.criteria[0].criterion_id == "duration_or_trade_count"
    assert package.criteria_statuses["duration_or_trade_count"] == "pending"


def test_market_day_automation_types_capture_run_artifacts() -> None:
    timestamp = datetime(2026, 4, 18, 8, 0, tzinfo=UTC)
    run_record = MarketAutomationRunRecord(
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
        summary="Automation completed with refreshed Gate 3 evidence.",
        evidence_refs=(
            "artifacts/operator_platform/market_automation_runs/automation-1.json",
        ),
    )
    run_result = MarketAutomationRunResult(
        run_record=run_record,
        run_record_path=Path(
            "artifacts/operator_platform/market_automation_runs/automation-1.json"
        ),
        session_paths=(
            Path("artifacts/operator_platform/market_sessions/session-preopen-1.json"),
            Path(
                "artifacts/operator_platform/market_sessions/session-heartbeat-1.json"
            ),
            Path(
                "artifacts/operator_platform/market_sessions/session-heartbeat-2.json"
            ),
            Path("artifacts/operator_platform/market_sessions/session-close-1.json"),
        ),
        daily_digest_paths=(
            Path("artifacts/operator_platform/daily_digests/digest-preopen.json"),
            Path("artifacts/operator_platform/daily_digests/digest-heartbeat.json"),
            Path("artifacts/operator_platform/daily_digests/digest-close.json"),
        ),
        replay_summary_path=Path(
            "artifacts/validation/replay_slippage_summaries/replay-summary-1.json"
        ),
        gate3_report_path=Path("artifacts/validation/gate3_reports/gate3-1.json"),
        gate3_package_path=Path(
            "artifacts/validation/gate3_packages/gate3-package-1.json"
        ),
    )

    assert run_record.heartbeat_count == 2
    assert run_record.latest_gate3_package_id == "gate3-package-1"
    assert len(run_result.session_paths) == 4
    assert run_result.gate3_package_path.name == "gate3-package-1.json"


def test_scheduler_types_are_available_for_runtime_and_persistence() -> None:
    assert getattr(types_module, "MarketDayScheduleRecord", None) is not None
    assert getattr(types_module, "MarketDaySchedulerState", None) is not None
