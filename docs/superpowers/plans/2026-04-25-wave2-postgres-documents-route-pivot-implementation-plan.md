---
id: PLAN-0025
title: Headless control plane Wave 2 Postgres documents route pivot implementation plan
version: 1.0.0
status: draft
created: 2026-04-25
last_amended: 2026-04-25
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Headless Control Plane Wave 2 Postgres Documents Route Pivot Implementation Plan

## Purpose

This implementation plan turns clean-approved `PLAN-0024` into a
test-first execution sequence. It is planning only: no production code,
tests, migrations, or runtime wiring are changed by this artifact.

The slice pivots only the existing v1 document read routes to the
completed Postgres document read path when configuration and scoped
readiness allow it:

```text
/api/v1/documents
/api/v1/documents/{document_id}
```

Legacy `/api/documents`, config proposal APIs, bridge/projector work,
repository migrations, and non-document routes remain outside this
slice.

## Authority

- `PLAN-0024`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-route-pivot-plan.md`
- `PLAN-0023`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-projector-execution-plan.md`
- `PLAN-0022`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-projector-implementation-plan.md`
- `PLAN-0021`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-implementation-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`

## Current Code Facts

These facts are the baseline for implementation:

1. `src/tradingx/web/app.py` owns the v1 document routes.
2. `src/tradingx/web/app.py` has `/api/v1/documents` at about line
   862 and `/api/v1/documents/{document_id}` at about line 867.
3. Both v1 routes currently read from `read_model.list_documents()`.
4. The legacy `/api/documents` route at about line 1024 also reads from
   `read_model.list_documents()` and must stay legacy-backed.
5. `src/tradingx/persistence/repositories/postgres.py` already exposes
   `PostgresControlPlaneRepository.list_documents(page=...)` and
   `get_document(document_id)`.
6. `PostgresControlPlaneRepository.list_documents(...)` and
   `get_document(...)` are the route pivot's Postgres read source and
   already exclude tombstoned documents.
7. `src/tradingx/controlplane/document_projectors.py` already exposes
   `documents_route_readiness_from_source_statuses(...)`.
8. `src/tradingx/persistence/postgres.py` already exposes
   `require_postgres_dsn`, `settings_from_control_plane`, and
   `build_postgres_engine`.
9. Config supports global store `legacy|hybrid|postgres`, domain
   overrides `documents=legacy|postgres`, and
   `TRADINGX_POSTGRES_REQUIRED`.
10. The scoped v1 documents route readiness families are
    `handover_sessions` and `state_and_index_docs`.
11. `config_proposals` remains config-specific and outside the v1
    documents route scope.

## Non-Negotiable Locks

1. Write tests before production code.
2. Pivot only `/api/v1/documents` and
   `/api/v1/documents/{document_id}`.
3. Keep `/api/documents` legacy-backed.
4. Keep config proposal routes legacy/config-specific and out of the
   document provider path.
5. Preserve the public v1 response shape; do not expose metadata,
   revision internals, page cursors, SQL/table shape, or
   `DocumentReadRecord` internals.
6. Default legacy app creation must not construct Postgres engines,
   repositories, providers, bridges, or projectors.
7. Optional `hybrid` or `documents=postgres` modes may fall back to
   legacy when Postgres is unavailable or scoped readiness is blocked.
8. `TRADINGX_POSTGRES_REQUIRED=true` and global
   `TRADINGX_CONTROL_PLANE_STORE=postgres` fail closed for blocked or
   unavailable Postgres with `503 documents_postgres_unavailable`.
9. Readiness for this route requires only `handover_sessions` and
   `state_and_index_docs`; `config_proposals` must neither block nor
   appear.
10. Detail reads in Postgres-ready mode must call `get_document`; they
    must not scan the legacy list.
11. Do not schedule bridge, projector, repository, or migration work
    unless a failing route test proves a tiny adapter import is needed.
12. Keep route errors redacted: no DSNs, SQL, absolute paths, or raw
    exception text in API responses.

## Owned Files/Write Scope

This plan artifact edits only docs. The implementation slice is expected
to touch a narrow code/test set:

- `tests/unit/test_web_app.py`
- `tests/integration/test_web_app_postgres_documents_routes.py`
- `src/tradingx/web/app.py`
- `src/tradingx/web/document_routes.py` or a similarly small web-local
  provider file, if used
- `src/tradingx/web/runtime.py`
- `src/tradingx/persistence/postgres.py`, only if failing tests prove a
  tiny DSN/settings adapter is needed
