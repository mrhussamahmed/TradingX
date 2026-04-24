---
id: PLAN-0017
title: Headless control plane Wave 2 Postgres outbox checkpoint and readiness plan
version: 1.0.0
status: draft
created: 2026-04-24
last_amended: 2026-04-24
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-24
---

# Headless Control Plane Wave 2 Postgres Outbox Checkpoint And Readiness Plan

## Purpose

This plan defines the next executable Wave 2 slice after `PLAN-0016`:
implement the previously contract-only Postgres boundaries for outbox
append, projection checkpoint load/save, and domain projection
source-status upsert/read.

The goal is to make projection progress resumable and source readiness
testable before legacy bridge, projector runner, read-router, or
`/api/v1` pivot work continues. This slice must not run projectors, pivot
routes to Postgres, or make legacy local mode database-dependent.

## Authority

- `PLAN-0013`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `PLAN-0014`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
- `PLAN-0015`: `docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-slice-plan.md`
- `PLAN-0016`: `docs/superpowers/plans/2026-04-24-wave2-postgres-repository-contracts-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `ADR-0025`: `docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md`

## Current State

Already complete:

1. Postgres schemas and migration helpers exist.
2. `tradingx.controlplane.repositories` defines Slice 3 contract-only
   protocols and dataclasses for outbox append, projection checkpoints,
   and projection source status.
3. `PostgresControlPlaneRepository` implements only Slice 2 read-side
   methods and explicitly does not implement the Slice 3 boundaries.
4. Real Postgres tests cover repository read ordering, pagination,
   public timeline union sources, redacted failures, and legacy
   no-Postgres startup.
5. `system.outbox_event`, `system.projection_checkpoint`,
   `system.domain_projection_source_status`, and
   `system.domain_projection_status` exist in the initial migration.

Still missing before bridge/projector/router work:

1. SQL-backed outbox append with dedupe conflict handling.
2. SQL-backed projection checkpoint load/save.
3. SQL-backed source-status upsert/read by source natural key.
4. Pure readiness aggregation rules from source-status rows.
5. Derived `domain_projection_status` writes from source-status
   authority.
6. Transaction semantics proving failed projection batches do not
   advance checkpoints.

## Non-Negotiable Locks

1. Legacy local mode remains the default and must not connect to
   Postgres during config load, app creation, default local web
   component construction, default startup wiring, or legacy route
   handling.
2. No `/api/v1` route pivots to Postgres in this slice.
3. No bridge, tailer, backfill command, projector runner, or
   `PostgresControlPlaneReadModel` is introduced.
4. No public helper POST route is introduced for incidents, replays,
   acknowledgement, command sessions, source status, checkpoints, or
   outbox events.
5. The Slice 2 read repository must remain read-side only. Slice 3
   write/progress behavior belongs in a separate projection-state
   repository implementation.
6. `system.domain_projection_source_status` is the readiness authority.
   `system.domain_projection_status` is only a derived diagnostic
   summary.
7. `system.outbox_event` remains an internal projector input. Public
   event timeline reads must not consume it.
8. Raw DSNs and passwords must stay out of exceptions, reprs, args,
   chained exceptions, logs, and test output.
9. Postgres-gated tests must skip explicitly without
   `TRADINGX_TEST_POSTGRES_DSN`; they must not pass by exercising only
   fakes.

## Out Of Scope

- legacy source adapters
- bridge, backfill, or tailer commands
- projector runners
- domain read-model projectors
- `PostgresControlPlaneReadModel`
- `/api/v1` route pivoting
- SSE parity
- governed command intake
- frontend changes
- local compose stack
- cloud deployment

## Architecture Approach

Keep the new behavior separate from Slice 2 read repositories:

- `src/tradingx/controlplane/repositories.py` continues to own public
  protocols, value dataclasses, and repository error types.
- `src/tradingx/controlplane/projections.py` owns pure projection-state
  readiness rules, source requirements, and derived summary shapes.
- `src/tradingx/persistence/repositories/projection_state.py` owns the
  Postgres implementation for outbox append, checkpoint load/save,
  source-status upsert/read, and derived status persistence.
- `PostgresControlPlaneRepository` remains read-side only and must not
  implement `OutboxAppendBoundary`, `ProjectionCheckpointBoundary`, or
  `ProjectionSourceStatusBoundary`.

The implementation should use SQLAlchemy Core text statements and
explicit transactions. Do not add an ORM layer.

## Required Behavior

### Outbox Append

1. Append writes to `system.outbox_event`.
2. `dedupe_key` is the database conflict key.
3. First insert returns the new `outbox_event_id`.
4. Repeating the same logical append with the same `dedupe_key` returns
   the existing `outbox_event_id` and does not add a row.
5. Reusing a `dedupe_key` with conflicting `aggregate_type`,
   `aggregate_id`, `event_type`, `event_version`, `occurred_at_utc`, or
   payload fingerprint raises a domain conflict error with redacted
   diagnostics.
6. `published_at_utc` remains `NULL`; publishing is not implemented in
   this slice.
7. The method does not update public timeline tables and does not make
   `/api/v1/events` read from the outbox.

### Projection Checkpoints

1. Checkpoints are keyed by `projection_name`.
2. Missing checkpoints return `None`.
3. Save uses an upsert on `system.projection_checkpoint`.
4. Checkpoint records include `last_outbox_event_id`,
   `last_processed_at_utc`, `source_watermark`,
   `last_source_observed_at_utc`, `lag_seconds`, `status`, and
   `metadata_json`.
5. Batch work and checkpoint advancement must be transaction-compatible:
   tests must prove a simulated batch failure rolls back checkpoint
   advancement.
6. The projection-state repository must expose a `transaction()` context
   manager that yields a transaction-bound repository view. Writes made
   through that view commit only on normal exit and roll back on
   exception. This helper exists only to prove atomicity for later
   projectors; it must not implement projector orchestration.

### Source Status And Readiness

1. Source status is keyed by `(domain_name, source_family,
   source_identity)`.
2. Upsert writes to `system.domain_projection_source_status`.
3. Read methods can fetch one source status by key and list statuses by
   domain.
4. A source row is ready only when:
   - the row exists
   - `ready_for_postgres` is true
   - `projected_watermark` equals `source_watermark` when
     `source_watermark` is present
   - mutable sources have a non-null `checked_at_utc` within the required
     freshness window
   - `lag_seconds` is present and no greater than the source requirement
     when a max lag is configured
5. A domain is ready only when every required source identity is ready.
6. Missing, stale, unprojected, lagging, or explicitly not-ready source
   rows block the domain.
7. Derived `domain_projection_status` rows must summarize readiness, name
   blocker reasons in metadata, and must not become the readiness
   authority for routers.

## Implementation Tasks

### Task 0: Baseline Verification

Run before edits:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_repository_contracts.py tests/integration/test_controlplane_postgres_repositories.py tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_repository_contracts.py tests/unit/test_persistence_namespace.py tests/unit/test_postgres_config.py tests/unit/test_web_app.py::test_legacy_local_web_paths_do_not_construct_postgres tests/contract/test_local_web_app_api_contract.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_repositories.py -q
python3 scripts/check_index.py
git diff --check
```

