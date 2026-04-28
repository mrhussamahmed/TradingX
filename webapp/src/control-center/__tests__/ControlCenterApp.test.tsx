import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { ControlCenterApp } from '../ControlCenterApp'

const blankCommandCenter = {
  generated_at_utc: '2026-04-27T13:30:00Z',
  service_status: {
    status: 'idle',
    active_symbols: [],
    interval_seconds: 300,
    cycles_completed: 0,
    started_at_utc: null,
    last_completed_at_utc: null,
    last_error: '',
  },
  market_session_label: 'pre_open',
  session_mode: 'standby',
  account_summary: { cash: '0', equity: '0', buying_power: '0', daily_pnl: '0' },
  equity_curve: [],
  exposure_breakdown: [],
  watchlist: [{ symbol: 'SPY', status: 'tracking' }],
  gate_statuses: { paper: 'pass', limits: 'pass' },
  recommendations: {},
  headline_incidents: [],
}

const blankConfig = {
  config: {
    web_write_mode_enabled: false,
    web_write_signing_configured: false,
    web_write_max_age_seconds: 300,
    symbol_universe: ['SPY'],
    service_interval_seconds: 300,
    web_refresh_interval_seconds: 15,
  },
  live_disable_report: {
    paper_only_mode: true,
    live_trading_enabled: false,
    manual_kill_switch_active: false,
  },
}

const blankPortfolio = {
  generated_at_utc: '2026-04-27T13:30:00Z',
  source_evidence_at_utc: null,
  trading_mode: 'paper',
  data_state: 'available',
  source_summary: '',
  source_notes: [],
  metric_cards: [],
  equity_curve: { status: 'unavailable', headline: '', detail: '', points: [] },
  benchmark_panel: { status: 'unavailable', headline: '', detail: '', benchmark_rows: [] },
  strategy_panel: { status: 'unavailable', headline: '', detail: '', strategies: [] },
  execution_panel: {
    status: 'unavailable',
    headline: '',
    detail: '',
    summary_metrics: [],
    recent_events: [],
  },
  positions_panel: { status: 'available', headline: 'No open positions', detail: '', positions: [] },
  diagnostics: [],
}

const blankRuntimeState = {
  status: 'idle',
  status_reason: '',
  active_symbols: [],
  started_at_utc: null,
  updated_at_utc: '',
  last_error: '',
  active_strategy_id: '',
  active_model_snapshot_id: '',
  latest_selection_id: '',
}

const blankRuntimeHeartbeat = {
  heartbeat_state: 'Idle',
  heartbeat_summary: '',
  heartbeat_tone: 'neutral',
  cadence_seconds: 60,
  cadence_label: '60s',
  last_evaluation_at_utc: null,
  next_evaluation_at_utc: null,
  last_decision: '',
  decision_reason: '',
  score_explanation: '',
  current_exposure: '',
  current_exposure_detail: '',
  active_symbol: '',
  selected_symbol: '',
  decision: '',
  runtime_truth: [],
  symbol_rows: [],
  decision_ladder: [],
  operator_guidance: null,
}

const blankResearch = {
  generated_at_utc: '',
  gate_summaries: [],
  candidate_summaries: [],
  decision_summary: '',
}

const blankReplay = {
  replay_id: '',
  focus_type: 'symbol',
  focus_value: 'SPY',
  headline: 'Replay unavailable',
  events: [],
  summary: '',
}

const blankGate3 = {
  report_id: '',
  generated_at_utc: '',
  source_evidence_at_utc: null,
  oldest_required_source_evidence_at_utc: null,
  latest_source_evidence_at_utc: null,
  missing_source_criterion_ids: [],
  required_criterion_ids: [],
  status: 'pending',
  closed_trade_count: 0,
  calendar_days_observed: 0,
  criteria: [],
  summary: '',
  required_operator_action: '',
  evidence_refs: [],
}

const blankScheduler = {
  status: 'idle',
  poll_interval_seconds: 60,
  active_symbols: [],
  next_run_at_utc: null,
  last_started_at_utc: null,
  last_completed_at_utc: null,
  active_trading_day: '',
  last_error: '',
}

