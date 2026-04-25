from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from tradingx.controlplane import document_projectors, projections, repositories

FIXED_NOW = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)


def test_document_read_record_uses_public_route_shape() -> None:
    record_type = getattr(repositories, "DocumentReadRecord", None)

    assert record_type is not None
    record = record_type(
        document_id="STATE",
        document_kind="state",
        title="Project state",
        preview="Ready for projector work.",
        logical_retrieval_ref="docs/handover/STATE.md",
        source_ref="repo:docs/state_index:file:docs/handover/STATE.md:abc",
        created_at_utc=datetime(2026, 4, 24, 12, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 24, 13, tzinfo=UTC),
        metadata={
            "internal_document_key": (
                "document:state_and_index_docs:docs/handover/STATE.md"
            )
        },
        latest_revision=None,
    )

    assert record.document_id == "STATE"
    assert not record.document_id.startswith("document:")
    assert record.logical_retrieval_ref == "docs/handover/STATE.md"


def test_document_projection_records_name_revision_key_scope() -> None:
    document_type = getattr(repositories, "DocumentProjectionDocument", None)
    revision_type = getattr(repositories, "DocumentProjectionRevision", None)

    assert document_type is not None
    assert revision_type is not None
    document = document_type(
        document_id="STATE",
        document_kind="state",
        title="Project state",
        preview="First revision.",
        logical_retrieval_ref="docs/handover/STATE.md",
        document_state="active",
        created_at_utc=datetime(2026, 4, 24, 12, tzinfo=UTC),
        updated_at_utc=datetime(2026, 4, 24, 12, tzinfo=UTC),
        source_ref="source:file:STATE:first",
        metadata={"content_hash": "hash-1"},
    )
    revision = revision_type(
        document_revision_id="STATE:1",
        document_id="STATE",
        revision_number=1,
        created_at_utc=datetime(2026, 4, 24, 12, tzinfo=UTC),
        source_ref="source:file:STATE:first",
        metadata={"content_hash": "hash-1"},
    )

    assert document.document_id == revision.document_id
    assert revision.revision_key == ("STATE", 1)


def test_documents_projector_reads_only_api_document_source_families() -> None:
    uow = FakeDocumentsProjectorUnitOfWork(
        events=(
            _file_event(source_family="state_and_index_docs", document_id="STATE"),
            _file_event(source_family="config_proposals", document_id="proposal-1"),
        ),
        statuses=(
            _status(source_family="state_and_index_docs"),
            _status(source_family="handover_sessions"),
            _status(source_family="config_proposals"),
        ),
    )

    projector = document_projectors.DocumentsProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )
    projector.run_once(batch_size=10)

    assert {
        call["source_families"] for call in uow.projection_repo.outbox_read_calls
    } == {("handover_sessions",), ("state_and_index_docs",)}
    assert all(
        call["source_families"] != ("config_proposals",)
        for call in uow.projection_repo.outbox_read_calls
    )
    assert [document.document_id for document in uow.document_repo.documents] == [
        "STATE"
    ]


def test_documents_projector_materializes_file_events_and_object_refs() -> None:
    event = _file_event(document_id="STATE", content_hash="hash-state")
    uow = FakeDocumentsProjectorUnitOfWork(
        events=(event,),
        statuses=(
            _status(
                source_family="state_and_index_docs",
                source_watermark="collect-watermark",
                latest_source_event_id="file:docs/handover/STATE.md:hash-state",
            ),
            _status(source_family="handover_sessions"),
        ),
    )

    projector = document_projectors.DocumentsProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )
    result = projector.run_once(batch_size=10)

    assert result.projected_event_count == 1
    assert uow.document_repo.allocations == [
        ("STATE", uow.document_repo.revisions[0].document_revision_id)
    ]
    document = uow.document_repo.documents[0]
    revision = uow.document_repo.revisions[0]
    refs = uow.document_repo.object_refs[revision.document_revision_id]
    assert document.document_id == "STATE"
    assert document.logical_retrieval_ref == "docs/handover/STATE.md"
    assert document.metadata["latest_active_outbox_event_id"] == event.outbox_event_id
    assert revision.revision_number == 1
    assert refs[0].object_uri == "docs/handover/STATE.md"
    assert refs[0].sha256_hash == "hash-state"
    status = uow.projection_repo.statuses[
        ("documents", "state_and_index_docs", "repo:docs/state_index")
    ]
    checkpoint = uow.projection_repo.checkpoints[
        document_projectors.document_projection_name(
            domain_name="documents",
            source_family="state_and_index_docs",
        )
    ]
    assert status.projected_watermark == "collect-watermark"
    assert checkpoint.source_watermark == "collect-watermark"


