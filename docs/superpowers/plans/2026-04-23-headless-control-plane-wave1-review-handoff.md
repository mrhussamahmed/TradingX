---
id: REPORT-0001
title: Headless control plane Wave 1 adversarial review handoff
version: 1.0.0
status: draft
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-23
---

# Headless Control Plane Wave 1 Adversarial Review Handoff

## Scope

This handoff covers the first implementation slice from
[`2026-04-23-headless-control-plane-implementation-plan.md`](./2026-04-23-headless-control-plane-implementation-plan.md):
canonical read-side `/api/v1` control-plane routes inside the existing
FastAPI surface, plus the Wave 1 realtime scaffold.

## Files Changed

- `src/tradingx/web/app.py`
- `tests/contract/test_local_web_app_api_contract.py`

## What Was Implemented

### 1. Canonical read-side `/api/v1` routes

Added canonical read-side routes with a common response envelope:

- `GET /api/v1/control-posture`
- `GET /api/v1/runtime`
- `GET /api/v1/runtime/heartbeats`
- `GET /api/v1/stream`
- `GET /api/v1/incidents`
- `GET /api/v1/events`
- `GET /api/v1/portfolio`
- `GET /api/v1/portfolio/positions`
- `GET /api/v1/portfolio/performance`
- `GET /api/v1/portfolio/execution-quality`
- `GET /api/v1/validation/readiness`
- `GET /api/v1/validation/candidates/{candidate_id}/criteria`
- `GET /api/v1/validation/reports`
- `GET /api/v1/validation/pbo-reports`
- `GET /api/v1/investigations`
- `GET /api/v1/replays/{replay_id}`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`

Every canonical route returns:

```json
{
  "request_id": "req_...",
  "generated_at": "2026-04-23T15:00:00Z",
  "data": {}
}
```

### 2. Read-side compatibility seam

The new route layer intentionally tolerates both:

- existing dataclass-backed read-model results
- dict-backed legacy/fixture results

This was necessary to keep Wave 1 backward-compatible while the repo
still straddles multiple response shapes.

### 3. Canonical SSE scaffold

Added `GET /api/v1/stream` as the Wave 1 canonical multiplexed SSE
endpoint.

Current supported topics:

- `control_posture`
- `runtime`
- `incidents`
- `events`
- `commands`

Current behavior is intentionally a snapshot-style SSE scaffold rather
than a long-lived production fanout service. The route validates topic
names and emits a structured error event for unknown topics.

### 4. Risk mitigation for unstable governed writes

To avoid frontend/codegen drift before Wave 3 hardens the write path:

- `/api/v1/commands` exists only as a **provisional** hidden route
- `/api/v1/command-sessions` exists only as a **provisional** hidden
  route
- both return `503`
- both carry `X-TradingX-Stability: provisional`
- both are excluded from OpenAPI via `include_in_schema=False`

This is the main implementation-time mitigation for the approved review
risk: Wave 1 should expose a stable read-side control-plane surface
without accidentally advertising governed writes as ready.

## Explicit Risk Mitigations

### Governed write drift

Mitigation:

- provisional write stubs are hidden from OpenAPI and return `503`
- no frontend-facing stable write contract is exposed yet
- legacy write routes remain in place, but the new `/api/v1` write paths
  are clearly non-integratable until Wave 3

### Realtime API omission

Mitigation:

- `GET /api/v1/stream` is implemented in Wave 1
- contract tests assert valid topic streaming and invalid-topic failure

### Legacy split-brain during transition

Mitigation:

- Wave 1 routes are adapters over the current read model rather than
  direct artifact parsing from the frontend
- the compatibility seam accepts both dict and dataclass payloads

## Intentional Deferrals

The following are **not** claimed complete in this slice and should not
be treated as blockers unless the plan required them in Wave 1:

- stable `/api/v1/commands` semantics
- stable `/api/v1/command-sessions` semantics
- signed command-session lifecycle
- mutation preconditions
- Postgres operational store
- outbox/projection layer
- worker/runtime split
- job workers for replay/validation/analytics

Those remain scheduled for later waves in the approved implementation
plan.

## Verification Run

Commands executed:

```bash
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
uv run ruff check src/tradingx/web/app.py tests/contract/test_local_web_app_api_contract.py
```

Result:

- both commands passed

## Reviewer Focus Areas

Please review this slice for:

1. Whether the canonical `/api/v1` envelopes and route shapes are
   coherent enough for frontend targeting.
2. Whether `GET /api/v1/control-posture` is sufficiently detailed for
   remediation UX at this wave.
3. Whether the snapshot-style SSE scaffold is an acceptable Wave 1
   implementation of the canonical realtime seam.
4. Whether the provisional governed-write guardrails are strong enough
   to prevent accidental frontend/codegen adoption before Wave 3.
5. Whether any canonical read-side route is still too tightly coupled to
   legacy local-only assumptions.
