from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tradingx.config import TradingConfig
from tradingx.controlplane import repositories
from tradingx.types import (
    ConfigProposal,
    DocumentRecord,
    RuntimeHeartbeatSnapshot,
    WebActionResult,
)
from tradingx.web import app as web_app
from tradingx.web import runtime as web_runtime
from tradingx.web.app import create_app
from tradingx.web.document_routes import (
    DocumentsPostgresUnavailable,
    build_documents_route_provider,
)
from tradingx.web.security import (
    IDEMPOTENCY_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    sign_web_write_request,
)


class _ReadModel:
    def __init__(
        self,
        *,
        documents: tuple[DocumentRecord, ...] = (),
        proposals: tuple[ConfigProposal, ...] = (),
    ) -> None:
        self.documents = documents
        self.proposals = proposals
        self.list_documents_calls = 0

    def build_dashboard_snapshot(self):
        return {"status": "ok"}

    def build_command_center_snapshot(self):
        return {"status": "ok"}

    def build_portfolio_workspace_snapshot(self):
        return {"status": "ok"}

    def build_bot_brain_snapshot(self):
        return {"status": "ok"}

    def build_performance_analytics_snapshot(self):
        return {"status": "ok"}

    def list_documents(self):
        self.list_documents_calls += 1
        return self.documents

    def list_evidence(self, category=None):
        del category
        return ()

    def list_config_proposals(self):
        return self.proposals

    def get_service_state(self):
        return {"status": "idle"}

    def get_runtime_host_state(self):
        return {"status": "idle"}

    def get_latest_historical_warmup(self):
        return None

    def get_latest_strategy_activation(self):
        return None

    def get_latest_model_weight_snapshot(self):
        return None

    def get_latest_opportunity_selection(self):
        return None

    def build_runtime_heartbeat_snapshot(self):
        timestamp = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
        return RuntimeHeartbeatSnapshot(
            heartbeat_state="Idle",
            heartbeat_summary="Runtime is idle.",
            heartbeat_tone="info",
            cadence_seconds=60,
            cadence_label="Every minute",
            last_evaluation_at_utc=timestamp,
            next_evaluation_at_utc=timestamp,
            last_decision="No trade",
            decision_reason="No eligible setup.",
            score_explanation="No score.",
            current_exposure="Flat",
            current_exposure_detail="No open positions.",
            active_symbol="SPY",
            selected_symbol="",
            decision="no_trade",
        )

    def list_timeline_events(self, *, symbol=None, cycle_id=None, incident_id=None):
        del symbol, cycle_id, incident_id
        return ()

    def list_incidents(self):
        return ()

    def build_research_snapshot(self):
        return {"status": "ok"}

    def build_gate3_readiness(self):
        return {"status": "pending"}

    def get_latest_gate3_promotion_package(self):
        return None

    def get_latest_replay_slippage_summary(self):
        return None

    def build_replay_session(self, *, symbol=None, cycle_id=None, incident_id=None):
        del symbol, cycle_id, incident_id
        return {"status": "ok"}

    def search_records(self, *, query="", category=None):
        del query, category
        return ()

    def get_latest_daily_digest(self):
        return None

    def get_latest_market_automation_run(self):
        return None

    def get_scheduler_state(self):
        return {"status": "idle"}

    def get_latest_market_day_schedule(self):
        return None


class _ActionRunner:
    def __init__(self) -> None:
        self.start_service_calls = 0

    def start_service(self, **kwargs):
        del kwargs
        self.start_service_calls += 1
        return WebActionResult(
            action_id="action-start-service",
            action_type="service_start",
            status="accepted",
            message="Service start accepted.",
            evidence_refs=(),
        )

    def stop_service(self):
        return WebActionResult(
            action_id="action-stop-service",
            action_type="service_stop",
            status="accepted",
            message="Service stop accepted.",
            evidence_refs=(),
        )

    def create_config_proposal(self, **kwargs):
        del kwargs
        return {
            "proposal_id": "proposal-1",
            "target_area": "runtime",
            "proposed_values": {},
            "diff_preview": "",
            "output_path": "config/proposals/proposal-1.md",
        }


