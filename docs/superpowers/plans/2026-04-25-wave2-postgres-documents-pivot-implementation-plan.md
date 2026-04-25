---
id: PLAN-0021
title: Headless control plane Wave 2 Postgres documents pivot implementation plan
version: 1.0.1
status: draft
created: 2026-04-25
last_amended: 2026-04-25
supersedes: PLAN-0021@1.0.0
superseded_by: null
author_session: codex-gpt-5-2026-04-25
---

# Headless Control Plane Wave 2 Postgres Documents Pivot Implementation Plan

## Purpose

This plan turns approved `PLAN-0020` into an implementation-ready work
package. It does not implement code. It fixes the execution order, test
order, file ownership, and verification gates before the documents pivot
slice starts.

The target path remains narrow:

```text
revision-safe document bridge events
-> documents projector
-> Postgres document read/write repositories
-> scoped document API readiness
-> /api/v1/documents route pivot
```

The first implementation move must be a failing test for bridge
enrichment. The documents projector and route router must not be built
until the bridge can emit revision-safe, file-level, deletion-aware
document events for the current documents API scope.

## Authority

- `PLAN-0020`: `docs/superpowers/plans/2026-04-25-wave2-postgres-documents-pivot-plan.md`
- `PLAN-0019`: `docs/superpowers/plans/2026-04-25-wave2-postgres-runtime-projector-plan.md`
- `PLAN-0018`: `docs/superpowers/plans/2026-04-24-wave2-postgres-legacy-bridge-tailer-plan.md`
- `PLAN-0013`: `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-execution-plan.md`
- `DESIGN-0022`: `docs/architecture/TradingX_Headless_Control_Plane_Architecture.md`

## Current Code Facts

The implementation must start from these observed facts:

1. `FileTreeSourceAdapter` currently emits each file with
   `source_event_id = relative_path`.
2. The outbox dedupe key includes `source_event_id`, so editing the
   same file under the current adapter can create an outbox conflict
   instead of a new revision event.
3. `LocalWebReadModel.list_documents` currently returns only:
   - handover session markdown files from `docs/handover/SESSIONS/*.md`
   - `docs/handover/STATE.md`
   - `docs/INDEX.md`
4. The public document ID contract is the existing
   `DocumentRecord.doc_id`: `STATE`, `INDEX`, and handover session
   file stems. `/api/v1/documents/STATE` must remain valid after the
   pivot.
5. Config proposals are exposed through `list_config_proposals` and
   `/api/config/proposals`, not through `/api/v1/documents`.
6. `system.domain_projection_status` is keyed only by `domain_name`.
   This slice cannot write a ready `documents` row while
   `config_proposals` remains in the broader `documents` source
   inventory but outside the route scope.
7. Runtime projector tests already provide patterns for per-family
   checkpoints, ordered outbox cursors, rollback, and idempotency.

## Non-Negotiable Locks

1. No production code before the failing test that proves edited
   document files append new outbox events.
2. No documents projector before bridge enrichment is green.
3. No route pivot before Postgres document reads, scoped route
   readiness, fallback, and required-Postgres failure behavior are
   tested.
4. The scoped route readiness source families are only
   `handover_sessions` and `state_and_index_docs`.
5. `config_proposals` must not appear in `/api/v1/documents`, must not
   block scoped document API readiness, and must not be silently removed
   from the broader source inventory in this slice.
6. The scoped route readiness helper must not persist
   `system.domain_projection_status`.
7. The projector must not reread local files; it consumes only outbox
   envelopes and source-status/checkpoint data.
8. Legacy local web startup remains Postgres-free.
9. The route pivot must not affect `/api/documents`, explorer routes,
   platform routes, SSE, events, runtime, control posture, incidents,
   validation, portfolio, commands, investigations, or replays.

## Slice 0: Baseline

Goal: verify the branch starts from a known green state.

Run before edits:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence src/tradingx/web tests/unit/test_controlplane_legacy_bridge.py tests/unit/test_controlplane_runtime_projector.py tests/unit/test_web_app.py
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

If a guarded DSN is unavailable, record that the Postgres gate was not
run. Do not treat an unavailable DSN as passing evidence.

## Slice 1: Bridge Enrichment

Goal: make document bridge events revision-safe, file-level, and
deletion-aware without changing non-document source families.

Owned paths:

