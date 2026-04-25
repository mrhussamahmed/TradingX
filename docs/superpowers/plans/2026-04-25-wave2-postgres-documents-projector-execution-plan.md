---
id: PLAN-0023
title: Headless control plane Wave 2 Postgres documents projector execution plan
version: 1.0.1
status: draft
created: 2026-04-25
last_amended: 2026-04-25
supersedes: PLAN-0023@1.0.0
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Headless Control Plane Wave 2 Postgres Documents Projector Execution Plan

## Purpose

This plan turns approved `PLAN-0022` into an implementation sequence for
the documents projector. It is intentionally narrower than `PLAN-0022`:
it names the code moves, first failing tests, transaction choices, and
green gates for the implementation branch.

This is a review artifact only. No production code should be changed
until this plan has been reviewed.

## Authority

- `PLAN-0022`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-projector-implementation-plan.md`
- `PLAN-0021`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-implementation-plan.md`
- `PLAN-0020`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-plan.md`
- `PLAN-0019`: `docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-plan.md`

## End State

The slice is complete when:

1. A document-specific projector consumes legacy bridge outbox rows for
   `handover_sessions` and `state_and_index_docs`.
2. Active file events materialize `documents.document`,
   `documents.document_revision`, and `documents.document_object_ref`.
3. Inventory events tombstone absent documents and append tombstone
   revisions.
4. Revision-number allocation is concurrency-safe and repository-owned.
5. Per-family checkpoints advance only after durable document writes,
   object refs, tombstone revisions, and projected source-status updates.
6. Scoped documents route readiness is returned from static API-family
   requirements and does not write `system.domain_projection_status`.
7. `config_proposals` remains outside the projector scope.
8. Existing web startup remains Postgres-free unless a later route pivot
   deliberately enables Postgres.

## Out Of Scope

Do not implement these in this slice:

1. `/api/v1/documents` route pivot.
2. Fallback or required-Postgres route behavior.
3. New migrations.
4. Domain-wide `documents` projection status persistence.
5. Config proposal materialization into the documents API.
6. File-system reads inside the projector.

## Owned Files

Primary write set:

- `src/tradingx/controlplane/repositories.py`
- `src/tradingx/controlplane/document_projectors.py`
- `src/tradingx/persistence/repositories/document_projection.py`
- `src/tradingx/persistence/repositories/projection_state.py`
- `src/tradingx/persistence/repositories/__init__.py`
- `tests/unit/test_controlplane_repository_contracts.py`
- `tests/unit/test_controlplane_documents_projector.py`
- `tests/integration/test_controlplane_postgres_repositories.py`
- `tests/integration/test_controlplane_postgres_documents_projector.py`
- `tests/integration/test_controlplane_postgres_projection_state.py`
- `tests/unit/test_web_app.py`

Do not edit route implementation files unless a no-Postgres startup
regression forces a defensive test update. The route pivot stays in the
next slice.

## Baseline Gate

Run before edits:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py tests/unit/test_web_app.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py tests/unit/test_web_app.py -q
python3 scripts/check_index.py
git diff --check
```

