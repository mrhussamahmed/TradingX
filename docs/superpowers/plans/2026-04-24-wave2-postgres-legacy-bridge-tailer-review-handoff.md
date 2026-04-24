---
id: REPORT-0007
title: Headless control plane Wave 2 Postgres legacy bridge and tailer plan review handoff
version: 1.0.0
status: draft
created: 2026-04-24
last_amended: 2026-04-24
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-24
---

# Headless Control Plane Wave 2 Postgres Legacy Bridge And Tailer Plan Review Handoff

## Scope

This handoff prepares `PLAN-0018` for adversarial implementation-plan
review before legacy bridge and tailer code is written.

It covers planning only. The implementation branch should use this
handoff to challenge the next Wave 2 storage-pipeline slice: legacy
source adapters, source identities, source watermarks, outbox dedupe
keys, source-status writes, backfill/tail commands, dry-run behavior,
and local no-Postgres safety.

## Files To Review

- `docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-plan.md`
- `docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-review-handoff.md`
- `docs/INDEX.md`

Useful context:

- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
- `docs/superpowers/plans/2026-04-24-wave2-postgres-outbox-checkpoint-readiness-plan.md`
- `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `src/tradingx/controlplane/projections.py`
- `src/tradingx/persistence/repositories/projection_state.py`
- `src/tradingx/persistence/__init__.py`
- `src/tradingx/operator_control.py`
- `src/tradingx/journal.py`
- `src/tradingx/web/readmodels.py`

## Why This Slice Exists

`PLAN-0017` made projection progress resumable by implementing
outbox append, checkpoints, source-status read/write, derived domain
status persistence, and transaction rollback. The next step in
`PLAN-0014` is not projectors or route pivots yet. It is the legacy
bridge that turns current Wave 1 local artifacts, files, config/env
posture, and SQLite records into deterministic outbox input and
source-status freshness evidence.

This plan narrows Slice 4 so implementation does not accidentally start
domain projectors, read routers, SSE parity, or governed Wave 3 command
writes.

## What PLAN-0018 Schedules

1. Add test-first bridge contract coverage.
2. Create `src/tradingx/controlplane/legacy_bridge.py`.
3. Define bridge dataclasses for source identities, source events,
   source watermarks, previews, and run results.
4. Implement source adapters for filesystem artifacts, operator-control
   files, live config/env posture, market-data posture, approved
   weights, ops baselines, OMS journal SQLite, validation SQLite, and
   document indexes.
5. Convert source events into deterministic outbox append requests.
6. Add bridge commands:
   - `--once`
   - `--since`
   - `--tail`
   - `--dry-run`
7. Upsert source-status rows and derived diagnostic domain status.
8. Add real Postgres tests proving idempotency, redacted conflict
   behavior, source-status writes, tail freshness, stale-source
   blocking, and batch rollback.
9. Preserve legacy no-Postgres startup and route behavior.

## Review-Sensitive Locks

### Bridge is not a projector

The bridge may append outbox events and update source-status rows. It
must not materialize final domain read-model tables such as
`runtime.runtime_heartbeat`, `incidents.incident`,
`portfolio.portfolio_snapshot`, `validation.validation_run`,
`documents.document`, or public timeline rows. Domain projectors remain
the next slice.

### Bridge is not a router

The plan must not pivot `/api/v1` routes or SSE topics. It may persist
diagnostic readiness summaries, but those summaries do not authorize
route routing in this slice.

### Source inventory must match Wave 1 read surfaces

Stable source coverage is defined by current Wave 1 `/api/v1` read
contracts and `LocalWebReadModel`, not just convenient directories. If a
stable route depends on a legacy artifact source, the source must be
bridged, explicitly derived from another bridged source, or the future
route must remain on legacy reads.

Artifact-backed `source_family` values must match the exact
`FilesystemArtifactStore` category and directory names so the bridge
cannot tail empty sibling roots by accident.

The amended plan now requires explicit source rows and inventory tests
for current Wave 1 read inputs including `strategy_activations`,
`opportunity_selections`, `blueprint_activation`,
`sleeve_daily_attribution`, `drift_monitor_verdicts`,
`operator_sleeve_halts`, `trade_intents`, `orders`, `reconciliation`,
`daily_digests`, and `incident_acknowledgements`. Review should still
try to find missing stable read inputs in `LocalWebReadModel`.

### Source identities must be stable

`source_family` and `source_identity` must not include absolute local
paths, temporary directories, random values, process IDs, hostnames, or
secrets. They become readiness contract values used by later projectors
and routers.

### Watermarks must prove content position

Snapshot watermarks must include content hashes. Append-only source
watermarks must use deterministic event identity. SQLite watermarks must
not rely on query order alone when payload content can change. Mtime-only
watermarks are not sufficient.

### Dedupe keys must make reruns safe

Outbox dedupe keys must be stable across reruns and collision-resistant
across domains, source families, source identities, and source events.
Changed payloads under the same logical event must surface as redacted
conflicts, not silent history mutation.

`occurred_at_utc` is part of the outbox idempotency comparison. The plan
now requires it to be deterministic per `source_event_id`: durable source
timestamp first, durable SQLite timestamp second, fixed legacy epoch
when absent. Process observation time belongs only in metadata as
`observed_at_utc`.

### Tail mode must prove active freshness

`write_path: "active_bridge"` should be emitted only by an active tail
loop that observes sources and updates `checked_at_utc`. Backfill-only
mode must not pretend an active bridge is present.

### Projected watermark must not be forged

The bridge may advance `source_watermark`. It must not advance
`projected_watermark` for future projectors. Domains should remain not
router-ready until projectors later catch up.

### Secrets stay redacted

Dry-run output and errors must redact Postgres DSNs, signing secrets,
API keys, broker credentials, SMTP passwords, Telegram tokens, and any
environment secret values.

The plan also requires `source_root_display` instead of raw
`source_root`. Persisted metadata, dry-run previews, and logs must use
logical repo-relative refs or redacted display refs, and tests must
cover a secret-looking temporary path segment.

### Legacy local mode stays database-free

Bridge code and imports must not instantiate Postgres engines during
normal legacy config load, app creation, default local web component
construction, default startup wiring, or route handling. The bridge is
explicitly invoked by CLI or future operator workflow only.

## Known Deferrals

Intentionally not in this slice:

- domain projectors
- projector runner
- `PostgresControlPlaneReadModel`
- domain-aware read router
- `/api/v1` route pivots
- SSE parity
- stable `/api/v1/commands`
- stable `/api/v1/command-sessions`
- incident acknowledgement command implementation
- replay creation command implementation
- local compose stack
- frontend changes

## Verification Notes

Local Postgres on this workstation has been using port `5433`:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py -q
```

