import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  CalendarClock,
  CheckCircle2,
  CircleSlash,
  FileWarning,
  Gauge,
  GitBranch,
} from 'lucide-react'

import { formatTimestamp, parseNumericValue, prettyLabel, toCurrency } from '../../platform/format'
import type { IncidentRecord } from '../../types'
import { describePnl } from '../shell/TopStatusStrip'
import { useData } from '../state/DataContext'
import { usePreferences } from '../state/PreferencesContext'
import type { ViewFlavor } from '../state/types'

import styles from './Flavor.module.css'
import {
  describeTradePermission,
  deriveCombinedGateTone,
  deriveDecisionEvidenceTimestamp,
  deriveGateEvidenceTimestamp,
  deriveRequiredSafetyEvidence,
  latestSourceEvidenceTimestamp,
  type VerdictTone,
} from './OperatorMissionControlModel'

type StatusCardModel = {
  id: string
  label: string
  value: string
  detail: string
  tone: VerdictTone
  evidence: string
  route: ViewFlavor
}

type AttentionItem = {
  id: string
  title: string
  detail: string
  tone: VerdictTone
  route: ViewFlavor
}

const STALE_MINUTES = 20

export function OperatorMissionControlFlavor() {
  const data = useData()
  const { setActiveFlavor } = usePreferences()
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    const id = window.setInterval(() => {
      setNowMs(Date.now())
    }, 60_000)
    return () => window.clearInterval(id)
  }, [])

  const {
    commandCenter,
    configSummary,
    runtimeState,
    runtimeHeartbeat,
    incidents,
    digest,
    portfolio,
    gate3Readiness,
    research,
    replay,
    explorer,
    schedulerState,
    generatedAt,
    runtimeSelection,
  } = data

  const gateTone = deriveCombinedGateTone({
    commandCenterGates: commandCenter.gate_statuses,
    gate3Criteria: gate3Readiness.criteria,
  })
  const unacknowledged = incidents.filter((incident) => !incident.acknowledged_at_utc)
  const openPositions = portfolio.positions_panel.positions
  const latestEvidenceAt = latestSourceEvidenceTimestamp({
    uiRefreshTimestamp: generatedAt,
    sourceTimestamps: [
      commandCenter.generated_at_utc,
      portfolio.generated_at_utc,
      research.generated_at_utc,
      gate3Readiness.generated_at_utc,
      digest?.generated_at_utc,
      runtimeHeartbeat.last_evaluation_at_utc,
      runtimeState.updated_at_utc,
      ...replay.events.map((event) => event.occurred_at_utc),
      ...explorer.map((record) => record.recorded_at_utc),
    ],
  })
  const evidenceAge = latestEvidenceAt ? ageMinutes(latestEvidenceAt, nowMs) : null
  const decisionEvidenceAt = deriveDecisionEvidenceTimestamp({
    lastDecision: runtimeHeartbeat.last_decision,
    decision: runtimeHeartbeat.decision,
    selectionId: runtimeSelection?.selection_id,
    selectionGeneratedAt: runtimeSelection?.generated_at_utc,
  })
  const requiredSafetyEvidence = deriveRequiredSafetyEvidence({
    nowMs,
    staleMinutes: STALE_MINUTES,
    heartbeatTimestamp: runtimeHeartbeat.last_evaluation_at_utc,
    gateTimestamp: deriveGateEvidenceTimestamp({
      commandCenterGeneratedAt: commandCenter.generated_at_utc,
      gateStatuses: commandCenter.gate_statuses,
      gate3GeneratedAt: gate3Readiness.generated_at_utc,
      gate3Criteria: gate3Readiness.criteria,
    }),
    portfolioTimestamp: null,
    decisionTimestamp: decisionEvidenceAt,
  })
  const staleEvidence = requiredSafetyEvidence.stale

  const tradePermission = describeTradePermission({
    liveTradingEnabled: configSummary.live_disable_report.live_trading_enabled,
    paperOnlyMode: configSummary.live_disable_report.paper_only_mode,
    killSwitchActive: configSummary.live_disable_report.manual_kill_switch_active,
    gateTone: gateTone.tone,
    runtimeStatus: runtimeState.status,
    evidenceStale: staleEvidence,
  })

  const cards = useMemo<StatusCardModel[]>(() => {
    const runtimeTone = runtimeStatusTone(runtimeState.status, runtimeHeartbeat.heartbeat_tone)
    const pnl = describePnl(commandCenter.account_summary.daily_pnl)
    const positionValue = openPositions.reduce(
      (sum, position) => sum + Math.abs(parseNumericValue(position.market_value)),
      0,
    )

    return [
      {
        id: 'runtime',
        label: 'Bot runtime',
        value: prettyLabel(runtimeState.status || runtimeHeartbeat.heartbeat_state || 'idle'),
        detail:
          runtimeHeartbeat.heartbeat_summary ||
          runtimeState.status_reason ||
          'Runtime has not published a detailed status yet.',
        tone: runtimeTone,
        evidence: runtimeHeartbeat.last_evaluation_at_utc
          ? `Calculated heartbeat at ${formatTimestamp(runtimeHeartbeat.last_evaluation_at_utc)}`
          : 'Missing heartbeat evidence',
        route: 'market-day-ops',
      },
      {
        id: 'permission',
        label: 'Allowed to trade',
        value: tradePermission.value,
        detail: tradePermission.detail,
        tone: tradePermission.tone,
        evidence: tradePermission.evidence,
        route: 'risk-core',
      },
      {
        id: 'pnl',
        label: 'Today P&L',
        value: pnl.display,
        detail: `${commandCenter.service_status.cycles_completed || 0} service cycles. Mode: ${
          configSummary.live_disable_report.paper_only_mode ? 'paper result' : 'live setting present'
        }.`,
        tone: pnl.tone === 'risk' ? 'risk' : pnl.tone === 'good' ? 'good' : 'info',
        evidence: commandCenter.generated_at_utc
          ? `Measured account snapshot at ${formatTimestamp(commandCenter.generated_at_utc)}`
          : 'Missing account snapshot evidence',
        route: 'market-chart',
      },
      {
        id: 'risk',
        label: 'Open risk',
        value: openPositions.length ? `${openPositions.length} position${openPositions.length === 1 ? '' : 's'}` : 'Flat',
        detail: openPositions.length
          ? `${toCurrency(positionValue)} gross position value from portfolio snapshot.`
          : portfolio.positions_panel.detail || 'No open paper positions reported.',
        tone: gateTone.tone === 'risk' ? 'risk' : openPositions.length ? 'watch' : 'good',
        evidence: portfolio.generated_at_utc
          ? `Calculated portfolio state at ${formatTimestamp(portfolio.generated_at_utc)}`
          : 'Missing portfolio evidence',
        route: 'portfolio-constellation',
      },
      {
        id: 'alerts',
        label: 'Operator attention',
        value: unacknowledged.length ? `${unacknowledged.length} open` : 'None open',
        detail: unacknowledged[0]?.title || 'No unacknowledged incidents in the current incident feed.',
        tone: worstIncidentTone(unacknowledged),
        evidence: unacknowledged[0]
          ? `Incident ${unacknowledged[0].incident_id} seen ${formatTimestamp(unacknowledged[0].latest_seen_at_utc)}`
          : 'Incident feed has no active items',
        route: 'risk-core',
      },
      {
        id: 'freshness',
        label: 'Evidence freshness',
        value: staleEvidence ? 'Stale or missing' : 'Current',
        detail: latestEvidenceAt
          ? `Newest local evidence is ${Math.max(0, Math.round(evidenceAge ?? 0))} minutes old.`
          : 'No timestamped local evidence has been loaded.',
        tone: staleEvidence ? 'watch' : 'good',
        evidence: requiredSafetyEvidence.stale
          ? describeRequiredEvidenceGap(requiredSafetyEvidence.missing, requiredSafetyEvidence.staleClasses)
          : latestEvidenceAt
            ? `Latest evidence timestamp ${formatTimestamp(latestEvidenceAt)}`
            : 'Missing evidence timestamp',
        route: 'evidence-replay',
      },
      {
        id: 'decision',
        label: 'Last trade decision',
        value: decisionEvidenceAt
          ? runtimeSelection?.decision || runtimeHeartbeat.last_decision || runtimeHeartbeat.decision || 'Decision evidence'
          : 'No decision evidence',
        detail: decisionEvidenceAt
          ? runtimeSelection?.decision_reason ||
            runtimeHeartbeat.decision_reason ||
            'Decision evidence exists, but structured signal, regime, risk-check, and execution fields are not fully exposed.'
          : 'No opportunity-selection evidence is available. Placeholder decision labels are not treated as evidence.',
        tone: decisionEvidenceAt ? 'info' : 'watch',
        evidence: decisionEvidenceAt
          ? `Decision evidence at ${formatTimestamp(decisionEvidenceAt)}`
          : 'Missing selection-backed decision evidence',
        route: 'evidence-replay',
      },
      {
        id: 'next-eval',
        label: 'Next evaluation',
        value: runtimeHeartbeat.next_evaluation_at_utc
          ? formatTimestamp(runtimeHeartbeat.next_evaluation_at_utc)
          : schedulerState.next_run_at_utc
            ? formatTimestamp(schedulerState.next_run_at_utc)
            : 'Not scheduled',
        detail: runtimeHeartbeat.cadence_label || `Scheduler ${prettyLabel(schedulerState.status)}`,
        tone: runtimeHeartbeat.next_evaluation_at_utc || schedulerState.next_run_at_utc ? 'info' : 'watch',
        evidence: schedulerState.last_error
          ? `Scheduler error: ${schedulerState.last_error}`
          : `Scheduler state: ${prettyLabel(schedulerState.status)}`,
        route: 'market-day-ops',
      },
    ]
  }, [
    commandCenter,
    configSummary,
    evidenceAge,
    gateTone.tone,
    latestEvidenceAt,
    openPositions,
    portfolio,
    decisionEvidenceAt,
    runtimeHeartbeat,
    runtimeSelection,
    runtimeState,
    schedulerState,
    requiredSafetyEvidence,
    staleEvidence,
    tradePermission,
    unacknowledged,
  ])

  const attention = useMemo<AttentionItem[]>(() => {
    const items: AttentionItem[] = []
    if (configSummary.live_disable_report.manual_kill_switch_active) {
      items.push({
        id: 'kill-switch',
        title: 'Manual kill switch is active',
        detail: 'Runtime resume remains blocked until the kill-switch evidence is cleared through the runbook.',
        tone: 'risk',
        route: 'risk-core',
      })
    }
    if (gateTone.tone === 'risk' || gateTone.tone === 'watch') {
      items.push({
        id: 'gates',
        title: `Risk gates require review: ${gateTone.label}`,
        detail: gateTone.detail,
        tone: gateTone.tone === 'risk' ? 'risk' : 'watch',
        route: 'risk-core',
      })
    }
    for (const incident of unacknowledged.slice(0, 3)) {
      items.push({
        id: incident.incident_id,
        title: incident.title,
        detail: incident.suggested_action || incident.summary,
        tone: incidentTone(incident),
        route: 'risk-core',
      })
    }
    if (staleEvidence) {
      items.push({
        id: 'stale-evidence',
        title: 'Evidence freshness is not current',
        detail: latestEvidenceAt
          ? `Newest timestamp is ${formatTimestamp(latestEvidenceAt)}. Confirm feeds and scheduled jobs before trusting fresh-state claims.`
          : 'No timestamped evidence is loaded. Dashboard claims should be treated as incomplete.',
        tone: 'watch',
        route: 'evidence-replay',
      })
    }
    if (!decisionEvidenceAt) {
      items.push({
        id: 'decision-missing',
        title: 'No structured trade decision is available',
        detail: 'Use Evidence & Why for raw events. Backend still needs selection-backed signal, regime, risk, and execution details.',
        tone: 'watch',
        route: 'evidence-replay',
      })
    }
    if (items.length === 0) {
      items.push({
        id: 'clear',
        title: 'No immediate operator blocker detected',
        detail: 'Continue monitoring runtime heartbeat, gate evidence, and current exposure.',
        tone: 'good',
        route: 'market-day-ops',
      })
    }
    return items
  }, [
    configSummary.live_disable_report.manual_kill_switch_active,
    gateTone,
    decisionEvidenceAt,
    latestEvidenceAt,
    staleEvidence,
    unacknowledged,
  ])

  const trustRows = [
    {
      label: 'Declared config',
      value: configSummary.live_disable_report.paper_only_mode ? 'Paper-only declared' : 'Live flags present',
      tone: configSummary.live_disable_report.live_trading_enabled ? 'risk' : 'info',
      detail: 'From config summary and live-disable report.',
    },
    {
      label: 'Calculated state',
      value: runtimeHeartbeat.heartbeat_state || 'Missing',
      tone: runtimeHeartbeat.last_evaluation_at_utc ? 'info' : 'watch',
      detail: runtimeHeartbeat.last_evaluation_at_utc
        ? `Heartbeat ${formatTimestamp(runtimeHeartbeat.last_evaluation_at_utc)}`
        : 'No heartbeat timestamp.',
    },
    {
      label: 'Measured result',
      value: commandCenter.account_summary.equity
        ? `${toCurrency(commandCenter.account_summary.equity)} equity`
        : 'Missing',
      tone: commandCenter.account_summary.equity ? 'info' : 'watch',
      detail: 'Account summary is treated as measured paper-account evidence.',
    },
    {
      label: 'Research/backtest',
      value: research.candidate_summaries.length
        ? `${research.candidate_summaries.length} candidates`
        : 'No candidates',
      tone: research.candidate_summaries.length ? 'info' : 'watch',
      detail: research.decision_summary || 'Research evidence is incomplete.',
    },
    {
      label: 'Paper/live-shadow/live',
      value: configSummary.live_disable_report.paper_only_mode ? 'Paper result' : 'Mode needs review',
      tone: configSummary.live_disable_report.paper_only_mode ? 'info' : 'watch',
      detail: 'Current API does not expose separate live-shadow and live result ledgers.',
    },
    {
      label: 'Missing evidence',
      value: describeRequiredEvidenceGap(
        requiredSafetyEvidence.missing,
        requiredSafetyEvidence.staleClasses,
      ),
      tone: 'watch',
      detail: 'Required safety evidence gaps are not shown as green.',
    },
  ]

  return (
    <div className={styles.gridShell}>
      <div className={styles.symbolHeader}>
        <div>
          <div className={styles.metricLabel}>Can the bot trade safely now?</div>
          <div className={styles.symbolMain}>{tradePermission.value}</div>
          <div className={styles.metricSub}>{tradePermission.detail}</div>
        </div>
        <dl className={styles.symbolMeta}>
          <dt>Runtime</dt>
          <dd>{prettyLabel(runtimeState.status || 'idle')}</dd>
          <dt>Market</dt>
          <dd>{prettyLabel(commandCenter.market_session_label || 'unknown')}</dd>
          <dt>Mode</dt>
          <dd>{configSummary.live_disable_report.paper_only_mode ? 'Paper' : 'Live review'}</dd>
          <dt>Evidence</dt>
          <dd>{staleEvidence ? 'Stale/missing' : 'Current'}</dd>
        </dl>
      </div>

      <div className={styles.kpis}>
        {cards.slice(0, 4).map((card) => (
          <MissionCard key={card.id} card={card} onOpen={setActiveFlavor} />
        ))}
      </div>

      <div className={styles.kpis}>
        {cards.slice(4).map((card) => (
          <MissionCard key={card.id} card={card} onOpen={setActiveFlavor} />
        ))}
      </div>

      <div className={styles.forgeRow}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>What needs operator attention</span>
            <span className={styles.panelSub}>{attention.length} item{attention.length === 1 ? '' : 's'}</span>
          </div>
          <div className={styles.panelBody}>
            {attention.map((item) => (
              <button
                key={item.id}
                type="button"
                className={styles.gateRecRow}
                style={{ width: '100%', textAlign: 'left' }}
                onClick={() => setActiveFlavor(item.route, 'manual')}
              >
                <ToneIcon tone={item.tone} />
                <span style={{ flex: 1 }}>
                  <strong>{item.title}</strong>
                  <span style={{ display: 'block', color: 'var(--text-muted)', fontSize: 11 }}>
                    {item.detail}
                  </span>
                </span>
                <ArrowRight size={13} />
              </button>
            ))}
          </div>
        </div>

        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Today at a glance</span>
            <span className={styles.panelSub}>Paper operator digest</span>
          </div>
          <div className={styles.panelBody}>
            <DigestRow
              icon={<CalendarClock size={14} />}
              label="Session"
              value={digest?.session_label || prettyLabel(commandCenter.session_mode || 'standby')}
              detail={digest ? `Digest ${digest.digest_id}` : 'No daily digest evidence loaded.'}
            />
            <DigestRow
              icon={<CircleSlash size={14} />}
              label="Blocked or skipped"
              value={digest ? String(digest.blocked_trade_count) : 'Unknown'}
              detail="Blocked count comes from the latest digest when available."
            />
            <DigestRow
              icon={<Gauge size={14} />}
              label="Current exposure"
              value={runtimeHeartbeat.current_exposure || portfolio.positions_panel.headline || 'Flat'}
              detail={runtimeHeartbeat.current_exposure_detail || portfolio.positions_panel.detail}
            />
            <DigestRow
              icon={<GitBranch size={14} />}
              label="Active strategy"
              value={runtimeState.active_strategy_id || 'No active strategy'}
              detail={runtimeState.active_model_snapshot_id || 'No active model snapshot evidence.'}
            />
          </div>
        </div>
      </div>

      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span>Evidence trust ledger</span>
          <span className={styles.panelSub}>No confidence without evidence</span>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className={styles.simpleTable}>
            <thead>
              <tr>
                <th>Claim type</th>
                <th>Current label</th>
                <th>Evidence posture</th>
                <th>Why it matters</th>
              </tr>
            </thead>
            <tbody>
              {trustRows.map((row) => (
                <tr key={row.label}>
                  <td>{row.label}</td>
                  <td>{row.value}</td>
                  <td>
                    <span className={`badge badge-${row.tone}`}>{prettyLabel(row.tone)}</span>
                  </td>
                  <td>{row.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className={styles.forgeRow}>
        <DrilldownPanel
          title="Investigate a trade or skipped trade"
          detail="Open Evidence & Why to inspect timestamp, symbol, strategy, related IDs, artifact path, and logs currently exposed by the backend."
          button="Open Evidence & Why"
          route="evidence-replay"
          onOpen={setActiveFlavor}
        />
        <DrilldownPanel
          title="Review performance and risk"
          detail="Open P&L / Positions for the equity curve, benchmark rows, account state, and exposure context."
          button="Open P&L / Positions"
          route="market-chart"
          onOpen={setActiveFlavor}
        />
      </div>
    </div>
  )
}

function MissionCard({
  card,
  onOpen,
}: {
  card: StatusCardModel
  onOpen: (flavor: ViewFlavor, source: 'manual') => void
}) {
  return (
    <button
      type="button"
      className={styles.metric}
      style={{ textAlign: 'left', minHeight: 156 }}
      onClick={() => onOpen(card.route, 'manual')}
    >
      <span className={styles.metricLabel}>{card.label}</span>
      <span className={styles.metricValue} style={{ color: toneColor(card.tone) }}>
        {card.value}
      </span>
      <span className={styles.metricSub}>{card.detail}</span>
      <span className={styles.disabledNote} style={{ marginTop: 'auto' }}>
        {card.evidence}
      </span>
    </button>
  )
}

function DigestRow({
  icon,
  label,
  value,
  detail,
}: {
  icon: React.ReactNode
  label: string
  value: string
  detail: string
}) {
  return (
    <div className={styles.gateRecRow}>
      {icon}
      <span style={{ flex: 1 }}>
        <span style={{ display: 'block', color: 'var(--text-muted)', fontSize: 11 }}>
          {label}
        </span>
        <strong>{value || 'Unavailable'}</strong>
        <span style={{ display: 'block', color: 'var(--text-muted)', fontSize: 11 }}>
          {detail || 'No detail available.'}
        </span>
      </span>
    </div>
  )
}

function DrilldownPanel({
  title,
  detail,
  button,
  route,
  onOpen,
}: {
  title: string
  detail: string
  button: string
  route: ViewFlavor
  onOpen: (flavor: ViewFlavor, source: 'manual') => void
}) {
  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <span>{title}</span>
      </div>
      <div className={styles.panelBody}>
        <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{detail}</p>
        <button type="button" className="btn btn-sm btn-primary" onClick={() => onOpen(route, 'manual')}>
          {button} <ArrowRight size={12} />
        </button>
      </div>
    </div>
  )
}

function ToneIcon({ tone }: { tone: VerdictTone }) {
  if (tone === 'good') return <CheckCircle2 size={14} color="var(--good)" />
  if (tone === 'risk') return <AlertTriangle size={14} color="var(--risk)" />
  if (tone === 'watch') return <FileWarning size={14} color="var(--watch)" />
  return <BookOpenCheck size={14} color="var(--primary-bright)" />
}

function runtimeStatusTone(status: string, heartbeatTone: string): VerdictTone {
  const lowered = `${status} ${heartbeatTone}`.toLowerCase()
  if (/fail|halt|risk|error/.test(lowered)) return 'risk'
  if (/pause|warm|watch|warn|idle/.test(lowered)) return 'watch'
  if (/run|start|good|ok|pass/.test(lowered)) return 'good'
  return 'info'
}

function incidentTone(incident: IncidentRecord): VerdictTone {
  const value = `${incident.severity} ${incident.status}`.toLowerCase()
  if (/critical|high|risk|fail|open/.test(value)) return 'risk'
  if (/warn|watch|medium/.test(value)) return 'watch'
  return 'info'
}

function worstIncidentTone(incidents: IncidentRecord[]): VerdictTone {
  if (incidents.length === 0) return 'good'
  if (incidents.some((incident) => incidentTone(incident) === 'risk')) return 'risk'
  if (incidents.some((incident) => incidentTone(incident) === 'watch')) return 'watch'
  return 'info'
}

function ageMinutes(timestamp: string, nowMs: number): number {
  return (nowMs - new Date(timestamp).getTime()) / 60_000
}

function toneColor(tone: VerdictTone): string {
  if (tone === 'good') return 'var(--good)'
  if (tone === 'watch') return 'var(--watch)'
  if (tone === 'risk') return 'var(--risk)'
  return 'var(--primary-bright)'
}

function describeRequiredEvidenceGap(missing: string[], staleClasses: string[]): string {
  const parts = []
  if (missing.length > 0) {
    parts.push(`Missing ${missing.join(', ')}`)
  }
  if (staleClasses.length > 0) {
    parts.push(`Stale ${staleClasses.join(', ')}`)
  }
  return parts.join('; ') || 'Required safety evidence is current'
}
