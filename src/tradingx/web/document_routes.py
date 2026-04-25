"""Route-local document read provider for v1 document APIs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.engine import Engine

from tradingx.config import TradingConfig
from tradingx.controlplane import document_projectors, repositories
from tradingx.controlplane.legacy_bridge import document_api_source_families
from tradingx.types import DocumentRecord

_DOCUMENT_API_SOURCE_FAMILIES = frozenset(document_api_source_families())


class DocumentsPostgresUnavailable(RuntimeError):
    """Raised when a fail-closed documents route cannot serve Postgres."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class DocumentsRouteProvider(Protocol):
    def list_documents(self) -> tuple[DocumentRecord, ...]: ...

    def get_document(self, document_id: str) -> DocumentRecord | None: ...


@dataclass(frozen=True)
class _RouteMode:
    use_postgres: bool
    fail_closed: bool


class _LegacyDocumentsRouteProvider:
    def __init__(self, read_model: Any) -> None:
        self._read_model = read_model

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        return tuple(self._read_model.list_documents())

    def get_document(self, document_id: str) -> DocumentRecord | None:
        return next(
            (
                document
                for document in self._read_model.list_documents()
                if document.doc_id == document_id
            ),
            None,
        )


class _ConfiguredDocumentsRouteProvider:
    def __init__(
        self,
        *,
        config: TradingConfig,
        legacy_provider: _LegacyDocumentsRouteProvider,
        mode: _RouteMode,
        engine_factory: Callable[[Any], Engine],
        document_repository_factory: Callable[[Engine, str], Any],
        projection_repository_factory: Callable[[Engine, str], Any],
        clock: Callable[[], datetime],
    ) -> None:
        self._config = config
        self._legacy_provider = legacy_provider
        self._mode = mode
        self._engine_factory = engine_factory
        self._document_repository_factory = document_repository_factory
        self._projection_repository_factory = projection_repository_factory
        self._clock = clock
        self._engine: Engine | None = None
        self._document_repository: Any | None = None
        self._projection_repository: Any | None = None

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        if not self._mode.use_postgres:
            return self._legacy_provider.list_documents()
        bundle = self._postgres_bundle_or_fallback()
        if bundle is None:
            return self._legacy_provider.list_documents()
        document_repository, _projection_repository = bundle
        try:
            documents = _scoped_api_documents(
                _drain_document_pages(document_repository)
            )
        except Exception:
            self._raise_if_fail_closed("repository_unavailable")
            return self._legacy_provider.list_documents()
        return tuple(
            _document_record_from_postgres(document) for document in documents
        )

    def get_document(self, document_id: str) -> DocumentRecord | None:
        if not self._mode.use_postgres:
            return self._legacy_provider.get_document(document_id)
        bundle = self._postgres_bundle_or_fallback()
        if bundle is None:
            return self._legacy_provider.get_document(document_id)
        document_repository, _projection_repository = bundle
        try:
            document = document_repository.get_document(document_id)
        except Exception:
            self._raise_if_fail_closed("repository_unavailable")
            return self._legacy_provider.get_document(document_id)
        if document is None:
            return None
        if not _is_api_document(document):
            return None
        return _document_record_from_postgres(document)

    def _postgres_bundle_or_fallback(self) -> tuple[Any, Any] | None:
        dsn = self._config.control_plane.postgres_dsn.strip()
        if not dsn:
            self._raise_if_fail_closed("missing_dsn")
            return None
        try:
            bundle = self._postgres_bundle(dsn)
        except Exception:
            self._raise_if_fail_closed("connection_unavailable")
            return None
        try:
            documents_ready = self._documents_ready(bundle[1])
        except Exception:
            self._raise_if_fail_closed("readiness_unavailable")
            return None
        if not documents_ready:
            self._raise_if_fail_closed("scoped_readiness_blocked")
            return None
        return bundle

    def _postgres_bundle(self, dsn: str) -> tuple[Any, Any]:
        if (
            self._engine is None
            or self._document_repository is None
            or self._projection_repository is None
        ):
            from tradingx.persistence import postgres

            settings = postgres.settings_from_control_plane(self._config)
            engine = self._engine_factory(settings)
            document_repository = self._document_repository_factory(engine, dsn)
            projection_repository = self._projection_repository_factory(engine, dsn)
            self._engine = engine
            self._document_repository = document_repository
            self._projection_repository = projection_repository
        return self._document_repository, self._projection_repository

    def _documents_ready(self, projection_repository: Any) -> bool:
        statuses = projection_repository.list_projection_source_statuses("documents")
        readiness = document_projectors.documents_route_readiness_from_source_statuses(
            source_statuses=tuple(statuses),
            evaluated_at_utc=_aware_utc(self._clock()),
        )
        return readiness.ready_for_postgres

    def _raise_if_fail_closed(self, reason: str) -> None:
        if self._mode.fail_closed:
            raise DocumentsPostgresUnavailable(reason=reason)


