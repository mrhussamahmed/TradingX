export type EvidenceCategory =
  | 'operator_alerts'
  | 'service_cycles'
  | 'validation_reports'
  | 'market_sessions'
  | 'recovery_drills'
  | 'alert_drills'

export type EvidenceItem = Record<string, unknown>

export type DashboardSnapshot = {
  generated_at_utc: string
  service_status: {
    status: string
    active_symbols: string[]
    interval_seconds: number
    cycles_completed: number
    started_at_utc: string | null
    last_completed_at_utc: string | null
    last_error: string
  }
  account_summary: {
    cash: string
    equity: string
    buying_power: string
    daily_pnl: string
  }
  positions: Array<{
    symbol: string
    quantity: string
    market_value: string
  }>
  alerts: string[]
  gate_statuses: Record<string, string>
  recommendations: Record<string, number>
  document_summary: Record<string, string | number>
}

export type CommandCenterSnapshot = {
  generated_at_utc: string
  service_status: DashboardSnapshot['service_status']
  market_session_label: string
  session_mode: string
  account_summary: DashboardSnapshot['account_summary']
  equity_curve: Array<{ label: string; value: string }>
  exposure_breakdown: Array<{
    symbol: string
    value: string | null
    value_status?: string
    missing_reason?: string
  }>
  watchlist: Array<{ symbol: string; status: string }>
  gate_statuses: Record<string, string>
  recommendations: Record<string, number>
  headline_incidents: Array<{ incident_id: string; severity: string }>
}

export type PortfolioMetricCard = {
  metric_id: string
  label: string
  value: string
  delta: string
  health: string
  summary: string
  detail: string
  sparkline: string[]
  provenance?: PortfolioSourceNote | null
}

export type PortfolioSourceNote = {
  source_id: string
  label: string
  tone: string
  detail: string
}

export type PortfolioSeriesPoint = {
  label: string
  timestamp_utc: string | null
  equity: string
  cash: string
  buying_power: string
}

export type PortfolioCurvePanel = {
  status: string
  headline: string
  detail: string
  points: PortfolioSeriesPoint[]
}

export type PortfolioBenchmarkRow = {
  benchmark_id: string
  label: string
  portfolio_return: string
  benchmark_return: string
  excess_return: string
  detail: string
}

export type PortfolioBenchmarkPanel = {
  status: string
  headline: string
  detail: string
  benchmark_rows: PortfolioBenchmarkRow[]
}

export type PortfolioStrategyRow = {
  strategy_id: string
  label: string
  status: string
  pnl: string
  trade_count: string
  win_rate: string
  max_drawdown: string
  detail: string
}

export type PortfolioStrategyPanel = {
  status: string
  headline: string
  detail: string
  strategies: PortfolioStrategyRow[]
  active_blueprint_id?: string | null
  constituent_sleeve_ids?: string[]
  narrowing_notice?: string | null
}

export type BlueprintSleeveBinding = {
  sleeve_id: string
  strategy_id: string
  captured_snapshot_id: string
}

export type BlueprintActivationRecord = {
  activation_id: string
  blueprint_id: string
  sleeve_activation_bindings: BlueprintSleeveBinding[]
  status: string
  approved_at_utc: string
  approved_by: string
  source_blueprint_path: string
  blueprint_content_hash?: string | null
  blueprint_payload?: Record<string, unknown> | null
  superseded_at_utc?: string | null
  supersedes_activation_id?: string | null
}

export type PortfolioBlueprintSleeveSummary = {
  sleeve_id: string
  strategy_id: string
  budget_fraction_of_equity: string
  max_correlation_with_other_sleeves: string
}

export type PortfolioBlueprintSummary = {
  blueprint_id: string
  source_path: string
  sleeve_budgets: PortfolioBlueprintSleeveSummary[]
  max_gross_exposure: string
  max_net_exposure: string
  status: string
  detail: string
}

export type BlueprintActivationCheck = {
  code: string
  status: string
  severity: string
  message: string
  sleeve_id?: string | null
  strategy_id?: string | null
  evidence_refs: string[]
  captured_snapshot_ids: string[]
}

