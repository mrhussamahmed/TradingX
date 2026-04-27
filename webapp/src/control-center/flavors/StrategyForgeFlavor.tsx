import { useMemo, useState } from 'react'
import { CheckCircle2, FlaskConical, Plus, XCircle } from 'lucide-react'

import { parseNumericValue, prettyLabel } from '../../platform/format'
import type { ResearchCandidateSummary } from '../../types'
import { useData } from '../state/DataContext'

import styles from './Flavor.module.css'

const APPROVAL_AUTHORITY = false

export function StrategyForgeFlavor() {
  const { research, runtimeModel, runtimeSelection, configSummary, gate3Readiness } = useData()
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(
    () => research.candidate_summaries[0]?.candidate_id ?? null,
  )

  const candidates = research.candidate_summaries
  const selected: ResearchCandidateSummary | null = useMemo(() => {
    if (!selectedCandidateId) return null
    return candidates.find((candidate) => candidate.candidate_id === selectedCandidateId) ?? null
  }, [candidates, selectedCandidateId])

  const weightEntries = runtimeModel?.weights ? Object.entries(runtimeModel.weights) : []
  const weightTotal = weightEntries.reduce((sum, [, value]) => sum + parseNumericValue(value), 0) || 1

  const opportunities = runtimeSelection?.ranked_opportunities ?? []

  const liveExecutionBlocked = !configSummary.live_disable_report.live_trading_enabled
  const approvalBlocker = !APPROVAL_AUTHORITY
    ? 'Approval blocked: your operator role cannot approve strategy promotion. Request review from an authorized approver.'
    : liveExecutionBlocked
      ? 'Approval blocked: live trading is disabled. Paper-research approval is permitted but live deployment is not.'
      : null

  const evidenceMissing =
    selected && (!selected.adversarial_checks.length || !selected.gate_statuses)
  const promotionBlockedByEvidence = evidenceMissing
    ? 'Promotion blocked: candidate does not have complete adversarial checks or gate statuses. Run gate evaluation before approving.'
    : null

  return (
    <div className={styles.gridShell}>
      <div className={styles.forgeGrid}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Candidate Strategies</span>
            <span className={styles.panelSub}>
              {candidates.length} from research feed
            </span>
            <div className={styles.panelHeaderActions}>
              <button type="button" className="btn btn-sm" disabled>
                <Plus size={12} /> New Strategy
                <span className={styles.disabledNote} style={{ marginLeft: 4 }}>
                  (no proposal-create endpoint)
                </span>
              </button>
            </div>
          </div>
          {candidates.length === 0 ? (
            <div className={styles.panelBody}>
              <div className={styles.emptyState}>
                <strong>No candidates yet</strong>
                <p>{research.decision_summary || 'Research is waiting for the first candidate snapshot.'}</p>
              </div>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className={styles.simpleTable}>
                <thead>
                  <tr>
                    <th>Candidate</th>
                    <th>Family</th>
                    <th>Recommendation</th>
                    <th>Gate</th>
                    <th>Adversarial</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((candidate) => {
                    const recommendation = candidate.recommendation?.toLowerCase() ?? ''
                    const recommendationClass = /reject|block/.test(recommendation)
                      ? styles.statusRejected
                      : /watch|review/.test(recommendation)
                        ? styles.statusWatch
                        : /promote|approve|ready/.test(recommendation)
                          ? styles.statusActive
                          : styles.statusCandidate
                    const gateValues = Object.values(candidate.gate_statuses ?? {})
                    const failingGate = gateValues.find((value) =>
                      /fail|block|risk/i.test(value),
                    )
                    return (
                      <tr
                        key={candidate.candidate_id}
                        onClick={() => setSelectedCandidateId(candidate.candidate_id)}
                        style={{ cursor: 'pointer' }}
                        aria-selected={selectedCandidateId === candidate.candidate_id}
                      >
                        <td>
                          <div style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ fontWeight: 600 }}>{candidate.candidate_id}</span>
                            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                              {candidate.summary || 'No summary recorded.'}
                            </span>
                          </div>
                        </td>
                        <td>{prettyLabel(candidate.family)}</td>
                        <td>
                          <span className={[styles.statusPill, recommendationClass].filter(Boolean).join(' ')}>
                            {prettyLabel(candidate.recommendation || 'pending')}
                          </span>
                        </td>
                        <td>
                          <span className={`badge badge-${failingGate ? 'risk' : 'good'}`}>
                            {failingGate ? prettyLabel(failingGate) : `${gateValues.length} pass`}
                          </span>
                        </td>
                        <td>
                          {candidate.adversarial_checks.length > 0
                            ? `${candidate.adversarial_checks.length} checks`
                            : '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className={styles.gridShell}>
          <div className={styles.inspectorPanel}>
            <h3>Inspector</h3>
            {selected ? (
              <CandidateInspector candidate={selected} />
            ) : (
              <p>Select a candidate to inspect.</p>
            )}

            <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={!selected || !!approvalBlocker || !!promotionBlockedByEvidence}
              >
                <CheckCircle2 size={12} /> Approve
              </button>
              <button
                type="button"
                className="btn btn-warn btn-sm"
                disabled={!selected || !!approvalBlocker}
              >
                <XCircle size={12} /> Reject
              </button>
              <button type="button" className="btn btn-sm" disabled={!selected}>
                <FlaskConical size={12} /> Simulate
              </button>
            </div>
            {approvalBlocker ? (
              <p className={styles.disabledNote}>{approvalBlocker}</p>
            ) : null}
            {promotionBlockedByEvidence ? (
              <p className={styles.disabledNote}>{promotionBlockedByEvidence}</p>
            ) : null}
          </div>

          <div className={styles.panel}>
            <div className={styles.panelHeader}>
              <span>Gate 3 Readiness</span>
              <span className={styles.panelSub}>{prettyLabel(gate3Readiness.status)}</span>
            </div>
            <div className={styles.panelBody}>
              <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{gate3Readiness.summary}</p>
              {gate3Readiness.required_operator_action ? (
                <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 12 }}>
                  Operator action: {gate3Readiness.required_operator_action}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <div className={styles.forgeRow}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Model Weights</span>
            <span className={styles.panelSub}>
              {runtimeModel?.snapshot_id ? `Snapshot ${runtimeModel.snapshot_id}` : 'No snapshot yet'}
            </span>
          </div>
          <div className={styles.panelBody}>
            {weightEntries.length === 0 ? (
              <div className={styles.emptyState}>
                <strong>No model weights yet</strong>
                <p>Run a strategy training cycle to populate model snapshot weights.</p>
              </div>
            ) : (
              <div className={styles.weightLegend}>
                {weightEntries.map(([key, value]) => {
                  const numeric = parseNumericValue(value)
                  const ratio = numeric / weightTotal
                  return (
                    <div key={key} style={{ display: 'contents' }}>
                      <span>
                        <span
                          className={styles.weightSwatch}
                          style={{ background: weightSwatchColor(key) }}
                        />
                        {prettyLabel(key)}
                      </span>
                      <span>
                        {numeric.toFixed(3)} <span style={{ color: 'var(--text-muted)' }}>({(ratio * 100).toFixed(0)}%)</span>
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Opportunity Selection</span>
            <span className={styles.panelSub}>
              {runtimeSelection?.selection_id ? `Selection ${runtimeSelection.selection_id}` : 'Pending'}
            </span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            {opportunities.length === 0 ? (
              <div className={styles.panelBody}>
                <div className={styles.emptyState}>
                  <strong>No opportunities ranked</strong>
                  <p>Selection waits for runtime model + symbol heartbeat data.</p>
                </div>
              </div>
            ) : (
              <table className={styles.simpleTable}>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Final Score</th>
                    <th>Threshold</th>
                    <th>Eligible</th>
                  </tr>
                </thead>
                <tbody>
                  {opportunities.map((opportunity) => (
                    <tr key={opportunity.symbol}>
                      <td className="mono">{opportunity.symbol}</td>
                      <td className="numeric">{opportunity.final_score}</td>
                      <td className="numeric">{opportunity.regime_weight}</td>
                      <td>
                        <span className={`badge badge-${opportunity.eligible ? 'good' : 'risk'}`}>
                          {opportunity.eligible ? 'Eligible' : opportunity.ineligibility_reason || 'Blocked'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function CandidateInspector({ candidate }: { candidate: ResearchCandidateSummary }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <h3>{candidate.candidate_id}</h3>
      <p>{candidate.summary || 'No summary available.'}</p>
      <div className={styles.weightLegend}>
        {Object.entries(candidate.candidate_metrics ?? {}).map(([key, value]) => (
          <div key={key} style={{ display: 'contents' }}>
            <span>{prettyLabel(key)}</span>
            <span className="numeric">{value}</span>
          </div>
        ))}
      </div>
      {candidate.adversarial_checks.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--text-secondary)', fontSize: 12 }}>
          {candidate.adversarial_checks.map((check, i) => (
            <li key={i}>{check}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

function weightSwatchColor(key: string): string {
  let hash = 0
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0
  }
  const hue = hash % 360
  return `hsl(${hue}, 70%, 60%)`
}
