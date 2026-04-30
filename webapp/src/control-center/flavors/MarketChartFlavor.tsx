import { useMemo, useState } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Compass, Info, Layers3 } from 'lucide-react'

import { parseNumericValue, prettyLabel, toCurrency } from '../../platform/format'
import type { PortfolioSeriesPoint } from '../../types'
import { useData } from '../state/DataContext'
import { usePreferences } from '../state/PreferencesContext'

import {
  EvidenceTimeline,
  buildTimelineFromExplorer,
  buildTimelineFromIncidents,
  buildTimelineFromReplay,
  type TimelineEvent,
} from './EvidenceTimeline'
import styles from './Flavor.module.css'

const TIMEFRAMES = [
  { id: '1m', label: '1m', interactive: false },
  { id: '5m', label: '5m', interactive: false },
  { id: '15m', label: '15m', interactive: false },
  { id: '1h', label: '1H', interactive: false },
  { id: '4h', label: '4H', interactive: false },
  { id: '1d', label: '1D', interactive: true },
  { id: '1w', label: '1W', interactive: false },
  { id: '1M', label: '1M', interactive: false },
] as const

type TimeframeId = (typeof TIMEFRAMES)[number]['id']

export function MarketChartFlavor() {
  const { commandCenter, portfolio, runtimeHeartbeat, incidents, replay, explorer } = useData()
  const { prefs } = usePreferences()
  const [activeSymbol, setActiveSymbol] = useState<string | null>(
    () => commandCenter.watchlist[0]?.symbol ?? null,
  )
  const [timeframe, setTimeframe] = useState<TimeframeId>('1d')

  const events = useMemo<TimelineEvent[]>(() => {
    const items: TimelineEvent[] = [
      ...buildTimelineFromIncidents(incidents),
      ...buildTimelineFromReplay(replay.events),
      ...buildTimelineFromExplorer(explorer),
    ]
    return items
  }, [incidents, replay.events, explorer])

  const equityPoints = portfolio.equity_curve.points
  const fallbackEquityPoints =
    equityPoints.length === 0
      ? commandCenter.equity_curve.map<PortfolioSeriesPoint>((point, index) => ({
          label: point.label,
          timestamp_utc: null,
          equity: point.value,
          cash: '',
          buying_power: '',
          // index used only for sort stability
          ...{ __order: index },
        }))
      : equityPoints
  const useIntradayLabels = fallbackEquityPoints.some((point) => point.timestamp_utc)
  const chartData = useMemo(
    () =>
      fallbackEquityPoints
        .map((point) => ({
          label: point.timestamp_utc
            ? new Date(point.timestamp_utc).toLocaleTimeString([], {
                hour: 'numeric',
                minute: '2-digit',
              })
            : point.label,
          tooltipLabel: point.timestamp_utc
            ? new Date(point.timestamp_utc).toLocaleString([], {
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
              })
            : point.label,
          equity: parseNumericValue(point.equity),
          cash: parseNumericValue(point.cash),
        }))
        .filter((point) => point.equity > 0),
    [fallbackEquityPoints],
  )

  const equity = commandCenter.account_summary.equity
    ? toCurrency(commandCenter.account_summary.equity)
    : '—'
  const dailyPnl = commandCenter.account_summary.daily_pnl
    ? toCurrency(commandCenter.account_summary.daily_pnl)
    : '—'
  const buyingPower = commandCenter.account_summary.buying_power
    ? toCurrency(commandCenter.account_summary.buying_power)
    : '—'

  const gateEntries = Object.entries(commandCenter.gate_statuses ?? {})
  const exposure = commandCenter.exposure_breakdown ?? []
  const pricedExposure = exposure.filter((item) => item.value != null)
  const missingExposure = exposure.filter((item) => item.value == null)
  const exposureTotal =
    pricedExposure.reduce(
      (sum, item) => sum + Math.abs(parseNumericValue(item.value)),
      0,
    )
  const cashValue = parseNumericValue(commandCenter.account_summary.cash)
  const equityValue = parseNumericValue(commandCenter.account_summary.equity)

  return (
    <div className={styles.gridShell}>
      <div className={styles.symbolHeader}>
        <div>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)' }}>
            Active Symbol
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
            {commandCenter.watchlist.length === 0 ? (
              <span className="badge">No symbols configured</span>
            ) : (
              commandCenter.watchlist.map((entry) => (
                <button
                  key={entry.symbol}
                  type="button"
                  className={
                    activeSymbol === entry.symbol ? 'btn btn-primary btn-sm mono' : 'btn btn-sm mono'
                  }
                  onClick={() => setActiveSymbol(entry.symbol)}
                >
                  {entry.symbol}
                  <span style={{ fontSize: 10, opacity: 0.75 }}>· {entry.status}</span>
                </button>
              ))
            )}
          </div>
        </div>
        <dl className={styles.symbolMeta}>
          <dt>Mode</dt>
          <dd>{prettyLabel(commandCenter.session_mode || 'standby')}</dd>
          <dt>Equity</dt>
          <dd className="numeric">{equity}</dd>
          <dt>Buying Power</dt>
          <dd className="numeric">{buyingPower}</dd>
          <dt>Daily P&amp;L</dt>
          <dd className="numeric">{dailyPnl}</dd>
        </dl>
        <div className={styles.symbolPrice}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Heartbeat</span>
          <span className={`${styles.symbolMain} numeric`} style={{ fontSize: 16 }}>
            {runtimeHeartbeat.heartbeat_state || '—'}
          </span>
        </div>
      </div>

      <div className={styles.marketGrid}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Equity Curve</span>
            <span className={styles.panelSub}>
              {portfolio.equity_curve.headline}
            </span>
            <div className={styles.panelHeaderActions}>
              <button type="button" className="btn btn-sm" disabled>
                <Layers3 size={12} /> Indicators
                <span className={styles.disabledNote} style={{ marginLeft: 4 }}>
                  (per-symbol OHLC not in current API)
                </span>
              </button>
              <button type="button" className="btn btn-sm" disabled>
                <Compass size={12} /> Compare
              </button>
            </div>
          </div>
          <div className={styles.timeframeBar}>
            {TIMEFRAMES.map((option) => (
              <button
                type="button"
                key={option.id}
                className={[styles.timeframeBtn, timeframe === option.id ? styles.timeframeActive : '']
                  .filter(Boolean)
                  .join(' ')}
                onClick={() => option.interactive && setTimeframe(option.id)}
                disabled={!option.interactive}
                aria-pressed={timeframe === option.id}
              >
                {option.label}
              </button>
            ))}
            <span className={styles.toolbarRight}>
              <span className={styles.disabledNote}>
                {useIntradayLabels ? 'Intraday account snapshots' : 'Source account snapshots'}
              </span>
            </span>
          </div>
          <div className={styles.panelBody} style={{ minHeight: 280, flex: '0 0 auto' }}>
            {chartData.length === 0 ? (
              <div className={styles.emptyState}>
                <strong>{portfolio.equity_curve.headline}</strong>
                <p>{portfolio.equity_curve.detail}</p>
              </div>
            ) : (
              <div className={styles.portfolioGraphDeck}>
                <div className={styles.equityChartFrame}>
                  <ResponsiveContainer width="100%" height={230}>
                    <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                      <defs>
                        <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--primary-bright)" stopOpacity={0.28} />
                          <stop offset="100%" stopColor="var(--primary-bright)" stopOpacity={0.03} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="rgba(36, 82, 122, 0.24)" strokeDasharray="2 6" />
                      <XAxis
                        dataKey="label"
                        stroke="var(--text-muted)"
                        fontSize={10}
                        fontFamily="var(--font-mono)"
                        interval="preserveStartEnd"
                        minTickGap={28}
                      />
                      <YAxis
                        stroke="var(--text-muted)"
                        fontSize={10}
                        fontFamily="var(--font-mono)"
                        width={48}
                        domain={['dataMin - 5', 'dataMax + 5']}
                        tickFormatter={(value: number) => `$${(value / 1000).toFixed(1)}k`}
                      />
                      <Tooltip
                        labelFormatter={(_, payload) =>
                          payload?.[0]?.payload?.tooltipLabel ?? ''
                        }
                        formatter={(value, name) => [toCurrency(value as number), name ?? 'Value']}
                        contentStyle={{
                          background: 'var(--bg-panel-elevated)',
                          border: '1px solid var(--border-strong)',
                          borderRadius: 6,
                          fontSize: 12,
                        }}
                      />
                      <Area
                        type="linear"
                        dataKey="equity"
                        stroke="var(--primary-bright)"
                        strokeWidth={1.8}
                        fill="url(#equityFill)"
                        dot={{ r: 2 }}
                        activeDot={{ r: 4 }}
                        isAnimationActive={false}
                        name="Equity"
                      />
                      <Line
                        type="linear"
                        dataKey="cash"
                        stroke="var(--secondary)"
                        strokeWidth={1.2}
                        strokeDasharray="4 4"
                        dot={false}
                        isAnimationActive={false}
                        name="Cash"
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <HoldingsDonut exposure={pricedExposure} total={exposureTotal} />
                <CapitalUseChart cash={cashValue} exposure={exposureTotal} equity={equityValue} />
              </div>
            )}
          </div>
        </div>

        <div className={styles.gridShell}>
          <div className={styles.kpis}>
            <KpiCard label="Account Equity" value={equity} sub="Cash + position value" />
            <KpiCard label="Daily P&L" value={dailyPnl} sub={`${commandCenter.service_status.cycles_completed} cycles`} />
            <KpiCard
              label="Buying Power"
              value={buyingPower}
              sub={runtimeHeartbeat.current_exposure || 'Flat'}
            />
            <KpiCard
              label="Active Symbol"
              value={activeSymbol ?? '—'}
              sub={runtimeHeartbeat.decision || 'No decision yet'}
            />
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Risk Gates Live</span>
              <span className={styles.panelSub}>{gateEntries.length} gates</span>
            </div>
            <div className={styles.panelBody}>
              {gateEntries.length === 0 ? (
                <div className={styles.emptyState}>
                  <strong>No gate evidence yet</strong>
                  <p>Gate statuses will appear once the runtime publishes evidence.</p>
                </div>
              ) : (
                gateEntries.map(([gateId, status]) => {
                  const lowered = status.toLowerCase()
                  const tone = /fail|block|error|risk/.test(lowered)
                    ? 'risk'
                    : /watch|warn|degrad/.test(lowered)
                      ? 'watch'
                      : /pass|ok|good|ready/.test(lowered)
                        ? 'good'
                        : 'info'
                  return (
                    <div key={gateId} className={styles.gateRecRow}>
                      <span style={{ flex: 1 }}>{prettyLabel(gateId)}</span>
                      <span className={`badge badge-${tone}`}>{status}</span>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Exposure</span>
              <span
                className={styles.panelSub}
                title="Shows current source-backed market value by symbol when prices are available. Missing prices render as unavailable, never as zero or equal placeholder allocation."
              >
                <Info size={13} /> By symbol
              </span>
            </div>
            <div className={styles.panelBody}>
              {exposure.length === 0 ? (
                <div className={styles.emptyState}>
                  <strong>No active exposure</strong>
                  <p>Account is currently flat.</p>
                </div>
              ) : pricedExposure.length === 0 ? (
                <div className={styles.emptyState}>
                  <strong>Exposure unavailable</strong>
                  <p>
                    Open-position symbols are available ({exposure.map((entry) => entry.symbol).join(', ')}), but
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

      <EvidenceTimeline
        events={events}
        showEvidenceLayer={prefs.showEvidenceLayer}
        symbolFilter={activeSymbol ?? undefined}
        emptyStateMessage="Evidence will appear after the first incident, replay event, or explorer record."
      />
    </div>
  )
}

function KpiCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className={styles.metric}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={styles.metricValue}>{value}</span>
      <span className={styles.metricSub}>{sub}</span>
    </div>
  )
}

function HoldingsDonut({
  exposure,
  total,
}: {
  exposure: Array<{ symbol: string; value: string | null }>
  total: number
}) {
  if (exposure.length === 0 || total <= 0) {
    return (
      <div className={styles.miniChartPanel}>
        <span className={styles.metricLabel}>Holdings %</span>
        <div className={styles.emptyMiniChart}>No priced holdings</div>
      </div>
    )
  }
  const colors = ['var(--primary-bright)', 'var(--good)', 'var(--watch)', 'var(--risk)']
  let cursor = 0
  return (
    <div className={styles.miniChartPanel}>
      <span className={styles.metricLabel}>Holdings %</span>
      <svg viewBox="0 0 120 120" className={styles.donutChart} aria-label="Holdings allocation by market value">
        {exposure.map((entry, index) => {
          const value = Math.abs(parseNumericValue(entry.value))
          const start = cursor
          const fraction = value / total
          cursor += fraction
          return (
            <circle
              key={entry.symbol}
              cx="60"
              cy="60"
              r="42"
              fill="none"
              stroke={colors[index % colors.length]}
              strokeWidth="14"
              strokeDasharray={`${fraction * 263.89} 263.89`}
              strokeDashoffset={-start * 263.89}
              transform="rotate(-90 60 60)"
            />
          )
        })}
        <text x="60" y="58" textAnchor="middle" className={styles.donutValue}>
          {exposure.length}
        </text>
        <text x="60" y="73" textAnchor="middle" className={styles.donutLabel}>
          holdings
        </text>
      </svg>
      <div className={styles.donutLegend}>
        {exposure.map((entry, index) => {
          const value = Math.abs(parseNumericValue(entry.value))
          return (
            <span key={entry.symbol}>
              <i style={{ background: colors[index % colors.length] }} />
              {entry.symbol} {(value / total * 100).toFixed(1)}%
            </span>
          )
        })}
      </div>
    </div>
  )
}

function CapitalUseChart({ cash, exposure, equity }: { cash: number; exposure: number; equity: number }) {
  const denominator = equity > 0 ? equity : Math.max(cash + exposure, 1)
  const cashPct = Math.min(100, Math.max(0, (cash / denominator) * 100))
  const exposurePct = Math.min(100, Math.max(0, (exposure / denominator) * 100))
  return (
    <div className={styles.miniChartPanel}>
      <span className={styles.metricLabel}>Capital Use</span>
      <div className={styles.capitalBars}>
        <span>Cash</span>
        <div><i style={{ width: `${cashPct}%` }} /></div>
        <strong>{cashPct.toFixed(1)}%</strong>
        <span>Exposure</span>
        <div><i style={{ width: `${exposurePct}%` }} /></div>
        <strong>{exposurePct.toFixed(1)}%</strong>
      </div>
    </div>
  )
}
