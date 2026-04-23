---
id: PLAN-0013
title: Headless control plane Wave 2 Postgres projections execution plan
version: 1.0.0
status: draft
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-23
---

# Headless Control Plane Wave 2 Postgres Projections Execution Plan

## Purpose

Wave 2 moves the operator-critical control-plane read side from local
artifact adapters toward Postgres-backed canonical state. Wave 1 created
the stable `/api/v1` read contracts in the existing FastAPI app. Wave 2
must give those contracts a durable operational store, projection
pipeline, and legacy history bridge without promoting governed writes
before Wave 3.

The result should be a production-grade storage foundation that the web
app can target locally and in cloud staging, while the runtime worker and
job-worker split remain scheduled for later waves.

## Authority

- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `DESIGN-0020`: `docs/architecture/TradingX_Frontend_Design.md`
- `DESIGN-0021`: `docs/architecture/TradingX_Dashboard_And_Design_System.md`
- Wave 1 handoff: `docs/superpowers/plans/2026-04-23-headless-control-plane-wave1-review-handoff.md`
- Broad plan: `docs/superpowers/plans/2026-04-23-headless-control-plane-implementation-plan.md`
- Gate 4 signing authority: `docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md`

## Scope

Wave 2 includes:

1. Postgres dependency, configuration, connection management, and local
   database bootstrap.
2. Alembic-backed schema migrations for the `access`, `commanding`,
   `runtime`, `incidents`, `portfolio`, `validation`, `investigations`,
   `documents`, and `system` schemas.
3. Canonical tables for command/session summaries, runtime state,
   control posture snapshots, incidents, portfolio analytics,
   validation metadata, replay/investigation indexes, document indexes,
   outbox events, and projection checkpoints.
4. Repository interfaces and Postgres implementations for Wave 1 read
   routes.
5. Deterministic legacy bridge/backfill from current artifacts,
   operator-control files, and SQLite OMS journal data into canonical
   tables.
6. A projector runner that materializes canonical read models from
   source events and records checkpoints.
7. `/api/v1` read-route pivoting to Postgres-backed read models when the
   canonical projection exists and is healthy.
8. Contract, unit, migration, backfill, and local-stack verification.

Wave 2 does not include:

1. Stable `POST /api/v1/commands`.
2. Stable `/api/v1/command-sessions`.
3. Final command-session proof/signature semantics.
4. Runtime worker split or lease epoch fencing.
5. Job workers for asynchronous replay, validation, or analytics
   execution.
6. Frontend redesign work.

## Review Locks

These constraints are intentionally strict because they are the areas
most likely to create implementation drift:

1. **Read-side stability only.** Wave 2 may store command/session
   summaries, but `/api/v1/commands` and `/api/v1/command-sessions`
   remain hidden, provisional, and excluded from OpenAPI until Wave 3.
2. **No second write model.** Incident acknowledgement, replay creation,
   and command-session lifecycle remain deferred as governed writes.
   Wave 2 may create storage for them but must not expose helper POSTs.
3. **No split-brain history.** A route may pivot to Postgres only when
   its current projection and historical bridge/backfill are both
   available for that domain.
4. **No frontend artifact dependency.** The frontend-facing `/api/v1`
   contract must not require consumers to parse artifact-shaped payloads.
5. **Control posture stays fail-closed.** Missing governance approval
   remains a first-class blocker in Postgres snapshots and API payloads.
6. **SSE command topic stays absent.** `GET /api/v1/stream` must not
   expose `commands` until the Wave 3 command lifecycle is stable.
7. **Backfill is idempotent.** Re-running the bridge must not duplicate
   command, runtime, incident, portfolio, validation, replay, or document
   rows.
8. **Local remains usable.** The existing local appliance must still run
   with legacy stores while Postgres mode is being introduced.

## Target Source Layout

Add the storage and projection foundation without forcing a broad
rewrite:

