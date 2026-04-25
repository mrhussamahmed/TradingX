"""Postgres projection-state repository for outbox and readiness progress."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import bindparam, text

from tradingx.controlplane import projections, repositories

T = TypeVar("T")


class PostgresProjectionStateRepository:
    """SQL-backed repository for projector outbox, checkpoint, and readiness state."""

    def __init__(
        self,
        *,
        engine: Any,
        dsn: str,
        id_provider: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        connection: Any | None = None,
    ) -> None:
        self.engine = engine
        self._dsn = dsn
        self._id_provider = id_provider or (lambda: str(uuid.uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._connection = connection

    @contextmanager
    def transaction(self) -> Iterator[PostgresProjectionStateRepository]:
        """Yield a transaction-bound repository view for atomic projector batches."""

        if self._connection is not None:
            yield self
            return

        body_error: Exception | None = None
        storage_error: repositories.RepositoryStorageError | None = None
        try:
            with self.engine.begin() as connection:
                try:
                    yield PostgresProjectionStateRepository(
                        engine=self.engine,
                        dsn=self._dsn,
                        id_provider=self._id_provider,
                        clock=self._clock,
                        connection=connection,
                    )
                except Exception as exc:
                    body_error = exc
                    raise
        except Exception as exc:
            if body_error is exc:
                raise
            storage_error = repositories.RepositoryStorageError.from_exception(
                "projection state transaction",
                exc,
                dsn=self._dsn,
            )
        if storage_error is not None:
            raise storage_error

    def append_outbox_event(
        self,
        request: repositories.OutboxEventAppendRequest,
    ) -> str:
        def append(connection: Any) -> str:
            outbox_event_id = self._id_provider()
            created_at_utc = _aware_utc(self._clock())
            inserted = connection.execute(
                text(
                    """
                    INSERT INTO system.outbox_event (
                        outbox_event_id,
                        aggregate_type,
                        aggregate_id,
                        event_type,
                        event_version,
                        occurred_at_utc,
                        dedupe_key,
                        payload_json,
                        created_at_utc,
                        published_at_utc
                    ) VALUES (
                        :outbox_event_id,
                        :aggregate_type,
                        :aggregate_id,
                        :event_type,
                        :event_version,
                        :occurred_at_utc,
                        :dedupe_key,
                        CAST(:payload_json AS JSONB),
                        :created_at_utc,
                        NULL
                    )
                    ON CONFLICT (dedupe_key) DO NOTHING
                    RETURNING outbox_event_id
                    """
                ),
                {
                    "outbox_event_id": outbox_event_id,
                    "aggregate_type": request.aggregate_type,
                    "aggregate_id": request.aggregate_id,
                    "event_type": request.event_type,
                    "event_version": request.event_version,
                    "occurred_at_utc": _aware_utc(request.occurred_at_utc),
                    "dedupe_key": request.dedupe_key,
                    "payload_json": _json_dumps(request.payload),
                    "created_at_utc": created_at_utc,
                },
            ).scalar_one_or_none()
            if inserted is not None:
                return str(inserted)

            existing = connection.execute(
                text(
                    """
                    SELECT outbox_event_id
                    FROM system.outbox_event
                    WHERE dedupe_key = :dedupe_key
                      AND aggregate_type = :aggregate_type
                      AND aggregate_id = :aggregate_id
                      AND event_type = :event_type
                      AND event_version = :event_version
                      AND occurred_at_utc = :occurred_at_utc
                      AND payload_json = CAST(:payload_json AS JSONB)
                    """
                ),
                {
                    "dedupe_key": request.dedupe_key,
                    "aggregate_type": request.aggregate_type,
                    "aggregate_id": request.aggregate_id,
                    "event_type": request.event_type,
                    "event_version": request.event_version,
                    "occurred_at_utc": _aware_utc(request.occurred_at_utc),
                    "payload_json": _json_dumps(request.payload),
                },
            ).scalar_one_or_none()
            if existing is not None:
                return str(existing)

            raise repositories.OutboxAppendConflictError.from_conflict(
                dedupe_key=request.dedupe_key,
                dsn=self._dsn,
                details=(
                    "dedupe_key already exists with different aggregate, event, "
                    "timestamp, version, or JSONB payload."
                ),
            )

        return self._write("append outbox event", append)

    def get_outbox_event_id_by_dedupe_key(self, dedupe_key: str) -> str | None:
        rows = self._query(
            "get outbox event by dedupe key",
            """
            SELECT outbox_event_id
            FROM system.outbox_event
            WHERE dedupe_key = :dedupe_key
            """,
            {"dedupe_key": dedupe_key},
        )
        return str(rows[0]["outbox_event_id"]) if rows else None

    def get_outbox_event_cursor(
        self,
        outbox_event_id: str,
    ) -> tuple[datetime, str] | None:
        rows = self._query(
            "get outbox event cursor",
            """
            SELECT created_at_utc, outbox_event_id
            FROM system.outbox_event
            WHERE outbox_event_id = :outbox_event_id
            """,
            {"outbox_event_id": outbox_event_id},
        )
        if not rows:
            return None
        return (_datetime(rows[0]["created_at_utc"]), str(rows[0]["outbox_event_id"]))

    def list_outbox_events_after(
        self,
        *,
        cursor_created_at_utc: datetime | None,
        cursor_outbox_event_id: str | None,
        aggregate_types: tuple[str, ...],
        source_families: tuple[str, ...],
        batch_size: int,
    ) -> tuple[repositories.OutboxProjectionEvent, ...]:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if not aggregate_types:
            return ()
        if not source_families:
            return ()
        if (cursor_created_at_utc is None) != (cursor_outbox_event_id is None):
            raise ValueError(
                "cursor_created_at_utc and cursor_outbox_event_id must be paired"
            )

        cursor_filter = ""
        params: dict[str, Any] = {
            "aggregate_types": tuple(aggregate_types),
            "source_families": tuple(source_families),
            "batch_size": batch_size,
        }
        if cursor_created_at_utc is not None and cursor_outbox_event_id is not None:
            cursor_filter = """
              AND (
                    created_at_utc > :cursor_created_at_utc
                    OR (
                        created_at_utc = :cursor_created_at_utc
                        AND outbox_event_id > :cursor_outbox_event_id
                    )
              )
            """
            params["cursor_created_at_utc"] = _aware_utc(cursor_created_at_utc)
            params["cursor_outbox_event_id"] = cursor_outbox_event_id

        statement = text(
            f"""
            SELECT
                outbox_event_id,
                aggregate_type,
                aggregate_id,
                event_type,
                event_version,
                occurred_at_utc,
                dedupe_key,
                payload_json,
                created_at_utc
            FROM system.outbox_event
            WHERE aggregate_type IN :aggregate_types
              AND payload_json ->> 'source_family' IN :source_families
              {cursor_filter}
            ORDER BY created_at_utc ASC, outbox_event_id ASC
            LIMIT :batch_size
            """
        ).bindparams(
            bindparam("aggregate_types", expanding=True),
            bindparam("source_families", expanding=True),
        )
        rows = self._query(
            "list outbox projection events",
            statement,
            params,
        )
        return tuple(_outbox_projection_event_from_row(row) for row in rows)

    def load_projection_checkpoint(
        self,
        projection_name: str,
    ) -> repositories.ProjectionCheckpointRecord | None:
        rows = self._query(
            "load projection checkpoint",
            """
            SELECT
                projection_name,
                last_outbox_event_id,
                last_processed_at_utc,
                source_watermark,
                last_source_observed_at_utc,
                lag_seconds,
                status,
                metadata_json
            FROM system.projection_checkpoint
            WHERE projection_name = :projection_name
            """,
            {"projection_name": projection_name},
        )
        return _checkpoint_from_row(rows[0]) if rows else None

    def save_projection_checkpoint(
        self,
        record: repositories.ProjectionCheckpointRecord,
    ) -> None:
        self._write(
            "save projection checkpoint",
            lambda connection: connection.execute(
                text(
                    """
                    INSERT INTO system.projection_checkpoint (
                        projection_name,
                        last_outbox_event_id,
                        last_processed_at_utc,
                        source_watermark,
                        last_source_observed_at_utc,
                        lag_seconds,
                        status,
                        metadata_json
                    ) VALUES (
                        :projection_name,
                        :last_outbox_event_id,
                        :last_processed_at_utc,
                        :source_watermark,
                        :last_source_observed_at_utc,
                        :lag_seconds,
                        :status,
                        CAST(:metadata_json AS JSONB)
                    )
                    ON CONFLICT (projection_name) DO UPDATE SET
                        last_outbox_event_id = EXCLUDED.last_outbox_event_id,
                        last_processed_at_utc = EXCLUDED.last_processed_at_utc,
                        source_watermark = EXCLUDED.source_watermark,
                        last_source_observed_at_utc =
                            EXCLUDED.last_source_observed_at_utc,
                        lag_seconds = EXCLUDED.lag_seconds,
                        status = EXCLUDED.status,
                        metadata_json = EXCLUDED.metadata_json
                    """
                ),
                {
                    "projection_name": record.projection_name,
                    "last_outbox_event_id": record.last_outbox_event_id,
                    "last_processed_at_utc": _optional_aware_utc(
                        record.last_processed_at_utc
                    ),
                    "source_watermark": record.source_watermark,
                    "last_source_observed_at_utc": _optional_aware_utc(
                        record.last_source_observed_at_utc
                    ),
                    "lag_seconds": record.lag_seconds,
                    "status": record.status,
                    "metadata_json": _json_dumps(record.metadata),
                },
            ),
        )

    def get_projection_source_status(
        self,
        *,
        domain_name: str,
        source_family: str,
        source_identity: str,
    ) -> repositories.ProjectionSourceStatusRecord | None:
        rows = self._query(
            "get projection source status",
            """
            SELECT
                domain_name,
                source_family,
                source_identity,
                source_watermark,
                projected_watermark,
                lag_seconds,
                is_mutable,
                ready_for_postgres,
                checked_at_utc,
                metadata_json
            FROM system.domain_projection_source_status
            WHERE domain_name = :domain_name
              AND source_family = :source_family
              AND source_identity = :source_identity
            """,
            {
                "domain_name": domain_name,
                "source_family": source_family,
                "source_identity": source_identity,
            },
        )
        return _source_status_from_row(rows[0]) if rows else None

    def list_projection_source_statuses(
        self,
        domain_name: str,
    ) -> tuple[repositories.ProjectionSourceStatusRecord, ...]:
        rows = self._query(
            "list projection source statuses",
            """
            SELECT
                domain_name,
                source_family,
                source_identity,
                source_watermark,
                projected_watermark,
                lag_seconds,
                is_mutable,
                ready_for_postgres,
                checked_at_utc,
                metadata_json
            FROM system.domain_projection_source_status
            WHERE domain_name = :domain_name
            ORDER BY source_family ASC, source_identity ASC
            """,
            {"domain_name": domain_name},
        )
        return tuple(_source_status_from_row(row) for row in rows)

    def upsert_projection_source_status(
        self,
        record: repositories.ProjectionSourceStatusRecord,
    ) -> None:
        self._write(
            "upsert projection source status",
            lambda connection: connection.execute(
                text(
                    """
                    INSERT INTO system.domain_projection_source_status (
                        domain_name,
                        source_family,
                        source_identity,
                        source_watermark,
                        projected_watermark,
                        lag_seconds,
                        is_mutable,
                        ready_for_postgres,
                        checked_at_utc,
                        metadata_json
                    ) VALUES (
                        :domain_name,
                        :source_family,
                        :source_identity,
                        :source_watermark,
                        :projected_watermark,
                        :lag_seconds,
                        :is_mutable,
                        :ready_for_postgres,
                        :checked_at_utc,
                        CAST(:metadata_json AS JSONB)
                    )
                    ON CONFLICT (
                        domain_name,
                        source_family,
                        source_identity
                    ) DO UPDATE SET
                        source_watermark = EXCLUDED.source_watermark,
                        projected_watermark = EXCLUDED.projected_watermark,
                        lag_seconds = EXCLUDED.lag_seconds,
                        is_mutable = EXCLUDED.is_mutable,
                        ready_for_postgres = EXCLUDED.ready_for_postgres,
                        checked_at_utc = EXCLUDED.checked_at_utc,
                        metadata_json = EXCLUDED.metadata_json
                    """
                ),
                {
                    "domain_name": record.domain_name,
                    "source_family": record.source_family,
                    "source_identity": record.source_identity,
                    "source_watermark": record.source_watermark,
                    "projected_watermark": record.projected_watermark,
                    "lag_seconds": record.lag_seconds,
                    "is_mutable": record.is_mutable,
                    "ready_for_postgres": record.ready_for_postgres,
                    "checked_at_utc": _aware_utc(record.checked_at_utc),
                    "metadata_json": _json_dumps(record.metadata),
                },
            ),
        )

    def save_domain_projection_status_from_readiness(
        self,
        report: projections.ProjectionReadinessReport,
    ) -> repositories.ProjectionStatusSummary:
        summary = projections.projection_status_from_readiness(report)
        self.save_domain_projection_status(summary)
        return summary

    def save_domain_projection_status(
        self,
        summary: repositories.ProjectionStatusSummary,
    ) -> None:
        self._write(
            "save domain projection status",
            lambda connection: connection.execute(
                text(
                    """
                    INSERT INTO system.domain_projection_status (
                        domain_name,
                        target_store,
                        bridge_status,
                        projection_status,
                        source_watermark,
                        last_projected_outbox_event_id,
                        lag_seconds,
                        ready_for_postgres,
                        checked_at_utc,
                        metadata_json
                    ) VALUES (
                        :domain_name,
                        :target_store,
                        :bridge_status,
                        :projection_status,
                        :source_watermark,
                        :last_projected_outbox_event_id,
                        :lag_seconds,
                        :ready_for_postgres,
                        :checked_at_utc,
                        CAST(:metadata_json AS JSONB)
                    )
                    ON CONFLICT (domain_name) DO UPDATE SET
                        target_store = EXCLUDED.target_store,
                        bridge_status = EXCLUDED.bridge_status,
                        projection_status = EXCLUDED.projection_status,
                        source_watermark = EXCLUDED.source_watermark,
                        last_projected_outbox_event_id =
                            EXCLUDED.last_projected_outbox_event_id,
                        lag_seconds = EXCLUDED.lag_seconds,
                        ready_for_postgres = EXCLUDED.ready_for_postgres,
                        checked_at_utc = EXCLUDED.checked_at_utc,
                        metadata_json = EXCLUDED.metadata_json
                    """
                ),
                {
                    "domain_name": summary.domain_name,
                    "target_store": summary.target_store,
                    "bridge_status": summary.bridge_status,
                    "projection_status": summary.projection_status,
                    "source_watermark": summary.source_watermark,
                    "last_projected_outbox_event_id": (
                        summary.last_projected_outbox_event_id
                    ),
                    "lag_seconds": summary.lag_seconds,
                    "ready_for_postgres": summary.ready_for_postgres,
                    "checked_at_utc": _aware_utc(summary.checked_at_utc),
                    "metadata_json": _json_dumps(summary.metadata),
                },
            ),
        )

    def _query(
        self,
        operation: str,
        sql: Any,
        params: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], ...]:
        def query(connection: Any) -> tuple[Mapping[str, Any], ...]:
            statement = text(sql) if isinstance(sql, str) else sql
            rows = connection.execute(statement, dict(params)).mappings().all()
            return tuple(dict(row) for row in rows)

        error: repositories.RepositoryStorageError | None = None
        if self._connection is not None:
            try:
                return query(self._connection)
            except Exception as exc:
                error = repositories.RepositoryStorageError.from_exception(
                    operation,
                    exc,
                    dsn=self._dsn,
                )
            raise error

        try:
            with self.engine.connect() as connection:
                return query(connection)
        except Exception as exc:
            error = repositories.RepositoryStorageError.from_exception(
                operation,
                exc,
                dsn=self._dsn,
            )
        raise error

    def _write(
        self,
        operation: str,
        writer: Callable[[Any], T],
    ) -> T:
        error: repositories.RepositoryStorageError | None = None
        if self._connection is not None:
            try:
                return writer(self._connection)
            except repositories.OutboxAppendConflictError:
                raise
            except Exception as exc:
                error = repositories.RepositoryStorageError.from_exception(
                    operation,
                    exc,
                    dsn=self._dsn,
                )
            raise error

        try:
            with self.engine.begin() as connection:
                return writer(connection)
        except repositories.OutboxAppendConflictError:
            raise
        except Exception as exc:
            error = repositories.RepositoryStorageError.from_exception(
                operation,
                exc,
                dsn=self._dsn,
            )
        raise error


def _checkpoint_from_row(
    row: Mapping[str, Any],
) -> repositories.ProjectionCheckpointRecord:
    return repositories.ProjectionCheckpointRecord(
        projection_name=str(row["projection_name"]),
        last_outbox_event_id=_optional_str(row["last_outbox_event_id"]),
        last_processed_at_utc=_optional_datetime(row["last_processed_at_utc"]),
        source_watermark=_optional_str(row["source_watermark"]),
        last_source_observed_at_utc=_optional_datetime(
            row["last_source_observed_at_utc"]
        ),
        lag_seconds=_optional_int(row["lag_seconds"]),
        status=str(row["status"]),
        metadata=_json_mapping(row["metadata_json"]),
    )


def _source_status_from_row(
    row: Mapping[str, Any],
) -> repositories.ProjectionSourceStatusRecord:
    return repositories.ProjectionSourceStatusRecord(
        domain_name=str(row["domain_name"]),
        source_family=str(row["source_family"]),
        source_identity=str(row["source_identity"]),
        source_watermark=_optional_str(row["source_watermark"]),
        projected_watermark=_optional_str(row["projected_watermark"]),
        lag_seconds=_optional_int(row["lag_seconds"]),
        is_mutable=bool(row["is_mutable"]),
        ready_for_postgres=bool(row["ready_for_postgres"]),
        checked_at_utc=_datetime(row["checked_at_utc"]),
        metadata=_json_mapping(row["metadata_json"]),
    )


def _outbox_projection_event_from_row(
    row: Mapping[str, Any],
) -> repositories.OutboxProjectionEvent:
    return repositories.OutboxProjectionEvent(
        outbox_event_id=str(row["outbox_event_id"]),
        aggregate_type=str(row["aggregate_type"]),
        aggregate_id=str(row["aggregate_id"]),
        event_type=str(row["event_type"]),
        event_version=int(row["event_version"]),
        occurred_at_utc=_datetime(row["occurred_at_utc"]),
        dedupe_key=str(row["dedupe_key"]),
        payload=_json_mapping(row["payload_json"]),
        created_at_utc=_datetime(row["created_at_utc"]),
    )


def _json_dumps(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {"value": decoded}
    if isinstance(value, dict):
        return value
    return dict(value)


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value)
    return _aware_utc(datetime.fromisoformat(str(value)))


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _optional_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return _aware_utc(value)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


__all__ = ("PostgresProjectionStateRepository",)
