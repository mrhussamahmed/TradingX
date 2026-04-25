---
id: PLAN-0022
title: Headless control plane Wave 2 Postgres documents projector implementation plan
version: 1.0.1
status: draft
created: 2026-04-25
last_amended: 2026-04-25
supersedes: PLAN-0022@1.0.0
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Headless Control Plane Wave 2 Postgres Documents Projector Implementation Plan

## Purpose

This plan scopes Slice 3 of `PLAN-0021`: build the documents projector
that consumes enriched legacy-bridge document outbox events and
materializes Postgres document rows transactionally.

This is a review plan only. It does not pivot web routes, does not make
`system.domain_projection_status` authoritative for scoped document
readiness, and does not expand `/api/v1/documents` beyond the current
public document API.

The target path for this slice is:

```text
document outbox events
-> documents projector
-> documents.document, documents.document_revision, and documents.document_object_ref
-> projected source watermarks
-> per-family projector checkpoints
-> scoped route-readiness report returned to callers
```

## Authority

- `PLAN-0021`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-implementation-plan.md`
- `PLAN-0020`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-plan.md`
- `PLAN-0019`: `docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-plan.md`
- `PLAN-0018`: `docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`

## Current Code Facts

These facts are true at the start of this slice:

1. `DocumentFileTreeSourceAdapter` emits active file events with
   `document_event_kind = "file_observed"` and revision-safe
   `source_event_id = "file:<relative_path>:<content_hash>"`.
2. Active document payloads include the public `document_id`,
   `document_kind`, `title`, `preview`, `relative_path`,
   `logical_retrieval_ref`, `content_hash`, `content_text`, and
   `internal_document_key`.
3. `DocumentFileTreeSourceAdapter` emits `inventory_snapshot` events for
   complete readable source-family inventories, including empty
   inventories.
4. Partial document read failures still emit safe active file events for
   readable files, but suppress inventory snapshots so a partial active
   set cannot become tombstone authority.
5. `document_api_source_families()` returns only
   `handover_sessions` and `state_and_index_docs`; `config_proposals`
   remains outside the current documents API scope.
6. `DocumentProjectionWriteRepository` currently inserts revisions and
   tombstones absent active documents, but it does not yet expose the
   transaction-bound revision-number lookup the projector needs for
   idempotent replay.
7. The current document projection writer does not yet expose normalized
   object-ref replacement or tombstone-revision creation. This slice
   must add those contracts before projector materialization.
8. `PostgresProjectionStateRepository` already supports ordered outbox
   reads, per-projection checkpoints, source-status reads/writes, and
   transaction-bound repository views.
9. The runtime projector already provides usable patterns for ordered
   cursors, per-family checkpoints, projected-watermark advancement,
   and rollback behavior.

## Non-Negotiable Locks

1. The projector consumes only outbox envelopes and projection state. It
   must not read local markdown files.
2. The projector selects only `handover_sessions` and
   `state_and_index_docs` for this route-scoped documents slice.
3. `config_proposals` must not be selected, checkpointed, materialized
   into `/api/v1/documents`, or used to block scoped route readiness.
4. Projection checkpoints are per source family and mapper version:

   ```text
   documents_projection:documents:handover_sessions:v1
   documents_projection:documents:state_and_index_docs:v1
   ```

5. Public `document_id` values stay bare and route-compatible:
   `STATE`, `INDEX`, and handover session stems. Internal namespaced
   keys may remain in metadata only.
6. The same deterministic revision key with different payload is a
   conflict. The same public document ID with a new content hash is a
   later revision, not a conflict.
7. Tombstones are inventory-driven and source-family scoped.
8. Empty inventories are valid evidence and can tombstone the last
   previously active document for that source family.
9. Projected source watermarks and checkpoints advance only after
   document writes and tombstones are durable in the same transaction.
10. The scoped readiness report is returned by the projector result but
    is not saved to `system.domain_projection_status`.
