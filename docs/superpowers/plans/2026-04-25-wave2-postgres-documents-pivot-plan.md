---
id: PLAN-0020
title: Headless control plane Wave 2 Postgres documents pivot plan
version: 1.0.1
status: draft
created: 2026-04-25
last_amended: 2026-04-25
supersedes: PLAN-0020@1.0.0
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Headless Control Plane Wave 2 Postgres Documents Pivot Plan

## Purpose

This plan defines the first guarded Wave 2 read-route pivot after the
runtime projector slice. It keeps the scope intentionally narrow:

```text
revision-safe legacy bridge document outbox events
-> documents projector
-> documents Postgres read tables
-> documents readiness guard
-> /api/v1/documents route pivot
```

Documents are the safest first route pivot because they are
read-only, index-like, and already listed first in the Wave 2 pivot
order. This slice proves the route-router pattern without touching live
runtime state, commands, portfolio analytics, validation readiness,
incidents, public timeline events, or SSE.

## Authority

- `PLAN-0013`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `PLAN-0018`: `docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-plan.md`
- `PLAN-0019`: `docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`
- `DESIGN-0020`: `docs/architecture/TradingX_Frontend_Design.md`
- `DESIGN-0021`: `docs/architecture/TradingX_Dashboard_And_Design_System.md`

## Current State

Already complete:

1. The Postgres `documents.document`, `documents.document_revision`, and
   `documents.document_object_ref` tables exist.
2. The legacy bridge source inventory includes the two document
   families currently used by `LocalWebReadModel.list_documents` and
   `/api/v1/documents`:
   - `handover_sessions`
   - `state_and_index_docs`
3. The legacy bridge inventory also includes `config_proposals`, but
   those are exposed through config-proposal APIs, not through
   `LocalWebReadModel.list_documents`; they must not block or expand
   this documents route pivot.
4. The bridge emits deterministic `system.outbox_event` envelopes and
   source-status rows for the `documents` domain.
5. Existing document bridge events are not yet revision-safe: file-tree
   events use relative path as `source_event_id`, so editing the same
   file can conflict under the same outbox dedupe key instead of
   appending a new revision event.
6. The runtime projector proved the per-domain/source-family/mapper
   checkpoint pattern, transaction-bound writes, projected-watermark
   updates, and full-domain diagnostic status persistence.
7. `/api/v1/documents` and `/api/v1/documents/{document_id}` already
   have stable Wave 1 response shapes backed by legacy local reads.

Still missing:

1. A bridge-enrichment prerequisite that emits file-level,
   revision-safe, deletion-aware document events for
   `handover_sessions` and `state_and_index_docs`.
2. A documents write repository for idempotent materialization.
3. A documents read repository/protocol that returns the existing
   `DocumentRecord` contract without exposing table-shaped payloads.
4. A documents projector that consumes only supported `documents`
   outbox events.
5. A small domain read router that can choose legacy or Postgres for
   documents only.
6. Readiness gating proving documents routes pivot only when every
   required documents source family is fresh and fully projected.
7. Contract and parity tests for list/detail behavior in both legacy
   and Postgres modes.

## Non-Negotiable Locks

1. This slice may pivot only `/api/v1/documents` and
   `/api/v1/documents/{document_id}`.
2. It must not pivot `/api/v1/events`, `/api/v1/runtime`,
   `/api/v1/control-posture`, `/api/v1/incidents`,
   `/api/v1/validation/*`, `/api/v1/portfolio/*`, investigations,
   replays, or any legacy `/api/*` route.
3. It must not pivot SSE topics.
4. It must not introduce governed write routes, command-session
   behavior, document mutation routes, or object-content download
   behavior.
5. Legacy local mode remains database-free. Default web startup,
   default local component construction, and legacy routes must not
   build Postgres engines, repositories, projectors, or routers.
6. The documents projector must consume `system.outbox_event`; it must
   not reread filesystem documents directly.
7. The route pivot must be readiness-gated by the full `documents`
   source requirement set for the current documents API
   (`handover_sessions` and `state_and_index_docs`), not by filtered
   mapper readiness and not by unrelated config proposal sources.
8. The fallback path must be explicit. If Postgres mode is requested but
   documents readiness is blocked, the route must either fail closed
   when Postgres is required or serve legacy reads when hybrid fallback
   is allowed.
9. Postgres document rows must store logical source references, not
   absolute user-machine paths, unless the existing public API already
   exposes a local retrieval reference in legacy mode.
10. The implementation must preserve the Wave 1 document response
    envelope and not require frontend consumers to understand bridge
    payloads or Postgres table names.
11. Bridge enrichment is a prerequisite for implementation. If
    file-level document events cannot be made revision-safe and
    deletion-aware, the route pivot must remain blocked.

