import { useEffect, useMemo, useState } from 'react'

import type {
  CommandCenterSnapshot,
  Gate3ReadinessReport,
  IncidentRecord,
  MarketDaySchedulerState,
} from '../../types'

import type { AutoSwitchSuggestion, ViewFlavor } from './types'

const RECENT_INTERACTION_WINDOW_MS = 60_000
const ACTIVITY_THROTTLE_MS = 1_000

export type AutoSwitchInput = {
  enabled: boolean
  manualOverride: boolean
  activeFlavor: ViewFlavor
  commandCenter: CommandCenterSnapshot
  incidents: IncidentRecord[]
  schedulerState: MarketDaySchedulerState
  gate3Readiness: Gate3ReadinessReport
}

function hasFailingGate(commandCenter: CommandCenterSnapshot): boolean {
  return Object.values(commandCenter.gate_statuses ?? {}).some((status) =>
    /fail|risk|block|error/i.test(status),
  )
}

function hasOpenIncident(incidents: IncidentRecord[]): boolean {
  return incidents.some((incident) => {
    if (incident.acknowledged_at_utc) {
      return false
    }
    return /critical|high|warn|risk/i.test(incident.severity)
  })
}

function isPreOpenWindow(scheduler: MarketDaySchedulerState, nowMs: number): boolean {
  if (scheduler.status === 'pending' || scheduler.status === 'preopen') {
    return true
  }
  if (!scheduler.next_run_at_utc) {
    return false
  }
  const next = new Date(scheduler.next_run_at_utc).getTime()
  if (Number.isNaN(next)) {
    return false
  }
  const minutesUntil = (next - nowMs) / 60_000
  return minutesUntil > 0 && minutesUntil <= 30
}

function gate3Pending(report: Gate3ReadinessReport): boolean {
  return /pending|fail|incomplete/i.test(report.status)
}

export type AutoSwitchContext = AutoSwitchInput & { nowMs: number }

export function deriveAutoSwitchSuggestion(input: AutoSwitchContext): AutoSwitchSuggestion | null {
  if (!input.enabled || input.manualOverride) {
    return null
  }
  if (hasFailingGate(input.commandCenter) || hasOpenIncident(input.incidents)) {
    if (input.activeFlavor === 'risk-core') {
      return null
    }
    return {
      flavor: 'risk-core',
      reason: hasOpenIncident(input.incidents) ? 'risk-incident' : 'gate-fail',
      detail: hasOpenIncident(input.incidents)
        ? 'Open incident detected — Risk Core has gate detail and acknowledgement actions.'
        : 'Gate status degraded — Risk Core shows blocking gate detail.',
    }
  }
  if (isPreOpenWindow(input.schedulerState, input.nowMs)) {
    if (input.activeFlavor === 'market-day-ops') {
      return null
    }
    return {
      flavor: 'market-day-ops',
      reason: 'pre-open-checklist',
      detail: 'Pre-open window active — Market Day Ops shows the readiness timeline.',
    }
  }
  if (gate3Pending(input.gate3Readiness) && input.gate3Readiness.criteria.length > 0) {
    if (input.activeFlavor === 'strategy-forge') {
      return null
    }
    return {
      flavor: 'strategy-forge',
      reason: 'strategy-proposal',
      detail: 'Gate 3 promotion in review — Strategy Forge surfaces proposal evidence.',
    }
  }
  return null
}

export function useAutoSwitchSuggestion(input: AutoSwitchInput): AutoSwitchSuggestion | null {
  const [lastActivityMs, setLastActivityMs] = useState(0)
  const [nowMs, setNowMs] = useState<number>(() => Date.now())

  useEffect(() => {
    let last = 0
    function recordActivity() {
      const ts = Date.now()
      if (ts - last < ACTIVITY_THROTTLE_MS) {
        return
      }
      last = ts
      setLastActivityMs(ts)
    }
    window.addEventListener('pointerdown', recordActivity, { passive: true })
    window.addEventListener('keydown', recordActivity, { passive: true })
    return () => {
      window.removeEventListener('pointerdown', recordActivity)
      window.removeEventListener('keydown', recordActivity)
    }
  }, [])

  useEffect(() => {
    if (!input.enabled) {
      return
    }
    const id = window.setInterval(() => {
      setNowMs(Date.now())
    }, 5_000)
    return () => {
      window.clearInterval(id)
    }
  }, [input.enabled])

  return useMemo(() => {
    if (lastActivityMs > 0 && nowMs - lastActivityMs < RECENT_INTERACTION_WINDOW_MS) {
      return null
    }
    return deriveAutoSwitchSuggestion({ ...input, nowMs })
  }, [input, lastActivityMs, nowMs])
}
