---
id: CONTRACT-0007
title: Market-day automation API contract
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-018
---

# Market-day automation API contract

## Read endpoints

| Route | Purpose |
| ----- | ------- |
| `GET /api/platform/gate3/automation/latest` | Latest market-day automation run artifact |
| `GET /api/platform/digests/latest` | Latest checkpoint digest |

## Write-mode endpoints

| Route | Purpose |
| ----- | ------- |
| `POST /api/actions/session/preopen` | Run the real pre-open checkpoint workflow |
| `POST /api/actions/session/heartbeat` | Run one real heartbeat workflow |
| `POST /api/actions/session/close` | Run the real close checkpoint workflow |
| `POST /api/actions/session/market-day` | Run one bounded market-day automation workflow |

## Guard rules

- All write endpoints return `403` when web write mode is disabled.
- Read endpoints remain available in read-only mode.
- The automation runner may return `completed`, `pending`, `skipped`, or
  `failed`, but every response must be structured and secret-safe.
- Automation endpoints may refresh evidence and reports, but they must
  not enable live trading or mutate active runtime configuration.