## Out Of Scope

- document write APIs
- document content retrieval or object blob storage
- config-proposal documents or changes to config-proposal APIs
- public timeline event pivot
- public event generation from document rows
- route pivots for runtime, control posture, incidents, validation,
  portfolio, investigations, replays, commands, or legacy `/api/*`
  endpoints
- generic all-domain router framework beyond the small surface needed
  to prove documents
- scheduler, market-day, portfolio, validation, incident, command,
  access, or investigation projectors
- frontend changes
- new migrations unless implementation proves the existing document
  schema cannot represent the stable Wave 1 document contract

## Implementation Shape

### Bridge document-event enrichment

Before projector materialization, enrich only the document bridge path
for `handover_sessions` and `state_and_index_docs`.

The bridge must emit file-level payload evidence sufficient for the
projector to build the existing API contract without touching the
filesystem:

- stable `document_id`
- document kind
- title
- preview text
- logical retrieval ref
- relative source path
- content hash
- source watermark
- deletion/tombstone marker when the file is absent from the current
  complete snapshot

The document event identity must be revision-safe. A file edit must
append a new outbox event rather than conflict with the prior event. Use
a stable logical `document_id` for the document row, but include a
revision discriminator such as content hash or source watermark in
`source_event_id` and the outbox dedupe key.

Deletion and rename handling must be explicit. The enriched source event
for each supported family must carry a complete active file set so the
projector can reconcile previously projected documents for that family
and tombstone documents no longer present. The read repository must
exclude tombstoned documents from `/api/v1/documents`.

If the existing table metadata cannot represent an active/tombstoned
state safely, implementation must add a reviewed migration before the
route pivot. It must not leave deleted documents visible.

### Document contracts

Extend `src/tradingx/controlplane/repositories.py` with a narrow
documents read protocol and DTOs only if existing `DocumentRecord`
cannot serve as the public contract cleanly.

The read boundary should support:

- `list_documents(page=PageRequest | None = None)`
- `get_document(document_id: str)`

The writer boundary should support:

- `upsert_document(record)`
- `upsert_document_revision(record)`
- `replace_document_object_refs(document_revision_id, refs)`
- optional `get_latest_document_revision(document_id)` when needed for
  no-op detection

Keep writer and reader responsibilities separate. Route code should
depend only on the read boundary.

### Documents projector

Add a documents-specific projector module or extend the existing
projector module with a documents runner only if the code stays clearly
separated from runtime mapping. Prefer concrete mapper functions over a
premature all-domain projector abstraction.

Projection names must follow the same per-domain/source-family/mapper
pattern:

```text
documents_projection:documents:handover_sessions:v1
documents_projection:documents:state_and_index_docs:v1
```

The projector must:

1. Load the family-specific checkpoint.
2. Read only `aggregate_type = 'documents'` outbox rows for that source
   family, ordered by `created_at_utc ASC, outbox_event_id ASC`.
3. Map each source event to one or more document records and revisions.
4. Write document rows in the same transaction as projected source
   status, checkpoint, and derived domain status updates.
5. Advance `projected_watermark` only after materialization succeeds or
   after a recognized idempotent no-op.
6. Persist `system.domain_projection_status` for the full `documents`
   domain only, never for a filtered subset.

### Mapping rules

For each document source event, store a stable document identity that
matches the existing API semantics:

| Source family | Document identity |
| --- | --- |
| `handover_sessions` | one document per handover session file, keyed by session stem |
| `state_and_index_docs` | one document each for `STATE.md` and `INDEX.md` |

The source event may represent a file-tree snapshot. If the enriched
bridge payload contains multiple observed files, the mapper should
materialize each file as its own logical document. If a source event
still contains only a family-level summary without per-file payloads,
implementation must stop before projector work and block the pivot with
an explicit `document_file_payload_missing` readiness blocker. It must
not invent document rows from filesystem reads inside the projector.

Required table mapping:

| Table | Mapping |
| --- | --- |
| `documents.document.document_id` | stable logical document ID |
| `document_type` | existing `DocumentRecord.kind` value |
| `title` | existing title semantics |
| `created_at_utc` | earliest known document observation or event occurrence |
| `updated_at_utc` | latest source event occurrence for that document |
| `source_ref` | logical source ref from bridge envelope |
| `metadata_json` | preview, retrieval ref, source family, source identity, source event ID, payload hash |
| `documents.document_revision.document_revision_id` | deterministic document ID plus source watermark or content hash |
| `revision_number` | monotonic per document, unchanged on idempotent reruns |
| `documents.document_object_ref.object_uri` | logical retrieval ref used by the API |

