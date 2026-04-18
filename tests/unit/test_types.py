from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.types import (
    AlertDrillRecord,
    ClosedTradeRecord,
    CommandCenterSnapshot,
    ConfigProposal,
    DailySessionDigest,
    DashboardSnapshot,
    DocumentRecord,
    ExecutionLifecycleRecord,
    ExplorerRecord,
    Gate3CriterionSnapshot,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    GateAssessment,
    GateDecisionBrief,
    GateDecisionCandidateSummary,
    GateReportResult,
    IncidentRecord,
    MarketSessionRecord,
    OperatorAlert,
    OperatorTimelineEvent,
    PortfolioState,
    ReconciliationSnapshot,
    RecoveryDrillRecord,
    ReplaySession,
    ResearchCandidateSummary,
    ResearchStudioSnapshot,
    RiskControlEvent,
    ServiceCycleSnapshot,
    ServiceRunResult,
    ServiceSymbolResult,
    StrategyCandidate,
    TradeIntent,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
    WebActionResult,
    WebServiceState,
)


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
