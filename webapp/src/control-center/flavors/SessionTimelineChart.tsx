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

const INSTANT_CLUSTER_MS = 15 * 60 * 1000

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
  const outOfSession = bounds ? summarizeOutOfSession(events, bounds) : { before: [], after: [] }

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
            {bounds?.source === 'authoritative_session'
              ? `Open ${formatTimelineTimestamp(bounds.start)}`
              : bounds
                ? `Reference open ${formatTimelineTimestamp(bounds.start)}`
                : 'Open missing'}
            {' · '}
            {bounds?.source === 'authoritative_session'
              ? `Close ${formatTimelineTimestamp(bounds.end)}`
              : bounds
                ? `Reference close ${formatTimelineTimestamp(bounds.end)}`
                : 'Close missing'}
            {bounds?.source === 'regular_session_reference' ? ' · schedule metadata missing' : ''}
          </span>
        </div>

        {bounds?.source === 'regular_session_reference' ? (
          <div className={styles.timelineNotice}>
            Market-day schedule metadata is missing, so the chart uses the regular XNYS session as a visual
            reference only. Out-of-session activity is summarized instead of stretching the session axis.
          </div>
        ) : null}

        {outOfSession.before.length > 0 || outOfSession.after.length > 0 ? (
          <div className={styles.timelineOutOfSession}>
            {outOfSession.before.length > 0 ? (
              <OutOfSessionSummary label="Before session" events={outOfSession.before} />
            ) : null}
            {outOfSession.after.length > 0 ? (
              <OutOfSessionSummary label="After session" events={outOfSession.after} />
            ) : null}
          </div>
        ) : null}

        {timeline.session.partial_reason && bounds?.source !== 'regular_session_reference' ? (
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
                  {lanes.map((lane) => {
                    const laneEvents = events
                      .filter((event) => (event.event_type || 'event') === lane)
                      .filter((event) => isInBounds(event, bounds))
                    const renderedLane = prepareLaneEvents(laneEvents)
                    return (
                      <div key={lane} className={styles.timelineRow}>
                        {renderedLane.spans.map((event, index) => (
                          <TimelineBar
                            key={`${event.event_id}-${index}`}
                            event={event}
                            bounds={bounds}
                            color={colorByType.get(lane) ?? EVENT_COLORS[0]}
                          />
                        ))}
                        {renderedLane.clusters.map((cluster) => (
                          <TimelineCluster
                            key={cluster.id}
                            cluster={cluster}
                            bounds={bounds}
                            color={colorByType.get(lane) ?? EVENT_COLORS[0]}
                          />
                        ))}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function OutOfSessionSummary({ label, events }: { label: string; events: SessionTimelineEvent[] }) {
  const byType = events.reduce<Record<string, number>>((accumulator, event) => {
    const key = event.event_type || 'event'
    accumulator[key] = (accumulator[key] ?? 0) + 1
    return accumulator
  }, {})
  const detail = Object.entries(byType)
    .map(([type, count]) => `${prettyLabel(type)}: ${count}`)
    .join('\n')
  return (
    <span className={styles.timelineOutOfSessionItem} title={detail}>
      {label}: {events.length}
    </span>
  )
}

function TimelineCluster({
  cluster,
  bounds,
  color,
}: {
  cluster: TimelineEventCluster
  bounds: TimelineBounds
  color: string
}) {
  const leftPct = clamp(((cluster.start - bounds.start) / bounds.span) * 100, 0, 100)
  const widthPct = Math.max(0.7, ((cluster.end - cluster.start) / bounds.span) * 100)
  const tooltip = clusterTooltip(cluster)
  const isSingle = cluster.events.length === 1
  return (
    <button
      type="button"
      className={`${styles.sessionTimelineCluster} ${isSingle ? styles.sessionTimelineSingleInstant : ''}`}
      style={{
        left: `${leftPct}%`,
        width: `${Math.min(widthPct, 8)}%`,
        borderColor: color,
        backgroundColor: color,
      }}
      title={tooltip}
      aria-label={`${prettyLabel(cluster.eventType)} ${isSingle ? cluster.events[0].headline : `${cluster.events.length} events`}`}
    >
      <span>{isSingle ? instantLabel(cluster.events[0]) : cluster.events.length}</span>
    </button>
  )
}

function TimelineBar({
  event,
  bounds,
  color,
}: {
  event: SessionTimelineEvent
  bounds: TimelineBounds
  color: string
}) {
  const startTime = eventTime(event, 'start')
  const endTime = eventTime(event, 'end')
  const widthPct = Math.max(1.5, ((endTime - startTime) / bounds.span) * 100)
  const safeWidth = Math.min(widthPct, 100)
  const leftPct = clamp(((startTime - bounds.start) / bounds.span) * 100, 0, 100)
  const tooltip = eventTooltip(event)

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

type TimelineBounds = {
  start: number
  end: number
  span: number
  source: 'authoritative_session' | 'regular_session_reference' | 'event_range'
}

type TimelineEventCluster = {
  id: string
  eventType: string
  start: number
  end: number
  events: SessionTimelineEvent[]
}

function prepareLaneEvents(events: SessionTimelineEvent[]) {
  const spans: SessionTimelineEvent[] = []
  const instantBuckets = new Map<string, TimelineEventCluster>()

  for (const event of events) {
    if (isAuthoritativeSpan(event)) {
      spans.push(event)
      continue
    }
    const occurred = eventTime(event, 'instant')
    const bucketStart = Math.floor(occurred / INSTANT_CLUSTER_MS) * INSTANT_CLUSTER_MS
    const bucketEnd = bucketStart + INSTANT_CLUSTER_MS
    const eventType = event.event_type || 'event'
    const id = `${eventType}-${bucketStart}`
    const existing = instantBuckets.get(id)
    if (existing) {
      existing.events.push(event)
      existing.start = Math.min(existing.start, occurred)
      existing.end = Math.max(existing.end, occurred + 60_000)
    } else {
      instantBuckets.set(id, {
        id,
        eventType,
        start: occurred,
        end: Math.min(bucketEnd, occurred + 60_000),
        events: [event],
      })
    }
  }

  return {
    spans,
    clusters: Array.from(instantBuckets.values()).sort((left, right) => left.start - right.start),
  }
}

function isAuthoritativeSpan(event: SessionTimelineEvent): boolean {
  return Boolean(event.shape === 'span' && event.started_at_utc && event.ended_at_utc)
}

function isInBounds(event: SessionTimelineEvent, bounds: TimelineBounds): boolean {
  const start = eventTime(event, 'start')
  const end = eventTime(event, 'end')
  return end >= bounds.start && start <= bounds.end
}

function summarizeOutOfSession(events: SessionTimelineEvent[], bounds: TimelineBounds) {
  return events.reduce(
    (summary, event) => {
      const start = eventTime(event, 'start')
      const end = eventTime(event, 'end')
      if (end < bounds.start) summary.before.push(event)
      if (start > bounds.end) summary.after.push(event)
      return summary
    },
    { before: [] as SessionTimelineEvent[], after: [] as SessionTimelineEvent[] },
  )
}

function eventTime(event: SessionTimelineEvent, edge: 'start' | 'end' | 'instant'): number {
  if (edge === 'start' && isAuthoritativeSpan(event)) {
    return new Date(event.started_at_utc as string).getTime()
  }
  if (edge === 'end' && isAuthoritativeSpan(event)) {
    return new Date(event.ended_at_utc as string).getTime()
  }
  return new Date(event.occurred_at_utc).getTime()
}

function eventTooltip(event: SessionTimelineEvent): string {
  return [
    `Type: ${prettyLabel(event.event_type)}`,
    event.symbol ? `Symbol: ${event.symbol}` : 'Symbol: none',
    `Start: ${formatTimestamp(event.started_at_utc ?? event.occurred_at_utc)}`,
    `End: ${formatTimestamp(event.ended_at_utc ?? event.occurred_at_utc)}`,
    `Duration: ${formatDuration(event.duration_seconds)}`,
    `Status: ${prettyLabel(event.status)}`,
    `Reason: ${event.reason || event.details || 'Not provided'}`,
    `Evidence freshness: ${prettyLabel(event.evidence_freshness || event.source_status)}`,
  ].join('\n')
}

function clusterTooltip(cluster: TimelineEventCluster): string {
  if (cluster.events.length === 1) return eventTooltip(cluster.events[0])
  const statuses = cluster.events.reduce<Record<string, number>>((accumulator, event) => {
    const key = event.status || 'unknown'
    accumulator[key] = (accumulator[key] ?? 0) + 1
    return accumulator
  }, {})
  const statusSummary = Object.entries(statuses)
    .map(([status, count]) => `${prettyLabel(status)}: ${count}`)
    .join(', ')
  const sampleReasons = cluster.events
    .slice(0, 4)
    .map((event) => event.reason || event.details || event.headline)
    .filter(Boolean)
    .join('\n')
  return [
    `Type: ${prettyLabel(cluster.eventType)}`,
    `Events: ${cluster.events.length}`,
    `First: ${formatTimelineTimestamp(cluster.start)}`,
    `Last: ${formatTimelineTimestamp(cluster.end)}`,
    `Status summary: ${statusSummary}`,
    sampleReasons ? `Sample reasons:\n${sampleReasons}` : 'Sample reasons: none',
  ].join('\n')
}

function instantLabel(event: SessionTimelineEvent): string {
  if (event.symbol) return event.symbol
  const label = prettyLabel(event.event_type)
  return label.slice(0, 1)
}

function timelineBounds(timeline: SessionTimelineResponse): TimelineBounds | null {
  const sessionOpen = timeline.session.session_open_at_utc
    ? new Date(timeline.session.session_open_at_utc).getTime()
    : NaN
  const sessionClose = timeline.session.session_close_at_utc
    ? new Date(timeline.session.session_close_at_utc).getTime()
    : NaN
  if (!Number.isNaN(sessionOpen) && !Number.isNaN(sessionClose) && sessionClose > sessionOpen) {
    return {
      start: sessionOpen,
      end: sessionClose,
      span: Math.max(60_000, sessionClose - sessionOpen),
      source: 'authoritative_session',
    }
  }

  const reference = regularXnysSessionReference(timeline.filters.trading_day || timeline.session.trading_day)
  if (reference) {
    return {
      ...reference,
      span: reference.end - reference.start,
      source: 'regular_session_reference',
    }
  }

  const timestamps = timeline.events
    .map((event) => new Date(event.occurred_at_utc).getTime())
    .filter((value) => !Number.isNaN(value))
  if (timestamps.length === 0) return null
  const start = Math.min(...timestamps)
  const end = Math.max(...timestamps)
  return { start, end, span: Math.max(60_000, end - start), source: 'event_range' }
}

function regularXnysSessionReference(tradingDay: string): { start: number; end: number } | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(tradingDay)) return null
  const offsetHours = isEasternDaylightTime(tradingDay) ? 4 : 5
  const open = Date.parse(`${tradingDay}T09:30:00-0${offsetHours}:00`)
  const close = Date.parse(`${tradingDay}T16:00:00-0${offsetHours}:00`)
  if (Number.isNaN(open) || Number.isNaN(close) || close <= open) return null
  return { start: open, end: close }
}

function isEasternDaylightTime(tradingDay: string): boolean {
  const [yearText, monthText, dayText] = tradingDay.split('-')
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  if (!year || !month || !day) return true
  const dstStart = nthSundayOfMonth(year, 3, 2)
  const dstEnd = nthSundayOfMonth(year, 11, 1)
  const value = Date.UTC(year, month - 1, day)
  return value >= dstStart && value < dstEnd
}

function nthSundayOfMonth(year: number, month: number, occurrence: number): number {
  const first = new Date(Date.UTC(year, month - 1, 1))
  const firstSundayDate = 1 + ((7 - first.getUTCDay()) % 7)
  return Date.UTC(year, month - 1, firstSundayDate + (occurrence - 1) * 7)
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

function formatTimelineTimestamp(value: number): string {
  return formatTimestamp(new Date(value).toISOString())
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return 'instant'
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remaining = seconds % 60
  return remaining ? `${minutes}m ${remaining}s` : `${minutes}m`
}