11. Unknown event kinds can be checkpointed only under the current mapper
    version. A later mapper that supports them must use a new mapper
    version and therefore a new per-family checkpoint name.
12. Scoped readiness requirements come from the static documents API
    source registry first, not from whichever source-status rows happen
    to exist. A missing `handover_sessions` or `state_and_index_docs`
    status row must block readiness.
13. Every active document revision writes its logical retrieval ref to
    `documents.document_object_ref`; metadata-only retrieval refs are
    not enough for this slice.
14. Every inventory deletion writes an inactive document summary plus a
    tombstone revision carrying the deletion-observing inventory event.
15. Revision-number allocation is owned by the repository inside the
    projector transaction and must use a per-document lock,
    serializable retry, or equivalent concurrency-safe mechanism.

## Proposed Code Shape

Add a document-specific projector module:

- `src/tradingx/controlplane/document_projectors.py`

Use these public objects:

- `DOCUMENTS_MAPPER_VERSION = "v1"`
- `DOCUMENTS_SOURCE_REGISTRY_VERSION = "legacy-bridge-documents-projector-v1"`
- `DOCUMENTS_DOMAIN_NAME = "documents"`
- `document_projection_name(domain_name, source_family, mapper_version)`
- `DocumentsProjector`
- `DocumentsProjectionBatchResult`
- `DocumentsProjectionFamilyResult`
- `document_from_outbox_event(event, revision_number)`
- `document_revision_from_outbox_event(event, revision_number)`
- `documents_route_readiness_from_source_statuses(...)`

The documents projector unit of work should expose both repositories in
one transaction:

```python
class DocumentsProjectorUnitOfWork(Protocol):
    @contextmanager
    def transaction(
        self,
    ) -> Iterator[
        tuple[ProjectionStateRepository, DocumentProjectionRepository]
    ]: ...
```

`ProjectionStateRepository` should match the runtime projector boundary:

- `list_outbox_events_after`
- `get_outbox_event_cursor`
- `load_projection_checkpoint`
- `save_projection_checkpoint`
- `get_projection_source_status`
- `list_projection_source_statuses`
- `upsert_projection_source_status`

`DocumentProjectionRepository` should extend the current write boundary
with transaction-bound revision lookup, allocation, object refs, and
tombstone revisions:

- `get_document_revision(document_revision_id)`
- `allocate_document_revision_number(document_id, document_revision_id)`
- `upsert_document_revision(document, revision)`
- `replace_document_object_refs(document_revision_id, refs)`
- `tombstone_documents_absent_from_inventory_with_revisions(...)`

These methods belong on the projection writer boundary rather than the
web read boundary because they are projector bookkeeping, not route read
behavior.

## Revision Number Strategy

The projector cannot invent revision numbers from content hashes alone:
the database has a unique `(document_id, revision_number)` contract,
replays must reuse the original revision number, and overlapping
projector runs must not both allocate the same next number.

Implement this deterministic flow for every active file event:

1. Build a stable `document_revision_id` from the public document ID,
   source family, source identity, and `source_event_id`.
2. Ask the projection repository for that exact revision ID.
3. If it exists, reuse its `revision_number` and call
   `upsert_document_revision` with the current event-derived document
   and revision payload. Existing repository hardening then catches
   same-revision payload drift while preserving valid tombstone replay.
4. If it does not exist, call
   `allocate_document_revision_number(document_id, document_revision_id)`.
5. The allocation method must run inside the same transaction as the
   eventual insert and must acquire a per-document lock, use
   `SERIALIZABLE` plus retry, or use an equivalent repository-level
   guard before reading the latest revision number.
6. The allocation method returns the existing revision number when the
   revision ID was inserted by a concurrent transaction, otherwise it
   returns the next monotonic number.
7. Insert through `upsert_document_revision`.

The revision ID must not include `observed_at_utc`, outbox
`created_at_utc`, random IDs, or any value that changes on an unchanged
bridge rerun.

