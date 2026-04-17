"""Stage 1 operator-alert helpers and transport adapters."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from tradingx.config import TradingConfig
from tradingx.types import EvaluationEvidencePack, OperatorAlert, RiskControlEvent


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


@dataclass
class MemoryAlertTransport:
    target_name: str = "memory"
    sent_alerts: list[OperatorAlert] = field(default_factory=list)

    def send(self, alert: OperatorAlert) -> None:
        self.sent_alerts.append(alert)


class OperatorAlertDispatcher:
    def __init__(
        self,
        *,
        transports: Sequence[MemoryAlertTransport],
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._transports = tuple(transports)
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def dispatch(self, alert: OperatorAlert) -> OperatorAlert:
        delivered = OperatorAlert(
            alert_id=alert.alert_id,
            severity=alert.severity,
            category=alert.category,
            summary=alert.summary,
            evidence_refs=alert.evidence_refs,
            delivery_targets=tuple(
                transport.target_name for transport in self._transports
            ),
            sent_at_utc=self._now_provider(),
        )
        for transport in self._transports:
            transport.send(delivered)
        return delivered


__all__ = (
    "MemoryAlertTransport",
    "OperatorAlertDispatcher",
    "build_evaluation_summary_alert",
    "build_live_disable_alert",
    "build_risk_control_alert",
)
