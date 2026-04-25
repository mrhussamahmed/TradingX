"""Postgres implementations of control-plane repository contracts."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import text

from tradingx.controlplane import repositories

T = TypeVar("T")


class PostgresControlPlaneRepository:
    """SQL-backed read repository for the Wave 2 control-plane slice."""

    def __init__(self, *, engine: Any, dsn: str) -> None:
        self.engine = engine
        self._dsn = dsn

    def list_control_posture_snapshots(
        self,
        *,
        page: repositories.PageRequest | None = None,
    ) -> repositories.Page[repositories.ControlPostureSnapshot]:
        return self._list_desc(
            operation="list control posture snapshots",
            base_sql="""
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
                WHERE TRUE
            """,
            params={},
            page=page,
            timestamp_column="observed_at_utc",
            stable_id_column="posture_id",
            mapper=self._control_posture_from_row,
            timestamp_getter=lambda item: item.observed_at_utc,
            stable_id_getter=lambda item: item.posture_id,
        )

    def get_control_posture_snapshot(
        self,
        posture_id: str,
    ) -> repositories.ControlPostureSnapshot | None:
        rows = self._query(
            "get control posture snapshot",
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
            """,
            {"posture_id": posture_id},
        )
        return self._control_posture_from_row(rows[0]) if rows else None

    def list_control_posture_blockers(
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
        return tuple(self._control_posture_blocker_from_row(row) for row in rows)

    def list_runtime_heartbeats(
        self,
        *,
        runtime_instance_id: str | None = None,
        page: repositories.PageRequest | None = None,
    ) -> repositories.Page[repositories.RuntimeHeartbeat]:
        if runtime_instance_id is None:
            heartbeat_filter = "TRUE"
            params: Mapping[str, Any] = {}
        else:
            heartbeat_filter = "runtime_instance_id = :runtime_instance_id"
            params = {"runtime_instance_id": runtime_instance_id}
        return self._list_desc(
            operation="list runtime heartbeats",
            base_sql=f"""
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
                WHERE {heartbeat_filter}
            """,
            params=params,
            page=page,
            timestamp_column="observed_at_utc",
            stable_id_column="heartbeat_id",
            mapper=self._runtime_heartbeat_from_row,
            timestamp_getter=lambda item: item.observed_at_utc,
            stable_id_getter=lambda item: item.heartbeat_id,
        )

    def list_incidents(
        self,
        *,
        page: repositories.PageRequest | None = None,
    ) -> repositories.Page[repositories.IncidentSummary]:
        return self._list_desc(
            operation="list incidents",
            base_sql="""
                SELECT
                    incident_id,
                    severity,
                    status,
                    summary,
                    opened_at_utc,
                    updated_at_utc,
                    resolved_at_utc,
                    resource_version,
                    state_fingerprint,
                    source_ref,
                    payload_json
                FROM incidents.incident
                WHERE TRUE
            """,
            params={},
            page=page,
            timestamp_column="updated_at_utc",
            stable_id_column="incident_id",
            mapper=self._incident_from_row,
            timestamp_getter=lambda item: item.updated_at_utc,
            stable_id_getter=lambda item: item.incident_id,
        )

    def get_incident(self, incident_id: str) -> repositories.IncidentSummary | None:
        rows = self._query(
            "get incident",
            """
            SELECT
                incident_id,
                severity,
                status,
                summary,
                opened_at_utc,
                updated_at_utc,
                resolved_at_utc,
                resource_version,
                state_fingerprint,
                source_ref,
                payload_json
            FROM incidents.incident
            WHERE incident_id = :incident_id
            """,
            {"incident_id": incident_id},
        )
        return self._incident_from_row(rows[0]) if rows else None

    def list_incident_events(
        self,
        incident_id: str,
        *,
        page: repositories.PageRequest | None = None,
    ) -> repositories.Page[repositories.IncidentEvent]:
        return self._list_desc(
            operation="list incident events",
            base_sql="""
                SELECT
                    incident_event_id,
                    incident_id,
                    event_id,
                    event_type,
                    occurred_at_utc,
                    payload_json
                FROM incidents.incident_event
                WHERE incident_id = :incident_id
            """,
            params={"incident_id": incident_id},
            page=page,
            timestamp_column="occurred_at_utc",
            stable_id_column="incident_event_id",
            mapper=self._incident_event_from_row,
            timestamp_getter=lambda item: item.occurred_at_utc,
            stable_id_getter=lambda item: item.incident_event_id,
        )

    def list_projection_statuses(
        self,
        *,
        page: repositories.PageRequest | None = None,
    ) -> repositories.Page[repositories.ProjectionStatusSummary]:
        return self._list_desc(
            operation="list projection statuses",
            base_sql="""
                SELECT
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
                FROM system.domain_projection_status
                WHERE TRUE
            """,
            params={},
            page=page,
            timestamp_column="checked_at_utc",
            stable_id_column="domain_name",
            mapper=self._projection_status_from_row,
            timestamp_getter=lambda item: item.checked_at_utc,
            stable_id_getter=lambda item: item.domain_name,
        )

    def get_projection_status(
        self,
        domain_name: str,
    ) -> repositories.ProjectionStatusSummary | None:
        rows = self._query(
            "get projection status",
            """
            SELECT
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
            FROM system.domain_projection_status
            WHERE domain_name = :domain_name
            """,
            {"domain_name": domain_name},
        )
        return self._projection_status_from_row(rows[0]) if rows else None

    def list_public_timeline_events(
        self,
        *,
        event_family: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        page: repositories.PageRequest | None = None,
    ) -> repositories.Page[repositories.PublicTimelineEvent]:
        filters = ["TRUE"]
        params: dict[str, Any] = {}
        if event_family is not None:
            filters.append("event_family = :event_family")
            params["event_family"] = event_family
        if resource_type is not None:
            filters.append("resource_type = :resource_type")
            params["resource_type"] = resource_type
        if resource_id is not None:
            filters.append("resource_id = :resource_id")
            params["resource_id"] = resource_id

        return self._list_desc(
            operation="list public timeline events",
            base_sql=f"""
                SELECT *
                FROM ({_PUBLIC_TIMELINE_UNION_SQL}) AS public_timeline
                WHERE {" AND ".join(filters)}
            """,
            params=params,
            page=page,
            timestamp_column="occurred_at_utc",
            stable_id_column="timeline_event_id",
            mapper=self._public_timeline_event_from_row,
            timestamp_getter=lambda item: item.occurred_at_utc,
            stable_id_getter=lambda item: item.timeline_event_id,
        )

    def list_documents(
        self,
        *,
        page: repositories.PageRequest | None = None,
    ) -> repositories.Page[repositories.DocumentReadRecord]:
        return self._list_desc(
            operation="list documents",
            base_sql=f"""
                {_DOCUMENT_SELECT_SQL}
                WHERE COALESCE(d.metadata_json ->> 'document_state', 'active')
                    = 'active'
            """,
            params={},
            page=page,
            timestamp_column="updated_at_utc",
            stable_id_column="document_id",
            mapper=self._document_from_row,
            timestamp_getter=lambda item: item.updated_at_utc,
            stable_id_getter=lambda item: item.document_id,
        )

    def get_document(
        self,
        document_id: str,
    ) -> repositories.DocumentReadRecord | None:
        rows = self._query(
            "get document",
            f"""
            {_DOCUMENT_SELECT_SQL}
            WHERE d.document_id = :document_id
              AND COALESCE(d.metadata_json ->> 'document_state', 'active')
                    = 'active'
            """,
            {"document_id": document_id},
        )
        return self._document_from_row(rows[0]) if rows else None

    def _list_desc(
        self,
        *,
        operation: str,
        base_sql: str,
        params: Mapping[str, Any],
        page: repositories.PageRequest | None,
        timestamp_column: str,
        stable_id_column: str,
        mapper: Callable[[Mapping[str, Any]], T],
        timestamp_getter: Callable[[T], datetime],
        stable_id_getter: Callable[[T], str],
    ) -> repositories.Page[T]:
        page_request = page or repositories.PageRequest()
        cursor = (
            repositories.OrderedCursor.decode(page_request.cursor)
            if page_request.cursor
            else None
        )
        query_params = dict(params)
        cursor_sql = ""
        if cursor is not None:
            cursor_sql = (
                f" AND ({timestamp_column} < :cursor_timestamp "
                f"OR ({timestamp_column} = :cursor_timestamp "
                f"AND {stable_id_column} < :cursor_stable_id))"
            )
            query_params["cursor_timestamp"] = cursor.timestamp
            query_params["cursor_stable_id"] = cursor.stable_id

        query_params["limit"] = page_request.page_size + 1
        rows = self._query(
            operation,
            f"""
            {base_sql}
            {cursor_sql}
            ORDER BY {timestamp_column} DESC, {stable_id_column} DESC
            LIMIT :limit
            """,
            query_params,
        )
        items = tuple(mapper(row) for row in rows[: page_request.page_size])
        next_cursor = None
        if len(rows) > page_request.page_size and items:
            last_item = items[-1]
            next_cursor = repositories.OrderedCursor.encode(
                timestamp=timestamp_getter(last_item),
                stable_id=stable_id_getter(last_item),
            )
        return repositories.Page(items=items, next_cursor=next_cursor)

    def _query(
        self,
        operation: str,
        sql: str,
        params: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], ...]:
        error: repositories.RepositoryStorageError | None = None
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(text(sql), dict(params)).mappings().all()
                return tuple(dict(row) for row in rows)
        except Exception as exc:
            error = repositories.RepositoryStorageError.from_exception(
                operation,
                exc,
                dsn=self._dsn,
            )
        raise error

    def _control_posture_from_row(
        self,
        row: Mapping[str, Any],
    ) -> repositories.ControlPostureSnapshot:
        posture_id = str(row["posture_id"])
        return repositories.ControlPostureSnapshot(
            posture_id=posture_id,
            observed_at_utc=_datetime(row["observed_at_utc"]),
            requested_mode=str(row["requested_mode"]),
            effective_mode=str(row["effective_mode"]),
            live_allowed=bool(row["live_allowed"]),
            governance_status=str(row["governance_status"]),
            blocker_count=int(row["blocker_count"]),
            explicit_blocker_codes=_string_tuple(row["explicit_blocker_codes"]),
            fail_closed_reason_codes=_string_tuple(row["fail_closed_reason_codes"]),
            resource_version=int(row["resource_version"]),
            state_fingerprint=str(row["state_fingerprint"]),
            payload_hash=_optional_str(row["payload_hash"]),
            payload=_json_mapping(row["payload_json"]),
            blockers=self.list_control_posture_blockers(posture_id),
        )

    def _control_posture_blocker_from_row(
        self,
        row: Mapping[str, Any],
    ) -> repositories.ControlPostureBlocker:
        return repositories.ControlPostureBlocker(
            blocker_id=str(row["blocker_id"]),
            posture_id=str(row["posture_id"]),
            blocker_code=str(row["blocker_code"]),
            severity=str(row["severity"]),
            message=str(row["message"]),
            source_ref=_optional_str(row["source_ref"]),
            metadata=_json_mapping(row["payload_json"]),
        )

    def _runtime_heartbeat_from_row(
        self,
        row: Mapping[str, Any],
    ) -> repositories.RuntimeHeartbeat:
        return repositories.RuntimeHeartbeat(
            heartbeat_id=str(row["heartbeat_id"]),
            runtime_instance_id=_optional_str(row["runtime_instance_id"]),
            observed_at_utc=_datetime(row["observed_at_utc"]),
            heartbeat_state=str(row["heartbeat_state"]),
            scheduler_cadence_seconds=_optional_int(row["scheduler_cadence_seconds"]),
            stream_state=_optional_str(row["stream_state"]),
            stale_after_utc=_optional_datetime(row["stale_after_utc"]),
            source_ref=_optional_str(row["source_ref"]),
            payload=_json_mapping(row["payload_json"]),
        )

    def _incident_from_row(
        self,
        row: Mapping[str, Any],
    ) -> repositories.IncidentSummary:
        return repositories.IncidentSummary(
            incident_id=str(row["incident_id"]),
            severity=str(row["severity"]),
            status=str(row["status"]),
            summary=str(row["summary"]),
            opened_at_utc=_datetime(row["opened_at_utc"]),
            updated_at_utc=_datetime(row["updated_at_utc"]),
            resolved_at_utc=_optional_datetime(row["resolved_at_utc"]),
            resource_version=int(row["resource_version"]),
            state_fingerprint=str(row["state_fingerprint"]),
            source_ref=_optional_str(row["source_ref"]),
            payload=_json_mapping(row["payload_json"]),
        )

    def _incident_event_from_row(
        self,
        row: Mapping[str, Any],
    ) -> repositories.IncidentEvent:
        return repositories.IncidentEvent(
            incident_event_id=str(row["incident_event_id"]),
            incident_id=str(row["incident_id"]),
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"]),
            occurred_at_utc=_datetime(row["occurred_at_utc"]),
            payload=_json_mapping(row["payload_json"]),
        )

    def _projection_status_from_row(
        self,
        row: Mapping[str, Any],
    ) -> repositories.ProjectionStatusSummary:
        return repositories.ProjectionStatusSummary(
            domain_name=str(row["domain_name"]),
            target_store=str(row["target_store"]),
            bridge_status=str(row["bridge_status"]),
            projection_status=str(row["projection_status"]),
            source_watermark=_optional_str(row["source_watermark"]),
            last_projected_outbox_event_id=_optional_str(
                row["last_projected_outbox_event_id"]
            ),
            lag_seconds=_optional_int(row["lag_seconds"]),
            ready_for_postgres=bool(row["ready_for_postgres"]),
            checked_at_utc=_datetime(row["checked_at_utc"]),
            metadata=_json_mapping(row["metadata_json"]),
        )

    def _public_timeline_event_from_row(
        self,
        row: Mapping[str, Any],
    ) -> repositories.PublicTimelineEvent:
        return repositories.PublicTimelineEvent(
            timeline_event_id=str(row["timeline_event_id"]),
            source_table=str(row["source_table"]),
            source_primary_key=str(row["source_primary_key"]),
            event_family=str(row["event_family"]),
            event_type=str(row["event_type"]),
            occurred_at_utc=_datetime(row["occurred_at_utc"]),
            resource_type=str(row["resource_type"]),
            resource_id=str(row["resource_id"]),
            severity=_optional_str(row["severity"]),
            summary=str(row["summary"]),
            metadata=_json_mapping(row["metadata"]),
        )

    def _document_from_row(
        self,
        row: Mapping[str, Any],
    ) -> repositories.DocumentReadRecord:
        metadata = _json_mapping(row["metadata_json"])
        return repositories.DocumentReadRecord(
            document_id=str(row["document_id"]),
            document_kind=str(row["document_type"]),
            title=str(row["title"]),
            preview=str(metadata.get("preview", "")),
            logical_retrieval_ref=str(
                metadata.get("logical_retrieval_ref")
                or metadata.get("relative_path")
                or row["source_ref"]
                or row["document_id"]
            ),
            source_ref=_optional_str(row["source_ref"]),
            created_at_utc=_datetime(row["created_at_utc"]),
            updated_at_utc=_datetime(row["updated_at_utc"]),
            metadata=metadata,
            latest_revision=_document_revision_from_row(row),
        )


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return _datetime(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _json_mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {"value": decoded}
    if isinstance(value, dict):
        return value
    return dict(value)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, list | tuple):
            return tuple(str(item) for item in decoded)
        return (str(decoded),)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return (str(value),)