If a baseline failure exists, stop and record it separately.

### Task 1: Add Test-First Projection-State Contract Coverage

Create:

- `tests/unit/test_controlplane_projection_state_contracts.py`

The first tests must prove:

1. Slice 3 dataclasses expose the natural keys named in `PLAN-0016`.
2. outbox append request validation rejects empty aggregate IDs,
   event types, and dedupe keys.
3. checkpoint records are keyed by `projection_name`.
4. source-status records are keyed by `(domain_name, source_family,
   source_identity)`.
5. readiness aggregation treats missing, stale, unprojected, lagging, and
   explicitly not-ready sources as blockers.
6. `domain_projection_status` is derived from source statuses and remains
   non-authoritative for routers.
7. `PostgresControlPlaneRepository` remains read-side only.
8. repository errors redact `str`, `repr`, `args`, `__cause__`, and
   `__context__`.

Expected red state: imports or assertions fail because projection-state
contracts and readiness helpers do not exist yet.

### Task 2: Add Projection-State Contracts And Readiness Rules

Update:

- `src/tradingx/controlplane/repositories.py`

Create:

- `src/tradingx/controlplane/projections.py`

Define:

- outbox append conflict error type
- validated outbox append request helper that rejects empty aggregate
  IDs, event types, dedupe keys, and non-positive event versions
- source-status key helpers
- `ProjectionSourceRequirement`
- `ProjectionReadinessBlocker`
- `ProjectionReadinessReport`
- pure readiness evaluation function
- derived `ProjectionStatusSummary` construction from readiness reports

Keep these modules independent of SQLAlchemy and FastAPI.

Checks:

```bash
uv run pytest tests/unit/test_controlplane_projection_state_contracts.py -q
uv run mypy src/tradingx
```

### Task 3: Add Postgres Projection-State Repository

Create:

- `src/tradingx/persistence/repositories/projection_state.py`

Update:

- `src/tradingx/persistence/repositories/__init__.py`

Implement:

1. `PostgresProjectionStateRepository`
2. outbox append with database `dedupe_key` conflict handling
3. checkpoint load/save upserts
4. source-status upsert/read/list methods
5. derived `domain_projection_status` upsert from readiness reports
6. `transaction()` context manager yielding a transaction-bound
   repository view, with rollback on exception
7. redacted exception wrapping consistent with Slice 2 repositories

Do not add bridge/tailer/projector runners. Do not add FastAPI wiring.
Do not add these methods to `PostgresControlPlaneRepository`.

### Task 4: Add Postgres-Gated Projection-State Tests

