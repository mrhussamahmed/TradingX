"""Stage 1 operator-alert helpers and transport adapters."""

from __future__ import annotations

import json
import smtplib
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol, Self, cast
from urllib.request import Request, urlopen

from tradingx.config import TradingConfig
from tradingx.types import (
    EvaluationEvidencePack,
    GateDecisionBrief,
    OperatorAlert,
    RiskControlEvent,
)


def build_risk_control_alert(
    event: RiskControlEvent,
    *,
    evidence_refs: tuple[str, ...],
) -> OperatorAlert:
    intent_id = event.intent_id or "unknown"
    return OperatorAlert(
        alert_id=f"alert-{event.event_id}",
        severity=event.severity,
        category="risk",
        summary=f"{event.control_type} blocked trade intent {intent_id}",
        evidence_refs=evidence_refs,
        delivery_targets=(),
        sent_at_utc=event.recorded_at_utc,
    )


def build_evaluation_summary_alert(
    evidence_pack: EvaluationEvidencePack,
    *,
    evidence_refs: tuple[str, ...],
) -> OperatorAlert:
    severity = "info" if evidence_pack.recommendation == "keep" else "warning"
    return OperatorAlert(
        alert_id=f"alert-{evidence_pack.evidence_pack_id}",
        severity=severity,
        category="performance",
        summary=(
            f"{evidence_pack.candidate_id} recommendation: "
            f"{evidence_pack.recommendation}"
        ),
        evidence_refs=evidence_refs,
        delivery_targets=(),
        sent_at_utc=evidence_pack.window_end_utc,
    )


def build_live_disable_alert(config: TradingConfig) -> OperatorAlert:
    report = config.live_disable_report()
    summary = (
        "Live trading disabled; manual halt active."
        if report["manual_kill_switch_active"]
        else "Live trading disabled; paper-only controls remain active."
    )
    return OperatorAlert(
        alert_id="alert-live-disable-status",
        severity="info",
        category="operations",
        summary=summary,
        evidence_refs=(),
        delivery_targets=(),
        sent_at_utc=datetime.now(UTC),
    )


def build_gate_decision_alert(brief: GateDecisionBrief) -> OperatorAlert:
    return OperatorAlert(
        alert_id=f"alert-gate-decision-{brief.gate_id}",
        severity="critical",
        category="gate",
        summary=(
            f"Gate {brief.gate_id} {brief.status}: {brief.required_operator_action}"
        ),
        evidence_refs=brief.evidence_refs,
        delivery_targets=(),
        sent_at_utc=brief.generated_at_utc,
    )


@dataclass
class MemoryAlertTransport:
    target_name: str = "memory"
    sent_alerts: list[OperatorAlert] = field(default_factory=list)

    def send(self, alert: OperatorAlert) -> None:
        self.sent_alerts.append(alert)


class AlertTransport(Protocol):
    target_name: str

    def send(self, alert: OperatorAlert) -> None: ...


class SmtpClientProtocol(Protocol):
    def starttls(self) -> object: ...

    def login(self, username: str, password: str) -> object: ...

    def send_message(self, message: EmailMessage) -> object: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> object: ...


def _render_alert_message(alert: OperatorAlert) -> str:
    message = f"[{alert.severity.upper()}] {alert.category}: {alert.summary}"
    if alert.evidence_refs:
        message = f"{message}\nEvidence:\n" + "\n".join(alert.evidence_refs)
    return message


@dataclass
class TelegramAlertTransport:
    bot_token: str
    chat_id: str
    target_name: str = "telegram"
    opener: Callable[[Request], AbstractContextManager[object]] = urlopen

    def send(self, alert: OperatorAlert) -> None:
        request = Request(
            url=f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data=json.dumps(
                {
                    "chat_id": self.chat_id,
                    "text": _render_alert_message(alert),
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener(request):
            pass


@dataclass
class SmtpAlertTransport:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    to_email: str
    use_starttls: bool = True
    target_name: str = "smtp"
    smtp_factory: Callable[[str, int], SmtpClientProtocol] = cast(
        Callable[[str, int], SmtpClientProtocol],
        smtplib.SMTP,
    )

    def send(self, alert: OperatorAlert) -> None:
        message = EmailMessage()
        message["Subject"] = f"TradingX {alert.severity}: {alert.category}"
        message["From"] = self.from_email
        message["To"] = self.to_email
        message.set_content(_render_alert_message(alert))

        with self.smtp_factory(self.host, self.port) as smtp_client:
            if self.use_starttls and hasattr(smtp_client, "starttls"):
                smtp_client.starttls()
            if self.username and hasattr(smtp_client, "login"):
                smtp_client.login(self.username, self.password)
            smtp_client.send_message(message)


def build_alert_dispatcher(
    config: TradingConfig,
    *,
    transports: Sequence[AlertTransport] | None = None,
) -> OperatorAlertDispatcher | None:
    configured_transports: list[AlertTransport] = list(transports or ())
    if transports is None:
        if config.alerting.telegram_enabled():
            configured_transports.append(
                TelegramAlertTransport(
                    bot_token=config.alerting.telegram_bot_token,
                    chat_id=config.alerting.telegram_chat_id,
                )
            )
        if config.alerting.smtp_enabled():
            configured_transports.append(
                SmtpAlertTransport(
                    host=config.alerting.smtp_host,
                    port=config.alerting.smtp_port,
                    username=config.alerting.smtp_username,
                    password=config.alerting.smtp_password,
                    from_email=config.alerting.smtp_from_email,
                    to_email=config.alerting.smtp_to_email,
                    use_starttls=config.alerting.smtp_use_starttls,
                )
            )
    if not configured_transports:
        return None
    return OperatorAlertDispatcher(transports=tuple(configured_transports))


class OperatorAlertDispatcher:
    def __init__(
        self,
        *,
        transports: Sequence[AlertTransport],
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._transports = tuple(transports)
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def dispatch(self, alert: OperatorAlert) -> OperatorAlert:
        delivery_targets: list[str] = []
        for transport in self._transports:
            try:
                transport.send(alert)
            except Exception:
                continue
            delivery_targets.append(transport.target_name)
        delivered = OperatorAlert(
            alert_id=alert.alert_id,
            severity=alert.severity,
            category=alert.category,
            summary=alert.summary,
            evidence_refs=alert.evidence_refs,
            delivery_targets=tuple(delivery_targets),
            sent_at_utc=self._now_provider(),
        )
        return delivered


__all__ = (
    "AlertTransport",
    "MemoryAlertTransport",
    "OperatorAlertDispatcher",
    "SmtpAlertTransport",
    "TelegramAlertTransport",
    "build_alert_dispatcher",
    "build_evaluation_summary_alert",
    "build_gate_decision_alert",
    "build_live_disable_alert",
    "build_risk_control_alert",
)