- `src/tradingx/controlplane/legacy_bridge.py`
- `tests/unit/test_controlplane_legacy_bridge.py`
- `tests/integration/test_controlplane_postgres_legacy_bridge.py`

First failing unit tests:

1. `test_document_file_tree_adapter_uses_revision_safe_event_ids`
   - Arrange a temp repo with `docs/handover/STATE.md`.
   - Collect once, edit file text, collect again.
   - Assert both events share the same stable document ID but have
     different `source_event_id` values containing a revision
     discriminator such as content hash or source watermark.
2. `test_document_file_tree_adapter_emits_file_level_document_payload`
   - Assert document events carry `document_id`, `document_kind`,
     `title`, `preview`, `relative_path`, `logical_retrieval_ref`,
     `content_hash`, `document_state = "active"`, and no absolute temp
     root.
3. `test_document_file_tree_adapter_preserves_public_document_ids`
   - Assert `STATE.md` maps to public `document_id = "STATE"`,
     `INDEX.md` maps to `document_id = "INDEX"`, and a handover file
     maps to its bare session stem.
   - Assert prefixed implementation keys, if needed, live only in
     metadata such as `internal_document_key`.
4. `test_document_file_tree_adapter_unchanged_rerun_reuses_event_id`
   - Collect the same unchanged document twice with different
     `observed_at_utc` values.
   - Assert the active file event has the same `source_event_id` and
     source watermark both times.
5. `test_document_file_tree_adapter_emits_inventory_snapshot`
   - Assert each supported document source family emits an inventory
     snapshot event whose payload contains the complete active document
     ID set and source family.
6. `test_document_file_tree_adapter_inventory_changes_after_delete`
   - Delete a previously observed handover session file.
   - Assert the next collect emits a new inventory snapshot with the
     deleted document absent from the active set.
7. `test_document_file_tree_adapter_emits_empty_inventory_snapshot`
   - Arrange a valid source family root with no matching files.
   - Assert collect still emits an inventory snapshot with an empty
     active set and marks the source as initially importable for scoped
     readiness.
8. `test_document_file_tree_adapter_last_file_delete_emits_empty_inventory`
   - Start with one handover file, delete it, collect again.
   - Assert the later inventory snapshot has an empty active set.
9. `test_document_bridge_scope_excludes_config_proposals_from_api_docs`
   - Assert the helper that returns scoped document API source families
     contains `handover_sessions` and `state_and_index_docs`, but not
     `config_proposals`.

First failing Postgres tests:

1. `test_document_bridge_edit_appends_new_outbox_event_not_conflict`
   - Run the real bridge for `state_and_index_docs`.
   - Edit `STATE.md`.
   - Run the bridge again.
   - Assert two outbox rows exist for the same document and no conflict
     is raised.
2. `test_document_bridge_unchanged_rerun_reuses_existing_outbox_row`
   - Run the real bridge for `state_and_index_docs` twice without
     changing files.
   - Assert the second run reuses the same outbox row, reports it as
     existing, and does not create a duplicate revision event.
3. `test_document_bridge_delete_appends_inventory_snapshot`
   - Run the bridge for handover sessions.
   - Delete one session file.
   - Run the bridge again.
   - Assert a later inventory snapshot outbox row exists and source
     status watermark advances.
4. `test_document_bridge_empty_valid_family_writes_inventory_snapshot`
   - Run the real bridge for a valid documents source family with no
     matching files.
   - Assert an empty inventory snapshot outbox row exists and source
     status can become ready for scoped route readiness.

Implementation notes:

1. Add a document-specific bridge path rather than changing all
   `FileTreeSourceAdapter` behavior. A small `DocumentFileTreeSourceAdapter`
   or explicit `document_mode` option is acceptable if non-document
   tests prove existing file-tree semantics remain stable.
2. Emit active file events with a stable public document ID and a
   revision-safe event key. `document_id` must exactly match the
   existing public `DocumentRecord.doc_id` contract: `STATE`, `INDEX`,
   or the handover session stem. If an internal namespace is needed for
   projection safety, store it separately in metadata such as
   `internal_document_key`; do not use it as the public document ID or
   route key. A valid shape is:

   ```text
   source_event_id = "file:<relative_path>:<content_hash>"
   document_id = "<existing public doc_id>"
   internal_document_key = "document:<source_family>:<relative_path>"
   ```