export type BlueprintActivationPreflight = {
  blueprint_id: string
  status: string
  checks: BlueprintActivationCheck[]
  sleeve_bindings: BlueprintSleeveBinding[]
  captured_snapshot_ids: string[]
  source_blueprint_path: string
  preview_hash: string
  blueprint_content_hash: string
  would_reuse_active_activation: boolean
}

export type PortfolioBlueprintCatalog = {
  blueprints: PortfolioBlueprintSummary[]
  active_activation?: BlueprintActivationRecord | null
  pending_activation?: BlueprintActivationRecord | null
}

export type PortfolioKeyValue = {
  label: string
  value: string
}

export type PortfolioEventSummary = {
  label: string
  value: string
  context: string
}

export type PortfolioExecutionPanel = {
  status: string
  headline: string
  detail: string
  summary_metrics: PortfolioKeyValue[]
  recent_events: PortfolioEventSummary[]
  provenance?: PortfolioSourceNote | null
}

export type PortfolioPositionRow = {
  symbol: string
  quantity: string | null
  market_value: string | null
  exposure_pct: string | null
  status: string
  quantity_status?: string
  price_status?: string
  exposure_status?: string
  average_entry_price?: string | null
  latest_price?: string | null
  latest_price_at_utc?: string | null
  source_evidence_at_utc?: string | null
}

export type PortfolioPositionsPanel = {
  status: string
  headline: string
  detail: string
  positions: PortfolioPositionRow[]
}

export type PortfolioDiagnostic = {
  diagnostic_id: string
  title: string
  detail: string
  severity: string
  owner: string
  action: string
}

export type PortfolioWorkspaceSnapshot = {
  generated_at_utc: string
  source_evidence_at_utc?: string | null
  trading_mode: string
  data_state: string
  source_summary: string
  source_notes: PortfolioSourceNote[]
  metric_cards: PortfolioMetricCard[]
  equity_curve: PortfolioCurvePanel
  benchmark_panel: PortfolioBenchmarkPanel
  strategy_panel: PortfolioStrategyPanel
  execution_panel: PortfolioExecutionPanel
  positions_panel: PortfolioPositionsPanel
  diagnostics: PortfolioDiagnostic[]
}

export type IncidentRecord = {
  incident_id: string
  title: string
  severity: string
  status: string
  category: string
  summary: string
  first_seen_at_utc: string
  latest_seen_at_utc: string
  acknowledged_at_utc: string | null
  acknowledged_by: string
  related_event_ids: string[]
  evidence_refs: string[]
  suggested_action: string
}

export type OperatorTimelineEvent = {
  event_id: string
  event_type: string
  symbol: string
  severity: string
  headline: string
  details: string
  occurred_at_utc: string
  artifact_path: string
  related_ids: string[]
}

export type SessionTimelineSession = {
  trading_day: string
  schedule_id: string
  session_open_at_utc: string | null
  session_close_at_utc: string | null
  exchange: string
  timezone: string
  status: string
  metadata_status: string
  partial_reason: string
}

export type SessionTimelineEvent = {
  event_id: string
  event_type: string
  symbol: string
  severity: string
  headline: string
  details: string
  occurred_at_utc: string
  artifact_path: string
  related_ids: string[]
  shape: 'instant' | 'span' | string
  started_at_utc: string | null
  ended_at_utc: string | null
  duration_seconds: number | null
  status: string
  reason: string
  evidence_freshness: string
  source_status: string
}

export type SessionTimelineFilters = {
  trading_day: string
  symbol: string | null
  cycle_id: string | null
  incident_id: string | null
}

export type SessionTimelineResponse = {
  session: SessionTimelineSession
  available_trading_days: string[]
  events: SessionTimelineEvent[]
  filters: SessionTimelineFilters
}

export type ReplaySession = {
  replay_id: string
  focus_type: string
  focus_value: string
  headline: string
  events: OperatorTimelineEvent[]
  summary: string
}

export type ResearchCandidateSummary = {
  candidate_id: string
  family: string
  recommendation: string
  benchmark_metrics: Record<string, string>
  candidate_metrics: Record<string, string>
  adversarial_checks: string[]
  gate_statuses: Record<string, string>
  summary: string
}

