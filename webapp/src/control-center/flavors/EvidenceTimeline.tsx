import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import { ChevronLeft, ChevronRight, Pause, Play, Search } from 'lucide-react'

import { formatTimestamp } from '../../platform/format'
import type { ExplorerRecord, IncidentRecord, OperatorTimelineEvent } from '../../types'

import styles from './Flavor.module.css'

export type TimelineSeverity = 'good' | 'info' | 'watch' | 'risk'

export type TimelineEvent = {
  id: string
  timestamp: string
  category: string
  source: string
  severity: TimelineSeverity
  symbol?: string
  headline: string
  detail?: string
  evidenceRef?: string
}

export type EvidenceTimelineProps = {
  events: TimelineEvent[]
  showEvidenceLayer: boolean
  initialPageSize?: number
  symbolFilter?: string
  emptyStateMessage?: string
}

const DEFAULT_PAGE_SIZE = 50
const VIRTUAL_THRESHOLD = 100

function severityBadge(severity: TimelineSeverity): string {
  if (severity === 'good') return 'badge badge-good'
  if (severity === 'watch') return 'badge badge-watch'
  if (severity === 'risk') return 'badge badge-risk'
  return 'badge badge-info'
}

const RISK_PATTERN = /\b(?:critical|high|risk(?:y)?|fail(?:ed|ing|ure)?|block(?:ed|ing)?|error(?:ed)?)\b/
const WATCH_PATTERN = /\b(?:watch(?:ed|ing)?|warn(?:ed|ing)?|degrad(?:ed|ing)?)\b/
const GOOD_PATTERN = /\b(?:pass(?:ed|ing)?|good|ok(?:ay)?|complete(?:d)?)\b/

// eslint-disable-next-line react-refresh/only-export-components
export function deriveTimelineSeverity(input: string | undefined): TimelineSeverity {
  if (!input) return 'info'
  const lowered = input.toLowerCase()
  if (RISK_PATTERN.test(lowered)) return 'risk'
  if (WATCH_PATTERN.test(lowered)) return 'watch'
  if (GOOD_PATTERN.test(lowered)) return 'good'
  return 'info'
}

// eslint-disable-next-line react-refresh/only-export-components
export function buildTimelineFromIncidents(incidents: IncidentRecord[]): TimelineEvent[] {
  return incidents.map((incident) => ({
    id: `incident:${incident.incident_id}`,
    timestamp: incident.latest_seen_at_utc,
    category: incident.category || 'incident',
    source: 'incidents',
    severity: deriveTimelineSeverity(incident.severity),
    headline: incident.title,
    detail: incident.summary,
    evidenceRef: incident.evidence_refs[0],
  }))
}

// eslint-disable-next-line react-refresh/only-export-components
export function buildTimelineFromReplay(events: OperatorTimelineEvent[]): TimelineEvent[] {
  return events.map((event) => ({
    id: `replay:${event.event_id}`,
    timestamp: event.occurred_at_utc,
    category: event.event_type,
    source: 'replay',
    severity: deriveTimelineSeverity(event.severity),
    symbol: event.symbol || undefined,
    headline: event.headline,
    detail: event.details,
    evidenceRef: event.artifact_path,
  }))
}

// eslint-disable-next-line react-refresh/only-export-components
export function buildTimelineFromExplorer(records: ExplorerRecord[]): TimelineEvent[] {
  return records.map((record) => ({
    id: `explorer:${record.record_id}`,
    timestamp: record.recorded_at_utc,
    category: record.category || 'evidence',
    source: 'explorer',
    severity: 'info',
    symbol: record.symbol || undefined,
    headline: record.title,
    detail: record.preview,
    evidenceRef: record.path,
  }))
}

