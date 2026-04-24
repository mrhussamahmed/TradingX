---
id: PLAN-0016
title: Headless control plane Wave 2 Postgres repository contracts plan
version: 1.0.0
status: draft
created: 2026-04-24
last_amended: 2026-04-24
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-24
---

# Headless Control Plane Wave 2 Postgres Repository Contracts Plan

## Purpose

This plan defines the next executable Wave 2 slice after
`PLAN-0015`: add repository contracts and test-first coverage for the
Postgres-backed control-plane domains.

The goal is to make storage behavior explicit before outbox,
checkpoint, source-readiness, bridge, projector, or `/api/v1` router work
continues. The slice must not pivot any route to Postgres and must not
make legacy local mode database-dependent.

This plan covers the recommended development activities:

1. plan and implement Wave 2 Slice 2 repository contracts
2. add tests before implementation code

## Authority

- `PLAN-0013`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `PLAN-0014`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
- `PLAN-0015`: `docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-slice-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `ADR-0025`: `docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md`

## Current State

Already complete:

1. Postgres dependencies are installed and locked.
2. `tradingx.persistence.postgres` exposes explicit engine, migration,
   reset, and catalog helpers with redacted diagnostics.
3. Package-local Alembic migrations create the Wave 2 schemas and table
   skeletons.
4. Real-DSN migration tests cover upgrade, idempotent upgrade,
   downgrade, re-upgrade, constraints, and indexes.
5. Legacy local mode still works without Postgres.

Still missing before projector and router work:

1. domain repository protocols
2. concrete return shapes for read-side records
3. deterministic ordering and pagination contracts
4. fake repositories for unit tests and later router composition tests
5. Postgres repository implementations or skeletons that prove the SQL
   contracts against the migration schema
6. safety tests proving contracts do not make `/api/v1` routes or legacy
   startup depend on Postgres

## Non-Negotiable Locks

1. Legacy local mode remains the default and must not connect to
   Postgres during config load, app creation, or legacy route handling.
2. No `/api/v1` route pivots to Postgres in this slice.
3. `/api/v1/commands` and `/api/v1/command-sessions` remain hidden,
   provisional, and excluded from OpenAPI.
4. No helper POST route is introduced for incidents, replays,
   acknowledgement, command sessions, or any governed mutation.
5. Repository method names and return shapes must be shaped around the
   stable control-plane domain model, not raw artifact filenames or
   migration-table accidents.
6. Raw DSNs and passwords must stay out of exceptions, reprs, logs, and
   test output.
7. Postgres-gated tests must skip explicitly without
   `TRADINGX_TEST_POSTGRES_DSN`; they must not pass by exercising only
   fakes.
8. Repository contracts may define the Slice 3 boundaries for outbox
   append, checkpoint load/save, and source-status upsert/read, but this
   slice must not implement those behaviors.
9. Repository contracts must not implement outbox publishing,
   checkpoint advancement, source-readiness aggregation, bridge/tailer
   behavior, projector orchestration, or domain router selection.
10. Access, command-session, and commanding contracts are read-side
    audit/summary contracts only. Write-shaped command intake,
    idempotency replay, precondition enforcement, and session issuance
    methods are prohibited until the Wave 3 command intake plan.

## Out Of Scope

- outbox insertion helpers
- projection checkpoint load/save behavior
- domain projection source-status upserts or readiness aggregation
- legacy bridge/backfill/tailer behavior
- projector runners
- `PostgresControlPlaneReadModel`
- `/api/v1` route pivoting
- SSE parity
- frontend changes
- local compose stack
- cloud deployment

## Architecture Approach

Create a thin control-plane repository boundary:

- `src/tradingx/controlplane/repositories.py` owns protocols,
  query parameter dataclasses, result dataclasses, page objects, and
  repository error types.
- `src/tradingx/persistence/repositories/` owns Postgres-backed
  implementations and package exports.
- Tests use in-memory fakes to pin method contracts before SQL behavior.
- Postgres integration tests insert minimal rows directly with SQL or
  helper fixtures, then assert repository output ordering, pagination,
  conflict behavior where relevant, and redacted failure diagnostics.

The contracts should be narrow and domain-specific. Do not create a
generic repository abstraction or ORM model layer in this slice.

Protocol categories are explicit:

1. **Implementation-backed repository protocols.** Every method in this
   category must have a concrete Postgres implementation and at least
   one Postgres-gated test in this slice.
2. **Contract-only next-slice boundaries.** These may define method
   signatures and dataclasses that Slice 3 must implement, but they must
   be named as contract-only, must not ship fake behavior that claims the
   method works, and must not be counted as SQL-backed repository
   coverage.

If a domain cannot receive real SQL coverage in this slice and is not a
contract-only Slice 3 boundary, defer that protocol.

## Repository Domains

Add protocols for these Wave 2 domains:

1. access and command-session audit summaries
2. commanding read-side audit summaries
3. runtime
4. incidents
5. public event timeline
6. portfolio
7. validation
8. investigations and replays
9. documents
10. system metadata needed by later readiness/router work
11. Slice 3 contract-only boundaries for outbox append, projection
    checkpoint load/save, and domain projection source-status upsert/read

Only implementation-backed domains may define ordinary repository
protocols. Domains that are not implemented against real SQL in this
slice must be represented as deferred domain notes, except for the
explicit Slice 3 contract-only boundaries.

Access, command-session, and commanding protocols must be read-only in
this slice. They may expose audit summaries, command lifecycle summaries,
session history lookups, and event-history reads. They must not expose
command creation, session issuance, idempotency replay, precondition
enforcement, or result recording.

Slice 3 operations may be represented as contract-only protocols and
dataclasses, but their concrete behavior and SQL implementation remain
owned by Slice 3.

The public event timeline contract is mandatory and
implementation-backed in this slice. It must be separate from
`system.outbox_event`: outbox rows are internal projector inputs, while
event timeline records are canonical API read records for later
`/api/v1/events` router work.

## Required Contract Behavior

1. List methods return deterministic order by a named timestamp plus a
   stable ID.
2. Each list method must name its timestamp column, sort direction,
   tie-break column, tie-break direction, null handling, default page
   size, and max page size.
3. List methods accept bounded cursor pagination parameters with
   defaults.
4. Lookup methods return `None` for not-found records rather than raising
   storage-driver errors.
5. Cursor pagination must specify cursor encoding, invalid cursor error
   behavior, next-page token behavior, and whether boundaries are
   inclusive or exclusive.
6. Cursor values must encode the ordered tuple used by the query, such
   as `(observed_at_utc, snapshot_id)`, so inserts between pages cannot
   duplicate or skip records.
7. Command/session contracts must not expose command intake,
   idempotency replay, precondition enforcement, session issuance, or
   other write-shaped methods in this slice.
8. Slice 3 boundary protocols must name the natural keys needed later for
   outbox append, checkpoint load/save, and source-status upsert/read,
   but must not implement the behavior.
9. Result dataclasses use plain Python types, tuples, and mappings; they
   do not leak SQLAlchemy row objects.
10. Repository exceptions wrap storage failures with domain context and
   redacted DSN diagnostics.
11. Contract tests assert protocol method names and return shape stability
   before any concrete Postgres implementation is written.

## Implementation Tasks

### Task 0: Baseline Verification

Run before edits:

```bash
uv run pytest tests/unit/test_postgres_config.py tests/unit/test_persistence_namespace.py tests/unit/test_postgres_connection.py tests/unit/test_postgres_migration_config.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
python3 scripts/check_index.py
```

If a baseline failure exists before repository edits, stop and record it
separately.

### Task 1: Add Test-First Repository Contract Coverage

Create the contract tests before implementation code:

- `tests/unit/test_controlplane_repository_contracts.py`

The first tests must prove:

1. repository protocols expose the expected domain method names
2. query dataclasses apply bounded cursor pagination defaults
3. result dataclasses are immutable or value-stable enough for tests to
   compare directly
4. fake repositories can satisfy the protocols without importing
   SQLAlchemy for implementation-backed methods only
5. not-found behavior returns `None`
6. list behavior is deterministic when records share a timestamp and
   cursor boundaries use the timestamp-plus-ID tuple
7. command/session protocols expose no write-shaped methods
8. Slice 3 contract-only boundaries exist for outbox append,
   checkpoint load/save, and source-status upsert/read, but have no
   fake implementation behavior
9. repository error `str`, `repr`, `args`, `__cause__`, and
   `__context__` do not expose raw DSNs or passwords

Expected red state: imports fail because the contracts do not exist yet.

### Task 2: Add Control-Plane Repository Protocols

Create:

- `src/tradingx/controlplane/__init__.py`
- `src/tradingx/controlplane/repositories.py`

Define:

- implementation-backed repository protocols per domain
- contract-only Slice 3 boundary protocols for outbox append,
  checkpoint load/save, and source-status upsert/read
- query dataclasses, including `PageRequest` and `Page`
- cursor dataclasses or helpers that encode ordered timestamp-plus-ID
  boundaries
- value objects for IDs, resource versions, state fingerprints, and
  source refs only where they remove ambiguity
- domain result dataclasses for each canonical read shape needed by
  Slice 3 and Slice 6
- typed repository errors with redacted diagnostics

Keep this module independent of SQLAlchemy and FastAPI.

Do not define ordinary repository protocols for deferred domains that
will not receive SQL coverage in this slice.

Checks:

```bash
uv run pytest tests/unit/test_controlplane_repository_contracts.py -q
uv run mypy src/tradingx
```

### Task 3: Add Postgres Repository Package Skeleton

Create:

- `src/tradingx/persistence/repositories/__init__.py`
- `src/tradingx/persistence/repositories/postgres.py`

The initial Postgres implementation should prove the repository boundary
without attempting every future read model. It should include:

1. a base helper for safe engine/session handling
2. row-to-dataclass conversion helpers
3. redacted exception wrapping
4. deterministic ordering helpers
5. concrete implementations for every implementation-backed method in
   this slice:
   - runtime posture snapshots and blockers
   - runtime heartbeats
   - incidents and incident events
   - system projection status reads
   - public event timeline reads

Do not implement outbox append, checkpoint writes, or source-status
upserts in this task. Those are contract-only Slice 3 boundaries.

### Task 4: Add Postgres-Gated Repository Tests

Create:

- `tests/integration/test_controlplane_postgres_repositories.py`

The tests must:

1. skip explicitly without `TRADINGX_TEST_POSTGRES_DSN`
2. reset only the guarded `tradingx_test` database through existing
   helpers
3. run the package-local migrations
4. seed rows with minimal SQL fixtures
5. assert deterministic cursor ordering and pagination against real
   Postgres for every implementation-backed method
6. assert not-found behavior
7. assert storage failures are wrapped with redacted diagnostics across
   `str`, `repr`, `args`, `__cause__`, and `__context__`
8. assert repository code uses the existing schema/table names from
   `PLAN-0015`
9. fail if an ordinary repository protocol method lacks real SQL
   coverage
10. assert contract-only Slice 3 boundaries are not exposed by the
    Postgres repository implementation yet

Run locally with this workstation's DSN:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_repositories.py -q
```

