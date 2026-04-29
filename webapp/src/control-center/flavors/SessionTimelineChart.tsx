import { Info } from 'lucide-react'

import { formatTimestamp, prettyLabel } from '../../platform/format'
import type { SessionTimelineEvent, SessionTimelineResponse } from '../../types'

import styles from './Flavor.module.css'

type Props = {
  title: string
  description: string
  timeline: SessionTimelineResponse
  selectedTradingDay: string
  onTradingDayChange: (tradingDay: string) => void
  emptyStateMessage: string
}

const EVENT_COLORS = [
  'var(--primary-bright)',
  'var(--good)',
  'var(--watch)',
  'var(--risk)',
  '#9b8cff',
  '#4fd6c8',
  '#f47cb9',
]

export function SessionTimelineChart({
  title,
  description,
  timeline,
  selectedTradingDay,
  onTradingDayChange,
  emptyStateMessage,
}: Props) {
  const events = timeline.events
  const lanes = Array.from(new Set(events.map((event) => event.event_type || 'event')))
  const colorByType = new Map(lanes.map((lane, index) => [lane, EVENT_COLORS[index % EVENT_COLORS.length]]))
  const bounds = timelineBounds(timeline)
  const dateValue = selectedTradingDay || timeline.filters.trading_day || ''

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <span>{title}</span>
        <span className={styles.panelSub}>
          {events.length} event{events.length === 1 ? '' : 's'} · {prettyLabel(timeline.session.status)}
        </span>
      </div>
      <div className={styles.panelBody}>
        <div className={styles.timelineControls}>
          <label className={styles.sizingField}>
            <span>Trading day</span>
            <input
              aria-label={`${title} trading day`}
              type="date"
              value={dateValue}
              list={`${title.replace(/\s+/g, '-')}-days`}
              onChange={(event) => onTradingDayChange(event.currentTarget.value)}
            />
            <datalist id={`${title.replace(/\s+/g, '-')}-days`}>
              {timeline.available_trading_days.map((day) => (
                <option key={day} value={day} />
              ))}
            </datalist>
          </label>
          <span className={styles.timelineInfo} title={description}>
            <Info size={14} aria-hidden />
            {timeline.session.session_open_at_utc
              ? `Open ${formatTimestamp(timeline.session.session_open_at_utc)}`
              : 'Open missing'}
            {' · '}
            {timeline.session.session_close_at_utc
              ? `Close ${formatTimestamp(timeline.session.session_close_at_utc)}`
              : 'Close missing'}
          </span>
        </div>

        {timeline.session.partial_reason ? (
          <div className={styles.timelineWarning}>{timeline.session.partial_reason}</div>
        ) : null}

        {events.length === 0 || bounds === null ? (
          <div className={styles.emptyState}>
            <strong>No timeline events</strong>
            <p>{emptyStateMessage}</p>
          </div>
        ) : (
          <>
            <div className={styles.timelineLegend}>
              {lanes.map((lane) => (
                <span key={lane}>
                  <i style={{ background: colorByType.get(lane) }} />
                  {prettyLabel(lane)}
                </span>
              ))}
            </div>
            <div className={styles.sessionTimelineScroller}>
              <div className={styles.timelineWrap} style={{ minWidth: 1040 }}>
                <div className={styles.timelineLanes}>
                  {lanes.map((lane) => (
                    <div key={lane} className={styles.timelineLaneLabel}>
                      {prettyLabel(lane)}
                    </div>
                  ))}
                </div>
                <div className={styles.timelineRows}>
                  <div className={styles.timelineHeader}>
                    {Array.from({ length: 8 }, (_, index) => (
                      <span key={index}>
                        {formatTimestampSlice(bounds.start + (index * bounds.span) / 7)}
                      </span>
                    ))}
                  </div>
                  {lanes.map((lane) => (
                    <div key={lane} className={styles.timelineRow}>
                      {events
                        .filter((event) => (event.event_type || 'event') === lane)
                        .map((event, index) => (
                          <TimelineBar
                            key={`${event.event_id}-${index}`}
                            event={event}
                            bounds={bounds}
                            color={colorByType.get(lane) ?? EVENT_COLORS[0]}
                          />
                        ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function TimelineBar({
  event,
  bounds,
  color,
}: {
  event: SessionTimelineEvent
  bounds: { start: number; span: number }
  color: string
}) {
  const startTime =
    event.shape === 'span' && event.started_at_utc
      ? new Date(event.started_at_utc).getTime()
      : new Date(event.occurred_at_utc).getTime()
  const endTime =
    event.shape === 'span' && event.ended_at_utc
      ? new Date(event.ended_at_utc).getTime()
      : startTime
  const widthPct =
    event.shape === 'span' && event.started_at_utc && event.ended_at_utc
      ? Math.max(1, ((endTime - startTime) / bounds.span) * 100)
      : 0.75
  const safeWidth = Math.min(widthPct, 100)
  const leftPct = clamp(((startTime - bounds.start) / bounds.span) * 100, 0, 100)
  const tooltip = [
    `Type: ${prettyLabel(event.event_type)}`,
    event.symbol ? `Symbol: ${event.symbol}` : 'Symbol: none',
    `Start: ${formatTimestamp(event.started_at_utc ?? event.occurred_at_utc)}`,
    `End: ${formatTimestamp(event.ended_at_utc ?? event.occurred_at_utc)}`,
    `Duration: ${formatDuration(event.duration_seconds)}`,
    `Status: ${prettyLabel(event.status)}`,
    `Reason: ${event.reason || event.details || 'Not provided'}`,
    `Evidence freshness: ${prettyLabel(event.evidence_freshness || event.source_status)}`,
  ].join('\n')

  return (
    <button
      type="button"
      className={styles.sessionTimelineEvent}
      style={{
        left: `${leftPct}%`,
        width: `${safeWidth}%`,
        transform: leftPct > 98 ? 'translateX(-100%)' : undefined,
        borderColor: color,
        color,
      }}
      title={tooltip}
      aria-label={`${prettyLabel(event.event_type)} ${event.headline}`}
    >
      <span>{event.symbol || prettyLabel(event.event_type)}</span>
      <small>{event.headline}</small>
    </button>
  )
}

function timelineBounds(timeline: SessionTimelineResponse) {
  const sessionOpen = timeline.session.session_open_at_utc
    ? new Date(timeline.session.session_open_at_utc).getTime()
    : NaN
  const sessionClose = timeline.session.session_close_at_utc
    ? new Date(timeline.session.session_close_at_utc).getTime()
    : NaN
  const timestamps = timeline.events
    .map((event) => new Date(event.occurred_at_utc).getTime())
    .filter((value) => !Number.isNaN(value))
  if (!Number.isNaN(sessionOpen) && !Number.isNaN(sessionClose) && sessionClose > sessionOpen) {
    const start = Math.min(sessionOpen, ...timestamps)
    const end = Math.max(sessionClose, ...timestamps)
    return { start, span: Math.max(60_000, end - start) }
  }
  if (timestamps.length === 0) return null
  const start = Math.min(...timestamps)
  const end = Math.max(...timestamps)
  return { start, span: Math.max(60_000, end - start) }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function formatTimestampSlice(value: number): string {
  return new Date(value).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return 'instant'
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remaining = seconds % 60
  return remaining ? `${minutes}m ${remaining}s` : `${minutes}m`
}
