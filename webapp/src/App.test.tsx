import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const overviewPayload = {
  generated_at_utc: '2026-04-20T08:40:00+00:00',
  service_status: {
    status: 'halted',
    active_symbols: ['SPY', 'QQQ', 'IWM'],
    interval_seconds: 180,
    cycles_completed: 0,
    started_at_utc: null,
    last_completed_at_utc: null,
    last_error: '',
  },
  account_summary: {
    cash: '99999.57',
    equity: '99999.57',
    buying_power: '399998.28',
    daily_pnl: '0.00',
  },
  positions: [],
  alerts: [],
  gate_statuses: {},
  recommendations: {},
  document_summary: {
    session_count: 1,
    latest_state: 'System waiting for the first supervised market cycle.',
  },
}

const commandCenterPayload = {
  generated_at_utc: '2026-04-20T08:40:00+00:00',
  service_status: overviewPayload.service_status,
  market_session_label: 'Local operator monitor',
  session_mode: 'standby',
  account_summary: overviewPayload.account_summary,
  equity_curve: [],
  exposure_breakdown: [],
  watchlist: [
    { symbol: 'SPY', status: 'monitor' },
    { symbol: 'QQQ', status: 'monitor' },
    { symbol: 'IWM', status: 'monitor' },
  ],
  gate_statuses: {},
  recommendations: {},
  headline_incidents: [],
}

const configSummaryPayload = {
  config: {
    web_write_mode_enabled: true,
    symbol_universe: ['SPY', 'QQQ', 'IWM'],
    service_interval_seconds: 180,
    web_refresh_interval_seconds: 15,
  },
  live_disable_report: {
    paper_only_mode: true,
    live_trading_enabled: false,
    manual_kill_switch_active: false,
  },
}

const documentsPayload = [
  {
    doc_id: 'STATE',
    title: 'Project state',
    path: 'docs/handover/STATE.md',
    preview: 'System waiting for the first supervised market cycle.',
    kind: 'state',
  },
]

const proposalsPayload: Array<Record<string, unknown>> = []

const incidentsPayload = [
  {
    incident_id: 'incident-alert-1',
    title: 'Warmup breadth incomplete',
    severity: 'warning',
    status: 'open',
    category: 'runtime',
    summary: 'QQQ is still blocked because the warmup window is incomplete.',
    first_seen_at_utc: '2026-04-20T08:35:00+00:00',
    latest_seen_at_utc: '2026-04-20T08:35:00+00:00',
    acknowledged_at_utc: null,
    acknowledged_by: '',
    related_event_ids: ['event-1'],
    evidence_refs: ['artifacts/operator_platform/runtime_host/state.json'],
    suggested_action: 'Refresh warmup inputs before broadening the universe.',
  },
]

const researchPayload = {
  generated_at_utc: '2026-04-20T08:40:00+00:00',
  gate_summaries: [],
  candidate_summaries: [],
  decision_summary: 'No gate assessments are available yet.',
}

const replayPayload = {
  replay_id: 'replay-1',
  focus_type: 'symbol',
  focus_value: 'SPY',
  headline: 'SPY replay',
  events: [
    {
      event_id: 'event-1',
      event_type: 'reject',
      symbol: 'SPY',
      severity: 'warning',
      headline: 'Insufficient buying power',
      details: 'Paper submit was rejected because requested exposure was too large.',
      occurred_at_utc: '2026-04-20T08:35:00+00:00',
      artifact_path: 'artifacts/ops/data/journal.db',
      related_ids: ['incident-alert-1'],
    },
  ],
  summary: 'Replay contains the latest rejected execution attempts.',
}

const explorerPayload = [
  {
    record_id: 'record-1',
    category: 'validation_report',
    title: 'Gate 1 report',
    preview: 'No validated alpha report has been generated yet.',
    path: 'artifacts/validation/validation_reports/gate-1.json',
    symbol: 'SPY',
    recorded_at_utc: '2026-04-20T08:10:00+00:00',
  },
]