def test_documents_projector_records_custom_mapper_version_metadata() -> None:
    event = _file_event(document_id="STATE", content_hash="hash-state")
    uow = FakeDocumentsProjectorUnitOfWork(
        events=(event,),
        statuses=(
            _status(
                source_family="state_and_index_docs",
                latest_source_event_id="file:docs/handover/STATE.md:hash-state",
            ),
            _status(source_family="handover_sessions"),
        ),
    )

    projector = document_projectors.DocumentsProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
        mapper_version="v2",
    )
    projector.run_once(batch_size=10)

    document = uow.document_repo.documents[0]
    revision = uow.document_repo.revisions[0]
    ref = uow.document_repo.object_refs[revision.document_revision_id][0]
    assert document.metadata["mapper_version"] == "v2"
    assert revision.metadata["mapper_version"] == "v2"
    assert ref.metadata["mapper_version"] == "v2"


def test_documents_projector_inventory_tombstone_writes_revision_history() -> None:
    event = _inventory_event(active_document_ids=("STATE",))
    uow = FakeDocumentsProjectorUnitOfWork(
        events=(event,),
        statuses=(
            _status(source_family="state_and_index_docs"),
            _status(source_family="handover_sessions"),
        ),
    )

    projector = document_projectors.DocumentsProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )
    projector.run_once(batch_size=10)

    assert uow.document_repo.tombstone_calls == [
        {
            "source_family": "state_and_index_docs",
            "active_document_ids": ("STATE",),
            "tombstoned_at_utc": event.occurred_at_utc,
            "source_ref": "repo:docs/state_index:inventory:state_and_index_docs",
            "inventory_cursor_created_at_utc": event.created_at_utc,
            "inventory_outbox_event_id": event.outbox_event_id,
        }
    ]


def test_documents_projector_scoped_readiness_blocks_when_api_family_missing() -> None:
    uow = FakeDocumentsProjectorUnitOfWork(
        events=(),
        statuses=(
            _status(
                source_family="state_and_index_docs",
                source_watermark="state-watermark",
                projected_watermark="state-watermark",
            ),
        ),
    )

    projector = document_projectors.DocumentsProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )
    result = projector.run_once(batch_size=10)

    report = result.scoped_readiness
    assert report.ready_for_postgres is False
    assert {requirement.source_family for requirement in report.requirements} == {
        "handover_sessions",
        "state_and_index_docs",
    }
    assert any(
        blocker.code == "missing_sources"
        and blocker.source_family == "handover_sessions"
        for blocker in report.blockers
    )


def test_documents_projector_rollback_does_not_advance_checkpoint() -> None:
    uow = FakeDocumentsProjectorUnitOfWork(
        events=(_file_event(document_id="STATE"),),
        statuses=(
            _status(source_family="state_and_index_docs"),
            _status(source_family="handover_sessions"),
        ),
        fail_on_upsert=True,
    )
    projector = document_projectors.DocumentsProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(RuntimeError, match="document write failed"):
        projector.run_once(batch_size=10)

    assert uow.projection_repo.checkpoints == {}
    status = uow.projection_repo.statuses[
        ("documents", "state_and_index_docs", "repo:docs/state_index")
    ]
    assert status.projected_watermark is None
    assert uow.document_repo.documents == []


