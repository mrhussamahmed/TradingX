---
id: DATAMODEL-0006
title: TradingX market-day automation data model
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-018
---

# Data Model: TradingX market-day automation

## MarketAutomationRunRecord

- `run_id`
- `started_at_utc`
- `completed_at_utc`
- `trading_day`
- `status`
- `heartbeat_count`
- `preopen_session_id`
- `heartbeat_session_ids`
- `close_session_id`
- `latest_replay_summary_id`
- `latest_gate3_report_id`
- `latest_gate3_package_id`
- `summary`
- `evidence_refs`

## MarketAutomationRunResult

- `run_record`
- `run_record_path`
- `session_paths`
- `daily_digest_paths`
- `replay_summary_path`
- `gate3_report_path`
- `gate3_package_path`

## Existing reused entities

- `MarketSessionRecord`
- `DailySessionDigest`
- `ReplaySlippageSummary`
- `Gate3ReadinessReport`
- `Gate3PromotionPackage`