const digestPayload = {
  digest_id: 'digest-1',
  generated_at_utc: '2026-04-20T08:30:00+00:00',
  session_label: 'session_preopen',
  service_status: 'idle',
  blocked_trade_count: 2,
  reconciliation_failure_count: 0,
  latest_positions: [],
  top_incidents: ['incident-alert-1'],
  recommended_actions: ['Complete warmup before resuming automation.'],
  evidence_refs: ['artifacts/operator_platform/daily_digests/digest-1.json'],
}

const gate3ReadinessPayload = {
  report_id: 'gate3-1',
  generated_at_utc: '2026-04-20T08:40:00+00:00',
  status: 'pending',
  closed_trade_count: 0,
  calendar_days_observed: 0,
  criteria: [],
  summary: 'Gate 3 is waiting for real paper evidence.',
  required_operator_action: 'Keep the paper runtime supervised until enough evidence exists.',
  evidence_refs: ['artifacts/validation/gate3_reports/gate3-1.json'],
}

const gate3PackagePayload = null
const replaySlippageSummaryPayload = null
const marketAutomationPayload = null

const schedulerStatePayload = {
  status: 'idle',
  poll_interval_seconds: 60,
  active_symbols: ['SPY'],
  next_run_at_utc: null,
  last_started_at_utc: null,
  last_completed_at_utc: null,
  active_trading_day: '',
  last_error: '',
}

const schedulerLatestPayload = null

const portfolioPayload = {
  generated_at_utc: '2026-04-20T08:40:00+00:00',
  trading_mode: 'paper',
  data_state: 'partial',
  source_summary:
    'Account balances, runtime posture, and execution journal are live. Seeded-account comparisons still use the saved rehearsal baseline. Benchmark comparison and strategy attribution stay hidden until TradingX records real portfolio history.',
  source_notes: [
    {
      source_id: 'live_account',
      label: 'Live account',
      tone: 'good',
      detail:
        'Equity, cash, buying power, positions, and balance snapshots come from the current paper account and live TradingX service artifacts.',
    },
    {
      source_id: 'live_oms_journal',
      label: 'Live OMS journal',
      tone: 'good',
      detail:
        'Execution diagnostics come from the current local OMS journal at data/journal.db, not from rehearsal artifacts.',
    },
    {
      source_id: 'rehearsal_baseline',
      label: 'Rehearsal baseline',
      tone: 'watch',
      detail:
        'Comparisons that mention the seeded account use the saved starting-state snapshot from artifacts/ops/paper_account_starting_state.json.',
    },
  ],
  metric_cards: [
    {
      metric_id: 'equity',
      label: 'Total Equity',
      value: '$99,999.57',
      delta: 'Flat vs seeded account',
      health: 'neutral',
      summary:
        'Neutral for the main bot goal because capital is preserved, but no completed supervised cycle has produced edge yet.',
      detail:
        'The balance is intact. This is good for capital preservation, but it does not yet prove that the strategy can generate risk-adjusted returns.',
      sparkline: [],
      provenance: {
        source_id: 'mixed_evidence',
        label: 'Mixed evidence',
        tone: 'watch',
        detail:
          'The current value is live, but its comparison anchor comes from the saved rehearsal baseline snapshot.',
      },
    },
    {
      metric_id: 'buying_power',
      label: 'Buying Power',
      value: '$399,998.28',
      delta: 'Fully available',
      health: 'neutral',
      summary:
        'Neutral because capital is available, but deployment is blocked until warmup and execution sizing are healthy.',
      detail:
        'High buying power is only useful when the runtime can deploy it safely. Right now it mostly indicates idle capacity.',
      sparkline: [],
      provenance: {
        source_id: 'live_account',
        label: 'Live account',
        tone: 'good',
        detail:
          'Equity, cash, buying power, positions, and balance snapshots come from the current paper account and live TradingX service artifacts.',
      },
    },
    {
      metric_id: 'execution_quality',
      label: 'Execution Quality',
      value: '2 rejects',
      delta: 'Latest reason: insufficient buying power',
      health: 'bad',
      summary:
        'Bad for the bot goal because the bot is attempting orders the account cannot currently support.',
      detail:
        'Execution drag is not theoretical here. The latest journal shows repeated rejected submissions, which means the bot sizing or constraints need review before live supervision.',
      sparkline: ['2', '2'],
      provenance: {
        source_id: 'live_oms_journal',
        label: 'Live OMS journal',
        tone: 'good',
        detail:
          'Execution diagnostics come from the current local OMS journal at data/journal.db, not from rehearsal artifacts.',
      },
    },
  ],
  equity_curve: {
    status: 'unavailable',
    headline: 'No real TradingX equity curve yet',
    detail:
      'The portfolio curve will appear after at least one timestamped service cycle is recorded.',
    points: [],
  },
  benchmark_panel: {
    status: 'unavailable',
    headline: 'Benchmark comparison waiting for evidence',
    detail:
      'TradingX needs a persisted equity history window before benchmark-relative analytics can be trusted.',
    benchmark_rows: [],
  },
  strategy_panel: {
    status: 'unavailable',
    headline: 'Strategy attribution waiting for closed-trade evidence',
    detail:
      'Strategy contribution will unlock after TradingX records closed trades and realized P&L.',
    strategies: [],
  },
  execution_panel: {
    status: 'available',
    headline: 'Execution journal is available',
    detail:
      'Recent order attempts are available from the OMS journal and are safe to inspect now.',
    provenance: {
      source_id: 'live_oms_journal',
      label: 'Live OMS journal',
      tone: 'good',
      detail:
        'Execution diagnostics come from the current local OMS journal at data/journal.db, not from rehearsal artifacts.',
    },
    summary_metrics: [
      { label: 'Reject Count', value: '2' },
      { label: 'Latest Reason', value: 'insufficient buying power' },
      { label: 'Latest Symbol', value: 'SPY' },
    ],
    recent_events: [
      {
        label: 'Reject',
        value: 'SPY buy rejected',
        context: 'insufficient buying power',
      },
    ],
  },
  positions_panel: {
    status: 'available',
    headline: 'No open positions',
    detail: 'The account is flat right now.',
    positions: [],
  },
  diagnostics: [
    {
      diagnostic_id: 'runtime',
      title: 'Runtime is halted before warmup completed',
      detail: 'QQQ remains blocked by insufficient warmup coverage.',
      severity: 'warning',
      owner: 'Runtime Host',
      action: 'Complete warmup and retest order sizing before resuming automation.',
    },
  ],
}

