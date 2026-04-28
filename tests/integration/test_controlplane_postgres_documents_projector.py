from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tradingx.controlplane import document_projectors, repositories
from tradingx.controlplane.legacy_bridge import build_default_bridge
from tradingx.persistence import postgres
from tradingx.persistence.repositories.document_projection import (
    PostgresDocumentsProjectorUnitOfWork,
)
from tradingx.persistence.repositories.postgres import PostgresControlPlaneRepository
from tradingx.persistence.repositories.projection_state import (
    PostgresProjectionStateRepository,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip(),
    reason="TRADINGX_TEST_POSTGRES_DSN is not configured",
)

FIXED_NOW = datetime(2026, 4, 24, 13, 0, tzinfo=UTC)
PROJECTOR_NOW = datetime(2026, 4, 24, 13, 1, tzinfo=UTC)
EVENT_TIME = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)


def _postgres_dsn() -> str:
    dsn = os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("TRADINGX_TEST_POSTGRES_DSN is not configured")
    return dsn


@pytest.fixture()
def store() -> Iterator[ProjectorStore]:
    dsn = _postgres_dsn()
    engine = postgres.build_postgres_engine(postgres.PostgresSettings(dsn=dsn))
    postgres.reset_postgres_test_database(engine, dsn=dsn)
    postgres.run_postgres_migrations(dsn, revision="head")
    try:
        yield ProjectorStore(
            engine=engine,
            dsn=dsn,
            id_provider=_sequential_id_provider(),
        )
    finally:
        engine.dispose()


@dataclass(frozen=True)
class ProjectorStore:
    engine: Engine
    dsn: str
    id_provider: Callable[[], str]

    def projection_repo(self) -> PostgresProjectionStateRepository:
        return PostgresProjectionStateRepository(
            engine=self.engine,
            dsn=self.dsn,
            id_provider=self.id_provider,
            clock=lambda: PROJECTOR_NOW,
        )

    def projector(self) -> document_projectors.DocumentsProjector:
        return document_projectors.DocumentsProjector(
            unit_of_work=PostgresDocumentsProjectorUnitOfWork(
                engine=self.engine,
                dsn=self.dsn,
                id_provider=self.id_provider,
                clock=lambda: PROJECTOR_NOW,
            ),
            clock=lambda: PROJECTOR_NOW,
        )

    def read_repo(self) -> PostgresControlPlaneRepository:
        return PostgresControlPlaneRepository(engine=self.engine, dsn=self.dsn)


