---
id: CONTRACT-0003
title: Local web app API contract
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-013
---

# Local Web App API Contract

## Read endpoints

| Route | Purpose |
| ----- | ------- |
| `GET /api/overview` | Dashboard snapshot |
| `GET /api/evidence/{category}` | Evidence list by category |
| `GET /api/gates/summary` | Latest gate statuses and reports |
| `GET /api/gates/{gate_id}/decision` | Latest decision brief for one gate |
| `GET /api/documents` | Handover/state/index/session listings |
| `GET /api/config/summary` | Current safe config summary and write-mode state |

## Write-mode endpoints

| Route | Purpose |
| ----- | ------- |
| `POST /api/actions/service/start` | Start local paper service |
| `POST /api/actions/service/stop` | Stop local paper service |
| `POST /api/actions/paper-loop` | Run one bounded paper loop |
| `POST /api/actions/recover` | Run bounded recovery for one symbol |
| `POST /api/actions/prepare-benchmark` | Prepare benchmark close artifact |
| `POST /api/actions/gate-report` | Generate Gate 1 or Gate 2 report |
| `POST /api/actions/decision-report` | Refresh a gate decision brief |
| `POST /api/config/proposals` | Write a config proposal artifact |

## Guard rules

- All write endpoints return `403` when web write mode is disabled.
- No endpoint may enable live trading.
- No endpoint may mutate the constitution, ADRs, or active runtime
  config in place.
