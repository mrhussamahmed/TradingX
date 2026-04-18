---
id: DATAMODEL-0004
title: TradingX Gate 3 operations and evidence data model
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-016
---

# Data Model: TradingX Gate 3 operations and evidence

## ExecutionLifecycleRecord

- `execution_id`
- `intent_id`
- `symbol`
- `side`
- `reason_code`
- `reference_price`
- `fill_price`
- `filled_qty`
- `slippage_bps`
- `submitted_at_utc`
- `filled_at_utc`
- `recovered`

## ClosedTradeRecord

- `trade_id`
- `symbol`
- `entry_intent_id`
- `exit_intent_id`
- `opened_at_utc`
- `closed_at_utc`
- `quantity`
- `entry_price`
- `exit_price`
- `gross_pnl`
- `return_pct`
- `outcome`
- `holding_period_seconds`

## RecoveryDrillRecord

- `drill_id`
- `symbol`
- `started_at_utc`
- `completed_at_utc`
- `status`
- `summary`
- `evidence_refs`

## AlertDrillRecord

- `drill_id`
- `channel`
- `recorded_at_utc`
- `status`
- `summary`
- `evidence_refs`

## MarketSessionRecord

- `session_id`
- `session_label`
- `recorded_at_utc`
- `service_status`
- `blocked_trade_count`
- `reconciliation_failure_count`
- `open_positions`
- `top_incidents`
- `recommended_actions`
- `evidence_refs`

## Gate3CriterionSnapshot

- `criterion_id`
- `status`
- `threshold`
- `observed_value`
- `details`
- `evidence_refs`

## Gate3ReadinessReport

- `report_id`
- `generated_at_utc`
- `status`
- `closed_trade_count`
- `calendar_days_observed`
- `criteria`
- `summary`
- `required_operator_action`
- `evidence_refs`

## Gate3PromotionPackage

- `package_id`
- `generated_at_utc`
- `status`
- `headline`
- `decision_summary`
- `criteria_statuses`
- `evidence_refs`