def test_documents_projector_materializes_state_and_index_from_bridge_outbox(
    store: ProjectorStore,
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n\nReady.\n")
    _write_text(tmp_path / "docs" / "INDEX.md", "# Index\n\nArtifacts.\n")
    _run_bridge(store, tmp_path, source_families=("state_and_index_docs",))

    result = store.projector().run_once(batch_size=20)

    documents = store.read_repo().list_documents(
        page=repositories.PageRequest(page_size=10)
    )
    refs = _rows(
        store.engine,
        """
        SELECT object_uri
        FROM documents.document_object_ref
        ORDER BY object_uri ASC
        """,
    )
    assert result.projected_event_count == 3
    assert {document.document_id for document in documents.items} == {
        "INDEX",
        "STATE",
    }
    latest_revisions = {
        document.document_id: document.latest_revision.revision_number
        for document in documents.items
    }
    assert latest_revisions == {
        "INDEX": 1,
        "STATE": 1,
    }
    assert {row["object_uri"] for row in refs} == {
        "docs/INDEX.md",
        "docs/handover/STATE.md",
    }


def test_documents_projector_materializes_handover_sessions_from_bridge_outbox(
    store: ProjectorStore,
    tmp_path: Path,
) -> None:
    _write_text(
        tmp_path / "docs" / "handover" / "SESSIONS" / "2026-04-25-wave2.md",
        "# Handover\n\nProjector notes.\n",
    )
    _run_bridge(store, tmp_path, source_families=("handover_sessions",))

    store.projector().run_once(batch_size=20)

    document = store.read_repo().get_document("2026-04-25-wave2")
    assert document is not None
    assert document.document_kind == "handover"
    assert document.logical_retrieval_ref == (
        "docs/handover/SESSIONS/2026-04-25-wave2.md"
    )


def test_documents_projector_idempotent_rerun_does_not_duplicate_revisions_or_refs(
    store: ProjectorStore,
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n\nStable.\n")
    _run_bridge(store, tmp_path, source_families=("state_and_index_docs",))
    store.projector().run_once(batch_size=20)
    first_counts = _document_counts(store.engine)

    _run_bridge(store, tmp_path, source_families=("state_and_index_docs",))
    store.projector().run_once(batch_size=20)

    assert _document_counts(store.engine) == first_counts


def test_documents_projector_edit_appends_later_revision(
    store: ProjectorStore,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "docs" / "handover" / "STATE.md"
    _write_text(state_path, "# State\n\nFirst.\n")
    _run_bridge(store, tmp_path, source_families=("state_and_index_docs",))
    store.projector().run_once(batch_size=20)

    _write_text(state_path, "# State\n\nSecond.\n")
    _run_bridge(store, tmp_path, source_families=("state_and_index_docs",))
    store.projector().run_once(batch_size=20)

    document = store.read_repo().get_document("STATE")
    revisions = _revision_rows(store.engine, "STATE")
    assert document is not None
    assert document.preview == "Second."
    assert document.latest_revision is not None
    assert document.latest_revision.revision_number == 2
    assert [row["revision_number"] for row in revisions] == [1, 2]


def test_documents_projector_old_revision_replay_does_not_roll_summary_back(
    store: ProjectorStore,
) -> None:
    first_id = _append_file_event(
        store,
        document_id="STATE",
        content_text="# State\n\nFirst.\n",
        content_hash="hash-state-1",
    )
    second_id = _append_file_event(
        store,
        document_id="STATE",
        content_text="# State\n\nSecond.\n",
        content_hash="hash-state-2",
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("STATE", "hash-state-2"),
        source_watermark="collect-state-v2",
    )
    store.projector().run_once(batch_size=20)
    _delete_checkpoint(store, "state_and_index_docs")

    result = store.projector().run_once(batch_size=1)

    document = store.read_repo().get_document("STATE")
    assert first_id != second_id
    assert result.consumed_event_count == 1
    assert document is not None
    assert document.preview == "Second."
    assert document.latest_revision is not None
    assert document.latest_revision.revision_number == 2


def test_documents_projector_inventory_deletion_tombstones_and_writes_revision(
    store: ProjectorStore,
) -> None:
    _append_file_event(store, document_id="STATE", content_hash="hash-active")
    _append_inventory_event(
        store,
        source_family="state_and_index_docs",
        active_document_ids=(),
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id="inventory:state_and_index_docs:empty",
        source_watermark="collect-empty",
    )

    store.projector().run_once(batch_size=20)

    assert store.read_repo().get_document("STATE") is None
    revisions = _revision_rows(store.engine, "STATE")
    assert [row["revision_number"] for row in revisions] == [1, 2]
    assert revisions[1]["metadata_json"]["document_state"] == "tombstoned"


def test_documents_projector_empty_inventory_tombstones_last_document(
    store: ProjectorStore,
) -> None:
    _append_file_event(
        store,
        document_id="only-session",
        source_family="handover_sessions",
        content_hash="hash-only-session",
    )
    _append_inventory_event(
        store,
        source_family="handover_sessions",
        active_document_ids=(),
    )
    _upsert_status(
        store,
        source_family="handover_sessions",
        latest_source_event_id="inventory:handover_sessions:empty",
        source_watermark="collect-empty-handover",
    )

    store.projector().run_once(batch_size=20)

    assert store.read_repo().get_document("only-session") is None
    assert store.read_repo().list_documents().items == ()
    revisions = _revision_rows(store.engine, "only-session")
    assert [row["revision_number"] for row in revisions] == [1, 2]


def test_documents_projector_partial_read_without_inventory_does_not_tombstone(
    store: ProjectorStore,
    tmp_path: Path,
) -> None:
    _write_text(tmp_path / "docs" / "handover" / "STATE.md", "# State\n\nReady.\n")
    _write_text(tmp_path / "docs" / "INDEX.md", "# Index\n\nReady.\n")
    _run_bridge(store, tmp_path, source_families=("state_and_index_docs",))
    store.projector().run_once(batch_size=20)
    (tmp_path / "docs" / "INDEX.md").write_bytes(b"\xff")

    _run_bridge(store, tmp_path, source_families=("state_and_index_docs",))
    store.projector().run_once(batch_size=20)

    assert store.read_repo().get_document("INDEX") is not None
    status = store.projection_repo().get_projection_source_status(
        domain_name="documents",
        source_family="state_and_index_docs",
        source_identity="repo:docs/state_index",
    )
    assert status is not None
    assert status.ready_for_postgres is False
    assert status.metadata["source_errors"] == ["unreadable_file:docs/INDEX.md"]


def test_documents_projector_conflict_rolls_back_all_projection_state(
    store: ProjectorStore,
) -> None:
    initial_id = _append_file_event(
        store,
        document_id="STATE",
        content_hash="hash-state",
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("STATE", "hash-state"),
        source_watermark="collect-state",
    )
    store.projector().run_once(batch_size=20)
    conflict_id = _append_file_event(
        store,
        document_id="STATE",
        content_text="# State\n\nMutated.\n",
        content_hash="different-hash",
        source_event_id=_source_event_id("STATE", "hash-state"),
        dedupe_suffix="same-revision-conflict",
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("STATE", "hash-state"),
        source_watermark="collect-conflict",
    )

    with pytest.raises(repositories.RepositoryConflictError):
        store.projector().run_once(batch_size=20)

    checkpoint = _checkpoint(store, "state_and_index_docs")
    status = store.projection_repo().get_projection_source_status(
        domain_name="documents",
        source_family="state_and_index_docs",
        source_identity="repo:docs/state_index",
    )
    assert conflict_id != initial_id
    assert checkpoint is not None
    assert checkpoint.last_outbox_event_id == initial_id
    assert status is not None
    assert status.projected_watermark is None


def test_documents_projector_same_revision_payload_mismatch_conflicts(
    store: ProjectorStore,
) -> None:
    _append_file_event(store, document_id="STATE", content_hash="hash-state")
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("STATE", "hash-state"),
        source_watermark="collect-state",
    )
    store.projector().run_once(batch_size=20)
    _append_file_event(
        store,
        document_id="STATE",
        title="Mutated project state",
        content_hash="different-hash",
        source_event_id=_source_event_id("STATE", "hash-state"),
        dedupe_suffix="mutated-same-revision",
    )

    with pytest.raises(repositories.RepositoryConflictError):
        store.projector().run_once(batch_size=20)

    revisions = _revision_rows(store.engine, "STATE")
    assert len(revisions) == 1
    assert revisions[0]["metadata_json"]["content_hash"] == "hash-state"


def test_documents_projector_active_revision_replay_after_tombstone_noops_when_stable_fields_match(  # noqa: E501
    store: ProjectorStore,
) -> None:
    _append_file_event(store, document_id="STATE", content_hash="hash-state")
    _append_inventory_event(
        store,
        source_family="state_and_index_docs",
        active_document_ids=(),
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id="inventory:state_and_index_docs:empty",
        source_watermark="collect-empty",
    )
    store.projector().run_once(batch_size=20)
    _delete_checkpoint(store, "state_and_index_docs")

    store.projector().run_once(batch_size=20)

    assert store.read_repo().get_document("STATE") is None
    revision_numbers = [
        row["revision_number"] for row in _revision_rows(store.engine, "STATE")
    ]
    assert revision_numbers == [1, 2]


def test_documents_projector_active_revision_replay_after_tombstone_conflicts_when_stable_fields_drift(  # noqa: E501
    store: ProjectorStore,
) -> None:
    _append_file_event(store, document_id="STATE", content_hash="hash-state")
    _append_inventory_event(
        store,
        source_family="state_and_index_docs",
        active_document_ids=(),
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id="inventory:state_and_index_docs:empty",
        source_watermark="collect-empty",
    )
    store.projector().run_once(batch_size=20)
    _delete_checkpoint(store, "state_and_index_docs")
    _update_document_title(store.engine, "STATE", "Drifted title")

    with pytest.raises(repositories.RepositoryConflictError):
        store.projector().run_once(batch_size=20)


def test_documents_projector_real_uow_rolls_back_documents_refs_source_status_and_checkpoint(  # noqa: E501
    store: ProjectorStore,
) -> None:
    initial_id = _append_file_event(
        store,
        document_id="STATE",
        content_hash="hash-state",
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("STATE", "hash-state"),
        source_watermark="collect-state",
    )
    store.projector().run_once(batch_size=20)
    _append_file_event(store, document_id="INDEX", content_hash="hash-index")
    _append_file_event(
        store,
        document_id="STATE",
        content_text="# State\n\nConflict.\n",
        content_hash="different-hash",
        source_event_id=_source_event_id("STATE", "hash-state"),
        dedupe_suffix="rollback-conflict",
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("STATE", "hash-state"),
        source_watermark="collect-rollback",
    )

    with pytest.raises(repositories.RepositoryConflictError):
        store.projector().run_once(batch_size=20)

    status = store.projection_repo().get_projection_source_status(
        domain_name="documents",
        source_family="state_and_index_docs",
        source_identity="repo:docs/state_index",
    )
    assert store.read_repo().get_document("INDEX") is None
    assert _object_ref_rows(store.engine, "INDEX") == []
    assert _checkpoint(store, "state_and_index_docs").last_outbox_event_id == initial_id
    assert status is not None
    assert status.projected_watermark is None


def test_documents_projector_family_checkpoints_are_independent(
    store: ProjectorStore,
) -> None:
    state_first = _append_file_event(
        store,
        document_id="STATE",
        content_hash="hash-state-1",
    )
    handover_first = _append_file_event(
        store,
        document_id="session-one",
        source_family="handover_sessions",
        content_hash="hash-session-1",
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("STATE", "hash-state-1"),
        source_watermark="collect-state-1",
    )
    _upsert_status(
        store,
        source_family="handover_sessions",
        latest_source_event_id=_source_event_id(
            "session-one",
            "hash-session-1",
            source_family="handover_sessions",
        ),
        source_watermark="collect-session-1",
    )
    store.projector().run_once(batch_size=20)
    _append_file_event(
        store,
        document_id="STATE",
        content_hash="hash-state-2",
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("STATE", "hash-state-2"),
        source_watermark="collect-state-2",
    )

    store.projector().run_once(batch_size=20)

    state_checkpoint = _checkpoint(store, "state_and_index_docs")
    handover_checkpoint = _checkpoint(store, "handover_sessions")
    assert state_checkpoint is not None
    assert handover_checkpoint is not None
    assert state_checkpoint.last_outbox_event_id not in {state_first, handover_first}
    assert handover_checkpoint.last_outbox_event_id == handover_first


def test_documents_projector_legacy_checkpoint_cursor_recovers_from_event_id(
    store: ProjectorStore,
) -> None:
    first_id = _append_file_event(store, document_id="STATE", content_hash="hash-state")
    second_id = _append_file_event(
        store,
        document_id="INDEX",
        content_hash="hash-index",
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("INDEX", "hash-index"),
        source_watermark="collect-index",
    )
    store.projection_repo().save_projection_checkpoint(
        repositories.ProjectionCheckpointRecord(
            projection_name=_projection_name("state_and_index_docs"),
            last_outbox_event_id=first_id,
            last_processed_at_utc=PROJECTOR_NOW,
            source_watermark="legacy-watermark",
            last_source_observed_at_utc=EVENT_TIME,
            lag_seconds=0,
            status="running",
            metadata={},
        )
    )

    store.projector().run_once(batch_size=20)

    assert second_id != first_id
    assert store.read_repo().get_document("STATE") is None
    assert store.read_repo().get_document("INDEX") is not None


def test_documents_projector_ignores_config_proposals(
    store: ProjectorStore,
) -> None:
    _append_file_event(
        store,
        document_id="proposal-one",
        source_family="config_proposals",
        content_hash="hash-proposal",
    )
    _upsert_status(
        store,
        source_family="config_proposals",
        latest_source_event_id=_source_event_id(
            "proposal-one",
            "hash-proposal",
            source_family="config_proposals",
        ),
        source_watermark="collect-proposal",
    )

    result = store.projector().run_once(batch_size=20)

    assert result.consumed_event_count == 0
    assert store.read_repo().list_documents().items == ()
    assert _checkpoint(store, "config_proposals") is None


def test_documents_projector_does_not_write_domain_projection_status(
    store: ProjectorStore,
) -> None:
    _append_file_event(store, document_id="STATE", content_hash="hash-state")
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=_source_event_id("STATE", "hash-state"),
        source_watermark="collect-state",
    )

    store.projector().run_once(batch_size=20)

    assert _domain_projection_status(store.engine, "documents") is None


def test_documents_projector_missing_api_family_status_blocks_scoped_readiness(
    store: ProjectorStore,
) -> None:
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        source_watermark="collect-state",
        projected_watermark="collect-state",
    )

    result = store.projector().run_once(batch_size=20)

    assert result.scoped_readiness.ready_for_postgres is False
    assert any(
        blocker.code == "missing_sources"
        and blocker.source_family == "handover_sessions"
        for blocker in result.scoped_readiness.blockers
    )


