"""Stage 1 Prometheus-backed monitoring helpers."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge


class StageMetrics:
    def __init__(
        self,
        *,
        registry: CollectorRegistry | None = None,
        namespace: str = "tradingx",
    ) -> None:
        self._registry = registry or CollectorRegistry()
        self._trade_terminal_states_total = Counter(
            "trade_terminal_states_total",
            "Number of terminal trade outcomes by state.",
            ("terminal_state",),
            namespace=namespace,
            registry=self._registry,
        )
        self._operator_alerts_total = Counter(
            "operator_alerts_total",
            "Number of operator alerts emitted by severity.",
            ("severity",),
            namespace=namespace,
            registry=self._registry,
        )
        self._reconciliation_age_seconds = Gauge(
            "reconciliation_age_seconds",
            "Age in seconds of the most recent reconciliation snapshot.",
            namespace=namespace,
            registry=self._registry,
        )
        self._evidence_artifacts_total = Counter(
            "evidence_artifacts_total",
            "Number of evidence artifacts written by category.",
            ("category",),
            namespace=namespace,
            registry=self._registry,
        )
        self._live_trading_disabled = Gauge(
            "live_trading_disabled",
            "Whether live trading is currently disabled.",
            namespace=namespace,
            registry=self._registry,
        )
        self._manual_halt_active = Gauge(
            "manual_halt_active",
            "Whether the manual halt is currently active.",
            namespace=namespace,
            registry=self._registry,
        )

    @property
    def registry(self) -> CollectorRegistry:
        return self._registry

    def record_trade_terminal_state(self, terminal_state: str) -> None:
        self._trade_terminal_states_total.labels(terminal_state=terminal_state).inc()

    def record_operator_alert(self, severity: str) -> None:
        self._operator_alerts_total.labels(severity=severity).inc()

    def record_reconciliation_age_seconds(self, age_seconds: float) -> None:
        self._reconciliation_age_seconds.set(age_seconds)

    def record_evidence_artifact(self, category: str) -> None:
        self._evidence_artifacts_total.labels(category=category).inc()

    def record_live_disable_state(self, disabled: bool) -> None:
        self._live_trading_disabled.set(1 if disabled else 0)

    def record_manual_halt_state(self, active: bool) -> None:
        self._manual_halt_active.set(1 if active else 0)


__all__ = ("StageMetrics",)