const runtimeStatePayload = {
  status: 'trading_ready',
  status_reason: 'Runtime boot complete.',
  active_symbols: ['SPY', 'QQQ', 'IWM'],
  started_at_utc: '2026-04-20T08:55:00+00:00',
  updated_at_utc: '2026-04-20T08:58:00+00:00',
  last_error: '',
  active_strategy_id: 'baseline-long-only-v1',
  active_model_snapshot_id: 'snapshot-1',
  latest_selection_id: 'selection-1',
}

const runtimeHeartbeatPayload = {
  heartbeat_state: 'Waiting for next evaluation',
  heartbeat_summary:
    'TradingX evaluated the configured universe, found no deployable trade, and is waiting for the next cadence tick.',
  heartbeat_tone: 'info',
  cadence_seconds: 180,
  cadence_label: 'Every 3m',
  last_evaluation_at_utc: '2026-04-20T08:58:30+00:00',
  next_evaluation_at_utc: '2026-04-20T09:01:30+00:00',
  last_decision: 'No trade',
  decision_reason: 'No eligible opportunity cleared the deploy threshold.',
  score_explanation: 'SPY scored 0.4177 which is below the deploy threshold of 0.50.',
  current_exposure: 'Flat',
  current_exposure_detail: 'No open position is currently held in the paper account.',
  active_symbol: 'SPY',
  selected_symbol: '',
  decision: 'no_trade',
  runtime_truth: [
    {
      label: 'Session posture',
      value: 'Intraday monitor',
      detail: 'TradingX is actively supervising the market session.',
      tone: 'info',
    },
    {
      label: 'Trading mode',
      value: 'Paper',
      detail: 'TradingX is currently restricted to paper execution only.',
      tone: 'good',
    },
    {
      label: 'Runtime engine',
      value: 'Active',
      detail: 'The runtime host is active and capable of evaluating the configured universe.',
      tone: 'good',
    },
    {
      label: 'Open positions',
      value: '0',
      detail: 'The paper account is flat right now.',
      tone: 'neutral',
    },
    {
      label: 'Pending orders',
      value: '0',
      detail: 'No in-flight OMS orders are waiting for a terminal event.',
      tone: 'neutral',
    },
    {
      label: 'Evaluation freshness',
      value: '<1m ago',
      detail: 'This measures how recently TradingX completed a full opportunity review.',
      tone: 'info',
    },
  ],
  symbol_rows: [
    {
      symbol: 'SPY',
      status: 'Below threshold',
      score: '0.4177',
      threshold_gap: '-0.0823',
      reason: 'Score remained below the deploy threshold.',
      warmup_state: 'Ready',
      exposure_state: 'Flat',
      tone: 'info',
    },
    {
      symbol: 'QQQ',
      status: 'Below threshold',
      score: '0.3310',
      threshold_gap: '-0.1690',
      reason: 'Score remained below the deploy threshold.',
      warmup_state: 'Ready',
      exposure_state: 'Flat',
      tone: 'info',
    },
    {
      symbol: 'IWM',
      status: 'Blocked',
      score: 'n/a',
      threshold_gap: 'n/a',
      reason: 'Insufficient daily bars for warmup coverage.',
      warmup_state: 'Blocked',
      exposure_state: 'Flat',
      tone: 'watch',
    },
  ],
  decision_ladder: [
    {
      rank: 1,
      symbol: 'SPY',
      final_score: '0.4177',
      threshold: '0.50',
      threshold_gap: '-0.0823',
      primary_driver: 'Volatility penalty',
      disposition: 'Monitor',
    },
    {
      rank: 2,
      symbol: 'QQQ',
      final_score: '0.3310',
      threshold: '0.50',
      threshold_gap: '-0.1690',
      primary_driver: 'Volatility penalty',
      disposition: 'Monitor',
    },
    {
      rank: 3,
      symbol: 'IWM',
      final_score: 'n/a',
      threshold: '0.50',
      threshold_gap: 'n/a',
      primary_driver: 'Warmup blocked',
      disposition: 'Blocked',
    },
  ],
  operator_guidance: {
    recommendation: 'Investigate warmup failure',
    detail:
      'IWM is still blocked by warmup, so TradingX is evaluating an incomplete universe. Resolve the warmup gap before broadening unattended operation.',
    tone: 'watch',
  },
}