class _InjectedDocumentsProvider:
    def __init__(
        self,
        *,
        documents: tuple[DocumentRecord, ...] = (),
        error: Exception | None = None,
    ) -> None:
        self.documents = documents
        self.error = error
        self.list_calls = 0
        self.detail_calls: list[str] = []

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        self.list_calls += 1
        if self.error is not None:
            raise self.error
        return self.documents

    def get_document(self, document_id: str) -> DocumentRecord | None:
        self.detail_calls.append(document_id)
        if self.error is not None:
            raise self.error
        return next(
            (document for document in self.documents if document.doc_id == document_id),
            None,
        )


class _FakePostgresDocumentRepository:
    def __init__(
        self,
        documents: tuple[repositories.DocumentReadRecord, ...],
        *,
        next_cursor: str | None = None,
        pages_by_cursor: (
            dict[str, repositories.Page[repositories.DocumentReadRecord]] | None
        ) = None,
    ) -> None:
        self.documents = {document.document_id: document for document in documents}
        self.next_cursor = next_cursor
        self.pages_by_cursor = pages_by_cursor or {}
        self.list_pages: list[repositories.PageRequest | None] = []
        self.detail_ids: list[str] = []

    def list_documents(
        self,
        *,
        page: repositories.PageRequest | None = None,
    ) -> repositories.Page[repositories.DocumentReadRecord]:
        self.list_pages.append(page)
        if page is not None and page.cursor in self.pages_by_cursor:
            return self.pages_by_cursor[page.cursor]
        return repositories.Page(
            items=tuple(self.documents.values()),
            next_cursor=self.next_cursor,
        )

    def get_document(
        self,
        document_id: str,
    ) -> repositories.DocumentReadRecord | None:
        self.detail_ids.append(document_id)
        return self.documents.get(document_id)


class _FakeProjectionStatusRepository:
    def __init__(
        self,
        statuses: tuple[repositories.ProjectionSourceStatusRecord, ...],
    ) -> None:
        self.statuses = statuses
        self.domains: list[str] = []

    def list_projection_source_statuses(
        self,
        domain_name: str,
    ) -> tuple[repositories.ProjectionSourceStatusRecord, ...]:
        self.domains.append(domain_name)
        return self.statuses


def _app_config(tmp_path: Path, **overrides: str) -> TradingConfig:
    values = {
        "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
        "TRADINGX_WEB_WRITE_MODE_ENABLED": "true",
        "TRADINGX_WEB_WRITE_SIGNING_SECRET": "super-secret",
    }
    values.update(overrides)
    return TradingConfig.from_mapping(values)


def _document_record(
    document_id: str,
    *,
    title: str | None = None,
    kind: str = "state",
    preview: str = "Legacy preview.",
    path: str | None = None,
) -> DocumentRecord:
    return DocumentRecord(
        doc_id=document_id,
        title=title or document_id,
        path=Path(path or f"docs/{document_id}.md"),
        preview=preview,
        kind=kind,
    )


def _postgres_document(
    document_id: str,
    *,
    title: str | None = None,
    kind: str = "state",
    preview: str = "Postgres preview.",
    retrieval_ref: str | None = None,
    source_family: str = "state_and_index_docs",
) -> repositories.DocumentReadRecord:
    timestamp = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    return repositories.DocumentReadRecord(
        document_id=document_id,
        document_kind=kind,
        title=title or document_id,
        preview=preview,
        logical_retrieval_ref=retrieval_ref or f"docs/{document_id}.md",
        source_ref="source-ref",
        created_at_utc=timestamp,
        updated_at_utc=timestamp,
        metadata={"internal": "not-public", "source_family": source_family},
        latest_revision=repositories.DocumentRevisionRecord(
            document_revision_id=f"{document_id}:1",
            document_id=document_id,
            revision_number=1,
            created_at_utc=timestamp,
            source_ref="revision-source-ref",
            metadata={"revision": "not-public"},
        ),
    )