class FakeDocumentsProjectorUnitOfWork:
    def __init__(
        self,
        *,
        events: tuple[repositories.OutboxProjectionEvent, ...],
        statuses: tuple[repositories.ProjectionSourceStatusRecord, ...],
        fail_on_upsert: bool = False,
    ) -> None:
        self.projection_repo = FakeProjectionRepository(
            events=events,
            statuses=statuses,
        )
        self.document_repo = FakeDocumentProjectionRepository(
            fail_on_upsert=fail_on_upsert
        )

    @contextmanager
    def transaction(
        self,
    ) -> Iterator[tuple[FakeProjectionRepository, FakeDocumentProjectionRepository]]:
        projection_snapshot = self.projection_repo.snapshot()
        document_snapshot = self.document_repo.snapshot()
        try:
            yield self.projection_repo, self.document_repo
        except Exception:
            self.projection_repo.restore(projection_snapshot)
            self.document_repo.restore(document_snapshot)
            raise


class FakeProjectionRepository:
    def __init__(
        self,
        *,
        events: tuple[repositories.OutboxProjectionEvent, ...],
        statuses: tuple[repositories.ProjectionSourceStatusRecord, ...],
    ) -> None:
        self.events = events
        self.statuses = {status.identity_key: status for status in statuses}
        self.checkpoints: dict[str, repositories.ProjectionCheckpointRecord] = {}
        self.outbox_read_calls: list[dict[str, object]] = []

    def snapshot(self) -> dict[str, object]:
        return {
            "statuses": deepcopy(self.statuses),
            "checkpoints": deepcopy(self.checkpoints),
            "outbox_read_calls": deepcopy(self.outbox_read_calls),
        }

    def restore(self, snapshot: Mapping[str, object]) -> None:
        self.statuses = deepcopy(snapshot["statuses"])
        self.checkpoints = deepcopy(snapshot["checkpoints"])
        self.outbox_read_calls = deepcopy(snapshot["outbox_read_calls"])

    def load_projection_checkpoint(
        self,
        projection_name: str,
    ) -> repositories.ProjectionCheckpointRecord | None:
        return self.checkpoints.get(projection_name)

    def save_projection_checkpoint(
        self,
        record: repositories.ProjectionCheckpointRecord,
    ) -> None:
        self.checkpoints[record.projection_name] = record

    def list_outbox_events_after(
        self,
        *,
        cursor_created_at_utc: datetime | None,
        cursor_outbox_event_id: str | None,
        aggregate_types: tuple[str, ...],
        source_families: tuple[str, ...],
        batch_size: int,
    ) -> tuple[repositories.OutboxProjectionEvent, ...]:
        self.outbox_read_calls.append(
            {
                "cursor_created_at_utc": cursor_created_at_utc,
                "cursor_outbox_event_id": cursor_outbox_event_id,
                "aggregate_types": aggregate_types,
                "source_families": source_families,
                "batch_size": batch_size,
            }
        )
        rows = tuple(
            event
            for event in sorted(
                self.events,
                key=lambda item: (item.created_at_utc, item.outbox_event_id),
            )
            if event.aggregate_type in aggregate_types
            and str(event.payload["source_family"]) in source_families
        )
        return rows[:batch_size]

    def get_outbox_event_cursor(
        self,
        outbox_event_id: str,
    ) -> tuple[datetime, str] | None:
        for event in self.events:
            if event.outbox_event_id == outbox_event_id:
                return (event.created_at_utc, event.outbox_event_id)
        return None

    def get_projection_source_status(
        self,
        *,
        domain_name: str,
        source_family: str,
        source_identity: str,
    ) -> repositories.ProjectionSourceStatusRecord | None:
        return self.statuses.get((domain_name, source_family, source_identity))

    def upsert_projection_source_status(
        self,
        record: repositories.ProjectionSourceStatusRecord,
    ) -> None:
        self.statuses[record.identity_key] = record

    def list_projection_source_statuses(
        self,
        domain_name: str,
    ) -> tuple[repositories.ProjectionSourceStatusRecord, ...]:
        return tuple(
            status
            for status in self.statuses.values()
            if status.domain_name == domain_name
        )

    def save_domain_projection_status_from_readiness(
        self,
        report: projections.ProjectionReadinessReport,
    ) -> repositories.ProjectionStatusSummary:
        del report
        raise AssertionError("documents projector must not persist domain status")