export type ResearchStudioSnapshot = {
  generated_at_utc: string
  gate_summaries: Array<Record<string, string>>
  candidate_summaries: ResearchCandidateSummary[]
  decision_summary: string
}

export type ExplorerRecord = {
  record_id: string
  category: string
  title: string
  preview: string
  path: string
  symbol: string
  recorded_at_utc: string
}

export type DailySessionDigest = {
  digest_id: string
  generated_at_utc: string
  session_label: string
  service_status: string
  blocked_trade_count: number
  reconciliation_failure_count: number
  latest_positions: string[]
  top_incidents: string[]
  recommended_actions: string[]
  evidence_refs: string[]
}

export type ConfigSummary = {
  config: {
    web_write_mode_enabled: boolean
    web_write_signing_configured: boolean
    web_write_max_age_seconds: number
    symbol_universe: string[]
    service_interval_seconds: number
    web_refresh_interval_seconds: number
  } & Record<string, unknown>
  live_disable_report: {
    paper_only_mode: boolean
    live_trading_enabled: boolean
    manual_kill_switch_active: boolean
  }
}

export type DocumentRecord = {
  doc_id: string
  title: string
  path: string
  preview: string
  kind: string
}

export type ActionResult = {
  action_id: string
  action_type: string
  status: string
  message: string
  evidence_refs: string[]
}

export type BotRuntimeState = {
  status: string
  status_reason: string
  active_symbols: string[]
  started_at_utc: string | null
  updated_at_utc: string
  last_error: string
  active_strategy_id: string
  active_model_snapshot_id: string
  latest_selection_id: string
}

export type BotBrainDecisionStage = {
  stage: string
  status: string
  detail: string
  occurred_at_utc: string | null
}

export type BotBrainOrderEvent = {
  event_type: string
  recorded_at_utc: string
  symbol: string
  side: string
  client_order_id: string
  broker_order_id: string
  reason: string
}

export type BotBrainSleeveReadiness = {
  sleeve_id: string
  strategy_id: string
  implemented: boolean
  runtime_resolvable: boolean
  paper_approved: boolean
  allocation_approved: boolean
  display_state: string
  blocker_code: string
  human_explanation: string
  fix_guidance: string
  evidence_refs: string[]
  activation_id?: string
  blueprint_id?: string
  activation_role?: string
}

export type BotBrainSleeveCycleReason = {
  sleeve_id: string
  status: string
  reason: string
}

export type BotBrainCycleExplanation = {
  summary: string
  primary_reason_code: string
  market_state: string
  planner_status: string
  risk_status: string
  sleeve_reasons: BotBrainSleeveCycleReason[]
}

export type BotBrainSnapshot = {
  generated_at_utc: string
  active_blueprint_id: string
  queued_blueprint_id: string
  trading_mode: string
  market_state: string
  next_check_at_utc: string | null
  decision_stages: BotBrainDecisionStage[]
  last_real_order: BotBrainOrderEvent | null
  sleeve_readiness: BotBrainSleeveReadiness[]
  cycle_explanation: BotBrainCycleExplanation
}

export type RuntimeTruthItem = {
  label: string
  value: string
  detail: string
  tone: string
}

export type RuntimeSymbolHeartbeatRow = {
  symbol: string
  status: string
  score: string
  threshold_gap: string
  reason: string
  warmup_state: string
  exposure_state: string
  tone: string
}

export type RuntimeDecisionLadderRow = {
  rank: number
  symbol: string
  final_score: string
  threshold: string
  threshold_gap: string
  primary_driver: string
  disposition: string
}

export type RuntimeOperatorGuidance = {
  recommendation: string
  detail: string
  tone: string
}

