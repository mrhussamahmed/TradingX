---
id: DESIGN-0005
title: TradingX recurring market-day scheduler design
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-020
---

# TradingX recurring market-day scheduler design

## Goal

Add a recurring, local-only scheduler that launches the existing
market-day automation on each trading day without manual babysitting and
leaves behind one durable record per scheduled day.

## Approach

Build a dedicated scheduler layer above `MarketDayAutomationRunner`
rather than teaching the automation runner to be long-running. The
automation runner remains the bounded workflow for a single day; the new
scheduler owns recurrence, duplicate prevention, restart-safe resume
logic, and next-run visibility.

## Core components

- `MarketDayScheduler`: a backend loop that:
  - discovers the current or next regular session from Alpaca's market
    calendar
  - launches `run_market_day(...)` once per trading day
  - writes one persisted schedule record summarizing the scheduled day,
    timing, outcome, and evidence refs
  - avoids relaunching a day that already has a completed schedule
    record
- `MarketDayScheduleRecord`: the persisted artifact for one scheduled
  market day
- `SchedulerState`: the live runtime state used by CLI and web surfaces
  to show whether the scheduler is idle, waiting, running, stopped, or
  in error
- `LocalSchedulerManager`: the background-thread wrapper used by the web
  app so the operator can start and stop the scheduler from the local
  website

## Data flow

1. Scheduler polls on a configured cadence.
2. It asks the regular-hours calendar for the current-or-next session.
3. If the market is already in session and no schedule record exists for
   that trading day, it launches the existing market-day runner
   immediately.
4. If the next session has not opened yet, it waits until the next poll
   cycle while exposing the computed next-run time.
5. When the market-day runner finishes, the scheduler writes a schedule
   record pointing to the automation-run artifact and any resulting
   Gate 3 evidence.

## Safety model

- One launch per trading day
- Local-only and read-only by default in the web app
- No browser-owned scheduling logic
- No weakening of live-trading defenses
- Fail-closed status reporting if the scheduler or automation runner
  errors

## Operator surfaces

- CLI command for running the recurring scheduler directly
- Web start/stop controls and latest scheduler status in the `Gate 3
  Ops` view
- Persisted schedule history so the operator can audit which days were
  launched automatically and what evidence each day produced

## Testing shape

- unit tests for session selection and duplicate prevention
- unit tests for persisted schedule records
- CLI parser tests for the new scheduler command
- web-runtime and API tests for scheduler state and actions
- frontend tests for the scheduler controls and status surface
