"""Repository contracts for the headless control-plane read model."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, Literal, Protocol, TypeVar, runtime_checkable
from urllib.parse import (
    parse_qsl,
    unquote,
    unquote_plus,
    urlencode,
    urlsplit,
    urlunsplit,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

IMPLEMENTED_REPOSITORY_PROTOCOLS = (
    "RuntimePostureRepository",
    "RuntimeHeartbeatRepository",
    "IncidentRepository",
    "ProjectionStatusRepository",
    "PublicEventTimelineRepository",
)
DEFERRED_DOMAIN_NOTES = {
    "access_command_session_audit",
    "commanding_audit",
    "portfolio",
    "validation",
    "investigations_replays",
    "documents",
}
SLICE3_CONTRACT_ONLY_PROTOCOLS = (
    "OutboxAppendBoundary",
    "ProjectionCheckpointBoundary",
    "ProjectionSourceStatusBoundary",
)
PUBLIC_TIMELINE_SOURCE_TABLES = (
    "incidents.incident_event",
    "commanding.command_event",
    "access.command_session_event",
    "runtime.control_posture_snapshot",
    "runtime.runtime_heartbeat",
    "investigations.replay_event",
)
PUBLIC_TIMELINE_ORDERING = (
    ("occurred_at_utc", "desc", "not_null"),
    ("timeline_event_id", "desc", "not_null"),
)
PROJECTION_STATUS_IS_ROUTER_READINESS_AUTHORITY = False
_SECRET_QUERY_PARAMETERS = frozenset(
    {"pass", "passwd", "password", "pwd", "sslpassword"}
)

T = TypeVar("T")


class InvalidCursorError(ValueError):
    """Raised when a repository cursor cannot be decoded safely."""


class RepositoryStorageError(RuntimeError):
    """Raised when a repository cannot complete a storage operation safely."""

    @classmethod
    def from_exception(
        cls,
        operation: str,
        exc: BaseException,
        *,
        dsn: str,
    ) -> RepositoryStorageError:
        message = _redact_exception_message(str(exc), dsn)
        error = cls(
            f"Control-plane repository operation {operation!r} failed for "
            f"{redact_dsn(dsn)}: {message}"
        )
        error.__cause__ = None
        error.__context__ = None
        error.__suppress_context__ = True
        return error


@dataclass(frozen=True)
class OrderedCursor:
    """Cursor boundary for descending timestamp-plus-ID queries."""

    timestamp: datetime
    stable_id: str
    boundary: Literal["exclusive"] = "exclusive"

    @staticmethod
    def encode(*, timestamp: datetime, stable_id: str) -> str:
        payload = {
            "timestamp": _aware_utc(timestamp).isoformat(),
            "stable_id": stable_id,
            "boundary": "exclusive",
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def decode(cursor: str) -> OrderedCursor:
        try:
            padded = cursor + ("=" * (-len(cursor) % 4))
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
            timestamp = datetime.fromisoformat(str(payload["timestamp"]))
            stable_id = str(payload["stable_id"])
            boundary = str(payload.get("boundary", "exclusive"))
        except Exception as exc:
            raise InvalidCursorError(
                "Invalid control-plane repository cursor."
            ) from exc

        if boundary != "exclusive":
            raise InvalidCursorError("Unsupported control-plane cursor boundary.")
        if not stable_id:
            raise InvalidCursorError("Control-plane cursor stable ID is required.")
        return OrderedCursor(
            timestamp=_aware_utc(timestamp),
            stable_id=stable_id,
            boundary="exclusive",
        )


@dataclass(frozen=True)
class PageRequest:
    """Bounded cursor pagination request shared by repository list methods."""

    page_size: int = DEFAULT_PAGE_SIZE
    cursor: str | None = None

    def __post_init__(self) -> None:
        if self.page_size < 1:
            raise ValueError("page_size must be at least 1")
        object.__setattr__(self, "page_size", min(self.page_size, MAX_PAGE_SIZE))
        if self.cursor is not None:
            OrderedCursor.decode(self.cursor)


@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class ControlPostureBlocker:
    blocker_id: str
    posture_id: str
    blocker_code: str
    severity: str
    message: str
    source_ref: str | None
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class ControlPostureSnapshot:
    posture_id: str
    observed_at_utc: datetime
    requested_mode: str
    effective_mode: str
    live_allowed: bool
    governance_status: str
    blocker_count: int
    explicit_blocker_codes: tuple[str, ...]
    fail_closed_reason_codes: tuple[str, ...]
    resource_version: int
    state_fingerprint: str
    payload_hash: str | None
    payload: Mapping[str, Any]
    blockers: tuple[ControlPostureBlocker, ...] = ()


@dataclass(frozen=True)
class RuntimeHeartbeat:
    heartbeat_id: str
    runtime_instance_id: str | None
    observed_at_utc: datetime
    heartbeat_state: str
    scheduler_cadence_seconds: int | None
    stream_state: str | None
    stale_after_utc: datetime | None
    source_ref: str | None
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class IncidentSummary:
    incident_id: str
    severity: str
    status: str
    summary: str
    opened_at_utc: datetime
    updated_at_utc: datetime
    resolved_at_utc: datetime | None
    resource_version: int
    state_fingerprint: str
    source_ref: str | None
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class IncidentEvent:
    incident_event_id: str
    incident_id: str
    event_id: str
    event_type: str
    occurred_at_utc: datetime
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class ProjectionStatusSummary:
    domain_name: str
    target_store: str
    bridge_status: str
    projection_status: str
    source_watermark: str | None
    last_projected_outbox_event_id: str | None
    lag_seconds: int | None
    ready_for_postgres: bool
    checked_at_utc: datetime
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class PublicTimelineEvent:
    timeline_event_id: str
    source_table: str
    source_primary_key: str
    event_family: str
    event_type: str
    occurred_at_utc: datetime
    resource_type: str
    resource_id: str
    severity: str | None
    summary: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class OutboxEventAppendRequest:
    aggregate_type: str
    aggregate_id: str
    event_type: str
    event_version: int
    dedupe_key: str
    occurred_at_utc: datetime
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class ProjectionCheckpointRecord:
    projection_name: str
    last_outbox_event_id: str | None
    last_processed_at_utc: datetime | None
    source_watermark: str | None
    last_source_observed_at_utc: datetime | None
    lag_seconds: int | None
    status: str
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class ProjectionSourceStatusRecord:
    domain_name: str
    source_family: str
    source_identity: str
    source_watermark: str | None
    projected_watermark: str | None
    lag_seconds: int | None
    is_mutable: bool
    ready_for_postgres: bool
    checked_at_utc: datetime
    metadata: Mapping[str, Any]


@runtime_checkable
class RuntimePostureRepository(Protocol):
    def list_control_posture_snapshots(
        self,
        *,
        page: PageRequest | None = None,
    ) -> Page[ControlPostureSnapshot]: ...

    def get_control_posture_snapshot(
        self,
        posture_id: str,
    ) -> ControlPostureSnapshot | None: ...

    def list_control_posture_blockers(
        self,
        posture_id: str,
    ) -> tuple[ControlPostureBlocker, ...]: ...


@runtime_checkable
class RuntimeHeartbeatRepository(Protocol):
    def list_runtime_heartbeats(
        self,
        *,
        runtime_instance_id: str | None = None,
        page: PageRequest | None = None,
    ) -> Page[RuntimeHeartbeat]: ...


@runtime_checkable
class IncidentRepository(Protocol):
    def list_incidents(
        self,
        *,
        page: PageRequest | None = None,
    ) -> Page[IncidentSummary]: ...

    def get_incident(self, incident_id: str) -> IncidentSummary | None: ...

    def list_incident_events(
        self,
        incident_id: str,
        *,
        page: PageRequest | None = None,
    ) -> Page[IncidentEvent]: ...


@runtime_checkable
class ProjectionStatusRepository(Protocol):
    def list_projection_statuses(
        self,
        *,
        page: PageRequest | None = None,
    ) -> Page[ProjectionStatusSummary]: ...

    def get_projection_status(
        self,
        domain_name: str,
    ) -> ProjectionStatusSummary | None: ...


@runtime_checkable
class PublicEventTimelineRepository(Protocol):
    def list_public_timeline_events(
        self,
        *,
        event_family: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        page: PageRequest | None = None,
    ) -> Page[PublicTimelineEvent]: ...


@runtime_checkable
class OutboxAppendBoundary(Protocol):
    def append_outbox_event(self, request: OutboxEventAppendRequest) -> str: ...


@runtime_checkable
class ProjectionCheckpointBoundary(Protocol):
    def load_projection_checkpoint(
        self,
        projection_name: str,
    ) -> ProjectionCheckpointRecord | None: ...

    def save_projection_checkpoint(
        self,
        record: ProjectionCheckpointRecord,
    ) -> None: ...


@runtime_checkable
class ProjectionSourceStatusBoundary(Protocol):
    def get_projection_source_status(
        self,
        *,
        domain_name: str,
        source_family: str,
        source_identity: str,
    ) -> ProjectionSourceStatusRecord | None: ...

    def upsert_projection_source_status(
        self,
        record: ProjectionSourceStatusRecord,
    ) -> None: ...


def page_by_desc_timestamp_and_id(
    items: tuple[T, ...],
    *,
    page_request: PageRequest,
    timestamp_getter: Callable[[T], datetime],
    stable_id_getter: Callable[[T], str],
) -> Page[T]:
    cursor = OrderedCursor.decode(page_request.cursor) if page_request.cursor else None
    ordered = tuple(
        sorted(
            items,
            key=lambda item: (
                _aware_utc(timestamp_getter(item)),
                stable_id_getter(item),
            ),
            reverse=True,
        )
    )
    if cursor is not None:
        ordered = tuple(
            item
            for item in ordered
            if _is_after_desc_cursor(
                timestamp=_aware_utc(timestamp_getter(item)),
                stable_id=stable_id_getter(item),
                cursor=cursor,
            )
        )

    page_items = ordered[: page_request.page_size]
    next_cursor = None
    if len(ordered) > page_request.page_size and page_items:
        last_item = page_items[-1]
        next_cursor = OrderedCursor.encode(
            timestamp=_aware_utc(timestamp_getter(last_item)),
            stable_id=stable_id_getter(last_item),
        )
    return Page(items=page_items, next_cursor=next_cursor)


def redact_dsn(dsn: str) -> str:
    normalized = dsn.strip()
    if not normalized:
        return ""

    parsed = urlsplit(normalized)
    netloc = parsed.netloc
    if parsed.netloc and "@" in parsed.netloc:
        userinfo, hostinfo = parsed.netloc.rsplit("@", 1)
        username, separator, _password = userinfo.partition(":")
        if separator:
            netloc = f"{username}:***@{hostinfo}"

    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            _redact_query_parameters(parsed.query),
            parsed.fragment,
        )
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_after_desc_cursor(
    *,
    timestamp: datetime,
    stable_id: str,
    cursor: OrderedCursor,
) -> bool:
    return timestamp < cursor.timestamp or (
        timestamp == cursor.timestamp and stable_id < cursor.stable_id
    )


def _redact_query_parameters(query: str) -> str:
    if not query:
        return ""

    return urlencode(
        [
            (
                key,
                "***" if key.lower() in _SECRET_QUERY_PARAMETERS else value,
            )
            for key, value in parse_qsl(query, keep_blank_values=True)
        ],
        doseq=True,
        safe="*",
    )


def _append_secret_value(
    secrets: list[str],
    value: str,
    *,
    query_value: bool = False,
) -> None:
    if not value:
        return
    secrets.append(value)
    decoded = unquote(value)
    if decoded != value:
        secrets.append(decoded)
    query_decoded = unquote_plus(value) if query_value else decoded
    if query_decoded not in {value, decoded}:
        secrets.append(query_decoded)


def _dsn_secret_values(dsn: str) -> tuple[str, ...]:
    parsed = urlsplit(dsn.strip())
    secrets: list[str] = []
    if parsed.netloc and "@" in parsed.netloc:
        userinfo, _hostinfo = parsed.netloc.rsplit("@", 1)
        _username, separator, password = userinfo.partition(":")
        if separator:
            _append_secret_value(secrets, password)
    elif parsed.password:
        _append_secret_value(secrets, parsed.password)

    for item in parsed.query.split("&"):
        if not item:
            continue
        key, separator, value = item.partition("=")
        if separator and unquote_plus(key).lower() in _SECRET_QUERY_PARAMETERS:
            _append_secret_value(secrets, value, query_value=True)
    return tuple(dict.fromkeys(secrets))


def _redact_exception_message(message: str, dsn: str) -> str:
    redacted = message.replace(dsn, redact_dsn(dsn))
    for secret in _dsn_secret_values(dsn):
        redacted = redacted.replace(secret, "***")
    return redacted


__all__ = (
    "DEFAULT_PAGE_SIZE",
    "DEFERRED_DOMAIN_NOTES",
    "IMPLEMENTED_REPOSITORY_PROTOCOLS",
    "MAX_PAGE_SIZE",
    "PROJECTION_STATUS_IS_ROUTER_READINESS_AUTHORITY",
    "PUBLIC_TIMELINE_ORDERING",
    "PUBLIC_TIMELINE_SOURCE_TABLES",
    "SLICE3_CONTRACT_ONLY_PROTOCOLS",
    "ControlPostureBlocker",
    "ControlPostureSnapshot",
    "IncidentEvent",
    "IncidentRepository",
    "IncidentSummary",
    "InvalidCursorError",
    "OrderedCursor",
    "OutboxAppendBoundary",
    "OutboxEventAppendRequest",
    "Page",
    "PageRequest",
    "ProjectionCheckpointBoundary",
    "ProjectionCheckpointRecord",
    "ProjectionSourceStatusBoundary",
    "ProjectionSourceStatusRecord",
    "ProjectionStatusRepository",
    "ProjectionStatusSummary",
    "PublicEventTimelineRepository",
    "PublicTimelineEvent",
    "RepositoryStorageError",
    "RuntimeHeartbeat",
    "RuntimeHeartbeatRepository",
    "RuntimePostureRepository",
    "page_by_desc_timestamp_and_id",
    "redact_dsn",
)