def _document_revision_from_row(
    row: Mapping[str, Any],
) -> repositories.DocumentRevisionRecord | None:
    if row["document_revision_id"] is None:
        return None
    return repositories.DocumentRevisionRecord(
        document_revision_id=str(row["document_revision_id"]),
        document_id=str(row["document_id"]),
        revision_number=int(row["revision_number"]),
        created_at_utc=_datetime(row["revision_created_at_utc"]),
        source_ref=_optional_str(row["revision_source_ref"]),
        metadata=_json_mapping(row["revision_metadata_json"]),
    )


_DOCUMENT_SELECT_SQL = """
    SELECT
        d.document_id,
        d.document_type,
        d.title,
        d.created_at_utc,
        d.updated_at_utc,
        d.source_ref,
        d.metadata_json,
        latest_revision.document_revision_id,
        latest_revision.revision_number,
        latest_revision.created_at_utc AS revision_created_at_utc,
        latest_revision.source_ref AS revision_source_ref,
        latest_revision.metadata_json AS revision_metadata_json
    FROM documents.document AS d
    LEFT JOIN LATERAL (
        SELECT
            revision.document_revision_id,
            revision.revision_number,
            revision.created_at_utc,
            revision.source_ref,
            revision.metadata_json
        FROM documents.document_revision AS revision
        WHERE revision.document_id = d.document_id
        ORDER BY
            revision.revision_number DESC,
            revision.created_at_utc DESC,
            revision.document_revision_id DESC
        LIMIT 1
    ) AS latest_revision ON TRUE
"""


