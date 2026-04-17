---
id: CONTRACT-0004
title: Operator platform API contract
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-014
---

# Operator Platform API Contract

## Read endpoints

| Route | Purpose |
| ----- | ------- |
| `GET /api/overview` | Legacy overview snapshot for compatibility |
| `GET /api/platform/command-center` | Rich command-center snapshot |
| `GET /api/platform/timeline` | Normalized operator timeline |
| `GET /api/platform/incidents` | Incident queue |
| `GET /api/platform/research` | Research studio snapshot |
| `GET /api/platform/replay` | Replay session by symbol, cycle, or incident |
| `GET /api/platform/explorer` | Searchable artifact/document explorer |
| `GET /api/platform/digests/latest` | Latest daily session digest |
| `GET /api/documents` | Handover/state/index/session listings |
| `GET /api/evidence/{category}` | Evidence list by category |
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
| `POST /api/actions/session/preopen` | Generate a pre-open session check |
| `POST /api/actions/session/heartbeat` | Capture an intraday heartbeat |
| `POST /api/actions/session/close` | Generate an end-of-day digest |
| `POST /api/actions/incidents/{incident_id}/acknowledge` | Acknowledge an incident |
| `POST /api/config/proposals` | Write a config proposal artifact |

## Guard rules

- All write endpoints return `403` when web write mode is disabled.
- No endpoint may enable live trading.
- No endpoint may mutate the constitution, ADRs, or active runtime
  config in place.
- Replay and research endpoints are read-only even when write mode is
  enabled.