Create:

- `tests/integration/test_controlplane_postgres_projection_state.py`

The tests must:

1. skip explicitly without `TRADINGX_TEST_POSTGRES_DSN`
2. reset only the guarded `tradingx_test` database through existing
   helpers
3. run package-local migrations
4. prove outbox append is idempotent for identical `dedupe_key` reuse
5. prove conflicting `dedupe_key` reuse raises a redacted conflict error
6. prove `published_at_utc` remains `NULL`
7. prove checkpoint load returns `None` before save
8. prove checkpoint save upserts the expected fields
9. prove simulated batch failure rolls back checkpoint advancement
10. prove source-status upsert/read/list by natural key
11. prove derived domain readiness blocks on missing, stale, unprojected,
    lagging, and explicitly not-ready source statuses
12. prove derived `domain_projection_status` metadata names blocker
    reasons and is not used as router authority
13. prove `PostgresControlPlaneRepository` still does not implement the
    Slice 3 boundaries
14. prove storage failures redact `str`, `repr`, `args`, `__cause__`,
    and `__context__`

Run locally with this workstation's DSN:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_projection_state.py -q
```

### Task 5: Preserve Legacy And Web Contracts

Re-run:

```bash
uv run pytest tests/unit/test_persistence_namespace.py tests/unit/test_postgres_config.py -q
uv run pytest tests/unit/test_web_app.py::test_legacy_local_web_paths_do_not_construct_postgres -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
```

Extend the no-Postgres regression to monkeypatch
`PostgresProjectionStateRepository` construction to fail loudly, in
addition to the existing engine and read-repository monkeypatches.
Legacy app creation, default local web component construction, default
startup wiring, and representative read routes must still pass.

### Task 6: Documentation And Index Updates

Update docs only if new public local commands or environment variables
are introduced. This slice should not document Postgres as the default
store.

## Verification Gate

Focused verification:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_repository_contracts.py tests/unit/test_controlplane_projection_state_contracts.py tests/integration/test_controlplane_postgres_repositories.py tests/integration/test_controlplane_postgres_projection_state.py tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_repository_contracts.py tests/unit/test_controlplane_projection_state_contracts.py -q
uv run pytest tests/unit/test_postgres_connection.py tests/unit/test_postgres_migration_config.py -q
uv run pytest tests/unit/test_persistence_namespace.py tests/unit/test_postgres_config.py tests/unit/test_web_app.py::test_legacy_local_web_paths_do_not_construct_postgres -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
python3 scripts/check_index.py
git diff --check
```

Postgres-gated verification when a DSN is available:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_repositories.py tests/integration/test_controlplane_postgres_projection_state.py -q
```

CI note: remote GitHub Actions may remain blocked until the repository
owner resolves the account billing/spending-limit issue. Do not treat a
runner-not-started CI failure as repository test evidence.

## Adversarial Review Checklist

Reviewer should challenge:

1. whether the plan accidentally implements bridge, projector runner, or
   `/api/v1` router behavior
2. whether outbox append idempotency handles conflicting dedupe reuse
   safely
3. whether checkpoint advancement is transaction-compatible with later
   projector batches
4. whether a failed batch can advance a checkpoint
5. whether `domain_projection_source_status` remains the readiness
   authority
6. whether `domain_projection_status` can be mistaken for router
   readiness authority
7. whether missing, stale, unprojected, lagging, and not-ready source
   rows all block readiness
8. whether source freshness semantics distinguish mutable from immutable
   sources
9. whether source identity natural keys are explicit enough for Slice 4
   adapters
10. whether `system.outbox_event` leaks into public timeline behavior
11. whether the Slice 2 read repository accidentally gains write/progress
    methods
12. whether raw DSNs or passwords can leak through repository exceptions
13. whether fake tests could pass while real SQL behavior is broken
14. whether legacy startup can accidentally instantiate the new
    projection-state repository

## Definition Of Done

This slice is done when:

1. pure projection-state readiness contracts and tests exist
2. `PostgresProjectionStateRepository` implements outbox append,
   checkpoint load/save, source-status upsert/read/list, and derived
   status persistence
3. outbox append is idempotent and rejects conflicting dedupe reuse
4. checkpoint save/load and rollback behavior are integration-tested
   against real Postgres
5. source-readiness aggregation is integration-tested against real
   Postgres for missing, stale, unprojected, lagging, and not-ready
   sources
6. `PostgresControlPlaneRepository` remains read-side only
7. no `/api/v1` route pivots to Postgres
8. mandatory legacy no-Postgres startup and route regressions pass
9. Postgres connection, migration, repository, and projection-state gates
   pass
10. docs/index validation passes
11. Postgres-gated tests skip explicitly without a DSN and pass with a
   real `TRADINGX_TEST_POSTGRES_DSN`

Only after this definition is met should Wave 2 continue into legacy
bridge, projector runner, read-router, or `/api/v1` pivot work.
