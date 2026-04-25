---
id: DESIGN-0023
title: Headless control plane Wave 2 runtime projector design
version: 1.0.0
status: draft
created: 2026-04-25
last_amended: 2026-04-25
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Headless Control Plane Wave 2 Runtime Projector Design

## Purpose

This design defines the next Wave 2 slice after the legacy bridge and
tailer. The slice proves the first real projection path from
`system.outbox_event` into Postgres read tables without pivoting
`/api/v1` routes or expanding into every domain.

The goal is narrow by design:

```text
legacy bridge outbox events -> runtime projector -> runtime read tables
-> projection checkpoint/source status -> readiness evidence
```

This slice must not materialize non-runtime domains, introduce governed
writes, change web routing, or make legacy local startup require
Postgres.

## Scope

Included:

1. A runtime projector that consumes deterministic legacy bridge outbox
   events for the `runtime` and `control_posture` domains.
2. Materialization into existing tables:
   - `runtime.runtime_heartbeat`
   - `runtime.control_posture_snapshot`
   - `runtime.control_posture_blocker`
3. Projection checkpoint persistence through the existing projection
   state repository.
4. Source-status `projected_watermark` advancement for only the source
   families actually projected by this slice.
5. Derived domain status persistence for diagnostics.
6. Unit tests for mapping, idempotency, checkpoint behavior, unknown
   events, and readiness transitions.
7. Real Postgres tests for transaction rollback, reruns, checkpoint
   resume, and source-status watermark updates.

Excluded:

1. `/api/v1` route pivots or read-router changes.
2. SSE topic pivots.
3. Portfolio, validation, incident, document, investigation, command,
   scheduler, and market-day projectors.
4. Stable `POST /api/v1/commands`, command sessions, incident
   acknowledgement commands, or replay creation commands.
5. New migrations unless an implementation review proves an existing
   table cannot safely support the narrow runtime projection.

## Architecture

Add a small projector module under `tradingx.controlplane` rather than
folding projector logic into the bridge. The bridge is responsible for
observing legacy source state and appending source events. The projector
is responsible for consuming outbox events, writing domain tables, and
recording projection progress.

Proposed module ownership:

- `src/tradingx/controlplane/projectors.py`: pure projector contracts,
  runtime projector mapping, projector run results, and small helper
  functions.
- `src/tradingx/persistence/repositories/projection_state.py`: remains
  the checkpoint/source-status/outbox state boundary.
- `src/tradingx/persistence/repositories/runtime_projection.py` or an
  equivalent narrow write boundary: owns SQL writes to runtime read
  tables if the existing repositories stay read-only.
- `tests/unit/test_controlplane_runtime_projector.py`: pure behavior
  and fake-repository tests.
- `tests/integration/test_controlplane_postgres_runtime_projector.py`:
  guarded real Postgres proof.

The implementation should prefer concrete, source-family-specific
mapping functions over a broad generic framework. A generic projector
runner can emerge later after a second domain proves the pattern.

## Event Selection

The runtime projector should process only bridge outbox events whose
payload envelope includes:

- `domain_name` in `{"runtime", "control_posture"}`
- a known `source_family`
- a stable `source_identity`
- a stable `source_event_id`
- `source_watermark`
- `payload`
- `metadata`

Known source families for this slice:

- `runtime_host`
- `service_cycles`
- `runtime_portfolio_plans`
- `market_sessions`
- `market_automation_runs`
- `market_day_schedules`
- `daily_digests`
- `historical_warmups`
- `strategy_activations`
- `opportunity_selections`
- `blueprint_activation`
- `live_config_env`
- `operator_control_state`
- `operator_sleeve_halts`
- `market_data_posture`

The first implementation should only claim projected readiness for the
families it truly maps. Unknown or deferred families should be skipped
with explicit metadata and must not advance `projected_watermark`.

## Runtime Heartbeat Projection

`runtime.runtime_heartbeat` is the first concrete runtime read table.
It should be built from event evidence that already exists in the bridge
outbox:

- `service_cycles` provides cycle completion, equity/cash fields,
  open-position symbols, cycle status, and source references.
- `opportunity_selections`, `strategy_activations`, and
  `historical_warmups` provide decision and boot/evaluation evidence.
- `runtime_host` provides runtime status when a runtime-host artifact is
  available.

The first projector does not need to reproduce the entire local
`RuntimeHeartbeatSnapshot` response model. It should store a durable,
queryable heartbeat record with:

- `heartbeat_id`: deterministic, source-derived ID.
- `runtime_instance_id`: nullable until runtime instances are modeled.
- `observed_at_utc`: event occurrence time or the best durable source
  timestamp.
- `heartbeat_state`: derived coarse state such as `running`, `idle`,
  `blocked`, `waiting`, or `unknown`.
- `scheduler_cadence_seconds`: copied from payload/config evidence when
  available.
- `stream_state`: optional state text for later stream parity.
- `stale_after_utc`: derived from observed time plus cadence when
  available.
- `source_ref`: source identity plus event ID.
- `payload_json`: original event envelope plus projection metadata.

The mapping should be conservative. If a required field is missing, the
row may still be written with `unknown`-style values, but readiness must
not be claimed for that source unless the source status remains
complete and explicitly projected.

## Control Posture Projection