def _ready_document_statuses(
    *,
    ready: bool = True,
) -> tuple[repositories.ProjectionSourceStatusRecord, ...]:
    timestamp = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    identities = {
        "handover_sessions": "repo:docs/handover_sessions",
        "state_and_index_docs": "repo:docs/state_index",
        "config_proposals": "repo:config/proposals",
    }
    statuses: list[repositories.ProjectionSourceStatusRecord] = []
    for family in ("handover_sessions", "state_and_index_docs"):
        statuses.append(
            repositories.ProjectionSourceStatusRecord(
                domain_name="documents",
                source_family=family,
                source_identity=identities[family],
                source_watermark=f"{family}:watermark",
                projected_watermark=(
                    f"{family}:watermark" if ready else f"{family}:old-watermark"
                ),
                lag_seconds=None,
                is_mutable=True,
                ready_for_postgres=ready,
                checked_at_utc=timestamp,
                metadata={
                    "initial_import_complete": ready,
                    "write_path": "active_bridge" if ready else "disabled",
                    "latest_source_event_id": f"{family}:event",
                },
            )
        )
    statuses.append(
        repositories.ProjectionSourceStatusRecord(
            domain_name="documents",
            source_family="config_proposals",
            source_identity=identities["config_proposals"],
            source_watermark="config-proposals:watermark",
            projected_watermark=None,
            lag_seconds=None,
            is_mutable=True,
            ready_for_postgres=False,
            checked_at_utc=timestamp,
            metadata={},
        )
    )
    return tuple(statuses)


def _provider_from_fake_postgres(
    *,
    config: TradingConfig,
    read_model: _ReadModel,
    document_repo: _FakePostgresDocumentRepository,
    projection_repo: _FakeProjectionStatusRepository,
):
    return build_documents_route_provider(
        config=config,
        read_model=read_model,
        engine_factory=lambda settings: {"dsn": settings.dsn},
        document_repository_factory=lambda engine, dsn: document_repo,
        projection_repository_factory=lambda engine, dsn: projection_repo,
        clock=lambda: datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )


def _assert_postgres_document_payload(
    payload: dict[str, Any],
    *,
    list_response: bool = False,
) -> None:
    serialized = str(payload)
    assert "not-public" not in serialized
    assert "latest_revision" not in serialized
    assert "metadata" not in serialized
    if list_response:
        assert "next_cursor" in payload["data"]


def _repository_cursor(stable_id: str) -> str:
    return repositories.OrderedCursor.encode(
        timestamp=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        stable_id=stable_id,
    )


def _make_postgres_construction_fail(monkeypatch) -> None:
    from tradingx.controlplane import legacy_bridge
    from tradingx.persistence import postgres as postgres_helpers
    from tradingx.persistence.repositories import postgres as repository_postgres
    from tradingx.persistence.repositories import (
        projection_state as repository_projection_state,
    )
    from tradingx.persistence.repositories import (
        runtime_projection as repository_runtime_projection,
    )

    def fail(*args, **kwargs):
        del args, kwargs
        raise AssertionError("legacy local startup constructed Postgres")

    monkeypatch.setattr(postgres_helpers, "build_postgres_engine", fail)
    monkeypatch.setattr(
        repository_postgres.PostgresControlPlaneRepository,
        "__init__",
        fail,
    )
    monkeypatch.setattr(
        repository_projection_state.PostgresProjectionStateRepository,
        "__init__",
        fail,
    )
    monkeypatch.setattr(
        repository_runtime_projection.PostgresRuntimeProjectionRepository,
        "__init__",
        fail,
    )
    monkeypatch.setattr(
        repository_runtime_projection.PostgresRuntimeProjectorUnitOfWork,
        "__init__",
        fail,
    )
    monkeypatch.setattr(legacy_bridge.LegacyBridge, "__init__", fail)
    monkeypatch.setattr(legacy_bridge.JsonArtifactSourceAdapter, "__init__", fail)
    monkeypatch.setattr(legacy_bridge.SqliteOmsJournalSourceAdapter, "__init__", fail)


