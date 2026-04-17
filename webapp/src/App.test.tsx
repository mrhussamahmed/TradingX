import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const overviewPayload = {
  generated_at_utc: '2026-04-18T18:00:00+00:00',
  service_status: {
    status: 'running',
    active_symbols: ['SPY', 'QQQ'],
    interval_seconds: 300,
    cycles_completed: 4,
    started_at_utc: '2026-04-18T17:00:00+00:00',
    last_completed_at_utc: '2026-04-18T18:00:00+00:00',
    last_error: '',
  },
  account_summary: {
    cash: '10025.00',
    equity: '10030.00',
    buying_power: '20030.00',
    daily_pnl: '5.00',
  },
  positions: [{ symbol: 'SPY', quantity: '1', market_value: '101.00' }],
  alerts: ['Blocked trade due to stale broker state.'],
  gate_statuses: { '1': 'pass', '2': 'pending' },
  recommendations: { promote_candidate: 1 },
  document_summary: {
    session_count: 3,
    latest_state: 'Operator platform is in progress.',
  },
}

const commandCenterPayload = {
  generated_at_utc: '2026-04-18T18:00:00+00:00',
  service_status: overviewPayload.service_status,
  market_session_label: 'Regular session monitor',
  session_mode: 'intraday',
  account_summary: overviewPayload.account_summary,
  equity_curve: [
    { label: '09:30', value: '10000.00' },
    { label: '10:00', value: '10030.00' },
  ],
  exposure_breakdown: [
    { symbol: 'SPY', value: '65' },
    { symbol: 'QQQ', value: '35' },
  ],
  watchlist: [{ symbol: 'SPY', status: 'active' }],
  gate_statuses: { '1': 'pass', '2': 'pending' },
  recommendations: { promote_candidate: 1 },
  headline_incidents: [{ incident_id: 'incident-alert-1', severity: 'warning' }],
}

const configSummaryPayload = {
  config: {
    web_write_mode_enabled: true,
    symbol_universe: ['SPY', 'QQQ'],
    service_interval_seconds: 300,
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
    preview: 'Operator platform is in progress.',
    kind: 'state',
  },
]

const proposalsPayload = [
  {
    proposal_id: 'proposal-1',
    target_area: 'runtime',
    proposed_values: {},
    diff_preview: '+ TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ',
    output_path: 'config/proposals/proposal-1.md',
  },
]

const incidentsPayload = [
  {
    incident_id: 'incident-alert-1',
    title: 'Blocked trade',
    severity: 'warning',
    status: 'open',
    category: 'risk',
    summary: 'Stale broker state blocked a trade.',
    first_seen_at_utc: '2026-04-18T18:00:00+00:00',
    latest_seen_at_utc: '2026-04-18T18:00:00+00:00',
    acknowledged_at_utc: null,
    acknowledged_by: '',
    related_event_ids: ['event-1'],
    evidence_refs: ['artifacts/paper_loop/operator_alerts/alert-1.json'],
    suggested_action: 'Review broker state freshness.',
  },
]

const researchPayload = {
  generated_at_utc: '2026-04-18T18:00:00+00:00',
  gate_summaries: [{ gate_id: '1', status: 'pass' }],
  candidate_summaries: [
    {
      candidate_id: 'trend-following-v1',
      family: 'trend_following',
      recommendation: 'promote_candidate',
      benchmark_metrics: { sharpe: '1.0' },
      candidate_metrics: { sharpe: '1.4' },
      adversarial_checks: ['fee_stress'],
      gate_statuses: { '1': 'pass' },
      summary: 'Candidate cleared Gate 1.',
    },
  ],
  decision_summary: 'Gate 1 passed.',
}

const replayPayload = {
  replay_id: 'replay-1',
  focus_type: 'symbol',
  focus_value: 'SPY',
  headline: 'SPY replay',
  events: [
    {
      event_id: 'event-1',
      event_type: 'operator_alert',
      symbol: 'SPY',
      severity: 'warning',
      headline: 'Blocked trade',
      details: 'Stale broker state blocked a trade.',
      occurred_at_utc: '2026-04-18T18:00:00+00:00',
      artifact_path: 'artifacts/paper_loop/operator_alerts/alert-1.json',
      related_ids: ['alert-1'],
    },
  ],
  summary: 'Replay ready.',
}

const explorerPayload = [
  {
    record_id: 'record-1',
    category: 'validation_report',
    title: 'Gate 1 report',
    preview: 'Gate 1 passed with benchmark-relative edge.',
    path: 'artifacts/validation/validation_reports/gate-1.json',
    symbol: 'SPY',
    recorded_at_utc: '2026-04-18T18:00:00+00:00',
  },
]

const digestPayload = {
  digest_id: 'digest-1',
  generated_at_utc: '2026-04-18T18:00:00+00:00',
  session_label: 'session_close',
  service_status: 'stopped',
  blocked_trade_count: 1,
  reconciliation_failure_count: 0,
  latest_positions: ['SPY'],
  top_incidents: ['incident-alert-1'],
  recommended_actions: ['Review broker freshness.'],
  evidence_refs: ['artifacts/operator_platform/daily_digests/digest-1.json'],
}

function mockFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (!init?.method || init.method === 'GET') {
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
      if (url.includes('/api/platform/replay')) {
        return new Response(JSON.stringify(replayPayload))
      }
      if (url.includes('/api/platform/explorer')) {
        return new Response(JSON.stringify(explorerPayload))
      }
      if (url.endsWith('/api/platform/digests/latest')) {
        return new Response(JSON.stringify(digestPayload))
      }
      if (url.endsWith('/api/evidence/operator_alerts')) {
        return new Response(JSON.stringify([]))
      }
      if (url.endsWith('/api/evidence/service_cycles')) {
        return new Response(JSON.stringify([]))
      }
      if (url.endsWith('/api/evidence/validation_reports')) {
        return new Response(JSON.stringify([]))
      }
    }

    if (url.endsWith('/api/actions/session/preopen')) {
      return new Response(
        JSON.stringify({
          action_id: 'action-preopen',
          action_type: 'session_preopen',
          status: 'completed',
          message: 'Pre-open checklist captured.',
          evidence_refs: ['artifacts/operator_platform/daily_digests/preopen.json'],
        }),
      )
    }
    if (url.endsWith('/api/actions/session/heartbeat')) {
      return new Response(
        JSON.stringify({
          action_id: 'action-heartbeat',
          action_type: 'session_heartbeat',
          status: 'completed',
          message: 'Heartbeat captured.',
          evidence_refs: ['artifacts/operator_platform/daily_digests/heartbeat.json'],
        }),
      )
    }
    if (url.endsWith('/api/actions/session/close')) {
      return new Response(
        JSON.stringify({
          action_id: 'action-close',
          action_type: 'session_close',
          status: 'completed',
          message: 'Session close digest generated.',
          evidence_refs: ['artifacts/operator_platform/daily_digests/close.json'],
        }),
      )
    }
    if (url.endsWith('/api/actions/incidents/incident-alert-1/acknowledge')) {
      return new Response(
        JSON.stringify({
          action_id: 'action-ack',
          action_type: 'incident_acknowledge',
          status: 'completed',
          message: 'Acknowledged incident-alert-1.',
          evidence_refs: [
            'artifacts/operator_platform/incident_acknowledgements/incident-alert-1.json',
          ],
        }),
      )
    }
    if (url.endsWith('/api/config/proposals')) {
      return new Response(
        JSON.stringify({
          proposal_id: 'proposal-2',
          target_area: 'runtime',
          proposed_values: { TRADINGX_SYMBOL_UNIVERSE: ['SPY', 'QQQ', 'IWM'] },
          diff_preview: '+ TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ,IWM',
          output_path: 'config/proposals/proposal-2.md',
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

  it('renders the operator platform workspace from API data', async () => {
    mockFetch()

    render(<App />)

    expect(await screen.findByText('TradingX Operator Platform')).toBeInTheDocument()
    expect(screen.getByText('Command Center')).toBeInTheDocument()
    expect(screen.getByText('Research Studio')).toBeInTheDocument()
    expect(screen.getByText('Incident Center')).toBeInTheDocument()
    expect(screen.getByText('Replay Lab')).toBeInTheDocument()
    expect(screen.getByText('Settings & Records')).toBeInTheDocument()
    expect(await screen.findByText('Regular session monitor')).toBeInTheDocument()
    expect(screen.getByText('10030.00')).toBeInTheDocument()
  })

  it('navigates operator views and runs bounded operator actions', async () => {
    const fetchMock = mockFetch()
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('TradingX Operator Platform')

    await user.click(screen.getByRole('button', { name: 'Research Studio' }))
    expect(await screen.findByText('trend-following-v1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Incident Center' }))
    expect(await screen.findByText('Stale broker state blocked a trade.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Acknowledge Incident' }))

    await user.click(screen.getByRole('button', { name: 'Replay Lab' }))
    expect(await screen.findByText('SPY replay')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Settings & Records' }))
    await user.type(screen.getByLabelText('Search records'), 'Gate')
    expect(await screen.findByText('Gate 1 report')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Command Center' }))
    await user.click(screen.getByRole('button', { name: 'Session Pre-Open' }))
    await user.click(screen.getByRole('button', { name: 'Session Heartbeat' }))
    await user.click(screen.getByRole('button', { name: 'Session Close' }))

    await user.type(screen.getByLabelText('Target Area'), 'runtime')
    await user.type(screen.getByLabelText('Rationale'), 'Expand the symbol universe.')
    await user.click(screen.getByLabelText('Proposed Values (JSON)'))
    await user.paste('{"TRADINGX_SYMBOL_UNIVERSE":["SPY","QQQ","IWM"]}')
    await user.click(screen.getByRole('button', { name: 'Save Proposal' }))

    await waitFor(() => {
      expect(screen.getAllByText('proposal-2')[0]).toBeInTheDocument()
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/actions/session/preopen',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/actions/session/heartbeat',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/actions/session/close',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/actions/incidents/incident-alert-1/acknowledge',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/config/proposals',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
