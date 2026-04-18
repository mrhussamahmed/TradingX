---
id: CONTRACT-0009
title: Local trading appliance API contract
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-022
---

# Local trading appliance API contract

## Runtime ownership rules

- The website may only call the operator API.
- The operator API may only change runtime state through the runtime
  host.
- Runtime state transitions must not bypass readiness checks.
- Learning and proposal generation must not activate model snapshots.

## Read endpoints

- `GET /api/runtime-host/state`
  Returns the current `BotRuntimeState`.
- `GET /api/runtime-host/warmup/latest`
  Returns the latest `HistoricalWarmupRecord` or `null`.
- `GET /api/runtime-host/selection/latest`
  Returns the latest `OpportunitySelectionRecord` or `null`.
- `GET /api/runtime-host/activation/latest`
  Returns the latest approved `StrategyActivationRecord` or `null`.
- `GET /api/runtime-host/model/latest`
  Returns the latest approved `ModelWeightSnapshot` or `null`.
- `GET /api/runtime-host/proposal/latest`
  Returns the latest `ModelWeightProposal` or `null`.

## Write endpoints

- `POST /api/actions/runtime-host/start`
  Starts the local trading appliance with:
  - `symbols`
  - `quantity`
  - optional `interval_seconds`
- `POST /api/actions/runtime-host/stop`
  Requests a safe runtime stop.
- `POST /api/actions/runtime-host/learn`
  Triggers a bounded learning/proposal refresh from persisted
  closed-trade artifacts.

## Response rules

- Write endpoints require web write mode.
- Write endpoints return the existing `WebActionResult` shape.
- No endpoint may include secrets, raw credentials, or unsanitized
  broker exception payloads.
- Read endpoints may expose only artifact-backed state and sanitized
  runtime summaries.

