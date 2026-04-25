---
id: PLAN-0019
title: Headless control plane Wave 2 Postgres runtime projector plan
version: 1.0.0
status: draft
created: 2026-04-25
last_amended: 2026-04-25
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Headless Control Plane Wave 2 Postgres Runtime Projector Plan

## Purpose

This plan defines the next executable Wave 2 slice after `PLAN-0018`:
build the first narrow domain projector that consumes deterministic
legacy bridge outbox events and materializes existing runtime Postgres
read tables.

The slice proves this path:

```text
legacy bridge outbox events -> runtime projector -> runtime read tables
-> projection checkpoint/source status -> readiness evidence
```

It does not pivot `/api/v1`, does not introduce a read router, and does
not claim full runtime-domain readiness until every required runtime
source has a matching projected watermark.

## Authority

- `DESIGN-0023`: `docs/superpowers/specs/2026-04-25-wave2-postgres-runtime-projector-design.md`
- `PLAN-0013`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `PLAN-0014`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
- `PLAN-0018`: `docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `ADR-0025`: `docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md`

## Current State

Already complete:

1. `system.outbox_event`, `system.projection_checkpoint`,
   `system.domain_projection_source_status`, and
   `system.domain_projection_status` exist.
2. `runtime.runtime_heartbeat`, `runtime.control_posture_snapshot`, and
   `runtime.control_posture_blocker` exist.
3. The legacy bridge emits deterministic outbox envelopes and updates
   source-status rows without advancing `projected_watermark`.
4. Readiness helpers block on unprojected sources, stale sources,
   lagging sources, missing initial import, inactive write path, and
   explicit not-ready rows.
5. Existing Postgres read repositories can read runtime heartbeats,
   control-posture snapshots, blockers, projection statuses, and public
   timeline events.

Still missing:

1. A repository boundary for ordered outbox reads by projectors.
2. A write boundary for runtime read-table materialization.
3. Pure mapping from bridge event envelopes to runtime rows.
4. Idempotent runtime/control-posture upserts with conflict detection.
5. A projector runner that updates checkpoints and projected
   source-status watermarks transactionally.
6. Real Postgres proof that reruns, rollbacks, checkpoint resume, and
   readiness transitions behave correctly.

## Non-Negotiable Locks

1. Legacy local mode remains database-free. Importing web modules,
   creating default local web components, and serving legacy routes must
   not instantiate Postgres or the projector.
2. No `/api/v1` route pivots or SSE pivots in this slice.
3. No `PostgresControlPlaneReadModel` or domain-aware read router in
   this slice.
4. No portfolio, validation, incident, document, investigation,
   command, scheduler, or market-day projector work.
5. No stable governed write routes such as `POST /api/v1/commands`.
6. Projector code must consume `system.outbox_event`; it must not
   reread legacy files, config, or SQLite sources directly.
7. Runtime write SQL belongs behind a repository boundary, not inside
   FastAPI route code or pure mapper functions.
8. `last_outbox_event_id` must not be treated as a sortable cursor.
   Outbox reads must order by `created_at_utc ASC, outbox_event_id ASC`
   and checkpoint that ordered cursor in metadata.
9. Unsupported source families must not advance `projected_watermark`.
10. A partial batch failure must not advance checkpoints, source-status
    watermarks, or derived domain status.

## Out Of Scope

- full parity with `LocalWebReadModel.build_runtime_heartbeat_snapshot`
- route or router changes
- SSE parity
- public timeline writes beyond what existing read SQL derives from
  runtime tables
- scheduler and market-day table materialization
- runtime instance modeling beyond nullable `runtime_instance_id`
- incident, portfolio, validation, document, investigation, command,
  and access projectors
- frontend changes
- cloud or local compose changes

## Implementation Shape

### Control-plane projector module

Add `src/tradingx/controlplane/projectors.py` with pure contracts and
runtime projector orchestration:

- `OutboxCursor`: ordered cursor with `created_at_utc` and
  `outbox_event_id`.
- `RuntimeProjectionBatchResult`: counts for seen, projected, skipped,
  conflicts, checkpoint position, and source watermark updates.
- `RuntimeProjector`: consumes repository protocols and clock, runs one
  bounded batch, and leaves looping to future work.
- Pure mapper functions for:
  - runtime heartbeat rows
  - control-posture snapshots
  - control-posture blockers
  - source-status projected-watermark updates

Keep mapper functions independent from SQLAlchemy, FastAPI, and legacy
filesystem adapters.

Add `OutboxProjectionEvent` to
`src/tradingx/controlplane/repositories.py`, not `projectors.py`, so the
repository layer can return a projection DTO without importing projector
orchestration and creating a circular dependency.

### Projection-state repository extension

Extend `src/tradingx/persistence/repositories/projection_state.py` with
an ordered read method:

```python
list_outbox_events_after(
    *,
    cursor_created_at_utc: datetime | None,
    cursor_outbox_event_id: str | None,
    aggregate_types: tuple[str, ...],
    batch_size: int,
) -> tuple[repositories.OutboxProjectionEvent, ...]
```

The SQL must:

1. Filter `aggregate_type IN ('runtime', 'control_posture')`.
2. Order by `created_at_utc ASC, outbox_event_id ASC`.
3. Use an exclusive cursor:

```sql
created_at_utc > :cursor_created_at_utc
OR (
  created_at_utc = :cursor_created_at_utc
  AND outbox_event_id > :cursor_outbox_event_id
)
```

4. Bound `batch_size`.

Checkpoint metadata must store:

- `cursor_created_at_utc`
- `cursor_outbox_event_id`
- `last_projected_dedupe_key`
- `supported_source_families`
- `skipped_source_families`

If an existing checkpoint has `last_outbox_event_id` but no cursor
metadata, the repository or projector must resolve the event's
`created_at_utc` before resuming. If resolution fails, the projector
must stop with a redacted error rather than guessing.

### Runtime materialization repository

Add `src/tradingx/persistence/repositories/runtime_projection.py` or an
equivalent narrow write boundary with transaction-bound construction:

- `upsert_runtime_heartbeat(record)`
- `upsert_control_posture_snapshot(record)`
- `replace_control_posture_blockers(posture_id, blockers)`
- `get_latest_control_posture_snapshot()`

The repository should accept either an engine or an existing
transaction connection. The projector run must create both the
projection-state repository view and the runtime materialization
repository view from the same `engine.begin()` connection, or add an
explicit transaction coordinator that does that. It must not use nested
independent `engine.begin()` calls that can commit one repository while
rolling back the other.

The shared transaction must include:

1. runtime table writes
2. source-status projected-watermark updates
3. checkpoint save
4. derived domain-status save, if written

Natural-key conflicts must be explicit:

- Existing heartbeat with same `heartbeat_id` and same payload hash:
  idempotent success.
- Existing heartbeat with same `heartbeat_id` and different payload or
  event metadata: redacted conflict.
- Existing control-posture snapshot with same `posture_id` and same
  `state_fingerprint`/`payload_hash`: idempotent success.
- Existing snapshot with same `posture_id` and different fingerprint or
  payload hash: redacted conflict.

### Supported source families

The first implementation maps only source families that can produce
durable runtime/control-posture rows without rereading legacy sources:

Runtime heartbeat candidates:

- `service_cycles`
- `runtime_host`
- `opportunity_selections`
- `strategy_activations`
- `historical_warmups`

Control posture candidates:

- `live_config_env`
- `operator_control_state`
- `operator_sleeve_halts`
- `market_data_posture`

If an event belongs to `runtime` or `control_posture` but its source
family is not in the supported set, the projector records skipped
metadata but does not advance `projected_watermark` for that source.

## Mapping Rules

### Runtime heartbeat

For a supported runtime event, write one durable heartbeat row when the
event contains enough evidence to identify an observation time and
state. Conservative defaults are allowed, but they must be explicit in
`payload_json.projection_metadata`.

Required row mapping:

| Column | Mapping |
| --- | --- |
| `heartbeat_id` | `legacy:runtime:<source_family>:<source_identity>:<source_event_id>` hashed or slugged to a stable text ID |
| `runtime_instance_id` | `NULL` until runtime instances are modeled |
| `observed_at_utc` | envelope `occurred_at_utc` |
| `heartbeat_state` | mapped coarse state; default `unknown` |
| `scheduler_cadence_seconds` | payload/config cadence when present, else `NULL` |
| `stream_state` | source stream/status text when present |
| `stale_after_utc` | observed time plus cadence/staleness hint when available |
| `source_ref` | envelope `source_ref` |
| `payload_json` | canonical envelope subset plus projection metadata and payload hash |

The projector must not attempt to reconstruct the whole local
`RuntimeHeartbeatSnapshot` response model in this slice.

### Control posture

For supported control-posture events, compute a canonical posture fact
set and blocker list. Fail closed when live-enable evidence is
incomplete.

Required row mapping:

| Column | Mapping |
| --- | --- |
| `posture_id` | deterministic ID for material posture changes |
| `observed_at_utc` | envelope `occurred_at_utc` |
| `requested_mode` | requested/live mode from payload, else `unknown` |
| `effective_mode` | fail-closed effective mode |
| `live_allowed` | `true` only when all required facts are explicit |
| `governance_status` | `blocked`, `paper_only`, `live_allowed`, or `unknown` |
| `blocker_count` | number of blockers written |
| `explicit_blocker_codes` | canonical blocker-code list |
| `fail_closed_reason_codes` | canonical fail-closed code list |
| `resource_version` | previous latest version plus one only for material fingerprint changes |
| `state_fingerprint` | canonical hash of facts and blockers |
| `payload_hash` | canonical hash of stored payload |
| `payload_json` | facts, blockers, source refs, and projection metadata |

No-op posture refreshes must not insert a new snapshot or increment
`resource_version` when the latest persisted `state_fingerprint` is
unchanged. The projector may still advance checkpoint and projected
source watermark for the source event it safely recognized.

## Checkpoint And Readiness Rules

Use projection name `runtime_projection`.

For each batch:

1. Load checkpoint.
2. Resolve ordered cursor from checkpoint metadata.
3. Read outbox events after cursor.
4. Map and write supported events.
5. Skip unsupported events with explicit metadata.
6. Advance `projected_watermark` only for source identities whose event
   was successfully projected or safely recognized as a no-op by this
   projector. The update must load the existing bridge source-status
   row and preserve its `source_watermark`, `is_mutable`,
   `ready_for_postgres`, `checked_at_utc`, and existing metadata unless
   the projector is intentionally adding projection metadata.
7. Save checkpoint to the last consumed outbox event only after all
   writes and source-status updates succeed.
8. Save derived domain status from readiness only after checkpoint and
   source-status updates succeed.

Readiness tests must distinguish two levels:

- Filtered projector readiness for the supported source-family subset.
- Full runtime-domain readiness, which must remain blocked while
  bridge inventory families are deferred or unmapped.

## Execution Plan

### 0. Baseline

Run before edits:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_legacy_bridge.py tests/unit/test_controlplane_projection_state_contracts.py tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_legacy_bridge.py tests/unit/test_controlplane_projection_state_contracts.py -q
python3 scripts/check_index.py
git diff --check
```