Guarded baseline:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_repositories.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py -q
```

If the guarded DSN is unavailable, record that and continue with local
tests only until the final proof can be run in a configured shell.

## Slice A: Repository Contract Tests

Goal: make the new document write contract explicit before touching the
projector.

Add failing unit contract tests in
`tests/unit/test_controlplane_repository_contracts.py`:

1. `test_document_projection_writer_exposes_revision_lookup_and_allocation`
2. `test_document_projection_writer_exposes_object_ref_replacement`
3. `test_document_projection_writer_exposes_tombstone_revision_reconciliation`

Add failing Postgres tests in
`tests/integration/test_controlplane_postgres_repositories.py`:

1. `test_document_projection_writer_gets_revision_by_id`
2. `test_document_projection_writer_allocates_first_revision_number`
3. `test_document_projection_writer_reuses_existing_revision_number`
4. `test_document_projection_writer_allocates_next_revision_number`
5. `test_document_projection_writer_replaces_object_refs_idempotently`
6. `test_document_projection_writer_tombstones_with_revision_history`
7. `test_document_projection_writer_empty_inventory_tombstones_all_active_docs`
8. `test_document_projection_writer_tombstone_respects_newer_active_cursor`
9. `test_document_projection_writer_concurrent_allocations_do_not_share_number`

Green gate:

```bash
uv run pytest tests/unit/test_controlplane_repository_contracts.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_repositories.py -q
```

## Slice B: Repository Implementation

Goal: implement only the write boundary needed by the projector.

Add DTOs to `src/tradingx/controlplane/repositories.py`:

1. `DocumentProjectionObjectRef`
   - `document_object_ref_id`
   - `document_revision_id`
   - `object_uri`
   - `content_type`
   - `sha256_hash`
   - `metadata`
2. `DocumentTombstoneRevision`
   - `document_id`
   - `document_revision_id`
   - `revision_number`
   - `created_at_utc`
   - `source_ref`
   - `metadata`

Extend `DocumentProjectionWriteRepository` with:

1. `get_document_revision(document_revision_id)`
2. `allocate_document_revision_number(document_id, document_revision_id)`
3. `replace_document_object_refs(document_revision_id, refs)`
4. `tombstone_documents_absent_from_inventory_with_revisions(...)`

Add a real Postgres projector unit of work to
`src/tradingx/persistence/repositories/document_projection.py`:

1. `PostgresDocumentsProjectorUnitOfWork`
2. `transaction()` opens one `engine.begin()` block and yields:
   - transaction-bound `PostgresProjectionStateRepository`
   - transaction-bound `PostgresDocumentProjectionRepository`
3. Both repository views must receive the same SQLAlchemy connection.
4. The class should mirror `PostgresRuntimeProjectorUnitOfWork` error
   handling so repository conflicts propagate and storage errors are
   redacted.

Implementation rules for
`PostgresDocumentProjectionRepository`:

1. Keep the existing `upsert_document_revision` semantics intact.
2. Implement allocation with a transaction-scoped per-document lock. The
   preferred SQL shape is:

   ```sql
   SELECT pg_advisory_xact_lock(
       hashtext('documents.document_revision'),
       hashtext(:document_id)
   )
   ```

   The lock may over-serialize on hash collision, but must not
   under-serialize revision allocation for the same document.
3. After the lock, look up `document_revision_id`; if present, return
   its `revision_number`.
4. Otherwise read the latest revision number for the document and return
   `latest + 1`, or `1` for the first revision.
5. `replace_document_object_refs` should delete refs for the revision
   and insert a deterministic sorted set in the same transaction.
6. Object ref IDs should be stable, for example a hash over
   `document_revision_id` and `object_uri`.
7. Tombstone reconciliation should:
   - select active documents for the source family that are absent from
     the active public ID set
   - skip any document whose latest active cursor is after the inventory
     cursor
   - update the document summary to tombstoned
   - append a deterministic tombstone revision per affected document
   - set tombstone revision `created_at_utc` from the inventory event's
     deterministic occurrence timestamp, never from wall-clock time
   - return affected public document IDs in deterministic order
8. The older `tombstone_documents_absent_from_inventory` method may
   remain as a compatibility wrapper, but projector code must use the
   revision-writing method.
9. Projector integration tests must construct the projector with
   `PostgresDocumentsProjectorUnitOfWork`, not standalone repositories.

Green gate:

```bash
uv run ruff check src/tradingx/controlplane/repositories.py src/tradingx/persistence/repositories/document_projection.py tests/unit/test_controlplane_repository_contracts.py tests/integration/test_controlplane_postgres_repositories.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_repository_contracts.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_repositories.py -q
```

## Slice C: Projector Unit Tests

Goal: lock projector behavior with fake repositories before production
projector code.

Write failing tests in `tests/unit/test_controlplane_documents_projector.py`:

1. `test_documents_projector_reads_only_api_document_source_families`
2. `test_documents_projector_does_not_select_config_proposals`
3. `test_documents_projector_uses_per_family_projection_names`
4. `test_documents_projector_materializes_file_events`
5. `test_documents_projector_public_document_ids_are_route_keys`
6. `test_documents_projector_reuses_revision_number_on_existing_revision`
7. `test_documents_projector_allocates_next_revision_number_for_new_content`
8. `test_documents_projector_replaces_object_refs_for_file_revision`
9. `test_documents_projector_inventory_snapshot_tombstones_missing_docs`
10. `test_documents_projector_inventory_tombstone_writes_revision_history`
11. `test_documents_projector_same_revision_payload_mismatch_conflicts`
12. `test_documents_projector_active_revision_replay_after_tombstone_noops_only_when_stable_fields_match`
13. `test_documents_projector_empty_inventory_tombstones_last_document`
14. `test_documents_projector_partial_inventory_absence_does_not_tombstone`
15. `test_documents_projector_advances_collect_watermark_only_on_latest_source_event`
16. `test_documents_projector_rollback_does_not_advance_checkpoint_or_watermark`
17. `test_documents_projector_returns_scoped_route_readiness_without_domain_status`
18. `test_documents_projector_scoped_readiness_blocks_when_api_family_status_missing`
19. `test_documents_projector_per_family_checkpoint_replays_old_rows`
20. `test_documents_projector_resolves_legacy_checkpoint_cursor_from_event_id`

Fake repository rules:

1. The fake unit of work must snapshot in-memory state and restore on
   exception so rollback tests are meaningful.
2. Fake repositories should record call order:
   - revision allocation
   - document revision upsert
   - object ref replacement
   - tombstone reconciliation
   - source-status update
   - checkpoint save
3. The fake projection repo must expose a domain-status save method that
   raises if called.
4. Readiness tests must build static requirements from fake inventory,
   then join status rows.
5. Tombstone revision records must carry event-derived
   `created_at_utc`.

Green gate:

```bash
uv run pytest tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py -q
```

## Slice D: Projector Implementation

Goal: implement `src/tradingx/controlplane/document_projectors.py`.

Implementation structure:

1. Constants:
   - `DOCUMENTS_DOMAIN_NAME = "documents"`
   - `DOCUMENTS_MAPPER_VERSION = "v1"`
   - `DOCUMENTS_SOURCE_REGISTRY_VERSION = "legacy-bridge-documents-projector-v1"`
2. Helpers:
   - `document_projection_name(...)`
   - `_cursor_from_checkpoint(...)`
   - `_payload_mapping(...)`
   - `_payload_str(...)`
   - `_stable_id(...)`
   - `_canonical_hash(...)`
   - `_document_revision_id(...)`
   - `_document_object_ref_id(...)`
3. Main class:
   - `DocumentsProjector.run_once(batch_size=250)`
   - `_run_family_once(...)`
   - `_project_event(...)`
   - `_project_file_observed(...)`
   - `_project_inventory_snapshot(...)`
   - `_advance_projected_source_status(...)`
   - `_scoped_route_readiness(...)`

Ordering rules:

1. Loop families from `document_api_source_families()`.
2. For each family, load its checkpoint and read ordered outbox rows.
3. Process each row in cursor order.
4. For active file events, allocate or reuse revision number, upsert the
   document revision, then replace object refs.
5. For inventory events, call the tombstone revision reconciliation
   method.
6. Advance projected source status only after the corresponding document
   write path succeeds.
7. Save the per-family checkpoint after the family batch succeeds.
8. Return scoped readiness but never persist domain status.

Watermark rules:

1. Individual outbox events carry per-event watermarks.
2. Source status rows carry collect-level watermarks.
3. Set `projected_watermark = status.source_watermark` only after
   consuming the event whose `source_event_id` equals
   `status.metadata["latest_source_event_id"]`.
4. Older rows may update last-projected metadata but must not claim the
   collect-level projected watermark.

Green gate:

```bash
uv run ruff check src/tradingx/controlplane/document_projectors.py src/tradingx/controlplane/repositories.py src/tradingx/persistence/repositories/document_projection.py tests/unit/test_controlplane_documents_projector.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py -q
```

## Slice E: Postgres Projector Proof

Goal: prove bridge to outbox to projector to repository under real
Postgres.

Create `tests/integration/test_controlplane_postgres_documents_projector.py`.

Required tests:

1. `test_documents_projector_materializes_state_and_index_from_bridge_outbox`
2. `test_documents_projector_materializes_handover_sessions_from_bridge_outbox`
3. `test_documents_projector_idempotent_rerun_does_not_duplicate_revisions_or_refs`
4. `test_documents_projector_edit_appends_later_revision`
5. `test_documents_projector_old_revision_replay_does_not_roll_summary_back`
6. `test_documents_projector_inventory_deletion_tombstones_and_writes_revision`
7. `test_documents_projector_empty_inventory_tombstones_last_document`
8. `test_documents_projector_partial_read_without_inventory_does_not_tombstone`
9. `test_documents_projector_conflict_rolls_back_all_projection_state`
10. `test_documents_projector_same_revision_payload_mismatch_conflicts`
11. `test_documents_projector_active_revision_replay_after_tombstone_noops_when_stable_fields_match`
12. `test_documents_projector_active_revision_replay_after_tombstone_conflicts_when_stable_fields_drift`
13. `test_documents_projector_real_uow_rolls_back_documents_refs_source_status_and_checkpoint`
14. `test_documents_projector_family_checkpoints_are_independent`
15. `test_documents_projector_legacy_checkpoint_cursor_recovers_from_event_id`
16. `test_documents_projector_ignores_config_proposals`
17. `test_documents_projector_does_not_write_domain_projection_status`
18. `test_documents_projector_missing_api_family_status_blocks_scoped_readiness`
19. `test_documents_projector_collect_watermark_advances_only_after_latest_event`
20. `test_documents_projector_tombstone_revision_uses_inventory_event_time`

Concurrency proof:

1. Keep allocation concurrency tests in repository integration tests.
2. The projector integration suite should not rely on timing-sensitive
   thread scheduling beyond the repository allocation proof.
3. The real rollback proof must use `PostgresDocumentsProjectorUnitOfWork`
   so document writes, object refs, source-status updates, and checkpoint
   writes share one database transaction.

Green gate:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_documents_projector.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_repositories.py -q
```

