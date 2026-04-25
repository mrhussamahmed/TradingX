"""Postgres write repository for document projector materialization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import text

from tradingx.controlplane import repositories

T = TypeVar("T")


class PostgresDocumentProjectionRepository:
    """SQL-backed writer for projected document tables."""

    def __init__(
        self,
        *,
        engine: Any,
        dsn: str,
        connection: Any | None = None,
    ) -> None:
        self.engine = engine
        self._dsn = dsn
        self._connection = connection

    def get_document_revision(
        self,
        document_revision_id: str,
    ) -> repositories.DocumentProjectionRevision | None:
        def read(connection: Any) -> repositories.DocumentProjectionRevision | None:
            row = _load_revision_by_id(
                connection,
                document_revision_id=document_revision_id,
            )
            return None if row is None else _revision_from_row(row)

        return self._write("get document revision", read)

    def allocate_document_revision_number(
        self,
        document_id: str,
        document_revision_id: str,
    ) -> int:
        def allocate(connection: Any) -> int:
            return _allocate_document_revision_number(
                connection,
                document_id=document_id,
                document_revision_id=document_revision_id,
            )

        return self._write("allocate document revision number", allocate)

    def upsert_document_revision(
        self,
        document: repositories.DocumentProjectionDocument,
        revision: repositories.DocumentProjectionRevision,
    ) -> None:
        if document.document_id != revision.document_id:
            raise ValueError("document and revision document_id must match")

        def write(connection: Any) -> None:
            existing = _load_revision_by_key(
                connection,
                document_id=revision.document_id,
                revision_number=revision.revision_number,
            )
            if existing is not None:
                if not _revision_row_matches(existing, revision):
                    raise repositories.RepositoryConflictError(
                        "Document revision projection conflict for "
                        f"{revision.revision_key!r} in "
                        f"{repositories.redact_dsn(self._dsn)}."
                    )
                latest_revision_number = _load_latest_revision_number(
                    connection,
                    document.document_id,
                )
                if latest_revision_number == revision.revision_number:
                    existing_document = _load_document_by_id(
                        connection,
                        document.document_id,
                    )
                    if _document_row_matches(existing_document, document):
                        return
                    if _document_row_is_later_tombstone(
                        existing_document,
                        document,
                    ):
                        return
                    raise repositories.RepositoryConflictError(
                        "Document projection summary conflict for "
                        f"{document.document_id!r} revision "
                        f"{revision.revision_number!r} in "
                        f"{repositories.redact_dsn(self._dsn)}."
                    )
                if latest_revision_number is not None and (
                    latest_revision_number > revision.revision_number
                ):
                    existing_document = _load_document_by_id(
                        connection,
                        document.document_id,
                    )
                    if _document_row_is_later_tombstone(
                        existing_document,
                        document,
                    ):
                        return
                    if _document_row_is_tombstoned_active_replay(
                        existing_document,
                        document,
                    ):
                        raise repositories.RepositoryConflictError(
                            "Document projection summary conflict for "
                            f"{document.document_id!r} revision "
                            f"{revision.revision_number!r} in "
                            f"{repositories.redact_dsn(self._dsn)}."
                        )
                return

            latest_revision_number = _load_latest_revision_number(
                connection,
                document.document_id,
            )
            if (
                latest_revision_number is None
                or revision.revision_number >= latest_revision_number
            ):
                connection.execute(
                    text(
                        """
                        INSERT INTO documents.document (
                            document_id,
                            document_type,
                            title,
                            created_at_utc,
                            updated_at_utc,
                            source_ref,
                            metadata_json
                        ) VALUES (
                            :document_id,
                            :document_type,
                            :title,
                            :created_at_utc,
                            :updated_at_utc,
                            :source_ref,
                            CAST(:metadata_json AS JSONB)
                        )
                        ON CONFLICT (document_id) DO UPDATE SET
                            document_type = EXCLUDED.document_type,
                            title = EXCLUDED.title,
                            created_at_utc = LEAST(
                                documents.document.created_at_utc,
                                EXCLUDED.created_at_utc
                            ),
                            updated_at_utc = EXCLUDED.updated_at_utc,
                            source_ref = EXCLUDED.source_ref,
                            metadata_json = EXCLUDED.metadata_json
                        """
                    ),
                    _document_params(document),
                )

            connection.execute(
                text(
                    """
                    INSERT INTO documents.document_revision (
                        document_revision_id,
                        document_id,
                        revision_number,
                        created_at_utc,
                        source_ref,
                        metadata_json
                    ) VALUES (
                        :document_revision_id,
                        :document_id,
                        :revision_number,
                        :created_at_utc,
                        :source_ref,
                        CAST(:metadata_json AS JSONB)
                    )
                    """
                ),
                _revision_params(revision),
            )

        self._write("upsert document revision", write)

    def replace_document_object_refs(
        self,
        document_revision_id: str,
        refs: tuple[repositories.DocumentProjectionObjectRef, ...],
    ) -> None:
        def replace(connection: Any) -> None:
            connection.execute(
                text(
                    """
                    DELETE FROM documents.document_object_ref
                    WHERE document_revision_id = :document_revision_id
                    """
                ),
                {"document_revision_id": document_revision_id},
            )
            for ref in sorted(
                refs,
                key=lambda item: (item.object_uri, item.document_object_ref_id),
            ):
                if ref.document_revision_id != document_revision_id:
                    raise ValueError(
                        "object ref document_revision_id must match replacement key"
                    )
                connection.execute(
                    text(
                        """
                        INSERT INTO documents.document_object_ref (
                            document_object_ref_id,
                            document_revision_id,
                            object_uri,
                            content_type,
                            sha256_hash,
                            metadata_json
                        ) VALUES (
                            :document_object_ref_id,
                            :document_revision_id,
                            :object_uri,
                            :content_type,
                            :sha256_hash,
                            CAST(:metadata_json AS JSONB)
                        )
                        """
                    ),
                    _object_ref_params(ref),
                )

        self._write("replace document object refs", replace)

    def tombstone_documents_absent_from_inventory(
        self,
        *,
        source_family: str,
        active_document_ids: tuple[str, ...],
        tombstoned_at_utc: datetime,
        source_ref: str,
        metadata: Mapping[str, Any],
    ) -> tuple[str, ...]:
        active_ids = tuple(dict.fromkeys(str(item) for item in active_document_ids))

        def write(connection: Any) -> tuple[str, ...]:
            params: dict[str, Any] = {
                "source_family": source_family,
                "tombstoned_at_utc": _aware_utc(tombstoned_at_utc),
                "source_ref": source_ref,
                "metadata_json": _json_dumps(
                    {
                        **dict(metadata),
                        "document_state": "tombstoned",
                        "tombstoned_at_utc": _aware_utc(
                            tombstoned_at_utc
                        ).isoformat(),
                        "tombstone_source_ref": source_ref,
                    }
                ),
            }
            active_filter = ""
            if active_ids:
                bind_names = []
                for index, document_id in enumerate(active_ids):
                    key = f"active_document_id_{index}"
                    params[key] = document_id
                    bind_names.append(f":{key}")
                active_filter = (
                    f"AND document_id NOT IN ({', '.join(bind_names)})"
                )

            rows = connection.execute(
                text(
                    f"""
                    WITH to_tombstone AS (
                        SELECT document_id
                        FROM documents.document
                        WHERE metadata_json ->> 'source_family' = :source_family
                          AND COALESCE(
                                metadata_json ->> 'document_state',
                                'active'
                              ) = 'active'
                          {active_filter}
                        ORDER BY document_id ASC
                    ),
                    updated AS (
                        UPDATE documents.document AS document
                        SET
                            updated_at_utc = :tombstoned_at_utc,
                            source_ref = :source_ref,
                            metadata_json = (
                                COALESCE(document.metadata_json, '{{}}'::jsonb)
                                || CAST(:metadata_json AS JSONB)
                            )
                        FROM to_tombstone
                        WHERE document.document_id = to_tombstone.document_id
                        RETURNING document.document_id
                    )
                    SELECT document_id
                    FROM updated
                    ORDER BY document_id ASC
                    """
                ),
                params,
            ).mappings().all()
            return tuple(str(row["document_id"]) for row in rows)

        return self._write("tombstone documents absent from inventory", write)

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
        active_ids = tuple(dict.fromkeys(str(item) for item in active_document_ids))

        def write(connection: Any) -> tuple[str, ...]:
            candidates = _load_active_documents_for_family(
                connection,
                source_family=source_family,
                active_document_ids=active_ids,
            )
            tombstoned: list[str] = []
            for row in candidates:
                document_id = str(row["document_id"])
                _lock_document_revision_allocation(connection, document_id)
                current = _load_document_by_id(connection, document_id)
                if current is None:
                    continue
                if not _document_row_is_active_candidate(
                    current,
                    source_family=source_family,
                    active_document_ids=active_ids,
                ):
                    continue
                row_metadata = _json_mapping(current["metadata_json"])
                if _active_cursor_after_inventory(
                    row_metadata,
                    inventory_cursor_created_at_utc=inventory_cursor_created_at_utc,
                    inventory_outbox_event_id=inventory_outbox_event_id,
                ):
                    continue

                revision_id = _stable_id(
                    "document-tombstone-revision",
                    document_id,
                    source_ref,
                    metadata.get("source_event_id")
                    or metadata.get("inventory_event_id")
                    or "",
                )
                revision_number = _allocate_document_revision_number(
                    connection,
                    document_id=document_id,
                    document_revision_id=revision_id,
                )
                tombstone_metadata = {
                    **row_metadata,
                    **dict(metadata),
                    "document_state": "tombstoned",
                    "tombstoned_at_utc": _aware_utc(
                        tombstoned_at_utc
                    ).isoformat(),
                    "tombstone_source_ref": source_ref,
                }
                connection.execute(
                    text(
                        """
                        UPDATE documents.document
                        SET
                            updated_at_utc = :updated_at_utc,
                            source_ref = :source_ref,
                            metadata_json = CAST(:metadata_json AS JSONB)
                        WHERE document_id = :document_id
                        """
                    ),
                    {
                        "document_id": document_id,
                        "updated_at_utc": _aware_utc(tombstoned_at_utc),
                        "source_ref": source_ref,
                        "metadata_json": _json_dumps(tombstone_metadata),
                    },
                )
                existing = _load_revision_by_id(
                    connection,
                    document_revision_id=revision_id,
                )
                revision = repositories.DocumentProjectionRevision(
                    document_revision_id=revision_id,
                    document_id=document_id,
                    revision_number=revision_number,
                    created_at_utc=_aware_utc(tombstoned_at_utc),
                    source_ref=source_ref,
                    metadata=tombstone_metadata,
                )
                if existing is not None:
                    if not _revision_row_matches(existing, revision):
                        raise repositories.RepositoryConflictError(
                            "Document tombstone revision projection conflict for "
                            f"{revision.revision_key!r} in "
                            f"{repositories.redact_dsn(self._dsn)}."
                        )
                else:
                    connection.execute(
                        text(
                            """
                            INSERT INTO documents.document_revision (
                                document_revision_id,
                                document_id,
                                revision_number,
                                created_at_utc,
                                source_ref,
                                metadata_json
                            ) VALUES (
                                :document_revision_id,
                                :document_id,
                                :revision_number,
                                :created_at_utc,
                                :source_ref,
                                CAST(:metadata_json AS JSONB)
                            )
                            """
                        ),
                        _revision_params(revision),
                    )
                tombstoned.append(document_id)
            return tuple(tombstoned)

        return self._write(
            "tombstone documents absent from inventory with revisions",
            write,
        )

    def _write(
        self,
        operation: str,
        writer: Callable[[Any], T],
    ) -> T:
        if self._connection is not None:
            try:
                return writer(self._connection)
            except repositories.RepositoryConflictError:
                raise
            except Exception as exc:
                raise repositories.RepositoryStorageError.from_exception(
                    operation,
                    exc,
                    dsn=self._dsn,
                ) from None
        try:
            with self.engine.begin() as connection:
                return writer(connection)
        except (
            repositories.RepositoryConflictError,
            repositories.RepositoryStorageError,
        ):
            raise
        except Exception as exc:
            raise repositories.RepositoryStorageError.from_exception(
                operation,
                exc,
                dsn=self._dsn,
            ) from None


class PostgresDocumentsProjectorUnitOfWork:
    """Creates document and projection-state repository views in one transaction."""

    def __init__(
        self,
        *,
        engine: Any,
        dsn: str,
        id_provider: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.engine = engine
        self._dsn = dsn
        self._id_provider = id_provider
        self._clock = clock

    @contextmanager
    def transaction(self) -> Iterator[tuple[Any, PostgresDocumentProjectionRepository]]:
        from tradingx.persistence.repositories.projection_state import (
            PostgresProjectionStateRepository,
        )

        try:
            with self.engine.begin() as connection:
                yield (
                    PostgresProjectionStateRepository(
                        engine=self.engine,
                        dsn=self._dsn,
                        id_provider=self._id_provider,
                        clock=self._clock,
                        connection=connection,
                    ),
                    PostgresDocumentProjectionRepository(
                        engine=self.engine,
                        dsn=self._dsn,
                        connection=connection,
                    ),
                )
        except repositories.RepositoryConflictError:
            raise
        except Exception as exc:
            raise repositories.RepositoryStorageError.from_exception(
                "documents projector transaction",
                exc,
                dsn=self._dsn,
            ) from None


def _load_revision_by_id(
    connection: Any,
    *,
    document_revision_id: str,
) -> Mapping[str, Any] | None:
    row = connection.execute(
        text(
            """
            SELECT
                document_revision_id,
                document_id,
                revision_number,
                created_at_utc,
                source_ref,
                metadata_json
            FROM documents.document_revision
            WHERE document_revision_id = :document_revision_id
            """
        ),
        {"document_revision_id": document_revision_id},
    ).mappings().one_or_none()
    return None if row is None else dict(row)


def _load_revision_by_key(
    connection: Any,
    *,
    document_id: str,
    revision_number: int,
) -> Mapping[str, Any] | None:
    row = connection.execute(
        text(
            """
            SELECT
                document_revision_id,
                document_id,
                revision_number,
                created_at_utc,
                source_ref,
                metadata_json
            FROM documents.document_revision
            WHERE document_id = :document_id
              AND revision_number = :revision_number
            """
        ),
        {"document_id": document_id, "revision_number": revision_number},
    ).mappings().one_or_none()
    return None if row is None else dict(row)


def _load_latest_revision_number(connection: Any, document_id: str) -> int | None:
    value = connection.execute(
        text(
            """
            SELECT revision_number
            FROM documents.document_revision
            WHERE document_id = :document_id
            ORDER BY revision_number DESC
            LIMIT 1
            """
        ),
        {"document_id": document_id},
    ).scalar_one_or_none()
    return None if value is None else int(value)


def _load_active_documents_for_family(
    connection: Any,
    *,
    source_family: str,
    active_document_ids: tuple[str, ...],
) -> tuple[Mapping[str, Any], ...]:
    params: dict[str, Any] = {"source_family": source_family}
    active_filter = ""
    if active_document_ids:
        bind_names = []
        for index, document_id in enumerate(active_document_ids):
            key = f"active_document_id_{index}"
            params[key] = document_id
            bind_names.append(f":{key}")
        active_filter = f"AND document_id NOT IN ({', '.join(bind_names)})"

    rows = connection.execute(
        text(
            f"""
            SELECT
                document_id,
                document_type,
                title,
                updated_at_utc,
                source_ref,
                metadata_json
            FROM documents.document
            WHERE metadata_json ->> 'source_family' = :source_family
              AND COALESCE(metadata_json ->> 'document_state', 'active') = 'active'
              {active_filter}
            ORDER BY document_id ASC
            """
        ),
        params,
    ).mappings().all()
    return tuple(dict(row) for row in rows)


def _load_document_by_id(
    connection: Any,
    document_id: str,
) -> Mapping[str, Any] | None:
    row = connection.execute(
        text(
            """
            SELECT
                document_id,
                document_type,
                title,
                updated_at_utc,
                source_ref,
                metadata_json
            FROM documents.document
            WHERE document_id = :document_id
            """
        ),
        {"document_id": document_id},
    ).mappings().one_or_none()
    return None if row is None else dict(row)


def _document_row_is_active_candidate(
    row: Mapping[str, Any],
    *,
    source_family: str,
    active_document_ids: tuple[str, ...],
) -> bool:
    document_id = str(row["document_id"])
    if document_id in active_document_ids:
        return False
    metadata = _json_mapping(row["metadata_json"])
    if metadata.get("source_family") != source_family:
        return False
    return str(metadata.get("document_state", "active")) == "active"


def _document_params(
    document: repositories.DocumentProjectionDocument,
) -> dict[str, Any]:
    return {
        "document_id": document.document_id,
        "document_type": document.document_kind,
        "title": document.title,
        "created_at_utc": _aware_utc(document.created_at_utc),
        "updated_at_utc": _aware_utc(document.updated_at_utc),
        "source_ref": document.source_ref,
        "metadata_json": _json_dumps(_document_metadata(document)),
    }


def _revision_params(
    revision: repositories.DocumentProjectionRevision,
) -> dict[str, Any]:
    return {
        "document_revision_id": revision.document_revision_id,
        "document_id": revision.document_id,
        "revision_number": revision.revision_number,
        "created_at_utc": _aware_utc(revision.created_at_utc),
        "source_ref": revision.source_ref,
        "metadata_json": _json_dumps(revision.metadata),
    }


def _object_ref_params(
    ref: repositories.DocumentProjectionObjectRef,
) -> dict[str, Any]:
    return {
        "document_object_ref_id": ref.document_object_ref_id,
        "document_revision_id": ref.document_revision_id,
        "object_uri": ref.object_uri,
        "content_type": ref.content_type,
        "sha256_hash": ref.sha256_hash,
        "metadata_json": _json_dumps(ref.metadata),
    }


def _document_metadata(
    document: repositories.DocumentProjectionDocument,
) -> Mapping[str, Any]:
    return {
        **dict(document.metadata),
        "document_state": document.document_state,
        "logical_retrieval_ref": document.logical_retrieval_ref,
        "preview": document.preview,
    }


def _document_row_matches(
    row: Mapping[str, Any] | None,
    document: repositories.DocumentProjectionDocument,
) -> bool:
    if row is None:
        return False
    return {
        "document_type": row["document_type"],
        "title": row["title"],
        "updated_at_utc": _datetime(row["updated_at_utc"]),
        "source_ref": row["source_ref"],
        "metadata_json": _json_normalized(row["metadata_json"]),
    } == {
        "document_type": document.document_kind,
        "title": document.title,
        "updated_at_utc": _aware_utc(document.updated_at_utc),
        "source_ref": document.source_ref,
        "metadata_json": _json_normalized(_document_metadata(document)),
    }


def _document_row_is_later_tombstone(
    row: Mapping[str, Any] | None,
    document: repositories.DocumentProjectionDocument,
) -> bool:
    if row is None:
        return False
    existing_metadata = _json_mapping(row["metadata_json"])
    expected_metadata = _document_metadata(document)
    if existing_metadata.get("document_state") != "tombstoned":
        return False
    if expected_metadata.get("document_state") != "active":
        return False
    if row["document_type"] != document.document_kind:
        return False
    if row["title"] != document.title:
        return False
    stable_metadata_keys = (
        "content_hash",
        "internal_document_key",
        "latest_active_outbox_created_at_utc",
        "latest_active_outbox_event_id",
        "logical_retrieval_ref",
        "preview",
        "relative_path",
        "revision_number",
        "source_family",
        "source_identity",
    )
    for key in stable_metadata_keys:
        if key not in expected_metadata:
            continue
        value = expected_metadata[key]
        if _json_normalized(existing_metadata.get(key)) != _json_normalized(value):
            return False
    return True


def _document_row_is_tombstoned_active_replay(
    row: Mapping[str, Any] | None,
    document: repositories.DocumentProjectionDocument,
) -> bool:
    if row is None:
        return False
    existing_metadata = _json_mapping(row["metadata_json"])
    expected_metadata = _document_metadata(document)
    return (
        existing_metadata.get("document_state") == "tombstoned"
        and expected_metadata.get("document_state") == "active"
    )


def _revision_row_matches(
    row: Mapping[str, Any],
    revision: repositories.DocumentProjectionRevision,
) -> bool:
    return {
        "document_revision_id": row["document_revision_id"],
        "created_at_utc": _datetime(row["created_at_utc"]),
        "source_ref": row["source_ref"],
        "metadata_json": _json_normalized(row["metadata_json"]),
    } == {
        "document_revision_id": revision.document_revision_id,
        "created_at_utc": _aware_utc(revision.created_at_utc),
        "source_ref": revision.source_ref,
        "metadata_json": _json_normalized(revision.metadata),
    }


def _revision_from_row(
    row: Mapping[str, Any],
) -> repositories.DocumentProjectionRevision:
    return repositories.DocumentProjectionRevision(
        document_revision_id=str(row["document_revision_id"]),
        document_id=str(row["document_id"]),
        revision_number=int(row["revision_number"]),
        created_at_utc=_datetime(row["created_at_utc"]),
        source_ref=None if row["source_ref"] is None else str(row["source_ref"]),
        metadata=_json_mapping(row["metadata_json"]),
    )


def _active_cursor_after_inventory(
    metadata: Mapping[str, Any],
    *,
    inventory_cursor_created_at_utc: datetime | None,
    inventory_outbox_event_id: str | None,
) -> bool:
    if inventory_cursor_created_at_utc is None or inventory_outbox_event_id is None:
        return False
    created_raw = metadata.get("latest_active_outbox_created_at_utc")
    event_id = metadata.get("latest_active_outbox_event_id")
    if created_raw is None or event_id is None:
        return False
    created = _datetime(created_raw)
    inventory_created = _aware_utc(inventory_cursor_created_at_utc)
    return created > inventory_created or (
        created == inventory_created and str(event_id) > inventory_outbox_event_id
    )


def _lock_document_revision_allocation(connection: Any, document_id: str) -> None:
    connection.execute(
        text(
            """
            SELECT pg_advisory_xact_lock(
                hashtext('documents.document_revision'),
                hashtext(:document_id)
            )
            """
        ),
        {"document_id": document_id},
    )


def _allocate_document_revision_number(
    connection: Any,
    *,
    document_id: str,
    document_revision_id: str,
) -> int:
    _lock_document_revision_allocation(connection, document_id)
    existing = _load_revision_by_id(
        connection,
        document_revision_id=document_revision_id,
    )
    if existing is not None:
        return int(existing["revision_number"])
    latest = _load_latest_revision_number(connection, document_id)
    return 1 if latest is None else latest + 1


def _stable_id(prefix: str, *parts: object) -> str:
    raw = json.dumps(tuple(str(part) for part in parts), separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _json_dumps(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {"value": decoded}
    if isinstance(value, dict):
        return value
    return dict(value)


def _json_normalized(value: object) -> object:
    return json.loads(_json_dumps(value))


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    return _aware_utc(datetime.fromisoformat(str(value)))


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = (
    "PostgresDocumentProjectionRepository",
    "PostgresDocumentsProjectorUnitOfWork",
)