Tombstoned documents must be hidden from document list/detail reads. The
preferred representation is document metadata that marks the latest
known state as inactive plus a tombstone revision carrying the source
event that observed the deletion. If that is not queryable without
ambiguous JSON filtering, add a reviewed schema migration before the
pivot.

If the same natural key appears with different payload content, the
projector must raise a redacted conflict and roll back the batch.

### Documents read router

Introduce the smallest domain router needed for documents. It should be
constructed only when Postgres or hybrid mode is explicitly selected.

The router must evaluate:

- control-plane store mode: `legacy`, `hybrid`, or `postgres`
- optional domain override for `documents`
- `TRADINGX_POSTGRES_REQUIRED`
- current full-domain `documents` projection status
- availability of the Postgres document read repository

`TRADINGX_POSTGRES_REQUIRED=true` has precedence whenever the effective
documents store is Postgres. A required Postgres deployment must not
silently serve legacy documents after requesting the documents Postgres
path.

Expected behavior:

| Effective documents store | Required | Ready | Result |
| --- | --- | --- | --- |
| `legacy` | any | any | use legacy read model |
| `postgres` | any | ready | use Postgres documents |
| `postgres` | `true` | blocked | fail closed with a stable 503 diagnostic |
| `postgres` | `false` | blocked | use legacy with response metadata showing fallback |

In `hybrid` mode, the effective documents store is computed from the
domain override. `documents=legacy` is `legacy`; `documents=postgres` is
`postgres`.

Do not make `system.domain_projection_status` a general router
authority for every domain in this slice. It is authority only for the
documents pivot implemented here.

## Execution Plan

### 0. Baseline

Run before edits:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence src/tradingx/web tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_legacy_bridge.py tests/unit/test_controlplane_runtime_projector.py tests/unit/test_web_app.py -q
python3 scripts/check_index.py
git diff --check
```

Guarded Postgres baseline:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py tests/integration/test_controlplane_postgres_runtime_projector.py tests/integration/test_controlplane_postgres_repositories.py -q
```

### 1. First TDD checkpoint

Create failing unit tests before production code. The tests must cover:

1. Document bridge enrichment changes an edited file into a new
   outbox event by including a revision discriminator in
   `source_event_id`.
2. Document bridge enrichment emits file-level payloads for
   `handover_sessions`, `STATE.md`, and `INDEX.md`.
3. Document bridge enrichment emits complete active file sets so deleted
   or renamed files can be tombstoned without projector filesystem
   reads.
4. Documents projector reads only `handover_sessions` and
   `state_and_index_docs`; `config_proposals` is not selected and does
   not block `/api/v1/documents` readiness.
5. Per-family checkpoints do not strand deferred or newly supported
   document events.
6. File-level source payloads map to stable document IDs, kinds, titles,
   previews, and logical retrieval refs.
7. Family-level payloads without file-level evidence block projection
   instead of rereading the filesystem.
8. Projected watermarks advance only after document rows and revisions
   are durable.
9. Reruns are idempotent and do not duplicate revisions or object refs.
10. Payload conflicts are redacted and roll back checkpoints and source
   statuses.
11. Tombstoned documents disappear from list/detail reads without
    affecting unrelated active documents.
12. Full `documents` readiness stays blocked until all required document
   families are projected and fresh.
13. The document router uses legacy mode by default and constructs no
   Postgres objects during default local web startup.
14. The document router fails closed in required Postgres mode when
    documents readiness is blocked.
15. The document router fails closed in
    `hybrid` plus `documents=postgres` plus
    `TRADINGX_POSTGRES_REQUIRED=true` when documents readiness is
    blocked.
16. The document router falls back to legacy in non-required hybrid mode
    when documents readiness is blocked.
17. `/api/v1/documents/{document_id}` preserves the current 404 error
    shape.

### 2. Bridge enrichment

Implement the document bridge enrichment and tests first. This step is a
hard prerequisite for projector work. If enrichment reveals that bridge
events cannot carry complete file-level evidence and revision-safe event
identity, stop and revise the plan rather than implementing a projector
that rereads files.

### 3. Document repository boundaries

Add document read and write repository boundaries with narrow DTOs. Add
fake repositories for router and projector unit tests.

If the existing `PostgresControlPlaneRepository` grows document reads,
keep the methods focused on read behavior only. Write behavior belongs
in a separate projection repository.

### 4. Documents materialization

Implement the Postgres write repository and tests for:

1. Insert document plus first revision.
2. Insert a later revision for the same document.
3. Idempotent rerun of the same revision.
4. Natural-key conflict on changed payload.
5. Object-ref replacement without duplicates.
6. Tombstone revision and hidden read behavior for deleted documents.
7. Transaction rollback when any document write fails.

### 5. Documents projector orchestration

