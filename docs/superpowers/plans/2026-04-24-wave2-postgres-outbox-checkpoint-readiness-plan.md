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
3. The repository generates `outbox_event_id` as a UUID4 string unless a
   deterministic test ID provider is injected.
4. The repository sets `created_at_utc` from an injected clock, defaulting
   to the current UTC time. Request callers provide `occurred_at_utc`,
   not `created_at_utc`.
5. First insert returns the new `outbox_event_id`.
6. Repeating the same logical append with the same `dedupe_key` returns
   the existing `outbox_event_id` and does not add a row.
7. Reusing a `dedupe_key` with conflicting `aggregate_type`,
   `aggregate_id`, `event_type`, `event_version`, `occurred_at_utc`, or
   `payload_json` raises a domain conflict error with redacted
   diagnostics.
8. Payload conflict comparison uses Postgres JSONB equality between the
   existing `payload_json` and the requested payload. This slice must not
   add a `payload_fingerprint` column or silently compare a non-persisted
   hash as the source of truth.
9. `published_at_utc` remains `NULL`; publishing is not implemented in
   this slice.
10. The method does not update public timeline tables and does not make
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
   advancement, outbox append, source-status upsert, and derived
   status write together.
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
4. `ProjectionSourceStatusBoundary` must add
   `list_projection_source_statuses(domain_name: str)` as a stable
   protocol method. This is not an implementation-only helper.
5. A source row is ready only when:
   - the row exists
   - `ready_for_postgres` is true
   - `projected_watermark` equals `source_watermark` when
     `source_watermark` is present
   - mutable sources have a non-null `checked_at_utc` within the required
     freshness window
   - `lag_seconds` is present and no greater than the source requirement
     when a max lag is configured
6. A domain is ready only when every required source identity is ready.
7. Missing, stale, unprojected, lagging, initial-import-incomplete,
   inactive-write-path, missing outbox dedupe constraint, or explicitly
   not-ready source rows block the domain.
8. Derived `domain_projection_status` rows must summarize readiness, name
   blocker reasons in metadata, and must not become the readiness
   authority for routers.

### Required Source Registry

`ProjectionSourceRequirement` is the authoritative required-source
registry for readiness evaluation. It must live in
`src/tradingx/controlplane/projections.py` and be passed explicitly to
readiness evaluation. A domain with no registered requirements is not
ready; it returns a `missing_requirements` blocker rather than passing by
vacuous truth.

Each requirement must name:

1. `domain_name`
2. `source_family`
3. `source_identity`
4. whether the source is mutable
5. optional `max_freshness_seconds`
6. optional `max_lag_seconds`
7. whether initial import completion is required
8. whether active bridge or dual-write evidence is required

Source-status metadata must supply these readiness facts when the
requirement asks for them:

- `initial_import_complete: true`
- `write_path: "active_bridge"` or `write_path: "dual_write"` for
  mutable sources that require an active write path

Readiness evaluation must also receive an
`outbox_dedupe_constraint_present` boolean. If it is false, every domain
is blocked with `outbox_dedupe_constraint_missing`, because PLAN-0013
requires the outbox dedupe constraint before Postgres routing can be
trusted.

### Derived Domain Status Mapping

`system.domain_projection_status` is a diagnostic summary derived from
readiness reports. It must be written with this mapping:

| Column | Required mapping |
| --- | --- |
| `domain_name` | `ProjectionReadinessReport.domain_name`. |
| `target_store` | Literal `postgres`. |
| `bridge_status` | `not_required` when no requirement needs active bridge or dual-write evidence; `ready` when all such requirements have valid write-path metadata; otherwise `blocked`. |
| `projection_status` | `ready` when the report is ready; otherwise the highest-priority blocker category using this order: `missing_requirements`, `outbox_dedupe_constraint_missing`, `missing_sources`, `initial_import_incomplete`, `write_path_inactive`, `unprojected_sources`, `stale_sources`, `lagging_sources`, `not_ready_sources`, then `blocked`. |
| `source_watermark` | For one required source, that source's `projected_watermark`; for multiple sources, a deterministic JSON string of sorted `source_family/source_identity/projected_watermark` entries; `NULL` when no source has a projected watermark. |
| `last_projected_outbox_event_id` | The newest non-null source-status metadata field named `last_projected_outbox_event_id`, ordered by `checked_at_utc DESC`, then `source_family ASC`, then `source_identity ASC`; `NULL` when absent. |
| `lag_seconds` | The maximum non-null `lag_seconds` across required sources; `NULL` when no required source reports lag. |
| `ready_for_postgres` | `ProjectionReadinessReport.ready_for_postgres`. |
| `checked_at_utc` | The readiness evaluation timestamp from the injected clock, not an arbitrary source row timestamp. |
| `metadata_json` | Includes `authoritative: false`, blocker codes, requirement count, ready source count, source registry version, per-source status summaries, and any watermarks summarized into `source_watermark`. |

The implementation must not use arbitrary constants for these fields.
Tests must assert the mapping for both ready and blocked reports.

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
   event types, dedupe keys, and non-positive event versions.
3. outbox append contract names repository-owned `outbox_event_id` and
   `created_at_utc` generation.
4. checkpoint records are keyed by `projection_name`.
5. source-status records are keyed by `(domain_name, source_family,
   source_identity)`.
