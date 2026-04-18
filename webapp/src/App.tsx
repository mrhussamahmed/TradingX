import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useMemo,
  useState,
} from 'react'
import type { ReactNode } from 'react'

import './App.css'
import {
  getAlertDrills,
  getCommandCenter,
  getConfigProposals,
  getConfigSummary,
  getDocuments,
  getExplorer,
  getGate3PromotionPackage,
  getGate3Readiness,
  getLatestDigest,
  getMarketAutomationRun,
  getMarketSessions,
  getReplaySlippageSummary,
  getRecoveryDrills,
  getIncidents,
  getOverview,
  getReplay,
  getResearch,
  postAcknowledgeIncident,
  postAlertDrill,
  postDecisionReport,
  postGateReport,
  postGate3Package,
  postGate3Report,
  postMarketDayAutomation,
  postPaperLoop,
  postPrepareBenchmark,
  postProposal,
  postReplaySlippageReport,
  postRecover,
  postRecoveryDrill,
  postServiceStart,
  postServiceStop,
  postSessionClose,
  postSessionHeartbeat,
  postSessionPreopen,
} from './api'
import type {
  ActionResult,
  AlertDrillRecord,
  CommandCenterSnapshot,
  ConfigProposal,
  ConfigSummary,
  DailySessionDigest,
  DashboardSnapshot,
  DocumentRecord,
  ExplorerRecord,
  Gate3PromotionPackage,
  Gate3ReadinessReport,
  IncidentRecord,
  MarketAutomationRunRecord,
  MarketSessionRecord,
  ReplaySlippageSummary,
  ReplaySession,
  RecoveryDrillRecord,
  ResearchStudioSnapshot,
} from './types'

type ViewKey =
  | 'command'
  | 'trade'
  | 'research'
  | 'gate3'
  | 'incidents'
  | 'replay'
  | 'records'

const defaultOverview: DashboardSnapshot = {
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
  account_summary: {
    cash: '',
    equity: '',
    buying_power: '',
    daily_pnl: '',
  },
  positions: [],
  alerts: [],
  gate_statuses: {},
  recommendations: {},
  document_summary: {},
}

const defaultCommandCenter: CommandCenterSnapshot = {
  generated_at_utc: '',
  service_status: defaultOverview.service_status,
  market_session_label: 'Local operator monitor',
  session_mode: 'standby',
  account_summary: defaultOverview.account_summary,
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
  decision_summary: '',
}

const defaultGate3Readiness: Gate3ReadinessReport = {
  report_id: '',
  generated_at_utc: '',
  status: 'pending',
  closed_trade_count: 0,
  calendar_days_observed: 0,
  criteria: [],
  summary: 'No Gate 3 readiness report is available yet.',
  required_operator_action: 'Generate a Gate 3 report to begin the evidence trail.',
  evidence_refs: [],
}

const defaultReplay: ReplaySession = {
  replay_id: '',
  focus_type: 'symbol',
  focus_value: 'SPY',
  headline: 'Replay unavailable',
  events: [],
  summary: 'No replayable data is available yet.',
}

const defaultReplaySlippageSummary: ReplaySlippageSummary | null = null
const defaultMarketAutomationRun: MarketAutomationRunRecord | null = null

const viewOptions: Array<{ key: ViewKey; label: string; shortcut: string }> = [
  { key: 'command', label: 'Command Center', shortcut: '1' },
  { key: 'trade', label: 'Trade Intelligence', shortcut: '2' },
  { key: 'research', label: 'Research Studio', shortcut: '3' },
  { key: 'gate3', label: 'Gate 3 Ops', shortcut: '4' },
  { key: 'incidents', label: 'Incident Center', shortcut: '5' },
  { key: 'replay', label: 'Replay Lab', shortcut: '6' },
  { key: 'records', label: 'Settings & Records', shortcut: '7' },
]

