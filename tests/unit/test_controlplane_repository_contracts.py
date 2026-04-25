from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tradingx.controlplane import repositories

SECRET_DSN = "postgresql://tradingx:super-secret@db.internal:5432/tradingx"


def test_page_request_clamps_page_size_and_rejects_bad_cursors() -> None:
    default_request = repositories.PageRequest()
    oversized_request = repositories.PageRequest(page_size=999_999)

    assert default_request.page_size == repositories.DEFAULT_PAGE_SIZE
    assert oversized_request.page_size == repositories.MAX_PAGE_SIZE

    with pytest.raises(repositories.InvalidCursorError):
        repositories.OrderedCursor.decode("not-a-valid-cursor")


def test_ordered_cursor_encodes_exclusive_timestamp_id_boundary() -> None:
    observed_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)

    cursor = repositories.OrderedCursor.encode(
        timestamp=observed_at,
        stable_id="snapshot-002",
    )
    decoded = repositories.OrderedCursor.decode(cursor)

    assert decoded.timestamp == observed_at
    assert decoded.stable_id == "snapshot-002"
    assert decoded.boundary == "exclusive"


def test_result_dataclasses_are_value_stable_and_plain_python() -> None:
    observed_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    blocker = repositories.ControlPostureBlocker(
        blocker_id="blocker-1",
        posture_id="posture-1",
        blocker_code="operator_hold",
        severity="warning",
        message="Operator hold is active.",
        source_ref="operator://hold",
        metadata={"operator": "alice"},
    )
    snapshot = repositories.ControlPostureSnapshot(
        posture_id="posture-1",
        observed_at_utc=observed_at,
        requested_mode="paper",
        effective_mode="paper",
        live_allowed=False,
        governance_status="blocked",
        blocker_count=1,
        explicit_blocker_codes=("operator_hold",),
        fail_closed_reason_codes=(),
        resource_version=7,
        state_fingerprint="fingerprint-1",
        payload_hash="payload-hash",
        payload={"mode": "paper"},
        blockers=(blocker,),
    )

    assert snapshot == repositories.ControlPostureSnapshot(
        posture_id="posture-1",
        observed_at_utc=observed_at,
        requested_mode="paper",
        effective_mode="paper",
        live_allowed=False,
        governance_status="blocked",
        blocker_count=1,
        explicit_blocker_codes=("operator_hold",),
        fail_closed_reason_codes=(),
        resource_version=7,
        state_fingerprint="fingerprint-1",
        payload_hash="payload-hash",
        payload={"mode": "paper"},
        blockers=(blocker,),
    )
    assert isinstance(snapshot.payload, dict)
    assert isinstance(snapshot.blockers, tuple)


def test_domain_scope_matrix_is_executable_contract() -> None:
    assert repositories.IMPLEMENTED_REPOSITORY_PROTOCOLS == (
        "RuntimePostureRepository",
        "RuntimeHeartbeatRepository",
        "IncidentRepository",
        "ProjectionStatusRepository",
        "PublicEventTimelineRepository",
        "DocumentReadRepository",
    )
    assert repositories.DEFERRED_DOMAIN_NOTES == {
        "access_command_session_audit",
        "commanding_audit",
        "portfolio",
        "validation",
        "investigations_replays",
    }
    assert repositories.SLICE3_CONTRACT_ONLY_PROTOCOLS == (
        "OutboxAppendBoundary",
        "ProjectionCheckpointBoundary",
        "ProjectionSourceStatusBoundary",
    )

    for deferred_name in (
        "AccessCommandSessionRepository",
        "CommandingRepository",
        "PortfolioRepository",
        "ValidationRepository",
        "InvestigationRepository",
    ):
        assert not hasattr(repositories, deferred_name)


def test_public_timeline_contract_names_source_shape_and_ordering() -> None:
    assert repositories.PUBLIC_TIMELINE_SOURCE_TABLES == (
        "incidents.incident_event",
        "commanding.command_event",
        "access.command_session_event",
        "runtime.control_posture_snapshot",
        "runtime.runtime_heartbeat",
        "investigations.replay_event",
    )
    assert "system.outbox_event" not in repositories.PUBLIC_TIMELINE_SOURCE_TABLES
    assert repositories.PUBLIC_TIMELINE_ORDERING == (
        ("occurred_at_utc", "desc", "not_null"),
        ("timeline_event_id", "desc", "not_null"),
    )

    event = repositories.PublicTimelineEvent(
        timeline_event_id="incidents.incident_event:incident-event-1",
        source_table="incidents.incident_event",
        source_primary_key="incident-event-1",
        event_family="incident",
        event_type="opened",
        occurred_at_utc=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        resource_type="incident",
        resource_id="incident-1",
        severity="critical",
        summary="Incident opened.",
        metadata={"incident_id": "incident-1"},
    )

    assert event.source_table in repositories.PUBLIC_TIMELINE_SOURCE_TABLES
    assert event.event_family == "incident"


def test_projection_status_contract_is_non_authoritative() -> None:
    status = repositories.ProjectionStatusSummary(
        domain_name="runtime",
        target_store="postgres",
        bridge_status="running",
        projection_status="caught_up",
        source_watermark="source-10",
        last_projected_outbox_event_id="outbox-10",
        lag_seconds=2,
        ready_for_postgres=True,
        checked_at_utc=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        metadata={"source": "summary"},
    )

    assert repositories.PROJECTION_STATUS_IS_ROUTER_READINESS_AUTHORITY is False
    assert status.ready_for_postgres is True


