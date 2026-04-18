---
id: DATAMODEL-0008
title: TradingX local trading appliance data model
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-022
---

# Data Model: TradingX local trading appliance

## BotRuntimeState

- `status`: `idle | bootstrapping | historical_warmup | broker_sync |
  feature_ready | strategy_ready | trading_ready | degraded | halted |
  stopping`
- `status_reason`: operator-facing explanation for the current state
- `active_symbols`: currently configured universe
- `started_at_utc`: latest runtime start
- `updated_at_utc`: latest state transition time
- `last_error`: latest fail-closed summary if any
- `active_strategy_id`: loaded activation strategy id, if any
- `active_model_snapshot_id`: loaded weight snapshot id, if any
- `latest_selection_id`: latest opportunity-selection record id, if any

## HistoricalWarmupRecord

- `warmup_id`: unique record id
- `generated_at_utc`: creation timestamp
- `benchmark_symbol`: benchmark used for warmup context
- `symbols`: warmed universe
- `window_start_utc`: earliest bar used
- `window_end_utc`: latest bar used
- `required_bar_count`: minimum bars required by the runtime
- `symbols_ready`: symbols with enough bars
- `symbols_blocked`: mapping of symbol to warmup failure reason
- `return_summary`: simple return/trend statistics per symbol

## StrategyActivationRecord

- `activation_id`: unique activation record id
- `strategy_id`: active strategy identifier
- `strategy_version`: operator-approved version string
- `approved_symbols`: allowed universe
- `deploy_threshold`: minimum score required for entry
- `allow_fallback_weights`: whether deterministic fallback is legal
- `status`: `draft | approved | suspended | retired`
- `activated_at_utc`: approval timestamp
- `notes`: operator-facing explanation

## ModelWeightSnapshot

- `snapshot_id`: immutable weight snapshot id
- `strategy_id`: bound strategy id
- `status`: `draft | approved | superseded | rejected`
- `generated_at_utc`: creation timestamp
- `minimum_supporting_trades`: sample-size floor
- `weights`: mapping for:
  - `signal`
  - `regime`
  - `liquidity`
  - `spread_penalty`
  - `volatility_penalty`
  - `portfolio_overlap_penalty`
  - `execution_cost_penalty`

## ModelWeightProposal

- `proposal_id`: unique proposal id
- `generated_at_utc`: creation timestamp
- `strategy_id`: target strategy id
- `supporting_trade_count`: number of closed trades used
- `baseline_snapshot_id`: current snapshot used for comparison
- `candidate_snapshot`: proposed weights
- `improvement_score`: net improvement metric
- `statistically_significant`: whether thresholds were met
- `summary`: operator-facing recommendation

## OpportunityScore

- `symbol`: candidate symbol
- `base_signal`: raw strategy signal score
- `regime_weight`: regime factor
- `model_weight`: learned or fallback factor
- `liquidity_weight`: liquidity factor
- `spread_penalty`: spread cost term
- `volatility_penalty`: volatility term
- `portfolio_overlap_penalty`: overlap term
- `execution_cost_penalty`: expected execution drag
- `final_score`: final ranking score
- `eligible`: whether the symbol survived pre-ranking filters
- `ineligibility_reason`: blank when eligible

## OpportunitySelectionRecord

- `selection_id`: unique record id
- `generated_at_utc`: creation timestamp
- `strategy_id`: strategy used for ranking
- `model_snapshot_id`: snapshot used for ranking or fallback marker
- `symbols_considered`: universe passed into ranking
- `ranked_opportunities`: ordered `OpportunityScore` entries
- `selected_symbol`: chosen symbol or empty for `NO_TRADE`
- `decision`: `selected | no_trade`
- `decision_reason`: deploy-threshold or eligibility explanation