Guarded Postgres baseline:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py -q
```

### 1. First TDD checkpoint

Create `tests/unit/test_controlplane_runtime_projector.py` before
production code. The first failing tests must cover:

1. Outbox cursor ordering by `created_at_utc, outbox_event_id`, not UUID
   or dedupe key.
2. Runtime heartbeat mapper produces stable IDs and conservative
   unknown-state defaults.
3. Control-posture mapper fails closed when live evidence is incomplete.
4. No-op posture refresh does not create a new material snapshot.
5. Unsupported source family is skipped and does not advance
   `projected_watermark`.
6. Supported source family advances projected watermark only after
   materialization succeeds.
7. Projector rerun over the same event is idempotent.
8. Mapper or repository conflict rolls back checkpoint/source-status
   advancement.
9. Filtered readiness can clear `unprojected_sources` while full
   runtime readiness remains blocked by deferred sources.
10. Legacy web startup construction still does not construct the
    projector or Postgres write repositories.

### 2. Pure projector foundation

Implement `src/tradingx/controlplane/projectors.py` with dataclasses,
protocols, pure mappers, canonical hashing, cursor helpers, and
`RuntimeProjector.run_once`.

Keep fake repositories in unit tests simple and stateful enough to
prove rollback and idempotency behavior.

### 3. Projection-state repository read support

Extend `PostgresProjectionStateRepository` and repository contracts with
ordered outbox read support. Add or extend tests in:

- `tests/unit/test_controlplane_projection_state_contracts.py`
- `tests/integration/test_controlplane_postgres_projection_state.py`

Postgres tests must insert three outbox rows with deliberately
non-sortable UUIDs and tied timestamps, then prove the read method
returns deterministic cursor order and resumes after the exact ordered
cursor.

### 4. Runtime materialization repository

Implement the runtime write repository and tests for:

1. Insert heartbeat.
2. Idempotent heartbeat rerun.
3. Heartbeat natural-key conflict.
4. Insert control-posture snapshot and blockers.
5. Replace blockers for the same posture ID without duplicates.
6. No-op posture fingerprint does not churn resource version.
7. Runtime write errors redact DSNs and rollback with projection-state
   writes in the same transaction.

### 5. Runtime projector orchestration

Wire `RuntimeProjector.run_once` to:

1. Load checkpoint.
2. Read a bounded batch.
3. Map supported events.
4. Materialize runtime rows.
5. Upsert projected source statuses.
6. Save checkpoint metadata cursor.
7. Save diagnostic domain status.
8. Return a structured result.

The structured result must separate:

- consumed events
- projected events
- no-op events
- skipped unsupported events
- source statuses advanced
- checkpoint position

### 6. CLI entrypoint

Add a minimal explicit entrypoint:

```bash
TRADINGX_POSTGRES_DSN=postgresql://... \
  uv run python -m tradingx.controlplane.projectors --runtime --once --dsn-env TRADINGX_POSTGRES_DSN