def test_fake_repositories_satisfy_implemented_protocols_only() -> None:
    class FakeRepositories:
        def __init__(self) -> None:
            self._now = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)

        def list_control_posture_snapshots(
            self,
            *,
            page: repositories.PageRequest | None = None,
        ) -> repositories.Page[repositories.ControlPostureSnapshot]:
            del page
            return repositories.Page(items=(), next_cursor=None)

        def get_control_posture_snapshot(
            self,
            posture_id: str,
        ) -> repositories.ControlPostureSnapshot | None:
            del posture_id
            return None

        def list_control_posture_blockers(
            self,
            posture_id: str,
        ) -> tuple[repositories.ControlPostureBlocker, ...]:
            del posture_id
            return ()

        def list_runtime_heartbeats(
            self,
            *,
            runtime_instance_id: str | None = None,
            page: repositories.PageRequest | None = None,
        ) -> repositories.Page[repositories.RuntimeHeartbeat]:
            del runtime_instance_id, page
            return repositories.Page(items=(), next_cursor=None)

        def list_incidents(
            self,
            *,
            page: repositories.PageRequest | None = None,
        ) -> repositories.Page[repositories.IncidentSummary]:
            del page
            return repositories.Page(items=(), next_cursor=None)

        def get_incident(
            self,
            incident_id: str,
        ) -> repositories.IncidentSummary | None:
            del incident_id
            return None

        def list_incident_events(
            self,
            incident_id: str,
            *,
            page: repositories.PageRequest | None = None,
        ) -> repositories.Page[repositories.IncidentEvent]:
            del incident_id, page
            return repositories.Page(items=(), next_cursor=None)

        def list_projection_statuses(
            self,
            *,
            page: repositories.PageRequest | None = None,
        ) -> repositories.Page[repositories.ProjectionStatusSummary]:
            del page
            return repositories.Page(items=(), next_cursor=None)

        def get_projection_status(
            self,
            domain_name: str,
        ) -> repositories.ProjectionStatusSummary | None:
            del domain_name
            return None

        def list_public_timeline_events(
            self,
            *,
            event_family: str | None = None,
            resource_type: str | None = None,
            resource_id: str | None = None,
            page: repositories.PageRequest | None = None,
        ) -> repositories.Page[repositories.PublicTimelineEvent]:
            del event_family, resource_type, resource_id, page
            return repositories.Page(items=(), next_cursor=None)

        def list_documents(
            self,
            *,
            page: repositories.PageRequest | None = None,
        ) -> repositories.Page[Any]:
            del page
            return repositories.Page(items=(), next_cursor=None)

        def get_document(self, document_id: str) -> Any | None:
            del document_id
            return None

    fake = FakeRepositories()

    assert isinstance(fake, repositories.RuntimePostureRepository)
    assert isinstance(fake, repositories.RuntimeHeartbeatRepository)
    assert isinstance(fake, repositories.IncidentRepository)
    assert isinstance(fake, repositories.ProjectionStatusRepository)
    assert isinstance(fake, repositories.PublicEventTimelineRepository)
    assert isinstance(fake, repositories.DocumentReadRepository)
    assert not isinstance(fake, repositories.OutboxAppendBoundary)
    assert not isinstance(fake, repositories.ProjectionCheckpointBoundary)
    assert not isinstance(fake, repositories.ProjectionSourceStatusBoundary)


def test_repository_error_redacts_dsn_and_chained_diagnostics() -> None:
    cause = RuntimeError(f"driver failed for {SECRET_DSN} with super-secret")
    error = repositories.RepositoryStorageError.from_exception(
        "list runtime heartbeats",
        cause,
        dsn=SECRET_DSN,
    )

    inspected_values: tuple[Any, ...] = (
        str(error),
        repr(error),
        error.args,
        error.__cause__,
        error.__context__,
    )

    for value in inspected_values:
        assert "super-secret" not in str(value)
        assert SECRET_DSN not in str(value)


def test_page_orders_equal_timestamps_by_stable_id_for_cursor_boundary() -> None:
    observed_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    later = observed_at + timedelta(seconds=1)
    rows = (
        repositories.PublicTimelineEvent(
            timeline_event_id="event-002",
            source_table="runtime.runtime_heartbeat",
            source_primary_key="event-002",
            event_family="runtime_heartbeat",
            event_type="heartbeat_observed",
            occurred_at_utc=observed_at,
            resource_type="runtime_instance",
            resource_id="runtime-1",
            severity=None,
            summary="Heartbeat observed.",
            metadata={},
        ),
        repositories.PublicTimelineEvent(
            timeline_event_id="event-001",
            source_table="runtime.runtime_heartbeat",
            source_primary_key="event-001",
            event_family="runtime_heartbeat",
            event_type="heartbeat_observed",
            occurred_at_utc=observed_at,
            resource_type="runtime_instance",
            resource_id="runtime-1",
            severity=None,
            summary="Heartbeat observed.",
            metadata={},
        ),
        repositories.PublicTimelineEvent(
            timeline_event_id="event-003",
            source_table="runtime.runtime_heartbeat",
            source_primary_key="event-003",
            event_family="runtime_heartbeat",
            event_type="heartbeat_observed",
            occurred_at_utc=later,
            resource_type="runtime_instance",
            resource_id="runtime-1",
            severity=None,
            summary="Heartbeat observed.",
            metadata={},
        ),
    )

    page = repositories.page_by_desc_timestamp_and_id(
        rows,
        page_request=repositories.PageRequest(page_size=2),
        timestamp_getter=lambda row: row.occurred_at_utc,
        stable_id_getter=lambda row: row.timeline_event_id,
    )

    assert [event.timeline_event_id for event in page.items] == [
        "event-003",
        "event-002",
    ]
    assert page.next_cursor is not None
