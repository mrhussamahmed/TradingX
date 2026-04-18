---
id: DESIGN-0004
title: TradingX market-day automation design
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-018
---

# TradingX market-day automation design

## Intent

Turn the current manual session controls into a real market-day
automation workflow that can run pre-open checks, bounded intraday
heartbeats, closeout evidence refreshes, and daily Gate 3 rollups with
truthful persisted records.

## Product shape

The phase adds four connected capabilities:

- `Market-day runner` for pre-open, heartbeat, close, and bounded
  full-day execution
- `Automation run artifacts` that record what happened, what evidence
  was refreshed, and whether the run completed cleanly
- `Automatic Gate 3 refresh` so replay-slippage and readiness evidence
  stay in sync with new paper executions
- `Operator-platform automation surface` so the local website can run,
  inspect, and review automation history

## Architecture

The backend keeps one local FastAPI service and one React SPA. The new
layer introduces:

- a dedicated market-day automation module that orchestrates the
  existing paper service, replay-slippage engine, and Gate 3 reporting
- persisted automation-run artifacts under `artifacts/operator_platform`
- upgraded session actions that execute real pre-open, heartbeat, and
  close logic instead of snapshot-only placeholders
- one bounded full-run entry point for CLI and write-mode web actions

## Data flow

1. Pre-open writes a session checkpoint and a daily digest from current
   paper evidence and runtime state.
2. Each heartbeat optionally executes one paper-service cycle, then
   refreshes replay-slippage evidence and Gate 3 readiness.
3. Close writes the end-of-day checkpoint, refreshes Gate 3 package
   output, and persists a market-automation run summary.
4. The web read model surfaces the latest automation run and daily
   posture from persisted artifacts, never from browser-owned state.

## Safety model

- read-only remains the default website posture
- full automation remains bounded by explicit interval and optional
  heartbeat limits
- market-closed periods become structured `skipped` or `completed`
  statuses, not silent failures
- all automation errors are sanitized and persisted through structured
  artifacts or action results
- live trading stays disabled at all layers

## Testing shape

- backend unit tests for automation orchestration and run-artifact
  persistence
- parser tests for new CLI automation commands
- contract tests for new automation API endpoints
- web runtime tests for pre-open, heartbeat, close, and full-run
  actions
- frontend tests for the automation dashboard and action controls
- full repo validation through `./scripts/validate`