## Event Mapping Rules

For `file_observed` events:

1. Reject missing or empty `document_id`, `document_kind`, `title`,
   `content_hash`, or `logical_retrieval_ref`.
2. Create `DocumentProjectionDocument` with:
   - `document_id` from the payload public ID.
   - `document_kind` from `document_kind`.
   - `title` from `title`.
   - `preview` from `preview`.
   - `logical_retrieval_ref` from `logical_retrieval_ref`.
   - `document_state = "active"`.
   - `created_at_utc` and `updated_at_utc` from the outbox event's
     deterministic occurrence timestamp. The repository can preserve
     the earliest `created_at_utc` when updating an existing document.
   - `source_ref` from the envelope.
   - metadata containing `source_family`, `source_identity`,
     `source_event_id`, `source_watermark`, `content_hash`,
     `internal_document_key`, `relative_path`, outbox cursor fields, and
     projector version.
3. Create `DocumentProjectionRevision` with:
   - stable `document_revision_id`.
   - resolved `revision_number`.
   - `created_at_utc` from the event occurrence timestamp.
   - `source_ref` from the envelope.
   - metadata containing the same stable source facts plus
     `content_hash`; it may include redacted `content_text` if the route
     or future retrieval work needs it, but the existing route response
     must not expand in this slice.
4. Replace object refs for the revision with one normalized ref:
   - `object_uri = logical_retrieval_ref`.
   - `content_type = "text/markdown"` for the current markdown document
     sources.
   - `sha256_hash = content_hash`.
   - metadata containing source family, source identity, source event
     ID, relative path, and mapper version.
5. Object-ref replacement must be idempotent on rerun and must not
   duplicate refs for the same revision.

For `inventory_snapshot` events:

1. Read `active_document_ids` as the authoritative active public IDs for
   that source family.
2. Call
   `tombstone_documents_absent_from_inventory_with_revisions(source_family, active_document_ids, ...)`
   after all earlier active file events in ordered cursor sequence have
   been processed.
3. That repository method must update each missing active document to an
   inactive or tombstoned summary and append a tombstone revision for
   each affected document in the same transaction.
4. Tombstone revision IDs must be deterministic from the missing public
   document ID and inventory source event, and revision numbers must use
   the same concurrency-safe allocation contract as active revisions.
5. Tombstone revision metadata must carry the deletion-observing
   inventory outbox event ID, source ref, source family, source
   watermark, active-set hash, mapper version, and
   `document_state = "tombstoned"`.
6. Treat an empty active ID tuple as valid and tombstone all currently
   active documents for that source family.

For unknown document event kinds:

1. Skip them.
2. Count them as skipped.
3. Do not advance projected watermarks for skipped rows.
4. Checkpoint skipped rows only under the current mapper-version-specific
   projection name and record skipped event kinds in checkpoint metadata.

## Inventory Ordering Guard

The outbox read boundary orders by `created_at_utc ASC,
outbox_event_id ASC`. A documents projector must not rely on broad
kind-based sorting because an older inventory snapshot can hide a newer
document if all active rows are globally processed before all inventory
rows.

Use ordered cursor processing as the default:

```text
read row
-> project active file, or apply inventory tombstone
-> advance source status for that row
-> move to next row
```

Add a narrow same-cursor guard for tests and fixed-clock runs:

1. Persist each active document's latest active outbox cursor in document
   metadata.
2. Extend tombstone reconciliation to avoid tombstoning a document whose
   latest active cursor is strictly after the inventory event cursor.
3. Add a unit test and a Postgres test where an inventory row and active
   row share the same timestamp but their outbox IDs sort in the
   surprising order. The final visible document state must match cursor
   order plus inventory active-set semantics.

This keeps old inventory snapshots from overwriting newer active
evidence while still allowing later empty inventories to tombstone the
last document in a family.

## Source Watermark And Checkpoint Rules

Each source family gets one projection stream and one checkpoint. The
projector must not checkpoint a shared `documents` cursor.

