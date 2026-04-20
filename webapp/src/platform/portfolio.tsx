import { useState } from 'react'

import type { PortfolioWorkspaceSnapshot } from '../types'
import { EquityChart, Sparkline } from './charts'
import { cx, prettyLabel } from './format'
import { KeyValueList, Panel, StatusBadge } from './ui'

type PortfolioMode = 'guided' | 'analyst'

export function PortfolioWorkspace(props: {
  portfolio: PortfolioWorkspaceSnapshot
  mode: PortfolioMode
  onModeChange: (mode: PortfolioMode) => void
}) {
  const [expandedMetricId, setExpandedMetricId] = useState('')
  const toneForStatus = (status: string) => {
    if (status === 'available') {
      return 'good' as const
    }
    if (status === 'partial' || status === 'waiting') {
      return 'watch' as const
    }
    return 'neutral' as const
  }
  const toneForSource = (tone: string) => {
    if (tone === 'good') {
      return 'good' as const
    }
    if (tone === 'watch') {
      return 'watch' as const
    }
    if (tone === 'risk') {
      return 'risk' as const
    }
    if (tone === 'info') {
      return 'info' as const
    }
    return 'neutral' as const
  }

  return (
    <div className="workspace-grid">
      <Panel
        title="Portfolio"
        eyebrow="Truth-first performance supervision"
        className="workspace-hero-panel"
        actions={
          <div className="segmented-control" role="tablist" aria-label="Portfolio modes">
            {(['guided', 'analyst'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                className={cx('segmented-button', props.mode === mode && 'active')}
                aria-pressed={props.mode === mode}
                onClick={() => props.onModeChange(mode)}
              >
                {prettyLabel(mode)}
              </button>
            ))}
          </div>
        }
      >
        <div className="hero-summary-grid">
          <article className="hero-summary-card">
            <span>Data state</span>
            <strong>{prettyLabel(props.portfolio.data_state)}</strong>
            <p>{props.portfolio.source_summary}</p>
          </article>
          <article className="hero-summary-card">
            <span>Trading mode</span>
            <strong>{prettyLabel(props.portfolio.trading_mode)}</strong>
            <p>The dashboard is showing production-safe paper posture unless live mode is explicitly enabled.</p>
          </article>
          <article className="hero-summary-card">
            <span>Evidence provenance</span>
            <strong>{props.portfolio.source_notes.length ? 'Live versus rehearsal is labeled' : 'No source notes yet'}</strong>
            <div className="source-note-list">
              {props.portfolio.source_notes.map((note) => (
                <div key={note.source_id} className="source-note-item">
                  <StatusBadge label={note.label} tone={toneForSource(note.tone)} />
                  <p>{note.detail}</p>
                </div>
              ))}
            </div>
          </article>
          <article className="hero-summary-card">
            <span>Primary question</span>
            <strong>Is the bot healthy enough to trust?</strong>
            <p>Every card below explains the current value and what it means for the main goal.</p>
          </article>
        </div>
      </Panel>

      <Panel title="Portfolio Metrics" eyebrow="Interpretation first">
        <div className="metric-card-grid">
          {props.portfolio.metric_cards.map((metric) => {
            const open = expandedMetricId === metric.metric_id
            return (
              <article key={metric.metric_id} className={cx('metric-insight-card', `health-${metric.health}`)}>
                <div className="metric-insight-topline">
                  <div>
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                  </div>
                  <StatusBadge
                    label={prettyLabel(metric.health)}
                    tone={
                      metric.health === 'good'
                        ? 'good'
                        : metric.health === 'bad'
                          ? 'risk'
                          : 'neutral'
                    }
                  />
                </div>
                <div className="metric-meta-row">
                  <span>{metric.delta}</span>
                  <div className="metric-sparkline">
                    <Sparkline values={metric.sparkline} />
                  </div>
                </div>
                {metric.provenance ? (
                  <div className="badge-row">
                    <StatusBadge label={metric.provenance.label} tone={toneForSource(metric.provenance.tone)} />
                  </div>
                ) : null}
                <p>{metric.summary}</p>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setExpandedMetricId(open ? '' : metric.metric_id)}
                  aria-expanded={open}
                  aria-label={`What this means for ${metric.label}`}
                >
                  {open ? 'Hide interpretation' : 'What this means'}
                </button>
                {open ? (
                  <div className="metric-detail">
                    <p>{metric.detail}</p>
                    {metric.provenance ? (
                      <div className="metric-provenance-detail">
                        <strong>{metric.provenance.label}</strong>
                        <p>{metric.provenance.detail}</p>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </article>
            )
          })}
        </div>
      </Panel>

      <Panel
        title={props.portfolio.equity_curve.headline}
        eyebrow="Real account path"
        actions={
          <StatusBadge
            label={prettyLabel(props.portfolio.equity_curve.status)}
            tone={toneForStatus(props.portfolio.equity_curve.status)}
          />
        }
      >
        {props.portfolio.equity_curve.points.length ? (
          <p className="panel-supporting-text">{props.portfolio.equity_curve.detail}</p>
        ) : null}
        <EquityChart
          points={props.portfolio.equity_curve.points.map((point) => ({
            label: point.label,
            equity: point.equity,
            cash: point.cash,
            buying_power: point.buying_power,
          }))}
          emptyTitle={props.portfolio.equity_curve.headline}
          emptyDetail={props.portfolio.equity_curve.detail}
        />
      </Panel>

      <Panel
        title={props.portfolio.benchmark_panel.headline}
        eyebrow="Benchmark truth"
        actions={
          <StatusBadge
            label={prettyLabel(props.portfolio.benchmark_panel.status)}
            tone={toneForStatus(props.portfolio.benchmark_panel.status)}
          />
        }
      >
        {props.portfolio.benchmark_panel.benchmark_rows.length ? (
          <p className="panel-supporting-text">{props.portfolio.benchmark_panel.detail}</p>
        ) : null}
        {props.portfolio.benchmark_panel.benchmark_rows.length ? (
          <div className="table-shell">
            <div className="table-header">
              <span>Benchmark</span>
              <span>Portfolio</span>
              <span>Benchmark</span>
              <span>Excess</span>
            </div>
            {props.portfolio.benchmark_panel.benchmark_rows.map((row) => (
              <div key={row.benchmark_id} className="table-row">
                <strong>{row.label}</strong>
                <span>{row.portfolio_return}</span>
                <span>{row.benchmark_return}</span>
                <span>{row.excess_return}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <strong>{props.portfolio.benchmark_panel.headline}</strong>
            <p>{props.portfolio.benchmark_panel.detail}</p>
          </div>
        )}
      </Panel>

      {props.mode === 'guided' ? (
        <Panel title="What deserves attention next" eyebrow="Operator guidance">
          <div className="stack-list">
            {props.portfolio.diagnostics.map((diagnostic) => (
              <article key={diagnostic.diagnostic_id} className="list-card">
                <div className="list-card-header">
                  <div>
                    <strong>{diagnostic.title}</strong>
                    <div className="diagnostic-owner">{diagnostic.owner}</div>
                  </div>
                  <StatusBadge
                    label={prettyLabel(diagnostic.severity)}
                    tone={
                      diagnostic.severity === 'critical'
                        ? 'risk'
                        : diagnostic.severity === 'warning'
                          ? 'watch'
                          : 'info'
                    }
                  />
                </div>
                <p>{diagnostic.detail}</p>
                <span>{diagnostic.action}</span>
              </article>
            ))}
          </div>
        </Panel>
      ) : (
        <>
          <Panel
            title={props.portfolio.execution_panel.headline}
            eyebrow="Execution diagnostics"
            actions={
              <div className="badge-row wrap">
                <StatusBadge
                  label={prettyLabel(props.portfolio.execution_panel.status)}
                  tone={toneForStatus(props.portfolio.execution_panel.status)}
                />
                {props.portfolio.execution_panel.provenance ? (
                  <StatusBadge
                    label={props.portfolio.execution_panel.provenance.label}
                    tone={toneForSource(props.portfolio.execution_panel.provenance.tone)}
                  />
                ) : null}
              </div>
            }
          >
            <p className="panel-supporting-text">{props.portfolio.execution_panel.detail}</p>
            {props.portfolio.execution_panel.provenance ? (
              <p className="panel-provenance-note">{props.portfolio.execution_panel.provenance.detail}</p>
            ) : null}
            {props.portfolio.execution_panel.recent_events.length ? (
              <>
                <KeyValueList items={props.portfolio.execution_panel.summary_metrics} />
                <div className="stack-list">
                  {props.portfolio.execution_panel.recent_events.map((event) => (
                    <article key={`${event.label}-${event.value}`} className="list-card">
                      <div className="list-card-header">
                        <strong>{event.label}</strong>
                        <span>{event.value}</span>
                      </div>
                      <p>{event.context}</p>
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <strong>{props.portfolio.execution_panel.headline}</strong>
                <p>The execution journal has no recent operator-visible activity.</p>
              </div>
            )}
          </Panel>

          <Panel
            title={props.portfolio.positions_panel.headline}
            eyebrow="Exposure inventory"
            actions={
              <StatusBadge
                label={prettyLabel(props.portfolio.positions_panel.status)}
                tone={toneForStatus(props.portfolio.positions_panel.status)}
              />
            }
          >
            {props.portfolio.positions_panel.positions.length ? (
              <p className="panel-supporting-text">{props.portfolio.positions_panel.detail}</p>
            ) : null}
            {props.portfolio.positions_panel.positions.length ? (
              <div className="table-shell">
                <div className="table-header">
                  <span>Symbol</span>
                  <span>Quantity</span>
                  <span>Market Value</span>
                  <span>Status</span>
                </div>
                {props.portfolio.positions_panel.positions.map((position) => (
                  <div key={position.symbol} className="table-row">
                    <strong>{position.symbol}</strong>
                    <span>{position.quantity}</span>
                    <span>{position.market_value}</span>
                    <span>{prettyLabel(position.status)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <strong>{props.portfolio.positions_panel.headline}</strong>
                <p>Exposure is currently flat, so there is no live inventory to reconcile.</p>
              </div>
            )}
          </Panel>

          <Panel
            title={props.portfolio.strategy_panel.headline}
            eyebrow="Strategy analytics"
            actions={
              <StatusBadge
                label={prettyLabel(props.portfolio.strategy_panel.status)}
                tone={toneForStatus(props.portfolio.strategy_panel.status)}
              />
            }
          >
            {props.portfolio.strategy_panel.strategies.length ? (
              <p className="panel-supporting-text">{props.portfolio.strategy_panel.detail}</p>
            ) : null}
            {props.portfolio.strategy_panel.strategies.length ? (
              <div className="table-shell">
                <div className="table-header">
                  <span>Strategy</span>
                  <span>Trades</span>
                  <span>Win Rate</span>
                  <span>Drawdown</span>
                </div>
                {props.portfolio.strategy_panel.strategies.map((strategy) => (
                  <div key={strategy.strategy_id} className="table-row">
                    <strong>{strategy.label}</strong>
                    <span>{strategy.trade_count}</span>
                    <span>{strategy.win_rate}</span>
                    <span>{strategy.max_drawdown}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <strong>{props.portfolio.strategy_panel.headline}</strong>
                <p>{props.portfolio.strategy_panel.detail}</p>
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}