class FakeDocumentProjectionRepository:
    def __init__(self, *, fail_on_upsert: bool = False) -> None:
        self.fail_on_upsert = fail_on_upsert
        self.documents: list[repositories.DocumentProjectionDocument] = []
        self.revisions: list[repositories.DocumentProjectionRevision] = []
        self.object_refs: dict[
            str,
            tuple[repositories.DocumentProjectionObjectRef, ...],
        ] = {}
        self.tombstone_calls: list[dict[str, object]] = []
        self.allocations: list[tuple[str, str]] = []

    def snapshot(self) -> dict[str, object]:
        return {
            "documents": deepcopy(self.documents),
            "revisions": deepcopy(self.revisions),
            "object_refs": deepcopy(self.object_refs),
            "tombstone_calls": deepcopy(self.tombstone_calls),
            "allocations": deepcopy(self.allocations),
        }

    def restore(self, snapshot: Mapping[str, object]) -> None:
        self.documents = deepcopy(snapshot["documents"])
        self.revisions = deepcopy(snapshot["revisions"])
        self.object_refs = deepcopy(snapshot["object_refs"])
        self.tombstone_calls = deepcopy(snapshot["tombstone_calls"])
        self.allocations = deepcopy(snapshot["allocations"])

    def get_document_revision(
        self,
        document_revision_id: str,
    ) -> repositories.DocumentProjectionRevision | None:
        for revision in self.revisions:
            if revision.document_revision_id == document_revision_id:
                return revision
        return None

    def allocate_document_revision_number(
        self,
        document_id: str,
        document_revision_id: str,
    ) -> int:
        self.allocations.append((document_id, document_revision_id))
        existing = self.get_document_revision(document_revision_id)
        if existing is not None:
            return existing.revision_number
        latest = max(
            (
                revision.revision_number
                for revision in self.revisions
                if revision.document_id == document_id
            ),
            default=0,
        )
        return latest + 1

    def upsert_document_revision(
        self,
        document: repositories.DocumentProjectionDocument,
        revision: repositories.DocumentProjectionRevision,
    ) -> None:
        if self.fail_on_upsert:
            raise RuntimeError("document write failed")
        if self.get_document_revision(revision.document_revision_id) is None:
            self.revisions.append(revision)
        self.documents.append(document)

    def replace_document_object_refs(
        self,
        document_revision_id: str,
        refs: tuple[repositories.DocumentProjectionObjectRef, ...],
    ) -> None:
        self.object_refs[document_revision_id] = refs

    def tombstone_documents_absent_from_inventory_with_revisions(
        self,
        *,
        source_family: str,
        active_document_ids: tuple[str, ...],
        tombstoned_at_utc: datetime,
        source_ref: str,
        metadata: Mapping[str, Any],
        inventory_cursor_created_at_utc: datetime | None = None,
        inventory_outbox_event_id: str | None = None,
    ) -> tuple[str, ...]:
        del metadata
        self.tombstone_calls.append(
            {
                "source_family": source_family,
                "active_document_ids": active_document_ids,
                "tombstoned_at_utc": tombstoned_at_utc,
                "source_ref": source_ref,
                "inventory_cursor_created_at_utc": inventory_cursor_created_at_utc,
                "inventory_outbox_event_id": inventory_outbox_event_id,
            }
        )
        return ()