For each family run:

1. Load the family projection checkpoint.
2. Resolve old checkpoints that have `last_outbox_event_id` but missing
   ordered cursor metadata by calling `get_outbox_event_cursor`.
3. Read outbox events after that cursor with:
   - `aggregate_types = ("documents",)`
   - `source_families = (source_family,)`
   - caller-supplied `batch_size`
4. Process events in ordered cursor sequence.
5. After each projected active file or inventory event, load the current
   matching `domain_projection_source_status` row.
6. Do not blindly set `projected_watermark` to the individual outbox
   event's `source_watermark`. Document source statuses use the
   collect-level `source_watermark` from `ordered_event_watermark`, while
   individual rows carry per-event watermarks.
7. Set `projected_watermark = status.source_watermark` only when the
   consumed event's `source_event_id` equals
   `status.metadata["latest_source_event_id"]`. This proves the
   projector consumed the latest bridge event for the current source
   collect.
8. When processing an older event, preserve the previous
   `projected_watermark` and write only progress metadata such as the
   last projected outbox event ID and dedupe key.
9. Update the matching source-status metadata with:
   - existing `source_watermark`
   - the projected watermark rule above
   - existing source freshness and readiness fields
   - metadata for `last_projected_outbox_event_id`,
     `last_projected_dedupe_key`, `mapper_version`, `projection_name`,
     and `projected_at_utc`
10. After the family batch succeeds, save the checkpoint with:
   - `last_outbox_event_id`
   - `last_processed_at_utc`
   - the current collect-level source watermark when the latest source
     event was consumed, otherwise the last event-level watermark
   - `last_source_observed_at_utc`
   - `lag_seconds`
   - `status = "caught_up"` when fewer than `batch_size` rows were read,
     otherwise `"running"`
   - metadata for `cursor_created_at_utc`,
     `cursor_outbox_event_id`, supported source family, mapper version,
     and last projected dedupe key.

Any exception from document writes, tombstones, source-status updates,
or checkpoint writes must roll back the entire transaction.

## Scoped Readiness

The projector result should include a scoped route-readiness report for
the current documents API source families only:

```text
handover_sessions
state_and_index_docs
```

The report should use `evaluate_projection_readiness` with requirements
derived from the static legacy source inventory filtered by
`document_api_source_families()`, then joined to whatever source-status
rows exist. This deliberately differs from a status-row-only filter:
missing API families must remain requirements so they produce
missing-source blockers.

Rules:

1. Do not call `save_domain_projection_status_from_readiness`.
2. Do not write a ready `documents` row into
   `system.domain_projection_status`.
3. Require each scoped family to have a ready source status and matching
   projected watermark.
4. Block readiness on stale source status, unprojected source watermark,
   missing initial import, or inactive write path for mutable sources.
5. Ignore `config_proposals` for this scoped report.
6. Add an explicit missing-family test where `state_and_index_docs`
   exists and is projected, `handover_sessions` has no source-status
   row, and the scoped readiness report remains blocked.

## Slice 0: Baseline

Run before edits:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py -q
python3 scripts/check_index.py
git diff --check
```

Guarded Postgres baseline:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_repositories.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py -q
```

If the guarded DSN is unavailable, record that explicitly.

## Slice 1: Repository Lookup Contract

Goal: make revision-number allocation, object refs, and tombstone
revisions expressible before projector code.

Owned paths:

- `src/tradingx/controlplane/repositories.py`
- `src/tradingx/persistence/repositories/document_projection.py`
- `tests/unit/test_controlplane_repository_contracts.py`
- `tests/integration/test_controlplane_postgres_repositories.py`

First failing tests:

