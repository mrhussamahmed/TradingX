---
id: CONTRACT-0008
title: Market-day scheduler API contract
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-020
---

# Market-day scheduler API contract

## Read endpoints

- `GET /api/platform/gate3/scheduler/state`
  Returns the live scheduler runtime state.
- `GET /api/platform/gate3/scheduler/latest`
  Returns the latest persisted market-day schedule record or `null`.

## Write endpoints

- `POST /api/actions/scheduler/start`
  Starts the local recurring scheduler with:
  - `symbols`
  - `quantity`
  - `interval_seconds`
  - `poll_interval_seconds`
  - optional `max_scheduled_days`
- `POST /api/actions/scheduler/stop`
  Requests that the local recurring scheduler stop after the current
  wait or active run completes.

## Response rules

- write endpoints require web write mode
- responses use the existing `WebActionResult` shape
- responses must not include secrets or raw credentials
