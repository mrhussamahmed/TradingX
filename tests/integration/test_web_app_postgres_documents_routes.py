from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from tradingx.config import TradingConfig
from tradingx.controlplane import repositories
from tradingx.persistence import postgres
from tradingx.persistence.repositories.document_projection import (
    PostgresDocumentProjectionRepository,
)
from tradingx.persistence.repositories.projection_state import (
    PostgresProjectionStateRepository,
)
from tradingx.types import DocumentRecord
from tradingx.web.app import create_app

pytestmark = pytest.mark.skipif(
    not os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip(),
    reason="TRADINGX_TEST_POSTGRES_DSN is not configured",
)


def _postgres_dsn() -> str:
    dsn = os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("TRADINGX_TEST_POSTGRES_DSN is not configured")
    return dsn


@pytest.fixture()
def store() -> Iterator[_RouteStore]:
    dsn = _postgres_dsn()
    engine = postgres.build_postgres_engine(postgres.PostgresSettings(dsn=dsn))
    postgres.reset_postgres_test_database(engine, dsn=dsn)
    postgres.run_postgres_migrations(dsn, revision="head")
    try:
        yield _RouteStore(engine=engine, dsn=dsn)
    finally:
        engine.dispose()


@dataclass(frozen=True)
class _RouteStore:
    engine: Engine
    dsn: str

    def documents(self) -> PostgresDocumentProjectionRepository:
        return PostgresDocumentProjectionRepository(engine=self.engine, dsn=self.dsn)

    def projection_state(self) -> PostgresProjectionStateRepository:
        return PostgresProjectionStateRepository(engine=self.engine, dsn=self.dsn)


class _ReadModel:
    def __init__(self, documents: tuple[DocumentRecord, ...]) -> None:
        self._documents = documents

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        return self._documents


class _ActionRunner:
    pass


def test_v1_documents_hybrid_override_reads_ready_postgres_list_detail_and_tombstones(
    tmp_path: Path,
    store: _RouteStore,
) -> None:
    _seed_documents(store)
    _seed_scoped_readiness(store, ready=True, include_config_proposals=True)
    client = _client(
        tmp_path,
        store,
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
        },
    )

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/STATE")
    tombstone_response = client.get("/api/v1/documents/DELETED")

    assert list_response.status_code == 200
    document_ids = {
        item["doc_id"] for item in list_response.json()["data"]["items"]
    }
    assert {"STATE", "INDEX", "2026-04-25-wave2"} <= document_ids
    assert "DELETED" not in document_ids
    assert "LEGACY" not in document_ids
    assert detail_response.status_code == 200
    assert detail_response.json()["data"] == {
        "document_id": "STATE",
        "title": "Project state",
        "kind": "state",
        "preview": "Postgres state.",
        "retrieval_ref": "docs/handover/STATE.md",
    }
    assert tombstone_response.status_code == 404
    assert tombstone_response.json()["data"]["error"]["code"] == "document_not_found"


@pytest.mark.parametrize(
    "overrides",
    (
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
            "TRADINGX_POSTGRES_REQUIRED": "true",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "postgres",
        },
    ),
)
def test_v1_documents_required_and_global_postgres_ready_paths_serve_postgres(
    tmp_path: Path,
    store: _RouteStore,
    overrides: dict[str, str],
) -> None:
    _seed_documents(store)
    _seed_scoped_readiness(store, ready=True)
    client = _client(tmp_path, store, overrides)

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/INDEX")

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["doc_id"] in {
        "STATE",
        "INDEX",
        "2026-04-25-wave2",
    }
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["document_id"] == "INDEX"
    assert detail_response.json()["data"]["retrieval_ref"] == "docs/INDEX.md"


def test_v1_documents_optional_hybrid_falls_back_to_legacy_when_scoped_family_blocks(
    tmp_path: Path,
    store: _RouteStore,
) -> None:
    _seed_documents(store)
    _seed_scoped_readiness(store, ready=False)
    client = _client(
        tmp_path,
        store,
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
        },
    )

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/LEGACY")

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["doc_id"] == "LEGACY"
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["document_id"] == "LEGACY"


@pytest.mark.parametrize(
    "overrides",
    (
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
            "TRADINGX_POSTGRES_REQUIRED": "true",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "postgres",
        },
    ),
)
def test_v1_documents_required_and_global_postgres_fail_closed_when_family_blocks(
    tmp_path: Path,
    store: _RouteStore,
    overrides: dict[str, str],
) -> None:
    _seed_documents(store)
    _seed_scoped_readiness(store, ready=False)
    client = _client(tmp_path, store, overrides)

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/STATE")

    for response in (list_response, detail_response):
        assert response.status_code == 503
        assert response.json()["data"]["error"]["code"] == (
            "documents_postgres_unavailable"
        )