Remote GitHub Actions may remain blocked before runner startup by a
repository account billing or spending-limit issue. That is not code
evidence; implementation review should still inspect the planned local
gate carefully.

## Reviewer Prompt

Use this prompt with the teammate reviewer:

```text
Please adversarially review PLAN-0018 for the next TradingX headless
control-plane Wave 2 implementation slice.

Focus on whether the implementation plan is safe and complete enough
before legacy bridge and tailer code is written. Return P0/P1/P2
findings with exact file and line references.

Primary file:
- docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-plan.md

Context:
- docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-review-handoff.md
- docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md
- docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md
- docs/superpowers/plans/2026-04-24-wave2-postgres-outbox-checkpoint-readiness-plan.md
- docs/architecture/TradingX_Headless_Control_Plane_Architecture.md

Challenge these areas especially:
1. whether the source inventory misses a Wave 1 stable read-model input
2. whether source identities and watermarks are stable enough for later
   projector/router readiness contracts
3. whether timestamp-less source records still produce deterministic
   `occurred_at_utc` values across reruns
4. whether dedupe keys prevent duplicate outbox rows and detect changed
   payloads under the same logical source event
5. whether tail mode proves active freshness instead of merely marking
   source rows ready
6. whether bridge source-status writes can incorrectly advance
   projected_watermark or router readiness
7. whether dry-run, source-status metadata, and errors can leak secrets
   or absolute local source roots
8. whether the bridge accidentally becomes a projector, read router, or
   Wave 3 governed write path
9. whether fake-only tests could pass while real Postgres behavior is
   broken
10. whether legacy local mode remains database-free

Return whether PLAN-0018 is ready to implement as-is, ready after edits,
or blocked. Include concrete edits for every finding.
```

## Expected Review Output

Ask the reviewer to return:

1. P0/P1/P2 findings with `::code-comment` directives.
2. A short verdict: ready as-is, ready after edits, or blocked.
3. Confirmation or rejection that Slice 4 is the correct next step after
   `PLAN-0017`.
4. Any missing test gates needed before implementation starts.
