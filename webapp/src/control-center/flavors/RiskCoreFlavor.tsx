import { useMemo, useState } from 'react'
import { CheckCircle2, RefreshCcw, ShieldAlert, ShieldCheck } from 'lucide-react'

import { postAcknowledgeIncident, postGate3Report } from '../../api'
import { formatTimestamp, parseNumericValue, prettyLabel, toCurrency } from '../../platform/format'
import type { Gate3CriterionSnapshot, IncidentRecord } from '../../types'
import { useData } from '../state/DataContext'
import { useToast } from '../state/ToastContext'

import { deriveTimelineSeverity } from './EvidenceTimeline'
import styles from './Flavor.module.css'

type GateNode = {
  id: string
  label: string
  source: 'command-center' | 'gate3'
  status: string
  detail: string
  evidenceRefs: string[]
  observedValue?: string
  threshold?: string
}

const RADIUS_PRIMARY = 145
const RADIUS_SECONDARY = 80
const CENTER_X = 210
const CENTER_Y = 210

function describeStatus(status: string): {
  tone: 'good' | 'watch' | 'risk' | 'info'
  glyph: string
  className: string
} {
  const lowered = status.toLowerCase()
  if (/fail|block|error|risk/.test(lowered)) {
    return { tone: 'risk', glyph: '✕ FAIL', className: styles.gateNodeFail }
  }
  if (/watch|warn|degrad/.test(lowered)) {
    return { tone: 'watch', glyph: '⚠ WATCH', className: styles.gateNodeWatch }
  }
  if (/pass|good|ok/.test(lowered)) {
    return { tone: 'good', glyph: '✓ PASS', className: styles.gateNodePass }
  }
  if (/ready|complete/.test(lowered)) {
    return { tone: 'good', glyph: 'READY', className: styles.gateNodeReady }
  }
  return { tone: 'info', glyph: prettyLabel(status), className: styles.gateNodeReady }
}

function buildGateNodes(args: {
  commandCenterGates: Record<string, string>
  gate3Criteria: Gate3CriterionSnapshot[]
}): GateNode[] {
  const seen = new Set<string>()
  const nodes: GateNode[] = []
  for (const [id, status] of Object.entries(args.commandCenterGates ?? {})) {
    if (seen.has(id)) continue
    seen.add(id)
    nodes.push({
      id,
      label: prettyLabel(id),
      source: 'command-center',
      status,
      detail: '',
      evidenceRefs: [],
    })
  }
  for (const criterion of args.gate3Criteria ?? []) {
    const id = criterion.criterion_id
    if (seen.has(id)) continue
    seen.add(id)
    nodes.push({
      id,
      label: prettyLabel(id),
      source: 'gate3',
      status: criterion.status,
      detail: criterion.details,
      evidenceRefs: criterion.evidence_refs,
      observedValue: criterion.observed_value,
      threshold: criterion.threshold,
    })
  }
  return nodes
}

function RiskSummaryCard({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail: string
}) {
  return (
    <div className={styles.metric} title={`${label}: ${detail}`}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricValue}>{value}</span>
      <span className={styles.metricSub}>{detail}</span>
    </div>
  )
}

type FilterTone = 'all' | 'good' | 'watch' | 'risk' | 'info'

