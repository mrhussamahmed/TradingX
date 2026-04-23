---
id: PLAN-0014
title: Headless control plane Wave 2 Postgres projections implementation plan
version: 1.0.0
status: draft
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-23
---

# Headless Control Plane Wave 2 Postgres Projections Implementation Plan

## Purpose

This plan turns approved `PLAN-0013` into an implementation-ready work
package. It does not change the Wave 2 architecture or add scope. Its job
is to make the coding sequence, file ownership, verification gates, and
adversarial-review traps explicit before implementation starts.

Wave 2 moves the Wave 1 `/api/v1` read side from legacy artifact adapters
toward Postgres-backed canonical state while governed writes remain
hidden and provisional until Wave 3.

## Authority

- `PLAN-0013`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- Wave 1 handoff: `docs/superpowers/plans/2026-04-23-headless-control-plane-wave1-review-handoff.md`
- Broad plan: `docs/superpowers/plans/2026-04-23-headless-control-plane-implementation-plan.md`
- Gate 4 signing authority: `docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md`

## Non-Negotiable Locks

1. `/api/v1/commands` and `/api/v1/command-sessions` remain hidden,
   provisional, and excluded from OpenAPI.
2. No helper POST route is introduced for incident acknowledgement,
   replay creation, command sessions, or any other governed mutation.
3. A domain can route to Postgres only when every required source family
   is present, fresh, projected, and represented in
   `domain_projection_source_status`.
4. `domain_projection_status` is a derived summary, not the source of
   truth for readiness.
5. `/api/v1/events` pivots late, after incidents, runtime, validation,
   command read-side history, and market-data posture event families are
   projected and parity-tested.
6. Implemented `/api/v1/stream` topics use the same domain/source router
   as polling routes. Architecture-declared topics not implemented in
   Wave 2 remain explicitly rejected or legacy-routed until their polling
   domains move with them. `commands` remains rejected until Wave 3.
7. Control-posture live config/env evaluation must persist a versioned
   `control_posture_snapshot`, structured blockers, source status,
   `resource_version`, and `state_fingerprint` before the API response
   is built. If the effective posture is unchanged, the refresh must
   reuse the existing version/fingerprint; versions advance only when the
   effective posture changes.
8. The existing `tradingx.persistence` import surface must remain
   compatible while Postgres persistence code is introduced.
9. Legacy local mode remains the default and must not require Postgres.

## Implementation Slices

### Slice 0: Baseline and Dependency Guard

Goal: prepare the branch for Postgres work without changing runtime
behavior.

Tasks:

1. Confirm Wave 1 contract tests pass before code changes.
2. Add Postgres dependencies to project metadata.
3. Add Postgres/projection config fields with safe defaults:
   `TRADINGX_CONTROL_PLANE_STORE=legacy`, disabled projections, optional
   DSN.
4. Add config tests proving legacy mode does not require a database.

Owned paths:

- `pyproject.toml`
- `src/tradingx/config.py`
- `tests/unit/test_postgres_config.py`

Verification:

```bash
uv run pytest tests/unit/test_postgres_config.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
```

### Slice 1: Postgres Connection and Migrations

Goal: create the durable schema foundation from `PLAN-0013`.

Tasks:

1. Add Postgres engine/session helpers with timeout settings and redacted
   DSN logging.
2. Resolve the current `src/tradingx/persistence.py` module/package
   collision before adding submodules. Convert it into the package entry
   point `src/tradingx/persistence/__init__.py`, preserve the existing
   public exports there, and remove the standalone module shape so Python
   cannot shadow the old import surface. Existing imports such as
   `from tradingx.persistence import FilesystemArtifactStore` must keep
   working.
3. Add Alembic configuration and an initial migration for the `access`,
   `commanding`, `runtime`, `incidents`, `portfolio`, `validation`,
   `investigations`, `documents`, and `system` schemas.
4. Include required constraints for outbox dedupe, source readiness, and
   posture blockers.
5. Add migration tests against `TRADINGX_TEST_POSTGRES_DSN`, with clear
   skips when the DSN is absent.
6. Add namespace compatibility tests for existing `tradingx.persistence`
   exports before and after the package conversion.

Owned paths:

- `src/tradingx/persistence.py`
- `src/tradingx/persistence/__init__.py`
- `src/tradingx/persistence/postgres.py`
- `src/tradingx/persistence/migrations/`
- `tests/unit/test_persistence_namespace.py`
- `tests/integration/test_controlplane_postgres_store.py`

Verification:

```bash
uv run pytest tests/unit/test_persistence_namespace.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5432/tradingx_test uv run pytest tests/integration/test_controlplane_postgres_store.py -q
```

### Slice 2: Repository Contracts

Goal: isolate storage details behind explicit domain repositories.

Tasks:

1. Add repository protocols for each Wave 2 read domain.
2. Implement Postgres repositories with deterministic ordering,
   pagination defaults, upsert/idempotency behavior, and plain
   dict/dataclass return values.
