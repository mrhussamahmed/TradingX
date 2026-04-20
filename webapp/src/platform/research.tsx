import type {
  DailySessionDigest,
  DocumentRecord,
  ExplorerRecord,
  Gate3PromotionPackage,
  Gate3ReadinessReport,
  ReplaySession,
  ResearchStudioSnapshot,
} from '../types'
import { formatTimestamp, prettyLabel } from './format'
import { KeyValueList, Panel, StatusBadge } from './ui'

export function ResearchWorkspace(props: {
  research: ResearchStudioSnapshot
  replay: ReplaySession
  explorer: ExplorerRecord[]
  documents: DocumentRecord[]
  digest: DailySessionDigest | null
  gate3Readiness: Gate3ReadinessReport
  gate3Package: Gate3PromotionPackage | null
}) {
  const evidenceRecords = [
    ...props.explorer.map((record) => ({
      id: record.record_id,
      title: record.title,
      kind: prettyLabel(record.category),
      preview: record.preview,
      location: record.path,
    })),
    ...props.documents.map((document) => ({
      id: document.doc_id,
      title: document.title,
      kind: prettyLabel(document.kind),
      preview: document.preview,
      location: document.path,
    })),
  ]
  const seenLocations = new Set<string>()
  const uniqueEvidenceRecords = evidenceRecords.filter((record) => {
    const key = `${record.title}|${record.location}`
    if (seenLocations.has(key)) {
      return false
    }
    seenLocations.add(key)
    return true
  })

  return (
    <div className="workspace-grid">
      <Panel title="Research" eyebrow="Audit, evidence, and improvement">
        <div className="hero-summary-grid">
          <article className="hero-summary-card">
            <span>Research state</span>
            <strong>
              {props.research.candidate_summaries.length
                ? 'Candidate review in progress'
                : 'Evidence review open'}
            </strong>
            <p>
              {props.research.decision_summary} Use this workspace to understand what happened, what evidence exists,
              and what should improve next.
            </p>
          </article>
          <article className="hero-summary-card">
            <span>Replay focus</span>
            <strong>{props.replay.headline}</strong>
            <p>{props.replay.summary}</p>
          </article>
          <article className="hero-summary-card">
            <span>Latest digest</span>
            <strong>{props.digest ? prettyLabel(props.digest.session_label) : 'No digest yet'}</strong>
            <p>{props.digest?.recommended_actions[0] || 'The next digest will appear after the next session event.'}</p>
          </article>
        </div>
      </Panel>

      <Panel title="Strategy Research" eyebrow="Candidate evaluation">
        {props.research.candidate_summaries.length ? (
          <div className="stack-list">
            {props.research.candidate_summaries.map((candidate) => (
              <article key={candidate.candidate_id} className="list-card">
                <div className="list-card-header">
                  <strong>{candidate.candidate_id}</strong>
                  <StatusBadge label={prettyLabel(candidate.recommendation)} tone="info" />
                </div>
                <p>{candidate.summary}</p>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <strong>No active candidate study</strong>
            <p>{props.research.decision_summary}</p>
          </div>
        )}
      </Panel>

      <Panel title="Replay & Audit" eyebrow="What happened">
        <div className="stack-list">
          <article className="list-card">
            <div className="list-card-header">
              <strong>{props.replay.headline}</strong>
              <span>{prettyLabel(props.replay.focus_type)}</span>
            </div>
            <p>{props.replay.summary}</p>
            <span>Updated {formatTimestamp(props.replay.events[0]?.occurred_at_utc)}</span>
          </article>
          {props.replay.events.map((event) => (
            <article key={event.event_id} className="list-card">
              <div className="list-card-header">
                <strong>{event.headline}</strong>
                <StatusBadge
                  label={prettyLabel(event.severity)}
                  tone={event.severity === 'warning' ? 'watch' : 'info'}
                />
              </div>
              <p>{event.details}</p>
              <span>{event.symbol} · {formatTimestamp(event.occurred_at_utc)}</span>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title="Evidence Library" eyebrow="Records you can inspect now">
        <p className="panel-supporting-text">Showing the most recent unique records so the evidence deck stays readable.</p>
        <div className="stack-list">
          {uniqueEvidenceRecords.length ? (
            uniqueEvidenceRecords.slice(0, 12).map((record) => (
              <article key={record.id} className="list-card">
                <div className="list-card-header">
                  <strong>{record.title}</strong>
                  <span>{record.kind}</span>
                </div>
                <p>{record.preview}</p>
                <span>{record.location}</span>
              </article>
            ))
          ) : (
            <div className="empty-state">
              <strong>No evidence records yet</strong>
              <p>Replay, validation, and operator documents will appear here as soon as TradingX records them.</p>
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Promotion & Diagnostics" eyebrow="Readiness gates">
        <KeyValueList
          items={[
            { label: 'Gate 3 status', value: prettyLabel(props.gate3Readiness.status) },
            { label: 'Closed trades', value: String(props.gate3Readiness.closed_trade_count) },
            { label: 'Observed days', value: String(props.gate3Readiness.calendar_days_observed) },
            { label: 'Promotion package', value: props.gate3Package?.status || 'Not generated' },
          ]}
        />
        <div className="stack-list">
          <article className="list-card">
            <div className="list-card-header">
              <strong>Gate 3 readiness</strong>
              <StatusBadge label={prettyLabel(props.gate3Readiness.status)} tone="watch" />
            </div>
            <p>{props.gate3Readiness.summary}</p>
            <span>{props.gate3Readiness.required_operator_action}</span>
          </article>
          {props.gate3Package ? (
            <article className="list-card">
              <div className="list-card-header">
                <strong>{props.gate3Package.headline}</strong>
                <span>{prettyLabel(props.gate3Package.status)}</span>
              </div>
              <p>{props.gate3Package.decision_summary}</p>
            </article>
          ) : null}
        </div>
      </Panel>
    </div>
  )
}