## Slice F: Safety Closeout

Goal: prove the slice did not leak into startup or route behavior.

Run:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py tests/unit/test_web_app.py tests/integration/test_controlplane_postgres_documents_projector.py tests/integration/test_controlplane_postgres_repositories.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_documents_projector.py tests/unit/test_controlplane_repository_contracts.py tests/unit/test_web_app.py -q
python3 scripts/check_index.py
git diff --check
```

Guarded closeout:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_documents_projector.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_repositories.py tests/integration/test_controlplane_postgres_legacy_bridge.py -q
```

Run the unfinished-marker scan over touched files before review.

## Commit Plan

Prefer one implementation commit if the final diff stays easy to review.
If the diff becomes too large, split in this order:

1. `Extend document projection write contracts`
2. `Add documents projector`
3. `Prove documents projector with Postgres`

Do not merge any commit that leaves green unit tests but lacks the
guarded Postgres proof unless the DSN is unavailable and the user
explicitly accepts that risk.

## Review Checklist

Before implementation begins, review this execution plan for:

1. Whether advisory locking is the right concurrency primitive for
   revision allocation.
2. Whether object-ref replacement needs a schema constraint or whether
   delete-and-insert under transaction is enough for this slice.
3. Whether tombstone revisions need their own DTO or can reuse
   `DocumentProjectionRevision`.
4. Whether static readiness requirements can be built from the existing
   bridge inventory without adding another registry.
5. Whether collect-level watermark advancement is testable without
   coupling too tightly to bridge internals.
6. Whether old checkpoint cursor recovery belongs in a shared helper
   before duplicating runtime projector code.
7. Whether the fake unit of work proves rollback strongly enough before
   Postgres tests.
8. Whether any route construction path can import or instantiate
   Postgres dependencies before the later route pivot.
9. Whether the execution tests preserve `PLAN-0022` replay guarantees
   for same-revision conflicts and active replay after tombstone.
10. Whether tombstone revisions carry deterministic event time all the
    way to `documents.document_revision.created_at_utc`.
11. Whether real Postgres projector tests use the concrete UoW rather
    than separate repositories with independent transactions.
