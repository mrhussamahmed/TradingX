import { useEffect, useState } from 'react'

import type {
  BotRuntimeState,
  CommandCenterSnapshot,
  ConfigSummary,
  DailySessionDigest,
  DocumentRecord,
  HistoricalWarmupRecord,
  IncidentRecord,
  ModelWeightSnapshot,
  OpportunitySelectionRecord,
  RuntimeHeartbeatSnapshot,
  StrategyActivationRecord,
} from '../types'
import { EquityChart, ExposureChart } from './charts'
import { formatTimestamp, formatTimeUntil, prettyLabel } from './format'
import { ActionButton, KeyValueList, Panel, StatusBadge } from './ui'

function badgeTone(
  tone: string | undefined,
): 'neutral' | 'good' | 'watch' | 'risk' | 'info' {
  if (tone === 'risk' || tone === 'watch' || tone === 'info' || tone === 'good') {
    return tone
  }
  return 'neutral'
}

export function MissionControlWorkspace(props: {
  commandCenter: CommandCenterSnapshot
  configSummary: ConfigSummary
  digest: DailySessionDigest | null
  documents: DocumentRecord[]
  incidents: IncidentRecord[]
  runtimeState: BotRuntimeState
  runtimeHeartbeat: RuntimeHeartbeatSnapshot
  runtimeWarmup: HistoricalWarmupRecord | null
  runtimeActivation: StrategyActivationRecord | null
  runtimeModel: ModelWeightSnapshot | null
  runtimeSelection: OpportunitySelectionRecord | null
  onRunPaperLoop: () => void
  onStartBot: () => void
  onStopBot: () => void
  onRecover: () => void
  onSessionPreopen: () => void
  onSessionHeartbeat: () => void
  onSessionClose: () => void
}) {
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNowMs(Date.now())
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  const readinessItems = [
    { label: 'Bot status', value: props.runtimeHeartbeat.heartbeat_state },
    { label: 'Market posture', value: prettyLabel(props.commandCenter.session_mode) },
    {
      label: 'Approved strategy',
      value: props.runtimeActivation?.strategy_id || 'No activation artifact',
    },
    {
      label: 'Warmup coverage',
      value: props.runtimeWarmup
        ? `${props.runtimeWarmup.symbols_ready.length}/${props.runtimeWarmup.symbols.length} ready`
        : 'No warmup artifact yet',
    },
  ]

  const runtimeFacts = [
    { label: 'Current state', value: props.runtimeHeartbeat.heartbeat_state },
    { label: 'Last decision', value: props.runtimeHeartbeat.last_decision },
    { label: 'Current exposure', value: props.runtimeHeartbeat.current_exposure },
    { label: 'Cadence', value: props.runtimeHeartbeat.cadence_label },
  ]

  const decisionFacts = [
    { label: 'Why', value: props.runtimeHeartbeat.score_explanation || props.runtimeHeartbeat.decision_reason },
    { label: 'Next evaluation', value: formatTimestamp(props.runtimeHeartbeat.next_evaluation_at_utc) },
    {
      label: 'Clock',
      value: formatTimeUntil(props.runtimeHeartbeat.next_evaluation_at_utc, nowMs),
    },
    {
      label: 'Last evaluation',
      value: formatTimestamp(props.runtimeHeartbeat.last_evaluation_at_utc),
    },
  ]

  const runtimeTruth = props.runtimeHeartbeat.runtime_truth ?? []
  const symbolRows = props.runtimeHeartbeat.symbol_rows ?? []
  const decisionLadder = props.runtimeHeartbeat.decision_ladder ?? []
  const operatorGuidance = props.runtimeHeartbeat.operator_guidance

  return (
    <div className="workspace-grid">
      <Panel
        title="Mission Control"
        eyebrow="Default operator workspace"
        className="workspace-hero-panel"
        actions={
          <div className="badge-row">
            <StatusBadge
              label={prettyLabel(props.runtimeState.status)}
              tone={props.runtimeState.status === 'halted' ? 'watch' : 'good'}
            />
            <StatusBadge
              label={props.configSummary.live_disable_report.paper_only_mode ? 'Paper only' : 'Check mode'}
              tone="info"
            />
          </div>
        }
      >
        <div className="hero-summary-grid">
          <article className="hero-summary-card">
            <span>Mission state</span>
            <strong>{props.commandCenter.market_session_label}</strong>
            <p>Keep supervision tight, intervention bounded, and runtime reasons visible.</p>
          </article>
          <article className="hero-summary-card">
            <span>Active symbols</span>
            <strong>
              {props.commandCenter.watchlist.map((item) => item.symbol).join(', ') || 'None'}
            </strong>
            <p>These are the symbols currently under local monitoring.</p>
          </article>
          <article className="hero-summary-card">
            <span>Bot heartbeat</span>
            <strong>{props.runtimeHeartbeat.heartbeat_state}</strong>
            <p>
              {props.runtimeHeartbeat.heartbeat_summary}
            </p>
          </article>
        </div>
      </Panel>

      <Panel title="Live Operator Readiness" eyebrow="Desk health">
        <KeyValueList items={readinessItems} />
        <EquityChart
          points={props.commandCenter.equity_curve.map((point) => ({
            label: point.label,
            equity: point.value,
          }))}
          emptyTitle="No live equity path yet"
          emptyDetail="Mission Control will draw the real curve after TradingX records timestamped service cycles."
        />
      </Panel>

      <Panel
        title="Runtime Intelligence"
        eyebrow="Balanced runtime supervision"
        className="runtime-intelligence-panel"
        actions={
          <div className="badge-row wrap">
            <StatusBadge
              label={props.runtimeHeartbeat.heartbeat_state}
              tone={badgeTone(props.runtimeHeartbeat.heartbeat_tone)}
            />
            <StatusBadge
              label={formatTimeUntil(props.runtimeHeartbeat.next_evaluation_at_utc, nowMs)}
              tone="info"
            />
          </div>
        }
      >
        <div className="runtime-intelligence-grid">
          <article className="runtime-intelligence-card">
            <div className="runtime-card-header">
              <div>
                <p className="panel-eyebrow">Overall runtime</p>
                <h3>Bot Heartbeat</h3>
              </div>
              <StatusBadge
                label={props.runtimeHeartbeat.heartbeat_state}
                tone={badgeTone(props.runtimeHeartbeat.heartbeat_tone)}
              />
            </div>
            <KeyValueList items={runtimeFacts} />
            <p className="panel-supporting-text">{props.runtimeHeartbeat.heartbeat_summary}</p>
            <KeyValueList items={decisionFacts} />
            <p className="panel-supporting-text">
              <strong>Exposure detail</strong> {props.runtimeHeartbeat.current_exposure_detail}
            </p>
            <div className="badge-row wrap">
              {props.runtimeWarmup?.symbols_blocked && Object.keys(props.runtimeWarmup.symbols_blocked).length > 0
                ? Object.entries(props.runtimeWarmup.symbols_blocked).map(([symbol, reason]) => (
                    <StatusBadge key={symbol} label={`${symbol}: ${reason}`} tone="watch" />
                  ))
                : <StatusBadge label="Warmup clear" tone="good" />}
              <StatusBadge label={props.runtimeModel?.snapshot_id || 'Fallback only'} tone="info" />
            </div>
          </article>

          <article className="runtime-intelligence-card">
            <div className="runtime-card-header">
              <div>
                <p className="panel-eyebrow">Operational facts</p>
                <h3>Runtime Truth</h3>
              </div>
            </div>
            <div className="runtime-truth-grid">
              {runtimeTruth.map((item) => (
                <article key={item.label} className="runtime-truth-item">
                  <div className="badge-row wrap">
                    <span>{item.label}</span>
                    <StatusBadge label={item.value} tone={badgeTone(item.tone)} />
                  </div>
                  <p>{item.detail}</p>
                </article>
              ))}
            </div>
          </article>

          <article className="runtime-intelligence-card runtime-intelligence-span-2">
            <div className="runtime-card-header">
              <div>
                <p className="panel-eyebrow">Per symbol</p>
                <h3>Symbol Heartbeat</h3>
              </div>
            </div>
            <div className="table-shell runtime-symbol-table">
              <div className="table-header">
                <span>Symbol</span>
                <span>Status</span>
                <span>Score</span>
                <span>Gap</span>
                <span>Reason</span>
                <span>Warmup</span>
                <span>Exposure</span>
              </div>
              {symbolRows.map((row) => (
                <div key={row.symbol} className="table-row">
                  <strong>{row.symbol}</strong>
                  <div className="badge-row wrap">
                    <StatusBadge label={row.status} tone={badgeTone(row.tone)} />
                  </div>
                  <span>{row.score}</span>
                  <span>{row.threshold_gap}</span>
                  <span>{row.reason}</span>
                  <span>{row.warmup_state}</span>
                  <span>{row.exposure_state}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="runtime-intelligence-card">
            <div className="runtime-card-header">
              <div>
                <p className="panel-eyebrow">Ranked evaluation</p>
                <h3>Decision Ladder</h3>
              </div>
            </div>
            <div className="table-shell runtime-decision-table">
              <div className="table-header">
                <span>Rank</span>
                <span>Symbol</span>
                <span>Score</span>
                <span>Threshold</span>
                <span>Gap</span>
                <span>Primary driver</span>
                <span>Disposition</span>
              </div>
              {decisionLadder.map((row) => (
                <div key={`${row.rank}-${row.symbol}`} className="table-row">
                  <strong>{row.rank}</strong>
                  <span>{row.symbol}</span>
                  <span>{row.final_score}</span>
                  <span>{row.threshold}</span>
                  <span>{row.threshold_gap}</span>
                  <span>{row.primary_driver}</span>
                  <span>{row.disposition}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="runtime-intelligence-card">
            <div className="runtime-card-header">
              <div>
                <p className="panel-eyebrow">Recommended next move</p>
                <h3>Operator Guidance</h3>
              </div>
              {operatorGuidance ? (
                <StatusBadge label={operatorGuidance.recommendation} tone={badgeTone(operatorGuidance.tone)} />
              ) : null}
            </div>
            <p className="panel-supporting-text">
              <strong>{operatorGuidance?.recommendation || 'No guidance yet'}</strong>
            </p>
            <p className="panel-supporting-text">
              {operatorGuidance?.detail || 'TradingX has not emitted an operator recommendation yet.'}
            </p>
          </article>
        </div>
      </Panel>

      <Panel title="Operator Actions" eyebrow="Safe controls">
        <div className="action-row">
          <ActionButton label="Start Bot" variant="primary" onClick={props.onStartBot} />
          <ActionButton label="Pause Bot" variant="secondary" onClick={props.onStopBot} />
          <ActionButton label="Run One Cycle" variant="secondary" onClick={props.onRunPaperLoop} />
          <ActionButton label="Recover" variant="ghost" onClick={props.onRecover} />
        </div>
        <p className="panel-supporting-text">
          <strong>Start Bot</strong> keeps the runtime host running until you pause it. <strong>Run One Cycle</strong>{' '}
          submits one bounded paper cycle for quick verification.
        </p>
        <div className="action-row">
          <ActionButton label="Session Pre-Open" variant="secondary" onClick={props.onSessionPreopen} />
          <ActionButton label="Session Heartbeat" variant="secondary" onClick={props.onSessionHeartbeat} />
          <ActionButton label="Session Close" variant="ghost" onClick={props.onSessionClose} />
        </div>
      </Panel>

      <Panel title="Watchlist & Exposure" eyebrow="Market footprint">
        <div className="dual-column">
          <ExposureChart items={props.commandCenter.exposure_breakdown} />
          <div className="watchlist-panel">
            {props.commandCenter.watchlist.length ? (
              props.commandCenter.watchlist.map((item) => (
                <article key={item.symbol} className="list-card">
                  <strong>{item.symbol}</strong>
                  <span>{prettyLabel(item.status)}</span>
                </article>
              ))
            ) : (
              <div className="empty-state">
                <strong>No watchlist activity</strong>
                <p>TradingX is monitoring symbols but has not opened exposure yet.</p>
              </div>
            )}
          </div>
        </div>
      </Panel>

      <Panel title="Incident Board" eyebrow="What needs attention">
        <div className="stack-list">
          {props.incidents.length ? (
            props.incidents.slice(0, 4).map((incident) => (
              <article key={incident.incident_id} className="list-card">
                <div className="list-card-header">
                  <strong>{incident.title}</strong>
                  <StatusBadge label={prettyLabel(incident.severity)} tone="watch" />
                </div>
                <p>{incident.summary}</p>
                <span>{incident.suggested_action}</span>
              </article>
            ))
          ) : (
            <div className="empty-state">
              <strong>Incident board is clear</strong>
              <p>No operator-visible incidents are open right now.</p>
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Context & Docs" eyebrow="Pinned reference">
        <div className="stack-list">
          {props.documents.length ? (
            props.documents.slice(0, 8).map((document) => (
              <article key={document.doc_id} className="list-card">
                <div className="list-card-header">
                  <strong>{document.title}</strong>
                  <span>{prettyLabel(document.kind)}</span>
                </div>
                <p>{document.preview}</p>
              </article>
            ))
          ) : (
            <div className="empty-state">
              <strong>No pinned docs</strong>
              <p>Project reference documents will appear here as they are discovered.</p>
            </div>
          )}
        </div>
      </Panel>
    </div>
  )
}