### Task 5: Preserve Legacy And Web Contracts

Re-run legacy and web contract tests:

```bash
uv run pytest tests/unit/test_persistence_namespace.py tests/unit/test_postgres_config.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
```

Add a mandatory regression proving `create_app(...)` and representative
legacy `/api/v1` read routes do not instantiate Postgres repositories or
engines unless a later router slice explicitly wires them. The test
should monkeypatch repository and engine construction to fail loudly,
then prove legacy app creation and representative read routes still
pass.

### Task 6: Documentation And Index Updates

Update docs only if new public local commands or env variables are
introduced. This slice should usually need only `docs/INDEX.md` for the
new plan artifact.

Do not document Postgres as the default store.

## Verification Gate

Focused verification:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_repository_contracts.py tests/integration/test_controlplane_postgres_repositories.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_postgres_connection.py tests/unit/test_postgres_migration_config.py -q
uv run pytest tests/unit/test_controlplane_repository_contracts.py -q
uv run pytest tests/unit/test_persistence_namespace.py tests/unit/test_postgres_config.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
python3 scripts/check_index.py
git diff --check
```

Postgres-gated verification when a DSN is available:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_repositories.py -q
```

CI note: remote GitHub Actions may remain blocked until the repository
owner resolves the account billing/spending-limit issue. Do not treat a
runner-not-started CI failure as repository test evidence.

