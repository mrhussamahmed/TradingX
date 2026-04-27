import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import {
  areWebWritesUnlocked,
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
  getRuntimeHostActivation,
  getRuntimeHostHeartbeat,
  getRuntimeHostModel,
  getRuntimeHostSelection,
  getRuntimeHostState,
  getRuntimeHostWarmup,
  getSchedulerState,
  lockWebWrites,
  unlockWebWrites,
} from '../../api'
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
  MarketDaySchedulerState,
  ModelWeightSnapshot,
  OpportunitySelectionRecord,
  PortfolioWorkspaceSnapshot,
  ReplaySession,
  ResearchStudioSnapshot,
  RuntimeHeartbeatSnapshot,
  StrategyActivationRecord,
} from '../../types'

import { useToast } from './ToastContext'

export type WriteMode = {
  enabled: boolean
  configured: boolean
  unlocked: boolean
  detail: string
}

export type DataState = {
  generatedAt: string
  isBooting: boolean
  isRefreshing: boolean
  pageError: string
  writeMode: WriteMode
  commandCenter: CommandCenterSnapshot
  configSummary: ConfigSummary
  documents: DocumentRecord[]
  incidents: IncidentRecord[]
  research: ResearchStudioSnapshot
  replay: ReplaySession
  explorer: ExplorerRecord[]
  digest: DailySessionDigest | null
  portfolio: PortfolioWorkspaceSnapshot
  gate3Readiness: Gate3ReadinessReport
  gate3Package: Gate3PromotionPackage | null
  runtimeState: BotRuntimeState
  runtimeHeartbeat: RuntimeHeartbeatSnapshot
  runtimeWarmup: HistoricalWarmupRecord | null
  runtimeActivation: StrategyActivationRecord | null
  runtimeModel: ModelWeightSnapshot | null
  runtimeSelection: OpportunitySelectionRecord | null
  schedulerState: MarketDaySchedulerState
}

export type DataContextValue = DataState & {
  refresh: () => Promise<void>
  unlockWrites: (secret: string) => { ok: boolean; error?: string }
  lockWrites: () => void
  runAction: (
    label: string,
    request: () => Promise<ActionResult>,
  ) => Promise<ActionResult | null>
}

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
    web_write_signing_configured: false,
    web_write_max_age_seconds: 300,
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

const defaultSchedulerState: MarketDaySchedulerState = {
  status: 'idle',
  poll_interval_seconds: 60,
  active_symbols: [],
  next_run_at_utc: null,
  last_started_at_utc: null,
  last_completed_at_utc: null,
  active_trading_day: '',
  last_error: '',
}

// eslint-disable-next-line react-refresh/only-export-components
export function describeWriteMode(
  config: ConfigSummary,
  unlocked: boolean,
): WriteMode {
  const enabled = Boolean(config.config.web_write_mode_enabled)
  const configured = Boolean(config.config.web_write_signing_configured)
  let detail = ''
  if (!enabled) {
    detail = 'Write mode is disabled on the server.'
  } else if (!configured) {
    detail = 'Server-side write signing is not configured.'
  } else if (!unlocked) {
    detail = 'Enter the local signing secret to unlock write actions in this browser session.'
  } else {
    detail = 'Signed write actions are unlocked for this browser session.'
  }
  return { enabled, configured, unlocked, detail }
}

const DataContext = createContext<DataContextValue | null>(null)