1. `test_document_projection_writer_can_get_revision_by_id`
2. `test_document_projection_writer_allocates_revision_number_under_lock`
3. `test_document_projection_writer_returns_existing_number_for_existing_revision`
4. `test_document_projection_writer_returns_none_for_missing_revision`
5. `test_document_projection_writer_replaces_object_refs_idempotently`
6. `test_document_projection_writer_tombstones_with_revision_history`
7. `test_document_projection_writer_cursor_bound_tombstone_keeps_newer_active_doc`
8. `test_document_projection_writer_concurrent_allocations_do_not_share_number`

Implementation notes:

1. Add lookup, allocation, object-ref replacement, and tombstone revision
   methods to `DocumentProjectionWriteRepository`.
2. Implement the methods in `PostgresDocumentProjectionRepository`.
3. Keep all methods transaction-bound when the repository is created
   with a transaction connection.
4. Use a per-document lock, serializable retry, or equivalent
   repository-level allocation guard before assigning a new revision
   number.
5. Extend tombstone reconciliation only as far as needed for
   cursor-bound safety; preserve current source-family active-set
   behavior.

Green gate:

```bash
uv run pytest tests/unit/test_controlplane_repository_contracts.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_repositories.py -q
```

## Slice 2: Unit Projector

Goal: make the documents projector behavior green with fake
repositories and rollback-capable fake units of work.

Owned paths:

- `src/tradingx/controlplane/document_projectors.py`
- `tests/unit/test_controlplane_documents_projector.py`

First failing tests:

1. `test_documents_projector_reads_only_api_document_source_families`
2. `test_documents_projector_does_not_select_config_proposals`
3. `test_documents_projector_uses_per_family_projection_names`
4. `test_documents_projector_materializes_file_events`
5. `test_documents_projector_public_document_ids_are_route_keys`
6. `test_documents_projector_reuses_revision_number_on_existing_revision`
7. `test_documents_projector_assigns_next_revision_number_for_new_content`
8. `test_documents_projector_idempotent_rerun_does_not_duplicate_revisions`
9. `test_documents_projector_replaces_object_refs_for_file_revision`
10. `test_documents_projector_same_revision_payload_mismatch_conflicts`
11. `test_documents_projector_inventory_snapshot_tombstones_missing_docs`
12. `test_documents_projector_inventory_tombstone_writes_revision_history`
13. `test_documents_projector_empty_inventory_tombstones_last_document`
14. `test_documents_projector_inventory_cursor_guard_keeps_newer_active_doc`
15. `test_documents_projector_advances_collect_watermark_only_on_latest_source_event`
16. `test_documents_projector_rollback_does_not_advance_checkpoint_or_watermark`
17. `test_documents_projector_returns_scoped_route_readiness_without_domain_status`
18. `test_documents_projector_scoped_readiness_blocks_when_api_family_status_missing`
19. `test_documents_projector_per_family_checkpoint_replays_old_rows`
20. `test_documents_projector_resolves_legacy_checkpoint_cursor_from_event_id`

Implementation notes:

1. Reuse helper patterns from `projectors.py` where they are stable and
   small, but keep document-specific mapping in
   `document_projectors.py`.
2. Use fake repositories to prove exact call order: document writes,
   tombstones, projected source-status updates, then checkpoint writes.
3. Make the fake unit of work roll back in-memory writes on exceptions.
4. Assert no call is made to a domain-status persistence method.
5. Assert readiness requirements are built from the static API source
   registry, not only from existing source-status rows.

Green gate:

```bash
uv run pytest tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py -q
```

## Slice 3: Postgres Projector Proof

Goal: prove the projector works transactionally against real Postgres
state.

Owned paths:

- `tests/integration/test_controlplane_postgres_documents_projector.py`
- `tests/integration/test_controlplane_postgres_projection_state.py`
- `tests/integration/test_controlplane_postgres_repositories.py`

Required proof cases:

1. Bridge-seeded `STATE` and `INDEX` events materialize active document
   rows and revision rows.
2. Bridge-seeded handover session events materialize active document
   rows and revision rows.
3. A second projector run over the same events does not create duplicate
   revisions and does not bump resource state unnecessarily.
