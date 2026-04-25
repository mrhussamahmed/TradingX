---
id: PLAN-0024
title: Headless control plane Wave 2 Postgres documents route pivot plan
version: 1.0.1
status: draft
created: 2026-04-25
last_amended: 2026-04-25
supersedes: PLAN-0024@1.0.0
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Headless Control Plane Wave 2 Postgres Documents Route Pivot Plan

## Purpose

This execution plan scopes the next Wave 2 slice: pivot only the actual
`/api/v1/documents` and `/api/v1/documents/{document_id}` read routes
to the completed Postgres document read path when configuration and
scoped readiness allow it.

This plan supersedes the route-pivot portions of `PLAN-0020` and
`PLAN-0021`. It does not redo bridge enrichment, repository contracts,
document projection, tombstone handling, object refs, or scoped
readiness production from `PLAN-0022` and `PLAN-0023`; those slices are
complete and merged.

The desired implementation path is narrow:

```text
control-plane store config
-> documents v1 read provider/router adapter
-> scoped documents route readiness check
-> Postgres DocumentReadRecord list/get
-> existing v1 response envelope
```

## Authority

- `PLAN-0020`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-plan.md`
- `PLAN-0021`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-implementation-plan.md`
- `PLAN-0022`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-projector-implementation-plan.md`
- `PLAN-0023`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-projector-execution-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`

## Current Code Facts

These facts are true at the start of this slice:

1. `src/tradingx/web/app.py` owns both v1 document routes.
2. `/api/v1/documents` currently ignores `cursor` and returns
   `_list_response(read_model.list_documents())`.
3. `/api/v1/documents/{document_id}` currently scans
   `read_model.list_documents()` and returns `404 document_not_found`
   when no matching `DocumentRecord.doc_id` exists.
4. Legacy `/api/documents` also calls `read_model.list_documents()`.
   It must remain legacy-backed in this slice.
5. `src/tradingx/controlplane/repositories.py` defines
   `DocumentReadRecord`, `DocumentReadRepository.list_documents(page:
   PageRequest | None)`, and `get_document(document_id)`.
6. `PostgresControlPlaneRepository.list_documents(...)` and
   `get_document(...)` return active `DocumentReadRecord` rows and
   already exclude tombstoned documents.
7. `tradingx.controlplane.document_projectors.
   documents_route_readiness_from_source_statuses(...)` produces scoped
   readiness for the document API route families.
8. The scoped route families for this API are only
   `handover_sessions` and `state_and_index_docs`; `config_proposals`
   remains outside the v1 documents API scope.
9. Control-plane config currently parses:
   - `TRADINGX_CONTROL_PLANE_STORE=legacy|hybrid|postgres`
   - `TRADINGX_CONTROL_PLANE_DOMAIN_STORES` entries as
     `<domain>=legacy|postgres`
   - `TRADINGX_POSTGRES_REQUIRED`
10. Existing config tests already prove `documents=postgres` is accepted
    as a domain override. This route slice should preserve that parser
    behavior and add runtime-route tests for the effective documents
    store semantics.
11. Postgres engine construction is already intended to happen only
    when global store, domain overrides, or required mode request
    Postgres. Default local web startup must remain Postgres-free.

## Non-Negotiable Locks

1. Pivot only `/api/v1/documents` and
   `/api/v1/documents/{document_id}`.
2. Do not pivot legacy `/api/documents`.
3. Do not pivot config proposal APIs or materialize config proposals
   into the v1 documents route.
4. Do not pivot runtime, control posture, incidents, validation,
   portfolio, events, commands, investigations, replays, SSE, or any
   non-v1 route.
5. Preserve the existing v1 response shape. Frontend consumers must not
   learn `DocumentReadRecord`, page objects, Postgres table names, or
   projector payloads.
6. Keep default local web startup Postgres-free. Do not build a
   Postgres engine, repository, route provider, projector, or bridge
   component unless control-plane config requests or needs Postgres.
7. Required Postgres mode must fail closed. If documents are configured
   for Postgres and Postgres is unavailable or scoped readiness is
   blocked while `TRADINGX_POSTGRES_REQUIRED=true`, v1 document routes
   must return `503` with an explicit code such as
   `documents_postgres_unavailable`.
8. Optional hybrid mode may fall back to legacy reads when Postgres is
   unavailable or scoped readiness is blocked.
9. Scoped readiness for route activation is only
   `handover_sessions` plus `state_and_index_docs`. It must not include
   `config_proposals`.
10. A missing or blocked scoped source family prevents a Postgres route
    read. It either triggers optional legacy fallback or required-mode
    `503`.
