---
id: CONTRACT-0001
title: Trading loop contract
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-004
---

# Trading loop contract

## Purpose

Define the stable contract between strategy generation, hard risk
controls, paper execution, and reconciliation so every trade attempt ends
in an auditable terminal state.

## Lifecycle

```text
market observation
  -> trade intent
  -> risk decision
  -> paper order submission
  -> broker fill or rejection
  -> reconciliation snapshot
  -> evidence record
```

## Contract records

### 1. Market observation -> Trade intent

| Field | Required | Notes |
| ----- | -------- | ----- |
| `symbol` | yes | Uppercase ticker |
| `observed_at_utc` | yes | Must satisfy stale-data policy |
| `signal_family` | yes | Selected strategy family |
| `proposed_side` | yes | `buy`, `sell`, `hold`, `skip`, `reduce` |
| `proposed_quantity` | conditional | Required when side is actionable |
| `reason_code` | yes | Deterministic strategy rationale |

### 2. Trade intent -> Risk decision

| Field | Required | Notes |
| ----- | -------- | ----- |
| `intent_id` | yes | Stable idempotency anchor |
| `paper_only` | yes | Must be `true` in Stage 1 |
| `account_equity` | yes | Used for concentration and budget checks |
| `buying_power` | yes | Used for margin checks |
| `current_position_quantity` | yes | Used for exposure calculation |
| `kill_switch_active` | yes | Hard stop input |
| `decision` | yes | `approved` or `blocked` |
| `control_code` | yes | Stored for audit; not fed back to strategy |

### 3. Approved intent -> Paper order submission

| Field | Required | Notes |
| ----- | -------- | ----- |
| `client_order_id` | yes | Required for idempotency |
| `broker_mode` | yes | Must resolve to `paper` |
| `symbol` | yes | Uppercase ticker |
| `side` | yes | `buy` or `sell` |
| `quantity` | yes | Positive decimal |
| `order_type` | yes | Market for entry; deterministic broker-managed close for the walking skeleton exit path |
| `submitted_at_utc` | yes | UTC only |

### 4. Submission -> Reconciliation

| Field | Required | Notes |
| ----- | -------- | ----- |
| `order_id` | yes | Broker id |
| `broker_status` | yes | Filled, canceled, rejected, etc. |
| `filled_qty` | yes | `Decimal` in implementation |
| `filled_avg_price` | yes | `Decimal` in implementation |
| `final_position_quantity` | yes | Must reconcile against portfolio state |
| `reconciliation_id` | yes | Links order and account evidence |
| `terminal_state` | yes | `reconciled_trade` or `blocked_trade` |

## Invariants

- Every actionable trade intent must end as either `reconciled_trade` or
  `blocked_trade`; there is no silent drop path.
- Live trading cannot satisfy this contract because `paper_only` is a
  required true field in Stage 1.
- Risk blocks are visible to audit trails and operator alerts, but their
  detailed control codes are not strategy feedback.
- Reconciliation failure escalates to a material operator event.
