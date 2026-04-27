import type {
  ActionResult,
  AlertDrillRecord,
  BotRuntimeState,
  CommandCenterSnapshot,
  ConfigProposal,
  ConfigSummary,
  DailySessionDigest,
  DashboardSnapshot,
  DocumentRecord,
  EvidenceCategory,
  EvidenceItem,
  ExplorerRecord,
  Gate3PromotionPackage,
  Gate3ReadinessReport,
  HistoricalWarmupRecord,
  IncidentRecord,
  MarketAutomationRunRecord,
  MarketDayScheduleRecord,
  MarketDaySchedulerState,
  ModelWeightSnapshot,
  OpportunitySelectionRecord,
  MarketSessionRecord,
  PortfolioWorkspaceSnapshot,
  PerformanceAnalyticsSnapshot,
  ReplaySlippageSummary,
  ReplaySession,
  RecoveryDrillRecord,
  ResearchStudioSnapshot,
  RuntimeHeartbeatSnapshot,
  StrategyActivationRecord,
} from './types'

const WRITE_SECRET_SESSION_KEY = 'tradingx.web.writeSigningSecret'
const TIMESTAMP_HEADER = 'X-TradingX-Timestamp'
const IDEMPOTENCY_HEADER = 'X-TradingX-Idempotency-Key'
const SIGNATURE_HEADER = 'X-TradingX-Signature'

function getWriteSigningSecret(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  return window.sessionStorage.getItem(WRITE_SECRET_SESSION_KEY) ?? ''
}

export function unlockWebWrites(secret: string) {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.setItem(WRITE_SECRET_SESSION_KEY, secret)
}

export function lockWebWrites() {
  if (typeof window === 'undefined') {
    return
  }
  window.sessionStorage.removeItem(WRITE_SECRET_SESSION_KEY)
}

export function areWebWritesUnlocked() {
  return getWriteSigningSecret().length > 0
}

function bytesToHex(bytes: Uint8Array) {
  return Array.from(bytes)
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

async function sha256Hex(value: string) {
  const digest = await globalThis.crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value),
  )
  return bytesToHex(new Uint8Array(digest))
}

async function hmacSha256Hex(secret: string, payload: string) {
  const key = await globalThis.crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  )
  const signature = await globalThis.crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(payload),
  )
  return bytesToHex(new Uint8Array(signature))
}

function buildWritePath(url: string) {
  if (typeof window === 'undefined') {
    return url
  }
  const resolved = new URL(url, window.location.origin)
  return resolved.pathname
}