export type RuntimeHeartbeatSnapshot = {
  heartbeat_state: string
  heartbeat_summary: string
  heartbeat_tone: string
  cadence_seconds: number
  cadence_label: string
  last_evaluation_at_utc: string | null
  next_evaluation_at_utc: string | null
  last_decision: string
  decision_reason: string
  score_explanation: string
  current_exposure: string
  current_exposure_detail: string
  active_symbol: string
  selected_symbol: string
  decision: string
  runtime_truth: RuntimeTruthItem[]
  symbol_rows: RuntimeSymbolHeartbeatRow[]
  decision_ladder: RuntimeDecisionLadderRow[]
  operator_guidance: RuntimeOperatorGuidance | null
  configured_cadence_seconds?: number | null
  running_cadence_seconds?: number | null
  cadence_source?: string
  cadence_applies_at?: string
}

export type RuntimeDecisionSignalDetail = {
  source_evidence_at_utc?: string | null
} & Record<string, unknown>

export type RuntimeDecisionRegimeDetail = {
  source_evidence_at_utc?: string | null
} & Record<string, unknown>

export type RuntimeDecisionRiskDetail = {
  source_evidence_at_utc?: string | null
} & Record<string, unknown>

export type RuntimeDecisionExecutionDetail = {
  source_evidence_at_utc?: string | null
} & Record<string, unknown>

export type RuntimeDecisionFreshnessDetail = {
  decision_source_at_utc?: string | null
  missing_source_fields?: string[]
} & Record<string, unknown>

export type RuntimeDecisionDetail = {
  selection_id: string
  generated_at_utc: string
  decision_source_at_utc: string | null
  decision: string
  decision_reason: string
  signal?: RuntimeDecisionSignalDetail | null
  regime?: RuntimeDecisionRegimeDetail | null
  risk?: RuntimeDecisionRiskDetail | null
  execution?: RuntimeDecisionExecutionDetail | null
  freshness?: RuntimeDecisionFreshnessDetail | null
} & Record<string, unknown>

export type HistoricalWarmupRecord = {
  warmup_id: string
  generated_at_utc: string
  benchmark_symbol: string
  symbols: string[]
  window_start_utc: string
  window_end_utc: string
  required_bar_count: number
  symbols_ready: string[]
  symbols_blocked: Record<string, string>
  return_summary: Record<string, Record<string, string>>
}

export type StrategyActivationRecord = {
  activation_id: string
  strategy_id: string
  strategy_version: string
  approved_symbols: string[]
  deploy_threshold: string
  allow_fallback_weights: boolean
  status: string
  activated_at_utc: string
  notes: string
}

export type ModelWeightSnapshot = {
  snapshot_id: string
  strategy_id: string
  status: string
  generated_at_utc: string
  minimum_supporting_trades: number
  weights: Record<string, string>
}

export type OpportunityScore = {
  symbol: string
  base_signal: string
  regime_weight: string
  model_weight: string
  liquidity_weight: string
  spread_penalty: string
  volatility_penalty: string
  portfolio_overlap_penalty: string
  execution_cost_penalty: string
  final_score: string
  eligible: boolean
  ineligibility_reason: string
}

export type OpportunitySelectionRecord = {
  selection_id: string
  generated_at_utc: string
  strategy_id: string
  model_snapshot_id: string
  symbols_considered: string[]
  ranked_opportunities: OpportunityScore[]
  selected_symbol: string
  decision: string
  decision_reason: string
}

export type ConfigProposal = {
  proposal_id: string
  target_area: string
  proposed_values: Record<string, unknown>
  diff_preview: string
  output_path: string
}

export type PerformanceKpi = {
  metric_id: string
  label: string
  value: string
  delta: string
  tone: string
  context: string
  tooltip: string
  sparkline: string[]
}

export type BenchmarkOption = {
  benchmark_id: string
  label: string
}

export type PerformanceSeriesPoint = {
  label: string
  portfolio: string
  sp500: string
  nasdaq100: string
  custom: string
}

export type BenchmarkComparisonRow = {
  benchmark_id: string
  label: string
  portfolio_return: string
  benchmark_return: string
  excess_return: string
  alpha: string
  beta: string
  tracking_error: string
  information_ratio: string
  up_capture: string
  down_capture: string
  max_drawdown: string
  correlation: string
}

export type PerformancePeriodBar = {
  label: string
  value: string
}