3. Emit one inventory snapshot event per source family collect, with an
   event key derived from the active set digest:

   ```text
   source_event_id = "inventory:<active-set-hash>"
   ```

4. The inventory snapshot payload must include all active document IDs
   and relative paths for that family. The projector will use this
   snapshot to tombstone previously projected documents that are absent.
5. The adapter must emit an inventory snapshot even when no files match
   the family patterns. A valid empty inventory is current source
   evidence, not a missing import.
6. Keep payloads redacted. Payloads may include relative repo paths and
   logical retrieval refs, but not absolute user-machine paths.
7. Preserve `--since` behavior: timestamp-less document files that
   represent current snapshots must not be dropped solely because they
   lack durable timestamps.
8. Preserve source-status metadata and `latest_source_event_id`
   determinism.

Slice 1 green gates:

```bash
uv run pytest tests/unit/test_controlplane_legacy_bridge.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_legacy_bridge.py -q
```

## Slice 2: Document Repository Contracts

Goal: add narrow read/write boundaries for document materialization and
route reads.

Owned paths:

- `src/tradingx/controlplane/repositories.py`
- `src/tradingx/persistence/repositories/postgres.py`
- `src/tradingx/persistence/repositories/document_projection.py`
- `tests/unit/test_controlplane_documents_projector.py`
- `tests/integration/test_controlplane_postgres_repositories.py`

First failing tests:

1. `test_document_read_repository_lists_active_documents_only`
2. `test_document_read_repository_gets_document_by_id`
3. `test_document_read_repository_returns_none_for_tombstoned_document`
4. `test_document_read_repository_uses_public_document_id_contract`
   - Insert `STATE`, `INDEX`, and a session-stem document.
   - Assert reads use those bare IDs and not internal prefixed IDs.
5. `test_document_write_repository_inserts_document_and_first_revision`
6. `test_document_write_repository_adds_later_revision_for_same_document`
7. `test_document_write_repository_conflicts_only_on_same_revision_key`

Implementation notes:

1. Add DTOs only if the existing `DocumentRecord` is insufficient for
   repository boundaries. Do not leak table-shaped payloads into web
   route responses.
2. Keep read and projection write boundaries separate. The web router
   may use the read repository only.
3. Store the public document ID in `documents.document.document_id`.
   Internal namespaced keys may be kept in `metadata_json` for
   projector bookkeeping, but route lookups must use the public ID.
4. If JSON metadata cannot support efficient active/tombstone filtering
   without ambiguity, add a reviewed migration before the route pivot.
   The preferred code path may use `metadata_json.document_state` only
   if tests prove tombstoned rows are excluded consistently.
5. Natural-key conflicts are revision-key scoped. A new content hash for
   the same document ID creates a later revision.

Slice 2 green gates:

```bash
uv run pytest tests/unit/test_controlplane_documents_projector.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_repositories.py tests/integration/test_controlplane_postgres_store.py -q
```

## Slice 3: Documents Projector

Goal: consume enriched document outbox events and materialize Postgres
document rows transactionally.

Owned paths:

- `src/tradingx/controlplane/document_projectors.py`
- `src/tradingx/controlplane/repositories.py`
- `src/tradingx/persistence/repositories/projection_state.py`
- `src/tradingx/persistence/repositories/document_projection.py`
- `tests/unit/test_controlplane_documents_projector.py`
- `tests/integration/test_controlplane_postgres_documents_projector.py`

First failing tests:

1. `test_documents_projector_reads_only_api_document_source_families`
2. `test_documents_projector_does_not_select_config_proposals`
3. `test_documents_projector_materializes_file_events`
4. `test_documents_projector_inventory_snapshot_tombstones_missing_docs`
5. `test_documents_projector_idempotent_rerun_does_not_duplicate_revisions`
6. `test_documents_projector_later_revision_is_not_conflict`
7. `test_documents_projector_same_revision_payload_mismatch_conflicts`
8. `test_documents_projector_public_document_ids_are_route_keys`
9. `test_documents_projector_empty_inventory_tombstones_last_document`
10. `test_documents_projector_rollback_does_not_advance_checkpoint_or_watermark`
11. `test_documents_projector_returns_scoped_route_readiness_without_domain_status`
12. `test_documents_projector_per_family_checkpoint_replays_old_rows`

