---
id: CONTRACT-0002
title: Operator alerts and evidence contract
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-004
---

# Operator alerts and evidence contract

## Purpose

Define the stable payloads that TradingX sends to bounded operator
surfaces and stores as evidence for gate decisions.

## Event classes

| Class | Severity | Delivery target | Description |
| ----- | -------- | --------------- | ----------- |
| `risk_control_event` | `warning` or `critical` | Telegram, SMTP for critical | Hard pre-trade block, kill switch, stale state, or reconciliation failure |
| `paper_trade_evidence` | `info` | Stored artifact, Telegram summary optional | Completed paper trade with market, order, and reconciliation trail |
| `strategy_evaluation_summary` | `info` or `warning` | ClickUp summary, local artifacts | Candidate-level benchmark and adversarial results |
| `gate_decision_request` | `critical` | Telegram plus SMTP | Event requiring operator go/no-go attention |

## Required payload fields

### Common envelope

| Field | Required | Notes |
| ----- | -------- | ----- |
| `alert_id` | yes | Stable identifier |
| `created_at_utc` | yes | UTC only |
| `severity` | yes | `info`, `warning`, `critical` |
| `category` | yes | `risk`, `operations`, `performance`, `gate` |
| `summary` | yes | One-line operator-readable conclusion |
| `evidence_refs` | yes | Paths or artifact ids |

### Risk control event

| Field | Required | Notes |
| ----- | -------- | ----- |
| `control_type` | yes | Liquidity, price floor, stale data, stale state, kill switch, etc. |
| `intent_id` | conditional | Present when tied to a trade attempt |
| `blocked` | yes | Whether the event prevented order submission |
| `operator_action_required` | yes | Boolean escalation flag |

### Paper trade evidence

| Field | Required | Notes |
| ----- | -------- | ----- |
| `symbol` | yes | Uppercase ticker |
| `buy_order_id` | yes | Broker identifier |
| `sell_order_id` | yes | Broker identifier |
| `cash_delta` | yes | `Decimal` in implementation |
| `reconciliation_id` | yes | Links to final broker state |

### Strategy evaluation summary

| Field | Required | Notes |
| ----- | -------- | ----- |
| `candidate_id` | yes | Strategy lineage |
| `window` | yes | Evaluation observation window |
| `benchmark_comparison` | yes | Same-window SPY-relative metrics |
| `recommendation` | yes | `keep`, `reject`, `research_further` |
| `assumptions` | yes | Explicit caveats |

### Gate decision request

| Field | Required | Notes |
| ----- | -------- | ----- |
| `gate_id` | yes | `0`, `0.5`, `1`, `2`, `3`, or `4` |
| `status` | yes | `pass`, `pending`, `fail` |
| `decision_summary` | yes | Why the gate is in this state |
| `required_operator_action` | yes | Exact human decision needed |

## Delivery rules

- Telegram remains the hot path for real-time operator attention.
- SMTP is reserved for emergency or critical gate-facing events.
- ClickUp is allowed only for non-urgent summaries and must never be the
  sole delivery path for critical alerts.
- Delivery transport may fail, but the underlying evidence artifact must
  still be written and indexed by reference.
