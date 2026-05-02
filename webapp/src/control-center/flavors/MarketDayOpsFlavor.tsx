import { useEffect, useState } from 'react'
import {
  CalendarCheck2,
  Download,
  Info,
  LockKeyhole,
  LockOpen,
  Play,
  RefreshCcw,
  Square,
  Zap,
} from 'lucide-react'

import {
  postRuntimeHostCadence,
  postRuntimeHostStart,
  postRuntimeHostStop,
  postSessionClose,
  postSessionHeartbeat,
  postSessionPreopen,
} from '../../api'
import { formatTimestamp, parseNumericValue, prettyLabel, toCurrency } from '../../platform/format'
import { isRuntimeActive } from '../shell/runtimeStatus'
import { useData } from '../state/DataContext'
import { useToast } from '../state/ToastContext'
import {
  buildPaperRuntimeSizingPayload,
  describePaperRuntimeSizing,
  paperRuntimeFallbackQuantity,
  readPaperRuntimeSizingSettings,
  writePaperRuntimeSizingSettings,
  type PaperRuntimeSizingSettings,
} from '../state/paperRuntimeSizing'

import { SessionTimelineChart } from './SessionTimelineChart'
import styles from './Flavor.module.css'

type ActionState = 'idle' | 'running'

const CADENCE_OPTIONS = [180, 300, 600, 1200, 1800, 3600, 7200]

