from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.types import (
    GateAssessment,
    OperatorAlert,
    PortfolioState,
    ReconciliationSnapshot,
    RiskControlEvent,
    StrategyCandidate,
    TradeIntent,
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