```text
src/tradingx/
+-- controlplane/
|   +-- __init__.py
|   +-- readmodels.py
|   +-- projections.py
|   +-- legacy_bridge.py
|   +-- repositories.py
+-- persistence/
|   +-- __init__.py
|   +-- postgres.py
|   +-- migrations/
|   |   +-- env.py
|   |   +-- versions/
|   +-- repositories/
|   |   +-- __init__.py
|   |   +-- commanding.py
|   |   +-- runtime.py
|   |   +-- incidents.py
|   |   +-- portfolio.py
|   |   +-- validation.py
|   |   +-- investigations.py
|   |   +-- documents.py
|   |   +-- system.py
|   +-- outbox.py
+-- web/
    +-- app.py
    +-- runtime.py
```

The existing `src/tradingx/web/readmodels.py` remains the legacy source
adapter for this wave. The new control-plane read model should wrap
Postgres repositories and preserve the Wave 1 response envelope.

## Dependency And Tooling Decisions

Add production-grade Postgres tooling:

- `sqlalchemy>=2.0,<3`
- `psycopg[binary]>=3.2,<4`
- `alembic>=1.13,<2`

Keep `uv` as the package manager. Use SQLAlchemy Core for migrations,
repositories, and explicit SQL first; ORM models may be added later only
where they simplify repeated domain mapping.

Testing strategy:

- unit tests use repository fakes where persistence behavior is not the
  subject under test
- migration/backfill tests run against a real Postgres DSN from
  `TRADINGX_TEST_POSTGRES_DSN`
- tests that require Postgres skip with a clear reason when the DSN is
  absent
- contract tests continue to run without Postgres by exercising legacy
  mode, plus a new Postgres-backed contract subset when the DSN exists

## Configuration Model

Add configuration fields:

- `TRADINGX_POSTGRES_DSN`: Postgres connection URL
- `TRADINGX_CONTROL_PLANE_STORE`: `legacy` or `postgres`
- `TRADINGX_POSTGRES_REQUIRED`: fail startup if Postgres is unavailable
- `TRADINGX_PROJECTION_MODE`: `disabled`, `inline`, or `runner`
- `TRADINGX_PROJECTION_BATCH_SIZE`: default `250`
- `TRADINGX_LEGACY_BACKFILL_ENABLED`: default `false`
- `TRADINGX_LEGACY_BACKFILL_BATCH_SIZE`: default `500`

Default local behavior remains `legacy` until the operator explicitly
selects Postgres mode. CI can run legacy tests without a database, while
Postgres-specific verification runs with the test DSN.

Cloud/staging behavior should set:

- `TRADINGX_CONTROL_PLANE_STORE=postgres`
- `TRADINGX_POSTGRES_REQUIRED=true`
- `TRADINGX_PROJECTION_MODE=runner`

## Schema Plan

### `access`

Create storage now; stable session behavior remains Wave 3.

- `operator_account`
  - `operator_account_id` primary key
  - `display_name`
  - `auth_subject`
  - `status`
  - `created_at_utc`
  - `updated_at_utc`
- `operator_role_binding`
  - `binding_id` primary key
  - `operator_account_id`
  - `role_name`
  - `scope`
  - `granted_at_utc`
  - `revoked_at_utc`
- `command_session`
  - `command_session_id` primary key
  - `operator_account_id`
  - `status`
  - `issued_at_utc`
  - `expires_at_utc`
  - `refreshed_at_utc`
  - `revoked_at_utc`
  - `session_token_hash`
  - `proof_public_ref`
  - `metadata_json`
- `command_session_event`
  - `event_id` primary key
  - `command_session_id`
  - `event_type`
  - `occurred_at_utc`
  - `actor_ref`
  - `reason`
  - `metadata_json`

### `commanding`

Create canonical durable command read-side tables. Do not expose stable
write routes in this wave.

- `command`
  - `command_id` primary key
  - `job_id`
  - `command_type`
  - `lifecycle_state`
  - `target_resource_type`
  - `target_resource_id`
  - `expected_resource_version`
  - `expected_state`
  - `requested_transition`
  - `requested_by`
  - `command_session_id`
  - `idempotency_key_hash`
  - `request_hash`
  - `created_at_utc`
  - `accepted_at_utc`
  - `started_at_utc`
  - `completed_at_utc`
  - `error_code`
  - `error_message`
  - `payload_json`