def _patch_default_component_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(
        web_runtime,
        "build_trading_client_for_mode",
        lambda config, decision: object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "build_market_data_gateway_for_mode",
        lambda config, *, broker_mode=None: object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "LocalActivationGateway",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "HistoricalWarmupService",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "RuntimeOpportunityPlanner",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "AlpacaPortfolioGateway",
        lambda *args, **kwargs: object(),
    )


def _signed_headers(
    path: str,
    body: bytes,
    *,
    timestamp: str | None = None,
) -> dict[str, str]:
    actual_timestamp = timestamp or str(int(datetime.now(UTC).timestamp()))
    return {
        TIMESTAMP_HEADER: actual_timestamp,
        IDEMPOTENCY_HEADER: "idem-1",
        SIGNATURE_HEADER: sign_web_write_request(
            "super-secret",
            method="POST",
            path=path,
            timestamp=actual_timestamp,
            idempotency_key="idem-1",
            body=body,
        ),
    }


def test_spa_fallback_does_not_echo_requested_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tradingx.web.app._repo_root", lambda: Path(tmp_path))
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=_ReadModel(),
        action_runner=_ActionRunner(),
    )

    response = TestClient(app).get("/deep/link")

    assert response.status_code == 503
    assert response.json() == {"message": "Web app frontend has not been built yet."}


def test_legacy_local_web_paths_do_not_construct_postgres(
    tmp_path,
    monkeypatch,
) -> None:
    _make_postgres_construction_fail(monkeypatch)
    _patch_default_component_dependencies(monkeypatch)

    config = TradingConfig.from_mapping(
        {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
    )
    app = create_app(
        config=config,
        read_model=_ReadModel(),
        action_runner=_ActionRunner(),
    )
    client = TestClient(app)

    for path in (
        "/api/v1/runtime/heartbeats",
        "/api/v1/incidents",
        "/api/v1/events",
    ):
        assert client.get(path).status_code == 200

    captured: dict[str, object] = {}

    def fake_uvicorn_run(app_object, *, host, port):
        captured["app"] = app_object
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(web_app.uvicorn, "run", fake_uvicorn_run)

    web_app.run_web_app(config, host="127.0.0.1", port=0)

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 0
    assert captured["app"] is not None


def test_v1_documents_use_injected_provider_for_list_and_detail() -> None:
    provider = _InjectedDocumentsProvider(
        documents=(
            _document_record(
                "STATE",
                title="Project state",
                preview="Postgres preview.",
                path="docs/handover/STATE.md",
            ),
        )
    )
    read_model = _ReadModel(
        documents=(
            _document_record(
                "LEGACY",
                title="Legacy document",
                preview="Legacy preview.",
            ),
        )
    )
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=read_model,
        action_runner=_ActionRunner(),
        documents_route_provider=provider,
    )
    client = TestClient(app)

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/STATE")

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["doc_id"] == "STATE"
    assert detail_response.status_code == 200
    assert detail_response.json()["data"] == {
        "document_id": "STATE",
        "title": "Project state",
        "kind": "state",
        "preview": "Postgres preview.",
        "retrieval_ref": "docs/handover/STATE.md",
    }
    assert provider.list_calls == 1
    assert provider.detail_calls == ["STATE"]
    assert read_model.list_documents_calls == 0


def test_v1_documents_fail_closed_provider_returns_stable_503() -> None:
    provider = _InjectedDocumentsProvider(
        error=DocumentsPostgresUnavailable(reason="scoped_readiness_blocked")
    )
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=_ReadModel(),
        action_runner=_ActionRunner(),
        documents_route_provider=provider,
    )
    client = TestClient(app)

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/STATE")

    for response in (list_response, detail_response):
        assert response.status_code == 503
        assert response.json()["data"]["error"]["code"] == (
            "documents_postgres_unavailable"
        )