11. Tombstoned documents must not appear in v1 list or detail responses
    when served from Postgres.
12. Keep route errors redacted. Do not expose raw DSNs, SQL, absolute
    local paths, or internal exception text.

## Out of Scope

- Bridge, tailer, or outbox changes.
- Documents projector changes except defensive import/wiring needed to
  read scoped readiness.
- Repository schema or migration changes.
- Document write routes.
- Document content download or object blob serving.
- Frontend changes.
- Config proposal route changes.
- A generic all-domain route router framework.
- Domain-wide `documents` status persistence.

## Implementation Shape

### Small v1 documents read provider

Add a small documents route read provider/router adapter near the web
route layer. It should be deliberately boring:

1. Resolve the effective documents store from:
   - `TRADINGX_CONTROL_PLANE_DOMAIN_STORES=documents=...` first.
   - Otherwise `TRADINGX_CONTROL_PLANE_STORE`.
2. Lazily construct Postgres dependencies only when the effective route
   behavior may read from Postgres.
3. Evaluate scoped documents route readiness before any Postgres-backed
   route response.
4. For list reads, start with
   `PostgresControlPlaneRepository.list_documents(page=None)` and drain
   every returned repository `next_cursor` internally via
   `PageRequest(cursor=...)`; detail reads must call
   `get_document(document_id)`.
5. Map `DocumentReadRecord` to the same public shape currently returned
   from `DocumentRecord`:
   - list route remains `_list_response(...)` compatible.
   - detail route returns `document_id`, `title`, `kind`, `preview`, and
     `retrieval_ref`.
6. Keep `read_model.list_documents()` as the legacy provider for:
   - legacy store mode
   - optional fallback
   - `/api/documents`
7. Keep pagination out of the public response until the existing v1
   route contract intentionally grows. The public `cursor` query
   parameter may remain ignored, but the provider must not silently
   truncate to the repository default page.

Acceptable implementation names are intentionally small, for example:

```text
DocumentsRouteReadProvider
LegacyDocumentsRouteReadProvider
PostgresDocumentsRouteReadProvider
HybridDocumentsRouteReadProvider
DocumentRouteRecord
```

The provider should be route-local or web-local unless existing project
structure clearly has a better home. Do not introduce a broad domain
router abstraction in this slice.

### Effective behavior matrix

The implementation must lock this behavior with tests:

| Global store | Domain override | Required | Postgres DSN/readiness | v1 documents behavior | Engine construction |
| --- | --- | --- | --- | --- | --- |
| `legacy` | none | `false` | absent or present | serve legacy | no engine |
| `legacy` | `documents=legacy` | `false` | absent or present | serve legacy | no engine |
| `legacy` | `documents=legacy` | `true` | absent or present | serve legacy | no documents-route engine for this domain |
| `legacy` | none | `true` | ready | serve Postgres | build lazily or required startup wiring |
| `legacy` | none | `true` | missing DSN, connection error, or readiness blocked | `503 documents_postgres_unavailable` | no secret leakage |
| `legacy` | `documents=postgres` | `false` | ready | serve Postgres | build lazily |
| `legacy` | `documents=postgres` | `false` | missing DSN, connection error, or readiness blocked | serve legacy fallback | attempt only when needed; no startup failure |
| `legacy` | `documents=postgres` | `true` | ready | serve Postgres | build lazily or at app construction if existing startup path requires it |
| `legacy` | `documents=postgres` | `true` | missing DSN, connection error, or readiness blocked | `503 documents_postgres_unavailable` | no secret leakage |
| `hybrid` | none | `false` | ready | serve Postgres | build lazily |
| `hybrid` | none | `false` | missing DSN, connection error, or readiness blocked | serve legacy fallback | attempt only when route needs Postgres |
| `hybrid` | none | `true` | ready | serve Postgres | build lazily or required startup wiring |
| `hybrid` | none | `true` | missing DSN, connection error, or readiness blocked | `503 documents_postgres_unavailable` | no secret leakage |
| `hybrid` | `documents=postgres` | `false` | ready | serve Postgres | build lazily |
| `hybrid` | `documents=postgres` | `false` | missing DSN, connection error, or readiness blocked | serve legacy fallback | attempt only when route needs Postgres |
| `hybrid` | `documents=postgres` | `true` | ready | serve Postgres | build lazily or required startup wiring |
| `hybrid` | `documents=postgres` | `true` | missing DSN, connection error, or readiness blocked | `503 documents_postgres_unavailable` | no secret leakage |
| `hybrid` | `documents=legacy` | either | absent or present | serve legacy for v1 documents | no documents-route engine for this domain |
| `postgres` | none | `false` | ready | serve Postgres | build lazily or via existing Postgres app factory path |
| `postgres` | none | `false` | missing DSN, connection error, or readiness blocked | `503 documents_postgres_unavailable` | no secret leakage |
| `postgres` | none | `true` | ready | serve Postgres | build lazily or required startup wiring |
| `postgres` | none | `true` | missing DSN, connection error, or readiness blocked | `503 documents_postgres_unavailable` | no secret leakage |
| `postgres` | `documents=legacy` | either | absent or present | serve legacy for v1 documents only | no documents-route engine for this domain |

