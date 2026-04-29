import { useEffect, useMemo, useState } from 'react'
import { Activity, Bell } from 'lucide-react'

import { parseNumericValue, prettyLabel, toCurrency } from '../../platform/format'
import type {
  CommandCenterSnapshot,
  ConfigSummary,
  IncidentRecord,
  RuntimeHeartbeatSnapshot,
} from '../../types'

import styles from './Shell.module.css'

export type RiskTone = 'good' | 'watch' | 'risk' | 'info' | 'neutral'

// eslint-disable-next-line react-refresh/only-export-components
export function deriveRiskTone(gateStatuses: Record<string, string>): {
  tone: RiskTone
  label: string
  detail: string
} {
  const entries = Object.entries(gateStatuses ?? {})
  if (entries.length === 0) {
    return { tone: 'neutral', label: 'No gates', detail: 'No gate evidence yet.' }
  }
  const failing = entries.filter(([, status]) => /fail|block|error|risk/i.test(status))
  if (failing.length > 0) {
    return {
      tone: 'risk',
      label: 'Risk',
      detail: `${failing.length} gate${failing.length === 1 ? '' : 's'} failing`,
    }
  }
  const watching = entries.filter(([, status]) => /watch|warn|degrad/i.test(status))
  if (watching.length > 0) {
    return {
      tone: 'watch',
      label: 'Watch',
      detail: `${watching.length} gate${watching.length === 1 ? '' : 's'} watching`,
    }
  }
  return { tone: 'good', label: 'Normal', detail: 'All gates passing' }
}

// eslint-disable-next-line react-refresh/only-export-components
export function deriveRuntimeTone(heartbeat: RuntimeHeartbeatSnapshot): RiskTone {
  const tone = heartbeat.heartbeat_tone?.toLowerCase() ?? ''
  if (tone === 'risk' || tone === 'fail' || tone === 'critical') return 'risk'
  if (tone === 'watch' || tone === 'warn') return 'watch'
  if (tone === 'good' || tone === 'ok' || tone === 'pass') return 'good'
  return 'neutral'
}

// eslint-disable-next-line react-refresh/only-export-components
export function describePnl(value: string): { display: string; tone: RiskTone } {
  const numeric = parseNumericValue(value)
  if (!value) {
    return { display: '—', tone: 'neutral' }
  }
  if (numeric > 0) {
    return { display: `+${toCurrency(numeric)}`, tone: 'good' }
  }
  if (numeric < 0) {
    return { display: toCurrency(numeric), tone: 'risk' }
  }
  return { display: toCurrency(0), tone: 'neutral' }
}

export type TopStatusStripProps = {
  commandCenter: CommandCenterSnapshot
  configSummary: ConfigSummary
  runtimeHeartbeat: RuntimeHeartbeatSnapshot
  incidents: IncidentRecord[]
  generatedAt: string
  onOpenAlertsCenter: () => void
}