3. Keep repository methods shaped around canonical `/api/v1` responses,
   not artifact payloads.
4. Add unit coverage with repository fakes and Postgres-gated integration
   coverage for real SQL behavior.

Owned paths:

- `src/tradingx/controlplane/repositories.py`
- `src/tradingx/persistence/repositories/`
- `tests/unit/test_controlplane_repositories.py`

Verification:

```bash
uv run pytest tests/unit/test_controlplane_repositories.py -q
```

### Slice 3: Outbox, Checkpoints, and Source Readiness

Goal: make projection progress resumable and readiness testable per
source family.

Tasks:

1. Implement outbox insertion with database-level conflict handling on
   `dedupe_key`.
2. Implement projection checkpoint load/save.
3. Implement `domain_projection_source_status` upserts and derived
   `domain_projection_status` aggregation.
4. Add tests proving a domain cannot be ready when any required source
   family is stale, missing, or unprojected.
5. Add failure tests proving partial projector batches do not advance
   checkpoints.

Owned paths:

- `src/tradingx/persistence/outbox.py`
- `src/tradingx/controlplane/projections.py`
- `tests/unit/test_controlplane_projectors.py`

Verification:

```bash
uv run pytest tests/unit/test_controlplane_projectors.py -q
```

### Slice 4: Legacy Bridge and Tailer

Goal: import current local history and keep mutable legacy sources fresh
until canonical writers arrive later.

Tasks:

1. Add source adapters for artifacts, operator-control files, live
   config/env posture inputs, market-data posture inputs, weights, ops
   baselines, `data/journal.db`, validation SQLite data, and documents.
2. Add bridge commands:
   `--once`, `--since`, `--tail`, and `--dry-run`.
3. Emit stable source identities, dedupe keys, source watermarks, and
   canonical domain events.
4. Add idempotency tests that run the same import twice without
   duplicating rows.
5. Add freshness tests proving a stale mutable source blocks Postgres
   routing for its domain.

Owned paths:

- `src/tradingx/controlplane/legacy_bridge.py`
- `tests/unit/test_controlplane_legacy_bridge.py`

Verification:

```bash
uv run pytest tests/unit/test_controlplane_legacy_bridge.py -q
```

### Slice 5: Domain Projectors

Goal: materialize Postgres read models for every Wave 2 domain.

Tasks:

1. Implement `runtime_projection`, including runtime snapshots,
   heartbeat history, control-posture snapshots, and market-data posture
   timeline events.
2. Implement `incident_projection`, including incidents and operator
   timeline events.
3. Implement `portfolio_projection`, including portfolio workspace,
   positions, performance, exposure, attribution, and execution quality.
4. Implement `validation_projection`, including readiness, criteria,
   report indexes, blocker changes, candidate decisions, report
   publication, and validation timeline events.
5. Implement `investigation_projection`, including replay indexes, replay
   events, investigation workspaces, and list/detail consistency.
6. Implement `document_projection`, including document indexes and object
   references.
7. Implement `commanding_projection` for command/session/audit summaries
   and command timeline events only. Do not expose stable command writes.
8. Ensure control-posture live fact evaluation persists versioned
   snapshots and blocker rows before responses use them, and that
   no-op refreshes reuse the existing `resource_version` and
   `state_fingerprint`.
9. Add tests proving control-posture versions advance only when the
   effective posture changes.

Owned paths:

- `src/tradingx/controlplane/projections.py`
- `src/tradingx/persistence/repositories/`
- `tests/unit/test_controlplane_projectors.py`
- `tests/integration/test_controlplane_postgres_store.py`

Verification:

```bash
uv run pytest tests/unit/test_controlplane_projectors.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5432/tradingx_test uv run pytest tests/integration/test_controlplane_postgres_store.py -q
```

### Slice 6: Postgres Read Model and Domain Router

Goal: let `/api/v1` domains move independently without source drift.

Tasks:

1. Add `PostgresControlPlaneReadModel`.
2. Add a domain-aware read router that supports `legacy`, `hybrid`, and
   required-Postgres modes.
3. Map each stable route family to a domain:
   documents, incidents, events, runtime, runtime heartbeats,
   control-posture, validation, portfolio, investigations, replays, and
   command read side.
4. Refuse Postgres routing when source readiness is false. In required
   Postgres mode, fail startup instead of silently falling back.
5. Add router tests for fallback, startup failure, per-domain rollback,
   and stale source blocking.

Owned paths:

- `src/tradingx/controlplane/readmodels.py`
- `src/tradingx/web/runtime.py`
- `src/tradingx/web/app.py`
- `tests/unit/test_controlplane_domain_router.py`

Verification:

```bash
uv run pytest tests/unit/test_controlplane_domain_router.py -q
```

### Slice 7: `/api/v1` Pivot and SSE Parity

Goal: keep the Wave 1 contract stable while adding Postgres-backed read
mode.

Tasks:

