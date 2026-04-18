---
id: CONTRACT-0006
title: Replay slippage API contract
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# Contract: Replay slippage API

## Read endpoints

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/api/platform/gate3/readiness` | Includes replay criterion and replay summary fields |
| `GET` | `/api/platform/gate3/replay-slippage/latest` | Latest replay-slippage summary |

## Write endpoints

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/api/actions/replay-slippage/generate` | Generate replay-slippage records and latest summary |

## Response notes

- read endpoints return sanitized payloads only
- write endpoints reject when web write mode is disabled
- replay generation is idempotent for the same execution inputs
