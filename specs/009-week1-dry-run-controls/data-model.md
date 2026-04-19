---
id: DATAMODEL-0009
title: TradingX week-1 dry-run controls data model
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-024
---

# Data Model: TradingX week-1 dry-run controls

## PolicySnapshot

- `policy_snapshot_id`
- `generated_at_utc`
- `schema_version`
- `dry_run`
- `universe`
- `max_new_entries_per_day`
- `max_concurrent_positions`
- `max_entries_per_symbol_per_day`
- `reentry_cooldown_scope`
- `per_position_dollar_cap`
- `total_deployed_cap_fraction`
- `daily_drawdown_halt_fraction`
- `quote_absolute_spread_cap`
- `quote_relative_spread_bps_cap`
- `quote_staleness_seconds`
- `data_stall_seconds`
- `broker_failure_threshold`
- `broker_staleness_seconds`
- `cycle_budget_seconds`
- `decision_budget_seconds`
- `close_ladder`

## DecisionSnapshotV1

- `decision_snapshot_id`
- `schema_version`
- `timestamp_utc`
- `cycle_correlation_id`
- `session_snapshot_id`
- `universe_snapshot_id`
- `policy_snapshot_id`
- `model_snapshot_id`
- `strategy_version`
- `strategy_config_hash`
- `git_sha`
- `dry_run`
- `market_data_window_hash`
- `feature_snapshot_id`
- `session_start_equity`
- `candidate_intents`
- `final_action`
- `risk_verdict_id`

## CandidateIntentRecord

- `symbol`
- `selected`
- `terminal_reason`
- `base_score`
- `final_score`
- `eligibility`
- `risk_status`

## OmsJournalEvent

- `event_id`
- `event_type`
- `recorded_at_utc`
- `decision_snapshot_id`
- `cycle_correlation_id`
- `client_order_id`
- `broker_order_id`
- `symbol`
- `side`
- `payload_json`

## RecoveryStateRecord

- `state_id`
- `status`
- `trigger`
- `root_cause`
- `documented`
- `recorded_at_utc`

## DryRunReport

- `report_id`
- `session_date`
- `generated_at_utc`
- `cycle_summaries`
- `blocked_intents`
- `simulated_orders`
- `anomalies`
- `decision_snapshot_refs`
- `journal_backup_path`
