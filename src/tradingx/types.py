from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, TypeAlias

import pandas as pd  # type: ignore[import-untyped]

ScalarValue: TypeAlias = str | int | float | bool | Decimal


def _serialize_dataclass_payload(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize_dataclass_payload(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_serialize_dataclass_payload(item) for item in value]
    if isinstance(value, list):
        return [_serialize_dataclass_payload(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _serialize_dataclass_payload(item) for key, item in value.items()
        }
    return value


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
    sleeve_class_path: str | None = None


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
    annualized_cost_drag_bps: Decimal | None = None
    deflated_sharpe_ratio: Decimal | None = None
    north_star_sharpe_met: bool | None = None
    marginal_sharpe_delta: Decimal | None = None
    marginal_calmar_delta: Decimal | None = None
    marginal_cdar_delta: Decimal | None = None
    pbo_value: Decimal | None = None
    pbo_report_id: str | None = None
    promotion_valid: bool = False
    evidence_class: str = "exploratory"
    blocker_codes: tuple[str, ...] = ()
    metric_visibility_context: dict[str, object] | None = None


@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    candidate_id: str
    family: str
    window_start_utc: datetime
    window_end_utc: datetime
    observed_sharpe_net_of_costs: Decimal
    observed_cagr_net_of_costs: Decimal
    observed_max_drawdown: Decimal
    observed_cdar_95: Decimal
    annualized_cost_drag_bps: Decimal
    passed: bool
    recorded_at_utc: datetime
    git_sha: str
    config_fingerprint: str


@dataclass(frozen=True)
class TrialStatistics:
    n_trials: int
    trial_sharpe_mean: float
    trial_sharpe_variance: float


@dataclass(frozen=True)
class CPCVTrialRecord:
    trial_id: str
    cohort_window_id: str
    candidate_id: str
    config_fingerprint: str
    strategy_config_id: str
    cpcv_path_id: str
    n_groups: int
    test_group_count: int
    embargo_days: int
    label_horizon: int
    window_start_utc: datetime
    window_end_utc: datetime
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    in_sample_sharpe: Decimal
    out_of_sample_sharpe: Decimal
    in_sample_n_trades: int
    out_of_sample_n_trades: int
    git_sha: str
    recorded_at_utc: datetime


@dataclass(frozen=True)
class PBOReport:
    report_id: str
    evaluation_id: str
    cohort_window_id: str
    cohort_size: int
    n_paths: int
    n_splits_sampled: int
    pbo_value: Decimal
    logit_distribution_percentiles: tuple[tuple[Decimal, Decimal], ...]
    cpcv_config_fingerprint: str
    metric_name: str
    random_seed: int
    generated_at_utc: datetime
    full_cpcv_matrix_ref: str = ""


@dataclass(frozen=True)
class CPCVCohortWindowSummary:
    cohort_window_id: str
    cpcv_config_fingerprint: str
    window_start_utc: datetime
    window_end_utc: datetime
    earliest_recorded_at_utc: datetime
    latest_recorded_at_utc: datetime
    record_count: int
    strategy_config_count: int
    path_count: int
    git_shas: frozenset[str]


@dataclass(frozen=True)
class TradeIntent:
    intent_id: str
    candidate_id: str
    symbol: str
    side: str
    quantity: Decimal | None
    reason_code: str
    generated_at_utc: datetime
    sleeve_attributions: tuple[tuple[str, Decimal], ...] = ()


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
    promotion_valid: bool = False
    evidence_class: str = "exploratory"
    blocker_codes: tuple[str, ...] = ()
    experiment_id: str = ""
    run_id: str = ""
    dataset_manifest_id: str = ""


@dataclass(frozen=True)
class ValidationCriterionResult:
    criterion_id: str
    passed: bool
    threshold: str
    details: str
    status: str | None = None


@dataclass(frozen=True)
class ValidationCandidateResult:
    candidate_id: str
    gate_id: str
    status: str
    evidence_pack_id: str
    criteria: tuple[ValidationCriterionResult, ...]
    summary: str
    annualized_cost_drag_bps: Decimal | None = None
    marginal_sharpe_delta: Decimal | None = None
    marginal_calmar_delta: Decimal | None = None
    marginal_cdar_delta: Decimal | None = None


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
    promotion_valid: bool = False
    evidence_class: str = "exploratory"
    blocker_codes: tuple[str, ...] = ()
    experiment_id: str = ""
    run_id: str = ""
    promotion_decision_scope: str = ""
    metric_vault_release_status: str = "not_applicable"
    metric_release_token_ref: str = ""
    dataset_manifest_id: str = ""

    def to_json(self) -> dict[str, object]:
        payload = _serialize_dataclass_payload(self)
        if not isinstance(payload, dict):
            raise TypeError("ValidationReport serialization must produce an object")
        return payload


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
class OperatingConstraintBudget:
    max_drawdown_design: Decimal
    max_drawdown_halt: Decimal
    cdar_threshold: Decimal
    cdar_confidence: Decimal


@dataclass(frozen=True)
class BenchmarkStackPayload:
    hurdle_returns: tuple[Decimal, ...]
    opportunity_cost_returns: tuple[Decimal, ...]
    opportunity_cost_weights: tuple[tuple[str, Decimal], ...]
    operating_constraint: OperatingConstraintBudget


@dataclass(frozen=True)
class RegimeSnapshot:
    observation_date: date
    regime: str
    above_sma_200: bool | None
    vix_elevated: bool | None
    vix_stressed: bool | None
    yield_curve_inverted: bool | None
    spy_close: Decimal
    spy_sma_200: Decimal
    vix_close: Decimal | None
    yield_curve_spread_bps: Decimal | None


class SleeveFailureReason:
    """String constants for sleeve-level failure diagnostics."""

    HALT_BY_OPERATOR: Final[str] = "halt_by_operator"
    DRIFT_ALARM_LIVE: Final[str] = "drift_alarm_live"
    SLEEVE_SHARPE_BELOW_THRESHOLD_6M: Final[str] = "sleeve_sharpe_below_threshold_6m"
    REGIME_STRESSED: Final[str] = "regime_stressed"
    INSUFFICIENT_HISTORY: Final[str] = "insufficient_history"


@dataclass(frozen=True)
class SleeveTrade:
    sleeve_id: str
    symbol: str
    side: str
    target_weight_of_sleeve_budget: Decimal
    rationale: str
    regime: str


@dataclass(frozen=True)
class SleeveContext:
    observation_date: date
    bars_by_symbol: dict[str, pd.DataFrame]
    regime: RegimeSnapshot
    current_weights_by_symbol: dict[str, Decimal]
    sleeve_budget_equity: Decimal


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
    control_type: str | None = None


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
class SleeveTargetWeights:
    sleeve_id: str
    target_weights_by_symbol: tuple[tuple[str, Decimal], ...]


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
    sleeve_attributions: tuple[tuple[str, Decimal], ...] = ()


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
    entry_sleeve_attributions: tuple[tuple[str, Decimal], ...] = ()
    exit_sleeve_attributions: tuple[tuple[str, Decimal], ...] = ()


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
class MarketAutomationRunRecord:
    run_id: str
    started_at_utc: datetime
    completed_at_utc: datetime
    trading_day: str
    status: str
    heartbeat_count: int
    preopen_session_id: str
    heartbeat_session_ids: tuple[str, ...]
    close_session_id: str
    latest_replay_summary_id: str
    latest_gate3_report_id: str
    latest_gate3_package_id: str
    summary: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class MarketDayScheduleRecord:
    schedule_id: str
    trading_day: str
    scheduled_open_at_utc: datetime
    launched_at_utc: datetime
    completed_at_utc: datetime | None
    status: str
    automation_run_id: str
    summary: str
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
    quote_quality_state: str = ""
    cost_evidence_class: str = "legacy_cost_evidence"
    kind: str = "replay_slippage_summary"


@dataclass(frozen=True)
class ReplaySlippageGenerationResult:
    summary: ReplaySlippageSummary
    record_paths: tuple[Path, ...]
    summary_path: Path


@dataclass(frozen=True)
class BootstrapPositionAllocation:
    sleeve_id: str
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    allocation_source: str
    confidence: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ResidualPositionAllocation:
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SleeveBootstrapAllocationRecord:
    bootstrap_id: str
    ledger_genesis_id: str
    bootstrapped_from_activation_id: str
    trading_day: str
    recorded_at_utc: datetime
    position_allocations: tuple[BootstrapPositionAllocation, ...]
    residual_cash_balance: Decimal
    residual_positions: tuple[ResidualPositionAllocation, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class SleeveLedgerPosition:
    sleeve_id: str
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    realized_pnl_cumulative: Decimal


@dataclass(frozen=True)
class SleevePositionLedgerSnapshot:
    snapshot_id: str
    ledger_genesis_id: str
    active_blueprint_activation_id: str
    trading_day: str
    recorded_at_utc: datetime
    sleeve_id: str
    cash_balance: Decimal
    positions: tuple[SleeveLedgerPosition, ...]
    bootstrap_id: str


@dataclass(frozen=True)
class ResidualReserveSnapshot:
    snapshot_id: str
    ledger_genesis_id: str
    active_blueprint_activation_id: str
    trading_day: str
    recorded_at_utc: datetime
    cash_balance: Decimal
    positions: tuple[ResidualPositionAllocation, ...]
    bootstrap_id: str


@dataclass(frozen=True)
class SessionOpenPortfolioStateRecord:
    record_id: str
    trading_day: str
    recorded_at_utc: datetime
    portfolio_state: PortfolioState


@dataclass(frozen=True)
class SleeveAttributionGapRecord:
    gap_id: str
    sleeve_id: str
    trading_day: str
    recorded_at_utc: datetime
    severity: str
    reason: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SleeveDailyAttributionRecord:
    attribution_id: str
    sleeve_id: str
    trading_day: str
    recorded_at_utc: datetime
    starting_equity: Decimal
    ending_equity: Decimal
    daily_return: Decimal
    per_symbol_open_weight: tuple[tuple[str, Decimal], ...]
    per_symbol_close_weight: tuple[tuple[str, Decimal], ...]
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    cash_balance: Decimal | None = None
    calculation_mode: str | None = None
    bootstrap_confidence: str | None = None
    ledger_genesis_id: str | None = None


@dataclass(frozen=True)
class SleeveDecompositionRecord:
    decomposition_id: str
    cycle_id: str
    trading_day: str
    recorded_at_utc: datetime
    blueprint_activation_id: str
    per_sleeve_target_weights: tuple[SleeveTargetWeights, ...]


@dataclass(frozen=True)
class DriftMonitorVerdictRecord:
    verdict_id: str
    monitor_id: str
    sleeve_id: str | None
    severity: str
    metric_value: Decimal | None
    threshold_value: Decimal | None
    details: str
    recorded_at_utc: datetime


@dataclass(frozen=True)
class Gate3CriterionSnapshot:
    criterion_id: str
    status: str
    threshold: str
    observed_value: str
    details: str
    evidence_refs: tuple[str, ...]
    source_evidence_at_utc: datetime | None = None
    required: bool = True


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
    source_evidence_at_utc: datetime | None = None
    oldest_required_source_evidence_at_utc: datetime | None = None
    latest_source_evidence_at_utc: datetime | None = None
    required_criterion_ids: tuple[str, ...] = ()
    missing_source_criterion_ids: tuple[str, ...] = ()


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
class BotRuntimeState:
    status: str
    status_reason: str
    active_symbols: tuple[str, ...]
    started_at_utc: datetime | None
    updated_at_utc: datetime
    last_error: str
    active_strategy_id: str
    active_model_snapshot_id: str
    latest_selection_id: str


@dataclass(frozen=True)
class RuntimeHeartbeatSnapshot:
    heartbeat_state: str
    heartbeat_summary: str
    heartbeat_tone: str
    cadence_seconds: int
    cadence_label: str
    last_evaluation_at_utc: datetime | None
    next_evaluation_at_utc: datetime | None
    last_decision: str
    decision_reason: str
    score_explanation: str
    current_exposure: str
    current_exposure_detail: str
    active_symbol: str
    selected_symbol: str
    decision: str
    runtime_truth: tuple[RuntimeTruthItem, ...] = ()
    symbol_rows: tuple[RuntimeSymbolHeartbeatRow, ...] = ()
    decision_ladder: tuple[RuntimeDecisionLadderRow, ...] = ()
    operator_guidance: RuntimeOperatorGuidance | None = None


@dataclass(frozen=True)
class RuntimeTruthItem:
    label: str
    value: str
    detail: str
    tone: str


@dataclass(frozen=True)
class RuntimeSymbolHeartbeatRow:
    symbol: str
    status: str
    score: str
    threshold_gap: str
    reason: str
    warmup_state: str
    exposure_state: str
    tone: str


@dataclass(frozen=True)
class RuntimeDecisionLadderRow:
    rank: int
    symbol: str
    final_score: str
    threshold: str
    threshold_gap: str
    primary_driver: str
    disposition: str


@dataclass(frozen=True)
class RuntimeOperatorGuidance:
    recommendation: str
    detail: str
    tone: str


@dataclass(frozen=True)
class RuntimeDecisionSignalDetail:
    available: bool
    symbol: str | None
    final_score: Decimal | str | None
    base_signal: Decimal | str | None
    model_weight: Decimal | str | None
    regime_weight: Decimal | str | None
    liquidity_weight: Decimal | str | None


@dataclass(frozen=True)
class RuntimeDecisionRegimeDetail:
    label: str
    source: str
    context_source_at_utc: datetime | None


@dataclass(frozen=True)
class RuntimeDecisionRiskDetail:
    eligible: bool | None
    ineligibility_reason: str
    threshold: Decimal | str | None
    threshold_gap: Decimal | str | None
    portfolio_overlap_penalty: Decimal | str | None


@dataclass(frozen=True)
class RuntimeDecisionExecutionDetail:
    current_exposure: str
    pending_order_count: int
    latest_reject_reason: str
    context_source_at_utc: datetime | None


@dataclass(frozen=True)
class RuntimeDecisionFreshnessDetail:
    decision_source_at_utc: datetime
    runtime_context_source_at_utc: datetime | None
    execution_context_source_at_utc: datetime | None


@dataclass(frozen=True)
class RuntimeDecisionDetail:
    selection_id: str
    decision_source_at_utc: datetime
    decision: str
    decision_reason: str
    mode: str
    selected_symbol: str
    signal: RuntimeDecisionSignalDetail
    regime: RuntimeDecisionRegimeDetail
    risk: RuntimeDecisionRiskDetail
    execution: RuntimeDecisionExecutionDetail
    freshness: RuntimeDecisionFreshnessDetail


@dataclass(frozen=True)
class HistoricalWarmupRecord:
    warmup_id: str
    generated_at_utc: datetime
    benchmark_symbol: str
    symbols: tuple[str, ...]
    window_start_utc: datetime
    window_end_utc: datetime
    required_bar_count: int
    symbols_ready: tuple[str, ...]
    symbols_blocked: dict[str, str]
    return_summary: dict[str, dict[str, Decimal]]


@dataclass(frozen=True)
class StrategyActivationRecord:
    activation_id: str
    strategy_id: str
    strategy_version: str
    approved_symbols: tuple[str, ...]
    deploy_threshold: Decimal
    allow_fallback_weights: bool
    status: str
    activated_at_utc: datetime
    notes: str


@dataclass(frozen=True)
class BlueprintSleeveBinding:
    sleeve_id: str
    strategy_id: str
    captured_snapshot_id: str


@dataclass(frozen=True)
class BlueprintActivationRecord:
    activation_id: str
    blueprint_id: str
    sleeve_activation_bindings: tuple[BlueprintSleeveBinding, ...]
    status: str
    approved_at_utc: datetime
    approved_by: str
    source_blueprint_path: Path
    superseded_at_utc: datetime | None = None
    supersedes_activation_id: str | None = None


@dataclass(frozen=True)
class ApprovedWeightSnapshot:
    # semantics: approved weights are operator-reviewed offline configuration
    # artifacts loaded from committed YAML under config/strategy/weights/.
    # Runtime code must not construct them from observations or learning output.
    snapshot_id: str
    strategy_id: str
    status: str
    generated_at_utc: datetime
    minimum_supporting_trades: int
    weights: dict[str, Decimal]


@dataclass(frozen=True)
class OpportunityScore:
    symbol: str
    base_signal: Decimal
    regime_weight: Decimal
    model_weight: Decimal
    liquidity_weight: Decimal
    spread_penalty: Decimal
    volatility_penalty: Decimal
    portfolio_overlap_penalty: Decimal
    execution_cost_penalty: Decimal
    final_score: Decimal
    eligible: bool
    ineligibility_reason: str


@dataclass(frozen=True)
class OpportunitySelectionRecord:
    selection_id: str
    generated_at_utc: datetime
    strategy_id: str
    model_snapshot_id: str
    symbols_considered: tuple[str, ...]
    ranked_opportunities: tuple[OpportunityScore, ...]
    selected_symbol: str
    decision: str
    decision_reason: str


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
class MarketDaySchedulerState:
    status: str
    poll_interval_seconds: int
    active_symbols: tuple[str, ...]
    next_run_at_utc: datetime | None
    last_started_at_utc: datetime | None
    last_completed_at_utc: datetime | None
    active_trading_day: str
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
    gate_authority_statuses: dict[str, str] = field(default_factory=dict)
    recommendation_authority_statuses: dict[str, str] = field(default_factory=dict)


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
class MarketAutomationRunResult:
    run_record: MarketAutomationRunRecord
    run_record_path: Path
    session_paths: tuple[Path, ...]
    daily_digest_paths: tuple[Path, ...]
    replay_summary_path: Path | None
    gate3_report_path: Path | None
    gate3_package_path: Path | None


@dataclass(frozen=True)
class MarketDaySchedulerRunResult:
    scheduled_days_completed: int
    latest_schedule_record_path: Path | None


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


@dataclass(frozen=True)
class PortfolioSourceNote:
    source_id: str
    label: str
    tone: str
    detail: str


@dataclass(frozen=True)
class PortfolioMetricCard:
    metric_id: str
    label: str
    value: str
    delta: str
    health: str
    summary: str
    detail: str
    sparkline: tuple[str, ...]
    provenance: PortfolioSourceNote | None = None


@dataclass(frozen=True)
class PortfolioSeriesPoint:
    label: str
    timestamp_utc: datetime | None
    equity: str
    cash: str
    buying_power: str


@dataclass(frozen=True)
class PortfolioCurvePanel:
    status: str
    headline: str
    detail: str
    points: tuple[PortfolioSeriesPoint, ...]


@dataclass(frozen=True)
class PortfolioBenchmarkRow:
    benchmark_id: str
    label: str
    portfolio_return: str
    benchmark_return: str
    excess_return: str
    detail: str


@dataclass(frozen=True)
class PortfolioBenchmarkPanel:
    status: str
    headline: str
    detail: str
    benchmark_rows: tuple[PortfolioBenchmarkRow, ...]


@dataclass(frozen=True)
class PortfolioStrategyRow:
    strategy_id: str
    label: str
    status: str
    pnl: str
    trade_count: str
    win_rate: str
    max_drawdown: str
    detail: str
    drift_severity: str = "pending"


@dataclass(frozen=True)
class PortfolioStrategyPanel:
    status: str
    headline: str
    detail: str
    strategies: tuple[PortfolioStrategyRow, ...]
    active_blueprint_id: str | None = None
    constituent_sleeve_ids: tuple[str, ...] = ()
    narrowing_notice: str | None = None


@dataclass(frozen=True)
class PortfolioKeyValue:
    label: str
    value: str


@dataclass(frozen=True)
class PortfolioEventSummary:
    label: str
    value: str
    context: str


@dataclass(frozen=True)
class PortfolioExecutionPanel:
    status: str
    headline: str
    detail: str
    summary_metrics: tuple[PortfolioKeyValue, ...]
    recent_events: tuple[PortfolioEventSummary, ...]
    provenance: PortfolioSourceNote | None = None


@dataclass(frozen=True)
class PortfolioPositionRow:
    symbol: str
    quantity: str
    market_value: str
    exposure_pct: str
    status: str


@dataclass(frozen=True)
class PortfolioPositionsPanel:
    status: str
    headline: str
    detail: str
    positions: tuple[PortfolioPositionRow, ...]


@dataclass(frozen=True)
class PortfolioDiagnostic:
    diagnostic_id: str
    title: str
    detail: str
    severity: str
    owner: str
    action: str


@dataclass(frozen=True)
class PortfolioWorkspaceSnapshot:
    generated_at_utc: datetime
    trading_mode: str
    data_state: str
    source_summary: str
    source_notes: tuple[PortfolioSourceNote, ...]
    metric_cards: tuple[PortfolioMetricCard, ...]
    equity_curve: PortfolioCurvePanel
    benchmark_panel: PortfolioBenchmarkPanel
    strategy_panel: PortfolioStrategyPanel
    execution_panel: PortfolioExecutionPanel
    positions_panel: PortfolioPositionsPanel
    diagnostics: tuple[PortfolioDiagnostic, ...]
    source_evidence_at_utc: datetime | None = None
    account_position_source_at_utc: datetime | None = None
    execution_journal_source_at_utc: datetime | None = None
    closed_trade_source_at_utc: datetime | None = None


@dataclass(frozen=True)
class PerformanceKpi:
    metric_id: str
    label: str
    value: str
    delta: str
    tone: str
    context: str
    tooltip: str
    sparkline: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkOption:
    benchmark_id: str
    label: str


@dataclass(frozen=True)
class PerformanceSeriesPoint:
    label: str
    portfolio: Decimal
    sp500: Decimal
    nasdaq100: Decimal
    custom: Decimal


@dataclass(frozen=True)
class BenchmarkComparisonRow:
    benchmark_id: str
    label: str
    portfolio_return: str
    benchmark_return: str
    excess_return: str
    alpha: str
    beta: str
    tracking_error: str
    information_ratio: str
    up_capture: str
    down_capture: str
    max_drawdown: str
    correlation: str


@dataclass(frozen=True)
class PerformancePeriodBar:
    label: str
    value: Decimal


@dataclass(frozen=True)
class PerformanceWindowSnapshot:
    window_id: str
    label: str
    series: tuple[PerformanceSeriesPoint, ...]
    benchmark_rows: tuple[BenchmarkComparisonRow, ...]
    period_bars: tuple[PerformancePeriodBar, ...]


@dataclass(frozen=True)
class StrategyAttributionRow:
    strategy_id: str
    label: str
    pnl: str
    total_return: str
    sharpe_ratio: str
    max_drawdown: str
    win_rate: str
    profit_factor: str
    contribution_pct: str
    stability_score: str
    recent_trend: str
    regime_fit: str
    status: str


@dataclass(frozen=True)
class StrategyHeatmapCell:
    strategy_id: str
    regime: str
    value: Decimal
    tone: str


@dataclass(frozen=True)
class PerformanceDiagnostic:
    diagnostic_id: str
    title: str
    detail: str
    severity: str
    owner: str
    action: str


@dataclass(frozen=True)
class PerformanceAnalyticsSnapshot:
    generated_at_utc: datetime
    data_mode: str
    source_summary: str
    default_window: str
    default_benchmark_id: str
    current_regime: str
    kpi_cards: tuple[PerformanceKpi, ...]
    benchmark_options: tuple[BenchmarkOption, ...]
    available_windows: tuple[str, ...]
    performance_windows: dict[str, PerformanceWindowSnapshot]
    strategy_rows: tuple[StrategyAttributionRow, ...]
    strategy_heatmap: tuple[StrategyHeatmapCell, ...]
    diagnostics: tuple[PerformanceDiagnostic, ...]


__all__ = (
    "AccountSnapshot",
    "AlertDrillRecord",
    "BenchmarkComparisonRow",
    "BenchmarkOption",
    "BenchmarkCloseSeries",
    "BootstrapPositionAllocation",
    "BotRuntimeState",
    "BlueprintActivationRecord",
    "BlueprintSleeveBinding",
    "CPCVCohortWindowSummary",
    "CPCVTrialRecord",
    "ClosedTradeRecord",
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
    "HistoricalWarmupRecord",
    "LatestQuote",
    "MarketAutomationRunRecord",
    "MarketAutomationRunResult",
    "MarketDayScheduleRecord",
    "MarketDaySchedulerRunResult",
    "MarketDaySchedulerState",
    "MarketSessionRecord",
    "MarketSnapshot",
    "ApprovedWeightSnapshot",
    "OpportunityScore",
    "OpportunitySelectionRecord",
    "OperatorAlert",
    "OrderRecord",
    "PBOReport",
    "PortfolioBenchmarkPanel",
    "PortfolioBenchmarkRow",
    "PortfolioCurvePanel",
    "PortfolioDiagnostic",
    "PortfolioEventSummary",
    "PortfolioExecutionPanel",
    "PortfolioKeyValue",
    "PortfolioMetricCard",
    "PortfolioPositionRow",
    "PortfolioPositionsPanel",
    "PortfolioSeriesPoint",
    "PortfolioStrategyPanel",
    "PortfolioStrategyRow",
    "PortfolioState",
    "PortfolioWorkspaceSnapshot",
    "PerformanceAnalyticsSnapshot",
    "PerformanceDiagnostic",
    "PerformanceKpi",
    "PerformancePeriodBar",
    "PerformanceSeriesPoint",
    "PerformanceWindowSnapshot",
    "PositionSnapshot",
    "ReplaySlippageGenerationResult",
    "ReplaySlippageRecord",
    "ReplaySlippageSummary",
    "ReconciliationSnapshot",
    "RecoveryDrillRecord",
    "ResidualPositionAllocation",
    "ResidualReserveSnapshot",
    "RegimeSnapshot",
    "RiskControlEvent",
    "RoundTripResult",
    "RuntimeDecisionDetail",
    "RuntimeDecisionExecutionDetail",
    "RuntimeDecisionFreshnessDetail",
    "RuntimeDecisionRegimeDetail",
    "RuntimeDecisionRiskDetail",
    "RuntimeDecisionSignalDetail",
    "RuntimeHeartbeatSnapshot",
    "ScalarValue",
    "SessionOpenPortfolioStateRecord",
    "ServiceCycleSnapshot",
    "ServiceRunResult",
    "ServiceSymbolResult",
    "DriftMonitorVerdictRecord",
    "SleeveAttributionGapRecord",
    "SleeveBootstrapAllocationRecord",
    "SleeveContext",
    "SleeveDecompositionRecord",
    "SleeveDailyAttributionRecord",
    "SleeveFailureReason",
    "SleeveLedgerPosition",
    "SleevePositionLedgerSnapshot",
    "SleeveTargetWeights",
    "SleeveTrade",
    "StrategyActivationRecord",
    "StrategyAttributionRow",
    "StrategyCandidate",
    "StrategyHeatmapCell",
    "TrialRecord",
    "TrialStatistics",
    "TradeIntent",
    "TradingLoopResult",
    "ValidationCandidateResult",
    "ValidationCriterionResult",
    "ValidationReport",
    "WebActionResult",
    "WebServiceState",
)