```

The CLI must:

1. Require a DSN for write mode, read through an environment variable
   name by default.
2. Support `--batch-size`.
3. Avoid putting literal DSN values in argv; if `--dsn` is retained for
   tests, help text must prefer `--dsn-env` and errors must redact the
   literal value.
4. Avoid import-time Postgres construction.
5. Not run from web startup.

Looping `--tail` is deferred unless the implementation is already
small and the tests remain focused.

### 7. Real Postgres proof

Create `tests/integration/test_controlplane_postgres_runtime_projector.py`
with guarded tests for:

1. Bridge-seeded runtime event produces one heartbeat row.
2. Bridge-seeded control-posture event produces one snapshot and
   blockers.
3. Rerun produces no duplicates and stable checkpoint metadata.
4. Checkpoint resume skips already consumed events and processes only
   later ordered events.
5. Conflict during materialization rolls back runtime rows,
   checkpoint, source-status projected watermarks, and derived status.
6. Projected source watermark catches up for supported source families.
7. Stale bridge freshness still blocks readiness after projector
   catch-up.
8. Deferred runtime source families keep full-domain readiness blocked.

### 8. Safety closeout

Extend `tests/unit/test_web_app.py` so legacy local web startup fails if
runtime projector construction or runtime write-repository construction
is introduced into default app creation.

Run:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_runtime_projector.py tests/integration/test_controlplane_postgres_runtime_projector.py tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_runtime_projector.py -q
uv run pytest tests/unit/test_controlplane_projection_state_contracts.py tests/unit/test_controlplane_legacy_bridge.py tests/unit/test_web_app.py::test_legacy_local_web_paths_do_not_construct_postgres -q
python3 scripts/check_index.py
git diff --check
```

