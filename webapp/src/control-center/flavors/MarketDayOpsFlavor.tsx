import { useEffect, useMemo, useState } from 'react'
import {
  CalendarCheck2,
  CircleDot,
  Download,
  Play,
  RefreshCcw,
  Square,
  Zap,
} from 'lucide-react'

import {
  postRuntimeHostStart,
  postRuntimeHostStop,
  postSessionClose,
  postSessionHeartbeat,
  postSessionPreopen,
} from '../../api'
import { formatTimestamp, parseNumericValue, prettyLabel, toCurrency } from '../../platform/format'
import type { OperatorTimelineEvent } from '../../types'
import { useData } from '../state/DataContext'
import { useToast } from '../state/ToastContext'

import { deriveTimelineSeverity } from './EvidenceTimeline'
import styles from './Flavor.module.css'

type Lane = {
  id: string
  label: string
  matcher: (event: OperatorTimelineEvent) => boolean
}

const LANES: ReadonlyArray<Lane> = [
  {
    id: 'preopen',
    label: 'Pre-open',
    matcher: (event) => /preopen|warmup|prepare/i.test(event.event_type),
  },
  {
    id: 'runtime',
    label: 'Runtime',
    matcher: (event) => /heartbeat|cycle|runtime|sync/i.test(event.event_type),
  },
  {
    id: 'decisions',
    label: 'Decisions',
    matcher: (event) => /decision|selection|opportunity|trade|order/i.test(event.event_type),
  },
  {
    id: 'incidents',
    label: 'Incidents',
    matcher: (event) => /incident|halt|kill|error|fail/i.test(event.event_type),
  },
  {
    id: 'evidence',
    label: 'Evidence',
    matcher: (event) => /evidence|artifact|report|gate/i.test(event.event_type),
  },
  {
    id: 'closeout',
    label: 'Closeout',
    matcher: (event) => /close|digest|reconcile/i.test(event.event_type),
  },
]

type ActionState = 'idle' | 'running'

