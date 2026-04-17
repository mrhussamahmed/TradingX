import type {
  ActionResult,
  ConfigProposal,
  ConfigSummary,
  DashboardSnapshot,
  DocumentRecord,
  EvidenceCategory,
  EvidenceItem,
} from './types'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
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

export function getConfigSummary() {
  return request<ConfigSummary>('/api/config/summary')
}

export function getDocuments() {
  return request<DocumentRecord[]>('/api/documents')
}

export function getConfigProposals() {
  return request<ConfigProposal[]>('/api/config/proposals')
}

export function getEvidence(category: EvidenceCategory) {
  return request<EvidenceItem[]>(`/api/evidence/${category}`)
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

export function postRecover(payload: { symbol: string }) {
  return request<ActionResult>('/api/actions/recover', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function postPrepareBenchmark(payload: {
  symbol: string
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
  benchmark_closes_file: string
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
