import { startTransition, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import './App.css'
import {
  getConfigProposals,
  getConfigSummary,
  getDocuments,
  getEvidence,
  getOverview,
  postDecisionReport,
  postGateReport,
  postPaperLoop,
  postPrepareBenchmark,
  postProposal,
  postRecover,
  postServiceStart,
  postServiceStop,
} from './api'
import type {
  ActionResult,
  ConfigProposal,
  ConfigSummary,
  DashboardSnapshot,
  DocumentRecord,
  EvidenceCategory,
  EvidenceItem,
} from './types'

const evidenceCategories: Array<{ key: EvidenceCategory; label: string }> = [
  { key: 'operator_alerts', label: 'Operator Alerts' },
  { key: 'service_cycles', label: 'Service Cycles' },
  { key: 'validation_reports', label: 'Validation Reports' },
]

const defaultOverview: DashboardSnapshot = {
  generated_at_utc: '',
  service_status: {
    status: 'idle',
    active_symbols: [],
    interval_seconds: 300,
    cycles_completed: 0,
    started_at_utc: null,
    last_completed_at_utc: null,
    last_error: '',
  },
  account_summary: {
    cash: '',
    equity: '',
    buying_power: '',
    daily_pnl: '',
  },
  positions: [],
  alerts: [],
  gate_statuses: {},
  recommendations: {},
  document_summary: {},
}

const defaultConfigSummary: ConfigSummary = {
  config: {
    web_write_mode_enabled: false,
    symbol_universe: [],
    service_interval_seconds: 300,
  },
  live_disable_report: {
    paper_only_mode: true,
    live_trading_enabled: false,
    manual_kill_switch_active: false,
  },
}

function App() {
  const [overview, setOverview] = useState<DashboardSnapshot>(defaultOverview)
  const [configSummary, setConfigSummary] =
    useState<ConfigSummary>(defaultConfigSummary)
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [proposals, setProposals] = useState<ConfigProposal[]>([])
  const [evidenceCategory, setEvidenceCategory] =
    useState<EvidenceCategory>('operator_alerts')
  const [evidenceItems, setEvidenceItems] = useState<EvidenceItem[]>([])
  const [actionFeed, setActionFeed] = useState<ActionResult[]>([])
  const [isBooting, setIsBooting] = useState(true)
  const [pageError, setPageError] = useState('')

  const [serviceSymbols, setServiceSymbols] = useState('SPY,QQQ')
  const [serviceQuantity, setServiceQuantity] = useState('1')
  const [serviceIntervalSeconds, setServiceIntervalSeconds] = useState('300')
  const [loopSymbol, setLoopSymbol] = useState('SPY')
  const [loopQuantity, setLoopQuantity] = useState('1')
  const [recoverSymbol, setRecoverSymbol] = useState('SPY')
  const [benchmarkSymbol, setBenchmarkSymbol] = useState('SPY')
  const [benchmarkWindowStart, setBenchmarkWindowStart] = useState('2023-01-01')
  const [benchmarkWindowEnd, setBenchmarkWindowEnd] = useState('2026-04-17')
  const [gateBenchmarkPath, setGateBenchmarkPath] = useState(
    'artifacts/validation/benchmarks/spy.json',
  )
  const [gateWindowStart, setGateWindowStart] = useState('2023-01-01')
  const [gateWindowEnd, setGateWindowEnd] = useState('2026-04-17')
  const [gateUniverse, setGateUniverse] = useState('SPY,QQQ')
  const [proposalTargetArea, setProposalTargetArea] = useState('')
  const [proposalRationale, setProposalRationale] = useState('')
  const [proposalValues, setProposalValues] = useState('')

  useEffect(() => {
    void loadDashboard()
  }, [])

  useEffect(() => {
    void loadEvidence(evidenceCategory)
  }, [evidenceCategory])

  const writeModeEnabled = configSummary.config.web_write_mode_enabled

  const latestPositions = useMemo(
    () => overview.positions.filter((position) => position.symbol),
    [overview.positions],
  )

  async function loadDashboard() {
    setIsBooting(true)
    setPageError('')
    try {
      const [nextOverview, nextConfigSummary, nextDocuments, nextProposals] =
        await Promise.all([
          getOverview(),
          getConfigSummary(),
          getDocuments(),
          getConfigProposals(),
        ])
      startTransition(() => {
        setOverview(nextOverview)
        setConfigSummary(nextConfigSummary)
        setDocuments(nextDocuments)
        setProposals(nextProposals)
      })
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : 'Unable to load the local control center.'
      setPageError(message)
    } finally {
      setIsBooting(false)
    }
  }

  async function loadEvidence(category: EvidenceCategory) {
    try {
      const payload = await getEvidence(category)
      startTransition(() => {
        setEvidenceItems(payload)
      })
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : `Unable to load ${category} evidence.`
      pushAction({
        action_type: 'evidence_refresh',
        status: 'failed',
        message,
      })
    }
  }

  function pushAction(action: Partial<ActionResult> & { message: string }) {
    startTransition(() => {
      setActionFeed((current) => [
        {
          action_type: action.action_type ?? 'ui_feedback',
          status: action.status ?? 'completed',
          message: action.message,
          action_id: action.action_id ?? `ui-${Date.now()}`,
          evidence_refs: action.evidence_refs ?? [],
        },
        ...current,
      ].slice(0, 6))
    })
  }

  async function runAction(request: () => Promise<ActionResult>) {
    try {
      const result = await request()
      pushAction(result)
      await Promise.all([loadDashboard(), loadEvidence(evidenceCategory)])
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Action failed unexpectedly.'
      pushAction({
        action_type: 'ui_feedback',
        status: 'failed',
        message,
      })
    }
  }

  async function handleProposalSubmit() {
    let parsedValues: Record<string, unknown>
    try {
      parsedValues = JSON.parse(proposalValues) as Record<string, unknown>
    } catch {
      pushAction({
        action_type: 'config_proposal',
        status: 'failed',
        message: 'Proposed Values (JSON) must be valid JSON before saving.',
      })
      return
    }

    try {
      const proposal = await postProposal({
        target_area: proposalTargetArea,
        rationale: proposalRationale,
        proposed_values: parsedValues,
      })
      startTransition(() => {
        setProposals((current) => [proposal, ...current])
        setProposalTargetArea('')
        setProposalRationale('')
        setProposalValues('')
      })
      pushAction({
        action_type: 'config_proposal',
        status: 'completed',
        message: proposal.proposal_id,
      })
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Unable to save the proposal.'
      pushAction({
        action_type: 'config_proposal',
        status: 'failed',
        message,
      })
    }
  }

  return (
    <main className="shell">
      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">Local-only operator cockpit</p>
          <h1>TradingX Control Center</h1>
          <p className="hero-summary">
            Local supervision for paper trading, evidence review, validation
            gates, and safe config proposals. Live trading stays disabled at
            every layer.
          </p>
        </div>
        <div className="hero-status">
          <StatusChip label={overview.service_status.status} tone="teal" />
          <StatusChip
            label={
              configSummary.live_disable_report.paper_only_mode
                ? 'paper-only'
                : 'check mode'
            }
            tone="gold"
          />
          <StatusChip
            label={writeModeEnabled ? 'write mode on' : 'read-only'}
            tone={writeModeEnabled ? 'ink' : 'soft'}
          />
        </div>
        <div className="hero-grid">
          <KpiCard label="Equity" value={overview.account_summary.equity || '0.00'} />
          <KpiCard label="Cash" value={overview.account_summary.cash || '0.00'} />
          <KpiCard
            label="Buying Power"
            value={overview.account_summary.buying_power || '0.00'}
          />
          <KpiCard label="Daily P&L" value={overview.account_summary.daily_pnl || '0.00'} />
        </div>
      </section>

      {pageError ? <Banner tone="error">{pageError}</Banner> : null}
      {isBooting ? <Banner tone="info">Loading the latest local operator data…</Banner> : null}

      <div className="content-grid">
        <section className="panel panel-wide">
          <PanelHeader
            title="Operations Deck"
            subtitle="Run bounded local actions, supervise the paper service, and keep the bot on a short operational leash."
          />
          <div className="control-grid">
            <div className="subpanel">
              <h3>Quick controls</h3>
              <p className="muted">
                These buttons respect the repo’s write-mode switch and never touch live trading.
              </p>
              <div className="button-row">
                <ActionButton
                  disabled={!writeModeEnabled}
                  onClick={() =>
                    runAction(() =>
                      postPaperLoop({ symbol: loopSymbol, quantity: loopQuantity }),
                    )
                  }
                >
                  Run One Cycle
                </ActionButton>
                <ActionButton
                  disabled={!writeModeEnabled}
                  variant="secondary"
                  onClick={() =>
                    runAction(() =>
                      postServiceStart({
                        symbols: serviceSymbols
                          .split(',')
                          .map((symbol) => symbol.trim())
                          .filter(Boolean),
                        quantity: serviceQuantity,
                        interval_seconds: Number(serviceIntervalSeconds),
                        max_cycles: 1,
                      }),
                    )
                  }
                >
                  Start Service
                </ActionButton>
                <ActionButton
                  disabled={!writeModeEnabled}
                  variant="secondary"
                  onClick={() => runAction(() => postServiceStop())}
                >
                  Stop Service
                </ActionButton>
                <ActionButton
                  disabled={!writeModeEnabled}
                  variant="ghost"
                  onClick={() =>
                    runAction(() => postRecover({ symbol: recoverSymbol }))
                  }
                >
                  Recover
                </ActionButton>
              </div>
              <div className="field-grid compact">
                <Field label="Loop Symbol">
                  <input
                    value={loopSymbol}
                    onChange={(event) => setLoopSymbol(event.target.value)}
                  />
                </Field>
                <Field label="Loop Quantity">
                  <input
                    value={loopQuantity}
                    onChange={(event) => setLoopQuantity(event.target.value)}
                  />
                </Field>
                <Field label="Recover Symbol">
                  <input
                    value={recoverSymbol}
                    onChange={(event) => setRecoverSymbol(event.target.value)}
                  />
                </Field>
                <Field label="Service Symbols">
                  <input
                    value={serviceSymbols}
                    onChange={(event) => setServiceSymbols(event.target.value)}
                  />
                </Field>
                <Field label="Service Quantity">
                  <input
                    value={serviceQuantity}
                    onChange={(event) => setServiceQuantity(event.target.value)}
                  />
                </Field>
                <Field label="Interval (seconds)">
                  <input
                    value={serviceIntervalSeconds}
                    onChange={(event) =>
                      setServiceIntervalSeconds(event.target.value)
                    }
                  />
                </Field>
              </div>
            </div>

            <div className="subpanel">
              <h3>Validation launchpad</h3>
              <p className="muted">
                Generate benchmark data and refresh the gate evidence pipeline without leaving the browser.
              </p>
              <div className="button-row">
                <ActionButton
                  disabled={!writeModeEnabled}
                  onClick={() =>
                    runAction(() =>
                      postPrepareBenchmark({
                        symbol: benchmarkSymbol,
                        window_start: benchmarkWindowStart,
                        window_end: benchmarkWindowEnd,
                      }),
                    )
                  }
                >
                  Prepare Benchmark
                </ActionButton>
                <ActionButton
                  disabled={!writeModeEnabled}
                  variant="secondary"
                  onClick={() =>
                    runAction(() =>
                      postGateReport({
                        gate: '1',
                        benchmark_closes_file: gateBenchmarkPath,
                        window_start: gateWindowStart,
                        window_end: gateWindowEnd,
                        universe: gateUniverse
                          .split(',')
                          .map((symbol) => symbol.trim())
                          .filter(Boolean),
                      }),
                    )
                  }
                >
                  Generate Gate Report
                </ActionButton>
                <ActionButton
                  disabled={!writeModeEnabled}
                  variant="ghost"
                  onClick={() => runAction(() => postDecisionReport({ gate: '1' }))}
                >
                  Generate Decision Brief
                </ActionButton>
              </div>
              <div className="field-grid compact">
                <Field label="Benchmark Symbol">
                  <input
                    value={benchmarkSymbol}
                    onChange={(event) => setBenchmarkSymbol(event.target.value)}
                  />
                </Field>
                <Field label="Benchmark Start">
                  <input
                    value={benchmarkWindowStart}
                    onChange={(event) => setBenchmarkWindowStart(event.target.value)}
                  />
                </Field>
                <Field label="Benchmark End">
                  <input
                    value={benchmarkWindowEnd}
                    onChange={(event) => setBenchmarkWindowEnd(event.target.value)}
                  />
                </Field>
                <Field label="Benchmark Artifact">
                  <input
                    value={gateBenchmarkPath}
                    onChange={(event) => setGateBenchmarkPath(event.target.value)}
                  />
                </Field>
                <Field label="Gate Start">
                  <input
                    value={gateWindowStart}
                    onChange={(event) => setGateWindowStart(event.target.value)}
                  />
                </Field>
                <Field label="Gate End">
                  <input
                    value={gateWindowEnd}
                    onChange={(event) => setGateWindowEnd(event.target.value)}
                  />
                </Field>
                <Field label="Universe">
                  <input
                    value={gateUniverse}
                    onChange={(event) => setGateUniverse(event.target.value)}
                  />
                </Field>
              </div>
            </div>
          </div>
        </section>

        <section className="panel">
          <PanelHeader
            title="Gate Cockpit"
            subtitle="Track gate outcomes and recommendation counts side by side."
          />
          <div className="chip-row">
            {Object.entries(overview.gate_statuses).map(([gate, status]) => (
              <div className="metric-pill" key={gate}>
                <span>Gate {gate}</span>
                <strong>{status}</strong>
              </div>
            ))}
          </div>
          <div className="recommendation-list">
            {Object.entries(overview.recommendations).map(([label, count]) => (
              <div className="recommendation-item" key={label}>
                <span>{label.replaceAll('_', ' ')}</span>
                <strong>{count}</strong>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <PanelHeader
            title="Evidence Radar"
            subtitle="Switch between evidence streams and inspect the freshest artifacts."
          />
          <div className="tab-row">
            {evidenceCategories.map((category) => (
              <button
                className={category.key === evidenceCategory ? 'tab active' : 'tab'}
                key={category.key}
                onClick={() => setEvidenceCategory(category.key)}
                type="button"
              >
                {category.label}
              </button>
            ))}
          </div>
          <div className="evidence-list">
            {evidenceItems.length === 0 ? (
              <p className="muted">No evidence artifacts are present in this category yet.</p>
            ) : (
              evidenceItems.map((item, index) => (
                <article className="evidence-card" key={`${evidenceCategory}-${index}`}>
                  <strong>{extractHeadline(item)}</strong>
                  <p>{extractBody(item)}</p>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="panel">
          <PanelHeader
            title="Project Intelligence"
            subtitle="Keep handovers, state, and local context close to the operator surface."
          />
          <p className="muted">{String(overview.document_summary.latest_state ?? '')}</p>
          <div className="document-list">
            {documents.map((document) => (
              <article className="document-card" key={document.doc_id}>
                <div>
                  <strong>{document.title}</strong>
                  <span>{document.kind}</span>
                </div>
                <p>{document.preview}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <PanelHeader
            title="Proposal Studio"
            subtitle="Create safe config proposals on disk instead of mutating runtime state directly."
          />
          <div className="field-grid">
            <Field label="Target Area">
              <input
                aria-label="Target Area"
                value={proposalTargetArea}
                onChange={(event) => setProposalTargetArea(event.target.value)}
              />
            </Field>
            <Field label="Rationale">
              <textarea
                aria-label="Rationale"
                rows={4}
                value={proposalRationale}
                onChange={(event) => setProposalRationale(event.target.value)}
              />
            </Field>
            <Field label="Proposed Values (JSON)">
              <textarea
                aria-label="Proposed Values (JSON)"
                rows={6}
                value={proposalValues}
                onChange={(event) => setProposalValues(event.target.value)}
              />
            </Field>
          </div>
          <div className="button-row">
            <ActionButton disabled={!writeModeEnabled} onClick={handleProposalSubmit}>
              Save Proposal
            </ActionButton>
          </div>
          <div className="proposal-list">
            {proposals.map((proposal) => (
              <article className="proposal-card" key={proposal.proposal_id}>
                <strong>{proposal.proposal_id}</strong>
                <p>{proposal.diff_preview}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="panel panel-wide">
          <PanelHeader
            title="Action Chronicle"
            subtitle="Recent operator actions, feedback, and local status changes."
          />
          <div className="timeline">
            {actionFeed.length === 0 ? (
              <p className="muted">No actions have been triggered in this session yet.</p>
            ) : (
              actionFeed.map((action) => (
                <article className="timeline-item" key={action.action_id}>
                  <StatusChip label={action.status} tone={action.status === 'failed' ? 'rose' : 'teal'} />
                  <div>
                    <strong>{action.action_type.replaceAll('_', ' ')}</strong>
                    <p>{action.message}</p>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="panel">
          <PanelHeader
            title="Position Lens"
            subtitle="Open positions from the latest local evidence snapshot."
          />
          <div className="position-list">
            {latestPositions.length === 0 ? (
              <p className="muted">No open positions are visible in the latest local evidence.</p>
            ) : (
              latestPositions.map((position) => (
                <div className="position-row" key={position.symbol}>
                  <strong>{position.symbol}</strong>
                  <span>{position.quantity || 'open'}</span>
                  <span>{position.market_value || 'n/a'}</span>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="panel">
          <PanelHeader
            title="Safety Frame"
            subtitle="The local app reflects the constitution’s boundaries at a glance."
          />
          <div className="safety-grid">
            <SafetyRow
              label="Paper-only mode"
              value={configSummary.live_disable_report.paper_only_mode ? 'enabled' : 'check'}
            />
            <SafetyRow
              label="Live trading"
              value={
                configSummary.live_disable_report.live_trading_enabled
                  ? 'enabled'
                  : 'disabled'
              }
            />
            <SafetyRow
              label="Kill switch"
              value={
                configSummary.live_disable_report.manual_kill_switch_active
                  ? 'active'
                  : 'inactive'
              }
            />
            <SafetyRow
              label="Write mode"
              value={writeModeEnabled ? 'enabled' : 'disabled'}
            />
          </div>
        </section>
      </div>
    </main>
  )
}

function PanelHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="panel-header">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </header>
  )
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="kpi-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  )
}

function StatusChip({
  label,
  tone,
}: {
  label: string
  tone: 'teal' | 'gold' | 'ink' | 'soft' | 'rose'
}) {
  return <span className={`status-chip ${tone}`}>{label}</span>
}

function ActionButton({
  children,
  disabled = false,
  onClick,
  variant = 'primary',
}: {
  children: string
  disabled?: boolean
  onClick: () => void | Promise<void>
  variant?: 'primary' | 'secondary' | 'ghost'
}) {
  return (
    <button
      className={`action-button ${variant}`}
      disabled={disabled}
      onClick={() => {
        void onClick()
      }}
      type="button"
    >
      {children}
    </button>
  )
}

function Field({
  children,
  label,
}: {
  children: ReactNode
  label: string
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  )
}

function Banner({
  children,
  tone,
}: {
  children: ReactNode
  tone: 'error' | 'info'
}) {
  return <div className={`banner ${tone}`}>{children}</div>
}

function SafetyRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="safety-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function extractHeadline(item: EvidenceItem) {
  const headline =
    item.summary ??
    item.report_id ??
    item.cycle_id ??
    item.alert_id ??
    item.gate_id ??
    'Evidence item'
  return String(headline)
}

function extractBody(item: EvidenceItem) {
  if (item.gate_id && item.status) {
    return `Gate ${String(item.gate_id)} is ${String(item.status)}.`
  }
  if (item.cycle_status && item.symbols) {
    return `Cycle status ${String(item.cycle_status)} across ${String(item.symbols)}.`
  }
  if (item.message) {
    return String(item.message)
  }
  return JSON.stringify(item)
}

export default App