Implement a bounded `run_once` documents projector with the same
transaction rules proven by the runtime projector:

1. Load family-specific checkpoint.
2. Read ordered outbox events for one source family.
3. Materialize documents and revisions.
4. Update projected source statuses.
5. Save checkpoint metadata with ordered cursor fields.
6. Save full-domain documents diagnostic status.
7. Return structured counts for seen, projected, no-op, skipped,
   conflicts, source updates, and checkpoint position.

### 6. Documents route router

Wire the documents routes through a small domain router. Keep route
payload construction explicit and preserve current response shapes:

- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`

The router must not affect legacy `/api/documents`, explorer routes,
platform routes, or any non-document `/api/v1` route.

### 7. Real Postgres proof

Add guarded integration tests for:

1. Bridge-seeded handover/session document events materialize rows.
2. Bridge-seeded `STATE.md` and `INDEX.md` document events materialize
   rows.
3. Config proposal source events do not appear in `/api/v1/documents`
   and do not block documents readiness.
4. Edited document files append later revisions instead of conflicting
   under the original outbox dedupe key.
5. Deleted or renamed document files are tombstoned and disappear from
   Postgres document reads.
6. Reruns do not duplicate documents, revisions, or object refs.
7. Checkpoint resume processes only later ordered document events.
8. Conflict rollback leaves document rows, checkpoints, source statuses,
   and domain status unchanged.
9. Full `documents` domain status blocks on stale or unprojected
   document source families.
10. Full `documents` domain status becomes ready only when all required
   document families are fresh and projected.
11. Postgres document reads preserve list/detail ordering and 404
   semantics.
12. `/api/v1/documents` pivots to Postgres only when readiness passes.
13. Required Postgres mode fails closed for blocked documents readiness,
    including `hybrid` with `documents=postgres`.

### 8. Safety closeout

Extend legacy startup tests so default local web construction fails if
documents Postgres repositories, documents projector, or document router
construction sneaks into legacy mode.

Run:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence src/tradingx/web tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_legacy_bridge.py tests/unit/test_controlplane_runtime_projector.py tests/unit/test_web_app.py -q
python3 scripts/check_index.py
git diff --check
```

Guarded Postgres final:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py tests/integration/test_controlplane_postgres_runtime_projector.py tests/integration/test_controlplane_postgres_repositories.py tests/integration/test_controlplane_postgres_documents_projector.py -q
```

## Expected Deliverables

Production files:

- `src/tradingx/controlplane/repositories.py`
- `src/tradingx/controlplane/legacy_bridge.py`
- `src/tradingx/controlplane/document_projectors.py` or a clearly
  separated documents section in `src/tradingx/controlplane/projectors.py`
- `src/tradingx/persistence/repositories/document_projection.py`
- `src/tradingx/persistence/repositories/postgres.py`
- `src/tradingx/web/app.py`
- optional small router module under `src/tradingx/web/`

Test files:

- `tests/unit/test_controlplane_documents_projector.py`
- `tests/unit/test_controlplane_projection_state_contracts.py`
- `tests/unit/test_web_app.py`
- `tests/integration/test_controlplane_postgres_documents_projector.py`
- `tests/integration/test_controlplane_postgres_repositories.py`

Documentation files:

- `docs/INDEX.md` if new artifacts are added
- `docs/handover/STATE.md` if project state changes

## Adversarial Review Checklist

Before implementation starts, review must challenge:

1. Whether this slice accidentally pivots non-document routes.
2. Whether the documents projector rereads filesystem state instead of
   consuming outbox event payloads.
3. Whether bridge document events contain enough file-level evidence and
   revision-safe event identities to
   materialize the existing document API contract.
4. Whether `config_proposals` accidentally expands or blocks the
   `/api/v1/documents` scope.
5. Whether deleted or renamed files can leave stale Postgres documents
   visible.
6. Whether full documents readiness can be confused with filtered
   mapper readiness.
7. Whether route fallback behavior can hide a required-Postgres failure.
8. Whether response metadata leaks absolute local paths beyond the
   existing legacy retrieval references.
9. Whether document revisions churn on no-op reruns.
10. Whether per-family checkpoints prevent newly supported document
   families from being stranded.
11. Whether conflicts roll back source watermarks and domain status.
12. Whether default local web startup remains Postgres-free.
13. Whether public timeline or SSE behavior changes accidentally.

## Definition Of Done

This plan is implementation-ready only after adversarial review confirms
that:

1. documents are still the only pivoted domain,
2. bridge enrichment proves document materialization from outbox events
   without projector filesystem reads,
3. readiness and fallback behavior are testable and fail closed where
   required,
4. legacy local startup remains database-free, and
5. the validation gates above are enough to prove parity and safety.