export function RiskCoreFlavor() {
  const {
    commandCenter,
    gate3Readiness,
    gate3Package,
    incidents,
    portfolio,
    configSummary,
    writeMode,
    refresh,
    runAction,
  } = useData()
  const { pushToast } = useToast()

  const allNodes = useMemo(
    () =>
      buildGateNodes({
        commandCenterGates: commandCenter.gate_statuses,
        gate3Criteria: gate3Readiness.criteria,
      }),
    [commandCenter.gate_statuses, gate3Readiness.criteria],
  )
  const [selectedId, setSelectedId] = useState<string | null>(allNodes[0]?.id ?? null)
  const [filter, setFilter] = useState<FilterTone>('all')

  const filteredNodes = useMemo(() => {
    if (filter === 'all') return allNodes
    return allNodes.filter((node) => describeStatus(node.status).tone === filter)
  }, [allNodes, filter])

  const selected = useMemo(() => {
    if (!selectedId) return null
    return allNodes.find((node) => node.id === selectedId) ?? null
  }, [allNodes, selectedId])

  const placedNodes = useMemo(() => {
    return placeOnRings(filteredNodes)
  }, [filteredNodes])

  const counts = useMemo(() => {
    let pass = 0
    let watch = 0
    let risk = 0
    for (const node of allNodes) {
      const tone = describeStatus(node.status).tone
      if (tone === 'good') pass += 1
      else if (tone === 'watch') watch += 1
      else if (tone === 'risk') risk += 1
    }
    return { pass, watch, risk, total: allNodes.length }
  }, [allNodes])

  const writeBlocked = !writeMode.enabled || !writeMode.unlocked
  const unacknowledged = incidents.filter((incident) => !incident.acknowledged_at_utc)
  const pricedPositions = portfolio.positions_panel.positions.filter(
    (position) => position.market_value != null,
  )
  const unpricedPositionCount = portfolio.positions_panel.positions.length - pricedPositions.length
  const grossExposure = pricedPositions.reduce(
    (sum, position) => sum + Math.abs(parseNumericValue(position.market_value)),
    0,
  )
  const largestExposure = Math.max(
    0,
    ...pricedPositions.map((position) => Math.abs(parseNumericValue(position.market_value))),
  )
  const concentrationPct =
    grossExposure > 0 && unpricedPositionCount === 0
      ? (largestExposure / grossExposure) * 100
      : null

  return (
    <div className={styles.riskCoreGrid}>
      <div className={styles.panel} style={{ gridColumn: '1 / -1' }}>
        <div className={styles.panelHeader}>
          <span>Open Risk Summary</span>
          <span className={styles.panelSub}>
            Allocation, exposure, concentration, and limit status
          </span>
        </div>
        <div className={styles.kpis}>
          <RiskSummaryCard
            label="Allocation by symbol"
            value={
              portfolio.positions_panel.positions.length
                ? `${portfolio.positions_panel.positions.length} position${portfolio.positions_panel.positions.length === 1 ? '' : 's'}`
                : 'Flat'
            }
            detail={portfolio.positions_panel.detail}
          />
          <RiskSummaryCard
            label="Priced exposure"
            value={pricedPositions.length ? toCurrency(grossExposure) : 'Missing prices'}
            detail={
              pricedPositions.length
                ? `${pricedPositions.length} priced position${pricedPositions.length === 1 ? '' : 's'}; ${unpricedPositionCount} unpriced.`
                : 'No market-value evidence is available, so exposure is not rendered as zero.'
            }
          />
          <RiskSummaryCard
            label="Concentration"
            value={concentrationPct == null ? 'Unavailable' : `${concentrationPct.toFixed(1)}% largest`}
            detail={
              unpricedPositionCount
                ? `${unpricedPositionCount} unpriced open position${unpricedPositionCount === 1 ? '' : 's'}; concentration is unavailable.`
                : 'Largest position divided by priced gross exposure.'
            }
          />
          <RiskSummaryCard
            label="Risk limit status"
            value={counts.risk ? `${counts.risk} breach/fail` : counts.watch ? `${counts.watch} warning` : 'No breach shown'}
            detail="Gate failures and warnings are shown below; missing portfolio evidence is not treated as pass."
          />
        </div>
      </div>
      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span>Risk Core</span>
          <span className={styles.panelSub}>
            {counts.total} gates · {counts.pass} pass · {counts.watch} watch · {counts.risk} fail
          </span>
          <div className={styles.panelHeaderActions}>
            <select
              aria-label="Filter gates"
              value={filter}
              onChange={(event) => setFilter(event.target.value as FilterTone)}
            >
              <option value="all">All gates</option>
              <option value="good">Pass</option>
              <option value="watch">Watch</option>
              <option value="risk">Fail</option>
              <option value="info">Pending</option>
            </select>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                void refresh()
                pushToast('Refreshing risk snapshot…', 'info')
              }}
            >
              <RefreshCcw size={12} /> Refresh
            </button>
          </div>
        </div>
        <div className={styles.panelBody}>
          <div className={styles.riskCanvas}>
            <div className={styles.riskCanvasInner}>
              <svg viewBox="0 0 420 420" width={420} height={420} aria-hidden>
                {placedNodes.map((node) => (
                  <line
                    key={node.id}
                    x1={CENTER_X}
                    y1={CENTER_Y}
                    x2={node.x}
                    y2={node.y}
                    stroke="rgba(46, 161, 255, 0.18)"
                    strokeWidth={1}
                  />
                ))}
                <circle
                  cx={CENTER_X}
                  cy={CENTER_Y}
                  r={42}
                  fill="rgba(46, 161, 255, 0.15)"
                  stroke="rgba(46, 161, 255, 0.55)"
                  strokeWidth={1.5}
                />
                <text
                  x={CENTER_X}
                  y={CENTER_Y + 5}
                  fill="var(--primary-bright)"
                  textAnchor="middle"
                  fontSize="14"
                  fontWeight="600"
                >
                  RISK CORE
                </text>
              </svg>
              {placedNodes.map((node) => {
                const status = describeStatus(node.status)
                const isSelected = selectedId === node.id
                return (
                  <button
                    key={node.id}
                    type="button"
                    className={[
                      styles.gateNodeButton,
                      status.className,
                      isSelected ? styles.gateNodeActive : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    style={{ left: node.x, top: node.y }}
                    onClick={() => setSelectedId(node.id)}
                    aria-pressed={isSelected}
                  >
                    <span className={styles.gateNodeStatusDot} />
                    {node.label}
                    <div style={{ fontSize: 9, opacity: 0.85, marginTop: 2 }}>{status.glyph}</div>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      <div className={styles.gridShell}>
        <div className={styles.inspectorPanel}>
          <h3>Gate Detail</h3>
          {selected ? (
            <>
              <p>
                <strong>{selected.label}</strong> — {prettyLabel(selected.source)}
              </p>
              <p>
                Status:{' '}
                <span className={`badge badge-${describeStatus(selected.status).tone}`}>
                  {selected.status}
                </span>
              </p>
              {selected.detail ? <p>{selected.detail}</p> : null}
              {selected.observedValue ? (
                <p style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  Observed {selected.observedValue}
                  {selected.threshold ? ` · Threshold ${selected.threshold}` : ''}
                </p>
              ) : null}
              {selected.evidenceRefs.length > 0 ? (
                <pre>{selected.evidenceRefs.join('\n')}</pre>
              ) : null}
            </>
          ) : (
            <p>Select a gate to view detail.</p>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 6 }}>
            <button
              type="button"
              className="btn btn-sm"
              disabled={writeBlocked}
              onClick={() =>
                void runAction('Generate Gate 3 Report', () => postGate3Report())
              }
            >
              <ShieldCheck size={12} /> Generate Gate 3 Report
            </button>
            <button type="button" className="btn btn-sm" disabled>
              Run Gate Check
              <span className={styles.disabledNote} style={{ marginLeft: 4 }}>
                (no per-gate endpoint)
              </span>
            </button>
          </div>
          {writeBlocked ? (
            <p className={styles.disabledNote}>{writeMode.detail}</p>
          ) : null}
        </div>

        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Promotion Readiness</span>
            <span className={styles.panelSub}>{prettyLabel(gate3Readiness.status)}</span>
          </div>
          <div className={styles.panelBody}>
            <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
              {gate3Readiness.summary}
            </p>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 12 }}>
              Closed trades: {gate3Readiness.closed_trade_count} · Calendar days:{' '}
              {gate3Readiness.calendar_days_observed}
            </p>
            {gate3Package ? (
              <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 12 }}>
                Latest package: {gate3Package.package_id} ({gate3Package.status})
              </p>
            ) : null}
          </div>
        </div>

        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Incidents</span>
            <span className={styles.panelSub}>
              {unacknowledged.length} open · {incidents.length} total
            </span>
          </div>
          <div className={styles.panelBody}>
            {incidents.length === 0 ? (
              <div className={styles.emptyState}>
                <strong>No incidents recorded</strong>
                <p>Risk events will list here as the runtime publishes them.</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {incidents.slice(0, 5).map((incident) => (
                  <IncidentRow
                    key={incident.incident_id}
                    incident={incident}
                    writeBlocked={writeBlocked}
                    onAcknowledge={() =>
                      void runAction(`Acknowledge ${incident.incident_id}`, () =>
                        postAcknowledgeIncident(incident.incident_id),
                      )
                    }
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {configSummary.live_disable_report.manual_kill_switch_active ? (
          <div className={styles.panel} style={{ borderColor: 'var(--risk)' }}>
            <div className={styles.panelHeader}>
              <ShieldAlert size={14} color="var(--risk)" />
              <span style={{ color: 'var(--risk)' }}>Kill Switch is active</span>
            </div>
            <div className={styles.panelBody}>
              <p style={{ margin: 0 }}>
                Manual kill-switch evidence is recorded. Resume blocked until cleared via runbook.
              </p>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function IncidentRow({
  incident,
  writeBlocked,
  onAcknowledge,
}: {
  incident: IncidentRecord
  writeBlocked: boolean
  onAcknowledge: () => void
}) {
  const tone = deriveTimelineSeverity(incident.severity)
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        padding: 10,
        border: '1px solid var(--border-muted)',
        borderRadius: 6,
        background: 'var(--bg-panel)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className={`badge badge-${tone}`}>{prettyLabel(incident.severity)}</span>
        <strong style={{ flex: 1 }}>{incident.title}</strong>
        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>
          {formatTimestamp(incident.latest_seen_at_utc)}
        </span>
      </div>
      <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 12 }}>{incident.summary}</p>
      {incident.suggested_action ? (
        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 11 }}>
          Suggested: {incident.suggested_action}
        </p>
      ) : null}
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          type="button"
          className="btn btn-sm"
          disabled={writeBlocked || Boolean(incident.acknowledged_at_utc)}
          onClick={onAcknowledge}
        >
          <CheckCircle2 size={12} />{' '}
          {incident.acknowledged_at_utc ? 'Acknowledged' : 'Acknowledge'}
        </button>
      </div>
    </div>
  )
}

function placeOnRings(nodes: GateNode[]): Array<GateNode & { x: number; y: number }> {
  const total = nodes.length
  if (total === 0) return []
  if (total <= 9) {
    return nodes.map((node, index) => {
      const angle = (index / total) * Math.PI * 2 - Math.PI / 2
      return {
        ...node,
        x: CENTER_X + RADIUS_PRIMARY * Math.cos(angle),
        y: CENTER_Y + RADIUS_PRIMARY * Math.sin(angle),
      }
    })
  }
  const primary = nodes.slice(0, 9)
  const secondary = nodes.slice(9)
  const placedPrimary = primary.map((node, index) => {
    const angle = (index / primary.length) * Math.PI * 2 - Math.PI / 2
    return {
      ...node,
      x: CENTER_X + RADIUS_PRIMARY * Math.cos(angle),
      y: CENTER_Y + RADIUS_PRIMARY * Math.sin(angle),
    }
  })
  const placedSecondary = secondary.map((node, index) => {
    const angle = (index / secondary.length) * Math.PI * 2 - Math.PI / 4
    return {
      ...node,
      x: CENTER_X + RADIUS_SECONDARY * Math.cos(angle),
      y: CENTER_Y + RADIUS_SECONDARY * Math.sin(angle),
    }
  })
  return [...placedPrimary, ...placedSecondary]
}
