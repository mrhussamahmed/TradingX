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
  getBotBrain,
  getCommandCenter,
  getConfigSummary,
  getDocuments,
  getExplorer,
  getGate3PromotionPackage,
  getGate3Readiness,
  getIncidents,
  getLatestDigest,
  getBlueprintCatalog,
  getPortfolioWorkspace,
  getReplay,
  getResearch,
  getRuntimeHostActivation,
  getRuntimeHostDecisionDetail,
  getRuntimeHostHeartbeat,
  getRuntimeHostModel,
  getRuntimeHostSelection,
  getRuntimeHostState,
  getRuntimeHostWarmup,
  getSchedulerState,
  getSessionTimeline,
  lockWebWrites,
  unlockWebWrites,
} from '../../api'
import type {
  ActionResult,
  BotBrainSnapshot,
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
  PortfolioBlueprintCatalog,
  ReplaySession,
  ResearchStudioSnapshot,
  RuntimeHeartbeatSnapshot,
  RuntimeDecisionDetail,
  SessionTimelineResponse,
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
  sessionTimeline: SessionTimelineResponse
  sessionTimelineDate: string
  explorer: ExplorerRecord[]
  digest: DailySessionDigest | null
  portfolio: PortfolioWorkspaceSnapshot
  blueprintCatalog: PortfolioBlueprintCatalog
  gate3Readiness: Gate3ReadinessReport
  gate3Package: Gate3PromotionPackage | null
  runtimeState: BotRuntimeState
  runtimeHeartbeat: RuntimeHeartbeatSnapshot
  runtimeWarmup: HistoricalWarmupRecord | null
  runtimeActivation: StrategyActivationRecord | null
  runtimeModel: ModelWeightSnapshot | null
  runtimeSelection: OpportunitySelectionRecord | null
  runtimeDecisionDetail: RuntimeDecisionDetail | null
  botBrain: BotBrainSnapshot
  schedulerState: MarketDaySchedulerState
}

