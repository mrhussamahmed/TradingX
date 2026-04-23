---
id: REPORT-0003
title: Headless control plane Wave 2 implementation plan adversarial review handoff
version: 1.0.0
status: draft
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-23
---

# Headless Control Plane Wave 2 Implementation Plan Adversarial Review Handoff

## Scope

This report prepares
`docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
for adversarial review. It covers planning only. No implementation code
is changed in this branch beyond documentation and index updates.

PR #7 merged the approved Wave 2 execution plan. This branch creates the
implementation-ready task breakdown that should be reviewed before code
execution begins.

## Files To Review

- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-review-handoff.md`
- `docs/INDEX.md`

## What This Plan Adds

The implementation plan turns approved `PLAN-0013` into ordered slices:

1. Baseline and dependency guard.
2. Postgres connection and Alembic migrations.
3. Repository contracts and Postgres repositories.
4. Outbox, checkpoints, and per-source readiness.
5. Legacy bridge/backfill and continuous tailer.
6. Domain projectors.
7. Postgres read model and domain router.
8. `/api/v1` read-route pivot and SSE parity.
9. Local stack and operator notes.

## Review-Sensitive Locks

### Governed writes stay provisional

The plan explicitly keeps `/api/v1/commands` and
`/api/v1/command-sessions` hidden from OpenAPI and returning provisional
errors until Wave 3. Command storage and command timeline read-side work
is allowed, but command intake is not promoted.

### Readiness is per source family

The implementation requires `domain_projection_source_status` as the
source of readiness truth. `domain_projection_status` is only a derived
summary, so one fresh source cannot hide a stale or missing source in a
multi-source domain.

### `/api/v1/events` remains late

The events route cannot pivot to Postgres until incidents, runtime,
validation, command read-side history, and market-data posture events are
all projected and parity-tested. The plan assigns validation timeline
events to `validation_projection` and command timeline events to
`commanding_projection`.

### Control posture stays versioned

Live config/env facts may be evaluated during a read only if the
evaluation persists a versioned `control_posture_snapshot`, structured
blockers, source status, monotonic `resource_version`, and
`state_fingerprint` before the API response is built.

### SSE follows polling sources

Implemented stream topics for `runtime`, `incidents`, `events`,
`control_posture`, `validation`, and `portfolio` must use the same
domain/source router as their polling routes. Topics not implemented in
Wave 2 must be explicitly rejected or legacy-routed until their polling
domains move with them. `commands` remains rejected as a stream topic
until Wave 3.

## Reviewer Focus Areas

Please challenge the plan on:

1. Whether the slice order permits any route pivot before storage,
   projection, source readiness, and router support exist.
2. Whether any task could introduce a second write surface or stable
   governed command route.
3. Whether the per-source readiness model is concrete enough for
   multi-source domains.
4. Whether `/api/v1/events` can still become partial or silently omit a
   required event family.
5. Whether read-time control-posture evaluation can bypass persisted
   version/fingerprint updates.
6. Whether stream parity or explicit rejection is testable for every
   architecture-declared topic that Wave 2 touches.
7. Whether the verification plan catches Postgres tests that skip or pass
   without exercising a real DSN.
8. Whether local legacy mode remains usable while Postgres mode is added.

## Known Deferrals

The following remain intentionally outside Wave 2 implementation:

- stable command-session lifecycle APIs
- stable command intake
- signed-write proof verification
- runtime-worker split
- lease epoch fencing
- job workers for replay, validation, portfolio analytics, and document
  generation
- frontend implementation

## Planning Verification

This planning branch should pass:

```bash
python3 scripts/check_index.py
```

Before Wave 2 implementation review, the implementation branch should
run the full command set listed in `PLAN-0014`, with Postgres-gated tests
using `TRADINGX_TEST_POSTGRES_DSN` when available.

## Review Outcome Requested

Please return:

1. P0/P1/P2 findings with exact file and line references.
2. Confirmation that the implementation sequence preserves approved
   Wave 2 review locks.
3. Confirmation that Wave 2 is ready to start coding once findings are
   addressed.
