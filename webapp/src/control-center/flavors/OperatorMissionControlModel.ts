import { prettyLabel } from '../../platform/format'
import type { RiskTone } from '../shell/TopStatusStrip'

export type VerdictTone = 'good' | 'watch' | 'risk' | 'info'

export function describeTradePermission(args: {
  liveTradingEnabled: boolean
  paperOnlyMode: boolean
  killSwitchActive: boolean
  gateTone: RiskTone
  runtimeStatus: string
  evidenceStale: boolean
}): { value: string; detail: string; tone: VerdictTone; evidence: string } {
  if (args.killSwitchActive) {
    return {
      value: 'Blocked',
      detail: 'Manual kill switch is active.',
      tone: 'risk',
      evidence: 'Declared safety control from live-disable report',
    }
  }
  if (args.gateTone === 'risk') {
    return {
      value: 'Blocked by gates',
      detail: 'At least one risk or validation gate is failing.',
      tone: 'risk',
      evidence: 'Calculated from current gate statuses',
    }
  }
  if (args.gateTone === 'watch') {
    return {
      value: 'Review first',
      detail: 'A gate is degraded or watching. Inspect Risk & Safety before allowing more activity.',
      tone: 'watch',
      evidence: 'Calculated from current gate statuses',
    }
  }
  if (/fail|halt|error|crash|dead/i.test(args.runtimeStatus)) {
    return {
      value: 'Runtime unhealthy',
      detail: `Runtime is ${prettyLabel(args.runtimeStatus)}. Do not treat paper-only mode as a safe-to-run signal.`,
      tone: 'risk',
      evidence: 'Calculated from runtime host status',
    }
  }
  if (args.liveTradingEnabled) {
    return {
      value: 'Live flag on',
      detail: 'Live trading appears enabled in config. Confirm authority boundary before any action.',
      tone: 'risk',
      evidence: 'Declared config from live-disable report',
    }
  }
  if (args.evidenceStale) {
    return {
      value: 'Verify evidence',
      detail: 'Source evidence is stale or missing. Confirm runtime and data freshness before allowing activity.',
      tone: 'watch',
      evidence: 'Calculated from required safety evidence timestamps',
    }
  }
  if (args.paperOnlyMode) {
    return {
      value: 'Paper only',
      detail: `Runtime is ${prettyLabel(args.runtimeStatus || 'idle')}; live execution is disabled.`,
      tone: 'good',
      evidence: 'Declared paper-only mode plus calculated gate state',
    }
  }
  return {
    value: 'Needs review',
    detail: 'Trading mode is not clearly paper-only from the current config summary.',
    tone: 'watch',
    evidence: 'Missing or ambiguous execution-mode evidence',
  }
}

function latestTimestamp(values: Array<string | null | undefined>): string | null {
  let latest: { value: string; ms: number } | null = null
  for (const value of values) {
    if (!value) continue
    const ms = new Date(value).getTime()
    if (Number.isNaN(ms)) continue
    if (!latest || ms > latest.ms) {
      latest = { value, ms }
    }
  }
  return latest?.value ?? null
}

export function latestSourceEvidenceTimestamp(args: {
  uiRefreshTimestamp: string | null | undefined
  sourceTimestamps: Array<string | null | undefined>
}): string | null {
  void args.uiRefreshTimestamp
  return latestTimestamp(args.sourceTimestamps)
}

export type RequiredSafetyEvidence = {
  stale: boolean
  missing: string[]
  staleClasses: string[]
  latestRequiredTimestamp: string | null
}

export type GateEvidenceCriterion = {
  criterion_id?: string
  required?: boolean
  source_evidence_at_utc?: string | null
} & Record<string, unknown>

export function deriveRequiredSafetyEvidence(args: {
  nowMs: number
  staleMinutes: number
  heartbeatTimestamp: string | null | undefined
  gateTimestamp: string | null | undefined
  portfolioTimestamp: string | null | undefined
  decisionTimestamp: string | null | undefined
}): RequiredSafetyEvidence {
  const required = [
    { label: 'heartbeat evidence', timestamp: args.heartbeatTimestamp },
    { label: 'gate evidence', timestamp: args.gateTimestamp },
    { label: 'portfolio evidence', timestamp: args.portfolioTimestamp },
    { label: 'decision evidence', timestamp: args.decisionTimestamp },
  ]
  const missing: string[] = []
  const staleClasses: string[] = []
  for (const item of required) {
    if (!item.timestamp) {
      missing.push(item.label)
      continue
    }
    const ms = new Date(item.timestamp).getTime()
    if (Number.isNaN(ms)) {
      missing.push(item.label)
      continue
    }
    const ageMinutes = (args.nowMs - ms) / 60_000
    if (ageMinutes > args.staleMinutes) {
      staleClasses.push(item.label)
    }
  }
  return {
    stale: missing.length > 0 || staleClasses.length > 0,
    missing,
    staleClasses,
    latestRequiredTimestamp: latestTimestamp(required.map((item) => item.timestamp)),
  }
}

