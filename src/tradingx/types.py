from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TypeAlias

ScalarValue: TypeAlias = str | int | float | bool | Decimal


@dataclass(frozen=True)
class LatestQuote:
    symbol: str
    bid_price: Decimal
    ask_price: Decimal
    timestamp: datetime


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    last_trade_price: Decimal
    bid_price: Decimal
    ask_price: Decimal
    average_daily_volume_30d: Decimal
    timestamp: datetime


@dataclass(frozen=True)
class OrderRecord:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    status: str
    filled_qty: Decimal
    filled_avg_price: Decimal


@dataclass(frozen=True)
class AccountSnapshot:
    cash: Decimal
    equity: Decimal
    buying_power: Decimal


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    quantity: Decimal
    average_entry_price: Decimal
    market_value: Decimal


@dataclass(frozen=True)
class StrategyCandidate:
    candidate_id: str
    family: str
    benchmark_symbol: str
    universe: tuple[str, ...]
    parameter_set: dict[str, ScalarValue]
    status: str
    evidence_pack_id: str | None = None


@dataclass(frozen=True)
class EvaluationEvidencePack:
    evidence_pack_id: str
    candidate_id: str
    window_start_utc: datetime
    window_end_utc: datetime
    benchmark_metrics: dict[str, ScalarValue]
    candidate_metrics: dict[str, ScalarValue]
    adversarial_checks: tuple[str, ...]
    recommendation: str
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class TradeIntent:
    intent_id: str
    candidate_id: str
    symbol: str
    side: str
    quantity: Decimal | None
    reason_code: str
    generated_at_utc: datetime


@dataclass(frozen=True)
class RiskControlEvent:
    event_id: str
    intent_id: str | None
    severity: str
    control_type: str
    blocked: bool
    recorded_at_utc: datetime
    operator_visible: bool


@dataclass(frozen=True)
class PortfolioState:
    as_of_utc: datetime
    cash: Decimal
    equity: Decimal
    buying_power: Decimal
    positions: tuple[PositionSnapshot, ...]
    open_orders: tuple[str, ...]


@dataclass(frozen=True)
class ReconciliationSnapshot:
    reconciliation_id: str
    portfolio_state: PortfolioState
    broker_state_age_seconds: int
    differences: tuple[str, ...]
    resolved: bool


@dataclass(frozen=True)
class OperatorAlert:
    alert_id: str
    severity: str
    category: str
    summary: str
    evidence_refs: tuple[str, ...]
    delivery_targets: tuple[str, ...]
    sent_at_utc: datetime


@dataclass(frozen=True)
class GateAssessment:
    gate_id: str
    status: str
    evidence_refs: tuple[str, ...]
    decision_summary: str
    recorded_at_utc: datetime


@dataclass(frozen=True)
class ValidationCriterionResult:
    criterion_id: str
    passed: bool
    threshold: str
    details: str


@dataclass(frozen=True)
class ValidationCandidateResult:
    candidate_id: str
    gate_id: str
    status: str
    evidence_pack_id: str
    criteria: tuple[ValidationCriterionResult, ...]
    summary: str


@dataclass(frozen=True)
class ValidationReport:
    report_id: str
    gate_id: str
    generated_at_utc: datetime
    status: str
    benchmark_symbol: str
    window_start_utc: datetime
    window_end_utc: datetime
    candidate_results: tuple[ValidationCandidateResult, ...]
    summary: str
    assumptions: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkCloseSeries:
    symbol: str
    closes: tuple[Decimal, ...]
    window_start_utc: datetime | None
    window_end_utc: datetime | None
    generated_at_utc: datetime | None
    feed: str
    adjustment: str
    series_is_adjusted: bool


@dataclass(frozen=True)
class GateReportResult:
    report: ValidationReport
    gate_assessment: GateAssessment
    artifact_paths: tuple[Path, ...]


@dataclass(frozen=True)
class RoundTripResult:
    symbol: str
    quantity: Decimal
    quote: LatestQuote
    initial_account: AccountSnapshot
    final_account: AccountSnapshot
    buy_order: OrderRecord
    sell_order: OrderRecord
    final_position_quantity: Decimal
    cash_delta: Decimal
    log_path: Path


@dataclass(frozen=True)
class TradingLoopResult:
    terminal_state: str
    trade_intent: TradeIntent
    order_record: OrderRecord | None
    risk_event: RiskControlEvent | None
    reconciliation: ReconciliationSnapshot
    artifact_paths: tuple[Path, ...]
    recovered: bool = False


@dataclass(frozen=True)
class ServiceSymbolResult:
    symbol: str
    terminal_state: str
    reason_code: str
    recovered: bool


@dataclass(frozen=True)
class ServiceCycleSnapshot:
    cycle_id: str
    started_at_utc: datetime
    completed_at_utc: datetime
    cycle_status: str
    symbols: tuple[str, ...]
    symbol_results: tuple[ServiceSymbolResult, ...]
    blocked_trade_count: int
    reconciliation_failure_count: int
    open_position_symbols: tuple[str, ...]
    cash: Decimal
    equity: Decimal
    buying_power: Decimal


@dataclass(frozen=True)
class ServiceRunResult:
    cycles_completed: int
    last_cycle: ServiceCycleSnapshot
    artifact_paths: tuple[Path, ...]


__all__ = (
    "AccountSnapshot",
    "BenchmarkCloseSeries",
    "EvaluationEvidencePack",
    "GateAssessment",
    "GateReportResult",
    "LatestQuote",
    "MarketSnapshot",
    "OperatorAlert",
    "OrderRecord",
    "PortfolioState",
    "PositionSnapshot",
    "ReconciliationSnapshot",
    "RiskControlEvent",
    "RoundTripResult",
    "ScalarValue",
    "ServiceCycleSnapshot",
    "ServiceRunResult",
    "ServiceSymbolResult",
    "StrategyCandidate",
    "TradeIntent",
    "TradingLoopResult",
    "ValidationCandidateResult",
    "ValidationCriterionResult",
    "ValidationReport",
)