4. Editing `STATE.md` creates a later revision for public document ID
   `STATE` without conflict.
5. Replaying an already materialized old revision after a later revision
   does not roll the document summary backward.
6. Replaying an already materialized active revision after an inventory
   tombstone no-ops only when stable fields still match.
7. Same deterministic revision ID with different revision payload raises
   `RepositoryConflictError`.
8. Deleting one handover session tombstones only that document and hides
   it from `list_documents` and `get_document`.
9. Deleting one handover session appends a tombstone revision and keeps
   the previous active revision history.
10. Empty inventory tombstones the last previously active document for a
   family.
11. Partial-read bridge runs without inventory cannot tombstone a
    missing active document.
12. Active document revisions write normalized object refs and reruns do
    not duplicate those refs.
13. A projector conflict rolls back document rows, object refs, source
    projected watermarks, and family checkpoint changes.
14. Family checkpoints are independent; a new family checkpoint can
    replay old rows even if another family is caught up.
15. Existing checkpoints with `last_outbox_event_id` and missing cursor
    metadata resume through `get_outbox_event_cursor`.
16. `config_proposals` outbox rows are ignored and cannot advance a
    scoped documents checkpoint.
17. No ready `system.domain_projection_status` row is written for
    `documents` by this projector.
18. Projected source watermark equals the bridge collect-level source
    watermark only after the source status's latest source event is
    consumed.
19. Scoped readiness stays blocked when one API source family has no
    source-status row.
20. Concurrent new revisions for the same document allocate distinct
    monotonic revision numbers or retry to a stable idempotent result.

Green gate:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_documents_projector.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_repositories.py -q
```

## Slice 4: Safety And Closeout

Goal: prove the documents projector did not leak into web startup,
runtime projector behavior, or broader documents-domain readiness.

Run:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py tests/unit/test_web_app.py -q
python3 scripts/check_index.py
git diff --check
```

Guarded Postgres closeout:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_documents_projector.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_repositories.py tests/integration/test_controlplane_postgres_legacy_bridge.py -q
```

Run an unfinished-marker scan across touched production, test, and plan
files before review.

## Implementation Order

1. Baseline gates.
2. Repository lookup and cursor-bound tombstone contract tests.
3. Repository lookup implementation.
4. Documents projector unit tests with fake repositories.
5. Documents projector implementation.
6. Real Postgres projector integration tests.
7. Closeout validation and review.

Do not begin the route pivot from `PLAN-0021` Slice 4 until this plan's
Slice 3 Postgres projector proof is green and reviewed.

## Adversarial Review Checklist

Review this plan against these risks before implementation starts:

1. Can the projector assign revision numbers idempotently without
   relying on volatile timestamps?
2. Can a same-revision payload mismatch still be detected after adding
   revision lookup?
3. Can replaying an active revision over a later tombstone remain safe
   without resurrecting deleted documents?
4. Can inventory snapshots tombstone deletions without reading the
   filesystem?
5. Can an older inventory snapshot hide a newer active document in an
   equal-timestamp cursor tie?
6. Can empty inventories prove last-file deletion?
7. Can partial bridge read failures accidentally become tombstone
   authority?
8. Can `config_proposals` enter the scoped documents projection through
   source-family filters?
9. Can scoped readiness overwrite full-domain `documents` status?
10. Can a family checkpoint move past rows for another family?
11. Can rollback leave projected watermarks or checkpoints ahead of
    document writes?
12. Can public document IDs become prefixed internal IDs?
13. Can a later revision roll the summary backward when replayed out of
    order?
14. Can DSN-backed tests prove the same repository behavior used by the
    future route pivot?
15. Can a missing API source family be hidden by building readiness
    requirements from existing status rows only?
16. Can normalized object refs drift from document metadata or duplicate
    on rerun?
17. Can deletion history be audited through `documents.document_revision`
    after inventory tombstones?
18. Can concurrent projectors race on `latest + 1` revision allocation?