_PUBLIC_TIMELINE_UNION_SQL = """
    SELECT
        'incidents.incident_event:' || event.incident_event_id AS timeline_event_id,
        'incidents.incident_event' AS source_table,
        event.incident_event_id AS source_primary_key,
        'incident' AS event_family,
        event.event_type AS event_type,
        event.occurred_at_utc AS occurred_at_utc,
        'incident' AS resource_type,
        event.incident_id AS resource_id,
        incident.severity AS severity,
        incident.summary AS summary,
        event.payload_json AS metadata
    FROM incidents.incident_event AS event
    JOIN incidents.incident AS incident
        ON incident.incident_id = event.incident_id

    UNION ALL

    SELECT
        'commanding.command_event:' || event.event_id AS timeline_event_id,
        'commanding.command_event' AS source_table,
        event.event_id AS source_primary_key,
        'command' AS event_family,
        event.event_type AS event_type,
        event.occurred_at_utc AS occurred_at_utc,
        command.target_resource_type AS resource_type,
        command.target_resource_id AS resource_id,
        NULL AS severity,
        COALESCE(event.message, event.event_type) AS summary,
        event.payload_json AS metadata
    FROM commanding.command_event AS event
    JOIN commanding.command AS command
        ON command.command_id = event.command_id

    UNION ALL

    SELECT
        'access.command_session_event:' || event.event_id AS timeline_event_id,
        'access.command_session_event' AS source_table,
        event.event_id AS source_primary_key,
        'command_session' AS event_family,
        event.event_type AS event_type,
        event.occurred_at_utc AS occurred_at_utc,
        'command_session' AS resource_type,
        event.command_session_id AS resource_id,
        NULL AS severity,
        COALESCE(event.reason, event.event_type) AS summary,
        event.metadata_json AS metadata
    FROM access.command_session_event AS event

    UNION ALL

    SELECT
        'runtime.control_posture_snapshot:' || posture.posture_id
            AS timeline_event_id,
        'runtime.control_posture_snapshot' AS source_table,
        posture.posture_id AS source_primary_key,
        'runtime_posture' AS event_family,
        'control_posture_observed' AS event_type,
        posture.observed_at_utc AS occurred_at_utc,
        'control_posture' AS resource_type,
        posture.posture_id AS resource_id,
        CASE WHEN posture.live_allowed THEN NULL ELSE 'warning' END AS severity,
        posture.governance_status AS summary,
        posture.payload_json AS metadata
    FROM runtime.control_posture_snapshot AS posture

    UNION ALL

    SELECT
        'runtime.runtime_heartbeat:' || heartbeat.heartbeat_id
            AS timeline_event_id,
        'runtime.runtime_heartbeat' AS source_table,
        heartbeat.heartbeat_id AS source_primary_key,
        'runtime_heartbeat' AS event_family,
        'heartbeat_observed' AS event_type,
        heartbeat.observed_at_utc AS occurred_at_utc,
        'runtime_instance' AS resource_type,
        COALESCE(heartbeat.runtime_instance_id, heartbeat.heartbeat_id)
            AS resource_id,
        NULL AS severity,
        heartbeat.heartbeat_state AS summary,
        heartbeat.payload_json AS metadata
    FROM runtime.runtime_heartbeat AS heartbeat

    UNION ALL

    SELECT
        'investigations.replay_event:' || event.replay_event_id
            AS timeline_event_id,
        'investigations.replay_event' AS source_table,
        event.replay_event_id AS source_primary_key,
        'replay' AS event_family,
        event.event_type AS event_type,
        event.occurred_at_utc AS occurred_at_utc,
        'replay_run' AS resource_type,
        event.replay_run_id AS resource_id,
        NULL AS severity,
        event.event_type AS summary,
        event.payload_json AS metadata
    FROM investigations.replay_event AS event
"""


__all__ = ("PostgresControlPlaneRepository",)