function App() {
  const [activeView, setActiveView] = useState<ViewKey>('command')
  const [overview, setOverview] = useState<DashboardSnapshot>(defaultOverview)
  const [commandCenter, setCommandCenter] =
    useState<CommandCenterSnapshot>(defaultCommandCenter)
  const [configSummary, setConfigSummary] =
    useState<ConfigSummary>(defaultConfigSummary)
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [proposals, setProposals] = useState<ConfigProposal[]>([])
  const [incidents, setIncidents] = useState<IncidentRecord[]>([])
  const [research, setResearch] =
    useState<ResearchStudioSnapshot>(defaultResearch)
  const [gate3Readiness, setGate3Readiness] =
    useState<Gate3ReadinessReport>(defaultGate3Readiness)
  const [gate3Package, setGate3Package] =
    useState<Gate3PromotionPackage | null>(null)
  const [replaySlippageSummary, setReplaySlippageSummary] =
    useState<ReplaySlippageSummary | null>(defaultReplaySlippageSummary)
  const [marketAutomationRun, setMarketAutomationRun] =
    useState<MarketAutomationRunRecord | null>(defaultMarketAutomationRun)
  const [marketSessions, setMarketSessions] = useState<MarketSessionRecord[]>([])
  const [recoveryDrills, setRecoveryDrills] = useState<RecoveryDrillRecord[]>([])
  const [alertDrills, setAlertDrills] = useState<AlertDrillRecord[]>([])
  const [replay, setReplay] = useState<ReplaySession>(defaultReplay)
  const [explorer, setExplorer] = useState<ExplorerRecord[]>([])
  const [digest, setDigest] = useState<DailySessionDigest | null>(null)
  const [actionFeed, setActionFeed] = useState<ActionResult[]>([])
  const [pageError, setPageError] = useState('')
  const [isBooting, setIsBooting] = useState(true)
  const [paletteOpen, setPaletteOpen] = useState(false)

  const [serviceSymbols, setServiceSymbols] = useState('SPY,QQQ')
  const [serviceQuantity, setServiceQuantity] = useState('1')
  const [serviceIntervalSeconds, setServiceIntervalSeconds] = useState('300')
  const [marketDayHeartbeats, setMarketDayHeartbeats] = useState('2')
  const [loopSymbol, setLoopSymbol] = useState('SPY')
  const [loopQuantity, setLoopQuantity] = useState('1')
  const [recoverSymbol, setRecoverSymbol] = useState('SPY')
  const [benchmarkSymbol, setBenchmarkSymbol] = useState('SPY')
  const [benchmarkWindowStart, setBenchmarkWindowStart] = useState('2023-01-01')
  const [benchmarkWindowEnd, setBenchmarkWindowEnd] = useState('2026-04-17')
  const [gateBenchmarkPath, setGateBenchmarkPath] = useState(
    'artifacts/validation/benchmarks/spy.json',
  )
  const [gateWindowStart, setGateWindowStart] = useState('2023-01-01')
  const [gateWindowEnd, setGateWindowEnd] = useState('2026-04-17')
  const [gateUniverse, setGateUniverse] = useState('SPY,QQQ')
  const [gate3RecoverySymbol, setGate3RecoverySymbol] = useState('SPY')
  const [replaySymbol, setReplaySymbol] = useState('SPY')
  const [selectedIncidentId, setSelectedIncidentId] = useState('')
  const [explorerQuery, setExplorerQuery] = useState('')
  const [explorerCategory, setExplorerCategory] = useState('')
  const [proposalTargetArea, setProposalTargetArea] = useState('')
  const [proposalRationale, setProposalRationale] = useState('')
  const [proposalValues, setProposalValues] = useState('')

  const deferredExplorerQuery = useDeferredValue(explorerQuery)
  const writeModeEnabled = configSummary.config.web_write_mode_enabled

  const currentIncident = useMemo(
    () =>
      incidents.find((incident) => incident.incident_id === selectedIncidentId) ??
      incidents[0] ??
      null,
    [incidents, selectedIncidentId],
  )

  const refreshWorkspace = useEffectEvent(async () => {
    try {
      const [
        nextOverview,
        nextCommandCenter,
        nextConfigSummary,
        nextDocuments,
        nextProposals,
        nextIncidents,
        nextResearch,
        nextGate3Readiness,
        nextGate3Package,
        nextReplaySlippageSummary,
        nextMarketAutomationRun,
        nextMarketSessions,
        nextRecoveryDrills,
        nextAlertDrills,
        nextDigest,
      ] = await Promise.all([
        getOverview(),
        getCommandCenter(),
        getConfigSummary(),
        getDocuments(),
        getConfigProposals(),
        getIncidents(),
        getResearch(),
        getGate3Readiness(),
        getGate3PromotionPackage(),
        getReplaySlippageSummary(),
        getMarketAutomationRun(),
        getMarketSessions(),
        getRecoveryDrills(),
        getAlertDrills(),
        getLatestDigest(),
      ])
      startTransition(() => {
        setOverview(nextOverview)
        setCommandCenter(nextCommandCenter)
        setConfigSummary(nextConfigSummary)
        setDocuments(nextDocuments)
        setProposals(nextProposals)
        setIncidents(nextIncidents)
        setResearch(nextResearch)
        setGate3Readiness(nextGate3Readiness)
        setGate3Package(nextGate3Package)
        setReplaySlippageSummary(nextReplaySlippageSummary)
        setMarketAutomationRun(nextMarketAutomationRun)
        setMarketSessions(nextMarketSessions)
        setRecoveryDrills(nextRecoveryDrills)
        setAlertDrills(nextAlertDrills)
        setDigest(nextDigest)
        setSelectedIncidentId((current) => current || nextIncidents[0]?.incident_id || '')
      })
      setPageError('')
    } catch (error) {
      setPageError(
        error instanceof Error
          ? error.message
          : 'Unable to load the operator platform.',
      )
    } finally {
      setIsBooting(false)
    }
  })

  const loadReplayView = useEffectEvent(async () => {
    try {
      const payload = await getReplay({ symbol: replaySymbol })
      startTransition(() => {
        setReplay(payload)
      })
    } catch (error) {
      pushAction({
        action_type: 'replay_refresh',
        status: 'failed',
        message:
          error instanceof Error
            ? error.message
            : 'Unable to refresh replay data.',
      })
    }
  })

  const loadExplorerView = useEffectEvent(async () => {
    try {
      const payload = await getExplorer({
        query: deferredExplorerQuery,
        category: explorerCategory || undefined,
      })
      startTransition(() => {
        setExplorer(payload)
      })
    } catch (error) {
      pushAction({
        action_type: 'explorer_refresh',
        status: 'failed',
        message:
          error instanceof Error
            ? error.message
            : 'Unable to refresh explorer records.',
      })
    }
  })

  useEffect(() => {
    void refreshWorkspace()
    void loadReplayView()
    void loadExplorerView()
  }, [])

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

  useEffect(() => {
    if (activeView === 'trade' || activeView === 'replay') {
      void loadReplayView()
    }
  }, [activeView, replaySymbol, loadReplayView])

  useEffect(() => {
    if (activeView === 'records') {
      void loadExplorerView()
    }
  }, [activeView, deferredExplorerQuery, explorerCategory, loadExplorerView])

  useEffect(() => {
    const handleKeydown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen((current) => !current)
        return
      }
      if (!event.metaKey && !event.ctrlKey && /^[1-7]$/.test(event.key)) {
        const nextView = viewOptions.find((option) => option.shortcut === event.key)
        if (nextView) {
          setActiveView(nextView.key)
        }
      }
      if (event.key === 'Escape') {
        setPaletteOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeydown)
    return () => {
      window.removeEventListener('keydown', handleKeydown)
    }
  }, [])

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
      ].slice(0, 8))
    })
  }

  async function runAction(
    request: () => Promise<ActionResult>,
    options?: { refreshReplay?: boolean; refreshExplorer?: boolean },
  ) {
    try {
      const result = await request()
      pushAction(result)
      await refreshWorkspace()
      if (options?.refreshReplay) {
        await loadReplayView()
      }
      if (options?.refreshExplorer) {
        await loadExplorerView()
      }
    } catch (error) {
      pushAction({
        action_type: 'ui_feedback',
        status: 'failed',
        message:
          error instanceof Error ? error.message : 'Action failed unexpectedly.',
      })
    }
  }

  async function handleProposalSubmit() {
    let parsedValues: Record<string, unknown>
    try {
      parsedValues = JSON.parse(proposalValues) as Record<string, unknown>
    } catch {
      pushAction({
        action_type: 'config_proposal',
        status: 'failed',
        message: 'Proposed Values (JSON) must be valid JSON before saving.',
      })
      return
    }
    try {
      const proposal = await postProposal({
        target_area: proposalTargetArea,
        rationale: proposalRationale,
        proposed_values: parsedValues,
      })
      startTransition(() => {
        setProposals((current) => [proposal, ...current])
        setProposalTargetArea('')
        setProposalRationale('')
        setProposalValues('')
      })
      pushAction({
        action_type: 'config_proposal',
        status: 'completed',
        message: proposal.proposal_id,
      })
    } catch (error) {
      pushAction({
        action_type: 'config_proposal',
        status: 'failed',
        message:
          error instanceof Error ? error.message : 'Unable to save the proposal.',
      })
    }
  }

  return (
    <main className="platform-shell">
      <div className="ambient-orb ambient-orb-a" aria-hidden="true" />
      <div className="ambient-orb ambient-orb-b" aria-hidden="true" />
      <div className="ambient-grid" aria-hidden="true" />
      <header className="masthead">
        <div className="masthead-grid">
          <div className="masthead-copy">
            <p className="eyebrow">Local-only operator workspace</p>
            <h1>TradingX Operator Platform</h1>
            <p className="hero-summary">
              A dense command surface for paper trading supervision, trade
              explainability, incident handling, replay, research, and records.
            </p>
            <div className="hero-ribbon">
              <article className="hero-ribbon-card">
                <span>Mission profile</span>
                <strong>{commandCenter.market_session_label}</strong>
                <p>Paper-only supervision with operator-safe controls.</p>
              </article>
              <article className="hero-ribbon-card">
                <span>Refresh cadence</span>
                <strong>
                  Every {configSummary.config.web_refresh_interval_seconds}s
                </strong>
                <p>
                  {overview.service_status.cycles_completed} cycles recorded in
                  the current service run.
                </p>
              </article>
              <article className="hero-ribbon-card">
                <span>Incident focus</span>
                <strong>{currentIncident?.title || 'Clear board'}</strong>
                <p>
                  {currentIncident?.summary ||
                    'No active incident is dominating the operator deck.'}
                </p>
              </article>
            </div>
          </div>

          <aside className="hero-aside">
            <div className="hero-aside-copy">
              <p className="eyebrow">Operator cadence</p>
              <h2>Run the desk like a control room.</h2>
              <p>
                Shortcuts, status, and intervention points stay visible while
                the dashboards carry the deeper evidence trail.
              </p>
            </div>
            <div className="hero-aside-stack">
              <div className="hero-aside-card">
                <span>Keyboard sweep</span>
                <strong>1-6 views, Cmd/Ctrl+K palette</strong>
              </div>
              <div className="hero-aside-card">
                <span>Write posture</span>
                <strong>{writeModeEnabled ? 'Enabled' : 'Read-only'}</strong>
              </div>
              <div className="hero-aside-card">
                <span>Active scan</span>
                <strong>
                  {overview.service_status.active_symbols.join(', ') || 'No active scan'}
                </strong>
              </div>
            </div>
          </aside>
        </div>

        <div className="masthead-meta">
          <StatusChip label={overview.service_status.status} tone="teal" />
          <StatusChip
            label={
              configSummary.live_disable_report.paper_only_mode
                ? 'paper-only'
                : 'check mode'
            }
            tone="gold"
          />
          <StatusChip
            label={writeModeEnabled ? 'write mode on' : 'read only'}
            tone={writeModeEnabled ? 'ink' : 'fog'}
          />
          <button
            type="button"
            className="palette-button"
            onClick={() => setPaletteOpen(true)}
          >
            Open command palette
          </button>
        </div>

        <div className="hero-metrics">
          <MetricCard label="Equity" value={commandCenter.account_summary.equity} />
          <MetricCard label="Cash" value={commandCenter.account_summary.cash} />
          <MetricCard
            label="Buying Power"
            value={commandCenter.account_summary.buying_power}
          />
          <MetricCard
            label="Daily P&L"
            value={commandCenter.account_summary.daily_pnl}
          />
        </div>
      </header>

      {pageError ? <div className="error-banner">{pageError}</div> : null}

      <div className="workspace-shell">
        <aside className="sidebar">
          <nav className="view-nav" aria-label="Operator views">
            {viewOptions.map((option) => (
              <button
                key={option.key}
                type="button"
                className={option.key === activeView ? 'view-tab active' : 'view-tab'}
                onClick={() => setActiveView(option.key)}
                aria-label={option.label}
              >
                <span>{option.label}</span>
                <strong aria-hidden="true">{option.shortcut}</strong>
              </button>
            ))}
          </nav>

          <Panel title="Session Posture" subtitle="Ops overview">
            <div className="mini-stack">
              <MiniStat label="Mode" value={commandCenter.session_mode} />
              <MiniStat
                label="Active Symbols"
                value={
                  overview.service_status.active_symbols.join(', ') || 'No active scan'
                }
              />
              <MiniStat
                label="Digest"
                value={digest?.session_label.replace('_', ' ') || 'No digest yet'}
              />
            </div>
          </Panel>

          <Panel title="Action Chronicle" subtitle="Recent operator feedback">
            <div className="feed-list">
              {actionFeed.length ? (
                actionFeed.map((action) => (
                  <article key={action.action_id} className="feed-item">
                    <span className={`feed-dot ${action.status}`} />
                    <div>
                      <strong>{action.action_type.replaceAll('_', ' ')}</strong>
                      <p>{action.message}</p>
                    </div>
                  </article>
                ))
              ) : (
                <p className="muted">No actions have been triggered in this session yet.</p>
              )}
            </div>
          </Panel>

          <Panel title="Safety Frame" subtitle="Constitution boundaries in view">
            <div className="safety-list">
              <SafetyRow
                label="Paper-only mode"
                value={
                  configSummary.live_disable_report.paper_only_mode ? 'enabled' : 'check'
                }
              />
              <SafetyRow
                label="Live trading"
                value={
                  configSummary.live_disable_report.live_trading_enabled
                    ? 'enabled'
                    : 'disabled'
                }
              />
              <SafetyRow
                label="Kill switch"
                value={
                  configSummary.live_disable_report.manual_kill_switch_active
                    ? 'active'
                    : 'inactive'
                }
              />
              <SafetyRow
                label="Write mode"
                value={writeModeEnabled ? 'enabled' : 'disabled'}
              />
            </div>
          </Panel>
        </aside>

        <section className="stage">
          {isBooting ? (
            <div className="boot-state">Loading operator platform…</div>
          ) : null}
          {activeView === 'command' ? (
            <CommandCenterView
              commandCenter={commandCenter}
              digest={digest}
              incidents={incidents}
              documents={documents}
              loopSymbol={loopSymbol}
              loopQuantity={loopQuantity}
              recoverSymbol={recoverSymbol}
              serviceSymbols={serviceSymbols}
              serviceQuantity={serviceQuantity}
              serviceIntervalSeconds={serviceIntervalSeconds}
              onLoopSymbolChange={setLoopSymbol}
              onLoopQuantityChange={setLoopQuantity}
              onRecoverSymbolChange={setRecoverSymbol}
              onServiceSymbolsChange={setServiceSymbols}
              onServiceQuantityChange={setServiceQuantity}
              onServiceIntervalChange={setServiceIntervalSeconds}
              onRunPaperLoop={() =>
                runAction(() =>
                  postPaperLoop({ symbol: loopSymbol, quantity: loopQuantity }),
                )
              }
              onStartService={() =>
                runAction(() =>
                  postServiceStart({
                    symbols: serviceSymbols
                      .split(',')
                      .map((value) => value.trim())
                      .filter(Boolean),
                    quantity: serviceQuantity,
                    interval_seconds: Number(serviceIntervalSeconds),
                    max_cycles: 1,
                  }),
                )
              }
              onStopService={() => runAction(() => postServiceStop())}
              onRecover={() =>
                runAction(
                  () => postRecover({ symbol: recoverSymbol }),
                  { refreshReplay: true },
                )
              }
              onSessionPreopen={() => runAction(() => postSessionPreopen())}
              onSessionHeartbeat={() => runAction(() => postSessionHeartbeat())}
              onSessionClose={() =>
                runAction(() => postSessionClose(), { refreshExplorer: true })
              }
              proposalTargetArea={proposalTargetArea}
              proposalRationale={proposalRationale}
              proposalValues={proposalValues}
              onProposalTargetAreaChange={setProposalTargetArea}
              onProposalRationaleChange={setProposalRationale}
              onProposalValuesChange={setProposalValues}
              onProposalSubmit={handleProposalSubmit}
            />
          ) : null}

          {activeView === 'trade' ? (
            <TradeIntelligenceView
              replay={replay}
              positions={overview.positions}
              replaySymbol={replaySymbol}
              onReplaySymbolChange={setReplaySymbol}
            />
          ) : null}

          {activeView === 'research' ? (
            <ResearchStudioView
              research={research}
              benchmarkSymbol={benchmarkSymbol}
              benchmarkWindowStart={benchmarkWindowStart}
              benchmarkWindowEnd={benchmarkWindowEnd}
              gateBenchmarkPath={gateBenchmarkPath}
              gateWindowStart={gateWindowStart}
              gateWindowEnd={gateWindowEnd}
              gateUniverse={gateUniverse}
              onBenchmarkSymbolChange={setBenchmarkSymbol}
              onBenchmarkWindowStartChange={setBenchmarkWindowStart}
              onBenchmarkWindowEndChange={setBenchmarkWindowEnd}
              onGateBenchmarkPathChange={setGateBenchmarkPath}
              onGateWindowStartChange={setGateWindowStart}
              onGateWindowEndChange={setGateWindowEnd}
              onGateUniverseChange={setGateUniverse}
              onPrepareBenchmark={() =>
                runAction(() =>
                  postPrepareBenchmark({
                    symbol: benchmarkSymbol,
                    window_start: benchmarkWindowStart,
                    window_end: benchmarkWindowEnd,
                  }),
                )
              }
              onGenerateGateReport={() =>
                runAction(() =>
                  postGateReport({
                    gate: '1',
                    benchmark_closes_file: gateBenchmarkPath,
                    window_start: gateWindowStart,
                    window_end: gateWindowEnd,
                    universe: gateUniverse
                      .split(',')
                      .map((value) => value.trim())
                      .filter(Boolean),
                  }),
                )
              }
              onGenerateDecisionBrief={() =>
                runAction(() => postDecisionReport({ gate: '1' }))
              }
            />
          ) : null}

          {activeView === 'gate3' ? (
            <Gate3OpsView
              readiness={gate3Readiness}
              promotionPackage={gate3Package}
              replaySlippageSummary={replaySlippageSummary}
              marketAutomationRun={marketAutomationRun}
              marketSessions={marketSessions}
              serviceSymbols={serviceSymbols}
              serviceQuantity={serviceQuantity}
              serviceIntervalSeconds={serviceIntervalSeconds}
              marketDayHeartbeats={marketDayHeartbeats}
              recoveryDrills={recoveryDrills}
              alertDrills={alertDrills}
              recoverySymbol={gate3RecoverySymbol}
              onServiceSymbolsChange={setServiceSymbols}
              onServiceQuantityChange={setServiceQuantity}
              onServiceIntervalChange={setServiceIntervalSeconds}
              onMarketDayHeartbeatsChange={setMarketDayHeartbeats}
              onRecoverySymbolChange={setGate3RecoverySymbol}
              onGenerateGate3Report={() => runAction(() => postGate3Report())}
              onGenerateGate3Package={() => runAction(() => postGate3Package())}
              onGenerateReplaySlippageReport={() =>
                runAction(() => postReplaySlippageReport())
              }
              onRunRecoveryDrill={() =>
                runAction(() => postRecoveryDrill({ symbol: gate3RecoverySymbol }))
              }
              onRunSmtpDrill={() =>
                runAction(() => postAlertDrill({ channel: 'smtp' }))
              }
              onRunMarketDay={() =>
                runAction(() =>
                  postMarketDayAutomation({
                    symbols: serviceSymbols
                      .split(',')
                      .map((value) => value.trim())
                      .filter(Boolean),
                    quantity: serviceQuantity,
                    interval_seconds: Number(serviceIntervalSeconds),
                    max_heartbeats: Number(marketDayHeartbeats),
                  }),
                )
              }
            />
          ) : null}

          {activeView === 'incidents' ? (
            <IncidentCenterView
              incidents={incidents}
              selectedIncidentId={currentIncident?.incident_id ?? ''}
              onSelectIncident={setSelectedIncidentId}
              onAcknowledgeIncident={() =>
                currentIncident
                  ? runAction(() =>
                      postAcknowledgeIncident(currentIncident.incident_id),
                    )
                  : Promise.resolve()
              }
            />
          ) : null}

          {activeView === 'replay' ? (
            <ReplayLabView
              replay={replay}
              replaySymbol={replaySymbol}
              onReplaySymbolChange={setReplaySymbol}
            />
          ) : null}

          {activeView === 'records' ? (
            <SettingsRecordsView
              explorer={explorer}
              explorerQuery={explorerQuery}
              explorerCategory={explorerCategory}
              documents={documents}
              proposals={proposals}
              proposalTargetArea={proposalTargetArea}
              proposalRationale={proposalRationale}
              proposalValues={proposalValues}
              onExplorerQueryChange={setExplorerQuery}
              onExplorerCategoryChange={setExplorerCategory}
              onProposalTargetAreaChange={setProposalTargetArea}
              onProposalRationaleChange={setProposalRationale}
              onProposalValuesChange={setProposalValues}
              onProposalSubmit={handleProposalSubmit}
            />
          ) : null}
        </section>
      </div>

      {paletteOpen ? (
        <div className="palette-overlay" role="dialog" aria-modal="true">
          <div className="palette-card">
            <div className="palette-header">
              <strong>Command palette</strong>
              <button
                type="button"
                className="palette-close"
                onClick={() => setPaletteOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="palette-grid">
              {viewOptions.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  className="palette-option"
                  onClick={() => {
                    setActiveView(option.key)
                    setPaletteOpen(false)
                  }}
                >
                  <span>{option.label}</span>
                  <strong>{option.shortcut}</strong>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </main>
  )
}

function CommandCenterView(props: {
  commandCenter: CommandCenterSnapshot
  digest: DailySessionDigest | null
  incidents: IncidentRecord[]
  documents: DocumentRecord[]
  loopSymbol: string
  loopQuantity: string
  recoverSymbol: string
  serviceSymbols: string
  serviceQuantity: string
  serviceIntervalSeconds: string
  onLoopSymbolChange: (value: string) => void
  onLoopQuantityChange: (value: string) => void
  onRecoverSymbolChange: (value: string) => void
  onServiceSymbolsChange: (value: string) => void
  onServiceQuantityChange: (value: string) => void
  onServiceIntervalChange: (value: string) => void
  onRunPaperLoop: () => void
  onStartService: () => void
  onStopService: () => void
  onRecover: () => void
  onSessionPreopen: () => void
  onSessionHeartbeat: () => void
  onSessionClose: () => void
  proposalTargetArea: string
  proposalRationale: string
  proposalValues: string
  onProposalTargetAreaChange: (value: string) => void
  onProposalRationaleChange: (value: string) => void
  onProposalValuesChange: (value: string) => void
  onProposalSubmit: () => void
}) {
  return (
    <div className="view-grid">
      <Panel title="Market Command" subtitle={props.commandCenter.market_session_label}>
        <div className="chart-card">
          <div className="chart-header">
            <strong>Equity trajectory</strong>
            <span>{props.commandCenter.session_mode}</span>
          </div>
          <Sparkline points={props.commandCenter.equity_curve} />
        </div>
        <div className="split-grid">
          <div className="subpanel">
            <h3>Exposure map</h3>
            <ExposureBars items={props.commandCenter.exposure_breakdown} />
          </div>
          <div className="subpanel">
            <h3>Watchlist</h3>
            <ul className="watchlist">
              {props.commandCenter.watchlist.length ? (
                props.commandCenter.watchlist.map((item) => (
                  <li key={item.symbol}>
                    <strong>{item.symbol}</strong>
                    <span>{item.status}</span>
                  </li>
                ))
              ) : (
                <li className="muted">No watchlist data yet.</li>
              )}
            </ul>
          </div>
        </div>
      </Panel>

      <Panel title="Day Operations" subtitle="Bounded session controls">
        <div className="button-row">
          <button type="button" className="action-button primary" onClick={props.onSessionPreopen}>
            Session Pre-Open
          </button>
          <button
            type="button"
            className="action-button secondary"
            onClick={props.onSessionHeartbeat}
          >
            Session Heartbeat
          </button>
          <button type="button" className="action-button ghost" onClick={props.onSessionClose}>
            Session Close
          </button>
        </div>
        <div className="field-grid compact">
          <Field label="Loop Symbol">
            <input
              value={props.loopSymbol}
              onChange={(event) => props.onLoopSymbolChange(event.target.value)}
            />
          </Field>
          <Field label="Loop Quantity">
            <input
              value={props.loopQuantity}
              onChange={(event) => props.onLoopQuantityChange(event.target.value)}
            />
          </Field>
          <Field label="Recover Symbol">
            <input
              value={props.recoverSymbol}
              onChange={(event) => props.onRecoverSymbolChange(event.target.value)}
            />
          </Field>
          <Field label="Service Symbols">
            <input
              value={props.serviceSymbols}
              onChange={(event) => props.onServiceSymbolsChange(event.target.value)}
            />
          </Field>
          <Field label="Service Quantity">
            <input
              value={props.serviceQuantity}
              onChange={(event) => props.onServiceQuantityChange(event.target.value)}
            />
          </Field>
          <Field label="Interval (seconds)">
            <input
              value={props.serviceIntervalSeconds}
              onChange={(event) => props.onServiceIntervalChange(event.target.value)}
            />
          </Field>
        </div>
        <div className="button-row">
          <button type="button" className="action-button primary" onClick={props.onRunPaperLoop}>
            Run One Cycle
          </button>
          <button type="button" className="action-button secondary" onClick={props.onStartService}>
            Start Service
          </button>
          <button type="button" className="action-button secondary" onClick={props.onStopService}>
            Stop Service
          </button>
          <button type="button" className="action-button ghost" onClick={props.onRecover}>
            Recover
          </button>
        </div>
      </Panel>

      <Panel title="Incident Pulse" subtitle="Current operator-visible alerts">
        <div className="incident-rail">
          {props.incidents.length ? (
            props.incidents.slice(0, 3).map((incident) => (
              <article key={incident.incident_id} className="incident-card">
                <StatusChip label={incident.severity} tone={toneForSeverity(incident.severity)} />
                <strong>{incident.title}</strong>
                <p>{incident.summary}</p>
              </article>
            ))
          ) : (
            <p className="muted">No active incidents.</p>
          )}
        </div>
      </Panel>

      <Panel title="Latest Digest" subtitle="Most recent daily summary">
        {props.digest ? (
          <div className="digest-grid">
            <MiniStat label="Label" value={props.digest.session_label.replace('_', ' ')} />
            <MiniStat label="Service" value={props.digest.service_status} />
            <MiniStat label="Blocked Trades" value={String(props.digest.blocked_trade_count)} />
            <MiniStat
              label="Reconcilations"
              value={String(props.digest.reconciliation_failure_count)}
            />
            <div className="digest-actions">
              {props.digest.recommended_actions.map((action) => (
                <p key={action}>{action}</p>
              ))}
            </div>
          </div>
        ) : (
          <p className="muted">No session digest has been generated yet.</p>
        )}
      </Panel>

      <Panel title="Project Context" subtitle="Pinned local records">
        <div className="document-stack">
          {props.documents.map((document) => (
            <article key={document.doc_id} className="record-card">
              <div>
                <strong>{document.title}</strong>
                <span>{document.kind}</span>
              </div>
              <p>{document.preview}</p>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Proposal Studio" subtitle="Safe config drafting without context switches">
        <div className="field-grid">
          <Field label="Target Area">
            <input
              aria-label="Target Area"
              value={props.proposalTargetArea}
              onChange={(event) => props.onProposalTargetAreaChange(event.target.value)}
            />
          </Field>
          <Field label="Rationale">
            <textarea
              aria-label="Rationale"
              rows={4}
              value={props.proposalRationale}
              onChange={(event) => props.onProposalRationaleChange(event.target.value)}
            />
          </Field>
          <Field label="Proposed Values (JSON)">
            <textarea
              aria-label="Proposed Values (JSON)"
              rows={6}
              value={props.proposalValues}
              onChange={(event) => props.onProposalValuesChange(event.target.value)}
            />
          </Field>
        </div>
        <div className="button-row">
          <button type="button" className="action-button primary" onClick={props.onProposalSubmit}>
            Save Proposal
          </button>
        </div>
      </Panel>
    </div>
  )
}

function Gate3OpsView(props: {
  readiness: Gate3ReadinessReport
  promotionPackage: Gate3PromotionPackage | null
  replaySlippageSummary: ReplaySlippageSummary | null
  marketAutomationRun: MarketAutomationRunRecord | null
  marketSessions: MarketSessionRecord[]
  serviceSymbols: string
  serviceQuantity: string
  serviceIntervalSeconds: string
  marketDayHeartbeats: string
  recoveryDrills: RecoveryDrillRecord[]
  alertDrills: AlertDrillRecord[]
  recoverySymbol: string
  onServiceSymbolsChange: (value: string) => void
  onServiceQuantityChange: (value: string) => void
  onServiceIntervalChange: (value: string) => void
  onMarketDayHeartbeatsChange: (value: string) => void
  onRecoverySymbolChange: (value: string) => void
  onGenerateGate3Report: () => void
  onGenerateGate3Package: () => void
  onGenerateReplaySlippageReport: () => void
  onRunRecoveryDrill: () => void
  onRunSmtpDrill: () => void
  onRunMarketDay: () => void
}) {
  return (
    <div className="view-grid">
      <Panel title="Gate 3 Readiness" subtitle="Paper-operations advancement">
        <div className="digest-grid">
          <MiniStat label="Status" value={props.readiness.status} />
          <MiniStat
            label="Closed Trades"
            value={String(props.readiness.closed_trade_count)}
          />
          <MiniStat
            label="Observed Days"
            value={String(props.readiness.calendar_days_observed)}
          />
          <MiniStat
            label="Package"
            value={props.promotionPackage?.status ?? 'not generated'}
          />
        </div>
        <p className="section-lead">{props.readiness.summary}</p>
        <p className="muted">{props.readiness.required_operator_action}</p>
        <div className="button-row">
          <button
            type="button"
            className="action-button primary"
            onClick={props.onGenerateGate3Report}
          >
            Generate Gate 3 Report
          </button>
          <button
            type="button"
            className="action-button secondary"
            onClick={props.onGenerateGate3Package}
          >
            Generate Promotion Package
          </button>
          <button
            type="button"
            className="action-button secondary"
            onClick={props.onGenerateReplaySlippageReport}
          >
            Refresh Replay Evidence
          </button>
        </div>
      </Panel>

      <Panel title="Criteria Matrix" subtitle="Every gate condition in view">
        <div className="record-grid">
          {props.readiness.criteria.length ? (
            props.readiness.criteria.map((criterion) => (
              <article key={criterion.criterion_id} className="record-card">
                <div className="record-card-header">
                  <strong>{criterion.criterion_id.replaceAll('_', ' ')}</strong>
                  <StatusChip label={criterion.status} tone={toneForStatus(criterion.status)} />
                </div>
                <p>{criterion.details}</p>
                <span>{criterion.observed_value || criterion.threshold}</span>
              </article>
            ))
          ) : (
            <p className="muted">No Gate 3 criteria have been materialized yet.</p>
          )}
        </div>
      </Panel>

      <Panel title="Replay Cross-Check" subtitle="Paper fills versus replay model">
        <div className="digest-grid">
          <MiniStat
            label="Replay Status"
            value={props.replaySlippageSummary?.status ?? 'not generated'}
          />
          <MiniStat
            label="Matched Executions"
            value={String(props.replaySlippageSummary?.matched_execution_count ?? 0)}
          />
          <MiniStat
            label="Paper Mean (bps)"
            value={
              props.replaySlippageSummary?.paper_mean_absolute_slippage_bps ?? 'n/a'
            }
          />
          <MiniStat
            label="Replay Mean (bps)"
            value={
              props.replaySlippageSummary?.replay_mean_absolute_slippage_bps ?? 'n/a'
            }
          />
        </div>
        <p className="section-lead">
          Replay divergence{' '}
          <strong>{props.replaySlippageSummary?.divergence_ratio ?? 'n/a'}x</strong>
        </p>
        <p className="muted">
          {props.replaySlippageSummary?.details ??
            'Replay-slippage evidence has not been generated yet.'}
        </p>
      </Panel>

      <Panel title="Automation Runway" subtitle="Bounded market-day orchestration">
        <div className="digest-grid">
          <MiniStat
            label="Automation Status"
            value={props.marketAutomationRun?.status ?? 'not run'}
          />
          <MiniStat
            label="Trading Day"
            value={props.marketAutomationRun?.trading_day ?? 'n/a'}
          />
          <MiniStat
            label="Heartbeats"
            value={String(props.marketAutomationRun?.heartbeat_count ?? 0)}
          />
          <MiniStat
            label="Latest Package"
            value={props.marketAutomationRun?.latest_gate3_package_id ?? 'n/a'}
          />
        </div>
        <p className="section-lead">
          {props.marketAutomationRun?.summary ??
            'No market-day automation run has been recorded yet.'}
        </p>
        <div className="field-grid compact">
          <Field label="Symbols">
            <input
              value={props.serviceSymbols}
              onChange={(event) => props.onServiceSymbolsChange(event.target.value)}
            />
          </Field>
          <Field label="Quantity">
            <input
              value={props.serviceQuantity}
              onChange={(event) => props.onServiceQuantityChange(event.target.value)}
            />
          </Field>
          <Field label="Interval (seconds)">
            <input
              value={props.serviceIntervalSeconds}
              onChange={(event) => props.onServiceIntervalChange(event.target.value)}
            />
          </Field>
          <Field label="Max Heartbeats">
            <input
              value={props.marketDayHeartbeats}
              onChange={(event) =>
                props.onMarketDayHeartbeatsChange(event.target.value)
              }
            />
          </Field>
        </div>
        <div className="button-row">
          <button
            type="button"
            className="action-button primary"
            onClick={props.onRunMarketDay}
          >
            Run Market Day
          </button>
        </div>
      </Panel>

      <Panel title="Operational Drills" subtitle="Recovery and emergency evidence">
        <div className="field-grid compact">
          <Field label="Recovery Symbol">
            <input
              value={props.recoverySymbol}
              onChange={(event) => props.onRecoverySymbolChange(event.target.value)}
            />
          </Field>
        </div>
        <div className="button-row">
          <button
            type="button"
            className="action-button primary"
            onClick={props.onRunRecoveryDrill}
          >
            Run Recovery Drill
          </button>
          <button
            type="button"
            className="action-button secondary"
            onClick={props.onRunSmtpDrill}
          >
            Run SMTP Drill
          </button>
        </div>
        <div className="split-grid">
          <div className="subpanel">
            <h3>Recovery drills</h3>
            <ul className="watchlist">
              {props.recoveryDrills.length ? (
                props.recoveryDrills.slice(0, 4).map((drill) => (
                  <li key={drill.drill_id}>
                    <strong>{drill.symbol}</strong>
                    <span>{drill.status}</span>
                  </li>
                ))
              ) : (
                <li className="muted">No recovery drills recorded yet.</li>
              )}
            </ul>
          </div>
          <div className="subpanel">
            <h3>Alert drills</h3>
            <ul className="watchlist">
              {props.alertDrills.length ? (
                props.alertDrills.slice(0, 4).map((drill) => (
                  <li key={drill.drill_id}>
                    <strong>{drill.channel}</strong>
                    <span>{drill.status}</span>
                  </li>
                ))
              ) : (
                <li className="muted">No alert drills recorded yet.</li>
              )}
            </ul>
          </div>
        </div>
      </Panel>

      <Panel title="Market Sessions" subtitle="Latest operating checkpoints">
        <div className="record-grid">
          {props.marketSessions.length ? (
            props.marketSessions.slice(0, 4).map((session) => (
              <article key={session.session_id} className="record-card">
                <div className="record-card-header">
                  <strong>{session.session_label.replaceAll('_', ' ')}</strong>
                  <StatusChip label={session.service_status} tone="ink" />
                </div>
                <p>
                  {session.recommended_actions[0] || 'No operator recommendation recorded.'}
                </p>
                <span>
                  blocked {session.blocked_trade_count} / reconciliation{' '}
                  {session.reconciliation_failure_count}
                </span>
              </article>
            ))
          ) : (
            <p className="muted">No market-session checkpoints have been captured yet.</p>
          )}
        </div>
      </Panel>
    </div>
  )
}

function TradeIntelligenceView(props: {
  replay: ReplaySession
  positions: DashboardSnapshot['positions']
  replaySymbol: string
  onReplaySymbolChange: (value: string) => void
}) {
  return (
    <div className="view-grid">
      <Panel title="Trade Intelligence" subtitle="Decision trace and evidence chain">
        <div className="field-inline">
          <Field label="Replay Symbol">
            <input
              value={props.replaySymbol}
              onChange={(event) => props.onReplaySymbolChange(event.target.value)}
            />
          </Field>
        </div>
        <div className="timeline-list">
          {props.replay.events.length ? (
            props.replay.events.map((event) => (
              <article key={event.event_id} className="timeline-card">
                <div className="timeline-topline">
                  <StatusChip label={event.event_type.replaceAll('_', ' ')} tone="fog" />
                  <strong>{event.headline}</strong>
                </div>
                <p>{event.details}</p>
                <span>{event.occurred_at_utc}</span>
              </article>
            ))
          ) : (
            <p className="muted">No trade-intelligence events are available yet.</p>
          )}
        </div>
      </Panel>

      <Panel title="Position Lens" subtitle="Latest position snapshot">
        <div className="position-list">
          {props.positions.length ? (
            props.positions.map((position) => (
              <div key={position.symbol} className="position-row">
                <strong>{position.symbol}</strong>
                <span>{position.quantity || 'n/a'}</span>
                <span>{position.market_value || 'n/a'}</span>
              </div>
            ))
          ) : (
            <p className="muted">No open positions recorded.</p>
          )}
        </div>
      </Panel>
    </div>
  )
}

function ResearchStudioView(props: {
  research: ResearchStudioSnapshot
  benchmarkSymbol: string
  benchmarkWindowStart: string
  benchmarkWindowEnd: string
  gateBenchmarkPath: string
  gateWindowStart: string
  gateWindowEnd: string
  gateUniverse: string
  onBenchmarkSymbolChange: (value: string) => void
  onBenchmarkWindowStartChange: (value: string) => void
  onBenchmarkWindowEndChange: (value: string) => void
  onGateBenchmarkPathChange: (value: string) => void
  onGateWindowStartChange: (value: string) => void
  onGateWindowEndChange: (value: string) => void
  onGateUniverseChange: (value: string) => void
  onPrepareBenchmark: () => void
  onGenerateGateReport: () => void
  onGenerateDecisionBrief: () => void
}) {
  return (
    <div className="view-grid">
      <Panel title="Research Studio" subtitle="Gate evidence and candidate review">
        <p className="feature-summary">{props.research.decision_summary || 'No gate decision summary yet.'}</p>
        <div className="candidate-grid">
          {props.research.candidate_summaries.length ? (
            props.research.candidate_summaries.map((candidate) => (
              <article key={candidate.candidate_id} className="candidate-card">
                <div className="candidate-header">
                  <strong>{candidate.candidate_id}</strong>
                  <StatusChip label={candidate.recommendation} tone="teal" />
                </div>
                <p>{candidate.summary}</p>
                <div className="metric-grid">
                  {Object.entries(candidate.candidate_metrics).map(([key, value]) => (
                    <MiniStat key={key} label={`Candidate ${key}`} value={String(value)} />
                  ))}
                  {Object.entries(candidate.benchmark_metrics).map(([key, value]) => (
                    <MiniStat key={key} label={`Benchmark ${key}`} value={String(value)} />
                  ))}
                </div>
              </article>
            ))
          ) : (
            <p className="muted">No research candidates are available yet.</p>
          )}
        </div>
      </Panel>

      <Panel title="Validation Launchpad" subtitle="Bounded research actions">
        <div className="field-grid compact">
          <Field label="Benchmark Symbol">
            <input
              value={props.benchmarkSymbol}
              onChange={(event) => props.onBenchmarkSymbolChange(event.target.value)}
            />
          </Field>
          <Field label="Benchmark Start">
            <input
              value={props.benchmarkWindowStart}
              onChange={(event) => props.onBenchmarkWindowStartChange(event.target.value)}
            />
          </Field>
          <Field label="Benchmark End">
            <input
              value={props.benchmarkWindowEnd}
              onChange={(event) => props.onBenchmarkWindowEndChange(event.target.value)}
            />
          </Field>
          <Field label="Benchmark Artifact">
            <input
              value={props.gateBenchmarkPath}
              onChange={(event) => props.onGateBenchmarkPathChange(event.target.value)}
            />
          </Field>
          <Field label="Gate Start">
            <input
              value={props.gateWindowStart}
              onChange={(event) => props.onGateWindowStartChange(event.target.value)}
            />
          </Field>
          <Field label="Gate End">
            <input
              value={props.gateWindowEnd}
              onChange={(event) => props.onGateWindowEndChange(event.target.value)}
            />
          </Field>
          <Field label="Universe">
            <input
              value={props.gateUniverse}
              onChange={(event) => props.onGateUniverseChange(event.target.value)}
            />
          </Field>
        </div>
        <div className="button-row">
          <button type="button" className="action-button primary" onClick={props.onPrepareBenchmark}>
            Prepare Benchmark
          </button>
          <button type="button" className="action-button secondary" onClick={props.onGenerateGateReport}>
            Generate Gate Report
          </button>
          <button type="button" className="action-button ghost" onClick={props.onGenerateDecisionBrief}>
            Generate Decision Brief
          </button>
        </div>
      </Panel>
    </div>
  )
}

function IncidentCenterView(props: {
  incidents: IncidentRecord[]
  selectedIncidentId: string
  onSelectIncident: (value: string) => void
  onAcknowledgeIncident: () => void | Promise<void>
}) {
  return (
    <div className="view-grid">
      <Panel title="Incident Center" subtitle="Triage, context, and acknowledgment">
        <div className="incident-list">
          {props.incidents.length ? (
            props.incidents.map((incident) => (
              <button
                key={incident.incident_id}
                type="button"
                className={
                  incident.incident_id === props.selectedIncidentId
                    ? 'incident-list-item active'
                    : 'incident-list-item'
                }
                onClick={() => props.onSelectIncident(incident.incident_id)}
              >
                <StatusChip label={incident.severity} tone={toneForSeverity(incident.severity)} />
                <div>
                  <strong>{incident.title}</strong>
                  <p>{incident.summary}</p>
                </div>
              </button>
            ))
          ) : (
            <p className="muted">No incidents are available.</p>
          )}
        </div>
        <div className="button-row">
          <button type="button" className="action-button primary" onClick={props.onAcknowledgeIncident}>
            Acknowledge Incident
          </button>
        </div>
      </Panel>
    </div>
  )
}

function ReplayLabView(props: {
  replay: ReplaySession
  replaySymbol: string
  onReplaySymbolChange: (value: string) => void
}) {
  return (
    <div className="view-grid">
      <Panel title="Replay Lab" subtitle="Historical reconstruction from persisted evidence">
        <div className="field-inline">
          <Field label="Replay Symbol">
            <input
              value={props.replaySymbol}
              onChange={(event) => props.onReplaySymbolChange(event.target.value)}
            />
          </Field>
        </div>
        <article className="hero-replay">
          <strong>{props.replay.headline}</strong>
          <p>{props.replay.summary}</p>
        </article>
        <div className="timeline-list">
          {props.replay.events.length ? (
            props.replay.events.map((event) => (
              <article key={event.event_id} className="timeline-card">
                <div className="timeline-topline">
                  <StatusChip label={event.severity} tone={toneForSeverity(event.severity)} />
                  <strong>{event.headline}</strong>
                </div>
                <p>{event.details}</p>
                <span>{event.occurred_at_utc}</span>
              </article>
            ))
          ) : (
            <p className="muted">No replay events are available yet.</p>
          )}
        </div>
      </Panel>
    </div>
  )
}

function SettingsRecordsView(props: {
  explorer: ExplorerRecord[]
  explorerQuery: string
  explorerCategory: string
  documents: DocumentRecord[]
  proposals: ConfigProposal[]
  proposalTargetArea: string
  proposalRationale: string
  proposalValues: string
  onExplorerQueryChange: (value: string) => void
  onExplorerCategoryChange: (value: string) => void
  onProposalTargetAreaChange: (value: string) => void
  onProposalRationaleChange: (value: string) => void
  onProposalValuesChange: (value: string) => void
  onProposalSubmit: () => void
}) {
  return (
    <div className="view-grid">
      <Panel title="Settings & Records" subtitle="Searchable evidence and safe proposals">
        <div className="field-grid compact">
          <Field label="Search records">
            <input
              aria-label="Search records"
              value={props.explorerQuery}
              onChange={(event) => props.onExplorerQueryChange(event.target.value)}
            />
          </Field>
          <Field label="Category filter">
            <select
              value={props.explorerCategory}
              onChange={(event) => props.onExplorerCategoryChange(event.target.value)}
            >
              <option value="">All</option>
              <option value="validation_report">Validation reports</option>
              <option value="operator_alert">Operator alerts</option>
              <option value="service_cycle">Service cycles</option>
              <option value="daily_digest">Daily digests</option>
            </select>
          </Field>
        </div>
        <div className="record-stack">
          {props.explorer.length ? (
            props.explorer.map((record) => (
              <article key={record.record_id} className="record-card">
                <div>
                  <strong>{record.title}</strong>
                  <span>{record.category}</span>
                </div>
                <p>{record.preview}</p>
                <small>{record.path}</small>
              </article>
            ))
          ) : (
            <p className="muted">No records matched the current search.</p>
          )}
        </div>
      </Panel>

      <Panel title="Proposal Studio" subtitle="Config proposals on disk">
        <div className="field-grid">
          <Field label="Target Area">
            <input
              aria-label="Target Area"
              value={props.proposalTargetArea}
              onChange={(event) => props.onProposalTargetAreaChange(event.target.value)}
            />
          </Field>
          <Field label="Rationale">
            <textarea
              aria-label="Rationale"
              rows={4}
              value={props.proposalRationale}
              onChange={(event) => props.onProposalRationaleChange(event.target.value)}
            />
          </Field>
          <Field label="Proposed Values (JSON)">
            <textarea
              aria-label="Proposed Values (JSON)"
              rows={6}
              value={props.proposalValues}
              onChange={(event) => props.onProposalValuesChange(event.target.value)}
            />
          </Field>
        </div>
        <div className="button-row">
          <button type="button" className="action-button primary" onClick={props.onProposalSubmit}>
            Save Proposal
          </button>
        </div>
        <div className="proposal-list">
          {props.proposals.map((proposal) => (
            <article key={proposal.proposal_id} className="proposal-card">
              <strong>{proposal.proposal_id}</strong>
              <p>{proposal.diff_preview}</p>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Documents" subtitle="Pinned project records">
        <div className="document-stack">
          {props.documents.map((document) => (
            <article key={document.doc_id} className="record-card">
              <div>
                <strong>{document.title}</strong>
                <span>{document.kind}</span>
              </div>
              <p>{document.preview}</p>
              <small>{document.path}</small>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  )
}

function Panel(props: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h2>{props.title}</h2>
          <p>{props.subtitle}</p>
        </div>
      </header>
      {props.children}
    </section>
  )
}

function Field(props: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{props.label}</span>
      {props.children}
    </label>
  )
}

function MetricCard(props: { label: string; value: string }) {
  return (
    <article className="metric-card">
      <span>{props.label}</span>
      <strong>{props.value || 'n/a'}</strong>
    </article>
  )
}

function MiniStat(props: { label: string; value: string }) {
  return (
    <div className="mini-stat">
      <span>{props.label}</span>
      <strong>{props.value || 'n/a'}</strong>
    </div>
  )
}

function SafetyRow(props: { label: string; value: string }) {
  return (
    <div className="safety-row">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  )
}

function StatusChip(props: { label: string; tone: string }) {
  return <span className={`status-chip ${props.tone}`}>{props.label}</span>
}

function Sparkline(props: { points: Array<{ label: string; value: string }> }) {
  if (!props.points.length) {
    return <p className="muted">No equity history is available yet.</p>
  }
  const numeric = props.points
    .map((point) => Number(point.value))
    .filter((value) => Number.isFinite(value))
  if (!numeric.length) {
    return <p className="muted">Equity values are not available yet.</p>
  }
  const min = Math.min(...numeric)
  const max = Math.max(...numeric)
  const spread = Math.max(max - min, 1)
  const path = props.points
    .map((point, index) => {
      const x = (index / Math.max(props.points.length - 1, 1)) * 100
      const y = 100 - ((Number(point.value) - min) / spread) * 100
      return `${index === 0 ? 'M' : 'L'} ${x},${y}`
    })
    .join(' ')
  return (
    <svg className="sparkline" viewBox="0 0 100 100" preserveAspectRatio="none">
      <path d={path} />
    </svg>
  )
}

function ExposureBars(props: { items: Array<{ symbol: string; value: string }> }) {
  if (!props.items.length) {
    return <p className="muted">No exposure data is available yet.</p>
  }
  return (
    <div className="exposure-list">
      {props.items.map((item) => (
        <div key={item.symbol} className="exposure-row">
          <div className="exposure-copy">
            <strong>{item.symbol}</strong>
            <span>{item.value}%</span>
          </div>
          <div className="exposure-track">
            <div className="exposure-fill" style={{ width: `${item.value}%` }} />
          </div>
        </div>
      ))}
    </div>
  )
}

function toneForSeverity(severity: string) {
  if (severity === 'critical') {
    return 'crimson'
  }
  if (severity === 'warning') {
    return 'gold'
  }
  return 'fog'
}

function toneForStatus(status: string) {
  if (status === 'pass' || status === 'completed') {
    return 'teal'
  }
  if (status === 'fail') {
    return 'crimson'
  }
  if (status === 'pending') {
    return 'gold'
  }
  return 'fog'
}

export default App
