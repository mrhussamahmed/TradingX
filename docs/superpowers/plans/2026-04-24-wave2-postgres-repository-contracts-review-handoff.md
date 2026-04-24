---
id: REPORT-0006
title: Headless control plane Wave 2 Postgres repository contracts implementation plan review handoff
version: 1.0.0
status: draft
created: 2026-04-24
last_amended: 2026-04-24
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-24
---

# Headless Control Plane Wave 2 Postgres Repository Contracts Implementation Plan Review Handoff

## Scope

This handoff prepares `PLAN-0016` for adversarial implementation-plan
review before repository contract code is written.

It covers planning only. The implementation branch should use this
handoff to challenge the next Wave 2 storage-boundary slice: repository
protocols, test-first contract coverage, implementation-backed Postgres
repository methods, contract-only Slice 3 boundaries, cursor pagination,
and legacy no-Postgres regressions.

## Files To Review

- `docs/superpowers/plans/2026-04-24-wave2-postgres-repository-contracts-plan.md`
- `docs/superpowers/plans/2026-04-24-wave2-postgres-repository-contracts-review-handoff.md`
- `docs/INDEX.md`

Useful context:

- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md`
- `docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-slice-plan.md`
- `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `src/tradingx/persistence/postgres.py`
- `tests/integration/test_controlplane_postgres_store.py`

## Why This Slice Exists

`PLAN-0015` created the Postgres dependency, migration, redaction, and
schema foundation. The next step in `PLAN-0014` is repository contracts,
but the initial high-level Slice 2 outline was too broad to execute
safely without a more precise plan.

`PLAN-0016` narrows that work so the next branch can add repository
boundaries without accidentally implementing outbox/projector/router
behavior or Wave 3 governed command writes.

## Prior Review Fixes Already Applied

The plan has already been amended after adversarial review to address
these issues:

1. Slice 3 outbox/checkpoint/source-status boundaries are now explicit
   contract-only interfaces.
2. Access, command-session, and commanding ordinary repository protocols
   are deferred; their event rows may appear only through the public
   timeline union, and write-shaped command intake and session issuance
   are prohibited until Wave 3.
3. Every implementation-backed repository method must have real
   Postgres-gated SQL coverage.
4. Cursor pagination semantics are explicit enough to prevent
   offset-limit drift under inserts between pages.
5. Legacy no-Postgres startup and representative `/api/v1` route
   regressions are mandatory.
6. DSN redaction tests must cover `str`, `repr`, `args`, `__cause__`,
   and `__context__`.
7. The final verification gate includes prior Postgres connection and
   migration safety tests.
8. The public event timeline contract is mandatory and
   implementation-backed, and is separate from internal
   `system.outbox_event`.
9. The domain scope is now a concrete matrix: implemented-now,
   deferred-note-only, and Slice 3 contract-only.
10. The public timeline now names its required SQL `UNION ALL` sources,
    canonical fields, ordering tuple, minimum event families, and
    `system.outbox_event` prohibition.
11. Real Postgres tests must cover page-1, mid-pagination insert, page-2
    cursor behavior for every SQL-backed list method.
12. Legacy no-Postgres regression coverage now includes `run_web_app`
    and `build_default_local_web_components`, not only `create_app`.
13. `system.domain_projection_status` reads are labeled derived and
    non-authoritative until Slice 3 source-status aggregation exists.

## What PLAN-0016 Schedules

1. Add test-first repository contract coverage.
2. Add `tradingx.controlplane` repository protocols, query/page/cursor
   dataclasses, domain result dataclasses, and repository errors.
3. Add contract-only Slice 3 boundaries for outbox append, checkpoint
   load/save, and source-status upsert/read.
4. Add a Postgres repository package skeleton without ORM coupling.
5. Implement and test the minimal load-bearing SQL-backed subset:
   runtime posture, runtime heartbeats, incidents/events, derived
   non-authoritative system projection status reads, and public event
   timeline reads.
6. Add mandatory no-Postgres legacy startup and route regressions.
7. Keep `/api/v1` routing, SSE parity, projectors, outbox behavior,
   checkpoint advancement, readiness aggregation, and frontend changes
   out of scope.

## Review-Sensitive Locks

### No Wave 3 write semantics

Access, command-session, and commanding ordinary repository protocols
are deferred in this slice; their event rows may appear only through the
public timeline union. The reviewer should reject any method shape that
implies stable command creation, session issuance, idempotency replay,
precondition enforcement, or result recording before Wave 3.

### Contract-only does not mean implemented

Slice 3 outbox/checkpoint/source-status boundaries may exist as
protocols and dataclasses, but they must not be implemented or counted as
SQL-backed coverage in this slice.

### Real SQL coverage must match protocol surface

Any method introduced as an implementation-backed repository method must
have a concrete Postgres implementation and a Postgres-gated integration
test. Fakes are useful for unit tests but cannot be the only proof.