6. `ProjectionSourceStatusBoundary` includes
   `list_projection_source_statuses(domain_name: str)`.
7. `ProjectionSourceRequirement` is the authoritative source registry,
   and an empty requirement set blocks readiness.
8. readiness aggregation treats missing, stale, unprojected, lagging,
   initial-import-incomplete, inactive-write-path, missing outbox dedupe
   constraint, and explicitly not-ready sources as blockers.
9. derived status field mapping is deterministic and follows the table
   above.
10. `domain_projection_status` is derived from source statuses and remains
   non-authoritative for routers.
11. `PostgresControlPlaneRepository` remains read-side only.
12. repository errors redact `str`, `repr`, `args`, `__cause__`, and
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
- authoritative required-source registry helpers with explicit
  empty-registry blocking semantics
- `ProjectionReadinessBlocker`
- `ProjectionReadinessReport`
- pure readiness evaluation function
- derived `ProjectionStatusSummary` construction from readiness reports
  using the field mapping above

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
2. outbox append with repository-generated `outbox_event_id`,
   repository-generated `created_at_utc`, database `dedupe_key` conflict
   handling, and JSONB equality conflict comparison
3. checkpoint load/save upserts
4. source-status upsert/read/list methods, including the stable
   `list_projection_source_statuses(domain_name)` protocol method
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
5. prove outbox append stores repository-generated `outbox_event_id` and
   `created_at_utc`
6. prove conflicting `dedupe_key` reuse uses JSONB payload equality and
   raises a redacted conflict error
7. prove `published_at_utc` remains `NULL`
8. prove checkpoint load returns `None` before save
9. prove checkpoint save upserts the expected fields
10. prove simulated batch failure rolls back checkpoint advancement,
    outbox append, source-status upsert, and derived status write
11. prove source-status upsert/read/list by natural key and by domain
12. prove derived domain readiness blocks on empty requirements, missing,
    stale, unprojected, lagging, initial-import-incomplete,
    inactive-write-path, missing outbox dedupe constraint, and explicitly
    not-ready source statuses
13. prove derived `domain_projection_status` column mapping and metadata
    match the mapping table and are not used as router authority
14. prove `PostgresControlPlaneRepository` still does not implement the
    Slice 3 boundaries
15. prove storage failures redact `str`, `repr`, `args`, `__cause__`,
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
3. whether outbox append defines who generates `outbox_event_id` and
   `created_at_utc`
4. whether payload conflict comparison is truly persisted JSONB equality,
   not an unstored fingerprint
5. whether checkpoint advancement is transaction-compatible with later
   projector batches
6. whether a failed batch can partially commit any combination of outbox,
   checkpoint, source-status, or derived status writes
7. whether `ProjectionSourceRequirement` is clearly the authoritative
   required-source registry
8. whether an empty or missing requirement set can incorrectly pass
   readiness
9. whether initial import completion, active bridge or dual-write for
   mutable sources, and outbox dedupe constraint presence are enforced
10. whether `domain_projection_source_status` remains the readiness
   authority
11. whether `domain_projection_status` can be mistaken for router
   readiness authority
12. whether derived `domain_projection_status` fields follow the required
    mapping instead of arbitrary constants
13. whether missing, stale, unprojected, lagging, not-ready,
    initial-import-incomplete, inactive-write-path, and missing outbox
    dedupe states all block readiness
14. whether source freshness semantics distinguish mutable from immutable
   sources
15. whether source identity natural keys are explicit enough for Slice 4
   adapters
16. whether `system.outbox_event` leaks into public timeline behavior
17. whether the Slice 2 read repository accidentally gains write/progress
    methods
18. whether `ProjectionSourceStatusBoundary` exposes list-by-domain as a
    stable protocol method
19. whether raw DSNs or passwords can leak through repository exceptions
20. whether fake tests could pass while real SQL behavior is broken
21. whether legacy startup can accidentally instantiate the new
    projection-state repository

## Definition Of Done

This slice is done when:

1. pure projection-state readiness contracts and tests exist
2. `PostgresProjectionStateRepository` implements outbox append,
   checkpoint load/save, source-status upsert/read/list, and derived
   status persistence
3. outbox append generates `outbox_event_id` and `created_at_utc`,
   remains idempotent, and rejects conflicting dedupe reuse by persisted
   field and JSONB payload comparison
4. checkpoint save/load and multi-write transaction rollback behavior
   are integration-tested against real Postgres
5. source-readiness aggregation is integration-tested against real
   Postgres for empty requirements, missing, stale, unprojected,
   lagging, initial-import-incomplete, inactive-write-path, missing
   outbox dedupe constraint, and not-ready sources
6. derived `domain_projection_status` field mapping is tested for ready
   and blocked reports
7. `ProjectionSourceStatusBoundary` exposes list-by-domain as a stable
   protocol method
8. `PostgresControlPlaneRepository` remains read-side only
9. no `/api/v1` route pivots to Postgres
10. mandatory legacy no-Postgres startup and route regressions pass
11. Postgres connection, migration, repository, and projection-state gates
   pass
12. docs/index validation passes
13. Postgres-gated tests skip explicitly without a DSN and pass with a
   real `TRADINGX_TEST_POSTGRES_DSN`

Only after this definition is met should Wave 2 continue into legacy
bridge, projector runner, read-router, or `/api/v1` pivot work.