- `command_attempt`
  - `attempt_id` primary key
  - `command_id`
  - `attempt_number`
  - `received_at_utc`
  - `remote_addr_hash`
  - `verification_state`
  - `rejection_reason`
  - `metadata_json`
- `command_idempotency_record`
  - `idempotency_key_hash` primary key
  - `command_id`
  - `request_hash`
  - `first_seen_at_utc`
  - `last_seen_at_utc`
  - `replay_count`
- `command_event`
  - `event_id` primary key
  - `command_id`
  - `event_seq`
  - `event_type`
  - `occurred_at_utc`
  - `message`
  - `payload_json`
- `command_result_snapshot`
  - `snapshot_id` primary key
  - `command_id`
  - `captured_at_utc`
  - `lifecycle_state`
  - `result_json`

Required indexes:

- unique `(command_id, event_seq)` on `command_event`
- unique `(idempotency_key_hash, request_hash)` on
  `command_idempotency_record`
- `(created_at_utc desc)` on `command`
- `(target_resource_type, target_resource_id, created_at_utc desc)` on
  `command`

### `runtime`

- `runtime_instance`
  - `runtime_instance_id` primary key
  - `environment`
  - `process_ref`
  - `status`
  - `started_at_utc`
  - `stopped_at_utc`
  - `lease_epoch`
  - `metadata_json`
- `runtime_state_snapshot`
  - `snapshot_id` primary key
  - `runtime_instance_id`
  - `observed_at_utc`
  - `status`
  - `current_action`
  - `next_action`
  - `next_evaluation_at_utc`
  - `source_ref`
  - `payload_json`
- `runtime_heartbeat`
  - `heartbeat_id` primary key
  - `runtime_instance_id`
  - `observed_at_utc`
  - `heartbeat_state`
  - `scheduler_cadence_seconds`
  - `stream_state`
  - `stale_after_utc`
  - `source_ref`
  - `payload_json`
- `scheduler_run`
  - `scheduler_run_id` primary key
  - `started_at_utc`
  - `completed_at_utc`
  - `status`
  - `payload_json`
- `market_day_run`
  - `market_day_run_id` primary key
  - `trading_day`
  - `started_at_utc`
  - `completed_at_utc`
  - `status`
  - `payload_json`
- `control_posture_snapshot`
  - `posture_id` primary key
  - `observed_at_utc`
  - `requested_mode`
  - `effective_mode`
  - `live_allowed`
  - `governance_status`
  - `blocker_count`
  - `payload_hash`
  - `payload_json`

### `incidents`

- `incident`
  - `incident_id` primary key
  - `severity`
  - `status`
  - `summary`
  - `opened_at_utc`
  - `updated_at_utc`
  - `resolved_at_utc`
  - `source_ref`
  - `payload_json`
- `incident_event`
  - `incident_event_id` primary key
  - `incident_id`
  - `event_id`
  - `event_type`
  - `occurred_at_utc`
  - `payload_json`
- `incident_acknowledgement`
  - `acknowledgement_id` primary key
  - `incident_id`
  - `command_id`
  - `acknowledged_by`
  - `acknowledged_at_utc`
  - `payload_json`

The acknowledgement table exists for Wave 3 command results. Wave 2 must
not expose a standalone acknowledgement POST.

### `portfolio`

- `portfolio_snapshot`
  - `snapshot_id` primary key
  - `portfolio_id`
  - `portfolio_slice`
  - `captured_at_utc`
  - `market_value`
  - `cash`
  - `gross_exposure`
  - `net_exposure`
  - `realized_pnl`
  - `unrealized_pnl`
  - `payload_json`
- `portfolio_timeseries_point`
  - `point_id` primary key
  - `portfolio_id`
  - `portfolio_slice`
  - `symbol`
  - `captured_at_utc`
  - `metric_name`
  - `metric_value`
  - `payload_json`