Interpretation rules:

1. Domain override wins for the documents route.
2. `documents=postgres` is already parser-valid and must mean
   "Postgres-preferred for the documents route."
3. Global `hybrid` means "Postgres-preferred with legacy fallback" for
   the documents route unless `documents=legacy` overrides it.
4. Global `postgres` means fail closed for this route when no
   `documents=legacy` override exists, even if
   `TRADINGX_POSTGRES_REQUIRED=false`.
5. `TRADINGX_POSTGRES_REQUIRED=true` turns any Postgres-requested
   documents route into fail-closed behavior. With global `legacy` and no
   documents override, required mode requests Postgres for this route;
   `documents=legacy` remains the explicit route-local escape hatch.
6. Optional fallback covers missing DSN, repository construction
   failure, connection failure, and scoped readiness blockers.
7. Fallback must be observable in tests but does not need a new public
   response field.

### Scoped readiness

Before serving Postgres data, the Postgres provider must evaluate
readiness using `documents_route_readiness_from_source_statuses(...)`
with statuses from the projection state repository. The readiness check
must:

1. Require `handover_sessions`.
2. Require `state_and_index_docs`.
3. Exclude `config_proposals`.
4. Treat missing source-status rows as not ready.
5. Treat unprojected or stale required rows as not ready.
6. Never persist a route-scoped ready result as domain-wide
   `system.domain_projection_status`.

If readiness is blocked:

- optional hybrid/Postgres-preferred route modes fall back to legacy;
- required/global-postgres fail-closed modes return `503` with an
  explicit route error code.

### Error response

Use the existing `_error_response(...)` helper for fail-closed behavior.
The expected status and code are:

```text
status: 503
code: documents_postgres_unavailable
message: Documents are temporarily unavailable from Postgres.
```

The exact message can vary slightly, but the test should assert the
status and stable code. Details may include a redacted reason category
such as `missing_dsn`, `connection_unavailable`, or
`scoped_readiness_blocked`; they must not include secrets.

## Test/Verification Plan

### Unit tests

Add or update tests around the provider and route behavior:

1. Config/runtime semantics:
   - `documents=postgres` remains accepted in
     `TRADINGX_CONTROL_PLANE_DOMAIN_STORES`.
   - Effective documents store resolution prefers the domain override.
   - Global `hybrid` plus `documents=postgres` selects
     Postgres-preferred behavior.
   - Global `hybrid` plus `documents=legacy` keeps v1 documents legacy.
2. Startup laziness:
   - Default `TradingConfig.from_mapping({})` and web app creation do
     not call Postgres engine construction.
   - `legacy` plus unrelated settings does not build documents
     Postgres dependencies.
3. v1 list route:
   - Optional hybrid with ready scoped Postgres data returns records from
     `PostgresControlPlaneRepository.list_documents(page=None)`.
   - Postgres-backed list reads drain repository `next_cursor` pages
     internally and do not truncate to the default repository page size.
   - Required mode with ready scoped Postgres data returns records from
     Postgres for both global `hybrid` plus `documents=postgres` and
     global `legacy`/`postgres` with no override.
   - Optional hybrid with readiness blocked falls back to
     `read_model.list_documents()`.
   - Required mode with readiness blocked returns
     `503 documents_postgres_unavailable`.
   - `documents=legacy` keeps v1 documents legacy-backed even when
     global store is `legacy`, `hybrid`, or `postgres` and
     `TRADINGX_POSTGRES_REQUIRED=true`.
4. v1 detail route:
   - Ready Postgres mode calls `get_document(document_id)` instead of
     scanning legacy list data.
   - Required mode with ready scoped Postgres data calls
     `get_document(document_id)` and serves Postgres for both global
     `hybrid` plus `documents=postgres` and global `legacy`/`postgres`
     with no override.
   - Missing Postgres record returns the existing
     `404 document_not_found`.
   - Required mode with unavailable Postgres returns
     `503 documents_postgres_unavailable`.