`runtime.control_posture_snapshot` and
`runtime.control_posture_blocker` are the second concrete runtime read
surface. They should project from:

- `live_config_env`
- `operator_control_state`
- `operator_sleeve_halts`
- `market_data_posture`

The first version should persist a snapshot for each material change in
the source facts. It should compute:

- `posture_id`: deterministic hash of source family, source event ID,
  and state fingerprint.
- `observed_at_utc`: event occurrence time.
- `requested_mode`: from config or market-data posture payload.
- `effective_mode`: fail-closed effective mode.
- `live_allowed`: false unless all live-enable facts are explicitly
  satisfied.
- `governance_status`: `blocked`, `paper_only`, `live_allowed`, or
  `unknown`.
- `blocker_count`, `explicit_blocker_codes`,
  `fail_closed_reason_codes`.
- `resource_version`: stable monotonic version per changed fingerprint.
- `state_fingerprint`: canonical hash of posture facts and blockers.
- `payload_hash`: canonical hash of stored payload.

No-op refreshes should not churn versions when the full fingerprint is
unchanged. If implementing version reuse is too large for the first
slice, the plan must explicitly limit route-readiness claims and add a
follow-up blocker before any route pivot.

## Checkpoint And Source Status

The runtime projector should have a projection name such as
`runtime_projection`. A run should:

1. Load the last checkpoint.
2. Read outbox events after the checkpoint in deterministic order.
3. Project supported events inside a transaction.
4. Save the checkpoint after successful writes.
5. Update source statuses for projected source families:
   - `projected_watermark` equals the latest fully projected
     `source_watermark` for that source.
   - `lag_seconds` is calculated only when enough timestamps exist.
   - `metadata.last_projected_outbox_event_id` records the checkpoint
     position.
6. Optionally persist derived domain status for diagnostics.

Partial batches must roll back. A conflict or mapper error must not
advance checkpoint or source-status watermarks.

## Idempotency

Projector writes must be idempotent under rerun. Reprocessing the same
outbox rows must not duplicate runtime rows, blockers, checkpoints, or
source-status evidence.

Natural keys:

- Runtime heartbeat rows use deterministic heartbeat IDs derived from
  source identity and source event ID.
- Control posture snapshots use deterministic posture IDs derived from
  source facts and fingerprint.
- Control posture blockers use deterministic blocker IDs derived from
  posture ID and blocker code.

If the same natural key appears with different payload content, the
projector should surface a redacted conflict instead of silently
rewriting historical state.

## Readiness

This slice may make a filtered runtime readiness evaluation pass only
for the source families it truly projects. It must not claim the full
runtime domain is router-ready unless all runtime requirements from the
bridge inventory have matching `projected_watermark` values, fresh
active write-path evidence, and no source blockers.

The plan must include tests showing:

1. Runtime readiness is blocked before projection because source
   statuses are unprojected.
2. A filtered set of projected source families stops reporting
   `unprojected_sources` only after projector success.
3. Stale bridge freshness still blocks readiness even when
   `projected_watermark` has caught up.
4. Deferred or unmapped runtime families remain blockers for full-domain
   routing.

## CLI And Runner Shape

The first slice may expose an explicit module entrypoint such as:

```bash
uv run python -m tradingx.controlplane.projectors --runtime --once
uv run python -m tradingx.controlplane.projectors --runtime --batch-size 250
```

The command should require a Postgres DSN for write modes and should not
run during legacy web startup. A future runner mode can loop or process
all domains after another projector proves the pattern.

## Testing And Verification

Required local gates:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_runtime_projector.py tests/integration/test_controlplane_postgres_runtime_projector.py tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_runtime_projector.py -q
uv run pytest tests/unit/test_controlplane_projection_state_contracts.py tests/unit/test_controlplane_legacy_bridge.py -q
uv run pytest tests/unit/test_web_app.py::test_legacy_local_web_paths_do_not_construct_postgres -q
python3 scripts/check_index.py
git diff --check
```

Guarded real Postgres gate:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py tests/integration/test_controlplane_postgres_runtime_projector.py -q
```

GitHub Actions may remain blocked before runner startup by account
billing or spending-limit status. That must be recorded as CI
infrastructure evidence, not as passing or failing code evidence.

## Review Questions

Before implementation, adversarial review should challenge:

1. Whether this slice is still too broad for a first projector.
2. Whether unsupported runtime families can accidentally be marked
   projected.
3. Whether source-status `projected_watermark` can advance before all
   writes for that source are durable.
4. Whether checkpoint order can skip or replay events incorrectly.
5. Whether reruns can duplicate heartbeat, posture, or blocker rows.
6. Whether changed projected payloads are detected as conflicts.
7. Whether control-posture resource versions churn on no-op refreshes.
8. Whether missing bridge freshness still blocks readiness.
9. Whether the projector accidentally becomes a read router or route
   pivot.
10. Whether legacy local startup remains Postgres-free.

## Definition Of Done

This design is ready to become an implementation plan when:

1. The user approves the narrow runtime-projector scope.
2. The implementation plan lists exact tests before production code.
3. The plan includes real Postgres proof for idempotency, rollback,
   checkpoint resume, and source-status watermark updates.
4. The plan explicitly keeps route pivots, stream pivots, and governed
   writes out of scope.
