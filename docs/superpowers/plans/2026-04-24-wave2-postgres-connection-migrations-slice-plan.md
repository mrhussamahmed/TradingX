---
id: PLAN-0015
title: Headless control plane Wave 2 Postgres connection and migrations slice plan
version: 1.0.0
status: draft
created: 2026-04-24
last_amended: 2026-04-24
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-24
---

# Headless Control Plane Wave 2 Postgres Connection And Migrations Slice Plan

## Purpose

This plan defines the next executable Wave 2 slice after the foundation
work in `REPORT-0004`: add the Postgres dependency/tooling layer,
connection helpers, Alembic migration structure, and the initial control
plane schema migration.

The slice is intentionally storage-foundation-only. It must make the
future repository, outbox, checkpoint, bridge, and projector work
possible without pivoting any `/api/v1` route, exposing any stable
governed write, or making local legacy mode database-dependent.

## Authority

- `PLAN-0013`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `PLAN-0014`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
- `REPORT-0004`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-foundation-review-handoff.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `ADR-0025`: `docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md`

## Current State

Already complete on `main`:

1. `TradingConfig.control_plane` has legacy-safe Postgres/projection
   configuration defaults.
2. Safe config summaries redact Postgres DSNs.
3. `tradingx.persistence` is a package and still exports the legacy
   filesystem persistence surface.
4. `src/tradingx/persistence/postgres.py` only contains DSN redaction.

Still missing before repository/projector work can start:

1. project dependencies for SQLAlchemy, psycopg, and Alembic
2. sync Postgres engine/session helpers with safe timeout behavior
3. Alembic configuration inside the package
4. initial schemas and table skeletons for the approved Wave 2 domains
5. DSN-gated migration tests that exercise a real database when present

## Non-Negotiable Locks

1. Legacy local mode remains default and must not import, connect to, or
   require Postgres during normal startup.
2. No `/api/v1` route pivots to Postgres in this slice.
3. `/api/v1/commands` and `/api/v1/command-sessions` remain hidden,
   provisional, and excluded from OpenAPI.
4. No helper POST route is introduced for incidents, replays,
   acknowledgement, command sessions, or any governed mutation.
5. Raw DSNs and passwords must never appear in config summaries, logs,
   exceptions, test failure messages, or migration output created by this
   slice.
6. Migration tests that require Postgres must skip with an explicit
   missing-DSN reason when `TRADINGX_TEST_POSTGRES_DSN` is absent. They
   must not silently pass without exercising the database, and this slice
   may not be closed until at least one real-DSN migration run is recorded.
7. Any destructive integration-test cleanup must be guarded so it cannot
   run against a non-test database by accident. A database-name substring
   match is not sufficient.
8. The `tradingx.persistence` import surface must remain compatible.

## Out Of Scope

- repository protocols or domain repositories
- outbox insertion helpers beyond table creation
- projection checkpoints beyond table creation
- legacy bridge/backfill/tailer behavior
- route/domain router changes
- stream/SSE parity work
- frontend changes
- cloud deployment or compose changes

## Implementation Tasks

### Task 0: Baseline Verification

Run the current foundation checks before edits:

```bash
uv run pytest tests/unit/test_postgres_config.py -q
uv run pytest tests/unit/test_persistence_namespace.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
```

If one fails before code changes, stop and record the failure in the
implementation notes instead of blending it into this slice.

### Task 1: Add Postgres Dependencies

Add production dependencies:

- `sqlalchemy>=2.0,<3`
- `psycopg[binary]>=3.2,<4`
- `alembic>=1.13,<2`

Update `uv.lock` through `uv sync`, not by hand.

Files:

- `pyproject.toml`
- `uv.lock`

Checks:

```bash
uv sync
uv run python -c "import alembic, psycopg, sqlalchemy"
```

### Task 2: Implement Connection Helpers

Extend `src/tradingx/persistence/postgres.py` with a small sync helper
surface:

1. a frozen settings object derived from `TradingConfig.control_plane`
2. `build_postgres_engine(...)` or equivalent helper that creates a
   SQLAlchemy `Engine`
3. safe timeout defaults:
   - connection timeout: 5 seconds
   - statement timeout: 30 seconds unless config later provides a
     narrower value
   - pool pre-ping enabled
4. `require_postgres_dsn(...)` behavior that raises a typed error when
   Postgres is requested/required but no DSN is configured
5. redacted DSN access for diagnostics

The helper must not create an engine during `TradingConfig` construction
or legacy app startup. Engine creation must be explicit.

Files:

- `src/tradingx/persistence/postgres.py`
- `tests/unit/test_postgres_connection.py`

Checks:

```bash
uv run pytest tests/unit/test_postgres_connection.py -q
uv run pytest tests/unit/test_postgres_config.py -q
```

### Task 3: Add Alembic Package Configuration

Add Alembic migration support under the package path so the migration
code can later ship with the application:

```text
src/tradingx/persistence/migrations/
  env.py
  script.py.mako
  versions/
    20260424_0001_control_plane_foundation.py
```

