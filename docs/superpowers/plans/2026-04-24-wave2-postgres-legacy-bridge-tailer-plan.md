---
id: PLAN-0018
title: Headless control plane Wave 2 Postgres legacy bridge and tailer plan
version: 1.0.0
status: draft
created: 2026-04-24
last_amended: 2026-04-24
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-24
---

# Headless Control Plane Wave 2 Postgres Legacy Bridge And Tailer Plan

## Purpose

This plan defines the next executable Wave 2 slice after `PLAN-0017`:
build the legacy bridge and tailer that reads current local TradingX
artifacts, files, and SQLite sources, emits deterministic outbox events,
and updates source-status readiness rows.

The goal is to make current Wave 1 history available as canonical
projection input before domain projectors, Postgres read models, domain
routers, or `/api/v1` route pivots are implemented. This slice must
not materialize final domain read tables, run domain projectors, or make
legacy local mode require Postgres.

## Authority

- `PLAN-0013`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `PLAN-0014`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
- `PLAN-0017`: `docs/superpowers/plans/2026-04-24-wave2-postgres-outbox-checkpoint-readiness-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `ADR-0025`: `docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md`

## Current State

Already complete:

1. Postgres schemas and migration helpers exist.
2. `system.outbox_event`, `system.projection_checkpoint`,
   `system.domain_projection_source_status`, and
   `system.domain_projection_status` exist in the initial migration.
3. `PostgresProjectionStateRepository` can append idempotent outbox
   events, save checkpoints, upsert source statuses, persist derived
   domain status, and prove multi-write rollback.
4. Pure readiness helpers can block domains on missing requirements,
   missing sources, stale sources, unprojected sources, lagging sources,
   incomplete initial import, inactive write path, missing outbox dedupe,
   and explicit not-ready rows.
5. `PostgresControlPlaneRepository` remains read-only and local legacy
   startup is still database-free.

Still missing before projector/router work:

1. A legacy source inventory tied to actual Wave 1 files and read-model
   inputs.
2. Stable source identities and watermarks for every bridge source.
3. Deterministic source-event envelopes and outbox dedupe keys.
4. Bridge commands for one-shot import, bounded repair, tailing, and
   dry-run previews.
5. Source-status updates that mark initial import completion and active
   bridge freshness.
6. Idempotency and freshness tests that prove reruns do not duplicate
   outbox events and stale mutable sources block readiness.

## Non-Negotiable Locks

1. Legacy local mode remains the default. Importing modules, loading
   config, creating the web app, building default local web components,
   and serving legacy routes must not connect to Postgres.
2. No `/api/v1` route pivots to Postgres in this slice.
3. No `PostgresControlPlaneReadModel`, domain read router, SSE parity
   switch, or route-level readiness decision is introduced here.
4. No domain projector materializes runtime, incident, portfolio,
   validation, investigation, document, command, or public timeline read
   tables in this slice. The bridge writes only outbox/source-status
   projection-state surfaces.
5. No stable `POST /api/v1/commands`, stable command sessions, incident
   acknowledgement route, replay creation route, or other governed write
   route is introduced.
6. `system.outbox_event` remains internal projector input. Public
   timeline reads must not consume outbox rows.
7. `system.domain_projection_source_status` remains the readiness
   authority. `system.domain_projection_status` remains a derived
   diagnostic summary.
8. Raw DSNs, passwords, filesystem secrets, and environment secret
   values must not leak through exceptions, reprs, args, chained
   exceptions, dry-run output, logs, or test output.
9. Bridge writes must use `PostgresProjectionStateRepository` and its
   transaction helper, not direct ad hoc inserts into projection-state
   tables.
10. The bridge must be idempotent. Re-running the same import over the
    same source state must not duplicate outbox rows.

## Out Of Scope

- domain read-model projectors
- projector runner orchestration
- `PostgresControlPlaneReadModel`
- domain-aware read router
- `/api/v1` route pivots
- SSE parity
- stable governed command intake
- command-session proof semantics
- frontend changes
- local compose stack
- cloud deployment

## Architecture Approach

Add a bridge module that is source-adapter oriented and does not know
about FastAPI route dispatch:

- `src/tradingx/controlplane/legacy_bridge.py` owns bridge dataclasses,
  source adapters, source discovery, source-event envelope construction,
  backfill/tail orchestration, dry-run previews, and CLI entrypoint.
- `src/tradingx/controlplane/projections.py` may add bridge-specific
  source requirement builders, but pure readiness evaluation remains
  independent of filesystem and Postgres.
- `src/tradingx/persistence/repositories/projection_state.py` remains
  the only SQL write boundary for outbox events, source statuses, and
  derived domain statuses.
- Existing legacy source modules remain the source of truth:
  `FilesystemArtifactStore`, `OperatorControlStore`,
  `SqliteOmsJournal`, `TradingConfig`, and `LocalWebReadModel`-backed
  artifact conventions.

Bridge output is a deterministic `LegacySourceEvent` converted to
`OutboxEventAppendRequest`:

```text
source adapter -> LegacySourceEvent -> outbox append -> source status
```

The bridge may evaluate source readiness and persist derived
`domain_projection_status` after a run, but it must not claim a domain
is router-ready unless later projector slices set `projected_watermark`
to match the bridge source watermark.

## Source Event Contract

Each adapter must emit plain Python values:

- `domain_name`
- `source_family`
- `source_identity`
- `source_event_id`
- `source_watermark`
- `occurred_at_utc`
- `event_family`
- `event_type`
- `resource_type`
- `resource_id`
- `is_mutable`
- `payload`
- `metadata`

`source_event_id` must be stable across reruns for the same logical
legacy record. It must not include process time, random values, absolute
temporary paths, or host-specific details.

`occurred_at_utc` must also be deterministic for a given
`source_event_id`, because outbox idempotency compares it on dedupe-key
conflicts. Adapters must choose timestamps in this order:

1. a durable timestamp field in the source record, such as
   `occurred_at_utc`, `recorded_at_utc`, `updated_at_utc`,
   `generated_at_utc`, `completed_at_utc`, or `sent_at_utc`
2. a durable SQLite timestamp column for row-backed sources
3. a source-specific fixed epoch of `1970-01-01T00:00:00Z` when the
   source has no durable timestamp

Adapters must not use current process observation time as
`occurred_at_utc`. If observation time is useful, it belongs in metadata
as `observed_at_utc`.

`source_watermark` is the latest logical source position observed by
that adapter. For ordered append-only sources it is the latest
`source_event_id`. For mutable snapshot files it is
`<relative-path>:<sha256>`. For SQLite sources it is the latest stable
row identifier plus a payload hash. For config/env posture it is a
canonical hash of the redacted posture fact set.
When source timestamps tie, latest-event selection must use a natural
stable ID tiebreaker so `cycle-10` does not sort behind `cycle-9`.

Do not stamp the adapter-level latest `source_watermark` into every
event payload. Existing outbox payloads must remain stable when a later
source event appears. Event envelopes may include an event-local
watermark for that `source_event_id`; source-status rows carry the
adapter-level latest source watermark.

Outbox request mapping:

| Outbox field | Mapping |
| --- | --- |
| `aggregate_type` | `domain_name` |
| `aggregate_id` | `resource_type/resource_id` |
| `event_type` | `event_type` |
| `event_version` | `1` for this slice |
| `occurred_at_utc` | deterministic durable source timestamp, or the fixed legacy epoch when absent |
| `dedupe_key` | `legacy:<domain>:<source_family>:<source_identity>:<source_event_id>` |
| `payload` | canonical source event envelope plus source metadata |

The payload must include enough provenance for later projectors to
derive read-model rows without re-reading legacy files:

- `domain_name`
- `source_family`
- `source_identity`
- `source_event_id`
- `source_watermark`
- `event_family`
- `resource_type`
- `resource_id`
- `source_ref`
- `payload`
- `metadata`

## Source Inventory

The implementation must start with this source matrix. If an adapter is
deferred, the implementation must include an explicit deferred-source
status row and the affected domain must remain not ready.

| Domain | Source family | Source identity | Inputs | Mutable | Watermark |
| --- | --- | --- | --- | --- | --- |
| runtime | `runtime_host` | `artifact:operator_platform/runtime_host` | `runtime_host/*.json` | yes | file sha over relative path |
| runtime | `service_cycles` | `artifact:paper_loop/service_cycles` | `service_cycles/*.json` | yes | latest cycle id plus payload hash |
| runtime | `runtime_portfolio_plans` | `artifact:paper_loop/runtime_portfolio_plans` | `runtime_portfolio_plans/*.json` | yes | latest plan id plus payload hash |
| runtime | `market_sessions` | `artifact:operator_platform/market_sessions` | `market_sessions/*.json` | yes | latest session id plus payload hash |
| runtime | `market_automation_runs` | `artifact:operator_platform/market_automation_runs` | `market_automation_runs/*.json` | yes | latest run id plus payload hash |
| runtime | `market_day_schedules` | `artifact:operator_platform/market_day_schedules` | `market_day_schedules/*.json` | yes | latest schedule id plus payload hash |
| runtime | `daily_digests` | `artifact:operator_platform/daily_digests` | `daily_digests/*.json` | yes | latest digest id plus payload hash |
| runtime | `historical_warmups` | `artifact:operator_platform/historical_warmups` | `historical_warmups/*.json` | yes | latest warmup id plus payload hash |
| runtime | `strategy_activations` | `artifact:operator_platform/strategy_activations` | `strategy_activations/*.json` | yes | latest activation id plus payload hash |
| runtime | `opportunity_selections` | `artifact:operator_platform/opportunity_selections` | `opportunity_selections/*.json` | yes | latest selection id plus payload hash |
| runtime | `blueprint_activation` | `artifact:operator_platform/blueprint_activation` | `blueprint_activation/*.json` | yes | latest activation id plus payload hash |
| control_posture | `live_config_env` | `config:local` | `TradingConfig` safe summary, live controls, dry-run, manual kill switch, write signing configured, broker credential presence | yes | redacted fact hash |
| control_posture | `operator_control_state` | `data:control/state` | `data/control/state.json`, halt, kill, clearance markers | yes | file tree sha over relative paths |
| control_posture | `operator_sleeve_halts` | `data:control/sleeve_halts` | `data/control/sleeve_halts/*.json` | yes | file tree sha over relative paths |
| control_posture | `market_data_posture` | `runtime:market_data` | configured market-data mode, effective runtime mode alignment, warmup failures, stale/degraded market-data risk controls exposed by Wave 1 sources | yes | fact hash plus latest input event |
| incidents | `operator_alerts` | `artifact:paper_loop/operator_alerts` | `operator_alerts/*.json` | yes | latest alert id plus payload hash |
| incidents | `risk_events` | `artifact:paper_loop/risk_events` | `risk_events/*.json` | yes | latest risk event id plus payload hash |
| incidents | `incident_acknowledgements` | `artifact:operator_platform/incident_acknowledgements` | incident acknowledgement artifacts consumed by `LocalWebReadModel` | yes | latest acknowledgement id plus payload hash |
| portfolio | `trade_intents` | `artifact:paper_loop/trade_intents` | `trade_intents/*.json` | yes | latest intent id plus payload hash |
| portfolio | `orders` | `artifact:paper_loop/orders` | `orders/*.json` | yes | latest order id plus payload hash |
| portfolio | `reconciliation` | `artifact:paper_loop/reconciliation` | `reconciliation/*.json` | yes | latest reconciliation id plus payload hash |
| portfolio | `closed_trades` | `artifact:paper_loop/closed_trades` | `closed_trades/*.json` | yes | latest trade id plus payload hash |
| portfolio | `execution_lifecycles` | `artifact:paper_loop/execution_lifecycles` | `execution_lifecycles/*.json` | yes | latest lifecycle id plus payload hash |
| portfolio | `sleeve_daily_attribution` | `artifact:sleeve_daily_attribution` | `sleeve_daily_attribution/*.json` | yes | latest attribution id plus payload hash |
| portfolio | `sleeve_bootstrap` | `artifact:sleeve_bootstrap` | `sleeve_bootstrap/*.json` | yes | latest allocation id plus payload hash |
| portfolio | `sleeve_position_ledger` | `artifact:sleeve_position_ledger` | `sleeve_position_ledger/*.json` | yes | latest ledger snapshot id plus payload hash |
| portfolio | `residual_reserve` | `artifact:residual_reserve` | `residual_reserve/*.json` | yes | latest reserve id plus payload hash |
| portfolio | `session_open_portfolio_state` | `artifact:session_open_portfolio_state` | session-open portfolio state artifacts | yes | latest record id plus payload hash |
| portfolio | `sleeve_attribution_gaps` | `artifact:sleeve_attribution_gaps` | `sleeve_attribution_gaps/*.json` | yes | latest gap id plus payload hash |
| portfolio | `sleeve_decomposition` | `artifact:sleeve_decomposition` | `sleeve_decomposition/*.json` | yes | latest decomposition id plus payload hash |
| portfolio | `drift_monitor_verdicts` | `artifact:drift_monitor_verdicts` | `drift_monitor_verdicts/*.json` | yes | latest verdict id plus payload hash |
| portfolio | `oms_journal` | `sqlite:data/journal.db` | `oms_journal` rows from `SqliteOmsJournal` | yes | latest row event id plus payload hash |
| portfolio | `approved_weights` | `config:strategy/weights` | approved model weight snapshots | yes | latest snapshot id plus content hash |
| portfolio | `ops_baseline` | `artifact:ops/paper_account_starting_state` | `artifacts/ops/paper_account_starting_state.json` | no | file sha |
| validation | `evaluation_evidence` | `artifact:validation/evaluation_evidence` | `evaluation_evidence/*.json` | yes | latest evidence pack id plus payload hash |
| validation | `validation_reports` | `artifact:validation/validation_reports` | validation reports | yes | latest report id plus payload hash |
| validation | `gate_assessments` | `artifact:validation/gate_assessments` | gate assessments | yes | latest gate assessment id plus payload hash |
| validation | `cpcv_trials` | `artifact:validation/cpcv_trials` | CPCV trial records | yes | latest trial id plus payload hash |
| validation | `cpcv_cohort_windows` | `derived:validation/cpcv_trials/cohort_windows` | derived by grouping `cpcv_trials/*.json` by `cohort_window_id` | yes | derived from the `cpcv_trials` source watermark plus cohort IDs |
| validation | `pbo_reports` | `artifact:validation/pbo_reports` | PBO reports | yes | latest PBO report id plus payload hash |
| validation | `gate3_reports` | `artifact:validation/gate3_reports` | `gate3_reports/*.json` | yes | latest readiness id plus payload hash |
| validation | `gate3_packages` | `artifact:validation/gate3_packages` | `gate3_packages/*.json` | yes | latest package id plus payload hash |
| validation | `validation_sqlite` | `sqlite:data/validation` | current validation SQLite data used by Wave 1 read models, when present | yes | latest row id plus payload hash |
| investigations | `replay_slippage_records` | `artifact:validation/replay_slippage_records` | replay slippage records | yes | latest replay record id plus payload hash |
| investigations | `replay_slippage_summaries` | `artifact:validation/replay_slippage_summaries` | replay slippage summaries | yes | latest replay summary id plus payload hash |
| documents | `handover_sessions` | `repo:docs/handover_sessions` | `docs/handover/SESSIONS/*.md` | yes | file tree sha over relative paths |
| documents | `state_and_index_docs` | `repo:docs/state_index` | `docs/handover/STATE.md`, `docs/INDEX.md` | yes | file tree sha over relative paths |
| documents | `config_proposals` | `repo:config/proposals` | `config/proposals/*.md` | yes | file tree sha over relative paths |
| commands_read_side | `legacy_command_audit` | `sqlite:data/journal.db` | command-like OMS journal rows and existing command/session audit artifacts only | yes | latest row event id plus payload hash |
| events | `legacy_timeline_sources` | `derived:source-events` | bridge source events for runtime, incidents, validation, command read-side, and market-data posture | yes | latest source event id |

Source identities are stable public strings for readiness and tests. Do
not use absolute machine paths as source identities.

For artifact-backed rows, `source_family` must match the exact
`FilesystemArtifactStore` category and directory name unless the row is
explicitly marked as derived.

The implementation must include an inventory test that pins every row in
this matrix and separately asserts that these current Wave 1 read-model
inputs are represented by a source row: `strategy_activations`,
`opportunity_selections`, `blueprint_activation`,
`sleeve_daily_attribution`, `drift_monitor_verdicts`,
`operator_sleeve_halts`, `trade_intents`, `orders`, `reconciliation`,
`daily_digests`, and `incident_acknowledgements`.

## Required Behavior

### Source Discovery And Dry Run

1. `--dry-run` lists source adapters, source identities, event counts,
   latest watermarks, would-write dedupe keys, and readiness effects
   without writing to Postgres.
2. Dry-run output must redact DSNs, credential values, signing secrets,
   API keys, environment secret values, and absolute local filesystem
   prefixes.
3. Missing optional source roots are reported as `missing_sources` for
   affected requirements, not swallowed as success.
4. Empty immutable sources may be represented as imported-but-empty only
   when the plan names that source as optional. Empty mutable required
   sources block readiness until first observed or explicitly deferred.

### Backfill And Incremental Repair

1. `--once` performs a bounded import of all configured source adapters.
2. `--since <timestamp>` imports only events whose `occurred_at_utc` is
   greater than or equal to the provided UTC timestamp. Snapshot sources
   are still evaluated because they may not have event timestamps.
3. Every event append uses `PostgresProjectionStateRepository` so
   dedupe conflicts compare persisted JSONB payloads.
4. Re-running the same backfill over unchanged sources returns existing
   outbox IDs and does not increase outbox row count.
5. If a legacy source record changes under the same stable
   `source_event_id`, the bridge must surface the repository conflict
   with redacted diagnostics instead of mutating history silently.

### Tail Mode

1. `--tail` polls mutable sources on a configurable interval and
   appends new source events.
2. Tail mode must publish `write_path: "active_bridge"` in source-status
   metadata for sources it is actively refreshing.
3. Tail mode must update `checked_at_utc` on each poll, even if no new
   events are discovered, so freshness can be evaluated.
4. Tail mode must stop cleanly when interrupted and must not leave a
   partial batch committed.
5. Tail mode is not a projector runner. It must not write final read
   model tables.

### Source Status

After each adapter run, the bridge upserts
`ProjectionSourceStatusRecord` with:

- `domain_name`
- `source_family`
- `source_identity`
- `source_watermark`
- `projected_watermark`: `NULL` in this slice unless a later projector
  test explicitly injects one
- `lag_seconds`: `NULL` until projectors calculate lag, or `0` only for
  bridge-only source discovery tests that do not claim router readiness
- `is_mutable`
- `ready_for_postgres`: true only when the adapter completed without
  source errors and its initial import is complete
- `checked_at_utc`
- metadata:
  - `initial_import_complete`
  - `write_path`: `"active_bridge"` only in active tail mode, otherwise
    `"backfill"` or `"dry_run"`
  - `source_registry_version`
  - `event_count`
  - `new_event_count`
  - `existing_event_count`
  - `source_root_display`: a logical display reference or repo-relative
    path, never an absolute path
  - `latest_source_event_id`
  - `source_errors`

Persisted metadata, dry-run previews, and logs must never include raw
absolute source roots. When a source lives under `repo_root`,
`artifact_root`, or `data_root`, metadata must store a logical
repository-relative reference such as `artifacts/paper_loop`. When a
test or operator override points outside those roots, metadata must
store a redacted display ref that preserves only the final non-secret
path segment. Path segments containing values such as `secret`, `token`,
`key`, `password`, or configured credential values must be replaced with
`***`.

Derived domain status may be written for diagnostics, but router
readiness must remain blocked until projectors set matching
`projected_watermark`.

### Transactions

Each adapter batch must run through `PostgresProjectionStateRepository`
transaction view:

1. Append all discovered outbox events for the source batch.
2. Upsert that source status.
3. Optionally persist derived domain status.
4. Commit only if the whole source batch succeeds.

Tests must prove a simulated failure after one or more outbox appends
rolls back the appended outbox events and source status update.

### CLI

The module must expose:

```bash
uv run python -m tradingx.controlplane.legacy_bridge --once
uv run python -m tradingx.controlplane.legacy_bridge --since 2026-04-24T00:00:00Z
uv run python -m tradingx.controlplane.legacy_bridge --tail
uv run python -m tradingx.controlplane.legacy_bridge --dry-run
```

Options:

- `--postgres-dsn`: optional override, otherwise config-derived.
- `--artifact-root`: optional source root override for tests.
- `--data-root`: optional source root override for tests.
- `--repo-root`: optional source root override for tests.
- `--domain`: repeatable domain filter.
- `--source-family`: repeatable source filter.
- `--poll-seconds`: tail mode interval.
- `--max-iterations`: test-only tail loop cap.
- `--source-registry-version`: default `legacy-bridge-v1`.

The CLI must fail loudly when a writing mode is requested without a
Postgres DSN. Dry-run may run without a DSN.

## Implementation Tasks

### Task 0: Baseline Verification

Run before edits:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_projection_state_contracts.py tests/integration/test_controlplane_postgres_projection_state.py tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_projection_state_contracts.py tests/unit/test_persistence_namespace.py tests/unit/test_postgres_config.py tests/unit/test_web_app.py::test_legacy_local_web_paths_do_not_construct_postgres -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py -q
python3 scripts/check_index.py
git diff --check
```

If a baseline failure exists, stop and record it separately.

### Task 1: Add Test-First Bridge Contract Coverage

Create:

- `tests/unit/test_controlplane_legacy_bridge.py`

The first tests must prove:

1. `LegacySourceIdentity` rejects empty domain, family, and identity
   values.
2. `LegacySourceEvent` produces deterministic dedupe keys.
3. File snapshot watermarks use relative paths plus SHA-256 content
   hashes, not absolute paths or mtimes alone.
4. Ordered artifact watermarks are deterministic across filesystem
   traversal order.
5. Timestamp-less legacy records use deterministic `occurred_at_utc`
   across reruns and keep process observation time only in metadata.
6. Dry-run previews include event counts and dedupe keys without
   writing to a repository.
7. Secret-looking config/env fields are redacted in previews and
   errors.
8. Absolute source roots and path segments such as
   `tmp/secret-token-fixture` are redacted in previews and source-status
   metadata.
9. Source status metadata distinguishes `dry_run`, `backfill`, and
   `active_bridge` write paths.
10. Missing required source roots produce blocker-style diagnostics.
11. The source inventory exposes the matrix above with stable
   source identities.
12. Inventory tests pin every stable Wave 1 `/api/v1` read-model input
    named in the source inventory section.

Expected red state: imports fail because `legacy_bridge` does not exist.

### Task 2: Add Bridge Dataclasses And Source Inventory

Create:

- `src/tradingx/controlplane/legacy_bridge.py`

Define:

- `LegacySourceIdentity`
- `LegacySourceEvent`
- `LegacySourceWatermark`
- `LegacySourceAdapter`
- `LegacyBridgePreview`
- `LegacyBridgeRunResult`
- `LegacyBridgeSourceResult`
- source inventory constants for the matrix above
- canonical redaction helper for preview/error payloads

Checks:

```bash
uv run pytest tests/unit/test_controlplane_legacy_bridge.py -q
uv run mypy src/tradingx
```

### Task 3: Add Filesystem And SQLite Source Adapters

Implement adapters for:

1. `FilesystemArtifactStore` categories used by stable Wave 1 routes.
2. `OperatorControlStore` state and marker files.
3. `TradingConfig` live config/env posture facts.
4. Market-data posture facts exposed by current runtime/warmup/risk
   sources.
5. Approved weights under `config/strategy/weights`.
6. Ops baseline file `artifacts/ops/paper_account_starting_state.json`.
7. `SqliteOmsJournal` events from `data/journal.db`.
8. Validation SQLite data under `data/validation`, when present.
9. Document index files currently listed by `LocalWebReadModel`.

Tests must use fixture directories and SQLite databases; they must not
depend on the developer machine's real artifacts.

### Task 4: Add Bridge Orchestrator And Source Status Mapping

Implement:

- bridge run coordinator
- domain/source filters
- `since` filtering
- dry-run previews
- source status construction
- source requirement construction for bridge-managed source families
- derived domain status persistence for diagnostics

Tests must prove:

1. successful backfill creates one source status per source identity
2. dry-run creates no outbox or source status writes
3. tail mode sets `write_path: "active_bridge"`
4. one failed adapter does not mark that source ready
5. source requirement evaluation blocks domains until projected
   watermarks catch up

### Task 5: Add CLI Entry Point

Add `if __name__ == "__main__"` support for
`python -m tradingx.controlplane.legacy_bridge`.

Tests must cover argument parsing and safe config behavior without
needing a real Postgres DSN for dry-run.

### Task 6: Add Real Postgres Bridge Integration Tests

Create:

- `tests/integration/test_controlplane_postgres_legacy_bridge.py`

The tests must:

1. skip explicitly without `TRADINGX_TEST_POSTGRES_DSN`
2. reset only guarded `tradingx_test`
3. run migrations
4. run bridge `--once` against fixture sources
5. prove outbox rows are appended with stable dedupe keys
6. rerun the same import, including a timestamp-less source record, and
   prove row counts do not increase and no outbox conflict occurs
7. change a source payload under the same source event ID and prove a
   redacted outbox conflict
8. prove source-status rows are written with correct natural keys and
   metadata
9. prove persisted source-status metadata contains only logical,
   relative, or redacted source-root display refs
10. prove a simulated batch failure rolls back outbox and source-status
   writes
11. prove tail mode updates `checked_at_utc` and `write_path`
12. prove stale mutable source status blocks readiness

### Task 7: Preserve Legacy And Web Contracts

Extend no-Postgres regressions so legacy app creation, default local
web component construction, default startup wiring, and representative
routes still pass when bridge construction and Postgres construction are
monkeypatched to fail loudly.

Do not wire the bridge into `run_web_app` by default. The bridge runs
only by explicit CLI invocation or explicit future operator workflow.

## Verification Gate

Focused verification:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_legacy_bridge.py tests/integration/test_controlplane_postgres_legacy_bridge.py tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_legacy_bridge.py -q
uv run pytest tests/unit/test_controlplane_projection_state_contracts.py tests/unit/test_persistence_namespace.py tests/unit/test_postgres_config.py -q
uv run pytest tests/unit/test_web_app.py::test_legacy_local_web_paths_do_not_construct_postgres -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
python3 scripts/check_index.py
git diff --check
```

Postgres-gated verification when a DSN is available:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py -q
```

CI note: remote GitHub Actions may remain blocked until the repository
owner resolves the account billing/spending-limit issue. Do not treat a
runner-not-started CI failure as repository test evidence.

## Adversarial Review Checklist

Reviewer should challenge:

1. whether the source inventory misses any Wave 1 stable `/api/v1`
   read-model input
2. whether source identities are stable and free of absolute local paths
3. whether watermarks are deterministic across reruns and machines
4. whether `occurred_at_utc` is deterministic for sources with no
   durable source timestamp and never uses process observation time
5. whether mtime-only watermarks could let changed content pass
6. whether dedupe keys can collide across domains or source families
7. whether rerunning a backfill can duplicate outbox rows
8. whether changed source payloads under the same logical event raise
   conflicts instead of silently rewriting history
9. whether tail mode proves active freshness or merely updates status
   rows without observing sources
10. whether missing or empty source roots can incorrectly mark a domain
   ready
11. whether immutable and mutable sources have distinct freshness rules
12. whether `source_root_display` can leak absolute paths, secret-like
   path segments, or configured credential values
13. whether config/env posture redaction is strong enough
14. whether live config/env and market-data posture facts are captured
   before control-posture routing can ever pivot
15. whether the bridge accidentally writes final read-model tables
16. whether any `/api/v1` route or SSE topic pivots in this slice
17. whether command/session storage drifts into stable Wave 3 write
   semantics
18. whether dry-run can leak secrets
19. whether adapter batch rollback is broad enough
20. whether fake tests could pass while real SQL behavior is broken
21. whether legacy local startup remains database-free
22. whether source-status `projected_watermark` is incorrectly advanced
   by the bridge before projectors exist

## Definition Of Done

This slice is done when:

1. `legacy_bridge` source contracts and source inventory are explicit
2. source adapters emit deterministic source events and watermarks
3. dry-run previews are available and redacted
4. `--once`, `--since`, `--tail`, and `--dry-run` are implemented
5. outbox appends use `PostgresProjectionStateRepository`
6. same-source reruns are idempotent
7. changed payload conflicts are redacted and tested
8. source-status rows are written for every source identity
9. active tail mode updates freshness without claiming projection
   completion
10. stale mutable source readiness blocks are tested
11. no final read-model tables are materialized
12. no `/api/v1` route pivots to Postgres
13. mandatory legacy no-Postgres startup and route regressions pass
14. docs/index validation passes
15. Postgres-gated tests skip explicitly without a DSN and pass with a
   real `TRADINGX_TEST_POSTGRES_DSN`

Only after this definition is met should Wave 2 continue into domain
projectors, Postgres read models, read routers, or `/api/v1` route
pivots.