def test_legacy_documents_and_config_proposals_bypass_v1_documents_provider() -> None:
    provider = _InjectedDocumentsProvider(
        error=AssertionError("v1 documents provider should not be used")
    )
    read_model = _ReadModel(
        documents=(
            _document_record(
                "LEGACY",
                title="Legacy document",
                preview="Legacy preview.",
            ),
        ),
        proposals=(
            ConfigProposal(
                proposal_id="proposal-1",
                target_area="runtime",
                proposed_values={"TRADINGX_SYMBOL_UNIVERSE": ["SPY"]},
                diff_preview="+ TRADINGX_SYMBOL_UNIVERSE=SPY",
                output_path=Path("config/proposals/proposal-1.md"),
            ),
        ),
    )
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=read_model,
        action_runner=_ActionRunner(),
        documents_route_provider=provider,
    )
    client = TestClient(app)

    legacy_documents = client.get("/api/documents")
    config_proposals = client.get("/api/config/proposals")

    assert legacy_documents.status_code == 200
    assert legacy_documents.json()[0]["doc_id"] == "LEGACY"
    assert config_proposals.status_code == 200
    assert config_proposals.json()[0]["proposal_id"] == "proposal-1"
    assert provider.list_calls == 0
    assert provider.detail_calls == []


@pytest.mark.parametrize(
    "overrides",
    (
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "legacy",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "legacy",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
            "TRADINGX_POSTGRES_REQUIRED": "true",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "legacy",
            "TRADINGX_POSTGRES_REQUIRED": "true",
        },
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
def test_v1_documents_postgres_ready_modes_use_repository_list_and_detail(
    tmp_path: Path,
    overrides: dict[str, str],
) -> None:
    config = _app_config(
        tmp_path,
        TRADINGX_POSTGRES_DSN="postgresql://tradingx:secret@db.local/tradingx",
        **overrides,
    )
    document_repo = _FakePostgresDocumentRepository(
        (
            _postgres_document(
                "STATE",
                title="Project state",
                preview="Postgres state.",
                retrieval_ref="docs/handover/STATE.md",
            ),
        )
    )
    projection_repo = _FakeProjectionStatusRepository(_ready_document_statuses())
    read_model = _ReadModel(documents=(_document_record("LEGACY"),))
    provider = _provider_from_fake_postgres(
        config=config,
        read_model=read_model,
        document_repo=document_repo,
        projection_repo=projection_repo,
    )
    app = create_app(
        config=config,
        read_model=read_model,
        action_runner=_ActionRunner(),
        documents_route_provider=provider,
    )
    client = TestClient(app)

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/STATE")

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["doc_id"] == "STATE"
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["document_id"] == "STATE"
    assert document_repo.list_pages == [None]
    assert document_repo.detail_ids == ["STATE"]
    assert read_model.list_documents_calls == 0
    _assert_postgres_document_payload(list_response.json(), list_response=True)
    _assert_postgres_document_payload(detail_response.json())


def test_v1_documents_postgres_list_drains_repository_pages(
    tmp_path: Path,
) -> None:
    next_cursor = _repository_cursor("STATE")
    config = _app_config(
        tmp_path,
        TRADINGX_POSTGRES_DSN="postgresql://tradingx:secret@db.local/tradingx",
        TRADINGX_CONTROL_PLANE_STORE="hybrid",
        TRADINGX_CONTROL_PLANE_DOMAIN_STORES="documents=postgres",
    )
    document_repo = _FakePostgresDocumentRepository(
        (_postgres_document("STATE"),),
        next_cursor=next_cursor,
        pages_by_cursor={
            next_cursor: repositories.Page(
                items=(
                    _postgres_document(
                        "2026-04-25-wave2",
                        kind="handover",
                        source_family="handover_sessions",
                    ),
                ),
                next_cursor=None,
            )
        },
    )
    projection_repo = _FakeProjectionStatusRepository(_ready_document_statuses())
    read_model = _ReadModel(documents=(_document_record("LEGACY"),))
    provider = _provider_from_fake_postgres(
        config=config,
        read_model=read_model,
        document_repo=document_repo,
        projection_repo=projection_repo,
    )
    app = create_app(
        config=config,
        read_model=read_model,
        action_runner=_ActionRunner(),
        documents_route_provider=provider,
    )

    response = TestClient(app).get("/api/v1/documents")

    assert response.status_code == 200
    assert [item["doc_id"] for item in response.json()["data"]["items"]] == [
        "STATE",
        "2026-04-25-wave2",
    ]
    assert document_repo.list_pages[0] is None
    assert document_repo.list_pages[1] is not None
    assert document_repo.list_pages[1].cursor == next_cursor


def test_v1_documents_postgres_filters_non_api_document_families(
    tmp_path: Path,
) -> None:
    config = _app_config(
        tmp_path,
        TRADINGX_POSTGRES_DSN="postgresql://tradingx:secret@db.local/tradingx",
        TRADINGX_CONTROL_PLANE_STORE="hybrid",
        TRADINGX_CONTROL_PLANE_DOMAIN_STORES="documents=postgres",
    )
    document_repo = _FakePostgresDocumentRepository(
        (
            _postgres_document("STATE"),
            _postgres_document(
                "proposal-1",
                kind="config_proposal",
                source_family="config_proposals",
            ),
        )
    )
    projection_repo = _FakeProjectionStatusRepository(_ready_document_statuses())
    read_model = _ReadModel(documents=(_document_record("LEGACY"),))
    provider = _provider_from_fake_postgres(
        config=config,
        read_model=read_model,
        document_repo=document_repo,
        projection_repo=projection_repo,
    )
    app = create_app(
        config=config,
        read_model=read_model,
        action_runner=_ActionRunner(),
        documents_route_provider=provider,
    )
    client = TestClient(app)

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/proposal-1")

    assert list_response.status_code == 200
    assert [item["doc_id"] for item in list_response.json()["data"]["items"]] == [
        "STATE"
    ]
    assert detail_response.status_code == 404
    assert detail_response.json()["data"]["error"]["code"] == "document_not_found"


@pytest.mark.parametrize(
    "overrides",
    (
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "legacy",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
        },
    ),
)
def test_v1_documents_optional_postgres_modes_fall_back_to_legacy_when_readiness_blocks(
    tmp_path: Path,
    overrides: dict[str, str],
) -> None:
    config = _app_config(
        tmp_path,
        TRADINGX_POSTGRES_DSN="postgresql://tradingx:secret@db.local/tradingx",
        **overrides,
    )
    document_repo = _FakePostgresDocumentRepository((_postgres_document("STATE"),))
    projection_repo = _FakeProjectionStatusRepository((_ready_document_statuses()[0],))
    read_model = _ReadModel(
        documents=(
            _document_record(
                "LEGACY",
                title="Legacy document",
                preview="Legacy fallback.",
            ),
        )
    )
    provider = _provider_from_fake_postgres(
        config=config,
        read_model=read_model,
        document_repo=document_repo,
        projection_repo=projection_repo,
    )
    app = create_app(
        config=config,
        read_model=read_model,
        action_runner=_ActionRunner(),
        documents_route_provider=provider,
    )
    client = TestClient(app)

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/LEGACY")

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["doc_id"] == "LEGACY"
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["document_id"] == "LEGACY"
    assert document_repo.list_pages == []
    assert document_repo.detail_ids == []
    assert read_model.list_documents_calls == 2