const warmupPayload = {
  warmup_id: 'warmup-1',
  generated_at_utc: '2026-04-20T08:10:00+00:00',
  benchmark_symbol: 'SPY',
  symbols: ['SPY', 'QQQ', 'IWM'],
  window_start_utc: '2026-04-01T00:00:00+00:00',
  window_end_utc: '2026-04-20T08:10:00+00:00',
  required_bar_count: 30,
  symbols_ready: ['SPY', 'QQQ'],
  symbols_blocked: { IWM: 'Insufficient daily bars for warmup coverage.' },
  return_summary: { SPY: { cumulative_return: '0.02' }, QQQ: { cumulative_return: '0.01' } },
}

const activationPayload = {
  activation_id: 'activation-1',
  strategy_id: 'baseline-long-only-v1',
  strategy_version: '1.0.0',
  approved_symbols: ['SPY', 'QQQ', 'IWM'],
  deploy_threshold: '0.50',
  allow_fallback_weights: true,
  status: 'approved',
  activated_at_utc: '2026-04-19T19:53:17.819270+00:00',
  notes: 'Default local trading appliance activation.',
}

const modelSnapshotPayload = {
  snapshot_id: 'snapshot-1',
  strategy_id: 'baseline-long-only-v1',
  status: 'approved',
  generated_at_utc: '2026-04-19T19:53:17.819270+00:00',
  minimum_supporting_trades: 5,
  weights: { signal: '1.0' },
}

const selectionPayload = {
  selection_id: 'selection-1',
  generated_at_utc: '2026-04-20T08:58:28+00:00',
  strategy_id: 'baseline-long-only-v1',
  model_snapshot_id: 'snapshot-1',
  symbols_considered: ['SPY', 'QQQ', 'IWM'],
  ranked_opportunities: [],
  selected_symbol: '',
  decision: 'no_trade',
  decision_reason: 'No eligible opportunity cleared the deploy threshold.',
}

