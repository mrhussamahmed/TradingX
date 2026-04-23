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
5. Legacy bridge/backfill and continuous tailing from current artifact
   directories, operator-control files, live config/env posture inputs,
   market-data posture inputs, config weight snapshots, ops baselines,
   and SQLite data.
6. Outbox-driven projectors with unique dedupe constraints, checkpoint
   resume behavior, per-source readiness rows, and domain readiness
   aggregation.
7. Domain-by-domain `/api/v1` read-route pivoting to Postgres mode
   through an explicit hybrid read router.
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
stable in Wave 3. It also requires stream topics to use the same
per-domain source router as polling reads, so a domain cannot pivot its
REST route to Postgres while realtime still emits legacy snapshots. This
now covers the architecture-declared `runtime`, `incidents`, `events`,
`control_posture`, `validation`, and `portfolio` topics; topics not
implemented in Wave 2 must remain explicitly rejected or legacy-routed
until their polling domains can move with them.

### No split-brain history

The plan requires each `/api/v1` route to pivot only after the current
projection, matching historical bridge/backfill, continuous bridge or
dual-write freshness, and per-source readiness rows all pass. The
domain-level readiness row is a derived summary and cannot go green when
any required source family is stale or missing. The legacy bridge must be
idempotent, and repeated or concurrent runs must not duplicate rows
because `system.outbox_event(dedupe_key)` is now required to be unique at
the database layer.

### Per-domain pivot mechanism

The plan now requires a hybrid read router and per-domain store map
instead of relying on a binary legacy/Postgres app switch. This makes the
documented pivot order executable, gives rollback a specific mechanism,
and prevents stale Postgres reads when readiness is false.

### Events pivot only after all timeline families exist

`GET /api/v1/events` is intentionally late in the pivot order. It cannot
move to Postgres until incidents, runtime, validation, command read-side
history, and market-data posture event families are all projected and
parity-tested, so the canonical timeline does not silently drop deferred
families. The projector inventory now assigns validation timeline events
to `validation_projection` and command timeline events to
`commanding_projection` while keeping command writes deferred.

### Control posture stays fail-closed

The plan requires missing governance approval to remain a first-class
blocker in Postgres snapshots and API responses. It also calls out
contradictory nested posture truth as an adversarial-review target.
Control-posture blockers must be queryable as structured rows or arrays,
not trapped only inside `payload_json`. Live config/env facts such as
broker credential presence, config live enablement, live opt-in,
write-signing configuration, dry-run state, and kill-switch state must be
bridged or evaluated by the Postgres-backed read model with their own
freshness source status. If those facts are evaluated during a read, the
evaluation must persist a versioned `control_posture_snapshot`, blocker
rows, source status, monotonic `resource_version`, and
`state_fingerprint` before the API response is built.

### Wave 3 preconditions have storage hooks

The plan now requires versioned command targets, including incidents,
runtime state, control posture, and acknowledgements, to expose
`resource_version` and `state_fingerprint` before Wave 3 promotes
mutation preconditions.

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
2. Whether the route pivot order and hybrid router prevent historical or
   realtime split-brain in Command Center, Mission Control, validation,
   replay, and portfolio views, especially for `/api/v1/events`.
3. Whether backfill dedupe, unique outbox constraints, per-source
   continuous bridge watermarks, and checkpoint rules are precise enough
   to make migration idempotent.
4. Whether Postgres mode can be tested locally and in CI without making
   all legacy-mode tests database-dependent.
5. Whether any planned endpoint or projector could leak artifact-shaped
   payloads back to frontend consumers.
6. Whether the plan leaves enough explicit verification around
   `/api/v1/stream`, control-posture truth, and provisional write
   guardrails.
7. Whether every current Wave 1 read-model source is bridged or the
   corresponding domain remains explicitly on legacy reads.
8. Whether a domain can be marked ready while one of its required source
   families is stale or missing.
9. Whether read-time control-posture evaluation can bypass persisted
   version/fingerprint updates.

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