export type DataContextValue = DataState & {
  refresh: () => Promise<void>
  setSessionTimelineDate: (tradingDay: string) => void
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

const defaultSessionTimeline: SessionTimelineResponse = {
  session: {
    trading_day: '',
    schedule_id: '',
    session_open_at_utc: null,
    session_close_at_utc: null,
    exchange: '',
    timezone: '',
    status: 'missing_session_metadata',
    metadata_status: 'schedule_missing',
    partial_reason: 'Session timeline is waiting for backend evidence.',
  },
  available_trading_days: [],
  events: [],
  filters: {
    trading_day: '',
    symbol: null,
    cycle_id: null,
    incident_id: null,
  },
}

const defaultPortfolio: PortfolioWorkspaceSnapshot = {
  generated_at_utc: '',
  source_evidence_at_utc: null,
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

const defaultBlueprintCatalog: PortfolioBlueprintCatalog = {
  blueprints: [],
  active_activation: null,
  pending_activation: null,
}

const defaultGate3Readiness: Gate3ReadinessReport = {
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

const defaultBotBrain: BotBrainSnapshot = {
  generated_at_utc: '',
  active_blueprint_id: '',
  queued_blueprint_id: '',
  trading_mode: 'paper',
  market_state: 'unknown',
  next_check_at_utc: null,
  decision_stages: [],
  last_real_order: null,
  sleeve_readiness: [],
  cycle_explanation: {
    summary: 'No service cycle has been recorded yet.',
    primary_reason_code: 'no_cycle',
    market_state: 'unknown',
    planner_status: 'unknown',
    risk_status: 'unknown',
    sleeve_reasons: [],
  },
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
  configured_cadence_seconds: 180,
  running_cadence_seconds: 180,
  cadence_source: 'config',
  cadence_applies_at: 'next_start',
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
  unlockedFromSession: boolean,
): WriteMode {
  const enabled = Boolean(config.config.web_write_mode_enabled)
  const configured = Boolean(config.config.web_write_signing_configured)
  if (!enabled) {
    return {
      enabled: false,
      configured,
      unlocked: false,
      detail: 'Write mode is disabled on the server.',
    }
  }
  if (!configured) {
    return {
      enabled: false,
      configured,
      unlocked: false,
      detail: 'Signed web writes are not configured on the server.',
    }
  }
  if (!unlockedFromSession) {
    return {
      enabled: true,
      configured,
      unlocked: false,
      detail: 'Enter the local signing secret to unlock writes.',
    }
  }
  return {
    enabled: true,
    configured,
    unlocked: true,
    detail: 'Local write actions are enabled and signed.',
  }
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
  const [sessionTimeline, setSessionTimeline] =
    useState<SessionTimelineResponse>(defaultSessionTimeline)
  const [sessionTimelineDate, setSessionTimelineDateState] = useState('')
  const [explorer, setExplorer] = useState<ExplorerRecord[]>([])
  const [digest, setDigest] = useState<DailySessionDigest | null>(null)
  const [portfolio, setPortfolio] = useState<PortfolioWorkspaceSnapshot>(defaultPortfolio)
  const [blueprintCatalog, setBlueprintCatalog] =
    useState<PortfolioBlueprintCatalog>(defaultBlueprintCatalog)
  const [gate3Readiness, setGate3Readiness] = useState<Gate3ReadinessReport>(defaultGate3Readiness)
  const [gate3Package, setGate3Package] = useState<Gate3PromotionPackage | null>(null)
  const [runtimeState, setRuntimeState] = useState<BotRuntimeState>(defaultRuntimeState)
  const [runtimeHeartbeat, setRuntimeHeartbeat] =
    useState<RuntimeHeartbeatSnapshot>(defaultRuntimeHeartbeat)
  const [runtimeWarmup, setRuntimeWarmup] = useState<HistoricalWarmupRecord | null>(null)
  const [runtimeActivation, setRuntimeActivation] = useState<StrategyActivationRecord | null>(null)
  const [runtimeModel, setRuntimeModel] = useState<ModelWeightSnapshot | null>(null)
  const [runtimeSelection, setRuntimeSelection] = useState<OpportunitySelectionRecord | null>(null)
  const [runtimeDecisionDetail, setRuntimeDecisionDetail] = useState<RuntimeDecisionDetail | null>(null)
  const [botBrain, setBotBrain] = useState<BotBrainSnapshot>(defaultBotBrain)
  const [schedulerState, setSchedulerState] =
    useState<MarketDaySchedulerState>(defaultSchedulerState)
  const [pageError, setPageError] = useState('')
  const [isBooting, setIsBooting] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [writesUnlocked, setWritesUnlocked] = useState(() => areWebWritesUnlocked())
  const [generatedAt, setGeneratedAt] = useState('')
  const inFlightRef = useRef<Promise<void> | null>(null)
  const watchlistSymbolRef = useRef<string>('SPY')
  const sessionTimelineDateRef = useRef<string>('')

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
        const selectedTradingDay = sessionTimelineDateRef.current
        const settled = await Promise.allSettled([
          getCommandCenter(),
          getConfigSummary(),
          getDocuments(),
          getIncidents(),
          getResearch(),
          getReplay({ symbol: watchlistSymbol }),
          getSessionTimeline({
            trading_day: selectedTradingDay || undefined,
          }),
          getExplorer({ query: '' }),
          getLatestDigest(),
          getPortfolioWorkspace(),
          getBlueprintCatalog(),
          getGate3Readiness(),
          getGate3PromotionPackage(),
          getRuntimeHostState(),
          getRuntimeHostHeartbeat(),
          getRuntimeHostWarmup(),
          getRuntimeHostActivation(),
          getRuntimeHostModel(),
          getRuntimeHostSelection(),
          getRuntimeHostDecisionDetail(),
          getBotBrain(),
          getSchedulerState(),
        ])

        const value = <T,>(index: number, fallback: T): T => {
          const result = settled[index]
          return result.status === 'fulfilled' && result.value !== undefined
            ? (result.value as T)
            : fallback
        }

        const nextCommandCenter = value(0, defaultCommandCenter)
        const nextConfigSummary = value(1, defaultConfigSummary)
        const nextDocuments = value<DocumentRecord[]>(2, [])
        const nextIncidents = value<IncidentRecord[]>(3, [])
        const nextResearch = value(4, defaultResearch)
        const nextReplay = value(5, defaultReplay)
        const nextSessionTimeline = value(6, defaultSessionTimeline)
        const nextExplorer = value<ExplorerRecord[]>(7, [])
        const nextDigest = value<DailySessionDigest | null>(8, null)
        const nextPortfolio = value(9, defaultPortfolio)
        const nextBlueprintCatalog = value(10, defaultBlueprintCatalog)
        const nextGate3Readiness = value(11, defaultGate3Readiness)
        const nextGate3Package = value<Gate3PromotionPackage | null>(12, null)
        const nextRuntimeState = value(13, defaultRuntimeState)
        const nextRuntimeHeartbeat = value(14, defaultRuntimeHeartbeat)
        const nextRuntimeWarmup = value<HistoricalWarmupRecord | null>(15, null)
        const nextRuntimeActivation = value<StrategyActivationRecord | null>(16, null)
        const nextRuntimeModel = value<ModelWeightSnapshot | null>(17, null)
        const nextRuntimeSelection = value<OpportunitySelectionRecord | null>(18, null)
        const nextRuntimeDecisionDetail = value<RuntimeDecisionDetail | null>(19, null)
        const nextBotBrain = value(20, defaultBotBrain)
        const nextSchedulerState = value(21, defaultSchedulerState)

        startTransition(() => {
          setCommandCenter(nextCommandCenter)
          setConfigSummary(nextConfigSummary)
          setDocuments(nextDocuments)
          setIncidents(nextIncidents)
          setResearch(nextResearch)
          setReplay(nextReplay)
          const currentTimelineDate = sessionTimelineDateRef.current
          const requestStillCurrent =
            currentTimelineDate === selectedTradingDay ||
            (!selectedTradingDay && !currentTimelineDate)
          if (requestStillCurrent) {
            setSessionTimeline(nextSessionTimeline)
          }
          if (
            requestStillCurrent &&
            !sessionTimelineDateRef.current &&
            nextSessionTimeline.filters.trading_day
          ) {
            sessionTimelineDateRef.current = nextSessionTimeline.filters.trading_day
            setSessionTimelineDateState(nextSessionTimeline.filters.trading_day)
          }
          setExplorer(nextExplorer)
          setDigest(nextDigest)
          setPortfolio(nextPortfolio)
          setBlueprintCatalog(nextBlueprintCatalog)
          setGate3Readiness(nextGate3Readiness)
          setGate3Package(nextGate3Package)
          setRuntimeState(nextRuntimeState)
          setRuntimeHeartbeat(nextRuntimeHeartbeat)
          setRuntimeWarmup(nextRuntimeWarmup)
          setRuntimeActivation(nextRuntimeActivation)
          setRuntimeModel(nextRuntimeModel)
          setRuntimeSelection(nextRuntimeSelection)
          setRuntimeDecisionDetail(nextRuntimeDecisionDetail)
          setBotBrain(nextBotBrain)
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

  const setSessionTimelineDate = useCallback((tradingDay: string) => {
    sessionTimelineDateRef.current = tradingDay
    setSessionTimelineDateState(tradingDay)
    const requestedTradingDay = tradingDay
    void getSessionTimeline({ trading_day: requestedTradingDay || undefined })
      .then((nextTimeline) => {
        if (sessionTimelineDateRef.current !== requestedTradingDay) {
          return
        }
        setSessionTimeline(nextTimeline)
        if (nextTimeline.filters.trading_day) {
          sessionTimelineDateRef.current = nextTimeline.filters.trading_day
          setSessionTimelineDateState(nextTimeline.filters.trading_day)
        }
      })
      .catch((error) => {
        setPageError(
          error instanceof Error
            ? `Timeline refresh failed: ${error.message}`
            : 'Timeline refresh failed.',
        )
      })
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
      sessionTimeline,
      sessionTimelineDate,
      explorer,
      digest,
      portfolio,
      blueprintCatalog,
      gate3Readiness,
      gate3Package,
      runtimeState,
      runtimeHeartbeat,
      runtimeWarmup,
      runtimeActivation,
      runtimeModel,
      runtimeSelection,
      runtimeDecisionDetail,
      botBrain,
      schedulerState,
      refresh,
      setSessionTimelineDate,
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
      sessionTimeline,
      sessionTimelineDate,
      explorer,
      digest,
      portfolio,
      blueprintCatalog,
      gate3Readiness,
      gate3Package,
      runtimeState,
      runtimeHeartbeat,
      runtimeWarmup,
      runtimeActivation,
      runtimeModel,
      runtimeSelection,
      runtimeDecisionDetail,
      botBrain,
      schedulerState,
      refresh,
      setSessionTimelineDate,
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
