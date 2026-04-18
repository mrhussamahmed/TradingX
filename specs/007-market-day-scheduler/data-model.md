---
id: DATAMODEL-0007
title: TradingX recurring market-day scheduler data model
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-020
---

# Data Model: TradingX recurring market-day scheduler

## MarketDayScheduleRecord

- `schedule_id`: unique record id
- `trading_day`: NY session date in `YYYY-MM-DD`
- `scheduled_open_at_utc`: session open time the scheduler targeted
- `launched_at_utc`: when the market-day runner actually started
- `completed_at_utc`: when the scheduled automation finished
- `status`: `completed | failed | skipped`
- `automation_run_id`: linked `MarketAutomationRunRecord.run_id`
- `summary`: operator-facing outcome summary
- `evidence_refs`: paths to automation and validation artifacts

## MarketDaySchedulerState

- `status`: `idle | waiting | running | stopped | error`
- `poll_interval_seconds`: scheduler poll cadence
- `active_symbols`: current configured symbol universe
- `next_run_at_utc`: next computed session open, if known
- `last_started_at_utc`: latest scheduler-launched day start time
- `last_completed_at_utc`: latest scheduler-launched day completion
- `active_trading_day`: trading day currently being processed
- `last_error`: latest error summary, if any

## SessionWindow

- `trading_day`: NY session date
- `open_at_utc`: regular session open
- `close_at_utc`: regular session close

This is an internal scheduler/calender structure, not a persisted
artifact.
