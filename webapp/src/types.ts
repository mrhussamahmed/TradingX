export type EvidenceCategory =
  | 'operator_alerts'
  | 'service_cycles'
  | 'validation_reports'

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

export type ConfigSummary = {
  config: {
    web_write_mode_enabled: boolean
    symbol_universe: string[]
    service_interval_seconds: number
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
