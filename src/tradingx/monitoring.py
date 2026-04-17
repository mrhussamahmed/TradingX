"""Stage 1 Prometheus-backed monitoring helpers."""

from __future__ import annotations

from decimal import Decimal

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
        self._service_cycles_total = Counter(
            "service_cycles_total",
            "Number of paper-service cycles by status.",
            ("cycle_status",),
            namespace=namespace,
            registry=self._registry,
        )
        self._symbols_scanned_total = Gauge(
            "symbols_scanned_total",
            "Number of symbols scanned during the most recent service cycle.",
            namespace=namespace,
            registry=self._registry,
        )
        self._open_positions = Gauge(
            "open_positions",
            "Number of currently open paper positions.",
            namespace=namespace,
            registry=self._registry,
        )
        self._paper_cash = Gauge(
            "paper_cash",
            "Latest paper-account cash balance.",
            namespace=namespace,
            registry=self._registry,
        )
        self._paper_equity = Gauge(
            "paper_equity",
            "Latest paper-account equity balance.",
            namespace=namespace,
            registry=self._registry,
        )
        self._paper_daily_pnl = Gauge(
            "paper_daily_pnl",
            "Observed paper-account daily profit and loss.",
            namespace=namespace,
            registry=self._registry,
        )
        self._blocked_trades_total = Counter(
            "blocked_trades_total",
            "Number of blocked trades by control code.",
            ("control_type",),
            namespace=namespace,
            registry=self._registry,
        )
        self._candidate_recommendations_total = Counter(
            "candidate_recommendations_total",
            "Number of candidate recommendations by outcome.",
            ("recommendation",),
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

    def record_service_cycle(self, cycle_status: str) -> None:
        self._service_cycles_total.labels(cycle_status=cycle_status).inc()

    def record_symbols_scanned(self, count: int) -> None:
        self._symbols_scanned_total.set(count)

    def record_open_positions(self, count: int) -> None:
        self._open_positions.set(count)

    def record_account_snapshot(
        self,
        *,
        cash: Decimal | str,
        equity: Decimal | str,
        daily_pnl: Decimal | str,
    ) -> None:
        self._paper_cash.set(float(Decimal(str(cash))))
        self._paper_equity.set(float(Decimal(str(equity))))
        self._paper_daily_pnl.set(float(Decimal(str(daily_pnl))))

    def record_blocked_trade(self, control_type: str) -> None:
        self._blocked_trades_total.labels(control_type=control_type).inc()

    def record_candidate_recommendation(self, recommendation: str) -> None:
        self._candidate_recommendations_total.labels(
            recommendation=recommendation
        ).inc()


__all__ = ("StageMetrics",)
