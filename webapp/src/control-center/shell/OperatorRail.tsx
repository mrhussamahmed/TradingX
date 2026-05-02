import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowRightCircle,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Info,
  Octagon,
  Play,
  ShieldAlert,
  Zap,
} from 'lucide-react'

import { formatTimestamp, prettyLabel } from '../../platform/format'
import type {
  BotRuntimeState,
  CommandCenterSnapshot,
  ConfigSummary,
  Gate3ReadinessReport,
  IncidentRecord,
  RuntimeHeartbeatSnapshot,
} from '../../types'
import { usePreferences } from '../state/PreferencesContext'

import { deriveRiskTone } from './TopStatusStrip'
import { isRuntimeActive, runtimeStatusTone } from './runtimeStatus'
import styles from './Shell.module.css'

const COLLAPSE_BREAKPOINT_PX = 1280

export type OperatorRailProps = {
  commandCenter: CommandCenterSnapshot
  runtimeState: BotRuntimeState
  runtimeHeartbeat: RuntimeHeartbeatSnapshot
  configSummary: ConfigSummary
  incidents: IncidentRecord[]
  gate3Readiness: Gate3ReadinessReport
  writeMode: { enabled: boolean; configured: boolean; unlocked: boolean; detail: string }
  onRequestKillSwitch: () => void
  onRequestFlattenAll: () => void
  onRequestResume: () => void
  onOpenGateReport: () => void
  onOpenAlertsCenter: () => void
  onOpenRuntimeHost: () => void
  onCollapsedChange?: (collapsed: boolean) => void
}

export type ResumeBlocker = {
  blocked: boolean
  reason: string
}

// eslint-disable-next-line react-refresh/only-export-components
export function deriveResumeBlocker(args: {
  runtimeState: BotRuntimeState
  runtimeHeartbeat: RuntimeHeartbeatSnapshot
  commandCenter: CommandCenterSnapshot
  configSummary: ConfigSummary
  writeUnlocked: boolean
}): ResumeBlocker {
  if (!args.configSummary.config.web_write_mode_enabled) {
    return {
      blocked: true,
      reason: 'Start blocked: server write mode is disabled.',
    }
  }
  if (!args.writeUnlocked) {
    return {
      blocked: true,
      reason: 'Start blocked: enter the local signing secret to unlock writes.',
    }
  }
  if (args.configSummary.live_disable_report.manual_kill_switch_active) {
    return {
      blocked: true,
      reason: 'Start blocked: manual kill switch is active. Clear the kill-switch evidence before starting.',
    }
  }
  if (
    !Array.isArray(args.configSummary.config.symbol_universe) ||
    args.configSummary.config.symbol_universe.length === 0
  ) {
    return {
      blocked: true,
      reason: 'Start blocked: configured symbol universe is empty. Configure at least one symbol before starting.',
    }
  }
  if (isRuntimeActive(args.runtimeState.status)) {
    return {
      blocked: true,
      reason: 'Start blocked: runtime host is already running.',
    }
  }
  const risk = deriveRiskTone(args.commandCenter.gate_statuses)
  if (risk.tone === 'risk') {
    const failingGate = Object.entries(args.commandCenter.gate_statuses ?? {}).find(([, status]) =>
      /fail|block|error|risk/i.test(status),
    )
    const gateName = failingGate ? prettyLabel(failingGate[0]) : 'a risk gate'
    return {
      blocked: true,
      reason: `Start blocked: ${gateName} is failing. Open Risk Core to inspect required action.`,
    }
  }
  return { blocked: false, reason: '' }
}