export function deriveGateEvidenceTimestamp(args: {
  commandCenterGeneratedAt: string | null | undefined
  gateStatuses: Record<string, string> | null | undefined
  gate3GeneratedAt: string | null | undefined
  gate3Criteria: GateEvidenceCriterion[] | null | undefined
  oldestRequiredSourceEvidenceAtUtc?: string | null | undefined
  missingSourceCriterionIds?: string[] | null | undefined
  requiredCriterionIds?: string[] | null | undefined
}): string | null {
  void args.commandCenterGeneratedAt
  void args.gateStatuses
  void args.gate3GeneratedAt
  const missingIds = args.missingSourceCriterionIds ?? []
  if (missingIds.length > 0) {
    return null
  }
  if (args.oldestRequiredSourceEvidenceAtUtc) {
    return args.oldestRequiredSourceEvidenceAtUtc
  }
  const requiredIds = new Set(args.requiredCriterionIds ?? [])
  const requiredCriteria = (args.gate3Criteria ?? []).filter((criterion) => {
    if (criterion.required) return true
    return Boolean(criterion.criterion_id && requiredIds.has(criterion.criterion_id))
  })
  if (requiredCriteria.length === 0) {
    return null
  }
  const timestamps = requiredCriteria.map((criterion) => criterion.source_evidence_at_utc)
  if (timestamps.some((timestamp) => !timestamp)) {
    return null
  }
  if (timestamps.some((timestamp) => Number.isNaN(new Date(timestamp ?? '').getTime()))) {
    return null
  }
  return oldestTimestamp(timestamps)
}

export function deriveDecisionEvidenceTimestamp(args: {
  lastDecision: string | null | undefined
  decision: string | null | undefined
  selectionId: string | null | undefined
  selectionGeneratedAt: string | null | undefined
  decisionSourceAtUtc?: string | null | undefined
}): string | null {
  void args.selectionGeneratedAt
  const label = `${args.lastDecision ?? ''} ${args.decision ?? ''}`.trim().toLowerCase()
  const placeholder = !label || /no decision|awaiting|pending|unavailable/.test(label)
  if (placeholder || !args.selectionId || !args.decisionSourceAtUtc) {
    return null
  }
  return args.decisionSourceAtUtc
}

function oldestTimestamp(values: Array<string | null | undefined>): string | null {
  let oldest: { value: string; ms: number } | null = null
  for (const value of values) {
    if (!value) continue
    const ms = new Date(value).getTime()
    if (Number.isNaN(ms)) continue
    if (!oldest || ms < oldest.ms) {
      oldest = { value, ms }
    }
  }
  return oldest?.value ?? null
}

export function deriveCombinedGateTone(args: {
  commandCenterGates: Record<string, string>
  gate3Criteria: Array<{ status?: string; criterion_id?: string }>
}): { tone: RiskTone; label: string; detail: string } {
  const commandEntries = Object.entries(args.commandCenterGates ?? {})
  const gate3Entries = (args.gate3Criteria ?? []).map((criterion) => [
    criterion.criterion_id ?? 'gate3',
    criterion.status ?? '',
  ] as const)
  const entries = [...commandEntries, ...gate3Entries.map(([id, status]) => [`Gate 3 ${id}`, status] as const)]
  if (entries.length === 0) {
    return { tone: 'neutral', label: 'No gates', detail: 'No gate source evidence yet.' }
  }
  const failing = entries.filter(([, status]) => /fail|block|error|risk/i.test(status))
  if (failing.length > 0) {
    return {
      tone: 'risk',
      label: 'Risk',
      detail: `${failing.length} gate${failing.length === 1 ? '' : 's'} failing, including ${prettyLabel(failing[0][0])}`,
    }
  }
  const watching = entries.filter(([, status]) => /watch|warn|degrad/i.test(status))
  if (watching.length > 0) {
    return {
      tone: 'watch',
      label: 'Watch',
      detail: `${watching.length} gate${watching.length === 1 ? '' : 's'} watching, including ${prettyLabel(watching[0][0])}`,
    }
  }
  const passingStatuses = new Set(['pass', 'good', 'ok', 'ready', 'complete'])
  const notPassing = entries.filter(([, status]) => !passingStatuses.has(status.trim().toLowerCase()))
  if (notPassing.length > 0) {
    return {
      tone: 'watch',
      label: 'Watch',
      detail: `${notPassing.length} gate${notPassing.length === 1 ? '' : 's'} pending or incomplete, including ${prettyLabel(notPassing[0][0])}`,
    }
  }
  return { tone: 'good', label: 'Normal', detail: 'All gate source evidence passing' }
}
