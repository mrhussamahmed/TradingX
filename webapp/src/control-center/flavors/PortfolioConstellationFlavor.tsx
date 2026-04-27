import { useMemo, useState } from 'react'
import { Layers, ListFilter, RefreshCcw } from 'lucide-react'

import { parseNumericValue, prettyLabel, toCurrency } from '../../platform/format'
import type {
  PortfolioBenchmarkRow,
  PortfolioPositionRow,
  PortfolioStrategyRow,
} from '../../types'
import { useData } from '../state/DataContext'

import styles from './Flavor.module.css'

type Filter = 'all' | 'long' | 'short' | 'flat'

const CENTER_X = 50
const CENTER_Y = 50
const SLEEVE_RADIUS = 22
const SYMBOL_RADIUS = 38

function classifyPosition(position: PortfolioPositionRow): Filter {
  const value = parseNumericValue(position.market_value)
  const status = position.status?.toLowerCase() ?? ''
  if (status.includes('flat') || value === 0) return 'flat'
  if (value < 0) return 'short'
  return 'long'
}

function classifyStrategy(strategy: PortfolioStrategyRow): 'good' | 'watch' | 'risk' | 'info' {
  const status = strategy.status?.toLowerCase() ?? ''
  if (/risk|fail|halt|block/.test(status)) return 'risk'
  if (/watch|warn|degrad/.test(status)) return 'watch'
  if (/healthy|active|good|ok/.test(status)) return 'good'
  return 'info'
}