const ROUTES: Record<string, unknown> = {
  '/api/platform/command-center': blankCommandCenter,
  '/api/config/summary': blankConfig,
  '/api/documents': [],
  '/api/platform/incidents': [],
  '/api/platform/research': blankResearch,
  '/api/platform/portfolio': blankPortfolio,
  '/api/platform/digests/latest': null,
  '/api/platform/gate3/readiness': blankGate3,
  '/api/platform/gate3/promotions/latest': null,
  '/api/runtime-host/state': blankRuntimeState,
  '/api/runtime-host/heartbeat': blankRuntimeHeartbeat,
  '/api/runtime-host/warmup/latest': null,
  '/api/runtime-host/activation/latest': null,
  '/api/runtime-host/model/latest': null,
  '/api/runtime-host/selection/latest': null,
  '/api/runtime-host/decision/latest': null,
  '/api/platform/gate3/scheduler/state': blankScheduler,
}

function setupFetchMock() {
  const fetchSpy = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : (input as URL).toString()
    const path = new URL(url, 'http://localhost').pathname
    const route = path
    let body: unknown = ROUTES[route]
    if (route === '/api/platform/replay') body = blankReplay
    if (route === '/api/platform/explorer') body = []
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => body,
      text: async () => JSON.stringify(body),
      headers: new Headers(),
      url,
      // satisfy minimal Response shape used by api.ts
      clone: () => undefined as unknown as Response,
      body: null,
      bodyUsed: false,
      arrayBuffer: async () => new ArrayBuffer(0),
      blob: async () => new Blob([]),
      formData: async () => new FormData(),
      redirected: false,
      type: 'basic',
    } as unknown as Response
  })
  vi.stubGlobal('fetch', fetchSpy)
  return fetchSpy
}

