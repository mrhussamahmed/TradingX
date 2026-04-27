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
import { Compass, Layers3 } from 'lucide-react'

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
  const chartData = useMemo(
    () =>
      fallbackEquityPoints.map((point) => ({
        label: point.label,
        equity: parseNumericValue(point.equity),
        cash: parseNumericValue(point.cash),
      })),
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
  const exposureTotal = exposure.reduce((sum, item) => sum + parseNumericValue(item.value), 0) || 1

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
              <span className={styles.disabledNote}>Daily granularity from portfolio snapshot</span>
            </span>
          </div>
          <div className={styles.panelBody} style={{ minHeight: 280 }}>
            {chartData.length === 0 ? (
              <div className={styles.emptyState}>
                <strong>{portfolio.equity_curve.headline}</strong>
                <p>{portfolio.equity_curve.detail}</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={chartData} margin={{ top: 10, right: 16, bottom: 4, left: 0 }}>
                  <defs>
                    <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--primary-bright)" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="var(--primary-bright)" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(36, 82, 122, 0.3)" strokeDasharray="2 4" />
                  <XAxis
                    dataKey="label"
                    stroke="var(--text-muted)"
                    fontSize={10}
                    fontFamily="var(--font-mono)"
                  />
                  <YAxis
                    stroke="var(--text-muted)"
                    fontSize={10}
                    fontFamily="var(--font-mono)"
                    tickFormatter={(value: number) =>
                      value >= 10000
                        ? `${(value / 1000).toFixed(0)}k`
                        : value.toFixed(0)
                    }
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--bg-panel-elevated)',
                      border: '1px solid var(--border-strong)',
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke="var(--primary-bright)"
                    strokeWidth={1.6}
                    fill="url(#equityFill)"
                    isAnimationActive={false}
                    name="Equity"
                  />
                  <Line
                    type="monotone"
                    dataKey="cash"
                    stroke="var(--secondary)"
                    strokeWidth={1.2}
                    strokeDasharray="3 3"
                    dot={false}
                    isAnimationActive={false}
                    name="Cash"
                  />
                </ComposedChart>
              </ResponsiveContainer>
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
              <span className={styles.panelSub}>By symbol</span>
            </div>
            <div className={styles.panelBody}>
              {exposure.length === 0 ? (
                <div className={styles.emptyState}>
                  <strong>No active exposure</strong>
                  <p>Account is currently flat.</p>
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
