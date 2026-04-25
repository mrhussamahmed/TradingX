---
id: REPORT-0008
title: Headless control plane Wave 2 Postgres runtime projector plan review handoff
version: 1.0.0
status: draft
created: 2026-04-25
last_amended: 2026-04-25
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Headless Control Plane Wave 2 Postgres Runtime Projector Plan Review Handoff

## Scope

This handoff prepares `PLAN-0019` for adversarial implementation-plan
review before runtime projector code is written.

It covers planning only. The implementation branch should use this
handoff to challenge the first domain projector slice: ordered outbox
consumption, runtime table materialization, idempotent upserts,
checkpoint resume, source-status projected watermarks, readiness
transitions, rollback behavior, and legacy no-Postgres safety.

## Files To Review

- `docs/superpowers/specs/2026-04-25-wave2-postgres-runtime-projector-design.md`
- `docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-plan.md`
- `docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-review-handoff.md`
- `docs/INDEX.md`

Useful context:

- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
- `docs/superpowers/plans/2026-04-24-wave2-postgres-outbox-checkpoint-readiness-plan.md`
- `docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-plan.md`
- `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `src/tradingx/controlplane/legacy_bridge.py`
- `src/tradingx/controlplane/projections.py`
- `src/tradingx/controlplane/repositories.py`
- `src/tradingx/persistence/repositories/projection_state.py`
- `src/tradingx/persistence/repositories/postgres.py`
- `src/tradingx/persistence/migrations/versions/20260424_0001_control_plane_foundation.py`

## Why This Slice Exists

`PLAN-0018` made current Wave 1 legacy state available as deterministic
outbox events and source-status rows. The next step is not route
pivoting. It is the smallest real projector that proves outbox events
can materialize existing Postgres runtime read tables and then advance
projected source watermarks.

This slice intentionally targets only:

- `runtime.runtime_heartbeat`
- `runtime.control_posture_snapshot`
- `runtime.control_posture_blocker`
- runtime projection checkpoint/source-status evidence

## Review-Sensitive Locks

### Projector is not a bridge

The projector must consume outbox envelopes. It must not reread
filesystem artifacts, config/env posture, SQLite journals, or local web
read models.

### Projector is not a router

The plan must not pivot `/api/v1`, introduce a domain read router, or
make `PostgresControlPlaneReadModel` active. Existing Postgres read
repositories can remain proof surfaces, but route dispatch stays legacy.

### Outbox order must be real order

`last_outbox_event_id` is an opaque UUID and cannot be used as an
ordered cursor. The plan requires `created_at_utc ASC, outbox_event_id
ASC` reads and checkpoint metadata with both cursor fields. Review
should look for any implementation shortcut that orders by UUID,
dedupe key, aggregate ID, or occurred time alone.

### Source-status advancement must be earned

`projected_watermark` can advance only after the projector writes the
corresponding materialized rows or safely recognizes a supported no-op.
Unsupported source families must remain unprojected. Full runtime
readiness must remain blocked while any required runtime source from
the bridge inventory is deferred or unmapped.

### Runtime rows must be idempotent

Rerunning the same outbox event must not duplicate heartbeat,
snapshot, blocker, checkpoint, or source-status rows. Reusing a natural
key with changed payload/fingerprint must raise a redacted conflict and
roll back the whole batch.

### Runtime and projection-state writes share a transaction

The projector must not commit runtime table writes and projection-state
writes through separate transactions. Review should look for nested
independent `engine.begin()` calls or repository helpers that can commit
one side before the other side fails.

### Control posture must not churn

No-op control-posture refreshes with the same latest
`state_fingerprint` must not create a new material snapshot or bump
`resource_version`. Material changes should advance resource version
deterministically.

### Local startup remains database-free

Web app creation, default local route handling, and legacy local read
model construction must not import-time construct the projector or its
Postgres write repository.

### DSNs stay out of argv

The CLI should prefer a DSN environment-variable name such as
`--dsn-env TRADINGX_POSTGRES_DSN`. Literal DSN argv values are review
sensitive because they can appear in process listings, shell history, or
test output.

## Known Deferrals

Intentionally not in this slice:

- scheduler and market-day table materialization
- runtime instance modeling
- portfolio projectors
- incident projectors
- validation projectors
- document projectors
- investigation/replay projectors
- command/access projectors
- read router and `/api/v1` pivots
- SSE parity
- stable governed write routes
- frontend changes

## Verification Notes

Local Postgres on this workstation has been using port `5433`:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py tests/integration/test_controlplane_postgres_runtime_projector.py -q
```

GitHub Actions may still be blocked before runner startup by account
billing or spending-limit status. Treat that as CI infrastructure
evidence, not code evidence.

## Reviewer Prompt

Use this prompt with the teammate reviewer:

```text
Please adversarially review PLAN-0019 for the next TradingX headless
control-plane Wave 2 implementation slice.

Focus on whether the implementation plan is safe and complete enough
before runtime projector code is written. Return P0/P1/P2 findings with
exact file and line references.

Primary file:
- docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-plan.md

Context:
- docs/superpowers/specs/2026-04-25-wave2-postgres-runtime-projector-design.md
- docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-review-handoff.md
- docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-plan.md
- docs/superpowers/plans/2026-04-24-wave2-postgres-outbox-checkpoint-readiness-plan.md
- docs/architecture/TradingX_Headless_Control_Plane_Architecture.md

Challenge these areas especially:
1. whether the slice still tries to do too much for the first projector
2. whether the projector can accidentally reread legacy files instead
   of consuming outbox envelopes
3. whether outbox cursor ordering can skip or duplicate events,
   especially tied timestamps and non-sortable UUIDs
4. whether checkpoint metadata can diverge from last_outbox_event_id
5. whether unsupported source families can advance projected_watermark
6. whether filtered readiness can be mistaken for full runtime-domain
   route readiness
7. whether no-op control-posture refreshes churn snapshots or versions
8. whether reruns duplicate heartbeat, posture, blocker, checkpoint, or
   source-status rows
9. whether changed payloads under the same natural key are detected as
   conflicts and rolled back
10. whether runtime writes and projection-state writes share one
    transaction
11. whether literal DSNs can leak through argv, help output, or errors
12. whether legacy local startup remains database-free

Return whether PLAN-0019 is ready to implement as-is, ready after edits,
or blocked. Include concrete edits for every finding.
```

## Expected Review Output

Ask the reviewer to return:

1. P0/P1/P2 findings with `::code-comment` directives.
2. A short verdict: ready as-is, ready after edits, or blocked.
3. Confirmation or rejection that a narrow runtime projector is the
   correct next slice after `PLAN-0018`.
4. Any missing test gates needed before implementation starts.