def test_documents_projector_collect_watermark_advances_only_after_latest_event(
    store: ProjectorStore,
) -> None:
    old_event_id = _source_event_id("STATE", "hash-old")
    latest_event_id = _source_event_id("INDEX", "hash-latest")
    _append_file_event(store, document_id="STATE", content_hash="hash-old")
    _append_file_event(store, document_id="INDEX", content_hash="hash-latest")
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id=latest_event_id,
        source_watermark="collect-latest",
    )

    store.projector().run_once(batch_size=1)
    mid_status = store.projection_repo().get_projection_source_status(
        domain_name="documents",
        source_family="state_and_index_docs",
        source_identity="repo:docs/state_index",
    )
    store.projector().run_once(batch_size=1)
    final_status = store.projection_repo().get_projection_source_status(
        domain_name="documents",
        source_family="state_and_index_docs",
        source_identity="repo:docs/state_index",
    )

    assert old_event_id != latest_event_id
    assert mid_status is not None
    assert mid_status.projected_watermark is None
    assert final_status is not None
    assert final_status.projected_watermark == "collect-latest"


def test_documents_projector_tombstone_revision_uses_inventory_event_time(
    store: ProjectorStore,
) -> None:
    tombstone_time = datetime(2026, 4, 24, 6, 30, tzinfo=UTC)
    _append_file_event(store, document_id="STATE", content_hash="hash-state")
    _append_inventory_event(
        store,
        source_family="state_and_index_docs",
        active_document_ids=(),
        occurred_at_utc=tombstone_time,
    )
    _upsert_status(
        store,
        source_family="state_and_index_docs",
        latest_source_event_id="inventory:state_and_index_docs:empty",
        source_watermark="collect-empty",
    )

    store.projector().run_once(batch_size=20)

    revisions = _revision_rows(store.engine, "STATE")
    assert revisions[1]["created_at_utc"] == tombstone_time


