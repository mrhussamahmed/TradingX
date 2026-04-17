from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.types import (
    ConfigProposal,
    DashboardSnapshot,
    DocumentRecord,
    GateAssessment,
    GateDecisionBrief,
    GateDecisionCandidateSummary,
    GateReportResult,
    OperatorAlert,
    PortfolioState,
    ReconciliationSnapshot,
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