export function MarketDayOpsFlavor() {
  const {
    commandCenter,
    schedulerState,
    runtimeState,
    runtimeHeartbeat,
    digest,
    portfolio,
    incidents,
    replay,
    configSummary,
    writeMode,
    runAction,
  } = useData()
  const { pushToast } = useToast()
  const [busyAction, setBusyAction] = useState<string | null>(null)

  const sortedEvents = useMemo(() => {
    return [...replay.events].sort((a, b) => {
      const at = new Date(a.occurred_at_utc).getTime() || 0
      const bt = new Date(b.occurred_at_utc).getTime() || 0
      return at - bt
    })
  }, [replay.events])

  const dayBounds = useMemo(() => {
    if (sortedEvents.length === 0) return null
    const earliest = new Date(sortedEvents[0].occurred_at_utc).getTime()
    const latest = new Date(sortedEvents[sortedEvents.length - 1].occurred_at_utc).getTime()
    if (Number.isNaN(earliest) || Number.isNaN(latest)) return null
    const span = Math.max(60_000, latest - earliest)
    return { earliest, latest, span }
  }, [sortedEvents])

  const positions = portfolio.positions_panel.positions
  const exposure = commandCenter.exposure_breakdown
  const exposureTotal = exposure.reduce((sum, item) => sum + parseNumericValue(item.value), 0) || 1

  const writeBlocked = !writeMode.enabled || !writeMode.unlocked
  const writeBlockedReason = writeMode.detail

  async function callAction(label: string, key: string, request: () => Promise<unknown>) {
    if (writeBlocked) {
      pushToast(`${label}: ${writeBlockedReason}`, 'watch')
      return
    }
    setBusyAction(key)
    try {
      await runAction(label, request as () => Promise<never>)
    } finally {
      setBusyAction((current) => (current === key ? null : current))
    }
  }

  function getActionState(key: string): ActionState {
    return busyAction === key ? 'running' : 'idle'
  }

  return (
    <div className={styles.gridShell}>
      <div className={styles.symbolHeader}>
        <div>
          <div className={styles.metricLabel}>Trading Day</div>
          <div className={styles.symbolMain}>
            {schedulerState.active_trading_day || prettyLabel(schedulerState.status)}
          </div>
          <div className={styles.metricSub}>
            Scheduler: {prettyLabel(schedulerState.status)}
            {schedulerState.next_run_at_utc
              ? ` · Next run ${formatTimestamp(schedulerState.next_run_at_utc)}`
              : ''}
          </div>
        </div>
        <dl className={styles.symbolMeta}>
          <dt>Runtime</dt>
          <dd>{prettyLabel(runtimeState.status)}</dd>
          <dt>Cadence</dt>
          <dd>{runtimeHeartbeat.cadence_label}</dd>
          <dt>Last Heartbeat</dt>
          <dd>
            {runtimeHeartbeat.last_evaluation_at_utc
              ? formatTimestamp(runtimeHeartbeat.last_evaluation_at_utc)
              : '—'}
          </dd>
          <dt>Cycles</dt>
          <dd className="numeric">{commandCenter.service_status.cycles_completed}</dd>
        </dl>
      </div>

      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span>Operations Timeline</span>
          <span className={styles.panelSub}>
            {sortedEvents.length} events captured
          </span>
        </div>
        <div className={styles.panelBody}>
          {sortedEvents.length === 0 || !dayBounds ? (
            <div className={styles.emptyState}>
              <strong>No timeline events yet</strong>
              <p>
                Start the runtime or run pre-open checks to populate the lanes.
              </p>
            </div>
          ) : (
            <div className={styles.timelineWrap}>
              <div className={styles.timelineLanes}>
                {LANES.map((lane) => (
                  <div key={lane.id} className={styles.timelineLaneLabel}>
                    {lane.label}
                  </div>
                ))}
              </div>
              <div className={styles.timelineRows}>
                <div className={styles.timelineHeader}>
                  {Array.from({ length: 8 }, (_, i) => (
                    <span key={i}>
                      {formatTimestampSlice(dayBounds.earliest + (i * dayBounds.span) / 8)}
                    </span>
                  ))}
                </div>
                {LANES.map((lane) => {
                  const events = sortedEvents.filter(lane.matcher)
                  return (
                    <div key={lane.id} className={styles.timelineRow}>
                      {events.map((event) => {
                        const ts = new Date(event.occurred_at_utc).getTime()
                        const ratio = (ts - dayBounds.earliest) / dayBounds.span
                        const severity = deriveTimelineSeverity(event.severity)
                        const cls =
                          severity === 'good'
                            ? styles.timelineEventGood
                            : severity === 'watch'
                              ? styles.timelineEventWatch
                              : severity === 'risk'
                                ? styles.timelineEventRisk
                                : styles.timelineEventInfo
                        return (
                          <span
                            key={event.event_id}
                            className={[styles.timelineEvent, cls].filter(Boolean).join(' ')}
                            style={{
                              left: `calc(${Math.max(0, Math.min(0.99, ratio)) * 100}% + 4px)`,
                              maxWidth: 220,
                            }}
                            title={`${formatTimestamp(event.occurred_at_utc)} — ${event.headline}`}
                          >
                            <CircleDot size={10} /> {event.headline}
                          </span>
                        )
                      })}
                    </div>
                  )
                })}
                <NowMarker dayBounds={dayBounds} />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className={styles.forgeRow}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Operator Actions</span>
            <span className={styles.panelSub}>
              {writeMode.unlocked ? 'Writes unlocked' : 'Writes locked'}
            </span>
          </div>
          <div className={styles.panelBody}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={writeBlocked || getActionState('preopen') === 'running'}
                onClick={() => callAction('Run Pre-open Checks', 'preopen', () => postSessionPreopen())}
              >
                <CalendarCheck2 size={14} /> Run Pre-open Checks
              </button>
              <button
                type="button"
                className="btn"
                disabled={writeBlocked || getActionState('heartbeat') === 'running'}
                onClick={() => callAction('Send Heartbeat', 'heartbeat', () => postSessionHeartbeat())}
              >
                <RefreshCcw size={14} /> Send Heartbeat
              </button>
              <button
                type="button"
                className="btn"
                disabled={
                  writeBlocked ||
                  runtimeState.status === 'running' ||
                  getActionState('start-runtime') === 'running'
                }
                onClick={() =>
                  callAction('Start Runtime', 'start-runtime', () =>
                    postRuntimeHostStart({
                      symbols: configSummary.config.symbol_universe.length
                        ? configSummary.config.symbol_universe
                        : ['SPY'],
                      quantity: '1',
                      interval_seconds: Number(configSummary.config.service_interval_seconds || 300),
                      max_cycles: null,
                    }),
                  )
                }
              >
                <Play size={14} /> Start Runtime
              </button>
              <button
                type="button"
                className="btn btn-warn"
                disabled={
                  writeBlocked ||
                  runtimeState.status !== 'running' ||
                  getActionState('stop-runtime') === 'running'
                }
                onClick={() => callAction('Stop Runtime', 'stop-runtime', () => postRuntimeHostStop())}
              >
                <Square size={14} /> Stop Runtime
              </button>
              <button
                type="button"
                className="btn"
                disabled={writeBlocked || getActionState('close') === 'running'}
                onClick={() => callAction('Close Session', 'close', () => postSessionClose())}
              >
                <Zap size={14} /> Close Session
              </button>
              <button
                type="button"
                className="btn"
                disabled={!digest}
                onClick={() => {
                  if (!digest) return
                  const blob = new Blob([JSON.stringify(digest, null, 2)], {
                    type: 'application/json',
                  })
                  const url = URL.createObjectURL(blob)
                  const link = document.createElement('a')
                  link.href = url
                  link.download = `${digest.digest_id || 'daily-digest'}.json`
                  document.body.appendChild(link)
                  link.click()
                  document.body.removeChild(link)
                  URL.revokeObjectURL(url)
                  pushToast('Daily digest exported.', 'good')
                }}
              >
                <Download size={14} /> Export Daily Digest
              </button>
            </div>
            {writeBlocked ? (
              <p className={styles.disabledNote}>{writeBlockedReason}</p>
            ) : null}
          </div>
        </div>

        <div className={styles.gridShell}>
          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Active Positions</span>
              <span className={styles.panelSub}>
                {positions.length} open · {prettyLabel(portfolio.positions_panel.status)}
              </span>
            </div>
            {positions.length === 0 ? (
              <div className={styles.panelBody}>
                <div className={styles.emptyState}>
                  <strong>{portfolio.positions_panel.headline}</strong>
                  <p>{portfolio.positions_panel.detail}</p>
                </div>
              </div>
            ) : (
              <table className={styles.simpleTable}>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Quantity</th>
                    <th>Market Value</th>
                    <th>Exposure %</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((position) => (
                    <tr key={position.symbol}>
                      <td className="mono">{position.symbol}</td>
                      <td className="numeric">{position.quantity}</td>
                      <td className="numeric">
                        {position.market_value ? toCurrency(position.market_value) : '—'}
                      </td>
                      <td className="numeric">{position.exposure_pct}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Exposure Allocation</span>
            </div>
            <div className={styles.panelBody}>
              {exposure.length === 0 ? (
                <div className={styles.emptyState}>
                  <strong>Account is flat</strong>
                  <p>Exposure will appear when positions are opened.</p>
                </div>
              ) : (
                exposure.map((entry) => {
                  const value = parseNumericValue(entry.value)
                  const ratio = Math.min(1, Math.abs(value) / exposureTotal)
                  return (
                    <div key={entry.symbol} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span className="mono">{entry.symbol}</span>
                        <span className="numeric">{toCurrency(value)}</span>
                      </div>
                      <div className={styles.exposureBar}>
                        <span style={{ width: `${ratio * 100}%` }} />
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>
      </div>

      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span>Daily Digest</span>
          <span className={styles.panelSub}>
            {digest
              ? `${prettyLabel(digest.session_label)} · ${formatTimestamp(digest.generated_at_utc)}`
              : 'No digest yet'}
          </span>
        </div>
        <div className={styles.panelBody}>
          {!digest ? (
            <div className={styles.emptyState}>
              <strong>No digest available yet</strong>
              <p>Run Close Session at end-of-day to generate the digest.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <p style={{ margin: 0, color: 'var(--text-secondary)' }}>
                Service status: <strong>{prettyLabel(digest.service_status)}</strong> · Blocked
                trades: {digest.blocked_trade_count} · Reconciliation failures:{' '}
                {digest.reconciliation_failure_count}
              </p>
              {digest.recommended_actions.length > 0 ? (
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {digest.recommended_actions.map((action, i) => (
                    <li key={i}>{action}</li>
                  ))}
                </ul>
              ) : null}
              {incidents.length > 0 ? (
                <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 12 }}>
                  {incidents.length} incident{incidents.length === 1 ? '' : 's'} recorded today.
                </p>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function NowMarker({ dayBounds }: { dayBounds: { earliest: number; span: number } }) {
  const [nowMs, setNowMs] = useState<number>(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])
  const ratio = (nowMs - dayBounds.earliest) / dayBounds.span
  if (ratio < 0 || ratio > 1) return null
  return <span className={styles.nowMarker} style={{ left: `${ratio * 100}%` }} />
}

function formatTimestampSlice(ms: number): string {
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(ms))
}