export function DataProvider({ children }: { children: ReactNode }) {
  const { pushToast } = useToast()

  const [configSummary, setConfigSummary] = useState<ConfigSummary>(defaultConfigSummary)
  const [commandCenter, setCommandCenter] = useState<CommandCenterSnapshot>(defaultCommandCenter)
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [incidents, setIncidents] = useState<IncidentRecord[]>([])
  const [research, setResearch] = useState<ResearchStudioSnapshot>(defaultResearch)
  const [replay, setReplay] = useState<ReplaySession>(defaultReplay)
  const [explorer, setExplorer] = useState<ExplorerRecord[]>([])
  const [digest, setDigest] = useState<DailySessionDigest | null>(null)
  const [portfolio, setPortfolio] = useState<PortfolioWorkspaceSnapshot>(defaultPortfolio)
  const [gate3Readiness, setGate3Readiness] = useState<Gate3ReadinessReport>(defaultGate3Readiness)
  const [gate3Package, setGate3Package] = useState<Gate3PromotionPackage | null>(null)
  const [runtimeState, setRuntimeState] = useState<BotRuntimeState>(defaultRuntimeState)
  const [runtimeHeartbeat, setRuntimeHeartbeat] =
    useState<RuntimeHeartbeatSnapshot>(defaultRuntimeHeartbeat)
  const [runtimeWarmup, setRuntimeWarmup] = useState<HistoricalWarmupRecord | null>(null)
  const [runtimeActivation, setRuntimeActivation] = useState<StrategyActivationRecord | null>(null)
  const [runtimeModel, setRuntimeModel] = useState<ModelWeightSnapshot | null>(null)
  const [runtimeSelection, setRuntimeSelection] = useState<OpportunitySelectionRecord | null>(null)
  const [schedulerState, setSchedulerState] =
    useState<MarketDaySchedulerState>(defaultSchedulerState)
  const [pageError, setPageError] = useState('')
  const [isBooting, setIsBooting] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [writesUnlocked, setWritesUnlocked] = useState(() => areWebWritesUnlocked())
  const [generatedAt, setGeneratedAt] = useState('')
  const inFlightRef = useRef<Promise<void> | null>(null)
  const watchlistSymbolRef = useRef<string>('SPY')

  useEffect(() => {
    watchlistSymbolRef.current = commandCenter.watchlist[0]?.symbol ?? 'SPY'
  }, [commandCenter.watchlist])

  const refresh = useCallback<DataContextValue['refresh']>(async () => {
    if (inFlightRef.current) {
      return inFlightRef.current
    }
    const work = (async () => {
      setIsRefreshing(true)
      try {
        const watchlistSymbol = watchlistSymbolRef.current
        const settled = await Promise.allSettled([
          getCommandCenter(),
          getConfigSummary(),
          getDocuments(),
          getIncidents(),
          getResearch(),
          getReplay({ symbol: watchlistSymbol }),
          getExplorer({ query: '' }),
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
          getSchedulerState(),
        ])

        const value = <T,>(index: number, fallback: T): T => {
          const result = settled[index]
          return result.status === 'fulfilled' ? (result.value as T) : fallback
        }

        const nextCommandCenter = value(0, defaultCommandCenter)
        const nextConfigSummary = value(1, defaultConfigSummary)
        const nextDocuments = value<DocumentRecord[]>(2, [])
        const nextIncidents = value<IncidentRecord[]>(3, [])
        const nextResearch = value(4, defaultResearch)
        const nextReplay = value(5, defaultReplay)
        const nextExplorer = value<ExplorerRecord[]>(6, [])
        const nextDigest = value<DailySessionDigest | null>(7, null)
        const nextPortfolio = value(8, defaultPortfolio)
        const nextGate3Readiness = value(9, defaultGate3Readiness)
        const nextGate3Package = value<Gate3PromotionPackage | null>(10, null)
        const nextRuntimeState = value(11, defaultRuntimeState)
        const nextRuntimeHeartbeat = value(12, defaultRuntimeHeartbeat)
        const nextRuntimeWarmup = value<HistoricalWarmupRecord | null>(13, null)
        const nextRuntimeActivation = value<StrategyActivationRecord | null>(14, null)
        const nextRuntimeModel = value<ModelWeightSnapshot | null>(15, null)
        const nextRuntimeSelection = value<OpportunitySelectionRecord | null>(16, null)
        const nextSchedulerState = value(17, defaultSchedulerState)

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
          setSchedulerState(nextSchedulerState)
          setGeneratedAt(
            nextPortfolio.generated_at_utc || nextCommandCenter.generated_at_utc || new Date().toISOString(),
          )
        })

        const failures = settled
          .map((result, index) =>
            result.status === 'rejected'
              ? `[${index}] ${result.reason instanceof Error ? result.reason.message : String(result.reason)}`
              : null,
          )
          .filter((item): item is string => item !== null)

        setPageError(
          failures.length > 0
            ? `Partial refresh failure (${failures.length}/${settled.length}): ${failures.join('; ')}`
            : '',
        )
      } catch (error) {
        setPageError(
          error instanceof Error ? error.message : 'Unable to load the operator platform.',
        )
      } finally {
        setIsBooting(false)
        setIsRefreshing(false)
      }
    })()
    inFlightRef.current = work
    work.finally(() => {
      if (inFlightRef.current === work) {
        inFlightRef.current = null
      }
    })
    return work
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    const seconds = Math.max(
      5,
      Number(configSummary.config.web_refresh_interval_seconds || 15),
    )
    const id = window.setInterval(() => {
      void refresh()
    }, seconds * 1000)
    return () => {
      window.clearInterval(id)
    }
  }, [configSummary.config.web_refresh_interval_seconds, refresh])

  const unlockWrites = useCallback<DataContextValue['unlockWrites']>((secret) => {
    const trimmed = secret.trim()
    if (!trimmed) {
      return { ok: false, error: 'Enter the local signing secret to unlock writes.' }
    }
    try {
      unlockWebWrites(trimmed)
      setWritesUnlocked(true)
      pushToast('Web writes unlocked for this browser session.', 'good')
      return { ok: true }
    } catch (error) {
      return {
        ok: false,
        error: error instanceof Error ? error.message : 'Unable to unlock writes.',
      }
    }
  }, [pushToast])

  const lockWrites = useCallback(() => {
    lockWebWrites()
    setWritesUnlocked(false)
    pushToast('Web writes locked for this browser session.', 'info')
  }, [pushToast])

  const runAction = useCallback<DataContextValue['runAction']>(
    async (label, request) => {
      try {
        const result = await request()
        const tone =
          result.status === 'failed' ? 'risk' : result.status === 'completed' ? 'good' : 'info'
        pushToast(`${label}: ${result.message || result.status}`, tone)
        if (inFlightRef.current) {
          await inFlightRef.current.catch(() => undefined)
        }
        await refresh()
        return result
      } catch (error) {
        pushToast(
          `${label}: ${error instanceof Error ? error.message : 'Action failed unexpectedly.'}`,
          'risk',
        )
        return null
      }
    },
    [pushToast, refresh],
  )

  const writeMode = useMemo(() => describeWriteMode(configSummary, writesUnlocked), [
    configSummary,
    writesUnlocked,
  ])

  const value = useMemo<DataContextValue>(
    () => ({
      generatedAt,
      isBooting,
      isRefreshing,
      pageError,
      writeMode,
      commandCenter,
      configSummary,
      documents,
      incidents,
      research,
      replay,
      explorer,
      digest,
      portfolio,
      gate3Readiness,
      gate3Package,
      runtimeState,
      runtimeHeartbeat,
      runtimeWarmup,
      runtimeActivation,
      runtimeModel,
      runtimeSelection,
      schedulerState,
      refresh,
      unlockWrites,
      lockWrites,
      runAction,
    }),
    [
      generatedAt,
      isBooting,
      isRefreshing,
      pageError,
      writeMode,
      commandCenter,
      configSummary,
      documents,
      incidents,
      research,
      replay,
      explorer,
      digest,
      portfolio,
      gate3Readiness,
      gate3Package,
      runtimeState,
      runtimeHeartbeat,
      runtimeWarmup,
      runtimeActivation,
      runtimeModel,
      runtimeSelection,
      schedulerState,
      refresh,
      unlockWrites,
      lockWrites,
      runAction,
    ],
  )

  return <DataContext.Provider value={value}>{children}</DataContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useData() {
  const ctx = useContext(DataContext)
  if (!ctx) {
    throw new Error('useData must be used inside DataProvider')
  }
  return ctx
}