def _run_bridge(
    store: ProjectorStore,
    repo_root: Path,
    *,
    source_families: tuple[str, ...],
) -> None:
    bridge = build_default_bridge(
        repo_root=repo_root,
        artifact_root=repo_root / "artifacts",
        data_root=repo_root / "data",
        domains=("documents",),
        source_families=source_families,
    )
    bridge.run_once(
        repository=store.projection_repo(),
        checked_at_utc=FIXED_NOW,
        source_registry_version=document_projectors.DOCUMENTS_SOURCE_REGISTRY_VERSION,
        write_path="active_bridge",
    )


def _append_file_event(
    store: ProjectorStore,
    *,
    document_id: str,
    source_family: str = "state_and_index_docs",
    content_text: str | None = None,
    content_hash: str | None = None,
    source_event_id: str | None = None,
    title: str | None = None,
    dedupe_suffix: str | None = None,
    occurred_at_utc: datetime = EVENT_TIME,
) -> str:
    text_value = content_text or f"# {document_id}\n\n{document_id} body.\n"
    hash_value = content_hash or _sha256(text_value)
    relative_path = _relative_path(document_id, source_family)
    resolved_source_event_id = source_event_id or _source_event_id(
        document_id,
        hash_value,
        source_family=source_family,
    )
    source_identity = _source_identity(source_family)
    return store.projection_repo().append_outbox_event(
        repositories.OutboxEventAppendRequest(
            aggregate_type="documents",
            aggregate_id=f"document/{document_id}",
            event_type=f"legacy.{source_family}.file_observed",
            event_version=1,
            dedupe_key=(
                f"test:{source_family}:{resolved_source_event_id}:"
                f"{dedupe_suffix or hash_value}"
            ),
            occurred_at_utc=occurred_at_utc,
            payload={
                "domain_name": "documents",
                "source_family": source_family,
                "source_identity": source_identity,
                "source_event_id": resolved_source_event_id,
                "source_watermark": f"{resolved_source_event_id}:event-watermark",
                "event_family": "documents",
                "event_type": f"legacy.{source_family}.file_observed",
                "resource_type": "document",
                "resource_id": document_id,
                "source_ref": f"{source_identity}:{resolved_source_event_id}",
                "payload": {
                    "document_event_kind": "file_observed",
                    "document_state": "active",
                    "document_id": document_id,
                    "internal_document_key": (
                        f"document:{source_family}:{relative_path}"
                    ),
                    "document_kind": _document_kind(document_id, source_family),
                    "title": title or _document_title(document_id, source_family),
                    "preview": _preview(text_value),
                    "relative_path": relative_path,
                    "logical_retrieval_ref": relative_path,
                    "content_hash": hash_value,
                    "content_text": text_value,
                },
                "metadata": {"document_event_kind": "file_observed"},
            },
        )
    )