def _file_event(
    *,
    document_id: str,
    source_family: str = "state_and_index_docs",
    source_identity: str = "repo:docs/state_index",
    content_hash: str = "hash-1",
) -> repositories.OutboxProjectionEvent:
    relative_path = (
        "docs/handover/STATE.md" if document_id == "STATE" else f"docs/{document_id}.md"
    )
    source_event_id = f"file:{relative_path}:{content_hash}"
    return repositories.OutboxProjectionEvent(
        outbox_event_id=f"outbox-{document_id}",
        aggregate_type="documents",
        aggregate_id=f"document/{document_id}",
        event_type=f"legacy.{source_family}.file_observed",
        event_version=1,
        occurred_at_utc=FIXED_NOW,
        dedupe_key=f"dedupe-{document_id}",
        payload={
            "domain_name": "documents",
            "source_family": source_family,
            "source_identity": source_identity,
            "source_event_id": source_event_id,
            "source_watermark": f"{source_event_id}:event-watermark",
            "source_ref": f"{source_identity}:{source_event_id}",
            "payload": {
                "document_event_kind": "file_observed",
                "document_state": "active",
                "document_id": document_id,
                "internal_document_key": f"document:{source_family}:{relative_path}",
                "document_kind": "state",
                "title": "Project state",
                "preview": "Project state preview",
                "relative_path": relative_path,
                "logical_retrieval_ref": relative_path,
                "content_hash": content_hash,
                "content_text": "# Project state",
            },
            "metadata": {"document_event_kind": "file_observed"},
        },
        created_at_utc=FIXED_NOW,
    )


def _inventory_event(
    *,
    active_document_ids: tuple[str, ...],
    source_family: str = "state_and_index_docs",
    source_identity: str = "repo:docs/state_index",
) -> repositories.OutboxProjectionEvent:
    source_event_id = f"inventory:{source_family}"
    return repositories.OutboxProjectionEvent(
        outbox_event_id=f"outbox-{source_event_id}",
        aggregate_type="documents",
        aggregate_id=f"document_inventory/{source_family}",
        event_type=f"legacy.{source_family}.inventory_snapshot",
        event_version=1,
        occurred_at_utc=FIXED_NOW,
        dedupe_key=f"dedupe-{source_event_id}",
        payload={
            "domain_name": "documents",
            "source_family": source_family,
            "source_identity": source_identity,
            "source_event_id": source_event_id,
            "source_watermark": f"{source_event_id}:event-watermark",
            "source_ref": f"{source_identity}:{source_event_id}",
            "payload": {
                "document_event_kind": "inventory_snapshot",
                "document_state": "inventory",
                "source_family": source_family,
                "active_document_ids": list(active_document_ids),
                "active_documents": [
                    {"document_id": document_id} for document_id in active_document_ids
                ],
            },
            "metadata": {"document_event_kind": "inventory_snapshot"},
        },
        created_at_utc=FIXED_NOW,
    )


def _status(
    *,
    source_family: str,
    source_identity: str | None = None,
    source_watermark: str = "collect-watermark",
    projected_watermark: str | None = None,
    latest_source_event_id: str = "source-event-latest",
) -> repositories.ProjectionSourceStatusRecord:
    identities = {
        "handover_sessions": "repo:docs/handover_sessions",
        "state_and_index_docs": "repo:docs/state_index",
        "config_proposals": "repo:config/proposals",
    }
    return repositories.ProjectionSourceStatusRecord(
        domain_name="documents",
        source_family=source_family,
        source_identity=source_identity or identities[source_family],
        source_watermark=source_watermark,
        projected_watermark=projected_watermark,
        lag_seconds=None,
        is_mutable=True,
        ready_for_postgres=True,
        checked_at_utc=FIXED_NOW,
        metadata={
            "initial_import_complete": True,
            "write_path": "active_bridge",
            "latest_source_event_id": latest_source_event_id,
        },
    )