export function MarketDayOpsFlavor() {
  const {
    commandCenter,
    schedulerState,
    runtimeState,
    runtimeHeartbeat,
    digest,
    portfolio,
    incidents,
    sessionTimeline,
    sessionTimelineDate,
    setSessionTimelineDate,
    configSummary,
    writeMode,
    unlockWrites,
    lockWrites,
    runAction,
  } = useData()
  const { pushToast } = useToast()
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [cadenceSaving, setCadenceSaving] = useState(false)
  const [writeSecret, setWriteSecret] = useState('')
  const [sizingSettings, setSizingSettings] = useState<PaperRuntimeSizingSettings>(
    readPaperRuntimeSizingSettings,
  )
  const [positionSymbolFilter, setPositionSymbolFilter] = useState('all')

  useEffect(() => {
    writePaperRuntimeSizingSettings(sizingSettings)
  }, [sizingSettings])

  const positions = portfolio.positions_panel.positions
  const exposure = commandCenter.exposure_breakdown
  const filterSymbols = Array.from(
    new Set([...positions.map((position) => position.symbol), ...exposure.map((entry) => entry.symbol)]),
  ).sort()
  const filteredPositions =
    positionSymbolFilter === 'all'
      ? positions
      : positions.filter((position) => position.symbol === positionSymbolFilter)
  const filteredExposure =
    positionSymbolFilter === 'all'
      ? exposure
      : exposure.filter((entry) => entry.symbol === positionSymbolFilter)
  const pricedExposure = filteredExposure.filter((item) => item.value != null)
  const missingExposure = filteredExposure.filter((item) => item.value == null)
  const exposureTotal =
    pricedExposure.reduce(
      (sum, item) => sum + Math.abs(parseNumericValue(item.value)),
      0,
    )

  const writeBlocked = !writeMode.enabled || !writeMode.unlocked
  const writeBlockedReason = writeMode.detail
  const configuredCadence =
    runtimeHeartbeat.configured_cadence_seconds ?? runtimeHeartbeat.cadence_seconds
  const runningCadence =
    runtimeHeartbeat.running_cadence_seconds ?? runtimeHeartbeat.cadence_seconds

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

  function handleUnlockWrites() {
    const result = unlockWrites(writeSecret)
    if (!result.ok) {
      pushToast(result.error ?? 'Unable to unlock writes.', 'watch')
      return
    }
    setWriteSecret('')
  }

  function updateSizingSettings(patch: Partial<PaperRuntimeSizingSettings>) {
    setSizingSettings((current) => ({ ...current, ...patch }))
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
          <dd>
            <select
              aria-label="Service cycle cadence"
              value={configuredCadence}
              disabled={cadenceSaving}
              onChange={async (event) => {
                const nextCadence = Number(event.currentTarget.value)
                setCadenceSaving(true)
                try {
                  await callAction('Update service cycle cadence', 'cadence', () =>
                    postRuntimeHostCadence(nextCadence),
                  )
                } finally {
                  setCadenceSaving(false)
                }
              }}
            >
              {CADENCE_OPTIONS.map((seconds) => (
                <option key={seconds} value={seconds}>
                  {cadenceLabel(seconds)}
                </option>
              ))}
            </select>
            <span className={styles.inlineMeta}>
              Running {cadenceLabel(runningCadence)}
              {runtimeHeartbeat.cadence_source === 'operator_override'
                ? ' · operator override'
                : ' · config'}
              {' · '}
              applies {prettyLabel(runtimeHeartbeat.cadence_applies_at ?? 'next_start')}
            </span>
          </dd>
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

      <SessionTimelineChart
        title="Operation Timeline"
        description="Shows source-backed TradingX activity for the selected trading day. The horizontal scale uses persisted market-session open and close when available; missing close metadata is called out instead of inferred."
        timeline={sessionTimeline}
        selectedTradingDay={sessionTimelineDate}
        onTradingDayChange={setSessionTimelineDate}
        emptyStateMessage="Start the runtime or run pre-open checks to populate the selected trading day."
      />

      <div className={styles.forgeRow}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Operator Actions</span>
            <span className={styles.panelSub}>
              {writeMode.unlocked ? 'Writes unlocked' : 'Writes locked'}
            </span>
          </div>
          <div className={styles.panelBody}>
            {writeMode.enabled && writeMode.configured ? (
              <div className={styles.writeUnlockPanel}>
                {writeMode.unlocked ? (
                  <>
                    <span className={styles.writeUnlockStatus}>Signed writes unlocked</span>
                    <button type="button" className="btn" onClick={lockWrites}>
                      <LockKeyhole size={14} /> Lock Writes
                    </button>
                  </>
                ) : (
                  <>
                    <label className={styles.sizingField}>
                      <span>Local signing secret</span>
                      <input
                        aria-label="Local signing secret"
                        type="password"
                        value={writeSecret}
                        onChange={(event) => setWriteSecret(event.currentTarget.value)}
                      />
                    </label>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={!writeSecret.trim()}
                      onClick={handleUnlockWrites}
                    >
                      <LockOpen size={14} /> Unlock Writes
                    </button>
                  </>
                )}
              </div>
            ) : null}
            <div className={styles.sizingControls} aria-label="Paper order sizing">
              <div className={styles.sizingHeader}>
                <span>Paper order sizing</span>
                <span className={styles.sizingSummary}>
                  {describePaperRuntimeSizing(sizingSettings)}
                </span>
              </div>
              <div className={styles.sizingGrid}>
                <label className={styles.sizingField}>
                  <span>Sizing mode</span>
                  <select
                    aria-label="Sizing mode"
                    value={sizingSettings.mode}
                    onChange={(event) =>
                      updateSizingSettings({
                        mode: event.currentTarget.value as PaperRuntimeSizingSettings['mode'],
                      })
                    }
                  >
                    <option value="fixed_shares">Fixed shares</option>
                    <option value="percent_equity">Percent equity</option>
                  </select>
                </label>
                <label className={styles.sizingField}>
                  <span>Fixed shares</span>
                  <input
                    aria-label="Fixed shares"
                    type="number"
                    min="1"
                    step="1"
                    value={sizingSettings.fixedQuantity}
                    onChange={(event) =>
                      updateSizingSettings({ fixedQuantity: event.currentTarget.value })
                    }
                  />
                </label>
                <label className={styles.sizingField}>
                  <span>Equity per new position</span>
                  <input
                    aria-label="Equity per new position"
                    type="number"
                    min="0"
                    step="0.1"
                    value={sizingSettings.equityPercent}
                    onChange={(event) =>
                      updateSizingSettings({ equityPercent: event.currentTarget.value })
                    }
                  />
                </label>
                <label className={styles.sizingField}>
                  <span>Max order notional</span>
                  <input
                    aria-label="Max order notional"
                    type="number"
                    min="0"
                    step="100"
                    value={sizingSettings.maxOrderNotional}
                    onChange={(event) =>
                      updateSizingSettings({ maxOrderNotional: event.currentTarget.value })
                    }
                  />
                </label>
                <label className={styles.sizingField}>
                  <span>Cash reserve</span>
                  <input
                    aria-label="Cash reserve"
                    type="number"
                    min="0"
                    max="100"
                    step="1"
                    value={sizingSettings.cashReservePercent}
                    onChange={(event) =>
                      updateSizingSettings({ cashReservePercent: event.currentTarget.value })
                    }
                  />
                </label>
              </div>
            </div>
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
                  isRuntimeActive(runtimeState.status) ||
                  getActionState('start-runtime') === 'running'
                }
                onClick={() =>
                  callAction('Start Paper Runtime', 'start-runtime', () =>
                    postRuntimeHostStart({
                      symbols: configSummary.config.symbol_universe.length
                        ? configSummary.config.symbol_universe
                        : ['SPY'],
                      quantity: paperRuntimeFallbackQuantity(sizingSettings),
                      interval_seconds: Number(
                        runtimeHeartbeat.configured_cadence_seconds ??
                          configSummary.config.service_interval_seconds ??
                          300,
                      ),
                      max_cycles: null,
                      sizing_policy: buildPaperRuntimeSizingPayload(sizingSettings),
                    }),
                  )
                }
              >
                <Play size={14} /> Start Paper Runtime
              </button>
              <button
                type="button"
                className="btn btn-warn"
                disabled={
                  writeBlocked ||
                  !isRuntimeActive(runtimeState.status) ||
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
                {positions.length} open · {filteredPositions.length} shown · {prettyLabel(portfolio.positions_panel.status)}
              </span>
              <div className={styles.panelHeaderActions}>
                <select
                  aria-label="Filter active positions by symbol"
                  value={positionSymbolFilter}
                  onChange={(event) => setPositionSymbolFilter(event.currentTarget.value)}
                >
                  <option value="all">All symbols</option>
                  {filterSymbols.map((symbol) => (
                    <option key={symbol} value={symbol}>
                      {symbol}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {positions.length === 0 ? (
              <div className={styles.panelBody}>
                <div className={styles.emptyState}>
                  <strong>{portfolio.positions_panel.headline}</strong>
                  <p>{portfolio.positions_panel.detail}</p>
                </div>
              </div>
            ) : filteredPositions.length === 0 ? (
              <div className={styles.panelBody}>
                <div className={styles.emptyState}>
                  <strong>No positions match this filter</strong>
                  <p>Select All symbols or another symbol with open exposure.</p>
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
                  {filteredPositions.map((position) => (
                    <tr key={position.symbol}>
                      <td className="mono">{position.symbol}</td>
                      <td className="numeric">
                        {position.quantity ?? prettyLabel(position.quantity_status ?? 'source_missing')}
                      </td>
                      <td className="numeric">
                        {position.market_value != null
                          ? toCurrency(position.market_value)
                          : prettyLabel(position.price_status ?? 'unpriced')}
                      </td>
                      <td className="numeric">
                        {position.exposure_pct != null
                          ? `${position.exposure_pct}%`
                          : prettyLabel(position.exposure_status ?? 'source_missing')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Exposure Allocation</span>
              <span
                className={styles.panelSub}
                title="Shows current source-backed market value by symbol when position prices are available. Missing prices render as unavailable, never as zero or equal placeholder allocation."
              >
                <Info size={13} /> Market value by symbol
              </span>
            </div>
            <div className={styles.panelBody}>
              {exposure.length === 0 ? (
                <div className={styles.emptyState}>
                  <strong>Account is flat</strong>
                  <p>Exposure will appear when positions are opened.</p>
                </div>
              ) : pricedExposure.length === 0 ? (
                <div className={styles.emptyState}>
                  <strong>Exposure unavailable</strong>
                  <p>
                    Open-position symbols are available ({filteredExposure.map((entry) => entry.symbol).join(', ')}), but
                    source-backed market values are missing. No allocation chart is shown.
                  </p>
                </div>
              ) : (
                <>
                  {pricedExposure.map((entry) => {
                    const value = parseNumericValue(entry.value)
                    const ratio = exposureTotal <= 0 ? 0 : Math.min(1, Math.abs(value) / exposureTotal)
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
                  })}
                  {missingExposure.length > 0 ? (
                    <div className={styles.timelineNotice}>
                      Missing market values:{' '}
                      {missingExposure
                        .map((entry) => `${entry.symbol} (${prettyLabel(entry.value_status ?? 'source_missing')})`)
                        .join(', ')}
                    </div>
                  ) : null}
                </>
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

function cadenceLabel(seconds: number): string {
  if (seconds >= 3600) {
    const hours = seconds / 3600
    return hours === 1 ? '1 hour' : `${hours} hours`
  }
  return `${Math.round(seconds / 60)} minutes`
}