export function EvidenceTimeline({
  events,
  showEvidenceLayer,
  initialPageSize,
  symbolFilter,
  emptyStateMessage,
}: EvidenceTimelineProps) {
  const [search, setSearch] = useState('')
  const [severityFilter, setSeverityFilter] = useState<'all' | TimelineSeverity>('all')
  const [sourceFilter, setSourceFilter] = useState<'all' | string>('all')
  const [paused, setPaused] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const [page, setPage] = useState(0)
  const tableRef = useRef<HTMLDivElement | null>(null)
  const pageSize = initialPageSize ?? DEFAULT_PAGE_SIZE

  const sources = useMemo(() => {
    const set = new Set<string>()
    events.forEach((event) => {
      if (event.source) set.add(event.source)
    })
    return Array.from(set)
  }, [events])

  const filteredEvents = useMemo(() => {
    if (paused) {
      return events
    }
    let next = events
    if (symbolFilter) {
      next = next.filter((event) => !event.symbol || event.symbol === symbolFilter)
    }
    if (severityFilter !== 'all') {
      next = next.filter((event) => event.severity === severityFilter)
    }
    if (sourceFilter !== 'all') {
      next = next.filter((event) => event.source === sourceFilter)
    }
    if (search.trim()) {
      const term = search.toLowerCase()
      next = next.filter(
        (event) =>
          event.headline.toLowerCase().includes(term) ||
          (event.detail?.toLowerCase().includes(term) ?? false) ||
          (event.symbol?.toLowerCase().includes(term) ?? false) ||
          (event.evidenceRef?.toLowerCase().includes(term) ?? false),
      )
    }
    return next
  }, [events, severityFilter, sourceFilter, search, paused, symbolFilter])

  const sorted = useMemo(() => {
    return [...filteredEvents].sort((a, b) => {
      const at = new Date(a.timestamp).getTime() || 0
      const bt = new Date(b.timestamp).getTime() || 0
      return bt - at
    })
  }, [filteredEvents])

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize))
  const safePage = Math.min(page, totalPages - 1)
  const pageStart = safePage * pageSize
  const pageEvents = sorted.slice(pageStart, pageStart + pageSize)
  const usePagination = sorted.length > VIRTUAL_THRESHOLD

  useEffect(() => {
    if (page > totalPages - 1) {
      setPage(Math.max(0, totalPages - 1)) // eslint-disable-line react-hooks/set-state-in-effect
    }
  }, [page, totalPages])

  useEffect(() => {
    if (autoScroll && tableRef.current) {
      tableRef.current.scrollTop = 0
    }
  }, [autoScroll, sorted])

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <span>Evidence Timeline</span>
        <span className={styles.panelSub}>
          {sorted.length} event{sorted.length === 1 ? '' : 's'}
          {showEvidenceLayer ? '' : ' · markers off'}
        </span>
      </div>
      <div className={styles.evidenceFilters}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Search size={12} color="var(--text-muted)" aria-hidden />
          <input
            className={styles.evidenceSearch}
            type="search"
            value={search}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setSearch(event.target.value)
              setPage(0)
            }}
            placeholder="Search evidence (headline, ref, symbol)"
            aria-label="Search evidence"
          />
        </span>
        <select
          aria-label="Severity filter"
          value={severityFilter}
          onChange={(event) => {
            setSeverityFilter(event.target.value as 'all' | TimelineSeverity)
            setPage(0)
          }}
        >
          <option value="all">All severities</option>
          <option value="risk">Risk</option>
          <option value="watch">Watch</option>
          <option value="info">Info</option>
          <option value="good">Good</option>
        </select>
        <select
          aria-label="Source filter"
          value={sourceFilter}
          onChange={(event) => {
            setSourceFilter(event.target.value)
            setPage(0)
          }}
        >
          <option value="all">All sources</option>
          {sources.map((source) => (
            <option key={source} value={source}>
              {source}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={paused ? 'btn btn-warn btn-sm' : 'btn btn-sm'}
          onClick={() => setPaused((value) => !value)}
          aria-pressed={paused}
        >
          {paused ? (
            <>
              <Play size={12} /> Resume
            </>
          ) : (
            <>
              <Pause size={12} /> Pause
            </>
          )}
        </button>
        <button
          type="button"
          className={autoScroll ? 'btn btn-sm' : 'btn btn-sm btn-ghost'}
          onClick={() => setAutoScroll((value) => !value)}
          aria-pressed={autoScroll}
        >
          Auto-scroll: {autoScroll ? 'on' : 'off'}
        </button>
      </div>
      <div ref={tableRef} style={{ maxHeight: 360, overflow: 'auto' }}>
        {sorted.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>No evidence yet</strong>
            <p>{emptyStateMessage ?? 'Evidence events will appear here as they are recorded.'}</p>
          </div>
        ) : (
          <table className={styles.simpleTable}>
            <thead>
              <tr>
                <th style={{ width: 140 }}>When</th>
                <th style={{ width: 110 }}>Type</th>
                <th style={{ width: 90 }}>Symbol</th>
                <th>Headline</th>
                <th style={{ width: 100 }}>Severity</th>
                {showEvidenceLayer ? <th style={{ width: 180 }}>Evidence</th> : null}
              </tr>
            </thead>
            <tbody>
              {pageEvents.map((event) => (
                <tr key={event.id}>
                  <td className="numeric">{formatTimestamp(event.timestamp)}</td>
                  <td>{event.category}</td>
                  <td className="mono" style={{ fontSize: 11 }}>
                    {event.symbol ?? '—'}
                  </td>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <span>{event.headline}</span>
                      {event.detail ? (
                        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{event.detail}</span>
                      ) : null}
                    </div>
                  </td>
                  <td>
                    <span className={severityBadge(event.severity)}>{event.severity}</span>
                  </td>
                  {showEvidenceLayer ? (
                    <td className={styles.evidenceRefCell} title={event.evidenceRef}>
                      {event.evidenceRef ? truncateMiddle(event.evidenceRef, 28) : '—'}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {usePagination ? (
        <div className={styles.evidencePagination}>
          <span>
            Showing {pageStart + 1}–{Math.min(sorted.length, pageStart + pageSize)} of {sorted.length}
          </span>
          <span className={styles.spacer} />
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => setPage((value) => Math.max(0, value - 1))}
            disabled={safePage === 0}
            aria-label="Previous page"
          >
            <ChevronLeft size={12} /> Prev
          </button>
          <span>
            Page {safePage + 1} / {totalPages}
          </span>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => setPage((value) => Math.min(totalPages - 1, value + 1))}
            disabled={safePage >= totalPages - 1}
            aria-label="Next page"
          >
            Next <ChevronRight size={12} />
          </button>
        </div>
      ) : null}
    </div>
  )
}

function truncateMiddle(value: string, max: number): string {
  if (value.length <= max) return value
  const half = Math.floor((max - 1) / 2)
  return `${value.slice(0, half)}…${value.slice(-half)}`
}