- `docs/INDEX.md` and `docs/handover/STATE.md` only for implementation
  closeout/version bookkeeping if the execution slice changes artifact
  state

Do not edit bridge, projector, repository, migration, frontend, or
non-document route files for this route pivot unless a failing route
test demonstrates that a minimal import/wiring adapter is unavoidable.

## Slice-by-slice implementation order

### Slice 0: Baseline and Harness

Run baseline commands and confirm no production files are edited before
tests. Identify the existing `create_app` injection seams in
`src/tradingx/web/app.py` and `src/tradingx/web/runtime.py`.

Green gate:

```bash
uv run pytest tests/unit/test_web_app.py -q
python3 scripts/check_index.py
git diff --check
```

### Slice 1: Unit Route Tests First

Add failing unit/provider route tests in `tests/unit/test_web_app.py`.
Use fake Postgres/legacy behavior through a route-provider injection
point, not a real engine, so tests can prove routing semantics without
constructing Postgres.

These tests must include both fail-closed cases and ready success cases
for `TRADINGX_POSTGRES_REQUIRED=true` and global
`TRADINGX_CONTROL_PLANE_STORE=postgres`. The ready-path tests must
prove list calls use `list_documents(page=None)` and detail calls use
`get_document(document_id)`.

No production code is allowed until these failing tests exist.

### Slice 2: Web-local Provider

After the failing tests are in place, add a small web-local provider
module/class, likely `src/tradingx/web/document_routes.py` or similar.
The provider should cover only v1 document list/detail reads and should
avoid a broad router abstraction.

Wire `create_app` with an optional `documents_route_provider` or
provider factory so unit tests can inject fake Postgres/legacy behavior
without building real engines.

### Slice 3: Runtime Wiring and Fail-closed Semantics

Wire the real provider factory from config/runtime:

1. Resolve effective documents store from the domain override first,
   then global store.
2. Lazily build Postgres only when the effective documents behavior may
   read from Postgres.
3. Evaluate route-scoped readiness before serving Postgres data.
4. Optional blocked/unavailable Postgres falls back to legacy.
5. Required or global-postgres blocked/unavailable returns
   `503 documents_postgres_unavailable`.

### Slice 4: Guarded DSN-backed Integration Tests

Add `tests/integration/test_web_app_postgres_documents_routes.py` with
real migrations/repositories and FastAPI `TestClient`, guarded by
`TRADINGX_TEST_POSTGRES_DSN`.

These tests prove the route pivot through the web app, not only through
repository calls.

The guarded suite must include ready success paths for required
Postgres mode and global Postgres mode. Do not close the implementation
slice with only optional-hybrid success plus fail-closed tests.

### Slice 5: Cleanup and Closeout

Run the full verification gates, update docs/index/state only if the
implementation execution changes artifact state, and capture any
guarded integration tests that could not run because no DSN was
available.

## First Failing Tests

Add these unit route tests in `tests/unit/test_web_app.py` before any
production code:

1. Default legacy app creation does not construct Postgres.
2. `hybrid` plus `documents=postgres` plus ready Postgres list/detail
   uses the Postgres provider through the v1 routes.
3. `TRADINGX_POSTGRES_REQUIRED=true` with ready scoped Postgres serves
   Postgres list and detail through the v1 routes.
4. Global `TRADINGX_CONTROL_PLANE_STORE=postgres` with ready scoped
   Postgres serves Postgres list and detail through the v1 routes.
5. The ready `hybrid`, required, and global-postgres list paths call
   `list_documents(page=None)`.
6. The ready `hybrid`, required, and global-postgres detail paths call
   `get_document(document_id)` and do not scan the legacy list.
7. Optional hybrid/readiness-blocked mode falls back to legacy.
8. `TRADINGX_POSTGRES_REQUIRED=true` or global `postgres` with blocked
   readiness returns `503 documents_postgres_unavailable`.
9. `/api/documents` remains legacy-backed.
10. The config proposals route remains legacy/config-specific and is not
   routed through the document provider.
11. The v1 detail route uses `get_document` rather than scanning the
   legacy list when Postgres-ready.
12. Postgres-backed list/detail response shape excludes metadata,
   revision internals, page cursors, and table-shaped payloads.

Add the guarded integration tests in
`tests/integration/test_web_app_postgres_documents_routes.py` after the
unit route tests establish the seam:

1. Ready Postgres list/detail reads use real migrations, repositories,
   projection source statuses, and `TestClient`.
2. `TRADINGX_POSTGRES_REQUIRED=true` with ready scoped Postgres serves
   Postgres list and detail through `TestClient`.