async function signedWriteHeaders(url: string, bodyText: string) {
  const secret = getWriteSigningSecret()
  if (!secret) {
    throw new Error('Web writes are locked. Enter the signing secret to continue.')
  }
  const timestamp = String(Math.floor(Date.now() / 1000))
  const idempotencyKey =
    globalThis.crypto.randomUUID?.() ??
    `idem-${timestamp}-${Math.random().toString(16).slice(2)}`
  const path = buildWritePath(url)
  const bodyHash = await sha256Hex(bodyText)
  const canonical = ['POST', path, timestamp, idempotencyKey, bodyHash].join('\n')
  const signature = await hmacSha256Hex(secret, canonical)
  return {
    [TIMESTAMP_HEADER]: timestamp,
    [IDEMPOTENCY_HEADER]: idempotencyKey,
    [SIGNATURE_HEADER]: signature,
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const method = init?.method?.toUpperCase() ?? 'GET'
  const isWrite = method === 'POST'
  const bodyText =
    typeof init?.body === 'string' ? init.body : init?.body ? String(init.body) : ''
  const signingHeaders = isWrite ? await signedWriteHeaders(url, bodyText) : {}
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...signingHeaders,
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null
    throw new Error(payload?.detail ?? `${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

export function getOverview() {
  return request<DashboardSnapshot>('/api/overview')
}

export function getCommandCenter() {
  return request<CommandCenterSnapshot>('/api/platform/command-center')
}

export function getConfigSummary() {
  return request<ConfigSummary>('/api/config/summary')
}

export function getDocuments() {
  return request<DocumentRecord[]>('/api/documents')
}

export function getRuntimeHostState() {
  return request<BotRuntimeState>('/api/runtime-host/state')
}

export function getRuntimeHostHeartbeat() {
  return request<RuntimeHeartbeatSnapshot>('/api/runtime-host/heartbeat')
}

export function getRuntimeHostWarmup() {
  return request<HistoricalWarmupRecord | null>('/api/runtime-host/warmup/latest')
}

export function getRuntimeHostActivation() {
  return request<StrategyActivationRecord | null>('/api/runtime-host/activation/latest')
}

export function getRuntimeHostModel() {
  return request<ModelWeightSnapshot | null>('/api/runtime-host/model/latest')
}

export function getRuntimeHostSelection() {
  return request<OpportunitySelectionRecord | null>('/api/runtime-host/selection/latest')
}

export function getConfigProposals() {
  return request<ConfigProposal[]>('/api/config/proposals')
}

export function getEvidence(category: EvidenceCategory) {
  return request<EvidenceItem[]>(`/api/evidence/${category}`)
}

export function getIncidents() {
  return request<IncidentRecord[]>('/api/platform/incidents')
}

export function getResearch() {
  return request<ResearchStudioSnapshot>('/api/platform/research')
}

export function getPortfolioWorkspace() {
  return request<PortfolioWorkspaceSnapshot>('/api/platform/portfolio')
}

export function getPerformanceAnalytics() {
  return request<PerformanceAnalyticsSnapshot>('/api/platform/performance')
}

export function getReplay(params: {
  symbol?: string
  cycle_id?: string
  incident_id?: string
}) {
  const query = new URLSearchParams()
  if (params.symbol) {
    query.set('symbol', params.symbol)
  }
  if (params.cycle_id) {
    query.set('cycle_id', params.cycle_id)
  }
  if (params.incident_id) {
    query.set('incident_id', params.incident_id)
  }
  return request<ReplaySession>(`/api/platform/replay?${query.toString()}`)
}

export function getExplorer(params: { query?: string; category?: string }) {
  const query = new URLSearchParams()
  if (params.query) {
    query.set('query', params.query)
  }
  if (params.category) {
    query.set('category', params.category)
  }
  return request<ExplorerRecord[]>(`/api/platform/explorer?${query.toString()}`)
}

export function getLatestDigest() {
  return request<DailySessionDigest | null>('/api/platform/digests/latest')
}

export function getGate3Readiness() {
  return request<Gate3ReadinessReport>('/api/platform/gate3/readiness')
}

export function getGate3PromotionPackage() {
  return request<Gate3PromotionPackage | null>('/api/platform/gate3/promotions/latest')
}

export function getReplaySlippageSummary() {
  return request<ReplaySlippageSummary | null>('/api/platform/gate3/replay-slippage/latest')
}

export function getMarketAutomationRun() {
  return request<MarketAutomationRunRecord | null>('/api/platform/gate3/automation/latest')
}

export function getSchedulerState() {
  return request<MarketDaySchedulerState>('/api/platform/gate3/scheduler/state')
}

export function getLatestMarketDaySchedule() {
  return request<MarketDayScheduleRecord | null>('/api/platform/gate3/scheduler/latest')
}

export function getMarketSessions() {
  return request<MarketSessionRecord[]>('/api/evidence/market_sessions')
}

export function getRecoveryDrills() {
  return request<RecoveryDrillRecord[]>('/api/evidence/recovery_drills')
}

export function getAlertDrills() {
  return request<AlertDrillRecord[]>('/api/evidence/alert_drills')
}

export function postPaperLoop(payload: { symbol: string; quantity: string }) {
  return request<ActionResult>('/api/actions/paper-loop', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postServiceStart(payload: {
  symbols: string[]
  quantity: string
  interval_seconds: number
  max_cycles: number | null
}) {
  return request<ActionResult>('/api/actions/service/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postServiceStop() {
  return request<ActionResult>('/api/actions/service/stop', {
    method: 'POST',
  })
}

export function postRuntimeHostStart(payload: {
  symbols: string[]
  quantity: string
  interval_seconds: number
  max_cycles: number | null
}) {
  return request<ActionResult>('/api/actions/runtime-host/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postRuntimeHostStop() {
  return request<ActionResult>('/api/actions/runtime-host/stop', {
    method: 'POST',
  })
}

export function postSchedulerStart(payload: {
  symbols: string[]
  quantity: string
  interval_seconds: number
  poll_interval_seconds: number
  max_scheduled_days: number | null
}) {
  return request<ActionResult>('/api/actions/scheduler/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postSchedulerStop() {
  return request<ActionResult>('/api/actions/scheduler/stop', {
    method: 'POST',
  })
}

export function postRecover(payload: { symbol: string }) {
  return request<ActionResult>('/api/actions/recover', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postPrepareBenchmark(payload: {
  window_start: string
  window_end: string
}) {
  return request<ActionResult>('/api/actions/prepare-benchmark', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postGateReport(payload: {
  gate: string
  benchmark_stack_file: string
  window_start: string
  window_end: string
  universe: string[]
}) {
  return request<ActionResult>('/api/actions/gate-report', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postDecisionReport(payload: { gate: string | null }) {
  return request<ActionResult>('/api/actions/decision-report', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postSessionPreopen() {
  return request<ActionResult>('/api/actions/session/preopen', {
    method: 'POST',
  })
}

export function postSessionHeartbeat() {
  return request<ActionResult>('/api/actions/session/heartbeat', {
    method: 'POST',
  })
}

export function postSessionClose() {
  return request<ActionResult>('/api/actions/session/close', {
    method: 'POST',
  })
}

export function postMarketDayAutomation(payload: {
  symbols: string[]
  quantity: string
  interval_seconds: number
  max_heartbeats: number | null
}) {
  return request<ActionResult>('/api/actions/session/market-day', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postAcknowledgeIncident(incidentId: string) {
  return request<ActionResult>(`/api/actions/incidents/${incidentId}/acknowledge`, {
    method: 'POST',
  })
}

export function postRecoveryDrill(payload: { symbol: string }) {
  return request<ActionResult>('/api/actions/recovery-drill', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postAlertDrill(payload: { channel: string }) {
  return request<ActionResult>('/api/actions/alert-drill', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postGate3Report() {
  return request<ActionResult>('/api/actions/gate3/report', {
    method: 'POST',
  })
}

export function postGate3Package() {
  return request<ActionResult>('/api/actions/gate3/package', {
    method: 'POST',
  })
}

export function postReplaySlippageReport() {
  return request<ActionResult>('/api/actions/replay-slippage/generate', {
    method: 'POST',
  })
}

export function postProposal(payload: {
  target_area: string
  rationale: string
  proposed_values: Record<string, unknown>
}) {
  return request<ConfigProposal>('/api/config/proposals', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export const KILL_SWITCH_ENDPOINT_AVAILABLE = false
export const FLATTEN_ALL_ENDPOINT_AVAILABLE = false

export function postKillSwitch(): Promise<ActionResult> {
  if (!KILL_SWITCH_ENDPOINT_AVAILABLE) {
    return Promise.reject(
      new Error(
        'Kill Switch endpoint is not implemented in the backend yet. Use the runbook to activate kill state.',
      ),
    )
  }
  return request<ActionResult>('/api/actions/kill-switch', { method: 'POST' })
}

export function postFlattenAll(): Promise<ActionResult> {
  if (!FLATTEN_ALL_ENDPOINT_AVAILABLE) {
    return Promise.reject(
      new Error(
        'Flatten All endpoint is not implemented in the backend yet. Use the closeout runbook.',
      ),
    )
  }
  return request<ActionResult>('/api/actions/flatten-all', { method: 'POST' })
}