@pytest.mark.parametrize(
    "overrides",
    (
        {
            "TRADINGX_CONTROL_PLANE_STORE": "legacy",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "documents=postgres",
            "TRADINGX_POSTGRES_REQUIRED": "true",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "legacy",
            "TRADINGX_POSTGRES_REQUIRED": "true",
        },
        {
            "TRADINGX_CONTROL_PLANE_STORE": "hybrid",
            "TRADINGX_POSTGRES_REQUIRED": "true",
        },
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
def test_v1_documents_required_and_global_postgres_fail_closed_when_readiness_blocks(
    tmp_path: Path,
    overrides: dict[str, str],
) -> None:
    config = _app_config(
        tmp_path,
        TRADINGX_POSTGRES_DSN="postgresql://tradingx:secret@db.local/tradingx",
        **overrides,
    )
    document_repo = _FakePostgresDocumentRepository((_postgres_document("STATE"),))
    projection_repo = _FakeProjectionStatusRepository((_ready_document_statuses()[0],))
    read_model = _ReadModel(documents=(_document_record("LEGACY"),))
    provider = _provider_from_fake_postgres(
        config=config,
        read_model=read_model,
        document_repo=document_repo,
        projection_repo=projection_repo,
    )
    app = create_app(
        config=config,
        read_model=read_model,
        action_runner=_ActionRunner(),
        documents_route_provider=provider,
    )
    client = TestClient(app)

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/STATE")

    for response in (list_response, detail_response):
        assert response.status_code == 503
        assert response.json()["data"]["error"]["code"] == (
            "documents_postgres_unavailable"
        )
    assert document_repo.list_pages == []
    assert document_repo.detail_ids == []


@pytest.mark.parametrize(
    "global_store",
    ("legacy", "hybrid", "postgres"),
)
def test_v1_documents_legacy_override_beats_required_postgres_modes(
    tmp_path: Path,
    global_store: str,
) -> None:
    config = _app_config(
        tmp_path,
        TRADINGX_CONTROL_PLANE_STORE=global_store,
        TRADINGX_CONTROL_PLANE_DOMAIN_STORES="documents=legacy",
        TRADINGX_POSTGRES_REQUIRED="true",
    )
    read_model = _ReadModel(
        documents=(
            _document_record(
                "LEGACY",
                title="Legacy document",
                preview="Legacy override.",
            ),
        )
    )
    document_repo = _FakePostgresDocumentRepository((_postgres_document("STATE"),))
    projection_repo = _FakeProjectionStatusRepository(_ready_document_statuses())
    provider = _provider_from_fake_postgres(
        config=config,
        read_model=read_model,
        document_repo=document_repo,
        projection_repo=projection_repo,
    )
    app = create_app(
        config=config,
        read_model=read_model,
        action_runner=_ActionRunner(),
        documents_route_provider=provider,
    )
    client = TestClient(app)

    list_response = client.get("/api/v1/documents")
    detail_response = client.get("/api/v1/documents/LEGACY")

    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"][0]["doc_id"] == "LEGACY"
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["document_id"] == "LEGACY"
    assert document_repo.list_pages == []
    assert document_repo.detail_ids == []
    assert read_model.list_documents_calls == 2


def test_unsigned_post_is_rejected(tmp_path) -> None:
    app = create_app(
        config=_app_config(tmp_path),
        read_model=_ReadModel(),
        action_runner=_ActionRunner(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/actions/service/start",
        json={
            "symbols": ["SPY"],
            "quantity": "1",
            "interval_seconds": 300,
            "max_cycles": 1,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Web write timestamp is required."


def test_signed_post_succeeds_and_duplicate_replays_stored_response(tmp_path) -> None:
    runner = _ActionRunner()
    app = create_app(
        config=_app_config(tmp_path),
        read_model=_ReadModel(),
        action_runner=runner,
    )
    client = TestClient(app)
    body = b'{"symbols":["SPY"],"quantity":"1","interval_seconds":300,"max_cycles":1}'
    headers = _signed_headers("/api/actions/service/start", body)

    first = client.post(
        "/api/actions/service/start",
        data=body,
        headers={**headers, "Content-Type": "application/json"},
    )
    second = client.post(
        "/api/actions/service/start",
        data=body,
        headers={**headers, "Content-Type": "application/json"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert runner.start_service_calls == 1


def test_config_summary_never_includes_raw_write_signing_secret(tmp_path) -> None:
    config = _app_config(tmp_path)
    app = create_app(
        config=config,
        read_model=_ReadModel(),
        action_runner=_ActionRunner(),
    )
    client = TestClient(app)

    response = client.get("/api/config/summary")

    assert response.status_code == 200
    payload = response.json()
    serialized = str(payload)
    assert "super-secret" not in serialized
    assert payload["config"]["web_write_signing_configured"] is True
    assert payload["live_disable_report"]["web_write_signing_configured"] is True
