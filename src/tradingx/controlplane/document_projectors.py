"""Documents projector orchestration for legacy bridge outbox events."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from tradingx.controlplane import projections, repositories
from tradingx.controlplane.legacy_bridge import (
    bridge_source_requirements,
    document_api_source_families,
)

DOCUMENTS_DOMAIN_NAME = "documents"
DOCUMENTS_MAPPER_VERSION = "v1"
DOCUMENTS_SOURCE_REGISTRY_VERSION = "legacy-bridge-documents-projector-v1"


class ProjectionStateRepository(
    repositories.OutboxProjectionReadBoundary,
    repositories.ProjectionCheckpointBoundary,
    repositories.ProjectionSourceStatusBoundary,
    Protocol,
):
    def list_projection_source_statuses(
        self,
        domain_name: str,
    ) -> tuple[repositories.ProjectionSourceStatusRecord, ...]: ...


class DocumentProjectionRepository(repositories.DocumentProjectionWriteRepository):
    pass


class DocumentsProjectorUnitOfWork(Protocol):
    @contextmanager
    def transaction(
        self,
    ) -> Iterator[tuple[ProjectionStateRepository, DocumentProjectionRepository]]: ...


@dataclass(frozen=True)
class OutboxCursor:
    created_at_utc: datetime
    outbox_event_id: str


@dataclass(frozen=True)
class DocumentsProjectionFamilyResult:
    consumed_event_count: int
    projected_event_count: int
    skipped_event_count: int
    advanced_source_count: int
    checkpoint_names: tuple[str, ...]


@dataclass(frozen=True)
class DocumentsProjectionBatchResult:
    consumed_event_count: int
    projected_event_count: int
    skipped_event_count: int
    advanced_source_count: int
    checkpoint_names: tuple[str, ...]
    scoped_readiness: projections.ProjectionReadinessReport


class DocumentsProjector:
    def __init__(
        self,
        *,
        unit_of_work: DocumentsProjectorUnitOfWork,
        clock: Callable[[], datetime] | None = None,
        mapper_version: str = DOCUMENTS_MAPPER_VERSION,
        source_registry_version: str = DOCUMENTS_SOURCE_REGISTRY_VERSION,
        outbox_dedupe_constraint_present: bool = True,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock or (lambda: datetime.now(UTC))
        self._mapper_version = mapper_version
        self._source_registry_version = source_registry_version
        self._outbox_dedupe_constraint_present = outbox_dedupe_constraint_present

    def run_once(self, *, batch_size: int = 250) -> DocumentsProjectionBatchResult:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")

        with self._unit_of_work.transaction() as (projection_repo, document_repo):
            consumed = 0
            projected = 0
            skipped = 0
            advanced = 0
            checkpoint_names: list[str] = []
            for source_family in document_api_source_families():
                result = self._run_family_once(
                    projection_repo=projection_repo,
                    document_repo=document_repo,
                    source_family=source_family,
                    batch_size=batch_size,
                )
                consumed += result.consumed_event_count
                projected += result.projected_event_count
                skipped += result.skipped_event_count
                advanced += result.advanced_source_count
                checkpoint_names.extend(result.checkpoint_names)

            readiness = documents_route_readiness_from_source_statuses(
                source_statuses=projection_repo.list_projection_source_statuses(
                    DOCUMENTS_DOMAIN_NAME
                ),
                evaluated_at_utc=_aware_utc(self._clock()),
                source_registry_version=self._source_registry_version,
                outbox_dedupe_constraint_present=(
                    self._outbox_dedupe_constraint_present
                ),
            )
            return DocumentsProjectionBatchResult(
                consumed_event_count=consumed,
                projected_event_count=projected,
                skipped_event_count=skipped,
                advanced_source_count=advanced,
                checkpoint_names=tuple(checkpoint_names),
                scoped_readiness=readiness,
            )

    def _run_family_once(
        self,
        *,
        projection_repo: ProjectionStateRepository,
        document_repo: DocumentProjectionRepository,
        source_family: str,
        batch_size: int,
    ) -> DocumentsProjectionFamilyResult:
        projection_name = document_projection_name(
            domain_name=DOCUMENTS_DOMAIN_NAME,
            source_family=source_family,
            mapper_version=self._mapper_version,
        )
        checkpoint = projection_repo.load_projection_checkpoint(projection_name)
        cursor = _cursor_from_checkpoint(
            checkpoint,
            projection_repo=projection_repo,
        )
        events = projection_repo.list_outbox_events_after(
            cursor_created_at_utc=(
                None if cursor is None else cursor.created_at_utc
            ),
            cursor_outbox_event_id=None if cursor is None else cursor.outbox_event_id,
            aggregate_types=(DOCUMENTS_DOMAIN_NAME,),
            source_families=(source_family,),
            batch_size=batch_size,
        )

        projected = 0
        skipped = 0
        advanced = 0
        last_event: repositories.OutboxProjectionEvent | None = None
        for event in events:
            last_event = event
            action = self._project_event(
                event=event,
                document_repo=document_repo,
            )
            if action == "skipped":
                skipped += 1
                continue
            projected += 1
            if _advance_projected_source_status(
                event=event,
                projection_name=projection_name,
                projection_repo=projection_repo,
                mapper_version=self._mapper_version,
                projected_at_utc=_aware_utc(self._clock()),
            ):
                advanced += 1

        if last_event is not None:
            projection_repo.save_projection_checkpoint(
                repositories.ProjectionCheckpointRecord(
                    projection_name=projection_name,
                    last_outbox_event_id=last_event.outbox_event_id,
                    last_processed_at_utc=_aware_utc(self._clock()),
                    source_watermark=_checkpoint_source_watermark(
                        event=last_event,
                        projection_repo=projection_repo,
                    ),
                    last_source_observed_at_utc=last_event.occurred_at_utc,
                    lag_seconds=_lag_seconds(
                        last_event.occurred_at_utc,
                        _aware_utc(self._clock()),
                    ),
                    status="caught_up" if len(events) < batch_size else "running",
                    metadata={
                        "cursor_created_at_utc": (
                            last_event.created_at_utc.isoformat()
                        ),
                        "cursor_outbox_event_id": last_event.outbox_event_id,
                        "last_projected_dedupe_key": last_event.dedupe_key,
                        "supported_source_families": (source_family,),
                        "mapper_version": self._mapper_version,
                    },
                )
            )

        return DocumentsProjectionFamilyResult(
            consumed_event_count=len(events),
            projected_event_count=projected,
            skipped_event_count=skipped,
            advanced_source_count=advanced,
            checkpoint_names=(projection_name,) if last_event is not None else (),
        )

    def _project_event(
        self,
        *,
        event: repositories.OutboxProjectionEvent,
        document_repo: DocumentProjectionRepository,
    ) -> str:
        payload = _payload_mapping(event.payload, "payload")
        event_kind = str(payload.get("document_event_kind") or "")
        if event_kind == "file_observed":
            self._project_file_observed(event=event, document_repo=document_repo)
            return "projected"
        if event_kind == "inventory_snapshot":
            self._project_inventory_snapshot(event=event, document_repo=document_repo)
            return "projected"
        return "skipped"

    def _project_file_observed(
        self,
        *,
        event: repositories.OutboxProjectionEvent,
        document_repo: DocumentProjectionRepository,
    ) -> None:
        document_payload = _payload_mapping(event.payload, "payload")
        document_id = _required_payload_str(document_payload, "document_id")
        revision_id = _document_revision_id(event, document_id)
        existing = document_repo.get_document_revision(revision_id)
        revision_number = (
            existing.revision_number
            if existing is not None
            else document_repo.allocate_document_revision_number(
                document_id,
                revision_id,
            )
        )
        document = document_from_outbox_event(
            event,
            revision_number=revision_number,
            mapper_version=self._mapper_version,
        )
        revision = document_revision_from_outbox_event(
            event,
            revision_number=revision_number,
            document_revision_id=revision_id,
            mapper_version=self._mapper_version,
        )
        document_repo.upsert_document_revision(document, revision)
        document_repo.replace_document_object_refs(
            revision.document_revision_id,
            (
                document_object_ref_from_outbox_event(
                    event,
                    document_revision_id=revision.document_revision_id,
                    mapper_version=self._mapper_version,
                ),
            ),
        )

    def _project_inventory_snapshot(
        self,
        *,
        event: repositories.OutboxProjectionEvent,
        document_repo: DocumentProjectionRepository,
    ) -> None:
        payload = _payload_mapping(event.payload, "payload")
        active_ids = tuple(str(item) for item in payload.get("active_document_ids", ()))
        document_repo.tombstone_documents_absent_from_inventory_with_revisions(
            source_family=_payload_str(event.payload, "source_family"),
            active_document_ids=active_ids,
            tombstoned_at_utc=_aware_utc(event.occurred_at_utc),
            source_ref=_payload_str(event.payload, "source_ref"),
            metadata={
                **_source_metadata(event, mapper_version=self._mapper_version),
                "document_state": "tombstoned",
                "inventory_active_set_hash": _canonical_hash(active_ids),
                "inventory_event_id": event.outbox_event_id,
            },
            inventory_cursor_created_at_utc=event.created_at_utc,
            inventory_outbox_event_id=event.outbox_event_id,
        )


def document_projection_name(
    *,
    domain_name: str,
    source_family: str,
    mapper_version: str = DOCUMENTS_MAPPER_VERSION,
) -> str:
    return f"documents_projection:{domain_name}:{source_family}:{mapper_version}"


def document_from_outbox_event(
    event: repositories.OutboxProjectionEvent,
    *,
    revision_number: int,
    mapper_version: str = DOCUMENTS_MAPPER_VERSION,
) -> repositories.DocumentProjectionDocument:
    payload = _payload_mapping(event.payload, "payload")
    document_id = _required_payload_str(payload, "document_id")
    logical_ref = _required_payload_str(payload, "logical_retrieval_ref")
    metadata = {
        **_source_metadata(event, mapper_version=mapper_version),
        "document_state": "active",
        "content_hash": _required_payload_str(payload, "content_hash"),
        "internal_document_key": _payload_str(payload, "internal_document_key"),
        "latest_active_outbox_created_at_utc": event.created_at_utc.isoformat(),
        "latest_active_outbox_event_id": event.outbox_event_id,
        "logical_retrieval_ref": logical_ref,
        "preview": _payload_str(payload, "preview"),
        "relative_path": _payload_str(payload, "relative_path"),
        "revision_number": revision_number,
    }
    return repositories.DocumentProjectionDocument(
        document_id=document_id,
        document_kind=_required_payload_str(payload, "document_kind"),
        title=_required_payload_str(payload, "title"),
        preview=_payload_str(payload, "preview"),
        logical_retrieval_ref=logical_ref,
        document_state="active",
        created_at_utc=_aware_utc(event.occurred_at_utc),
        updated_at_utc=_aware_utc(event.occurred_at_utc),
        source_ref=_payload_str(event.payload, "source_ref"),
        metadata=metadata,
    )


def document_revision_from_outbox_event(
    event: repositories.OutboxProjectionEvent,
    *,
    revision_number: int,
    document_revision_id: str | None = None,
    mapper_version: str = DOCUMENTS_MAPPER_VERSION,
) -> repositories.DocumentProjectionRevision:
    payload = _payload_mapping(event.payload, "payload")
    document_id = _required_payload_str(payload, "document_id")
    return repositories.DocumentProjectionRevision(
        document_revision_id=document_revision_id
        or _document_revision_id(event, document_id),
        document_id=document_id,
        revision_number=revision_number,
        created_at_utc=_aware_utc(event.occurred_at_utc),
        source_ref=_payload_str(event.payload, "source_ref"),
        metadata={
            **_source_metadata(event, mapper_version=mapper_version),
            "content_hash": _required_payload_str(payload, "content_hash"),
            "content_text": _payload_str(payload, "content_text"),
            "document_state": "active",
        },
    )


def document_object_ref_from_outbox_event(
    event: repositories.OutboxProjectionEvent,
    *,
    document_revision_id: str,
    mapper_version: str = DOCUMENTS_MAPPER_VERSION,
) -> repositories.DocumentProjectionObjectRef:
    payload = _payload_mapping(event.payload, "payload")
    logical_ref = _required_payload_str(payload, "logical_retrieval_ref")
    return repositories.DocumentProjectionObjectRef(
        document_object_ref_id=_document_object_ref_id(
            document_revision_id,
            logical_ref,
        ),
        document_revision_id=document_revision_id,
        object_uri=logical_ref,
        content_type="text/markdown",
        sha256_hash=_payload_str(payload, "content_hash"),
        metadata={
            **_source_metadata(event, mapper_version=mapper_version),
            "relative_path": _payload_str(payload, "relative_path"),
        },
    )


def documents_route_readiness_from_source_statuses(
    *,
    source_statuses: tuple[repositories.ProjectionSourceStatusRecord, ...],
    evaluated_at_utc: datetime,
    source_registry_version: str = DOCUMENTS_SOURCE_REGISTRY_VERSION,
    outbox_dedupe_constraint_present: bool = True,
) -> projections.ProjectionReadinessReport:
    source_families = set(document_api_source_families())
    requirements = tuple(
        requirement
        for requirement in bridge_source_requirements(
            source_registry_version=source_registry_version,
            max_freshness_seconds=120,
        )
        if requirement.domain_name == DOCUMENTS_DOMAIN_NAME
        and requirement.source_family in source_families
    )
    return projections.evaluate_projection_readiness(
        domain_name=DOCUMENTS_DOMAIN_NAME,
        requirements=requirements,
        source_statuses=source_statuses,
        evaluated_at_utc=_aware_utc(evaluated_at_utc),
        source_registry_version=source_registry_version,
        outbox_dedupe_constraint_present=outbox_dedupe_constraint_present,
    )


def _advance_projected_source_status(
    *,
    event: repositories.OutboxProjectionEvent,
    projection_name: str,
    projection_repo: ProjectionStateRepository,
    mapper_version: str,
    projected_at_utc: datetime,
) -> bool:
    domain_name = _payload_str(event.payload, "domain_name")
    source_family = _payload_str(event.payload, "source_family")
    source_identity = _payload_str(event.payload, "source_identity")
    status = projection_repo.get_projection_source_status(
        domain_name=domain_name,
        source_family=source_family,
        source_identity=source_identity,
    )
    if status is None:
        return False

    source_event_id = _payload_str(event.payload, "source_event_id")
    projected_watermark = status.projected_watermark
    if source_event_id == status.metadata.get("latest_source_event_id"):
        projected_watermark = status.source_watermark

    projection_repo.upsert_projection_source_status(
        repositories.ProjectionSourceStatusRecord(
            domain_name=status.domain_name,
            source_family=status.source_family,
            source_identity=status.source_identity,
            source_watermark=status.source_watermark,
            projected_watermark=projected_watermark,
            lag_seconds=status.lag_seconds,
            is_mutable=status.is_mutable,
            ready_for_postgres=status.ready_for_postgres,
            checked_at_utc=status.checked_at_utc,
            metadata={
                **dict(status.metadata),
                "last_projected_outbox_event_id": event.outbox_event_id,
                "last_projected_dedupe_key": event.dedupe_key,
                "mapper_version": mapper_version,
                "projection_name": projection_name,
                "projected_at_utc": projected_at_utc.isoformat(),
            },
        )
    )
    return True


def _checkpoint_source_watermark(
    *,
    event: repositories.OutboxProjectionEvent,
    projection_repo: ProjectionStateRepository,
) -> str:
    status = projection_repo.get_projection_source_status(
        domain_name=_payload_str(event.payload, "domain_name"),
        source_family=_payload_str(event.payload, "source_family"),
        source_identity=_payload_str(event.payload, "source_identity"),
    )
    if (
        status is not None
        and _payload_str(event.payload, "source_event_id")
        == status.metadata.get("latest_source_event_id")
    ):
        return status.source_watermark or ""
    return _payload_str(event.payload, "source_watermark")


def _cursor_from_checkpoint(
    checkpoint: repositories.ProjectionCheckpointRecord | None,
    *,
    projection_repo: ProjectionStateRepository,
) -> OutboxCursor | None:
    if checkpoint is None:
        return None
    created_raw = checkpoint.metadata.get("cursor_created_at_utc")
    event_id = checkpoint.metadata.get("cursor_outbox_event_id")
    if created_raw is None or event_id is None:
        if checkpoint.last_outbox_event_id is None:
            return None
        resolved = projection_repo.get_outbox_event_cursor(
            checkpoint.last_outbox_event_id
        )
        if resolved is not None:
            return OutboxCursor(
                created_at_utc=_aware_utc(resolved[0]),
                outbox_event_id=resolved[1],
            )
        raise RuntimeError(
            "Projection checkpoint is missing ordered outbox cursor metadata."
        )
    return OutboxCursor(
        created_at_utc=_aware_utc(datetime.fromisoformat(str(created_raw))),
        outbox_event_id=str(event_id),
    )


def _source_metadata(
    event: repositories.OutboxProjectionEvent,
    *,
    mapper_version: str = DOCUMENTS_MAPPER_VERSION,
) -> Mapping[str, Any]:
    return {
        "outbox_event_id": event.outbox_event_id,
        "dedupe_key": event.dedupe_key,
        "domain_name": _payload_str(event.payload, "domain_name"),
        "source_family": _payload_str(event.payload, "source_family"),
        "source_identity": _payload_str(event.payload, "source_identity"),
        "source_event_id": _payload_str(event.payload, "source_event_id"),
        "source_watermark": _payload_str(event.payload, "source_watermark"),
        "source_ref": _payload_str(event.payload, "source_ref"),
        "mapper_version": mapper_version,
    }


def _document_revision_id(
    event: repositories.OutboxProjectionEvent,
    document_id: str,
) -> str:
    return _stable_id(
        "document-revision",
        document_id,
        _payload_str(event.payload, "source_family"),
        _payload_str(event.payload, "source_identity"),
        _payload_str(event.payload, "source_event_id"),
    )


def _document_object_ref_id(document_revision_id: str, object_uri: str) -> str:
    return _stable_id("document-object-ref", document_revision_id, object_uri)


def _payload_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, Mapping) else {}


def _payload_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    return "" if value is None else str(value)


def _required_payload_str(payload: Mapping[str, Any], key: str) -> str:
    value = _payload_str(payload, key).strip()
    if not value:
        raise ValueError(f"document event payload field {key!r} is required")
    return value


def _stable_id(prefix: str, *parts: object) -> str:
    raw = json.dumps(tuple(str(part) for part in parts), separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _lag_seconds(start: datetime, end: datetime) -> int:
    return max(0, int((_aware_utc(end) - _aware_utc(start)).total_seconds()))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = (
    "DOCUMENTS_DOMAIN_NAME",
    "DOCUMENTS_MAPPER_VERSION",
    "DOCUMENTS_SOURCE_REGISTRY_VERSION",
    "DocumentsProjectionBatchResult",
    "DocumentsProjectionFamilyResult",
    "DocumentsProjector",
    "document_from_outbox_event",
    "document_object_ref_from_outbox_event",
    "document_projection_name",
    "document_revision_from_outbox_event",
    "documents_route_readiness_from_source_statuses",
)
