import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { DataContextValue } from '../../state/DataContext'
import { PortfolioConstellationFlavor } from '../PortfolioConstellationFlavor'

const { useDataMock } = vi.hoisted(() => ({
  useDataMock: vi.fn(),
}))

vi.mock('../../state/DataContext', () => ({
  useData: useDataMock,
}))

function makeData(): DataContextValue {
  return {
    portfolio: {
      generated_at_utc: '2026-04-30T17:00:00Z',
      source_evidence_at_utc: null,
      trading_mode: 'paper',
      data_state: 'available',
      source_summary: 'Runtime evidence loaded.',
      source_notes: [],
      metric_cards: [],
      equity_curve: { status: 'unavailable', headline: '', detail: '', points: [] },
      benchmark_panel: { status: 'unavailable', headline: '', detail: '', benchmark_rows: [] },
      strategy_panel: {
        status: 'active',
        headline: 'Strategy attribution',
        detail: '',
        active_blueprint_id: 'core-paper-ready-v1',
        constituent_sleeve_ids: ['baseline-long-only-v1'],
        strategies: [
          {
            strategy_id: 'baseline-long-only-v1',
            label: 'Baseline Long Only V1',
            status: 'active',
            pnl: '$0',
            trade_count: '0',
            win_rate: '0%',
            max_drawdown: '0%',
            detail: '',
          },
        ],
      },
      execution_panel: {
        status: 'unavailable',
        headline: '',
        detail: '',
        summary_metrics: [],
        recent_events: [],
      },
      positions_panel: {
        status: 'available',
        headline: 'Open positions',
        detail: '',
        positions: [
          {
            symbol: 'SPY',
            quantity: '1',
            market_value: '100',
            exposure_pct: '1',
            status: 'long',
          },
        ],
      },
      diagnostics: [],
    },
    blueprintCatalog: {
      blueprints: [
        {
          blueprint_id: 'core-paper-multi-sleeve-v1',
          source_path: 'config/portfolio/blueprints/core-paper-multi-sleeve-v1.yaml',
          max_gross_exposure: '1.0',
          max_net_exposure: '1.0',
          status: 'available',
          detail: '',
          sleeve_budgets: [
            {
              sleeve_id: 'baseline-long-only-v1',
              strategy_id: 'baseline-long-only-v1',
              budget_fraction_of_equity: '0.40',
              max_correlation_with_other_sleeves: '0.85',
            },
            {
              sleeve_id: 'mean-reversion-v1',
              strategy_id: 'mean-reversion-v1',
              budget_fraction_of_equity: '0.20',
              max_correlation_with_other_sleeves: '0.85',
            },
          ],
        },
        {
          blueprint_id: 'core-paper-ready-v1',
          source_path: 'config/portfolio/blueprints/core-paper-ready-v1.yaml',
          max_gross_exposure: '1.0',
          max_net_exposure: '1.0',
          status: 'available',
          detail: '',
          sleeve_budgets: [
            {
              sleeve_id: 'baseline-long-only-v1',
              strategy_id: 'baseline-long-only-v1',
              budget_fraction_of_equity: '0.05',
              max_correlation_with_other_sleeves: '0.85',
            },
          ],
        },
      ],
      active_activation: {
        activation_id: 'activation-ready',
        blueprint_id: 'core-paper-ready-v1',
        sleeve_activation_bindings: [
          {
            sleeve_id: 'baseline-long-only-v1',
            strategy_id: 'baseline-long-only-v1',
            captured_snapshot_id: 'approved-baseline-long-only-v1',
          },
        ],
        status: 'active',
        approved_at_utc: '2026-04-30T16:01:40Z',
        approved_by: 'local-operator',
        source_blueprint_path: 'config/portfolio/blueprints/core-paper-ready-v1.yaml',
        blueprint_content_hash: 'sha256:ready',
      },
      pending_activation: null,
    },
    botBrain: {
      generated_at_utc: '2026-04-30T17:00:00Z',
      active_blueprint_id: 'core-paper-ready-v1',
      queued_blueprint_id: '',
      trading_mode: 'paper',
      market_state: 'open',
      next_check_at_utc: null,
      decision_stages: [],
      last_real_order: null,
      cycle_explanation: {
        summary: 'No trade because the planner held.',
        primary_reason_code: 'no_trade',
        market_state: 'open',
        planner_status: 'no_trade',
        risk_status: 'not_blocked',
        sleeve_reasons: [],
      },
      sleeve_readiness: [
        {
          sleeve_id: 'mean-reversion-v1',
          strategy_id: 'mean-reversion-v1',
          implemented: true,
          runtime_resolvable: true,
          paper_approved: false,
          allocation_approved: false,
          display_state: 'blocked',
          blocker_code: 'authority_artifact_invalid',
          human_explanation: 'Missing authority package for paper trading.',
          fix_guidance: 'Generate and sign a valid paper-trading promotion bundle.',
          evidence_refs: [],
        },
      ],
    },
    writeMode: {
      enabled: false,
      configured: false,
      unlocked: false,
      detail: 'Writes locked.',
    },
    refresh: vi.fn(),
    runAction: vi.fn(),
  } as unknown as DataContextValue
}

describe('PortfolioConstellationFlavor blueprint activation panel', () => {
  beforeEach(() => {
    useDataMock.mockReturnValue(makeData())
  })

  it('defaults the blueprint selector and sleeve table to the active activation', () => {
    render(<PortfolioConstellationFlavor />)

    expect(screen.getByLabelText('Blueprint to activate')).toHaveValue('core-paper-ready-v1')
    expect(screen.getByText('5%')).toBeInTheDocument()
    expect(screen.queryByText('Mean Reversion V1')).not.toBeInTheDocument()
  })

  it('keeps an operator-selected candidate after the active default is shown', () => {
    render(<PortfolioConstellationFlavor />)

    fireEvent.change(screen.getByLabelText('Blueprint to activate'), {
      target: { value: 'core-paper-multi-sleeve-v1' },
    })

    expect(screen.getByLabelText('Blueprint to activate')).toHaveValue(
      'core-paper-multi-sleeve-v1',
    )
    expect(screen.getAllByText('Mean Reversion V1').length).toBeGreaterThan(0)
  })

  it('renders backend-provided strategy readiness guidance', () => {
    render(<PortfolioConstellationFlavor />)

    expect(screen.getByText('Missing authority package for paper trading.')).toBeInTheDocument()
    expect(screen.getByText('Generate and sign a valid paper-trading promotion bundle.')).toBeInTheDocument()
  })
})