def _append_inventory_event(
    store: ProjectorStore,
    *,
    source_family: str,
    active_document_ids: tuple[str, ...],
    source_event_id: str | None = None,
    occurred_at_utc: datetime = EVENT_TIME,
) -> str:
    if source_event_id is None and active_document_ids:
        active_set_hash = _sha256(json.dumps(active_document_ids))[:12]
        resolved_source_event_id = f"inventory:{source_family}:{active_set_hash}"
    else:
        resolved_source_event_id = source_event_id or f"inventory:{source_family}:empty"
    source_identity = _source_identity(source_family)
    return store.projection_repo().append_outbox_event(
        repositories.OutboxEventAppendRequest(
            aggregate_type="documents",
            aggregate_id=f"document_inventory/{source_family}",
            event_type=f"legacy.{source_family}.inventory_snapshot",
            event_version=1,
            dedupe_key=f"test:{source_family}:{resolved_source_event_id}",
            occurred_at_utc=occurred_at_utc,
            payload={
                "domain_name": "documents",
                "source_family": source_family,
                "source_identity": source_identity,
                "source_event_id": resolved_source_event_id,
                "source_watermark": f"{resolved_source_event_id}:event-watermark",
                "event_family": "documents",
                "event_type": f"legacy.{source_family}.inventory_snapshot",
                "resource_type": "document_inventory",
                "resource_id": source_family,
                "source_ref": f"{source_identity}:{resolved_source_event_id}",
                "payload": {
                    "document_event_kind": "inventory_snapshot",
                    "document_state": "inventory",
                    "source_family": source_family,
                    "active_document_ids": list(active_document_ids),
                    "active_documents": [
                        {"document_id": document_id}
                        for document_id in active_document_ids
                    ],
                },
                "metadata": {"document_event_kind": "inventory_snapshot"},
            },
        )
    )


