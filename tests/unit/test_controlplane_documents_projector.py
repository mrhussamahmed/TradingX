from __future__ import annotations

from datetime import UTC, datetime

from tradingx.controlplane import repositories


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
