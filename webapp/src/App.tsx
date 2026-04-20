import {
  Suspense,
  lazy,
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'

import './App.css'
import {
  getCommandCenter,
  getConfigSummary,
  getDocuments,
  getExplorer,
  getGate3PromotionPackage,
  getGate3Readiness,
  getIncidents,
  getLatestDigest,
  getPortfolioWorkspace,
  getReplay,
  getResearch,
  getRuntimeHostHeartbeat,
  getRuntimeHostActivation,
  getRuntimeHostModel,
  getRuntimeHostSelection,
  getRuntimeHostState,
  getRuntimeHostWarmup,
  postPaperLoop,
  postRecover,
  postRuntimeHostStart,
  postRuntimeHostStop,
  postSessionClose,
  postSessionHeartbeat,
  postSessionPreopen,
} from './api'
import { prettyLabel, formatTimestamp } from './platform/format'
import { Panel, StatusBadge } from './platform/ui'
import type {
  ActionResult,
  BotRuntimeState,
  CommandCenterSnapshot,
  ConfigSummary,
  DailySessionDigest,
  DocumentRecord,
  ExplorerRecord,
  Gate3PromotionPackage,
  Gate3ReadinessReport,
  HistoricalWarmupRecord,
  IncidentRecord,
  ModelWeightSnapshot,
  OpportunitySelectionRecord,
  PortfolioWorkspaceSnapshot,
  ReplaySession,
  ResearchStudioSnapshot,
  RuntimeHeartbeatSnapshot,
  StrategyActivationRecord,
} from './types'

type WorkspaceKey = 'mission' | 'portfolio' | 'research'
type PortfolioMode = 'guided' | 'analyst'

const MissionControlWorkspace = lazy(async () => {
  const module = await import('./platform/mission-control')
  return { default: module.MissionControlWorkspace }
})

const PortfolioWorkspace = lazy(async () => {
  const module = await import('./platform/portfolio')
  return { default: module.PortfolioWorkspace }
})

const ResearchWorkspace = lazy(async () => {
  const module = await import('./platform/research')
  return { default: module.ResearchWorkspace }
})

const workspaceOptions: Array<{ key: WorkspaceKey; label: string }> = [
  { key: 'mission', label: 'Mission Control' },
  { key: 'portfolio', label: 'Portfolio' },
  { key: 'research', label: 'Research' },
]

const defaultCommandCenter: CommandCenterSnapshot = {
  generated_at_utc: '',
  service_status: {
    status: 'idle',
    active_symbols: [],
    interval_seconds: 300,
    cycles_completed: 0,
    started_at_utc: null,
    last_completed_at_utc: null,
    last_error: '',
  },
  market_session_label: 'Local operator monitor',
  session_mode: 'standby',
  account_summary: {
    cash: '',
    equity: '',
    buying_power: '',
    daily_pnl: '',
  },
  equity_curve: [],
  exposure_breakdown: [],
  watchlist: [],
  gate_statuses: {},
  recommendations: {},
  headline_incidents: [],
}

const defaultConfigSummary: ConfigSummary = {
  config: {
    web_write_mode_enabled: false,
    symbol_universe: [],
    service_interval_seconds: 300,
    web_refresh_interval_seconds: 15,
  },
  live_disable_report: {
    paper_only_mode: true,
    live_trading_enabled: false,
    manual_kill_switch_active: false,
  },
}

const defaultResearch: ResearchStudioSnapshot = {
  generated_at_utc: '',
  gate_summaries: [],
  candidate_summaries: [],
  decision_summary: 'No research summary available yet.',
}

const defaultReplay: ReplaySession = {
  replay_id: '',
  focus_type: 'symbol',
  focus_value: 'SPY',
  headline: 'Replay unavailable',
  events: [],
  summary: 'Replay is waiting for the first recorded event.',
}

const defaultPortfolio: PortfolioWorkspaceSnapshot = {
  generated_at_utc: '',
  trading_mode: 'paper',
  data_state: 'waiting',
  source_summary: 'Portfolio analytics are loading.',
  source_notes: [],
  metric_cards: [],
  equity_curve: {
    status: 'unavailable',
    headline: 'No real TradingX equity curve yet',
    detail: 'The portfolio curve will appear after at least one timestamped service cycle is recorded.',
    points: [],
  },
  benchmark_panel: {
    status: 'unavailable',
    headline: 'Benchmark comparison waiting for evidence',
    detail: 'TradingX needs a persisted equity history window before benchmark-relative analytics can be trusted.',
    benchmark_rows: [],
  },
  strategy_panel: {
    status: 'unavailable',
    headline: 'Strategy attribution waiting for closed-trade evidence',
    detail: 'Strategy contribution will unlock after TradingX records closed trades and realized P&L.',
    strategies: [],
  },
  execution_panel: {
    status: 'unavailable',
    headline: 'Execution journal is waiting for events',
    detail: 'The OMS journal has not recorded any local order activity yet.',
    summary_metrics: [],
    recent_events: [],
  },
  positions_panel: {
    status: 'available',
    headline: 'No open positions',
    detail: 'The account is flat right now.',
    positions: [],
  },
  diagnostics: [],
}

const defaultGate3Readiness: Gate3ReadinessReport = {
  report_id: '',
  generated_at_utc: '',
  status: 'pending',
  closed_trade_count: 0,
  calendar_days_observed: 0,
  criteria: [],
  summary: 'Gate 3 evidence is not available yet.',
  required_operator_action: 'Build paper evidence before evaluating promotion.',
  evidence_refs: [],
}

const defaultRuntimeState: BotRuntimeState = {
  status: 'idle',
  status_reason: 'Runtime host is idle.',
  active_symbols: [],
  started_at_utc: null,
  updated_at_utc: '',
  last_error: '',
  active_strategy_id: '',
  active_model_snapshot_id: '',
  latest_selection_id: '',
}

const defaultRuntimeHeartbeat: RuntimeHeartbeatSnapshot = {
  heartbeat_state: 'Idle',
  heartbeat_summary: 'The runtime host is not currently active.',
  heartbeat_tone: 'neutral',
  cadence_seconds: 180,
  cadence_label: 'Every 3m',
  last_evaluation_at_utc: null,
  next_evaluation_at_utc: null,
  last_decision: 'No decision yet',
  decision_reason: 'TradingX has not recorded an opportunity selection yet.',
  score_explanation: 'No scored candidate has been recorded yet.',
  current_exposure: 'Flat',
  current_exposure_detail: 'No open position is currently held in the paper account.',
  active_symbol: '',
  selected_symbol: '',
  decision: '',
  runtime_truth: [],
  symbol_rows: [],
  decision_ladder: [],
  operator_guidance: null,
}

function App() {
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceKey>('mission')
  const [portfolioMode, setPortfolioMode] = useState<PortfolioMode>('guided')
  const [commandCenter, setCommandCenter] =
    useState<CommandCenterSnapshot>(defaultCommandCenter)
  const [configSummary, setConfigSummary] =
    useState<ConfigSummary>(defaultConfigSummary)
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [incidents, setIncidents] = useState<IncidentRecord[]>([])
  const [research, setResearch] = useState<ResearchStudioSnapshot>(defaultResearch)
  const [replay, setReplay] = useState<ReplaySession>(defaultReplay)
  const [explorer, setExplorer] = useState<ExplorerRecord[]>([])
  const [digest, setDigest] = useState<DailySessionDigest | null>(null)
  const [portfolio, setPortfolio] =
    useState<PortfolioWorkspaceSnapshot>(defaultPortfolio)
  const [gate3Readiness, setGate3Readiness] =
    useState<Gate3ReadinessReport>(defaultGate3Readiness)
  const [gate3Package, setGate3Package] =
    useState<Gate3PromotionPackage | null>(null)
  const [runtimeState, setRuntimeState] =
    useState<BotRuntimeState>(defaultRuntimeState)
  const [runtimeWarmup, setRuntimeWarmup] =
    useState<HistoricalWarmupRecord | null>(null)
  const [runtimeHeartbeat, setRuntimeHeartbeat] =
    useState<RuntimeHeartbeatSnapshot>(defaultRuntimeHeartbeat)
  const [runtimeActivation, setRuntimeActivation] =
    useState<StrategyActivationRecord | null>(null)
  const [runtimeModel, setRuntimeModel] =
    useState<ModelWeightSnapshot | null>(null)
  const [runtimeSelection, setRuntimeSelection] =
    useState<OpportunitySelectionRecord | null>(null)
  const [pageError, setPageError] = useState('')
  const [isBooting, setIsBooting] = useState(true)
  const [actionFeed, setActionFeed] = useState<ActionResult[]>([])

  const activeSymbols = useMemo(
    () => commandCenter.watchlist.map((item) => item.symbol),
    [commandCenter.watchlist],
  )

  const refreshWorkspace = useCallback(async () => {
    try {
      const [
        nextCommandCenter,
        nextConfigSummary,
        nextDocuments,
        nextIncidents,
        nextResearch,
        nextReplay,
        nextExplorer,
        nextDigest,
        nextPortfolio,
        nextGate3Readiness,
        nextGate3Package,
        nextRuntimeState,
        nextRuntimeHeartbeat,
        nextRuntimeWarmup,
        nextRuntimeActivation,
        nextRuntimeModel,
        nextRuntimeSelection,
      ] = await Promise.all([
        getCommandCenter(),
        getConfigSummary(),
        getDocuments(),
        getIncidents(),
        getResearch(),
        getReplay({ symbol: 'SPY' }),
        getExplorer({ query: '', category: undefined }),
        getLatestDigest(),
        getPortfolioWorkspace(),
        getGate3Readiness(),
        getGate3PromotionPackage(),
        getRuntimeHostState(),
        getRuntimeHostHeartbeat(),
        getRuntimeHostWarmup(),
        getRuntimeHostActivation(),
        getRuntimeHostModel(),
        getRuntimeHostSelection(),
      ])

      startTransition(() => {
        setCommandCenter(nextCommandCenter)
        setConfigSummary(nextConfigSummary)
        setDocuments(nextDocuments)
        setIncidents(nextIncidents)
        setResearch(nextResearch)
        setReplay(nextReplay)
        setExplorer(nextExplorer)
        setDigest(nextDigest)
        setPortfolio(nextPortfolio)
        setGate3Readiness(nextGate3Readiness)
        setGate3Package(nextGate3Package)
        setRuntimeState(nextRuntimeState)
        setRuntimeHeartbeat(nextRuntimeHeartbeat)
        setRuntimeWarmup(nextRuntimeWarmup)
        setRuntimeActivation(nextRuntimeActivation)
        setRuntimeModel(nextRuntimeModel)
        setRuntimeSelection(nextRuntimeSelection)
      })
      setPageError('')
    } catch (error) {
      setPageError(
        error instanceof Error ? error.message : 'Unable to load the operator platform.',
      )
    } finally {
      setIsBooting(false)
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void refreshWorkspace()
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [refreshWorkspace])

  useEffect(() => {
    const refreshSeconds = Math.max(
      5,
      Number(configSummary.config.web_refresh_interval_seconds || 15),
    )
    const intervalId = window.setInterval(() => {
      void refreshWorkspace()
    }, refreshSeconds * 1000)
    return () => {
      window.clearInterval(intervalId)
    }
  }, [configSummary.config.web_refresh_interval_seconds, refreshWorkspace])

  function pushAction(
    action: Partial<ActionResult> & {
      message: string
      action_type?: string
      status?: string
    },
  ) {
    startTransition(() => {
      setActionFeed((current) => [
        {
          action_id: action.action_id ?? `ui-${Date.now()}`,
          action_type: action.action_type ?? 'ui_feedback',
          status: action.status ?? 'completed',
          message: action.message,
          evidence_refs: action.evidence_refs ?? [],
        },
        ...current,
      ].slice(0, 6))
    })
  }

  async function runAction(request: () => Promise<ActionResult>) {
    try {
      const result = await request()
      pushAction(result)
      await refreshWorkspace()
    } catch (error) {
      pushAction({
        action_type: 'ui_feedback',
        status: 'failed',
        message: error instanceof Error ? error.message : 'Action failed unexpectedly.',
      })
    }
  }

  return (
    <main className="operator-app">
      <div className="operator-background" aria-hidden="true" />

      <header className="topbar">
        <div className="topbar-copy">
          <p className="eyebrow">Carbon / Steel operator console</p>
          <h1>TradingX Operator Platform</h1>
          <p className="hero-summary">
            Supervise the runtime, understand portfolio truth, and inspect evidence without guessing what is real.
          </p>
        </div>

        <div className="topbar-status">
          <StatusBadge
            label={prettyLabel(runtimeState.status)}
            tone={runtimeState.status === 'halted' ? 'watch' : 'good'}
          />
          <StatusBadge
            label={configSummary.live_disable_report.paper_only_mode ? 'Paper only' : 'Check mode'}
            tone="info"
          />
          <StatusBadge
            label={configSummary.config.web_write_mode_enabled ? 'Write mode on' : 'Read only'}
            tone={configSummary.config.web_write_mode_enabled ? 'good' : 'neutral'}
          />
          <span className="timestamp-label">
            Updated {formatTimestamp(portfolio.generated_at_utc || commandCenter.generated_at_utc)}
          </span>
        </div>
      </header>

      {pageError ? <div className="error-banner">{pageError}</div> : null}

      <section className="workspace-shell">
        <aside className="workspace-rail">
          <nav className="workspace-nav" aria-label="Workspace navigation">
            {workspaceOptions.map((option) => (
              <button
                key={option.key}
                type="button"
                className={option.key === activeWorkspace ? 'workspace-tab active' : 'workspace-tab'}
                onClick={() => setActiveWorkspace(option.key)}
              >
                {option.label}
              </button>
            ))}
          </nav>

          <Panel title="Desk Snapshot" eyebrow="Fast scan">
            <div className="rail-stat-list">
              <div className="rail-stat">
                <span>Symbols</span>
                <strong>{activeSymbols.join(', ') || 'SPY only'}</strong>
              </div>
              <div className="rail-stat">
                <span>Digest</span>
                <strong>{digest ? prettyLabel(digest.session_label) : 'Waiting'}</strong>
              </div>
              <div className="rail-stat">
                <span>Incidents</span>
                <strong>{String(incidents.length)}</strong>
              </div>
              <div className="rail-stat">
                <span>Portfolio data</span>
                <strong>{prettyLabel(portfolio.data_state)}</strong>
              </div>
            </div>
          </Panel>

          <Panel title="Recent Actions" eyebrow="Operator feedback">
            <div className="stack-list">
              {actionFeed.length ? (
                actionFeed.map((action) => (
                  <article key={action.action_id} className="list-card compact">
                    <div className="list-card-header">
                      <strong>{prettyLabel(action.action_type)}</strong>
                      <StatusBadge
                        label={prettyLabel(action.status)}
                        tone={action.status === 'failed' ? 'risk' : 'info'}
                      />
                    </div>
                    <p>{action.message}</p>
                  </article>
                ))
              ) : (
                <div className="empty-state">
                  <strong>No actions yet</strong>
                  <p>Run a bounded control action and the result will appear here.</p>
                </div>
              )}
            </div>
          </Panel>

          <Panel title="Safety Frame" eyebrow="Hard boundaries">
            <div className="stack-list">
              <article className="list-card compact">
                <div className="list-card-header">
                  <strong>Trading mode</strong>
                  <span>{configSummary.live_disable_report.paper_only_mode ? 'Paper only' : 'Live check'}</span>
                </div>
                <p>Local controls should remain conservative until evidence quality improves.</p>
              </article>
              <article className="list-card compact">
                <div className="list-card-header">
                  <strong>Kill switch</strong>
                  <span>{configSummary.live_disable_report.manual_kill_switch_active ? 'Active' : 'Inactive'}</span>
                </div>
                <p>Manual emergency posture remains visible at all times.</p>
              </article>
            </div>
          </Panel>
        </aside>

        <section className="workspace-stage">
          {isBooting ? <div className="boot-state">Loading operator platform…</div> : null}

          <Suspense fallback={<div className="boot-state">Loading workspace…</div>}>
            {activeWorkspace === 'mission' ? (
              <MissionControlWorkspace
                commandCenter={commandCenter}
                configSummary={configSummary}
                digest={digest}
                documents={documents}
                incidents={incidents}
                runtimeState={runtimeState}
                runtimeHeartbeat={runtimeHeartbeat}
                runtimeWarmup={runtimeWarmup}
                runtimeActivation={runtimeActivation}
                runtimeModel={runtimeModel}
                runtimeSelection={runtimeSelection}
                onRunPaperLoop={() => runAction(() => postPaperLoop({ symbol: 'SPY', quantity: '1' }))}
                onStartBot={() =>
                  runAction(() =>
                    postRuntimeHostStart({
                      symbols: configSummary.config.symbol_universe.length
                        ? configSummary.config.symbol_universe
                        : ['SPY'],
                      quantity: '1',
                      interval_seconds: Number(configSummary.config.service_interval_seconds || 300),
                      max_cycles: null,
                    }),
                  )
                }
                onStopBot={() => runAction(() => postRuntimeHostStop())}
                onRecover={() => runAction(() => postRecover({ symbol: 'SPY' }))}
                onSessionPreopen={() => runAction(() => postSessionPreopen())}
                onSessionHeartbeat={() => runAction(() => postSessionHeartbeat())}
                onSessionClose={() => runAction(() => postSessionClose())}
              />
            ) : null}

            {activeWorkspace === 'portfolio' ? (
              <PortfolioWorkspace
                portfolio={portfolio}
                mode={portfolioMode}
                onModeChange={setPortfolioMode}
              />
            ) : null}

            {activeWorkspace === 'research' ? (
              <ResearchWorkspace
                research={research}
                replay={replay}
                explorer={explorer}
                documents={documents}
                digest={digest}
                gate3Readiness={gate3Readiness}
                gate3Package={gate3Package}
              />
            ) : null}
          </Suspense>
        </section>
      </section>
    </main>
  )
}

export default App