export function TopStatusStrip({
  commandCenter,
  configSummary,
  runtimeHeartbeat,
  incidents,
  generatedAt,
  onOpenAlertsCenter,
}: TopStatusStripProps) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 10_000)
    return () => window.clearInterval(id)
  }, [])

  const risk = useMemo(
    () => deriveRiskTone(commandCenter.gate_statuses),
    [commandCenter.gate_statuses],
  )
  const runtimeTone = useMemo(() => deriveRuntimeTone(runtimeHeartbeat), [runtimeHeartbeat])

  const dailyPnl = describePnl(commandCenter.account_summary.daily_pnl)
  const equity = commandCenter.account_summary.equity
    ? toCurrency(commandCenter.account_summary.equity)
    : '—'
  const cash = commandCenter.account_summary.cash
    ? toCurrency(commandCenter.account_summary.cash)
    : '—'
  const buyingPower = commandCenter.account_summary.buying_power
    ? toCurrency(commandCenter.account_summary.buying_power)
    : '—'

  const accountMode = configSummary.live_disable_report.paper_only_mode
    ? 'Paper Only'
    : configSummary.live_disable_report.live_trading_enabled
      ? 'Live Active'
      : 'Live Disabled'
  const accountModeTone: RiskTone = configSummary.live_disable_report.paper_only_mode
    ? 'info'
    : configSummary.live_disable_report.live_trading_enabled
      ? 'risk'
      : 'watch'

  const unacknowledgedIncidents = incidents.filter((incident) => !incident.acknowledged_at_utc).length

  const sparkline = useMemo(() => {
    const seconds = runtimeHeartbeat.cadence_seconds || 0
    if (seconds <= 0) {
      return [4, 5, 4, 5, 4, 5, 4, 5]
    }
    const baseline = Math.min(9, Math.max(3, Math.round(9 - seconds / 60)))
    return Array.from({ length: 8 }, (_, i) => Math.max(2, baseline + ((i % 2 === 0 ? 1 : -1) * 1)))
  }, [runtimeHeartbeat.cadence_seconds])

  const heartbeatLabel = runtimeHeartbeat.last_evaluation_at_utc
    ? formatAgo(runtimeHeartbeat.last_evaluation_at_utc, now.getTime())
    : 'Awaiting first heartbeat'
  const marketStatusLabel = compactMarketSession(commandCenter.market_session_label || 'Market Closed')

  return (
    <header className={styles.topStrip} role="banner">
      <StatusCard label="Market">
        <div className={`${styles.statusCardChip} ${chipClass(risk.tone)}`}>
          <span className={dotClass(risk.tone)} />
          {marketStatusLabel}
        </div>
        <span className={styles.statusCardSub}>
          {prettyLabel(commandCenter.session_mode || 'standby')}
        </span>
      </StatusCard>

      <StatusCard label="Local Time">
        <span className={`${styles.statusCardValue} numeric`}>{formatTime(now)}</span>
        <span className={styles.statusCardSub}>{formatDate(now)}</span>
      </StatusCard>

      <StatusCard label="Runtime">
        <div className={`${styles.statusCardChip} ${chipClass(runtimeTone)}`}>
          <Activity size={11} />
          {runtimeHeartbeat.heartbeat_state || 'Idle'}
          <Sparkline values={sparkline} />
        </div>
        <span className={styles.statusCardSub}>{heartbeatLabel}</span>
      </StatusCard>

      <StatusCard label="Mode">
        <div className={`${styles.statusCardChip} ${chipClass(accountModeTone)}`}>{accountMode}</div>
        <span className={styles.statusCardSub}>
          {configSummary.live_disable_report.manual_kill_switch_active
            ? 'Kill switch active'
            : 'No live'}
        </span>
      </StatusCard>

      <StatusCard label="Equity">
        <span className={`${styles.statusCardValue} numeric`}>{equity}</span>
        <span className={`${styles.statusCardSub} numeric`}>Cash: {cash}</span>
      </StatusCard>

      <StatusCard label="Daily P&amp;L">
        <span
          className={`${styles.statusCardValue} numeric ${
            dailyPnl.tone === 'good' ? 'text-good' : dailyPnl.tone === 'risk' ? 'text-risk' : ''
          }`}
        >
          {dailyPnl.display}
        </span>
        <span className={styles.statusCardSub}>
          {commandCenter.service_status.cycles_completed
            ? `${commandCenter.service_status.cycles_completed} cycles`
            : 'No cycles yet'}
        </span>
      </StatusCard>

      <StatusCard label="Risk">
        <div className={`${styles.statusCardChip} ${chipClass(risk.tone)}`}>
          <span className={dotClass(risk.tone)} />
          {risk.label}
        </div>
        <span className={styles.statusCardSub}>{risk.detail}</span>
      </StatusCard>

      <StatusCard label="Buying Power">
        <span className={`${styles.statusCardValue} numeric`}>{buyingPower}</span>
        <span className={styles.statusCardSub}>
          {generatedAt ? `Updated ${formatAgo(generatedAt, now.getTime())}` : 'Awaiting snapshot'}
        </span>
      </StatusCard>

      <div className={styles.statusActions}>
        <button
          type="button"
          className={styles.iconButton}
          aria-label={`Alerts and messages: ${unacknowledgedIncidents} unacknowledged`}
          title="Alerts and messages"
          onClick={onOpenAlertsCenter}
        >
          <Bell size={16} />
          {unacknowledgedIncidents > 0 ? (
            <span className={styles.iconButtonBadge}>{unacknowledgedIncidents}</span>
          ) : null}
        </button>
      </div>
    </header>
  )
}

function compactMarketSession(value: string): string {
  const label = prettyLabel(value)
  if (/market closed posture/i.test(label)) return 'Market Closed'
  if (/local operator monitor/i.test(label)) return 'Monitor'
  return label
}

function chipClass(tone: RiskTone): string {
  if (tone === 'good') return styles.statusCardChipGood
  if (tone === 'watch') return styles.statusCardChipWatch
  if (tone === 'risk') return styles.statusCardChipRisk
  if (tone === 'info') return styles.statusCardChipInfo
  return styles.statusCardChipNeutral
}

function dotClass(tone: RiskTone): string {
  if (tone === 'good') return 'dot dot-good'
  if (tone === 'watch') return 'dot dot-watch'
  if (tone === 'risk') return 'dot dot-risk'
  if (tone === 'info') return 'dot dot-info'
  return 'dot dot-muted'
}

function StatusCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.statusCard}>
      <span className={styles.statusCardLabel}>{label}</span>
      {children}
    </div>
  )
}

function Sparkline({ values }: { values: number[] }) {
  const w = 48
  const h = 14
  const max = Math.max(...values)
  const step = w / (values.length - 1)
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(h - (v / max) * (h - 2) - 1).toFixed(1)}`)
    .join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function formatTime(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function formatDate(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    weekday: 'short',
  }).format(date)
}

function formatAgo(iso: string, nowMs: number): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) {
    return iso
  }
  const seconds = Math.max(0, Math.round((nowMs - then) / 1000))
  if (seconds < 60) {
    return `${seconds}s ago`
  }
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}