describe('ControlCenterApp', () => {
  beforeEach(() => {
    window.localStorage.clear()
    setupFetchMock()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    document.documentElement.removeAttribute('data-theme')
    document.documentElement.removeAttribute('data-density')
  })

  it('renders the shell with brand, top strip, left nav, canvas, and operator rail', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByLabelText('TradeX')).toBeInTheDocument()
    })
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByLabelText(/Primary navigation/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Center canvas$/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Operator command rail/i)).toBeInTheDocument()
  })

  it('uses the selected Pulse Route wordmark and matching header glyph', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByLabelText('Pulse Route TradeX wordmark')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Pulse Route TradeX glyph')).toBeInTheDocument()
  })

  it('renders the default Mission Control flavor on first load', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByRole('tab', { selected: true, name: /Mission Control/i })).toBeInTheDocument()
    })
    expect(screen.getAllByText(/Mission Control/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Can the bot trade safely now/i)).toBeInTheDocument()
    expect(screen.getByText(/What needs operator attention/i)).toBeInTheDocument()
    expect(screen.getByText(/Evidence trust ledger/i)).toBeInTheDocument()
  })

  it('does not treat placeholder decision labels as decision evidence', async () => {
    const originalHeartbeat = ROUTES['/api/runtime-host/heartbeat']
    ROUTES['/api/runtime-host/heartbeat'] = {
      ...blankRuntimeHeartbeat,
      last_decision: 'No decision yet',
      decision_reason: 'No opportunity selection has been recorded.',
      last_evaluation_at_utc: '2026-04-27T13:30:00Z',
    }
    try {
      render(<ControlCenterApp />)
      await waitFor(() => {
        expect(screen.getByRole('tab', { selected: true, name: /Mission Control/i })).toBeInTheDocument()
      })
      expect(screen.getByText(/No decision evidence/i)).toBeInTheDocument()
      expect(screen.getByText(/Missing selection-backed decision evidence/i)).toBeInTheDocument()
      expect(screen.getByText(/No structured trade decision is available/i)).toBeInTheDocument()
    } finally {
      ROUTES['/api/runtime-host/heartbeat'] = originalHeartbeat
    }
  })

  it('fetches runtime decision detail and uses its source timestamp for Mission Control evidence', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-04-28T12:10:00Z'))
    const originalHeartbeat = ROUTES['/api/runtime-host/heartbeat']
    const originalPortfolio = ROUTES['/api/platform/portfolio']
    const originalGate3 = ROUTES['/api/platform/gate3/readiness']
    const originalDecision = ROUTES['/api/runtime-host/decision/latest']
    ROUTES['/api/runtime-host/heartbeat'] = {
      ...blankRuntimeHeartbeat,
      last_evaluation_at_utc: '2026-04-28T12:00:00Z',
      last_decision: 'selected SPY',
      decision: 'buy',
    }
    ROUTES['/api/platform/portfolio'] = {
      ...blankPortfolio,
      generated_at_utc: '2026-04-28T12:00:00Z',
      source_evidence_at_utc: '2026-04-28T11:58:00Z',
    }
    ROUTES['/api/platform/gate3/readiness'] = {
      ...blankGate3,
      generated_at_utc: '2026-04-28T12:00:00Z',
      oldest_required_source_evidence_at_utc: '2026-04-28T11:57:00Z',
      latest_source_evidence_at_utc: '2026-04-28T11:59:00Z',
      missing_source_criterion_ids: [],
      required_criterion_ids: ['closed_trades'],
      criteria: [
        {
          criterion_id: 'closed_trades',
          status: 'pass',
          threshold: '',
          observed_value: '',
          details: '',
          evidence_refs: [],
          required: true,
          source_evidence_at_utc: '2026-04-28T11:57:00Z',
        },
      ],
    }
    ROUTES['/api/runtime-host/decision/latest'] = {
      selection_id: 'selection-1',
      generated_at_utc: '2026-04-28T12:00:00Z',
      decision_source_at_utc: '2026-04-28T11:56:00Z',
      decision: 'buy',
      decision_reason: 'Score crossed threshold.',
    }

    try {
      const fetchSpy = setupFetchMock()
      render(<ControlCenterApp />)
      await waitFor(() => {
        expect(screen.getByRole('tab', { selected: true, name: /Mission Control/i })).toBeInTheDocument()
      })

      expect(fetchSpy).toHaveBeenCalledWith(
        '/api/runtime-host/decision/latest',
        expect.any(Object),
      )
      expect(await screen.findByText(/Decision evidence at .*:56/i)).toBeInTheDocument()
      expect(screen.queryByText(/Missing portfolio evidence/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/Missing gate evidence/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/Missing decision evidence/i)).not.toBeInTheDocument()
    } finally {
      ROUTES['/api/runtime-host/heartbeat'] = originalHeartbeat
      ROUTES['/api/platform/portfolio'] = originalPortfolio
      ROUTES['/api/platform/gate3/readiness'] = originalGate3
      ROUTES['/api/runtime-host/decision/latest'] = originalDecision
    }
  })

  it('keeps decision evidence missing when the decision detail endpoint is unavailable', async () => {
    const originalHeartbeat = ROUTES['/api/runtime-host/heartbeat']
    const originalSelection = ROUTES['/api/runtime-host/selection/latest']
    const originalDecision = ROUTES['/api/runtime-host/decision/latest']
    ROUTES['/api/runtime-host/heartbeat'] = {
      ...blankRuntimeHeartbeat,
      last_evaluation_at_utc: '2026-04-28T12:00:00Z',
      last_decision: 'selected SPY',
      decision: 'buy',
    }
    ROUTES['/api/runtime-host/selection/latest'] = {
      selection_id: 'selection-1',
      generated_at_utc: '2026-04-28T12:00:00Z',
      strategy_id: 'strategy-1',
      model_snapshot_id: 'model-1',
      symbols_considered: ['SPY'],
      ranked_opportunities: [],
      selected_symbol: 'SPY',
      decision: 'buy',
      decision_reason: 'Score crossed threshold.',
    }
    ROUTES['/api/runtime-host/decision/latest'] = null

    try {
      render(<ControlCenterApp />)
      await waitFor(() => {
        expect(screen.getByRole('tab', { selected: true, name: /Mission Control/i })).toBeInTheDocument()
      })

      expect(screen.getByText(/No decision evidence/i)).toBeInTheDocument()
      expect(screen.getByText(/Missing selection-backed decision evidence/i)).toBeInTheDocument()
      expect(screen.getAllByText(/Missing .*decision evidence/i).length).toBeGreaterThan(0)
    } finally {
      ROUTES['/api/runtime-host/heartbeat'] = originalHeartbeat
      ROUTES['/api/runtime-host/selection/latest'] = originalSelection
      ROUTES['/api/runtime-host/decision/latest'] = originalDecision
    }
  })

  it('uses required safety evidence gaps in both freshness card and ledger', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByRole('tab', { selected: true, name: /Mission Control/i })).toBeInTheDocument()
    })

    expect(
      screen.getAllByText(/Missing heartbeat evidence, gate evidence, portfolio evidence, decision evidence/i),
    ).toHaveLength(2)
  })

  it('switches flavors via the canvas switcher and marks manual override', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByRole('tab', { selected: true, name: /Mission Control/i })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('tab', { name: /Risk & Safety/i }))
    await waitFor(() => {
      expect(screen.getByRole('tab', { selected: true, name: /Risk & Safety/i })).toBeInTheDocument()
    })
    expect(screen.getByText(/Manual view override active/i)).toBeInTheDocument()
  })

  it('shows the system defaults hint when nothing is stored', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(
        screen.getByText(/Using system view defaults\. Open View Settings to customize and persist\./i),
      ).toBeInTheDocument()
    })
  })

  it('uses trader-intent navigation labels instead of internal architecture labels', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByLabelText(/Primary navigation/i)).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /What is happening now/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Why did it happen/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Can I trust it/i })).toBeInTheDocument()
  })

  it('opens the view defaults drawer with operator-first flavors and density options', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /View Settings/i })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /View Settings/i }))
    expect(screen.getByRole('dialog', { name: /View Defaults/i })).toBeInTheDocument()
    const select = screen.getByLabelText(/Default startup view/i) as HTMLSelectElement
    expect(Array.from(select.options).map((option) => option.value)).toEqual([
      'mission-control',
      'market-chart',
      'strategy-forge',
      'market-day-ops',
      'risk-core',
      'portfolio-constellation',
      'evidence-replay',
    ])
    expect(screen.getByRole('button', { name: 'Compact' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cinematic' })).toBeInTheDocument()
  })

  it('keeps emergency commands visible at all times', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Kill Switch/i })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /Flatten All/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Resume Runtime/i })).toBeInTheDocument()
  })

  it('opens the kill switch dialog and requires the typed phrase', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Kill Switch/i })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /Kill Switch/i }))
    expect(screen.getByRole('alertdialog', { name: /Activate Kill Switch/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/Type KILL TRADINGX/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Activate Kill Switch/i })).toBeDisabled()
  })

  it('disables Resume Runtime with a clear blocker when writes are locked', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1600 })
    window.dispatchEvent(new Event('resize'))
    render(<ControlCenterApp />)
    const button = await screen.findByRole('button', {
      name: /Resume Runtime/i,
    })
    expect(button).toBeDisabled()
    expect(button.textContent ?? '').toMatch(/server write mode is disabled/i)
  })

  it('persists default flavor when saved and reloads from localStorage', async () => {
    render(<ControlCenterApp />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /View Settings/i })).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: /View Settings/i }))
    fireEvent.change(screen.getByLabelText(/Default startup view/i), {
      target: { value: 'risk-core' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save Defaults' }))
    expect(await screen.findByText(/Saved defaults — startup view: Risk & Safety\./i)).toBeInTheDocument()
    expect(window.localStorage.getItem('tradingx.viewFlavor.preferences')).not.toBeNull()
    const stored = JSON.parse(window.localStorage.getItem('tradingx.viewFlavor.preferences')!)
    expect(stored.defaultFlavor).toBe('risk-core')
  })
})
