---
id: DATAMODEL-0003
title: TradingX operator platform data model
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-014
---

# Data Model: TradingX operator platform

## CommandCenterSnapshot

- `generated_at_utc`
- `service_status`
- `session_mode`
- `market_session_label`
- `account_summary`
- `equity_curve`
- `exposure_breakdown`
- `watchlist`
- `gate_statuses`
- `recommendations`
- `headline_incidents`

## OperatorTimelineEvent

- `event_id`
- `event_type`
- `symbol`
- `severity`
- `headline`
- `details`
- `occurred_at_utc`
- `artifact_path`
- `related_ids`

## IncidentRecord

- `incident_id`
- `title`
- `severity`
- `status`
- `category`
- `summary`
- `first_seen_at_utc`
- `latest_seen_at_utc`
- `acknowledged_at_utc`
- `acknowledged_by`
- `related_event_ids`
- `evidence_refs`
- `suggested_action`

## ResearchCandidateSummary

- `candidate_id`
- `family`
- `recommendation`
- `benchmark_metrics`
- `candidate_metrics`
- `adversarial_checks`
- `gate_statuses`
- `summary`

## ReplaySession

- `replay_id`
- `focus_type`
- `focus_value`
- `headline`
- `events`
- `summary`

## DailySessionDigest

- `digest_id`
- `generated_at_utc`
- `session_label`
- `service_status`
- `blocked_trade_count`
- `reconciliation_failure_count`
- `latest_positions`
- `top_incidents`
- `recommended_actions`
- `evidence_refs`