def _upsert_status(
    store: ProjectorStore,
    *,
    source_family: str,
    latest_source_event_id: str = "latest-source-event",
    source_watermark: str = "collect-watermark",
    projected_watermark: str | None = None,
) -> None:
    store.projection_repo().upsert_projection_source_status(
        repositories.ProjectionSourceStatusRecord(
            domain_name="documents",
            source_family=source_family,
            source_identity=_source_identity(source_family),
            source_watermark=source_watermark,
            projected_watermark=projected_watermark,
            lag_seconds=None,
            is_mutable=True,
            ready_for_postgres=True,
            checked_at_utc=FIXED_NOW,
            metadata={
                "initial_import_complete": True,
                "write_path": "active_bridge",
                "source_registry_version": (
                    document_projectors.DOCUMENTS_SOURCE_REGISTRY_VERSION
                ),
                "latest_source_event_id": latest_source_event_id,
                "source_errors": (),
            },
        )
    )


def _checkpoint(
    store: ProjectorStore,
    source_family: str,
) -> repositories.ProjectionCheckpointRecord | None:
    return store.projection_repo().load_projection_checkpoint(
        _projection_name(source_family)
    )


def _delete_checkpoint(store: ProjectorStore, source_family: str) -> None:
    with store.engine.begin() as connection:
        connection.execute(
            text("""
                DELETE FROM system.projection_checkpoint
                WHERE projection_name = :projection_name
                """),
            {"projection_name": _projection_name(source_family)},
        )


