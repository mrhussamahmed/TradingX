import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const overviewPayload = {
  generated_at_utc: '2026-04-17T18:00:00+00:00',
  service_status: {
    status: 'running',
    active_symbols: ['SPY', 'QQQ'],
    interval_seconds: 300,
    cycles_completed: 4,
    started_at_utc: '2026-04-17T17:00:00+00:00',
    last_completed_at_utc: '2026-04-17T18:00:00+00:00',
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
    latest_state: 'Gate 3 evidence collection is in progress.',
  },
}

const configSummaryPayload = {
  config: {
    web_write_mode_enabled: true,
    symbol_universe: ['SPY', 'QQQ'],
    service_interval_seconds: 300,
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
    preview: 'Gate 3 evidence collection is in progress.',
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

const serviceCyclesPayload = [
  { cycle_id: 'cycle-1', cycle_status: 'executed', symbols: ['SPY', 'QQQ'] },
]

const alertsPayload = [
  { alert_id: 'alert-1', summary: 'Blocked trade due to stale broker state.' },
]

const validationPayload = [
  { report_id: 'gate-1', gate_id: '1', status: 'pass', summary: 'Gate 1 passed.' },
]

function mockFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (!init?.method || init.method === 'GET') {
      if (url.endsWith('/api/overview')) {
        return new Response(JSON.stringify(overviewPayload))
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
      if (url.endsWith('/api/evidence/service_cycles')) {
        return new Response(JSON.stringify(serviceCyclesPayload))
      }
      if (url.endsWith('/api/evidence/operator_alerts')) {
        return new Response(JSON.stringify(alertsPayload))
      }
      if (url.endsWith('/api/evidence/validation_reports')) {
        return new Response(JSON.stringify(validationPayload))
      }
    }

    if (url.endsWith('/api/actions/paper-loop')) {
      return new Response(
        JSON.stringify({
          status: 'completed',
          message: 'Ran a paper trading cycle for SPY.',
        }),
      )
    }
    if (url.endsWith('/api/actions/service/start')) {
      return new Response(
        JSON.stringify({
          status: 'accepted',
          message: 'Paper service started.',
        }),
      )
    }
    if (url.endsWith('/api/actions/service/stop')) {
      return new Response(
        JSON.stringify({
          status: 'accepted',
          message: 'Paper service stop requested.',
        }),
      )
    }
    if (url.endsWith('/api/actions/recover')) {
      return new Response(
        JSON.stringify({
          status: 'completed',
          message: 'Recovery check completed for SPY.',
        }),
      )
    }
    if (url.endsWith('/api/config/proposals')) {
      return new Response(
        JSON.stringify({
          proposal_id: 'proposal-2',
          diff_preview: '+ TRADINGX_SYMBOL_UNIVERSE=SPY,QQQ,IWM',
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

  it('renders the operator dashboard from API data', async () => {
    mockFetch()

    render(<App />)

    expect(await screen.findByText('TradingX Control Center')).toBeInTheDocument()
    expect(await screen.findByText('running')).toBeInTheDocument()
    expect(screen.getByText('Operations Deck')).toBeInTheDocument()
    expect(screen.getByText('Evidence Radar')).toBeInTheDocument()
    expect(screen.getByText('Project Intelligence')).toBeInTheDocument()
    expect(screen.getByText('Proposal Studio')).toBeInTheDocument()
    expect(screen.getByText('10030.00')).toBeInTheDocument()
    expect(
      screen.getAllByText('Gate 3 evidence collection is in progress.')[0],
    ).toBeInTheDocument()
  })

  it('runs local actions, switches evidence tabs, and submits a proposal', async () => {
    const fetchMock = mockFetch()
    const user = userEvent.setup()

    render(<App />)

    await screen.findByText('running')

    await user.click(screen.getByRole('button', { name: 'Run One Cycle' }))
    await user.click(screen.getByRole('button', { name: 'Start Service' }))
    await user.click(screen.getByRole('button', { name: 'Stop Service' }))
    await user.click(screen.getByRole('button', { name: 'Recover' }))
    await user.click(screen.getByRole('button', { name: 'Validation Reports' }))

    await waitFor(() => {
      expect(screen.getByText('Gate 1 passed.')).toBeInTheDocument()
    })

    await user.type(screen.getByLabelText('Target Area'), 'runtime')
    await user.type(
      screen.getByLabelText('Rationale'),
      'Expand the symbol universe for the next session.',
    )
    await user.click(screen.getByLabelText('Proposed Values (JSON)'))
    await user.paste('{"TRADINGX_SYMBOL_UNIVERSE":["SPY","QQQ","IWM"]}')
    await user.click(screen.getByRole('button', { name: 'Save Proposal' }))

    await waitFor(() => {
      expect(screen.getAllByText('proposal-2')[0]).toBeInTheDocument()
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/actions/paper-loop',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/actions/service/start',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/actions/service/stop',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/actions/recover',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/config/proposals',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