const marketSessionsPayload: Array<Record<string, unknown>> = []
const recoveryDrillsPayload: Array<Record<string, unknown>> = []
const alertDrillsPayload: Array<Record<string, unknown>> = []

function mockFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    void init

    if (url.endsWith('/api/overview')) {
      return new Response(JSON.stringify(overviewPayload))
    }
    if (url.endsWith('/api/platform/command-center')) {
      return new Response(JSON.stringify(commandCenterPayload))
    }
    if (url.endsWith('/api/config/summary')) {
      return new Response(JSON.stringify(configSummaryPayload))
    }
    if (url.endsWith('/api/documents')) {
      return new Response(JSON.stringify(documentsPayload))
    }
    if (url.endsWith('/api/config/proposals')) {
      return new Response(JSON.stringify(proposalsPayload))
    }
    if (url.endsWith('/api/platform/incidents')) {
      return new Response(JSON.stringify(incidentsPayload))
    }
    if (url.endsWith('/api/platform/research')) {
      return new Response(JSON.stringify(researchPayload))
    }
    if (url.endsWith('/api/platform/portfolio')) {
      return new Response(JSON.stringify(portfolioPayload))
    }
    if (url.endsWith('/api/platform/performance')) {
      return new Response(JSON.stringify(portfolioPayload))
    }
    if (url.includes('/api/platform/replay')) {
      return new Response(JSON.stringify(replayPayload))
    }
    if (url.includes('/api/platform/explorer')) {
      return new Response(JSON.stringify(explorerPayload))
    }
    if (url.endsWith('/api/platform/digests/latest')) {
      return new Response(JSON.stringify(digestPayload))
    }
    if (url.endsWith('/api/platform/gate3/readiness')) {
      return new Response(JSON.stringify(gate3ReadinessPayload))
    }
    if (url.endsWith('/api/platform/gate3/promotions/latest')) {
      return new Response(JSON.stringify(gate3PackagePayload))
    }
    if (url.endsWith('/api/platform/gate3/replay-slippage/latest')) {
      return new Response(JSON.stringify(replaySlippageSummaryPayload))
    }
    if (url.endsWith('/api/platform/gate3/automation/latest')) {
      return new Response(JSON.stringify(marketAutomationPayload))
    }
    if (url.endsWith('/api/platform/gate3/scheduler/state')) {
      return new Response(JSON.stringify(schedulerStatePayload))
    }
    if (url.endsWith('/api/platform/gate3/scheduler/latest')) {
      return new Response(JSON.stringify(schedulerLatestPayload))
    }
    if (url.endsWith('/api/runtime-host/state')) {
      return new Response(JSON.stringify(runtimeStatePayload))
    }
    if (url.endsWith('/api/runtime-host/heartbeat')) {
      return new Response(JSON.stringify(runtimeHeartbeatPayload))
    }
    if (url.endsWith('/api/runtime-host/warmup/latest')) {
      return new Response(JSON.stringify(warmupPayload))
    }
    if (url.endsWith('/api/runtime-host/activation/latest')) {
      return new Response(JSON.stringify(activationPayload))
    }
    if (url.endsWith('/api/runtime-host/model/latest')) {
      return new Response(JSON.stringify(modelSnapshotPayload))
    }
    if (url.endsWith('/api/runtime-host/selection/latest')) {
      return new Response(JSON.stringify(selectionPayload))
    }
    if (url.endsWith('/api/evidence/market_sessions')) {
      return new Response(JSON.stringify(marketSessionsPayload))
    }
    if (url.endsWith('/api/evidence/recovery_drills')) {
      return new Response(JSON.stringify(recoveryDrillsPayload))
    }
    if (url.endsWith('/api/evidence/alert_drills')) {
      return new Response(JSON.stringify(alertDrillsPayload))
    }

    if (url.endsWith('/api/actions/runtime-host/start')) {
      return new Response(
        JSON.stringify({
          action_id: 'action-runtime-start',
          action_type: 'runtime_host_start',
          status: 'accepted',
          message: 'Runtime host started.',
          evidence_refs: [],
        }),
      )
    }

    return new Response('{}', { status: 404 })
  })

  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('App', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('renders the redesigned workspace shell with mission control as the default view', async () => {
    const fetchMock = mockFetch()

    render(<App />)

    expect(await screen.findByText('TradingX Operator Platform')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mission Control' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Portfolio' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Research' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Performance' })).not.toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Mission Control' })).toBeInTheDocument()
    expect(screen.getByText('Bot Heartbeat')).toBeInTheDocument()
    expect(screen.getByText('No trade')).toBeInTheDocument()
    expect(screen.getByText('Runtime Intelligence')).toBeInTheDocument()
    expect(screen.getByText('Runtime Truth')).toBeInTheDocument()
    expect(screen.getByText('Symbol Heartbeat')).toBeInTheDocument()
    expect(screen.getByText('Decision Ladder')).toBeInTheDocument()
    expect(screen.getByText('Operator Guidance')).toBeInTheDocument()
    expect(screen.getByText('Session posture')).toBeInTheDocument()
    expect(screen.getAllByText('SPY')[0]).toBeInTheDocument()
    expect(screen.getAllByText('QQQ')[0]).toBeInTheDocument()
    expect(screen.getAllByText('IWM')[0]).toBeInTheDocument()
    expect(screen.getAllByText('Investigate warmup failure')[0]).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/platform/portfolio',
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
  })

  it('shows a guided portfolio by default, supports analyst mode, and explains metric meaning', async () => {
    const user = userEvent.setup()

    mockFetch()
    render(<App />)

    await screen.findByText('TradingX Operator Platform')

    await user.click(screen.getByRole('button', { name: 'Portfolio' }))

    expect(await screen.findByRole('heading', { name: 'Portfolio' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Guided' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getAllByText('Benchmark comparison waiting for evidence')[0]).toBeInTheDocument()
    expect(
      screen.getByText(
        'TradingX needs a persisted equity history window before benchmark-relative analytics can be trusted.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Evidence provenance')).toBeInTheDocument()
    expect(screen.getAllByText('Live account')[0]).toBeInTheDocument()
    expect(screen.getAllByText('Rehearsal baseline')[0]).toBeInTheDocument()
    expect(screen.getAllByText('Mixed evidence')[0]).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /What this means for Total Equity/i }))

    expect(
      await screen.findByText(
        'The balance is intact. This is good for capital preservation, but it does not yet prove that the strategy can generate risk-adjusted returns.',
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        'The current value is live, but its comparison anchor comes from the saved rehearsal baseline snapshot.',
      ),
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Analyst' }))

    expect(screen.getByRole('button', { name: 'Analyst' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByText('Execution journal is available')).toBeInTheDocument()
    expect(screen.getByText('Reject Count')).toBeInTheDocument()
  })

  it('organizes research and still exposes mission control actions', async () => {
    const fetchMock = mockFetch()
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('TradingX Operator Platform')
    await screen.findAllByText('QQQ')

    expect(screen.getByRole('button', { name: 'Start Bot' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start Bot' }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/actions/runtime-host/start',
        expect.objectContaining({ method: 'POST' }),
      )
    })

    const runtimeStartCall = fetchMock.mock.calls.find(
      ([url]) => url === '/api/actions/runtime-host/start',
    )
    expect(runtimeStartCall).toBeTruthy()
    const runtimeStartInit = runtimeStartCall?.[1] as RequestInit | undefined
    expect(JSON.parse(String(runtimeStartInit?.body))).toMatchObject({
      symbols: ['SPY', 'QQQ', 'IWM'],
      quantity: '1',
      interval_seconds: 180,
      max_cycles: null,
    })

    await user.click(screen.getByRole('button', { name: 'Research' }))

    expect(await screen.findByRole('heading', { name: 'Research' })).toBeInTheDocument()
    expect(screen.getByText('Replay & Audit')).toBeInTheDocument()
    expect(screen.getByText('Evidence Library')).toBeInTheDocument()
    expect(screen.getByText('Gate 1 report')).toBeInTheDocument()
    expect(screen.getAllByText('SPY replay')[0]).toBeInTheDocument()
  })
})