Implementation notes:

1. Keep projector logic in a document-specific module unless extending
   `projectors.py` remains clearly separated and small.
2. Use projection names:

   ```text
   documents_projection:documents:handover_sessions:v1
   documents_projection:documents:state_and_index_docs:v1
   ```

3. Read outbox rows ordered by `created_at_utc ASC, outbox_event_id ASC`.
4. Process active file events into document rows and revisions.
5. Process inventory snapshot events after active file events for the
   same batch so tombstones apply to the latest active set.
6. Empty inventory snapshots are valid events. They can tombstone all
   previously active documents for the family and can contribute to
   scoped readiness if the source itself is otherwise healthy.
7. Update projected source watermarks only after document writes and
   tombstones are durable.
8. Save checkpoints only after all writes and source-status updates
   succeed.
9. Do not call `save_domain_projection_status_from_readiness` for the
   scoped documents route pivot.

Slice 3 green gates:

```bash
uv run pytest tests/unit/test_controlplane_documents_projector.py -q
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_documents_projector.py tests/integration/test_controlplane_postgres_projection_state.py -q
```

## Slice 4: Scoped Documents Route Router

Goal: pivot only `/api/v1/documents` and
`/api/v1/documents/{document_id}` behind scoped readiness and explicit
fallback behavior.

Owned paths:

- `src/tradingx/web/app.py`
- optional `src/tradingx/web/document_router.py`
- `src/tradingx/web/runtime.py`
- `tests/unit/test_web_app.py`
- `tests/contract/test_local_web_app_api_contract.py` if present for
  these routes

First failing tests:

1. `test_legacy_local_web_paths_do_not_construct_documents_postgres`
2. `test_v1_documents_uses_legacy_by_default`
3. `test_v1_documents_uses_postgres_when_scoped_readiness_ready`
4. `test_v1_document_detail_uses_public_id_when_postgres_ready`
   - Assert `/api/v1/documents/STATE` succeeds against the Postgres
     document repository.
5. `test_v1_documents_falls_back_to_legacy_when_not_required`
6. `test_v1_documents_fails_closed_when_postgres_required_and_blocked`
7. `test_v1_documents_hybrid_postgres_required_fails_closed_when_blocked`
8. `test_v1_documents_404_shape_is_preserved`
9. `test_non_document_v1_routes_remain_legacy`

Implementation notes:

1. Construct Postgres document dependencies only when effective
   document store is Postgres.
2. Compute scoped route readiness directly from source-status rows and
   checkpoints for `handover_sessions` and `state_and_index_docs`.
3. Do not use `system.domain_projection_status` as the route authority.
4. Preserve current list/detail response shapes, including `document_id`,
   `title`, `kind`, `preview`, and `retrieval_ref`.
5. If fallback metadata is added, keep it in the existing envelope
   metadata and avoid changing item payload shape.

Slice 4 green gates:

```bash
uv run pytest tests/unit/test_web_app.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
```

If a contract file is not present for these routes, extend the nearest
existing web/API unit batch instead of creating a parallel contract
style.

## Slice 5: End-To-End Postgres Proof

Goal: prove the complete bridge to projector to route path under a real
Postgres test database.

Owned paths:

- `tests/integration/test_controlplane_postgres_documents_projector.py`
- `tests/integration/test_controlplane_postgres_repositories.py`
- `tests/integration/test_controlplane_postgres_documents_routes.py`
- `tests/unit/test_web_app.py`

Required proof cases:

1. Bridge-seeded `STATE.md` and `INDEX.md` events materialize Postgres
   document rows.
2. Bridge-seeded handover session events materialize Postgres document
   rows.
3. Editing a document creates a later revision and does not conflict.
4. Reprocessing the same revision is idempotent.
5. Deleting a handover session tombstones the Postgres document and
   hides it from list/detail reads.
6. Config proposal source events do not appear in `/api/v1/documents`
   and do not block scoped readiness.
7. Projector conflict rolls back document rows, source watermarks, and
   checkpoint metadata.
8. Scoped route readiness blocks on stale or unprojected API source
   families.
9. Scoped route readiness becomes ready only when both API source
   families are fresh and projected.
10. Required Postgres mode returns the stable 503 diagnostic when
    scoped documents readiness is blocked.
11. No ready `system.domain_projection_status` row is written for
    `documents` by this scoped projector.
