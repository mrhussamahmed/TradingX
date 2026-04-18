---
id: DESIGN-0002
title: TradingX Gate 3 operations and evidence design
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-016
---

# TradingX Gate 3 operations and evidence design

## Intent

Add the market-operations and evidence layer that turns the current bot
 and operator platform into a system that can accumulate, inspect, and
package Gate 3 paper-trading evidence safely.

## Product shape

The phase adds five tightly connected capabilities:

- `Market-day orchestration` for pre-open, intraday, close, and restart
  safe session records
- `Trade lifecycle evidence` for slippage, fills, outcomes, and closed
  trades
- `Operational drills` for recovery exercises and emergency alert drills
- `Gate 3 readiness` for criteria rollups, pass or pending status, and
  promotion packaging
- `Operator-platform readiness surface` for dashboard cards, drill
  history, and daily-operations controls

## Architecture

The backend remains one local FastAPI service and one React SPA. The
new layer introduces:

- a Gate 3 evidence engine that reads persisted artifacts and writes a
  readiness report
- additional paper-loop persistence for execution traces and closed
  trades
- explicit drill records for recovery and alert exercises
- market-session records that capture pre-open, intraday, and close
  checkpoints
- one readiness read model and bounded web or CLI actions for drills,
  report generation, and promotion packaging

## Evidence model

Gate 3 is built on artifacts rather than transient runtime state. The
key records are:

- `execution_lifecycles`
- `closed_trades`
- `recovery_drills`
- `alert_drills`
- `market_sessions`
- `gate3_reports`
- `gate3_packages`

These records are additive. They do not replace the existing service
cycles, reconciliations, alerts, or validation reports.

## Safety model

- read-only remains the default website posture
- all write actions stay behind the existing web write-mode gate
- drill failures are visible and persisted instead of being silently
  swallowed
- live trading remains disabled at all layers
- readiness reports explicitly mark `pending` when evidence is missing

## Testing shape

- backend unit tests for lifecycle persistence and Gate 3 rollups
- contract tests for new API endpoints
- web runtime tests for session and drill actions
- frontend tests for the readiness surface and daily-operations panel
- full repo validation through `./scripts/validate`