def build_documents_route_provider(
    *,
    config: TradingConfig,
    read_model: Any,
    engine_factory: Callable[[Any], Engine] | None = None,
    document_repository_factory: Callable[[Engine, str], Any] | None = None,
    projection_repository_factory: Callable[[Engine, str], Any] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> DocumentsRouteProvider:
    legacy_provider = _LegacyDocumentsRouteProvider(read_model)
    mode = _documents_route_mode(config)
    if not mode.use_postgres:
        return legacy_provider

    from tradingx.persistence import postgres
    from tradingx.persistence.repositories.postgres import (
        PostgresControlPlaneRepository,
    )
    from tradingx.persistence.repositories.projection_state import (
        PostgresProjectionStateRepository,
    )

    return _ConfiguredDocumentsRouteProvider(
        config=config,
        legacy_provider=legacy_provider,
        mode=mode,
        engine_factory=engine_factory or postgres.build_postgres_engine,
        document_repository_factory=(
            document_repository_factory
            or (
                lambda engine, dsn: PostgresControlPlaneRepository(
                    engine=engine,
                    dsn=dsn,
                )
            )
        ),
        projection_repository_factory=(
            projection_repository_factory
            or (
                lambda engine, dsn: PostgresProjectionStateRepository(
                    engine=engine,
                    dsn=dsn,
                )
            )
        ),
        clock=clock or (lambda: datetime.now(UTC)),
    )


def _documents_route_mode(config: TradingConfig) -> _RouteMode:
    domain_stores = dict(config.control_plane.domain_stores)
    documents_override = domain_stores.get("documents")
    if documents_override == "legacy":
        return _RouteMode(use_postgres=False, fail_closed=False)

    fail_closed = (
        config.control_plane.postgres_required
        or config.control_plane.store == "postgres"
    )
    if documents_override == "postgres":
        return _RouteMode(use_postgres=True, fail_closed=fail_closed)
    if config.control_plane.store == "postgres":
        return _RouteMode(use_postgres=True, fail_closed=True)
    if config.control_plane.store == "hybrid":
        return _RouteMode(
            use_postgres=True,
            fail_closed=config.control_plane.postgres_required,
        )
    if config.control_plane.postgres_required:
        return _RouteMode(use_postgres=True, fail_closed=True)
    return _RouteMode(use_postgres=False, fail_closed=False)


def _document_record_from_postgres(
    document: repositories.DocumentReadRecord,
) -> DocumentRecord:
    return DocumentRecord(
        doc_id=document.document_id,
        title=document.title,
        path=Path(document.logical_retrieval_ref),
        preview=document.preview,
        kind=document.document_kind,
    )


def _drain_document_pages(
    repository: Any,
) -> tuple[repositories.DocumentReadRecord, ...]:
    documents: list[repositories.DocumentReadRecord] = []
    page = repository.list_documents(page=None)
    documents.extend(page.items)
    seen_cursors: set[str] = set()
    next_cursor = page.next_cursor
    while next_cursor:
        if next_cursor in seen_cursors:
            raise RuntimeError("Document repository returned a repeated cursor.")
        seen_cursors.add(next_cursor)
        page = repository.list_documents(
            page=repositories.PageRequest(cursor=next_cursor)
        )
        documents.extend(page.items)
        next_cursor = page.next_cursor
    return tuple(documents)


def _scoped_api_documents(
    documents: tuple[repositories.DocumentReadRecord, ...],
) -> tuple[repositories.DocumentReadRecord, ...]:
    return tuple(document for document in documents if _is_api_document(document))


def _is_api_document(document: repositories.DocumentReadRecord) -> bool:
    source_family = document.metadata.get("source_family")
    return (
        isinstance(source_family, str)
        and source_family in _DOCUMENT_API_SOURCE_FAMILIES
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = (
    "DocumentsPostgresUnavailable",
    "DocumentsRouteProvider",
    "build_documents_route_provider",
)