1. Pivot domains only in the approved order from `PLAN-0013`.
2. Keep governed write routes hidden from OpenAPI and returning `503`.
3. Add Postgres-backed contract coverage for stable route families.
   This must boot the real FastAPI app with the domain router and a
   Postgres-backed read model; the existing fake-read-model contract
   suite is not sufficient for this gate.
4. Add `/api/v1/events` coverage proving runtime, validation, command
   read-side, incident, and market-data posture event families are
   present before Postgres routing is allowed.
5. Add stream parity or explicit-rejection tests for `runtime`,
   `incidents`, `events`, `control_posture`, `validation`, and
   `portfolio`.
6. Keep `commands` rejected as a stream topic until Wave 3.

Owned paths:

- `src/tradingx/web/app.py`
- `tests/contract/test_local_web_app_api_contract.py`
- `tests/contract/test_controlplane_stream_parity.py`
- `tests/integration/test_controlplane_postgres_web_app.py`

Verification:

```bash
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
uv run pytest tests/contract/test_controlplane_stream_parity.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5432/tradingx_test uv run pytest tests/integration/test_controlplane_postgres_web_app.py -q
```

### Slice 8: Local Stack and Operator Notes

Goal: make Postgres mode runnable locally without making it mandatory.

Tasks:

1. Add local Postgres compose support.
2. Add `.env` examples for Postgres/projection settings.
3. Document local bootstrap:
   migrations, bridge/backfill, tailer, projector, web app startup.
4. Keep legacy local mode documented as the default.
5. Add PR manual-run notes for migration command, bridge command,
   tail/freshness proof, projector command, per-source readiness status,
   `/api/v1/control-posture`, `/api/v1/runtime`, `/api/v1/events`, and at
   least one stream parity spot-check.

Owned paths:

- `docker-compose.yml`
- `.env.postgres.example` or existing env examples
- `docs/superpowers/plans/`

Verification:

```bash
python3 scripts/check_index.py
```

## End-To-End Verification

Required before implementation review:

```bash
uv sync
uv run ruff check src/tradingx tests
uv run mypy src/tradingx
uv run pytest tests/unit/test_postgres_config.py -q
uv run pytest tests/unit/test_persistence_namespace.py -q
uv run pytest tests/unit/test_controlplane_repositories.py -q
uv run pytest tests/unit/test_controlplane_legacy_bridge.py -q
uv run pytest tests/unit/test_controlplane_projectors.py -q
uv run pytest tests/unit/test_controlplane_domain_router.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
uv run pytest tests/contract/test_controlplane_stream_parity.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5432/tradingx_test uv run pytest tests/integration/test_controlplane_postgres_web_app.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5432/tradingx_test uv run pytest tests/integration/test_controlplane_postgres_store.py -q
python3 scripts/check_index.py
```

If `TRADINGX_TEST_POSTGRES_DSN` is unavailable, Postgres-gated tests must
skip with a clear missing-DSN reason. They must not silently pass without
exercising the database.

## Implementation Order

1. Baseline and dependency guard.
2. Postgres connection and migrations.
3. Repository contracts.
4. Outbox, checkpoints, and source readiness.
5. Legacy bridge and tailer.
6. Domain projectors.
7. Postgres read model and domain router.
8. `/api/v1` pivot and SSE parity.
9. Local stack and operator notes.
10. Implementation review handoff.

## Parallelization Notes

Work can split after the migration contract is stable:

- repository implementations by domain
- bridge source adapters by source family
- projector tests by domain
- local stack docs

The following stays sequential:

- migrations before repositories
- persistence namespace compatibility before adding
  `tradingx.persistence.*` submodules
- repository contracts before projectors
- per-source readiness before route pivot
- domain router before hybrid route mode
- projectors before `/api/v1/events` Postgres pivot
- real Postgres app/router tests before claiming route pivot coverage
- stream parity before claiming Wave 2 done

## Adversarial Review Checklist

Reviewers should challenge:

1. Whether any task exposes stable governed writes before Wave 3.
2. Whether any source family can be omitted while domain readiness still
   goes green.
3. Whether `/api/v1/events` can pivot before all required timeline
   families exist.
4. Whether `validation_projection` and `commanding_projection` own their
   timeline event families.
5. Whether control-posture read-time evaluation can bypass persisted
   version/fingerprint updates or churn versions when posture is
   unchanged.
6. Whether the `tradingx.persistence` namespace migration preserves
   existing imports while adding Postgres submodules.
7. Whether Postgres-backed route coverage boots the real app/router with
   a Postgres read model instead of only exercising fake-read-model
   contract tests.
8. Whether stream topics can drift from polling route sources.
9. Whether legacy local mode still works without Postgres.
10. Whether Postgres-gated tests can falsely pass without a DSN.

## Definition Of Ready For Implementation

This plan is ready to execute when adversarial review confirms:

1. The slice order preserves the approved Wave 2 migration boundaries.
2. Each prior Wave 2 review finding has a concrete task and verification
   gate.
3. The implementation can start without another planning round.
