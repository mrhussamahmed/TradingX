"""Postgres write repository for document projector materialization."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
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
    for key, value in expected_metadata.items():
        if key == "document_state":
            continue
        if _json_normalized(existing_metadata.get(key)) != _json_normalized(value):
            return False
    return True


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


__all__ = ("PostgresDocumentProjectionRepository",)
