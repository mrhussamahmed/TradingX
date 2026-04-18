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
class GateDecisionCandidateSummary:
    candidate_id: str
    status: str
    failed_criteria: tuple[str, ...]
    summary: str


@dataclass(frozen=True)
class GateDecisionBrief:
    gate_id: str
    status: str
    decision_summary: str
    required_operator_action: str
    generated_at_utc: datetime
    evidence_refs: tuple[str, ...]
    candidate_summaries: tuple[GateDecisionCandidateSummary, ...]
    latest_open_positions: tuple[str, ...]
    latest_cash: Decimal | None
    latest_equity: Decimal | None
    blocked_trade_count: int
    reconciliation_failure_count: int
    latest_alert_summary: str


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


@dataclass(frozen=True)
class ExecutionLifecycleRecord:
    execution_id: str
    intent_id: str
    symbol: str
    side: str
    reason_code: str
    reference_price: Decimal
    fill_price: Decimal
    filled_qty: Decimal
    slippage_bps: Decimal
    submitted_at_utc: datetime
    filled_at_utc: datetime
    recovered: bool
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    average_daily_volume_30d: Decimal | None = None


@dataclass(frozen=True)
class ClosedTradeRecord:
    trade_id: str
    symbol: str
    entry_intent_id: str
    exit_intent_id: str
    opened_at_utc: datetime
    closed_at_utc: datetime
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    return_pct: Decimal
    outcome: str
    holding_period_seconds: int


@dataclass(frozen=True)
class RecoveryDrillRecord:
    drill_id: str
    symbol: str
    started_at_utc: datetime
    completed_at_utc: datetime | None
    status: str
    summary: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class AlertDrillRecord:
    drill_id: str
    channel: str
    recorded_at_utc: datetime
    status: str
    summary: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class MarketSessionRecord:
    session_id: str
    session_label: str
    recorded_at_utc: datetime
    service_status: str
    blocked_trade_count: int
    reconciliation_failure_count: int
    open_positions: tuple[str, ...]
    top_incidents: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ReplaySlippageRecord:
    replay_id: str
    execution_id: str
    intent_id: str
    symbol: str
    side: str
    filled_qty: Decimal
    reference_price: Decimal
    paper_fill_price: Decimal
    paper_slippage_bps: Decimal
    simulated_fill_price: Decimal
    simulated_slippage_bps: Decimal
    divergence_ratio: Decimal
    quoted_spread_bps: Decimal
    participation_rate: Decimal
    generated_at_utc: datetime


@dataclass(frozen=True)
class ReplaySlippageSummary:
    summary_id: str
    matched_execution_count: int
    paper_mean_absolute_slippage_bps: Decimal
    replay_mean_absolute_slippage_bps: Decimal
    divergence_ratio: Decimal
    status: str
    details: str
    generated_at_utc: datetime


@dataclass(frozen=True)
class ReplaySlippageGenerationResult:
    summary: ReplaySlippageSummary
    record_paths: tuple[Path, ...]
    summary_path: Path


@dataclass(frozen=True)
class Gate3CriterionSnapshot:
    criterion_id: str
    status: str
    threshold: str
    observed_value: str
    details: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Gate3ReadinessReport:
    report_id: str
    generated_at_utc: datetime
    status: str
    closed_trade_count: int
    calendar_days_observed: int
    criteria: tuple[Gate3CriterionSnapshot, ...]
    summary: str
    required_operator_action: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Gate3PromotionPackage:
    package_id: str
    generated_at_utc: datetime
    status: str
    headline: str
    decision_summary: str
    criteria_statuses: dict[str, str]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class WebServiceState:
    status: str
    active_symbols: tuple[str, ...]
    interval_seconds: int
    cycles_completed: int
    started_at_utc: datetime | None
    last_completed_at_utc: datetime | None
    last_error: str


@dataclass(frozen=True)
class DashboardSnapshot:
    generated_at_utc: datetime
    service_status: WebServiceState
    account_summary: dict[str, str]
    positions: tuple[dict[str, str], ...]
    alerts: tuple[str, ...]
    gate_statuses: dict[str, str]
    recommendations: dict[str, int]
    document_summary: dict[str, str | int]


