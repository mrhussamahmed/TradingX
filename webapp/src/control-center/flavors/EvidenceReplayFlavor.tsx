import { useMemo, useState } from 'react'
import { Copy, ExternalLink } from 'lucide-react'

import { formatTimestamp, prettyLabel } from '../../platform/format'
import type { OperatorTimelineEvent } from '../../types'
import { useData } from '../state/DataContext'
import { usePreferences } from '../state/PreferencesContext'
import { useToast } from '../state/ToastContext'

import {
  EvidenceTimeline,
  buildTimelineFromExplorer,
  buildTimelineFromIncidents,
  buildTimelineFromReplay,
  deriveTimelineSeverity,
  type TimelineEvent,
  type TimelineSeverity,
} from './EvidenceTimeline'
import styles from './Flavor.module.css'

type ReplayTrack = {
  id: string
  label: string
  matcher: (event: OperatorTimelineEvent) => boolean
}

const TRACKS: ReadonlyArray<ReplayTrack> = [
  { id: 'trades', label: 'Trades', matcher: (event) => /trade|execution|fill|order/i.test(event.event_type) },
  { id: 'signals', label: 'Signals', matcher: (event) => /signal|opportunity|score/i.test(event.event_type) },
  { id: 'risk', label: 'Risk', matcher: (event) => /risk|gate|drawdown|limit/i.test(event.event_type) },
  { id: 'events', label: 'Events', matcher: (event) => /event|cycle|heartbeat|alert/i.test(event.event_type) },
  { id: 'incidents', label: 'Incidents', matcher: (event) => /incident|halt|kill/i.test(event.event_type) },
  { id: 'documents', label: 'Documents', matcher: (event) => /document|artifact|report|digest/i.test(event.event_type) },
]

const TRACK_COLOR: Record<TimelineSeverity, string> = {
  good: 'var(--good)',
  watch: 'var(--watch)',
  risk: 'var(--risk)',
  info: 'var(--primary-bright)',
}

function placeEventOnTrack(events: OperatorTimelineEvent[], track: ReplayTrack) {
  return events.filter(track.matcher)
}