export function PortfolioConstellationFlavor() {
  const { portfolio, refresh } = useData()
  const [filter, setFilter] = useState<Filter>('all')
  const [showBudget, setShowBudget] = useState(true)

  const positions = portfolio.positions_panel.positions
  const strategies = portfolio.strategy_panel.strategies
  const benchmarks = portfolio.benchmark_panel.benchmark_rows
  const diagnostics = portfolio.diagnostics

  const filteredPositions = useMemo(() => {
    if (filter === 'all') return positions
    return positions.filter((position) => classifyPosition(position) === filter)
  }, [positions, filter])

  const positionsTotal =
    positions.reduce((sum, position) => sum + Math.abs(parseNumericValue(position.market_value)), 0) ||
    1

  const hasGraphData = positions.length > 0 || strategies.length > 0
  const sparseMode = positions.length <= 1 && strategies.length === 0

  return (
    <div className={styles.gridShell}>
      <div className={styles.symbolHeader}>
        <div>
          <div className={styles.metricLabel}>Portfolio Mode</div>
          <div className={styles.symbolMain}>{prettyLabel(portfolio.trading_mode)}</div>
          <div className={styles.metricSub}>{portfolio.source_summary}</div>
        </div>
        <dl className={styles.symbolMeta}>
          <dt>Data State</dt>
          <dd>{prettyLabel(portfolio.data_state)}</dd>
          <dt>Positions</dt>
          <dd className="numeric">{positions.length}</dd>
          <dt>Sleeves</dt>
          <dd className="numeric">{strategies.length}</dd>
          <dt>Benchmarks</dt>
          <dd className="numeric">{benchmarks.length}</dd>
        </dl>
      </div>

      {sparseMode ? (
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Sparse Portfolio</span>
            <span className={styles.panelSub}>Graph hidden — table view</span>
          </div>
          <div className={styles.panelBody}>
            <div className={styles.emptyState}>
              <strong>{portfolio.positions_panel.headline}</strong>
              <p>{portfolio.positions_panel.detail}</p>
            </div>
          </div>
        </div>
      ) : hasGraphData ? (
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Allocation Constellation</span>
            <span className={styles.panelSub}>
              account → {strategies.length ? 'sleeves → ' : ''}symbols
            </span>
            <div className={styles.panelHeaderActions}>
              <select
                aria-label="Filter exposure"
                value={filter}
                onChange={(event) => setFilter(event.target.value as Filter)}
              >
                <option value="all">All</option>
                <option value="long">Long</option>
                <option value="short">Short</option>
                <option value="flat">Flat</option>
              </select>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => setShowBudget((value) => !value)}
                aria-pressed={showBudget}
              >
                <Layers size={12} /> Risk Budget: {showBudget ? 'On' : 'Off'}
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void refresh()}
              >
                <RefreshCcw size={12} /> Refresh
              </button>
            </div>
          </div>
          <div className={styles.panelBody}>
            <ConstellationGraph
              positions={filteredPositions}
              strategies={strategies}
              positionsTotal={positionsTotal}
            />
          </div>
        </div>
      ) : null}

      <div className={styles.forgeRow}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Strategy Attribution</span>
            <span className={styles.panelSub}>{prettyLabel(portfolio.strategy_panel.status)}</span>
          </div>
          {strategies.length === 0 ? (
            <div className={styles.panelBody}>
              <div className={styles.emptyState}>
                <strong>{portfolio.strategy_panel.headline}</strong>
                <p>{portfolio.strategy_panel.detail}</p>
              </div>
            </div>
          ) : (
            <table className={styles.simpleTable}>
              <thead>
                <tr>
                  <th>Sleeve</th>
                  <th>P&L</th>
                  <th>Trades</th>
                  <th>Win Rate</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {strategies.map((strategy) => {
                  const tone = classifyStrategy(strategy)
                  return (
                    <tr key={strategy.strategy_id}>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column' }}>
                          <span style={{ fontWeight: 600 }}>{strategy.label}</span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{strategy.detail}</span>
                        </div>
                      </td>
                      <td className="numeric">{strategy.pnl}</td>
                      <td className="numeric">{strategy.trade_count}</td>
                      <td className="numeric">{strategy.win_rate}</td>
                      <td>
                        <span className={`badge badge-${tone}`}>{prettyLabel(strategy.status)}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Benchmark Comparison</span>
            <span className={styles.panelSub}>{prettyLabel(portfolio.benchmark_panel.status)}</span>
          </div>
          {benchmarks.length === 0 ? (
            <div className={styles.panelBody}>
              <div className={styles.emptyState}>
                <strong>{portfolio.benchmark_panel.headline}</strong>
                <p>{portfolio.benchmark_panel.detail}</p>
              </div>
            </div>
          ) : (
            <table className={styles.simpleTable}>
              <thead>
                <tr>
                  <th>Benchmark</th>
                  <th>Portfolio</th>
                  <th>Benchmark</th>
                  <th>Excess</th>
                </tr>
              </thead>
              <tbody>
                {benchmarks.map((row) => (
                  <BenchmarkRowView key={row.benchmark_id} row={row} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <span>Positions</span>
          <span className={styles.panelSub}>{filteredPositions.length} shown</span>
          <div className={styles.panelHeaderActions}>
            <button type="button" className="btn btn-sm" disabled>
              <ListFilter size={12} /> Rebalance Proposal
              <span className={styles.disabledNote} style={{ marginLeft: 4 }}>
                (no proposal endpoint)
              </span>
            </button>
            <button type="button" className="btn btn-sm" disabled>
              Run Impact Simulation
            </button>
          </div>
        </div>
        {filteredPositions.length === 0 ? (
          <div className={styles.panelBody}>
            <div className={styles.emptyState}>
              <strong>No positions match this filter</strong>
              <p>Select a different filter or refresh.</p>
            </div>
          </div>
        ) : (
          <table className={styles.simpleTable}>
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>Quantity</th>
                <th>Market Value</th>
                <th>Exposure %</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredPositions.map((position) => {
                const side = classifyPosition(position)
                return (
                  <tr key={position.symbol}>
                    <td className="mono">{position.symbol}</td>
                    <td>
                      <span className={`badge badge-${side === 'long' ? 'good' : side === 'short' ? 'risk' : 'info'}`}>
                        {prettyLabel(side)}
                      </span>
                    </td>
                    <td className="numeric">{position.quantity}</td>
                    <td className="numeric">
                      {position.market_value ? toCurrency(position.market_value) : '—'}
                    </td>
                    <td className="numeric">{position.exposure_pct}</td>
                    <td>{position.status}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {diagnostics.length > 0 ? (
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <span>Diagnostics</span>
            <span className={styles.panelSub}>{diagnostics.length} item{diagnostics.length === 1 ? '' : 's'}</span>
          </div>
          <div className={styles.panelBody}>
            {diagnostics.map((diagnostic) => (
              <div
                key={diagnostic.diagnostic_id}
                style={{
                  padding: 8,
                  border: '1px solid var(--border-muted)',
                  borderRadius: 6,
                  background: 'var(--bg-panel)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
              >
                <div style={{ display: 'flex', gap: 6 }}>
                  <span className={`badge badge-${normalizeSeverity(diagnostic.severity)}`}>
                    {prettyLabel(diagnostic.severity)}
                  </span>
                  <strong>{diagnostic.title}</strong>
                </div>
                <p style={{ margin: 0, color: 'var(--text-secondary)', fontSize: 12 }}>{diagnostic.detail}</p>
                <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 11 }}>
                  Owner: {diagnostic.owner} · Action: {diagnostic.action}
                </p>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function BenchmarkRowView({ row }: { row: PortfolioBenchmarkRow }) {
  const excess = parseNumericValue(row.excess_return)
  const tone = excess > 0 ? 'good' : excess < 0 ? 'risk' : 'info'
  return (
    <tr>
      <td>{row.label}</td>
      <td className="numeric">{row.portfolio_return}</td>
      <td className="numeric">{row.benchmark_return}</td>
      <td>
        <span className={`badge badge-${tone}`}>{row.excess_return}</span>
      </td>
    </tr>
  )
}

function ConstellationGraph({
  positions,
  strategies,
  positionsTotal,
}: {
  positions: PortfolioPositionRow[]
  strategies: PortfolioStrategyRow[]
  positionsTotal: number
}) {
  const placedSleeves = useMemo(
    () =>
      strategies.map((strategy, index) => {
        const angle = (index / Math.max(strategies.length, 1)) * Math.PI * 2 - Math.PI / 2
        return {
          strategy,
          x: CENTER_X + SLEEVE_RADIUS * Math.cos(angle),
          y: CENTER_Y + SLEEVE_RADIUS * Math.sin(angle),
        }
      }),
    [strategies],
  )

  const placedSymbols = useMemo(
    () =>
      positions.map((position, index) => {
        const angle = (index / Math.max(positions.length, 1)) * Math.PI * 2 + Math.PI / 6
        return {
          position,
          x: CENTER_X + SYMBOL_RADIUS * Math.cos(angle),
          y: CENTER_Y + SYMBOL_RADIUS * Math.sin(angle),
        }
      }),
    [positions],
  )

  return (
    <div className={styles.constellationWrap}>
      <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" width="100%" height={420}>
        {placedSleeves.map(({ strategy, x, y }) => {
          const tone = classifyStrategy(strategy)
          const stroke =
            tone === 'risk'
              ? 'rgba(255, 51, 71, 0.7)'
              : tone === 'watch'
                ? 'rgba(255, 174, 47, 0.7)'
                : tone === 'good'
                  ? 'rgba(40, 224, 120, 0.7)'
                  : 'rgba(46, 161, 255, 0.55)'
          return (
            <line
              key={`l-${strategy.strategy_id}`}
              x1={CENTER_X}
              y1={CENTER_Y}
              x2={x}
              y2={y}
              stroke={stroke}
              strokeWidth={1}
            />
          )
        })}
        {placedSymbols.map(({ position, x, y }) => {
          const ratio = Math.abs(parseNumericValue(position.market_value)) / positionsTotal
          return (
            <line
              key={`s-${position.symbol}`}
              x1={CENTER_X}
              y1={CENTER_Y}
              x2={x}
              y2={y}
              stroke="rgba(46, 161, 255, 0.45)"
              strokeWidth={Math.max(0.4, Math.min(1.6, ratio * 3))}
            />
          )
        })}
        <circle cx={CENTER_X} cy={CENTER_Y} r={6} fill="var(--primary-bright)" opacity={0.85} />
        <text
          x={CENTER_X}
          y={CENTER_Y + 1.5}
          fill="#001225"
          fontSize="3.5"
          textAnchor="middle"
          fontWeight="700"
        >
          ACCT
        </text>
      </svg>
      {placedSleeves.map(({ strategy, x, y }) => {
        const tone = classifyStrategy(strategy)
        const colorClass =
          tone === 'risk'
            ? styles.constNodeRisk
            : tone === 'watch'
              ? styles.constNodeWatch
              : tone === 'good'
                ? styles.constNodeGood
                : styles.constNodeSleeve
        return (
          <div
            key={`sleeve-${strategy.strategy_id}`}
            className={[styles.constellationNode, colorClass].filter(Boolean).join(' ')}
            style={{ left: `${x}%`, top: `${y}%` }}
          >
            <div style={{ fontSize: 11, fontWeight: 600 }}>{strategy.label}</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{strategy.pnl}</div>
          </div>
        )
      })}
      {placedSymbols.map(({ position, x, y }) => {
        const side = classifyPosition(position)
        const colorClass =
          side === 'long'
            ? styles.constNodeGood
            : side === 'short'
              ? styles.constNodeRisk
              : styles.constNodeFlat
        return (
          <div
            key={`sym-${position.symbol}`}
            className={[styles.constellationNode, styles.constNodeSym, colorClass]
              .filter(Boolean)
              .join(' ')}
            style={{ left: `${x}%`, top: `${y}%` }}
          >
            <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}>{position.symbol}</div>
          </div>
        )
      })}
    </div>
  )
}

function normalizeSeverity(severity: string): 'good' | 'watch' | 'risk' | 'info' {
  const lowered = severity?.toLowerCase() ?? ''
  if (/risk|critical|fail/.test(lowered)) return 'risk'
  if (/watch|warn/.test(lowered)) return 'watch'
  if (/good|ok|info|low/.test(lowered)) return 'info'
  return 'info'
}
