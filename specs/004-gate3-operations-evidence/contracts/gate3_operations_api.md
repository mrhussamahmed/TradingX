---
id: CONTRACT-0005
title: Gate 3 operations and evidence API contract
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-016
---

# Gate 3 operations and evidence API contract

## Read endpoints

| Route | Purpose |
| ----- | ------- |
| `GET /api/platform/gate3/readiness` | Latest Gate 3 readiness report |
| `GET /api/platform/gate3/promotions/latest` | Latest Gate 3 promotion package |

## Write-mode endpoints

| Route | Purpose |
| ----- | ------- |
| `POST /api/actions/session/preopen` | Write a market-session pre-open record |
| `POST /api/actions/session/heartbeat` | Write a market-session heartbeat record |
| `POST /api/actions/session/close` | Write a market-session close record |
| `POST /api/actions/recovery-drill` | Exercise bounded recovery for one symbol and persist a recovery drill record |
| `POST /api/actions/alert-drill` | Exercise a bounded alert channel drill and persist an alert drill record |
| `POST /api/actions/gate3/report` | Generate the latest Gate 3 readiness report |
| `POST /api/actions/gate3/package` | Generate the latest Gate 3 promotion package |

## Guard rules

- All write endpoints return `403` when web write mode is disabled.
- Read endpoints remain available in read-only mode.
- A failed drill still returns a structured action result and writes a
  drill artifact when possible.
- No Gate 3 endpoint may enable live trading or alter active runtime
  configuration in place.