@dataclass(frozen=True)
class WebActionResult:
    action_id: str
    action_type: str
    status: str
    message: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ConfigProposal:
    proposal_id: str
    target_area: str
    proposed_values: dict[str, object]
    diff_preview: str
    output_path: Path


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    title: str
    path: Path
    preview: str
    kind: str


@dataclass(frozen=True)
class OperatorTimelineEvent:
    event_id: str
    event_type: str
    symbol: str
    severity: str
    headline: str
    details: str
    occurred_at_utc: datetime
    artifact_path: str
    related_ids: tuple[str, ...]


@dataclass(frozen=True)
class IncidentRecord:
    incident_id: str
    title: str
    severity: str
    status: str
    category: str
    summary: str
    first_seen_at_utc: datetime
    latest_seen_at_utc: datetime
    acknowledged_at_utc: datetime | None
    acknowledged_by: str
    related_event_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    suggested_action: str


@dataclass(frozen=True)
class ResearchCandidateSummary:
    candidate_id: str
    family: str
    recommendation: str
    benchmark_metrics: dict[str, ScalarValue]
    candidate_metrics: dict[str, ScalarValue]
    adversarial_checks: tuple[str, ...]
    gate_statuses: dict[str, str]
    summary: str


@dataclass(frozen=True)
class ResearchStudioSnapshot:
    generated_at_utc: datetime
    gate_summaries: tuple[dict[str, str], ...]
    candidate_summaries: tuple[ResearchCandidateSummary, ...]
    decision_summary: str


@dataclass(frozen=True)
class ReplaySession:
    replay_id: str
    focus_type: str
    focus_value: str
    headline: str
    events: tuple[OperatorTimelineEvent, ...]
    summary: str


@dataclass(frozen=True)
class DailySessionDigest:
    digest_id: str
    generated_at_utc: datetime
    session_label: str
    service_status: str
    blocked_trade_count: int
    reconciliation_failure_count: int
    latest_positions: tuple[str, ...]
    top_incidents: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ExplorerRecord:
    record_id: str
    category: str
    title: str
    preview: str
    path: str
    symbol: str
    recorded_at_utc: datetime


@dataclass(frozen=True)
class CommandCenterSnapshot:
    generated_at_utc: datetime
    service_status: WebServiceState
    market_session_label: str
    session_mode: str
    account_summary: dict[str, str]
    equity_curve: tuple[dict[str, str], ...]
    exposure_breakdown: tuple[dict[str, str], ...]
    watchlist: tuple[dict[str, str], ...]
    gate_statuses: dict[str, str]
    recommendations: dict[str, int]
    headline_incidents: tuple[dict[str, str], ...]


__all__ = (
    "AccountSnapshot",
    "BenchmarkCloseSeries",
    "ConfigProposal",
    "DashboardSnapshot",
    "DocumentRecord",
    "ExecutionLifecycleRecord",
    "EvaluationEvidencePack",
    "Gate3CriterionSnapshot",
    "Gate3PromotionPackage",
    "Gate3ReadinessReport",
    "GateAssessment",
    "GateDecisionBrief",
    "GateDecisionCandidateSummary",
    "GateReportResult",
    "LatestQuote",
    "MarketSessionRecord",
    "MarketSnapshot",
    "OperatorAlert",
    "OrderRecord",
    "PortfolioState",
    "PositionSnapshot",
    "ReplaySlippageGenerationResult",
    "ReplaySlippageRecord",
    "ReplaySlippageSummary",
    "ReconciliationSnapshot",
    "RecoveryDrillRecord",
    "RiskControlEvent",
    "RoundTripResult",
    "ScalarValue",
    "AlertDrillRecord",
    "ClosedTradeRecord",
    "ServiceCycleSnapshot",
    "ServiceRunResult",
    "ServiceSymbolResult",
    "StrategyCandidate",
    "TradeIntent",
    "TradingLoopResult",
    "ValidationCandidateResult",
    "ValidationCriterionResult",
    "ValidationReport",
    "WebActionResult",
    "WebServiceState",
)