3. Global `TRADINGX_CONTROL_PLANE_STORE=postgres` with ready scoped
   Postgres serves Postgres list and detail through `TestClient`.
4. The required and global-postgres ready list/detail cases prove the
   route uses the real Postgres repository methods
   `list_documents(page=None)` and `get_document(document_id)`.
5. Tombstoned documents are excluded from list and detail responses.
6. Optional mode falls back to legacy when one scoped family is blocked.
7. Required/global-postgres mode fails closed when one scoped family is
   blocked.
8. `config_proposals` is not required for readiness and is not returned
   by `/api/v1/documents`.

## Implementation Notes

The provider should stay deliberately local to the web route layer:

1. A small provider can expose `list_documents()` and
   `get_document(document_id)`.
2. It can return a route-local DTO compatible with the existing v1
   serializer, or directly produce the existing public route shape.
3. Legacy mode delegates to `read_model.list_documents()`.
4. Postgres-ready mode calls
   `PostgresControlPlaneRepository.list_documents(page=None)` for list
   and `get_document(document_id)` for detail.
5. Detail 404 behavior should remain `404 document_not_found`.
6. Public list/detail payloads should include only the existing public
   fields such as `document_id`, `title`, `kind`, `preview`, and
   `retrieval_ref`.
7. The `cursor` query parameter may remain ignored, matching the
   current v1 route behavior.
8. Readiness should be computed with
   `documents_route_readiness_from_source_statuses(...)`; do not
   persist a route-scoped readiness result as domain-wide documents
   status.
9. Missing DSN, engine construction failure, repository failure, and
   blocked readiness should collapse to optional fallback or redacted
   fail-closed response depending on effective mode.
10. Config proposal APIs must continue using their existing
    config-specific path and must not pass through the v1 document
    provider.

## Verification Gates

Run these commands before implementation review:

```bash
uv run ruff check src/tradingx/web src/tradingx/persistence/postgres.py tests/unit/test_web_app.py tests/integration/test_web_app_postgres_documents_routes.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_web_app.py -q
python3 scripts/check_index.py
git diff --check
```

Run the guarded Postgres route proof when a DSN is available:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_web_app_postgres_documents_routes.py -q
```

For this planning-only artifact, run:

```bash
python3 scripts/check_index.py
git diff --check -- docs/superpowers/plans/2026-04-25-wave2-postgres-documents-route-pivot-implementation-plan.md docs/INDEX.md docs/handover/STATE.md
```

If the guarded DSN is unavailable during implementation, record that it
was not run. Do not claim the Postgres route pivot is fully verified
without the guarded route proof.

## Adversarial Review Checklist

Reviewers should block execution if any answer is "no":

1. Does the plan require failing unit route tests before production
   code?
2. Does the plan pivot only the two v1 document read routes?
3. Does `/api/documents` remain legacy-backed?
4. Do config proposal routes stay config-specific and outside the
   document provider?
5. Does default legacy app creation stay Postgres-free?
6. Does optional hybrid/readiness-blocked behavior fall back to legacy?
7. Do required/global-postgres blocked modes return
   `503 documents_postgres_unavailable`?
8. Does the detail route use `get_document` in Postgres-ready mode?
9. Does the route response exclude metadata and revision internals?
10. Do guarded integration tests use real migrations/repositories plus
    `TestClient`?
11. Are tombstone exclusion, optional fallback, required fail-closed,
    and config-proposal exclusion all tested?
12. Does the implementation write set avoid bridge, projector,
    repository, migration, frontend, and broad-router work?
13. Are errors redacted?
14. Are verification commands precise and runnable?
15. Is `PLAN-0025` indexed and is `STATE.md` clear that execution has
    not started or completed?

## Ready-to-Execute Gate

Implementation may start only after:

1. `PLAN-0024` remains clean-approved.
2. `PLAN-0025` receives adversarial review approval.
3. `docs/INDEX.md` indexes `PLAN-0025`.
4. `docs/handover/STATE.md` names `PLAN-0025` as the current
   implementation-plan artifact pending adversarial review before
   execution.
5. The first implementation commit begins with failing tests in
   `tests/unit/test_web_app.py`.
6. The first production code move is the small web-local provider seam,
   not bridge/projector/repository/migration work.
7. Guarded DSN-backed route tests are planned in
   `tests/integration/test_web_app_postgres_documents_routes.py` and
   cannot be replaced by mocked repository-only tests.
8. Required-mode and global-postgres ready-path list/detail proofs are
   present in both unit/provider route tests and guarded DSN-backed
   `TestClient` tests.