export function EvidenceReplayFlavor() {
  const { replay, incidents, explorer, documents, digest } = useData()
  const { prefs } = usePreferences()
  const { pushToast } = useToast()
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)

  const sortedEvents = useMemo(() => {
    return [...replay.events].sort((a, b) => {
      const at = new Date(a.occurred_at_utc).getTime() || 0
      const bt = new Date(b.occurred_at_utc).getTime() || 0
      return at - bt
    })
  }, [replay.events])

  const timeBounds = useMemo(() => {
    if (sortedEvents.length === 0) return null
    const earliest = new Date(sortedEvents[0].occurred_at_utc).getTime()
    const latest = new Date(sortedEvents[sortedEvents.length - 1].occurred_at_utc).getTime()
    if (Number.isNaN(earliest) || Number.isNaN(latest) || earliest === latest) return null
    return { earliest, latest, span: latest - earliest }
  }, [sortedEvents])

  const allTimelineEvents: TimelineEvent[] = useMemo(() => {
    const items: TimelineEvent[] = [
      ...buildTimelineFromIncidents(incidents),
      ...buildTimelineFromReplay(replay.events),
      ...buildTimelineFromExplorer(explorer),
    ]
    documents.forEach((doc) => {
      items.push({
        id: `doc:${doc.doc_id}`,
        timestamp: digest?.generated_at_utc ?? new Date().toISOString(),
        category: doc.kind,
        source: 'documents',
        severity: 'info',
        headline: doc.title,
        detail: doc.preview,
        evidenceRef: doc.path,
      })
    })
    return items
  }, [incidents, replay.events, explorer, documents, digest])

  const selected = useMemo(() => {
    if (!selectedEventId) return null
    return replay.events.find((event) => event.event_id === selectedEventId) ?? null
  }, [replay.events, selectedEventId])

  function handleCopy(value: string) {
    if (!navigator.clipboard) {
      pushToast('Clipboard API unavailable in this browser.', 'watch')
      return
    }
    void navigator.clipboard
      .writeText(value)
      .then(() => pushToast('Copied evidence ref.', 'good'))
      .catch(() => pushToast('Failed to copy evidence ref.', 'risk'))
  }

  return (
    <div className={styles.replayWrap}>
      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span>{replay.headline || 'Replay Session'}</span>
          <span className={styles.panelSub}>
            {replay.events.length} event{replay.events.length === 1 ? '' : 's'} · {prettyLabel(replay.focus_type)}: {replay.focus_value}
          </span>
        </div>
        <div className={styles.panelBody}>
          {sortedEvents.length === 0 || !timeBounds ? (
            <div className={styles.emptyState}>
              <strong>{replay.headline}</strong>
              <p>{replay.summary}</p>
            </div>
          ) : (
            <div className={styles.replayTimeline}>
              <div className={styles.timelineLanes}>
                {TRACKS.map((track) => (
                  <div key={track.id} className={styles.timelineLaneLabel}>
                    {track.label}
                  </div>
                ))}
              </div>
              <div className={styles.replayTracks}>
                {TRACKS.map((track) => {
                  const trackEvents = placeEventOnTrack(sortedEvents, track)
                  return (
                    <div key={track.id} className={styles.replayTrack}>
                      {trackEvents.map((event) => {
                        const ts = new Date(event.occurred_at_utc).getTime()
                        const ratio = (ts - timeBounds.earliest) / timeBounds.span
                        const severity = deriveTimelineSeverity(event.severity)
                        const color = TRACK_COLOR[severity]
                        return (
                          <button
                            type="button"
                            key={event.event_id}
                            className={styles.replayMarker}
                            style={{
                              left: `${Math.max(0, Math.min(0.99, ratio)) * 100}%`,
                              color,
                            }}
                            onClick={() => setSelectedEventId(event.event_id)}
                            title={`${formatTimestamp(event.occurred_at_utc)} — ${event.headline}`}
                          >
                            {event.symbol || prettyLabel(event.event_type)}
                          </button>
                        )
                      })}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          <div className={styles.controls}>
            <button type="button" className="btn btn-sm" disabled>
              Play
              <span className={styles.disabledNote} style={{ marginLeft: 4 }}>
                (replay is static)
              </span>
            </button>
            <button type="button" className="btn btn-sm" disabled>
              Pause
            </button>
            <button type="button" className="btn btn-sm" disabled>
              Step
            </button>
            <span className={styles.disabledNote}>
              Backend currently exposes a static replay snapshot.
            </span>
          </div>
        </div>
      </div>

      {selected ? (
        <div className={styles.inspectorPanel}>
          <h3>{selected.headline}</h3>
          <p>{selected.details || 'No detail available.'}</p>
          <div className={styles.weightLegend}>
            <div style={{ display: 'contents' }}>
              <span>Type</span>
              <span>{prettyLabel(selected.event_type)}</span>
              <span>Symbol</span>
              <span className="mono">{selected.symbol || '—'}</span>
              <span>Severity</span>
              <span>{selected.severity}</span>
              <span>When</span>
              <span className="numeric">{formatTimestamp(selected.occurred_at_utc)}</span>
            </div>
          </div>
          {selected.artifact_path ? (
            <pre>{selected.artifact_path}</pre>
          ) : null}
          {selected.related_ids.length > 0 ? (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {selected.related_ids.map((id) => (
                <span key={id} className="badge badge-info mono">
                  {id}
                </span>
              ))}
            </div>
          ) : null}
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!selected.artifact_path}
              onClick={() => {
                if (selected.artifact_path && /^https?:/.test(selected.artifact_path)) {
                  window.open(selected.artifact_path, '_blank', 'noreferrer')
                } else {
                  pushToast('Artifact path is local — open via runbook tooling.', 'watch')
                }
              }}
            >
              <ExternalLink size={12} /> Open Artifact
            </button>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!selected.artifact_path}
              onClick={() => selected.artifact_path && handleCopy(selected.artifact_path)}
            >
              <Copy size={12} /> Copy Ref
            </button>
          </div>
        </div>
      ) : null}

      <EvidenceTimeline
        events={allTimelineEvents}
        showEvidenceLayer={prefs.showEvidenceLayer}
      />
    </div>
  )
}