## Adversarial Review Checklist

Reviewer should challenge:

1. whether the plan accidentally implements Slice 3 outbox/checkpoint
   behavior
2. whether the Slice 3 outbox/checkpoint/source-status boundaries are
   explicit enough for Slice 3 to implement without inventing new
   repository seams
3. whether any method shape is tied to legacy artifact filenames instead
   of canonical control-plane domains
4. whether the contracts are too broad for the next two slices
5. whether the contracts are too thin to support projectors and routers
   without churn
6. whether fake tests could pass while real SQL behavior is broken
7. whether deterministic ordering is fully specified per query
8. whether cursor pagination semantics are stable under inserts between
   pages
9. whether not-found behavior and storage failures are distinguished
10. whether raw DSNs or passwords can leak through repository exceptions
    or chained tracebacks
11. whether legacy startup or `/api/v1` routes can accidentally import or
    instantiate Postgres repositories
12. whether command/session contracts imply stable governed write APIs
    before Wave 3
13. whether public event timeline records are clearly separate from
    internal outbox rows
14. whether introducing dataclasses now creates a second schema model that
    conflicts with the migration tables

## Definition Of Done

This slice is done when:

1. repository protocols and value/result dataclasses exist under
   `tradingx.controlplane`
2. unit tests prove contract shape, deterministic ordering, cursor
   pagination, fakes, not-found behavior, command/session read-only
   scope, Slice 3 contract-only boundaries, and redacted repository
   errors
3. Postgres repository package skeleton exists without ORM coupling
4. every implementation-backed repository method is integration-tested
   against real Postgres
5. no `/api/v1` route pivots to Postgres
6. mandatory legacy no-Postgres startup and route regressions pass
7. legacy local mode and contract tests still pass
8. Postgres connection and migration safety tests still pass
9. docs/index validation passes
10. the Postgres-gated tests skip explicitly without a DSN and pass with a
   real `TRADINGX_TEST_POSTGRES_DSN`

Only after this definition is met should Wave 2 continue into outbox,
checkpoint, and source-readiness behavior.