def _projection_name(source_family: str) -> str:
    return document_projectors.document_projection_name(
        domain_name="documents",
        source_family=source_family,
    )


def _relative_path(document_id: str, source_family: str) -> str:
    if source_family == "handover_sessions":
        return f"docs/handover/SESSIONS/{document_id}.md"
    if source_family == "config_proposals":
        return f"config/proposals/{document_id}.md"
    if document_id == "STATE":
        return "docs/handover/STATE.md"
    if document_id == "INDEX":
        return "docs/INDEX.md"
    return f"docs/{document_id}.md"


def _source_event_id(
    document_id: str,
    content_hash: str,
    *,
    source_family: str = "state_and_index_docs",
) -> str:
    return f"file:{_relative_path(document_id, source_family)}:{content_hash}"


def _source_identity(source_family: str) -> str:
    return {
        "config_proposals": "repo:config/proposals",
        "handover_sessions": "repo:docs/handover_sessions",
        "state_and_index_docs": "repo:docs/state_index",
    }[source_family]


def _document_kind(document_id: str, source_family: str) -> str:
    if source_family == "handover_sessions":
        return "handover"
    if document_id == "STATE":
        return "state"
    if document_id == "INDEX":
        return "index"
    return "document"


def _document_title(document_id: str, source_family: str) -> str:
    if document_id == "STATE":
        return "Project state"
    if document_id == "INDEX":
        return "Artifact index"
    if source_family == "handover_sessions":
        return document_id.replace("-", " ")
    return document_id


def _preview(content_text: str) -> str:
    lines = [
        line.strip()
        for line in content_text.splitlines()
        if line.strip() and not line.strip().startswith("---")
    ]
    return lines[1] if len(lines) > 1 else (lines[0] if lines else "")


def _write_text(path: Path, text_value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text_value, encoding="utf-8")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sequential_id_provider() -> Callable[[], str]:
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"outbox-{counter:03d}"

    return next_id


def _document_counts(engine: Engine) -> dict[str, int]:
    return {
        "documents": _count(engine, "documents.document"),
        "revisions": _count(engine, "documents.document_revision"),
        "object_refs": _count(engine, "documents.document_object_ref"),
    }


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
    return int(value)


def _revision_rows(engine: Engine, document_id: str) -> list[dict[str, Any]]:
    return _rows(
        engine,
        """
        SELECT document_revision_id, revision_number, created_at_utc,
               source_ref, metadata_json
        FROM documents.document_revision
        WHERE document_id = :document_id
        ORDER BY revision_number ASC
        """,
        {"document_id": document_id},
    )


def _object_ref_rows(engine: Engine, document_id: str) -> list[dict[str, Any]]:
    return _rows(
        engine,
        """
        SELECT ref.document_object_ref_id, ref.object_uri
        FROM documents.document_object_ref AS ref
        JOIN documents.document_revision AS revision
          ON revision.document_revision_id = ref.document_revision_id
        WHERE revision.document_id = :document_id
        ORDER BY ref.object_uri ASC
        """,
        {"document_id": document_id},
    )


def _domain_projection_status(
    engine: Engine,
    domain_name: str,
) -> dict[str, Any] | None:
    rows = _rows(
        engine,
        """
        SELECT domain_name, metadata_json
        FROM system.domain_projection_status
        WHERE domain_name = :domain_name
        """,
        {"domain_name": domain_name},
    )
    return rows[0] if rows else None


def _update_document_title(engine: Engine, document_id: str, title: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("""
                UPDATE documents.document
                SET title = :title
                WHERE document_id = :document_id
                """),
            {"document_id": document_id, "title": title},
        )


def _rows(
    engine: Engine,
    sql: str,
    params: Mapping[str, object] | None = None,
) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        rows = connection.execute(text(sql), dict(params or {})).mappings().all()
    return [dict(row) for row in rows]
