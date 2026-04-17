from __future__ import annotations

import importlib
from datetime import UTC, datetime

from tradingx.alerts import (
    MemoryAlertTransport,
    OperatorAlertDispatcher,
    build_live_disable_alert,
    build_risk_control_alert,
)
from tradingx.config import TradingConfig
from tradingx.types import RiskControlEvent


def test_alerts_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.alerts")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_build_risk_control_alert_uses_operator_contract_fields() -> None:
    alert = build_risk_control_alert(
        RiskControlEvent(
            event_id="risk-1",
            intent_id="intent-1",
            severity="critical",
            control_type="kill_switch",
            blocked=True,
            recorded_at_utc=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
            operator_visible=True,
        ),
        evidence_refs=("artifacts/risk_events/risk-1.json",),
    )

    assert alert.category == "risk"
    assert alert.summary == "kill_switch blocked trade intent intent-1"
    assert alert.evidence_refs == ("artifacts/risk_events/risk-1.json",)


def test_live_disable_alert_reports_manual_halt_state() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
            "TRADINGX_MANUAL_KILL_SWITCH": "true",
        }
    )

    alert = build_live_disable_alert(config)

    assert alert.category == "operations"
    assert "manual halt active" in alert.summary.lower()


def test_operator_alert_dispatcher_records_delivery_targets() -> None:
    dispatcher = OperatorAlertDispatcher(
        transports=(MemoryAlertTransport(target_name="telegram"),)
    )
    alert = build_risk_control_alert(
        RiskControlEvent(
            event_id="risk-1",
            intent_id="intent-1",
            severity="warning",
            control_type="liquidity_filter",
            blocked=True,
            recorded_at_utc=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
            operator_visible=True,
        ),
        evidence_refs=("artifacts/risk_events/risk-1.json",),
    )

    delivered = dispatcher.dispatch(alert)

    assert delivered.delivery_targets == ("telegram",)
