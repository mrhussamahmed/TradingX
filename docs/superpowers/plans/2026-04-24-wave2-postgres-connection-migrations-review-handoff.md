---
id: REPORT-0005
title: Headless control plane Wave 2 Postgres connection and migrations plan review handoff
version: 1.0.0
status: draft
created: 2026-04-24
last_amended: 2026-04-24
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-24
---

# Headless Control Plane Wave 2 Postgres Connection And Migrations Plan Review Handoff

## Scope

This handoff prepares `PLAN-0015` for adversarial review before code
execution starts.

It covers planning only. The implementation branch should use this
handoff to challenge the next Wave 2 storage-foundation slice: Postgres
dependencies, explicit connection helpers, Alembic migration structure,
initial control-plane schemas/tables, and real-DSN migration tests.

## Teammate Review Outcome

The adversarial review returned a "proceed after doc tweaks"
recommendation, not an unconditional green light.

Required plan tightenings before implementation:

1. destructive cleanup must fail closed; database-name substring matching is
   not sufficient
2. a real `TRADINGX_TEST_POSTGRES_DSN` migration run is mandatory before
   closing this slice
3. Alembic downgrade, downgrade-to-base inspection, and re-upgrade
   verification must be explicit
4. Alembic version-table location and test-reset semantics must be concrete
   enough to prevent false-positive `upgrade(head)` runs
5. the initial migration must use the `PLAN-0013` table names directly
   rather than renamed or collapsed substitutes

`PLAN-0015` has been amended with those requirements. Implementation should
use the amended plan, not the original review draft.

## Files To Review

- `docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-slice-plan.md`
- `docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-review-handoff.md`
- `docs/INDEX.md`

## Why This Slice Exists

`main` already has the Wave 2 prerequisite foundation:

1. legacy-safe control-plane config
2. redacted Postgres DSN summaries
3. `tradingx.persistence` converted into a package
4. a narrow `postgres.py` helper module with DSN redaction only

The next implementation step in `PLAN-0014` is not repositories or route
pivots yet. It is the durable database foundation that those later
slices depend on.

## What PLAN-0015 Schedules

1. Add `sqlalchemy`, `psycopg[binary]`, and `alembic`.
2. Add explicit sync Postgres engine/session helpers with timeout,
   pool-pre-ping, missing-DSN, and redacted-diagnostic behavior.
3. Add package-local Alembic configuration under
   `src/tradingx/persistence/migrations/`.
4. Add the first migration for the nine Wave 2 schemas:
   `access`, `commanding`, `runtime`, `incidents`, `portfolio`,
   `validation`, `investigations`, `documents`, and `system`.
5. Create `PLAN-0013`-named table skeletons for command/session state,
   runtime posture, incidents, portfolio, validation,
   replay/investigation, documents, outbox, checkpoints, and source
   readiness.
6. Add DSN-gated integration tests that exercise the real migration when
   `TRADINGX_TEST_POSTGRES_DSN` is present and skip explicitly when it is
   absent.
7. Keep legacy local mode and existing `/api/v1` read contracts
   unchanged.

## Review-Sensitive Locks

### Legacy local mode must stay database-free

The plan says engine creation is explicit and must not happen during
`TradingConfig` construction or ordinary legacy app startup. Please
challenge whether any proposed helper shape could still import or
connect too early.

### No route or write-surface promotion

This is storage foundation only. It must not pivot `/api/v1` routes,
expose stable `/api/v1/commands`, expose stable command sessions, or add
helper POST routes for incidents/replays/acknowledgements.

### Test cleanup must be fail-closed

The plan allows destructive schema cleanup only when the parsed database
name is exactly `tradingx_test` or
`TRADINGX_ALLOW_POSTGRES_TEST_RESET=true`. Please challenge whether that is
sufficient and whether the managed schema list is tight enough.

### Migration tests must not fake success

Postgres-gated tests must skip loudly without a DSN and must exercise a
real database before this slice is closed. Please challenge any path where
tests could pass by only inspecting Python objects or Alembic files.

### Migration reversibility must be proven

The implementation must prove `upgrade(head)`, idempotent re-upgrade,
`downgrade(base)`, catalog inspection after downgrade, and final
`upgrade(head)` behavior against a real Postgres database.

### Table skeletons should not force a rewrite later

The migration table inventory is intentionally broad but skeletal.
Please challenge missing columns/constraints that would block the next
repository, outbox, source-readiness, or Wave 3 command-precondition
slices. Also challenge any table name that drifts from `PLAN-0013`, since
renaming storage tables later would force avoidable migration churn.

### Secrets must remain redacted

The plan requires raw DSNs/passwords to stay out of summaries, logs,
exceptions, and test output. Please challenge `repr`, exception, and
Alembic-output paths, not only `to_safe_summary()`.

## Known Deferrals

Intentionally not in this slice:

- repository protocols and repository implementations
- outbox insert/upsert helper behavior
- projection checkpoint logic beyond table creation
- domain/source readiness aggregation beyond table creation
- legacy bridge/backfill/tailer
- projector runner
- Postgres read model and domain router
- `/api/v1` route pivots
- SSE parity
- frontend changes
- local compose stack

## Reviewer Prompt

Use this prompt with the teammate reviewer:

```text
Please adversarially review PLAN-0015 for the next TradingX headless
control-plane Wave 2 implementation slice.

Focus on whether the plan is safe and complete enough to execute before
any SQL or connection code is written. Return P0/P1/P2 findings with
file and line references. In particular, challenge legacy-mode
Postgres coupling, secret leakage, destructive integration-test cleanup,
false-positive DSN-gated tests, missing table constraints, Alembic
package usability, downgrade/re-upgrade behavior, Alembic version-table
reset semantics, and any accidental promotion of governed writes or /api/v1
route pivots before Wave 3.

Files:
- docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-slice-plan.md
- docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-review-handoff.md
- docs/INDEX.md
```

## Review Outcome Requested

Please return:

1. P0/P1/P2 findings with exact file and line references.
2. Confirmation or rejection that `PLAN-0015` is the correct next
   executable slice after `REPORT-0004`.
3. Confirmation or rejection that the schema/table inventory is
   sufficient for the next repository/outbox/projector slices.
4. Confirmation or rejection that the test plan prevents both unsafe
   cleanup and false-positive Postgres coverage.
5. Any concrete edits required before implementation begins.