def test_legacy_documents_route_remains_legacy_when_v1_pivots(
    tmp_path: Path,
    store: _RouteStore,
) -> None:
    _seed_documents(store)
    _seed_scoped_readiness(store, ready=True)
    client = _client(
        tmp_path,
        store,
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
        },
    )

    response = client.get("/api/documents")

    assert response.status_code == 200
    assert response.json()[0]["doc_id"] == "LEGACY"


def _client(
    tmp_path: Path,
    store: _RouteStore,
    overrides: dict[str, str],
) -> TestClient:
    values = {
        "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
        "TRADINGX_POSTGRES_DSN": store.dsn,
    }
    values.update(overrides)
    config = TradingConfig.from_mapping(values)
    app = create_app(
        config=config,
        read_model=_ReadModel(
            (
                DocumentRecord(
                    doc_id="LEGACY",
                    title="Legacy document",
                    path=Path("docs/legacy.md"),
                    preview="Legacy fallback.",
                    kind="state",
                ),
            )
        ),
        action_runner=_ActionRunner(),
    )
    return TestClient(app)


def _seed_documents(store: _RouteStore) -> None:
    writer = store.documents()
    for document_id, kind, title, preview, retrieval_ref in (
        (
            "STATE",
            "state",
            "Project state",
            "Postgres state.",
            "docs/handover/STATE.md",
        ),
        (
            "INDEX",
            "index",
            "Artifact index",
            "Postgres index.",
            "docs/INDEX.md",
        ),
        (
            "2026-04-25-wave2",
            "handover",
            "2026 04 25 wave2",
            "Postgres session.",
            "docs/handover/SESSIONS/2026-04-25-wave2.md",
        ),
        (
            "DELETED",
            "state",
            "Deleted document",
            "Deleted preview.",
            "docs/deleted.md",
        ),
        (
            "proposal-1",
            "config_proposal",
            "Config proposal",
            "Config proposal preview.",
            "config/proposals/proposal-1.md",
        ),
    ):
        state = "tombstoned" if document_id == "DELETED" else "active"
        source_family = (
            "config_proposals"
            if document_id == "proposal-1"
            else None
        )
        writer.upsert_document_revision(
            _document_projection_document(
                document_id=document_id,
                kind=kind,
                title=title,
                preview=preview,
                retrieval_ref=retrieval_ref,
                document_state=state,
                source_family=source_family,
            ),
            _document_projection_revision(document_id=document_id),
        )


def _seed_scoped_readiness(
    store: _RouteStore,
    *,
    ready: bool,
    include_config_proposals: bool = False,
) -> None:
    repo = store.projection_state()
    families = ("handover_sessions", "state_and_index_docs")
    for family in families:
        repo.upsert_projection_source_status(
            _source_status(source_family=family, ready=ready)
        )
    if include_config_proposals:
        repo.upsert_projection_source_status(
            _source_status(source_family="config_proposals", ready=False)
        )


def _document_projection_document(
    *,
    document_id: str,
    kind: str,
    title: str,
    preview: str,
    retrieval_ref: str,
    document_state: str,
    source_family: str | None = None,
) -> repositories.DocumentProjectionDocument:
    timestamp = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    resolved_source_family = source_family or (
        "handover_sessions" if kind == "handover" else "state_and_index_docs"
    )
    return repositories.DocumentProjectionDocument(
        document_id=document_id,
        document_kind=kind,
        title=title,
        preview=preview,
        logical_retrieval_ref=retrieval_ref,
        document_state=document_state,
        created_at_utc=timestamp,
        updated_at_utc=timestamp,
        source_ref=f"source:{document_id}",
        metadata={"source_family": resolved_source_family},
    )


def _document_projection_revision(
    *,
    document_id: str,
) -> repositories.DocumentProjectionRevision:
    timestamp = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    return repositories.DocumentProjectionRevision(
        document_revision_id=f"{document_id}:1",
        document_id=document_id,
        revision_number=1,
        created_at_utc=timestamp,
        source_ref=f"source:{document_id}:revision",
        metadata={},
    )


def _source_status(
    *,
    source_family: str,
    ready: bool,
) -> repositories.ProjectionSourceStatusRecord:
    identities = {
        "handover_sessions": "repo:docs/handover_sessions",
        "state_and_index_docs": "repo:docs/state_index",
        "config_proposals": "repo:config/proposals",
    }
    watermark = f"{source_family}:watermark"
    return repositories.ProjectionSourceStatusRecord(
        domain_name="documents",
        source_family=source_family,
        source_identity=identities[source_family],
        source_watermark=watermark,
        projected_watermark=watermark if ready else f"{source_family}:old",
        lag_seconds=None,
        is_mutable=True,
        ready_for_postgres=ready,
        checked_at_utc=datetime.now(UTC),
        metadata={
            "initial_import_complete": ready,
            "write_path": "active_bridge" if ready else "disabled",
            "latest_source_event_id": f"{source_family}:event",
        },
    )