- `position_snapshot`
  - `position_snapshot_id` primary key
  - `snapshot_id`
  - `symbol`
  - `quantity`
  - `market_value`
  - `cost_basis`
  - `realized_pnl`
  - `unrealized_pnl`
  - `weight`
  - `payload_json`
- `exposure_snapshot`
  - `exposure_snapshot_id` primary key
  - `snapshot_id`
  - `dimension`
  - `bucket`
  - `gross_exposure`
  - `net_exposure`
  - `weight`
  - `payload_json`
- `benchmark_timeseries_point`
  - `point_id` primary key
  - `benchmark_id`
  - `captured_at_utc`
  - `metric_name`
  - `metric_value`
  - `payload_json`
- `attribution_snapshot`
  - `attribution_id` primary key
  - `snapshot_id`
  - `dimension`
  - `bucket`
  - `contribution_pnl`
  - `contribution_return`
  - `payload_json`
- `execution_quality_snapshot`
  - `execution_quality_id` primary key
  - `captured_at_utc`
  - `symbol`
  - `order_count`
  - `fill_count`
  - `average_slippage_bps`
  - `reject_count`
  - `payload_json`

### `validation`

- `validation_run`
- `validation_candidate`
- `validation_criterion_result`
- `validation_readiness_blocker`
- `pbo_report`
- `cpcv_cohort`

Each table must include a stable id, generated/captured timestamp,
source reference, status, and `payload_json`. Criterion results must
store effective tri-state status after legacy `null` derivation.

### `investigations`

- `replay_run`
- `replay_event`
- `investigation_workspace`
- `drift_analysis_snapshot`

Replay ids returned by `GET /api/v1/investigations` must be fetchable by
`GET /api/v1/replays/{replay_id}` after projection.

### `documents`

- `document`
- `document_revision`
- `document_object_ref`

Postgres stores indexes and retrieval references. Large immutable
payloads remain in artifacts/object storage until Wave 6 introduces the
full object-store profile.

### `system`

- `outbox_event`
  - `outbox_event_id` primary key
  - `aggregate_type`
  - `aggregate_id`
  - `event_type`
  - `event_version`
  - `occurred_at_utc`
  - `dedupe_key`
  - `payload_json`
  - `created_at_utc`
  - `published_at_utc`
- `projection_checkpoint`
  - `projection_name` primary key
  - `last_outbox_event_id`
  - `last_processed_at_utc`
  - `source_watermark`
  - `status`
  - `metadata_json`

`outbox_event.published_at_utc` is for optional external fanout. Projector
progress must be tracked by `projection_checkpoint`, not by a single
processed flag on the event, because multiple projectors can consume the
same event independently.

Wave 2 may add `system.legacy_import_batch` as an implementation-support
table for bridge auditability. If added, it must record source kind,
source path or DSN, started/completed timestamps, counts, and checksum
summary.

## Projection And Backfill Design

### Event flow

1. Legacy adapters read current artifact, operator-control, and SQLite
   journal sources.
2. The bridge normalizes each source record into an idempotent domain
   event.
3. Domain events are inserted into `system.outbox_event` with a stable
   `dedupe_key`.
4. Projectors consume unprocessed outbox events in order and update
   canonical tables.
5. Each projector commits its `projection_checkpoint` only after all
   writes in the batch succeed.

### Required projectors

- `runtime_projection`: runtime snapshots, heartbeat history, control
  posture snapshots
- `incident_projection`: incidents and operator timeline events
- `portfolio_projection`: portfolio workspace, positions, performance,
  exposure, attribution, execution quality
- `validation_projection`: readiness, candidate criteria, PBO/CPCV
  report indexes
- `investigation_projection`: replay indexes, replay events,
  investigation workspaces
- `document_projection`: document index and revision references
- `commanding_projection`: command/session/audit summaries only, with
  stable write behavior deferred

### Legacy source coverage

The bridge must cover at least:

- operator platform artifact directories under `artifacts/operator_platform`
- paper-loop lifecycle and service-cycle artifacts under
  `artifacts/paper_loop`
- validation reports, promotion packages, PBO reports, CPCV records, and
  replay summaries under `artifacts/validation`