export type PerformanceWindowSnapshot = {
  window_id: string
  label: string
  series: PerformanceSeriesPoint[]
  benchmark_rows: BenchmarkComparisonRow[]
  period_bars: PerformancePeriodBar[]
}

export type StrategyAttributionRow = {
  strategy_id: string
  label: string
  pnl: string
  total_return: string
  sharpe_ratio: string
  max_drawdown: string
  win_rate: string
  profit_factor: string
  contribution_pct: string
  stability_score: string
  recent_trend: string
  regime_fit: string
  status: string
}

export type StrategyHeatmapCell = {
  strategy_id: string
  regime: string
  value: string
  tone: string
}

export type PerformanceDiagnostic = {
  diagnostic_id: string
  title: string
  detail: string
  severity: string
  owner: string
  action: string
}

export type PerformanceAnalyticsSnapshot = {
  generated_at_utc: string
  data_mode: string
  source_summary: string
  default_window: string
  default_benchmark_id: string
  current_regime: string
  kpi_cards: PerformanceKpi[]
  benchmark_options: BenchmarkOption[]
  available_windows: string[]
  performance_windows: Record<string, PerformanceWindowSnapshot>
  strategy_rows: StrategyAttributionRow[]
  strategy_heatmap: StrategyHeatmapCell[]
  diagnostics: PerformanceDiagnostic[]
}

export type Gate3CriterionSnapshot = {
  criterion_id: string
  status: string
  threshold: string
  observed_value: string
  details: string
  evidence_refs: string[]
  source_evidence_at_utc?: string | null
  required?: boolean
}

export type Gate3ReadinessReport = {
  report_id: string
  generated_at_utc: string
  source_evidence_at_utc?: string | null
  oldest_required_source_evidence_at_utc?: string | null
  latest_source_evidence_at_utc?: string | null
  missing_source_criterion_ids?: string[]
  required_criterion_ids?: string[]
  status: string
  closed_trade_count: number
  calendar_days_observed: number
  criteria: Gate3CriterionSnapshot[]
  summary: string
  required_operator_action: string
  evidence_refs: string[]
}

export type Gate3PromotionPackage = {
  package_id: string
  generated_at_utc: string
  status: string
  headline: string
  decision_summary: string
  criteria_statuses: Record<string, string>
  evidence_refs: string[]
}

export type ReplaySlippageSummary = {
  summary_id: string
  matched_execution_count: number
  paper_mean_absolute_slippage_bps: string
  replay_mean_absolute_slippage_bps: string
  divergence_ratio: string
  status: string
  details: string
  generated_at_utc: string
}

export type MarketAutomationRunRecord = {
  run_id: string
  started_at_utc: string
  completed_at_utc: string
  trading_day: string
  status: string
  heartbeat_count: number
  preopen_session_id: string
  heartbeat_session_ids: string[]
  close_session_id: string
  latest_replay_summary_id: string
  latest_gate3_report_id: string
  latest_gate3_package_id: string
  summary: string
  evidence_refs: string[]
}

export type MarketDaySchedulerState = {
  status: string
  poll_interval_seconds: number
  active_symbols: string[]
  next_run_at_utc: string | null
  last_started_at_utc: string | null
  last_completed_at_utc: string | null
  active_trading_day: string
  last_error: string
}

export type MarketDayScheduleRecord = {
  schedule_id: string
  trading_day: string
  scheduled_open_at_utc: string
  launched_at_utc: string
  completed_at_utc: string | null
  status: string
  automation_run_id: string
  summary: string
  evidence_refs: string[]
}

export type MarketSessionRecord = {
  session_id: string
  session_label: string
  recorded_at_utc: string
  service_status: string
  blocked_trade_count: number
  reconciliation_failure_count: number
  open_positions: string[]
  top_incidents: string[]
  recommended_actions: string[]
  evidence_refs: string[]
}

export type RecoveryDrillRecord = {
  drill_id: string
  symbol: string
  started_at_utc: string
  completed_at_utc: string | null
  status: string
  summary: string
  evidence_refs: string[]
}

export type AlertDrillRecord = {
  drill_id: string
  channel: string
  recorded_at_utc: string
  status: string
  summary: string
  evidence_refs: string[]
}
