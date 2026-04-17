from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime

from tradingx.alerts import (
    MemoryAlertTransport,
    OperatorAlertDispatcher,
    SmtpAlertTransport,
    TelegramAlertTransport,
    build_alert_dispatcher,
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