export function OperatorRail({
  commandCenter,
  runtimeState,
  runtimeHeartbeat,
  configSummary,
  incidents,
  gate3Readiness,
  writeMode,
  onRequestKillSwitch,
  onRequestFlattenAll,
  onRequestResume,
  onOpenGateReport,
  onOpenAlertsCenter,
  onOpenRuntimeHost,
  onCollapsedChange,
}: OperatorRailProps) {
  const { prefs } = usePreferences()
  const [viewportWidth, setViewportWidth] = useState<number>(() =>
    typeof window !== 'undefined' ? window.innerWidth : 1440,
  )
  const [manuallyCollapsed, setManuallyCollapsed] = useState<boolean | null>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return
    function handleResize() {
      setViewportWidth(window.innerWidth)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const unacknowledged = incidents.filter((incident) => !incident.acknowledged_at_utc)

  const collapsed = useMemo(() => {
    const hasCriticalAlert = incidents.some(
      (incident) => !incident.acknowledged_at_utc && /critical|high|risk/i.test(incident.severity),
    )
    if (prefs.pinEmergencyControls && viewportWidth >= COLLAPSE_BREAKPOINT_PX) {
      return manuallyCollapsed ?? false
    }
    if (manuallyCollapsed !== null) {
      return manuallyCollapsed
    }
    if (hasCriticalAlert) {
      return false
    }
    return viewportWidth < COLLAPSE_BREAKPOINT_PX
  }, [prefs.pinEmergencyControls, viewportWidth, manuallyCollapsed, incidents])

  useEffect(() => {
    onCollapsedChange?.(collapsed)
  }, [collapsed, onCollapsedChange])

  const resumeBlocker = useMemo(
    () =>
      deriveResumeBlocker({
        runtimeState,
        runtimeHeartbeat,
        commandCenter,
        configSummary,
        writeUnlocked: writeMode.unlocked,
      }),
    [runtimeState, runtimeHeartbeat, commandCenter, configSummary, writeMode.unlocked],
  )

  const risk = useMemo(
    () => deriveRiskTone(commandCenter.gate_statuses),
    [commandCenter.gate_statuses],
  )

  const allGatesPassing = risk.tone === 'good'
  const railLabel = collapsed ? 'Operator command rail (collapsed)' : 'Operator command rail'

  if (collapsed) {
    return (
      <aside
        className={`${styles.rail} ${styles.railCollapsed}`}
        aria-label={railLabel}
        data-collapsed="true"
      >
        <button
          type="button"
          className={styles.railToggle}
          onClick={() => setManuallyCollapsed(false)}
          aria-label="Expand operator rail"
          aria-expanded={false}
        >
          <ChevronsLeft size={14} />
        </button>
        <div className={styles.railCollapsedActions}>
          <button
            type="button"
            className={`${styles.railCollapsedAction} ${styles.kill}`}
            onClick={onRequestKillSwitch}
            aria-label="Kill Switch"
            title="Kill Switch"
          >
            <Octagon size={18} />
          </button>
          <button
            type="button"
            className={`${styles.railCollapsedAction} ${styles.flatten}`}
            onClick={onRequestFlattenAll}
            aria-label="Flatten All"
            title="Flatten All"
          >
            <Zap size={18} />
          </button>
          <button
            type="button"
            className={`${styles.railCollapsedAction} ${styles.resume}`}
            onClick={onRequestResume}
            disabled={resumeBlocker.blocked}
            aria-label="Start Paper Runtime"
            title={resumeBlocker.blocked ? resumeBlocker.reason : 'Start Paper Runtime'}
          >
            <Play size={18} />
          </button>
          {unacknowledged.length > 0 ? (
            <span className={styles.railCollapsedAlertBadge} aria-label={`${unacknowledged.length} unacknowledged alerts`}>
              {unacknowledged.length}
            </span>
          ) : null}
        </div>
      </aside>
    )
  }

  return (
    <aside className={styles.rail} aria-label={railLabel} data-collapsed="false">
      <div className={styles.railSectionTitleRow}>
        <span className={styles.railSectionTitle}>Operator Commands</span>
        <button
          type="button"
          className={styles.railToggle}
          onClick={() => setManuallyCollapsed(true)}
          aria-label="Collapse operator rail"
          aria-expanded
        >
          <ChevronsRight size={14} />
        </button>
      </div>

      <section className={styles.railSection} aria-label="Operator commands">
        <div className={styles.commandStack}>
          <button
            type="button"
            className={`${styles.commandButton} ${styles.commandKill}`}
            onClick={onRequestKillSwitch}
          >
            <Octagon className={styles.commandIcon} aria-hidden />
            <div className={styles.commandLabel}>
              <span>Kill Switch</span>
              <span className={styles.commandSub}>Stop all activity</span>
            </div>
          </button>
          <button
            type="button"
            className={`${styles.commandButton} ${styles.commandFlatten}`}
            onClick={onRequestFlattenAll}
          >
            <Zap className={styles.commandIcon} aria-hidden />
            <div className={styles.commandLabel}>
              <span>Flatten All</span>
              <span className={styles.commandSub}>Close all positions</span>
            </div>
          </button>
          <button
            type="button"
            className={`${styles.commandButton} ${styles.commandResume}`}
            onClick={onRequestResume}
            disabled={resumeBlocker.blocked}
          >
            <Play className={styles.commandIcon} aria-hidden />
            <div className={styles.commandLabel}>
              <span>Start Paper Runtime</span>
              <span className={styles.commandSub}>
                {resumeBlocker.blocked ? resumeBlocker.reason : 'Start paper evaluation loop'}
              </span>
            </div>
          </button>
        </div>
      </section>

      <section className={styles.railSection} aria-label="Runtime status">
        <div className={styles.railSectionTitleRow}>
          <span className={styles.railSectionTitle}>Runtime Status</span>
          <RuntimeBadge state={runtimeState} />
        </div>
        <dl className={styles.statTable}>
          <dt>Host</dt>
          <dd>{runtimeState.active_strategy_id || 'Idle'}</dd>
          <dt>Started</dt>
          <dd>{runtimeState.started_at_utc ? formatTimestamp(runtimeState.started_at_utc) : '—'}</dd>
          <dt>Cadence</dt>
          <dd>
            {runtimeHeartbeat.configured_cadence_seconds
              ? cadenceLabel(runtimeHeartbeat.configured_cadence_seconds)
              : runtimeHeartbeat.cadence_label || `${runtimeHeartbeat.cadence_seconds}s`}
            {runtimeHeartbeat.running_cadence_seconds &&
            runtimeHeartbeat.configured_cadence_seconds &&
            runtimeHeartbeat.running_cadence_seconds !== runtimeHeartbeat.configured_cadence_seconds
              ? ` configured · running ${cadenceLabel(runtimeHeartbeat.running_cadence_seconds)}`
              : ''}
          </dd>
          <dt>Last Eval</dt>
          <dd>
            {runtimeHeartbeat.last_evaluation_at_utc
              ? formatTimestamp(runtimeHeartbeat.last_evaluation_at_utc)
              : 'Awaiting'}
          </dd>
        </dl>
        <button type="button" className="btn btn-ghost" onClick={onOpenRuntimeHost}>
          View Runtime Host <ChevronRight size={14} />
        </button>
      </section>

      <section className={styles.railSection} aria-label="Gate status">
        <div className={styles.railSectionTitleRow}>
          <span className={styles.railSectionTitle}>Gate Status</span>
          <span className={`badge badge-${allGatesPassing ? 'good' : risk.tone === 'risk' ? 'risk' : 'watch'}`}>
            {allGatesPassing ? 'All Systems Go' : risk.label}
          </span>
        </div>
        <div>
          {Object.entries(commandCenter.gate_statuses ?? {}).length === 0 ? (
            <div className={styles.gateRow}>
              <span className={styles.gateLabel}>No gate evidence</span>
              <span className="badge badge-info">PENDING</span>
            </div>
          ) : (
            Object.entries(commandCenter.gate_statuses).map(([gateId, status]) => (
              <GateRow key={gateId} gateId={gateId} status={status} />
            ))
          )}
        </div>
        <button type="button" className="btn btn-ghost" onClick={onOpenGateReport}>
          View Gate Report <ChevronRight size={14} />
          {gate3Readiness.criteria.length > 0 ? (
            <span className="text-muted" style={{ fontSize: 11, marginLeft: 4 }}>
              ({gate3Readiness.status})
            </span>
          ) : null}
        </button>
      </section>

      <section className={styles.railSection} aria-label="Active alerts">
        <div className={styles.railSectionTitleRow}>
          <span className={styles.railSectionTitle}>
            Active Alerts{' '}
            <span className={unacknowledged.length > 0 ? 'text-risk numeric' : 'text-muted numeric'}>
              {unacknowledged.length}
            </span>
          </span>
          <button type="button" className={styles.railLink} onClick={onOpenAlertsCenter}>
            View All
          </button>
        </div>
        <div>
          {unacknowledged.length === 0 ? (
            <div className={styles.alertRow}>
              <Info className={styles.alertIcon} color="var(--primary-bright)" aria-hidden />
              <div>
                <div className={styles.alertTitle}>No active alerts</div>
                <div className={styles.alertDetail}>All incidents are acknowledged.</div>
              </div>
              <div className={styles.alertTime} />
            </div>
          ) : (
            unacknowledged.slice(0, 3).map((incident) => (
              <AlertRow key={incident.incident_id} incident={incident} />
            ))
          )}
        </div>
        <button type="button" className="btn btn-ghost" onClick={onOpenAlertsCenter}>
          Open Alerts Center <ArrowRightCircle size={14} />
        </button>
      </section>
    </aside>
  )
}

function cadenceLabel(seconds: number): string {
  if (seconds >= 3600) {
    const hours = seconds / 3600
    return hours === 1 ? '1 hour' : `${hours} hours`
  }
  return `${Math.round(seconds / 60)} minutes`
}

function RuntimeBadge({ state }: { state: BotRuntimeState }) {
  const tone = runtimeStatusTone(state.status)
  return <span className={`badge badge-${tone}`}>{prettyLabel(state.status || 'idle')}</span>
}

function GateRow({ gateId, status }: { gateId: string; status: string }) {
  const lowered = status.toLowerCase()
  const tone = /fail|block|error|risk/.test(lowered)
    ? 'risk'
    : /watch|warn|degrad/.test(lowered)
      ? 'watch'
      : /pass|ok|good|ready/.test(lowered)
        ? 'good'
        : 'info'
  const glyph = tone === 'good' ? '✓ PASS' : tone === 'watch' ? '⚠ WATCH' : tone === 'risk' ? '✕ FAIL' : prettyLabel(status)
  return (
    <div className={styles.gateRow}>
      <span className={styles.gateLabel}>{prettyLabel(gateId)}</span>
      <span className={`badge badge-${tone}`}>{glyph}</span>
    </div>
  )
}

function AlertRow({ incident }: { incident: IncidentRecord }) {
  const sev = incident.severity?.toLowerCase() ?? ''
  const Icon = /critical|high|risk/.test(sev)
    ? ShieldAlert
    : /watch|warn/.test(sev)
      ? AlertTriangle
      : Info
  const color = /critical|high|risk/.test(sev)
    ? 'var(--risk)'
    : /watch|warn/.test(sev)
      ? 'var(--watch)'
      : 'var(--primary-bright)'
  return (
    <div className={styles.alertRow}>
      <Icon className={styles.alertIcon} color={color} aria-hidden />
      <div>
        <div className={styles.alertTitle}>{incident.title}</div>
        <div className={styles.alertDetail}>{incident.summary}</div>
      </div>
      <div className={styles.alertTime}>
        {incident.latest_seen_at_utc ? formatTimestamp(incident.latest_seen_at_utc) : '—'}
      </div>
    </div>
  )
}