- SQLite OMS journal events from `data/journal.db`
- operator-control state files and kill-switch markers
- document/report files currently listed by Wave 1 read models

Each source adapter must expose:

- source kind
- source identity
- observed timestamp
- stable dedupe key
- canonical event type
- payload

## `/api/v1` Pivot Plan

Route pivoting must be domain-by-domain and guarded by tests:

1. `documents`: pivot first because it is index-like and low risk.
2. `incidents` and `events`: pivot after incident/timeline bridge is
   proven idempotent.
3. `runtime` and `runtime/heartbeats`: pivot after heartbeat freshness
   and stale-state tests pass.
4. `control-posture`: pivot after governance blocker parity and
   fail-closed tests pass.
5. `validation`: pivot after candidate/criterion tri-state and report
   history tests pass.
6. `portfolio`: pivot after positions, P&L, benchmark, exposure,
   attribution, and execution-quality projections are populated.
7. `investigations` and `replays`: pivot after list/detail id
   consistency is tested.
8. `commands` read side: store and test summaries, but do not promote
   the route family to stable or OpenAPI-visible until Wave 3.

Every pivot must preserve the Wave 1 envelope:

```json
{
  "request_id": "req_...",
  "generated_at": "2026-04-23T15:00:00Z",
  "data": {}
}
```

## Execution Workstreams

### Workstream A: Persistence foundation

1. Add Postgres/Alembic dependencies.
2. Add `TradingConfig` fields for Postgres and projection settings.
3. Add `src/tradingx/persistence/postgres.py` with engine/session
   factories, health checks, timeout settings, and redacted DSN logging.
4. Add Alembic configuration and first migration creating schemas and
   tables.
5. Add migration tests for upgrade and schema presence.

Exit criteria:

- migrations run against a real Postgres database
- config can distinguish legacy mode, optional Postgres mode, and
  required Postgres mode
- local app still starts in legacy mode

### Workstream B: Repository contracts

1. Define protocol-style repository interfaces in
   `src/tradingx/controlplane/repositories.py`.
2. Implement Postgres repositories under
   `src/tradingx/persistence/repositories/`.
3. Add row mappers that return plain dict/dataclass payloads compatible
   with Wave 1 envelopes.
4. Add unit tests for insert/upsert/list/get behavior, idempotency, and
   ordering.

Exit criteria:

- each `/api/v1` read domain has a repository boundary
- repository tests cover pagination/cursor defaults and deterministic
  ordering

### Workstream C: Outbox, checkpoints, and projectors

1. Implement outbox insertion with dedupe-key conflict handling.
2. Implement checkpoint load/save.
3. Implement projector runner entrypoint:
   - `uv run python -m tradingx.controlplane.projections --once`
   - `uv run python -m tradingx.controlplane.projections --loop`
4. Add batch processing and checkpoint resume tests.
5. Add failure tests proving partial batches do not advance the
   checkpoint.

Exit criteria:

- projectors are idempotent
- projection checkpoints survive restart
- projection failures are visible without corrupting read state

### Workstream D: Legacy bridge and backfill

1. Build source adapters for artifact directories, operator-control
   files, and SQLite journal events.
2. Define stable dedupe keys for each source kind.
3. Add a backfill CLI:
   - `uv run python -m tradingx.controlplane.legacy_bridge --once`
   - `uv run python -m tradingx.controlplane.legacy_bridge --since 2026-04-23T00:00:00Z`
   - `uv run python -m tradingx.controlplane.legacy_bridge --dry-run`
4. Add bridge tests with fixture artifacts.
5. Add an idempotency test that runs the same backfill twice and proves
   row counts do not double.

Exit criteria:

- historical command/runtime/operator history is queryable through the
  canonical read path
- read routes are not split between old and new history once pivoted

### Workstream E: API read-model pivot

1. Add `PostgresControlPlaneReadModel`.
2. Extend web component construction to choose legacy or Postgres read
   model based on config.
3. Pivot domains in the order listed above.
4. Add contract tests for legacy mode and Postgres mode.
5. Assert provisional write routes remain hidden from OpenAPI and return
   `503` in both modes.

