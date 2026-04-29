import { useMemo } from 'react'

import { prettyLabel } from '../../platform/format'
import { useData } from '../state/DataContext'
import { usePreferences } from '../state/PreferencesContext'

import {
  EvidenceTimeline,
  buildTimelineFromExplorer,
  buildTimelineFromIncidents,
  buildTimelineFromReplay,
  type TimelineEvent,
} from './EvidenceTimeline'
import { SessionTimelineChart } from './SessionTimelineChart'
import styles from './Flavor.module.css'

export function EvidenceReplayFlavor() {
  const {
    replay,
    sessionTimeline,
    sessionTimelineDate,
    setSessionTimelineDate,
    incidents,
    explorer,
    documents,
    digest,
  } = useData()
  const { prefs } = usePreferences()

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

  return (
    <div className={styles.replayWrap}>
      <SessionTimelineChart
        title="Evidence / Why Timeline"
        description={`Shows evidence, action, and decision events for the selected trading day. Replay focus remains ${prettyLabel(replay.focus_type)}: ${replay.focus_value}.`}
        timeline={sessionTimeline}
        selectedTradingDay={sessionTimelineDate}
        onTradingDayChange={setSessionTimelineDate}
        emptyStateMessage={`No session-timeline evidence is available for ${sessionTimeline.filters.trading_day || 'the selected trading day'}. ${sessionTimeline.session.partial_reason || ''}`.trim()}
      />

      <EvidenceTimeline
        events={allTimelineEvents}
        showEvidenceLayer={prefs.showEvidenceLayer}
      />
    </div>
  )
}
