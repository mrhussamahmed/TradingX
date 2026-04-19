from __future__ import annotations

import importlib
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingx.alerts import (
    MemoryAlertTransport,
    OperatorAlertDispatcher,
    SmtpAlertTransport,
    TelegramAlertTransport,
    build_alert_dispatcher,
    build_gate_decision_alert,
    build_live_disable_alert,
    build_risk_control_alert,
)
from tradingx.config import TradingConfig
from tradingx.types import (
    GateDecisionBrief,
    GateDecisionCandidateSummary,
    RiskControlEvent,
)


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


def test_build_gate_decision_alert_matches_gate_contract() -> None:
    alert = build_gate_decision_alert(
        GateDecisionBrief(
            gate_id="1",
            status="pending",
            decision_summary=(
                "Gate 1 is pending because out-of-sample evidence " "is incomplete."
            ),
            required_operator_action=(
                "Do not advance; collect the missing evidence " "and rerun Gate 1."
            ),
            generated_at_utc=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
            evidence_refs=(
                "validation_reports/gate-1-20260417T180000Z.json",
                "evaluation_evidence/evaluation-1.json",
            ),
            candidate_summaries=(
                GateDecisionCandidateSummary(
                    candidate_id="trend-following-v1",
                    status="pending",
                    failed_criteria=("out_of_sample_profile",),
                    summary="Needs more history.",
                ),
            ),
            latest_open_positions=("SPY",),
            latest_cash=Decimal("10025.00"),
            latest_equity=Decimal("10030.00"),
            blocked_trade_count=2,
            reconciliation_failure_count=1,
            latest_alert_summary="stale_data blocked trade intent intent-1",
        )
    )

    assert alert.category == "gate"
    assert alert.severity == "critical"
    assert "gate 1 pending" in alert.summary.lower()
    assert alert.evidence_refs == (
        "validation_reports/gate-1-20260417T180000Z.json",
        "evaluation_evidence/evaluation-1.json",
    )


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


def test_telegram_alert_transport_posts_rendered_alert_message() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    def fake_opener(request):
        requests.append(
            (
                request.full_url,
                json.loads(request.data.decode("utf-8")),
            )
        )

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        return Response()

    transport = TelegramAlertTransport(
        bot_token="bot-token",
        chat_id="chat-id",
        opener=fake_opener,
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

    transport.send(alert)

    assert requests == [
        (
            "https://api.telegram.org/botbot-token/sendMessage",
            {
                "chat_id": "chat-id",
                "text": (
                    "[WARNING] risk: liquidity_filter blocked trade intent intent-1\n"
                    "Evidence:\nartifacts/risk_events/risk-1.json"
                ),
            },
        )
    ]


def test_smtp_alert_transport_sends_email_message() -> None:
    events: list[tuple[str, object]] = []

    class FakeSmtpClient:
        def starttls(self) -> None:
            events.append(("starttls", None))

        def login(self, username: str, password: str) -> None:
            events.append(("login", (username, password)))

        def send_message(self, message) -> None:
            events.append(("subject", message["Subject"]))
            events.append(("to", message["To"]))
            events.append(("body", message.get_content().strip()))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_factory(host: str, port: int):
        events.append(("connect", (host, port)))
        return FakeSmtpClient()

    transport = SmtpAlertTransport(
        host="smtp.example.com",
        port=587,
        username="mailer",
        password="secret",
        from_email="bot@example.com",
        to_email="ops@example.com",
        smtp_factory=fake_factory,
    )
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

    transport.send(alert)

    assert events[0] == ("connect", ("smtp.example.com", 587))
    assert ("starttls", None) in events
    assert ("login", ("mailer", "secret")) in events
    assert ("to", "ops@example.com") in events


def test_build_alert_dispatcher_uses_configured_real_transports() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
            "TRADINGX_TELEGRAM_BOT_TOKEN": "bot-token",
            "TRADINGX_TELEGRAM_CHAT_ID": "chat-id",
            "TRADINGX_SMTP_HOST": "smtp.example.com",
            "TRADINGX_SMTP_PORT": "587",
            "TRADINGX_SMTP_USERNAME": "mailer",
            "TRADINGX_SMTP_PASSWORD": "secret",
            "TRADINGX_SMTP_FROM_EMAIL": "bot@example.com",
            "TRADINGX_SMTP_TO_EMAIL": "ops@example.com",
        }
    )

    dispatcher = build_alert_dispatcher(
        config,
        transports=(
            MemoryAlertTransport(target_name="telegram"),
            MemoryAlertTransport(target_name="smtp"),
        ),
    )

    assert dispatcher is not None
    delivered = dispatcher.dispatch(
        build_risk_control_alert(
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
    )

    assert delivered.delivery_targets == ("telegram", "smtp")


def test_operator_alert_dispatcher_logs_transport_failures(caplog) -> None:
    class FailingTransport:
        target_name = "smtp"

        def send(self, alert) -> None:
            del alert
            raise RuntimeError("smtp offline")

    dispatcher = OperatorAlertDispatcher(
        transports=(FailingTransport(), MemoryAlertTransport(target_name="telegram"))
    )
    alert = build_risk_control_alert(
        RiskControlEvent(
            event_id="risk-2",
            intent_id="intent-2",
            severity="warning",
            control_type="stale_market_data",
            blocked=True,
            recorded_at_utc=datetime(2026, 4, 17, 18, 5, tzinfo=UTC),
            operator_visible=True,
        ),
        evidence_refs=("artifacts/risk_events/risk-2.json",),
    )

    with caplog.at_level(logging.ERROR):
        delivered = dispatcher.dispatch(alert)

    assert delivered.delivery_targets == ("telegram",)
    assert "smtp offline" in caplog.text


def test_operator_alert_dispatcher_raises_when_critical_alert_has_no_delivery() -> None:
    class FailingTransport:
        target_name = "smtp"

        def send(self, alert) -> None:
            del alert
            raise RuntimeError("smtp offline")

    dispatcher = OperatorAlertDispatcher(transports=(FailingTransport(),))
    alert = build_gate_decision_alert(
        GateDecisionBrief(
            gate_id="4",
            status="blocked",
            decision_summary="Gate 4 blocked.",
            required_operator_action="Do not enable live trading.",
            generated_at_utc=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
            evidence_refs=("validation_reports/gate-4.json",),
            candidate_summaries=(),
            latest_open_positions=(),
            latest_cash=Decimal("10025.00"),
            latest_equity=Decimal("10030.00"),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            latest_alert_summary="",
        )
    )

    with pytest.raises(RuntimeError, match="No alert transports delivered"):
        dispatcher.dispatch(alert)


def test_smtp_alert_transport_requires_starttls_when_enabled() -> None:
    class NoStartTlsClient:
        def login(self, username: str, password: str) -> None:
            del username, password

        def send_message(self, message) -> None:
            del message

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    transport = SmtpAlertTransport(
        host="smtp.example.com",
        port=587,
        username="mailer",
        password="secret",
        from_email="bot@example.com",
        to_email="ops@example.com",
        smtp_factory=lambda host, port: NoStartTlsClient(),
    )
    alert = build_risk_control_alert(
        RiskControlEvent(
            event_id="risk-3",
            intent_id="intent-3",
            severity="warning",
            control_type="liquidity_filter",
            blocked=True,
            recorded_at_utc=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
            operator_visible=True,
        ),
        evidence_refs=(),
    )

    with pytest.raises(AttributeError):
        transport.send(alert)
