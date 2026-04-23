---
id: REPORT-0002
title: Headless control plane Wave 2 planning adversarial review handoff
version: 1.0.0
status: draft
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-23
---

# Headless Control Plane Wave 2 Planning Adversarial Review Handoff

## Scope

This report prepares
`docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
for adversarial review. It covers planning only. No implementation code
is changed in this branch beyond documentation and index updates.

Wave 2 is the Postgres operational store and outbox/projection layer
for the approved headless control plane. It follows Wave 1, which added
canonical `/api/v1` read routes and kept governed writes provisional.

## Files To Review

- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-review-handoff.md`
- `docs/INDEX.md`

## What The Plan Schedules

The plan schedules:

1. Postgres configuration, connection management, and local bootstrap.
2. Alembic migrations for the architecture-approved schemas:
   `access`, `commanding`, `runtime`, `incidents`, `portfolio`,
   `validation`, `investigations`, `documents`, and `system`.
3. Canonical tables for command/session summaries, runtime state,
   incidents, portfolio analytics, validation metadata, replay indexes,
   documents, outbox events, and projection checkpoints.
4. Postgres repository boundaries for Wave 1 read routes.
5. Legacy bridge/backfill from current artifact directories,
   operator-control files, and SQLite OMS journal data.
6. Outbox-driven projectors with checkpoint resume behavior.
7. Domain-by-domain `/api/v1` read-route pivoting to Postgres mode.
8. Local Postgres dev support while preserving the current legacy local
   path.

## Explicit Mitigations

### Stable writes are still blocked

The plan explicitly keeps `/api/v1/commands` and
`/api/v1/command-sessions` hidden, provisional, and excluded from
OpenAPI until Wave 3. Wave 2 may create storage tables for command and
session summaries, but it does not promote stable command intake,
session minting, signatures, or mutation preconditions.

### No command-topic SSE drift

The plan repeats the Wave 1 guardrail that `GET /api/v1/stream` must
not expose a `commands` topic until the canonical command lifecycle is
stable in Wave 3.

### No split-brain history

The plan requires each `/api/v1` route to pivot only after both the
current projection and matching historical bridge/backfill exist. The
legacy bridge must be idempotent, and repeated runs must not duplicate
rows.

### Control posture stays fail-closed

The plan requires missing governance approval to remain a first-class
blocker in Postgres snapshots and API responses. It also calls out
contradictory nested posture truth as an adversarial-review target.

### No helper write routes

Incident acknowledgement, replay creation, and command-session lifecycle
are storage-only/deferred in Wave 2. The plan does not schedule helper
POST routes that could become a second mutation model.

### Local development remains practical

The plan adds Postgres mode and local bootstrap steps, while preserving
legacy mode as the default local path until a developer explicitly opts
into Postgres.

## Reviewer Focus Areas

Please challenge the plan on:

1. Whether the table set is sufficient for Wave 3 command-session and
   mutation-precondition work without exposing writes early.
2. Whether the route pivot order prevents historical split-brain in
   Command Center, Mission Control, validation, replay, and portfolio
   views.
3. Whether backfill dedupe and checkpoint rules are precise enough to
   make migration idempotent.
4. Whether Postgres mode can be tested locally and in CI without making
   all legacy-mode tests database-dependent.
5. Whether any planned endpoint or projector could leak artifact-shaped
   payloads back to frontend consumers.
6. Whether the plan leaves enough explicit verification around
   `/api/v1/stream`, control-posture truth, and provisional write
   guardrails.

## Known Deferrals

The following remain intentionally outside Wave 2:

- stable command-session lifecycle APIs
- stable command intake and command event timeline APIs
- signed-write proof verification
- runtime-worker split
- lease epoch fencing
- job workers for replay, validation, portfolio analytics, and document
  generation
- frontend implementation

Those deferrals match the approved broad plan and should not be treated
as Wave 2 blockers unless the reviewer finds that Wave 2 accidentally
depends on one of them.

## Planning Verification

The planning branch should pass:

```bash
python3 scripts/check_index.py
```

The implementation branch created after this plan should additionally
run the verification listed in `PLAN-0013`, including Postgres-gated
integration tests when `TRADINGX_TEST_POSTGRES_DSN` is available.

## Review Outcome Requested

Please return:

1. P0/P1/P2 findings with exact file and line references.
2. Confirmation that the plan preserves Wave 1 guardrails around
   provisional writes and stable read-side contracts.
3. Confirmation that Wave 2 has enough storage, bridge, projection, and
   verification detail to start implementation without another planning
   round.