5. Scope protection:
   - `config_proposals` readiness does not block v1 documents.
   - Config proposal APIs are not routed through the documents provider.
   - `/api/documents` still uses `read_model.list_documents()`.
6. Response shape:
   - Postgres-backed list/detail responses match the existing v1
     field names and do not expose `metadata`, revision internals, page
     cursors, or table-shaped payloads.

### Guarded Postgres integration tests

Add DSN-backed route tests guarded by `TRADINGX_TEST_POSTGRES_DSN`.
These tests should use real migrations/repositories and FastAPI
`TestClient`.

Required proofs:

1. Seed or project real Postgres document rows for `STATE`, `INDEX`, and
   at least one handover session.
2. Seed projection source statuses that make scoped documents readiness
   pass for `handover_sessions` and `state_and_index_docs`.
3. `GET /api/v1/documents` returns the Postgres documents in the
   existing v1 list envelope and excludes tombstoned rows.
4. `GET /api/v1/documents/STATE` returns the Postgres detail response
   with `document_id`, `title`, `kind`, `preview`, and `retrieval_ref`.
5. Removing or blocking one scoped readiness family causes optional
   hybrid to fall back to legacy.
6. The same blocked readiness in required mode returns
   `503 documents_postgres_unavailable`.
7. Required mode with ready scoped Postgres data serves Postgres list
   and detail responses for both global `hybrid` plus
   `documents=postgres` and global `legacy`/`postgres` with no
   override.
8. A present `config_proposals` source status must not be required for
   the v1 documents route. Seed an active Postgres document row whose
   `metadata.source_family` is `config_proposals`; it must not appear in
   `GET /api/v1/documents`, and
   `GET /api/v1/documents/{proposal_id}` must return the existing
   `404 document_not_found` shape.

### Full verification commands

Run before final review:

```bash
uv run ruff check src/tradingx/config.py src/tradingx/persistence src/tradingx/web tests/unit/test_postgres_config.py tests/unit/test_postgres_connection.py tests/unit/test_web_app.py tests/integration/test_web_app_postgres_documents_routes.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_postgres_config.py tests/unit/test_postgres_connection.py tests/unit/test_web_app.py -q
python3 scripts/check_index.py
git diff --check
```

Run the guarded Postgres route proof when a DSN is available:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_web_app_postgres_documents_routes.py -q
```

If the DSN is unavailable, record that the guarded route proof was not
run. Do not describe the Postgres route pivot as fully verified without
that proof.

## Adversarial Review Checklist

Reviewers must block implementation if any answer is "no":

1. Does the plan pivot only `/api/v1/documents` and v1 detail?
2. Does `/api/documents` remain legacy-backed?
3. Does the route adapter preserve the current response envelope?
4. Does `hybrid` plus `documents=postgres` have explicit optional
   fallback behavior?
5. Does `TRADINGX_POSTGRES_REQUIRED=true` fail closed with a stable
   `503` code?
6. Does global `postgres` fail closed even when required is false?
7. Does `documents=legacy` override global `hybrid` or `postgres` for
   this route?
8. Are Postgres engines/repositories built lazily and only when
   requested or needed?
9. Does scoped readiness require only `handover_sessions` and
   `state_and_index_docs`?
10. Is `config_proposals` excluded from readiness, API output, and route
    selection?
11. Do route tests prove Postgres list and detail through FastAPI
    `TestClient`, not only repository reads?
12. Do tests cover optional fallback and required fail-closed behavior?
13. Are DSN and SQL errors redacted from public responses?
14. Are tombstoned documents excluded from Postgres responses?
15. Does `python3 scripts/check_index.py` pass after adding this
    artifact?

## Ready-to-Implement Gate

Implementation may start only after review confirms:

1. `PLAN-0024` is indexed in `docs/INDEX.md`.
2. `docs/handover/STATE.md` points to `main` and names `PLAN-0024` as
   the current planning artifact.
3. The behavior matrix above is accepted without ambiguity.
4. The planned write set for implementation excludes bridge,
   projector, and frontend work unless a failing route test proves a
   tiny adapter import is necessary.
5. The first implementation move is a failing route/provider test for
   `hybrid` plus `documents=postgres` with ready Postgres data.
6. Required-mode fail-closed and optional fallback tests exist before
   route production code changes.
7. Guarded DSN-backed `TestClient` proofs are planned and cannot be
   replaced by mocked repository-only tests.
