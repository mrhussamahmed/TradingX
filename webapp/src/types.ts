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
  exposure_breakdown: Array<{ symbol: string; value: string }>
  watchlist: Array<{ symbol: string; status: string }>
  gate_statuses: Record<string, string>
  recommendations: Record<string, number>
  headline_incidents: Array<{ incident_id: string; severity: string }>
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

export type ConfigProposal = {
  proposal_id: string
  target_area: string
  proposed_values: Record<string, unknown>
  diff_preview: string
  output_path: string
}

export type Gate3CriterionSnapshot = {
  criterion_id: string
  status: string
  threshold: string
  observed_value: string
  details: string
  evidence_refs: string[]
}

export type Gate3ReadinessReport = {
  report_id: string
  generated_at_utc: string
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