Use SQLAlchemy Core / Alembic operations. Do not introduce ORM models in
this slice.

Add a small programmatic migration runner for tests and future CLI
integration. The runner may live in `postgres.py` or a narrow migration
module, but it must keep raw DSNs redacted in all raised messages.

The migration must implement both `upgrade()` and `downgrade()`. Downgrade
must remove the objects created by this initial migration in dependency-safe
reverse order and leave no managed Wave 2 schemas behind after
`downgrade(base)`.

Use Alembic's default `public.alembic_version` table for version tracking.
Do not place the version table in one of the managed Wave 2 schemas. Tests
that fully reset a database may drop exactly `public.alembic_version` after
the cleanup safety guard passes, but no other `public` object may be
touched.

Package-local migration loading must work from outside the repository root.
The implementation must verify that `env.py`, `script.py.mako`, and the
version files are discoverable through installed-package resources rather
than only through cwd-relative paths.

Files:

- `src/tradingx/persistence/migrations/env.py`
- `src/tradingx/persistence/migrations/script.py.mako`
- `src/tradingx/persistence/migrations/versions/20260424_0001_control_plane_foundation.py`
- `tests/unit/test_postgres_migration_config.py`

Checks:

```bash
uv run pytest tests/unit/test_postgres_migration_config.py -q
```

### Task 4: Create Initial Schemas And Table Skeletons

The initial migration must create these schemas:

- `access`
- `commanding`
- `runtime`
- `incidents`
- `portfolio`
- `validation`
- `investigations`
- `documents`
- `system`

Create table skeletons that support later Wave 2 repository and
projection work. The columns should match the approved architecture
closely enough that later slices do not need a destructive rewrite.
Use the `PLAN-0013` table names directly; do not create renamed,
collapsed, or convenience substitutes in this migration.

Required table inventory:

- `access.operator_account`
- `access.operator_role_binding`
- `access.command_session`
- `access.command_session_event`
- `commanding.command`
- `commanding.command_attempt`
- `commanding.command_idempotency_record`
- `commanding.command_event`
- `commanding.command_result_snapshot`
- `runtime.runtime_instance`
- `runtime.runtime_state_snapshot`
- `runtime.runtime_heartbeat`
- `runtime.scheduler_run`
- `runtime.market_day_run`
- `runtime.control_posture_snapshot`
- `runtime.control_posture_blocker`
- `incidents.incident`
- `incidents.incident_event`
- `incidents.incident_acknowledgement`
- `portfolio.portfolio_snapshot`
- `portfolio.portfolio_timeseries_point`
- `portfolio.position_snapshot`
- `portfolio.exposure_snapshot`
- `portfolio.benchmark_timeseries_point`
- `portfolio.attribution_snapshot`
- `portfolio.execution_quality_snapshot`
- `validation.validation_run`
- `validation.validation_candidate`
- `validation.validation_criterion_result`
- `validation.validation_readiness_blocker`
- `validation.pbo_report`
- `validation.cpcv_cohort`
- `investigations.replay_run`
- `investigations.replay_event`
- `investigations.investigation_workspace`
- `investigations.drift_analysis_snapshot`
- `documents.document`
- `documents.document_revision`
- `documents.document_object_ref`
- `system.outbox_event`
- `system.projection_checkpoint`
- `system.domain_projection_source_status`
- `system.domain_projection_status`

Required cross-cutting behavior:

1. UTC timestamp columns use `TIMESTAMPTZ`.
2. JSON payload columns use `JSONB`.
3. Stable identifiers use text primary keys unless the architecture names
   a different key.
4. `system.outbox_event.dedupe_key` is unique.
5. projection checkpoint and source-status tables have unique keys that
   make idempotent upsert possible in later slices.
6. control-posture snapshots include `resource_version` and
   `state_fingerprint`.
7. command tables include target resource version/fingerprint fields
   needed for Wave 3 mutation preconditions.
8. every table has an explicit primary key or, for status/checkpoint rows,
   the approved natural primary key from `PLAN-0013`.
9. parent-child tables created in this migration have explicit foreign keys
   where the parent table is in the same migration. This includes operator
   role/session rows, session events, command attempts/events, posture
   blockers, incident events, validation child rows, and portfolio child
   snapshots.
10. event/attempt tables have deterministic ordering constraints or indexes:
    `command_attempt(command_id, attempt_number)`,
    `command_event(command_id, event_seq)`, and
    `command_session_event(command_session_id, occurred_at_utc)`.
11. `command_idempotency_record` is keyed by `idempotency_key_hash` and has
    a uniqueness rule for `(idempotency_key_hash, request_hash)`.
12. `system.outbox_event` has unique `dedupe_key` plus an aggregate/time
    lookup index suitable for later projector reads.
13. `system.projection_checkpoint` is keyed by `projection_name`.
14. `system.domain_projection_source_status` is unique on
    `(domain_name, source_family, source_identity)`, and
    `system.domain_projection_status` is keyed by `domain_name`.