Exit criteria:

- Wave 1 route shapes remain stable
- Postgres-backed mode produces canonical responses
- `/api/v1/stream` remains read-topic only

### Workstream F: Local dev stack

1. Extend `docker-compose.yml` with `postgres`.
2. Add `.env.postgres.example` or update existing env examples with the
   Postgres/projection variables.
3. Add a local bootstrap command or documented sequence:
   - start Postgres
   - run migrations
   - run legacy bridge
   - run projectors
   - start web app in Postgres mode
4. Keep the broader multi-service stack for Wave 6.

Exit criteria:

- a developer can test Wave 2 locally with Postgres
- the existing local app path still works without Postgres

## Verification Plan

Required for the planning branch:

```bash
python3 scripts/check_index.py
```

Required for Wave 2 implementation:

```bash
uv sync
uv run ruff check src/tradingx tests
uv run mypy src/tradingx
uv run pytest tests/unit/test_postgres_config.py -q
uv run pytest tests/unit/test_controlplane_repositories.py -q
uv run pytest tests/unit/test_controlplane_legacy_bridge.py -q
uv run pytest tests/unit/test_controlplane_projectors.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5432/tradingx_test uv run pytest tests/integration/test_controlplane_postgres_store.py -q
python3 scripts/check_index.py
```

Implementation must also include a small manual local run note in the PR
body showing:

- migration command used
- bridge command used
- projector command used
- `/api/v1/control-posture` and `/api/v1/runtime` checked in Postgres
  mode

## Rollback Plan

Wave 2 must remain reversible at the application level:

1. Set `TRADINGX_CONTROL_PLANE_STORE=legacy`.
2. Stop the projector runner.
3. Keep Postgres data intact for diagnosis.
4. Continue serving `/api/v1` from the Wave 1 legacy adapters.

Database migrations should support downgrade for development, but
production rollback should prefer application-level fallback and forward
fixes over destructive data rollback.

## Implementation Order

1. Persistence dependencies, config, and migrations.
2. Repository interfaces and Postgres repositories.
3. Outbox and projection checkpoints.
4. Legacy bridge/backfill.
5. Projectors.
6. Postgres-backed read model.
7. Domain-by-domain API pivot.
8. Local dev stack updates.
9. Full verification and adversarial-review handoff.

## Parallelization Guidance

Some work can happen in parallel after the migration contract is merged:

- repository implementations by domain
- legacy source adapters by source kind
- projection tests by domain
- local stack documentation

The following must stay sequential:

- schema migration before repositories
- repositories before projectors
- bridge/backfill before route pivot
- route pivot before claiming Wave 2 exit criteria
- stable command/session write APIs must wait for Wave 3

## Definition Of Done

Wave 2 is done when:

1. Postgres schemas and migrations exist for every Wave 2 domain.
2. Outbox events and projection checkpoints exist and are tested.
3. Legacy history backfill is idempotent and covers command, runtime,
   operator, validation, replay, portfolio, incident, and document
   sources relevant to `/api/v1`.
4. `/api/v1` read routes can serve from Postgres mode without changing
   the Wave 1 envelope.
5. Route pivots only occur after the matching history bridge exists.
6. Provisional governed write routes remain hidden and non-integratable.
7. Local development can run the Postgres-backed control-plane read side.
8. Verification commands pass or documented Postgres-gated tests skip
   with a clear missing-DSN reason.

## Adversarial Review Checklist

Reviewers should challenge:

1. Whether any read route can pivot to Postgres before historical bridge
   coverage exists.
2. Whether any helper POST or write-like route sneaks into Wave 2.
3. Whether `/api/v1/stream` exposes command data before Wave 3.
4. Whether control-posture snapshots can contradict top-level
   fail-closed truth.
5. Whether backfill dedupe keys are stable across repeated runs and path
   changes.
6. Whether the schema supports Wave 3 mutation preconditions, including
   `target_resource_type`.
7. Whether Postgres mode can be enabled locally without breaking the
   legacy appliance path.
8. Whether the plan creates hidden dependency on artifact parsing in the
   frontend or mobile clients.