### Public timeline is not outbox

The public event timeline contract must be a canonical read API shape.
It must not leak internal outbox rows or make `/api/v1/events` depend on
projector internals. Its SQL source must be a `UNION ALL` over
`incidents.incident_event`, `commanding.command_event`,
`access.command_session_event`, `runtime.control_posture_snapshot`,
`runtime.runtime_heartbeat`, and `investigations.replay_event`, ordered
by `occurred_at_utc DESC` and `timeline_event_id DESC`.

### Domain matrix controls scope

Implemented-now surfaces must have real Postgres coverage.
Deferred-note-only domains must not add ordinary fake-only repository
protocols. Slice 3 contract-only boundaries may define shapes but cannot
claim working behavior.

### Projection status is not readiness authority

`system.domain_projection_status` is a derived diagnostic read in this
slice. Router readiness authority remains deferred until Slice 3
implements source-family aggregation over
`system.domain_projection_source_status`.

### Cursor pagination must be stable

List methods need named timestamp columns, sort direction, tie-break
columns and direction, null handling, cursor encoding, boundary
semantics, max page size, invalid cursor behavior, and next-token
behavior. Integration tests must fetch page 1, insert rows around the
page boundary, fetch page 2 with the original cursor, and prove no
duplicates or skips.

### Legacy local mode stays database-free

Repository contracts and package imports must not instantiate Postgres
engines during config load, app creation, default local web component
construction, default local startup wiring, or legacy route handling.

### Secrets stay redacted

Repository exceptions must not leak raw DSNs or passwords through
strings, reprs, args, chained exceptions, logs, or test output.

## Known Deferrals

Intentionally not in this slice:

- outbox append implementation
- checkpoint writes or checkpoint advancement
- source-status upsert implementation
- readiness aggregation
- bridge/backfill/tailer behavior
- projector runners
- `PostgresControlPlaneReadModel`
- `/api/v1` route pivots
- SSE parity
- frontend changes
- local compose stack
- cloud deployment

## Verification Notes

Local Postgres on this workstation uses the Homebrew server at port
`5433`:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py -q
```

Remote GitHub Actions is currently blocked before runner startup by a
repository account billing or spending-limit issue. That is not code
evidence; implementation review should still inspect the planned local
gate carefully.

## Reviewer Prompt

Use this prompt with the teammate reviewer:

```text
Please adversarially review PLAN-0016 for the next TradingX headless
control-plane Wave 2 implementation slice.

Focus on whether the implementation plan is safe and complete enough
before repository contract code is written. Return P0/P1/P2 findings
with exact file and line references.

Primary file:
- docs/superpowers/plans/2026-04-24-wave2-postgres-repository-contracts-plan.md

Context:
- docs/superpowers/plans/2026-04-24-wave2-postgres-repository-contracts-review-handoff.md
- docs/superpowers/plans/2026-04-23-wave2-postgres-projections-implementation-plan.md
- docs/superpowers/plans/2026-04-24-wave2-postgres-connection-migrations-slice-plan.md
- docs/architecture/TradingX_Headless_Control_Plane_Architecture.md
- src/tradingx/persistence/postgres.py
- tests/integration/test_controlplane_postgres_store.py

Challenge especially:
1. whether command/session contracts still imply Wave 3 governed writes
2. whether Slice 3 contract-only boundaries are explicit enough without
   accidentally implementing Slice 3 behavior
3. whether every implementation-backed method is required to have real
   Postgres SQL coverage
4. whether the implemented-now/deferred-note-only/Slice 3 contract-only
   matrix is enforceable
5. whether public event timeline reads are clearly separated from
   internal outbox rows and have a concrete SQL union source
6. whether projection status reads are clearly non-authoritative until
   source-status aggregation exists
7. whether cursor pagination semantics are complete and stable under
   inserts between pages
8. whether fake tests could pass while SQL behavior is broken
9. whether legacy config/app/route/startup paths can accidentally
   instantiate Postgres repositories
10. whether raw DSNs or passwords can leak through repository errors,
   reprs, args, chained exceptions, logs, or test output
11. whether dataclasses create a second schema model that conflicts with
   migration tables
12. whether the verification gates are sufficient and runnable on the
    workstation's 5433 Postgres DSN

Return whether PLAN-0016 is ready to implement as-is, ready after edits,
or blocked.
```

## Review Outcome Requested

Please return:

1. P0/P1/P2 findings with exact file and line references.
2. Confirmation or rejection that `PLAN-0016` is the correct next
   executable slice after `PLAN-0015`.
3. Confirmation or rejection that the plan prevents Wave 3 write-surface
   creep.
4. Confirmation or rejection that the plan provides enough Slice 3
   repository boundaries without implementing Slice 3.
5. Confirmation or rejection that fake and real-SQL tests cannot diverge
   silently.
6. Any concrete edits required before implementation begins.