Files:

- `src/tradingx/persistence/migrations/versions/20260424_0001_control_plane_foundation.py`
- `tests/integration/test_controlplane_postgres_store.py`

Checks:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5432/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py -q
```

### Task 5: Guard Integration Test Cleanup

The Postgres integration fixture may reset managed schemas only when one
of these is true:

1. the parsed database name is exactly `tradingx_test`
2. `TRADINGX_ALLOW_POSTGRES_TEST_RESET=true`

If neither condition is true, the test must fail with a clear safety
message before any destructive SQL is constructed or runs. Substring checks
such as "contains `test`" are not acceptable.

The managed schemas are exactly the nine Wave 2 schemas listed above.
No cleanup may touch `public` except dropping exactly
`public.alembic_version` after the same safety guard passes. This prevents
stale Alembic state from making a later `upgrade(head)` falsely no-op while
keeping all other `public` objects off limits.

Files:

- `tests/integration/test_controlplane_postgres_store.py`

### Task 6: Preserve Legacy Compatibility

Re-run namespace and legacy-mode tests after the migration files exist:

```bash
uv run pytest tests/unit/test_persistence_namespace.py -q
uv run pytest tests/unit/test_postgres_config.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
```

No legacy route, config summary, or filesystem persistence import should
change behavior in this slice.

### Task 7: Documentation And Index Updates

Update the relevant docs only if behavior or operator setup changes in
this slice:

- `.env.example` if new Postgres variables need clearer local examples
- `docs/operations/operator_manual.md` if a local migration command is
  exposed
- `docs/INDEX.md` for any new governed artifacts

Do not document Postgres mode as the default. Legacy mode remains the
operator default until later Wave 2 route-pivot work.

## Verification Gate

Focused verification:

```bash
uv sync
uv run ruff check src/tradingx/persistence tests/unit/test_postgres_connection.py tests/unit/test_postgres_migration_config.py tests/integration/test_controlplane_postgres_store.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_postgres_config.py -q
uv run pytest tests/unit/test_persistence_namespace.py -q
uv run pytest tests/unit/test_postgres_connection.py -q
uv run pytest tests/unit/test_postgres_migration_config.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
python3 scripts/check_index.py
```

Postgres-gated verification when a DSN is available:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5432/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py -q
```

If the DSN is absent, the integration test must report an explicit skip
reason. The implementation notes must say whether the real-DSN path was
run. A local skip is acceptable during iteration, but the slice is not done
until a real `TRADINGX_TEST_POSTGRES_DSN` run has passed and is recorded.

The DSN-backed integration test must verify this sequence:

1. safety guard rejects an unsafe database name before destructive SQL is
   built or executed
2. guarded reset removes the nine managed schemas and exactly
   `public.alembic_version`
3. `upgrade(head)` creates the schemas, tables, constraints, and indexes
4. Alembic current state reports the expected head revision
5. a second `upgrade(head)` is idempotent and does not recreate or corrupt
   objects
6. `downgrade(base)` removes the managed schemas and returns Alembic to
   base state
7. a final `upgrade(head)` succeeds after downgrade
8. catalog inspection confirms primary keys, foreign keys, unique
   constraints, and minimum indexes required above
9. failures and logs redact the raw DSN

## Adversarial Review Checklist

Reviewer should challenge:

1. whether the migration table inventory is too thin for the next
   repository/outbox/projector slices
2. whether any dependency or helper makes legacy local startup require
   Postgres
3. whether raw DSNs can leak through exceptions, reprs, config summaries,
   or test logs
4. whether migration tests can falsely pass without a database
5. whether destructive cleanup is safely constrained to test databases
6. whether Alembic configuration is usable from installed package code
   rather than only from the repo root
7. whether table constraints make later idempotent outbox and projection
   upserts possible
8. whether downgrade/re-upgrade coverage proves migration reversibility
9. whether Alembic version-table cleanup can create false-positive tests
10. whether command/session tables accidentally imply stable write APIs
    before Wave 3
11. whether introducing ORM state now would create unnecessary coupling
12. whether `tradingx.persistence` namespace compatibility remains intact

## Definition Of Done

This slice is done when:

1. dependencies are installed and locked
2. connection helpers exist and are explicit, redacted, and legacy-safe
3. Alembic migration structure exists under `tradingx.persistence`
4. package-local Alembic loading works from outside the repository root
5. the initial migration creates all required schemas, table skeletons,
   constraints, and indexes
6. downgrade and re-upgrade behavior is implemented and verified
7. integration tests skip explicitly without a DSN during local iteration,
   but at least one real `TRADINGX_TEST_POSTGRES_DSN` run has passed before
   the slice is closed
8. cleanup safety rejects unsafe DSNs before destructive SQL is built or
   executed
9. legacy config, namespace, and `/api/v1` contract tests still pass
10. `scripts/check_index.py` passes

Only after this definition is met should Wave 2 continue into repository
contracts and outbox/checkpoint/source-readiness behavior.
