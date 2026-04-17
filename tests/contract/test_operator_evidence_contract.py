from __future__ import annotations

from datetime import UTC, datetime

from tradingx.alerts import (
    MemoryAlertTransport,
    OperatorAlertDispatcher,
    build_risk_control_alert,
)
from tradingx.types import RiskControlEvent


def test_operator_alerts_preserve_required_envelope_fields() -> None:
    dispatcher = OperatorAlertDispatcher(
        transports=(MemoryAlertTransport(target_name="telegram"),)
    )
    alert = dispatcher.dispatch(
        build_risk_control_alert(
            RiskControlEvent(
                event_id="risk-1",
                intent_id="intent-1",
                severity="critical",
                control_type="stale_broker_state",
                blocked=True,
                recorded_at_utc=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
                operator_visible=True,
            ),
            evidence_refs=(
                "artifacts/risk_events/risk-1.json",
                "artifacts/reconciliation/reconcile-intent-1.json",
            ),
        )
    )

    assert alert.alert_id == "alert-risk-1"
    assert alert.severity == "critical"
    assert alert.category == "risk"
    assert alert.evidence_refs == (
        "artifacts/risk_events/risk-1.json",
        "artifacts/reconciliation/reconcile-intent-1.json",
    )
    assert alert.delivery_targets == ("telegram",)