12. A DSN-backed `TestClient` route proof serves
    `/api/v1/documents` from the real Postgres document repository after
    bridge and projector catch-up.
13. The same DSN-backed route proof serves
    `/api/v1/documents/STATE` by public document ID and preserves the
    current detail response shape.
14. A DSN-backed `TestClient` route proof returns the stable 503
    diagnostic when effective documents store is Postgres, Postgres is
    required, and scoped readiness is blocked.

Green gate:

```bash
TRADINGX_TEST_POSTGRES_DSN=postgresql://tradingx:tradingx@127.0.0.1:5433/tradingx_test \
  uv run pytest tests/integration/test_controlplane_postgres_store.py tests/integration/test_controlplane_postgres_projection_state.py tests/integration/test_controlplane_postgres_legacy_bridge.py tests/integration/test_controlplane_postgres_runtime_projector.py tests/integration/test_controlplane_postgres_repositories.py tests/integration/test_controlplane_postgres_documents_projector.py tests/integration/test_controlplane_postgres_documents_routes.py -q
```

## Slice 6: Safety Closeout

Goal: finish the implementation with broad focused gates and no scope
leakage.

Run:

```bash
uv run ruff check src/tradingx/controlplane src/tradingx/persistence src/tradingx/web tests/unit/test_controlplane_legacy_bridge.py tests/unit/test_controlplane_runtime_projector.py tests/unit/test_controlplane_documents_projector.py tests/unit/test_web_app.py tests/integration/test_controlplane_postgres_documents_projector.py tests/integration/test_controlplane_postgres_documents_routes.py
uv run mypy src/tradingx
uv run pytest tests/unit/test_controlplane_legacy_bridge.py tests/unit/test_controlplane_runtime_projector.py tests/unit/test_controlplane_documents_projector.py tests/unit/test_web_app.py -q
python3 scripts/check_index.py
git diff --check
```

Run the repository's standard placeholder scan over touched production
and test files. The scan must cover unfinished-marker phrases,
stub-only code, and deferred-implementation markers before merge.

Expected remaining untracked noise: the pre-existing local `output/`
directory is not part of this work and must stay untouched unless the
user explicitly asks otherwise.

## Commit Strategy

Prefer one implementation commit after the final green run unless the
work becomes too large to review. If split commits are needed, use this
order:

1. `Enrich document bridge events`
2. `Project documents into Postgres`
3. `Pivot documents route behind readiness`

Do not merge any commit that leaves the route pivot enabled without
green scoped readiness and fallback tests.

## Adversarial Review Checklist

Before implementation starts, review this plan for:

1. Whether Slice 1 can really emit deletion evidence without projector
   filesystem reads.
2. Whether inventory snapshot events are enough to tombstone deleted
   documents.
3. Whether edited files can still collide under an old dedupe key.
4. Whether config proposals can accidentally block route readiness.
5. Whether scoped route readiness can be mistaken for domain-wide
   documents readiness.
6. Whether the route can silently fall back when Postgres is required.
7. Whether document payloads leak absolute local paths or secrets.
8. Whether adding document bridge behavior changes non-document
   `FileTreeSourceAdapter` behavior.
9. Whether same-revision conflicts and later revisions are cleanly
   separated.
10. Whether unchanged reruns are idempotent and reuse existing outbox
    rows instead of creating duplicate revisions.
11. Whether empty inventories and last-file deletion still emit
    tombstone-capable evidence.
12. Whether deleted documents remain visible through list or detail
    reads.
13. Whether the public document ID contract remains `STATE`, `INDEX`,
    and session stems after the pivot.
14. Whether a real DSN-backed route proof covers list, detail, and
    required-Postgres 503 behavior.
15. Whether default local web startup stays Postgres-free.
16. Whether any non-document route, stream topic, or governed write
    sneaks into scope.

## Implementation Ready Criteria

This implementation plan is ready only when adversarial review confirms:

1. the first red tests target the bridge event identity problem,
2. bridge enrichment is a prerequisite and not optional,
3. deletion handling has an outbox-driven path,
4. unchanged reruns and empty inventories are explicitly tested,
5. scoped readiness avoids `system.domain_projection_status`,
6. public document IDs preserve the existing API contract, and
7. validation gates cover unit, web, and real Postgres route behavior.
