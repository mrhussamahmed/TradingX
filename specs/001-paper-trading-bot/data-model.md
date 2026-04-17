---
id: DATAMODEL-0001
title: TradingX Stage 1 planning data model
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-004
---

# Data model

## StrategyCandidate

| Field | Type | Notes |
| ----- | ---- | ----- |
| `candidate_id` | string | Stable identifier, e.g. `trend-following-v1` |
| `family` | enum | `trend_following`, `vol_target`, `mean_reversion`, `optional` |
| `benchmark_symbol` | string | Stage 1 default is `SPY` |
| `universe` | list[string] | Symbols or ETF basket under test |
| `parameter_set` | mapping | Deterministic strategy parameters only |
| `status` | enum | `proposed`, `under_evaluation`, `recommended`, `rejected` |
| `evidence_pack_id` | string/null | Pointer to the latest completed evidence pack |

**Validation rules**

- Mandatory candidates must exist before any optional candidate can be
  promoted.
- Parameters are versioned inputs, not mutable runtime state.

## EvaluationEvidencePack

| Field | Type | Notes |
| ----- | ---- | ----- |
| `evidence_pack_id` | string | Stable evidence artifact identifier |
| `candidate_id` | string | Foreign key to `StrategyCandidate` |
| `window_start_utc` | datetime | UTC only |
| `window_end_utc` | datetime | UTC only |
| `benchmark_metrics` | object | SPY-relative metrics over the same window |
| `candidate_metrics` | object | Net-of-cost candidate metrics |
| `adversarial_checks` | list[object] | OOS, walk-forward, sensitivity, regime checks |
| `recommendation` | enum | `keep`, `reject`, `research_further` |
| `assumptions` | list[string] | Explicit assumptions and caveats |

**Validation rules**

- Each mandatory candidate must receive the same adversarial check set.
- Every recommendation must cite the metrics window and cost assumptions.

## MarketObservation

| Field | Type | Notes |
| ----- | ---- | ----- |
| `symbol` | string | Uppercase ticker |
| `last_trade_price` | decimal | `Decimal` in implementation |
| `bid_price` | decimal | `Decimal` in implementation |
| `ask_price` | decimal | `Decimal` in implementation |
| `average_daily_volume_30d` | decimal | Used for liquidity gating |
| `observed_at_utc` | datetime | Used for stale-data checks |

**Validation rules**

- Observation timestamps must be within the stale-data window or the
  trading loop blocks.

## TradeIntent

| Field | Type | Notes |
| ----- | ---- | ----- |
| `intent_id` | string | Deterministic or idempotent identifier |
| `candidate_id` | string | Selected strategy lineage |
| `symbol` | string | Uppercase ticker |
| `side` | enum | `buy`, `sell`, `hold`, `skip`, `reduce` |
| `quantity` | decimal | Positive only for actionable intents |
| `reason_code` | string | Strategy-level rationale code |
| `generated_at_utc` | datetime | UTC only |

**State transitions**

- `generated` -> `blocked` when a hard risk check fails
- `generated` -> `approved` when all risk checks pass
- `approved` -> `submitted` when execution accepts the order
- `submitted` -> `reconciled` when broker and internal state agree

## RiskControlEvent

| Field | Type | Notes |
| ----- | ---- | ----- |
| `event_id` | string | Stable event identifier |
| `intent_id` | string/null | Present when tied to a trade intent |
| `severity` | enum | `info`, `warning`, `critical` |
| `control_type` | enum | Liquidity, price floor, stale data, kill switch, etc. |
| `blocked` | bool | True when the event prevented order submission |
| `recorded_at_utc` | datetime | UTC only |
| `operator_visible` | bool | Critical events must be operator-visible |

**Validation rules**

- Hard pre-trade violations always produce a recorded event.
- Strategy logic does not receive the detailed block reason back.

## PaperOrderRecord

| Field | Type | Notes |
| ----- | ---- | ----- |
| `order_id` | string | Broker order identifier |
| `client_order_id` | string | Idempotency key |
| `intent_id` | string | Foreign key to `TradeIntent` |
| `symbol` | string | Uppercase ticker |
| `side` | enum | `buy` or `sell` |
| `status` | enum | Broker lifecycle status |
| `filled_qty` | decimal | `Decimal` in implementation |
| `filled_avg_price` | decimal | `Decimal` in implementation |
| `submitted_at_utc` | datetime | UTC only |
| `completed_at_utc` | datetime/null | UTC only |

## PortfolioState

| Field | Type | Notes |
| ----- | ---- | ----- |
| `as_of_utc` | datetime | Snapshot time |
| `cash` | decimal | `Decimal` in implementation |
| `equity` | decimal | `Decimal` in implementation |
| `buying_power` | decimal | `Decimal` in implementation |
| `positions` | list[object] | Symbol, quantity, average price, exposure |
| `open_orders` | list[string] | Current order ids |

**Validation rules**

- Account equity must stay positive for any new trade approval.
- Exposure calculations use the reconciled snapshot, not stale cached
  state.

## ReconciliationSnapshot

| Field | Type | Notes |
| ----- | ---- | ----- |
| `reconciliation_id` | string | Stable reconciliation identifier |
| `portfolio_state` | object | Embedded `PortfolioState` |
| `broker_state_age_seconds` | integer | Compared against stale-state limit |
| `differences` | list[object] | Any internal vs broker mismatches |
| `resolved` | bool | True when the system reaches a terminal state |

## OperatorAlert

| Field | Type | Notes |
| ----- | ---- | ----- |
| `alert_id` | string | Stable alert identifier |
| `severity` | enum | `info`, `warning`, `critical` |
| `category` | enum | `risk`, `operations`, `gate`, `performance` |
| `summary` | string | Human-readable one-line summary |
| `evidence_refs` | list[string] | Artifact paths or ids |
| `delivery_targets` | list[enum] | `telegram`, `smtp`, `clickup` |
| `sent_at_utc` | datetime | UTC only |

## GateAssessment

| Field | Type | Notes |
| ----- | ---- | ----- |
| `gate_id` | enum | `0`, `0.5`, `1`, `2`, `3`, `4` |
| `status` | enum | `pass`, `pending`, `fail` |
| `evidence_refs` | list[string] | Validation artifacts and reports |
| `decision_summary` | string | Why the gate passed or failed |
| `recorded_at_utc` | datetime | UTC only |
