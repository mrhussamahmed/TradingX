"""Postgres write repository for runtime projector materialization."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import text

from tradingx.controlplane import repositories
from tradingx.persistence.repositories.projection_state import (
    PostgresProjectionStateRepository,
)

T = TypeVar("T")


class PostgresRuntimeProjectionRepository:
    """SQL-backed writer for runtime projector tables."""

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

    def upsert_runtime_heartbeat(
        self,
        record: repositories.RuntimeHeartbeat,
    ) -> None:
        def write(connection: Any) -> None:
            inserted = connection.execute(
                text(
                    """
                    INSERT INTO runtime.runtime_heartbeat (
                        heartbeat_id,
                        runtime_instance_id,
                        observed_at_utc,
                        heartbeat_state,
                        scheduler_cadence_seconds,
                        stream_state,
                        stale_after_utc,
                        source_ref,
                        payload_json
                    ) VALUES (
                        :heartbeat_id,
                        :runtime_instance_id,
                        :observed_at_utc,
                        :heartbeat_state,
                        :scheduler_cadence_seconds,
                        :stream_state,
                        :stale_after_utc,
                        :source_ref,
                        CAST(:payload_json AS JSONB)
                    )
                    ON CONFLICT (heartbeat_id) DO NOTHING
                    RETURNING heartbeat_id
                    """
                ),
                _runtime_heartbeat_params(record),
            ).scalar_one_or_none()
            if inserted is not None:
                return

            existing = connection.execute(
                text(
                    """
                    SELECT
                        heartbeat_id,
                        runtime_instance_id,
                        observed_at_utc,
                        heartbeat_state,
                        scheduler_cadence_seconds,
                        stream_state,
                        stale_after_utc,
                        source_ref,
                        payload_json
                    FROM runtime.runtime_heartbeat
                    WHERE heartbeat_id = :heartbeat_id
                    """
                ),
                {"heartbeat_id": record.heartbeat_id},
            ).mappings().one()
            if _runtime_heartbeat_row_matches(existing, record):
                return
            raise repositories.RepositoryConflictError(
                "Runtime heartbeat projection conflict for "
                f"{record.heartbeat_id!r} in {repositories.redact_dsn(self._dsn)}."
            )

        self._write("upsert runtime heartbeat", write)

    def get_latest_control_posture_snapshot(
        self,
    ) -> repositories.ControlPostureSnapshot | None:
        rows = self._query(
            "get latest control posture snapshot",
            """
            SELECT
                posture_id,
                observed_at_utc,
                requested_mode,
                effective_mode,
                live_allowed,
                governance_status,
                blocker_count,
                explicit_blocker_codes,
                fail_closed_reason_codes,
                resource_version,
                state_fingerprint,
                payload_hash,
                payload_json
            FROM runtime.control_posture_snapshot
            ORDER BY observed_at_utc DESC, posture_id DESC
            LIMIT 1
            """,
            {},
        )
        if not rows:
            return None
        snapshot = _control_posture_snapshot_from_row(rows[0])
        blockers = self._list_control_posture_blockers(snapshot.posture_id)
        return repositories.ControlPostureSnapshot(
            **{
                **snapshot.__dict__,
                "blockers": blockers,
            }
        )

    def upsert_control_posture_snapshot(
        self,
        record: repositories.ControlPostureSnapshot,
    ) -> None:
        def write(connection: Any) -> None:
            inserted = connection.execute(
                text(
                    """
                    INSERT INTO runtime.control_posture_snapshot (
                        posture_id,
                        observed_at_utc,
                        requested_mode,
                        effective_mode,
                        live_allowed,
                        governance_status,
                        blocker_count,
                        explicit_blocker_codes,
                        fail_closed_reason_codes,
                        resource_version,
                        state_fingerprint,
                        payload_hash,
                        payload_json
                    ) VALUES (
                        :posture_id,
                        :observed_at_utc,
                        :requested_mode,
                        :effective_mode,
                        :live_allowed,
                        :governance_status,
                        :blocker_count,
                        CAST(:explicit_blocker_codes AS JSONB),
                        CAST(:fail_closed_reason_codes AS JSONB),
                        :resource_version,
                        :state_fingerprint,
                        :payload_hash,
                        CAST(:payload_json AS JSONB)
                    )
                    ON CONFLICT (posture_id) DO NOTHING
                    RETURNING posture_id
                    """
                ),
                _control_posture_params(record),
            ).scalar_one_or_none()
            if inserted is not None:
                return

            existing = connection.execute(
                text(
                    """
                    SELECT
                        posture_id,
                        observed_at_utc,
                        requested_mode,
                        effective_mode,
                        live_allowed,
                        governance_status,
                        blocker_count,
                        explicit_blocker_codes,
                        fail_closed_reason_codes,
                        resource_version,
                        state_fingerprint,
                        payload_hash,
                        payload_json
                    FROM runtime.control_posture_snapshot
                    WHERE posture_id = :posture_id
                    """
                ),
                {"posture_id": record.posture_id},
            ).mappings().one()
            if _control_posture_row_matches(existing, record):
                return
            raise repositories.RepositoryConflictError(
                "Control posture projection conflict for "
                f"{record.posture_id!r} in {repositories.redact_dsn(self._dsn)}."
            )

        self._write("upsert control posture snapshot", write)

    def replace_control_posture_blockers(
        self,
        posture_id: str,
        blockers: tuple[repositories.ControlPostureBlocker, ...],
    ) -> None:
        def write(connection: Any) -> None:
            connection.execute(
                text(
                    """
                    DELETE FROM runtime.control_posture_blocker
                    WHERE posture_id = :posture_id
                    """
                ),
                {"posture_id": posture_id},
            )
            for blocker in blockers:
                connection.execute(
                    text(
                        """
                        INSERT INTO runtime.control_posture_blocker (
                            blocker_id,
                            posture_id,
                            blocker_code,
                            severity,
                            message,
                            source_ref,
                            payload_json
                        ) VALUES (
                            :blocker_id,
                            :posture_id,
                            :blocker_code,
                            :severity,
                            :message,
                            :source_ref,
                            CAST(:payload_json AS JSONB)
                        )
                        """
                    ),
                    {
                        "blocker_id": blocker.blocker_id,
                        "posture_id": blocker.posture_id,
                        "blocker_code": blocker.blocker_code,
                        "severity": blocker.severity,
                        "message": blocker.message,
                        "source_ref": blocker.source_ref,
                        "payload_json": _json_dumps(blocker.metadata),
                    },
                )

        self._write("replace control posture blockers", write)

    def _list_control_posture_blockers(
        self,
        posture_id: str,
    ) -> tuple[repositories.ControlPostureBlocker, ...]:
        rows = self._query(
            "list control posture blockers",
            """
            SELECT
                blocker_id,
                posture_id,
                blocker_code,
                severity,
                message,
                source_ref,
                payload_json
            FROM runtime.control_posture_blocker
            WHERE posture_id = :posture_id
            ORDER BY blocker_code ASC, blocker_id ASC
            """,
            {"posture_id": posture_id},
        )
        return tuple(_control_posture_blocker_from_row(row) for row in rows)

    def _query(
        self,
        operation: str,
        sql: str,
        params: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], ...]:
        def query(connection: Any) -> tuple[Mapping[str, Any], ...]:
            rows = connection.execute(text(sql), dict(params)).mappings().all()
            return tuple(dict(row) for row in rows)

        if self._connection is not None:
            try:
                return query(self._connection)
            except Exception as exc:
                raise repositories.RepositoryStorageError.from_exception(
                    operation,
                    exc,
                    dsn=self._dsn,
                ) from None
        try:
            with self.engine.connect() as connection:
                return query(connection)
        except Exception as exc:
            raise repositories.RepositoryStorageError.from_exception(
                operation,
                exc,
                dsn=self._dsn,
            ) from None

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


class PostgresRuntimeProjectorUnitOfWork:
    """Creates runtime and projection-state repository views in one transaction."""

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
    def transaction(
        self,
    ) -> Iterator[
        tuple[PostgresProjectionStateRepository, PostgresRuntimeProjectionRepository]
    ]:
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
                    PostgresRuntimeProjectionRepository(
                        engine=self.engine,
                        dsn=self._dsn,
                        connection=connection,
                    ),
                )
        except repositories.RepositoryConflictError:
            raise
        except Exception as exc:
            raise repositories.RepositoryStorageError.from_exception(
                "runtime projector transaction",
                exc,
                dsn=self._dsn,
            ) from None


def _runtime_heartbeat_params(
    record: repositories.RuntimeHeartbeat,
) -> dict[str, Any]:
    return {
        "heartbeat_id": record.heartbeat_id,
        "runtime_instance_id": record.runtime_instance_id,
        "observed_at_utc": _aware_utc(record.observed_at_utc),
        "heartbeat_state": record.heartbeat_state,
        "scheduler_cadence_seconds": record.scheduler_cadence_seconds,
        "stream_state": record.stream_state,
        "stale_after_utc": _optional_aware_utc(record.stale_after_utc),
        "source_ref": record.source_ref,
        "payload_json": _json_dumps(record.payload),
    }


def _control_posture_params(
    record: repositories.ControlPostureSnapshot,
) -> dict[str, Any]:
    return {
        "posture_id": record.posture_id,
        "observed_at_utc": _aware_utc(record.observed_at_utc),
        "requested_mode": record.requested_mode,
        "effective_mode": record.effective_mode,
        "live_allowed": record.live_allowed,
        "governance_status": record.governance_status,
        "blocker_count": record.blocker_count,
        "explicit_blocker_codes": _json_dumps(record.explicit_blocker_codes),
        "fail_closed_reason_codes": _json_dumps(record.fail_closed_reason_codes),
        "resource_version": record.resource_version,
        "state_fingerprint": record.state_fingerprint,
        "payload_hash": record.payload_hash,
        "payload_json": _json_dumps(record.payload),
    }


def _runtime_heartbeat_row_matches(
    row: Mapping[str, Any],
    record: repositories.RuntimeHeartbeat,
) -> bool:
    return {
        "runtime_instance_id": row["runtime_instance_id"],
        "observed_at_utc": _datetime(row["observed_at_utc"]),
        "heartbeat_state": row["heartbeat_state"],
        "scheduler_cadence_seconds": row["scheduler_cadence_seconds"],
        "stream_state": row["stream_state"],
        "stale_after_utc": _optional_datetime(row["stale_after_utc"]),
        "source_ref": row["source_ref"],
        "payload_json": _json_normalized(row["payload_json"]),
    } == {
        "runtime_instance_id": record.runtime_instance_id,
        "observed_at_utc": _aware_utc(record.observed_at_utc),
        "heartbeat_state": record.heartbeat_state,
        "scheduler_cadence_seconds": record.scheduler_cadence_seconds,
        "stream_state": record.stream_state,
        "stale_after_utc": _optional_aware_utc(record.stale_after_utc),
        "source_ref": record.source_ref,
        "payload_json": _json_normalized(record.payload),
    }


def _control_posture_row_matches(
    row: Mapping[str, Any],
    record: repositories.ControlPostureSnapshot,
) -> bool:
    return {
        "observed_at_utc": _datetime(row["observed_at_utc"]),
        "requested_mode": row["requested_mode"],
        "effective_mode": row["effective_mode"],
        "live_allowed": row["live_allowed"],
        "governance_status": row["governance_status"],
        "blocker_count": row["blocker_count"],
        "explicit_blocker_codes": tuple(row["explicit_blocker_codes"] or ()),
        "fail_closed_reason_codes": tuple(row["fail_closed_reason_codes"] or ()),
        "resource_version": row["resource_version"],
        "state_fingerprint": row["state_fingerprint"],
        "payload_hash": row["payload_hash"],
        "payload_json": _json_normalized(row["payload_json"]),
    } == {
        "observed_at_utc": _aware_utc(record.observed_at_utc),
        "requested_mode": record.requested_mode,
        "effective_mode": record.effective_mode,
        "live_allowed": record.live_allowed,
        "governance_status": record.governance_status,
        "blocker_count": record.blocker_count,
        "explicit_blocker_codes": record.explicit_blocker_codes,
        "fail_closed_reason_codes": record.fail_closed_reason_codes,
        "resource_version": record.resource_version,
        "state_fingerprint": record.state_fingerprint,
        "payload_hash": record.payload_hash,
        "payload_json": _json_normalized(record.payload),
    }


def _control_posture_snapshot_from_row(
    row: Mapping[str, Any],
) -> repositories.ControlPostureSnapshot:
    return repositories.ControlPostureSnapshot(
        posture_id=str(row["posture_id"]),
        observed_at_utc=_datetime(row["observed_at_utc"]),
        requested_mode=str(row["requested_mode"]),
        effective_mode=str(row["effective_mode"]),
        live_allowed=bool(row["live_allowed"]),
        governance_status=str(row["governance_status"]),
        blocker_count=int(row["blocker_count"]),
        explicit_blocker_codes=tuple(row["explicit_blocker_codes"] or ()),
        fail_closed_reason_codes=tuple(row["fail_closed_reason_codes"] or ()),
        resource_version=int(row["resource_version"]),
        state_fingerprint=str(row["state_fingerprint"]),
        payload_hash=(
            None if row["payload_hash"] is None else str(row["payload_hash"])
        ),
        payload=_json_mapping(row["payload_json"]),
        blockers=(),
    )


def _control_posture_blocker_from_row(
    row: Mapping[str, Any],
) -> repositories.ControlPostureBlocker:
    return repositories.ControlPostureBlocker(
        blocker_id=str(row["blocker_id"]),
        posture_id=str(row["posture_id"]),
        blocker_code=str(row["blocker_code"]),
        severity=str(row["severity"]),
        message=str(row["message"]),
        source_ref=None if row["source_ref"] is None else str(row["source_ref"]),
        metadata=_json_mapping(row["payload_json"]),
    )


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


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_aware_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _aware_utc(value)