Guarded Postgres final:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py tests/integration/test_controlplane_postgres_runtime_projector.py -q
```

## Expected Deliverables

Production files:

- `src/tradingx/controlplane/projectors.py`
- `src/tradingx/persistence/repositories/projection_state.py`
- `src/tradingx/persistence/repositories/runtime_projection.py`
- repository contract updates in `src/tradingx/controlplane/repositories.py`
- package exports only where needed

Test files:

- `tests/unit/test_controlplane_runtime_projector.py`
- `tests/unit/test_controlplane_projection_state_contracts.py`
- `tests/unit/test_web_app.py`
- `tests/integration/test_controlplane_postgres_projection_state.py`
- `tests/integration/test_controlplane_postgres_runtime_projector.py`

## Adversarial Review Checklist

Before implementation starts, review must challenge:

1. Whether this plan still smuggles in a route pivot.
2. Whether the projector can accidentally reread legacy artifacts.
3. Whether outbox ordering can skip tied timestamp events.
4. Whether checkpoint metadata can become inconsistent with
   `last_outbox_event_id`.
5. Whether unsupported source families can advance projected
   watermarks.
6. Whether full runtime readiness can pass while deferred sources remain
   unprojected.
7. Whether no-op posture events churn snapshots or resource versions.
8. Whether duplicate events create duplicate heartbeat/blocker rows.
9. Whether conflicts are detected rather than silently overwriting
   history.
10. Whether any new import path makes legacy local startup require
    Postgres.
