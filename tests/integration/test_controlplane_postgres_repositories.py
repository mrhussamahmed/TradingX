from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tradingx.controlplane import repositories
from tradingx.persistence import postgres

pytestmark = pytest.mark.skipif(
    not os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip(),
    reason="TRADINGX_TEST_POSTGRES_DSN is not configured",
)


def _postgres_dsn() -> str:
    dsn = os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("TRADINGX_TEST_POSTGRES_DSN is not configured")
    return dsn


@pytest.fixture()
def repo() -> Any:
    from tradingx.persistence.repositories.postgres import (
        PostgresControlPlaneRepository,
    )

    dsn = _postgres_dsn()
    engine = postgres.build_postgres_engine(postgres.PostgresSettings(dsn=dsn))
    postgres.reset_postgres_test_database(engine, dsn=dsn)
    postgres.run_postgres_migrations(dsn, revision="head")
    try:
        yield PostgresControlPlaneRepository(engine=engine, dsn=dsn)
    finally:
        engine.dispose()


def test_postgres_repository_implements_only_slice2_protocols(repo: Any) -> None:
    assert isinstance(repo, repositories.RuntimePostureRepository)
    assert isinstance(repo, repositories.RuntimeHeartbeatRepository)
    assert isinstance(repo, repositories.IncidentRepository)
    assert isinstance(repo, repositories.ProjectionStatusRepository)
    assert isinstance(repo, repositories.PublicEventTimelineRepository)

    assert not isinstance(repo, repositories.OutboxAppendBoundary)
    assert not isinstance(repo, repositories.ProjectionCheckpointBoundary)
    assert not isinstance(repo, repositories.ProjectionSourceStatusBoundary)

    for deferred_method in (
        "list_command_sessions",
        "list_commands",
        "list_portfolios",
        "list_validation_runs",
        "list_replay_runs",
        "list_documents",
    ):
        assert not hasattr(repo, deferred_method)


def test_runtime_posture_reads_blockers_and_not_found(repo: Any) -> None:
    first = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    second = first + timedelta(minutes=1)
    _insert_control_posture(repo.engine, "posture-001", first)
    _insert_control_posture(repo.engine, "posture-002", second)
    _insert_control_posture_blocker(repo.engine, "blocker-001", "posture-002")

    page = repo.list_control_posture_snapshots(
        page=repositories.PageRequest(page_size=10)
    )
    snapshot = repo.get_control_posture_snapshot("posture-002")

    assert [item.posture_id for item in page.items] == ["posture-002", "posture-001"]
    assert snapshot is not None
    assert snapshot.blockers[0].blocker_code == "operator_hold"
    assert repo.get_control_posture_snapshot("missing") is None


def test_incident_reads_events_and_not_found(repo: Any) -> None:
    opened_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    _insert_incident(repo.engine, "incident-001", opened_at)
    _insert_incident_event(
        repo.engine,
        "incident-event-001",
        "incident-001",
        "opened",
        opened_at,
    )

    incidents = repo.list_incidents(page=repositories.PageRequest(page_size=10))
    events = repo.list_incident_events(
        "incident-001",
        page=repositories.PageRequest(page_size=10),
    )

    assert [incident.incident_id for incident in incidents.items] == ["incident-001"]
    assert repo.get_incident("incident-001") is not None
    assert repo.get_incident("missing") is None
    assert [event.event_type for event in events.items] == ["opened"]


def test_projection_status_reads_are_non_authoritative(repo: Any) -> None:
    checked_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    _insert_projection_status(repo.engine, "runtime", checked_at)

    page = repo.list_projection_statuses(page=repositories.PageRequest(page_size=10))
    status = repo.get_projection_status("runtime")

    assert repositories.PROJECTION_STATUS_IS_ROUTER_READINESS_AUTHORITY is False
    assert [item.domain_name for item in page.items] == ["runtime"]
    assert status is not None
    assert status.ready_for_postgres is True
    assert repo.get_projection_status("missing") is None


def test_public_timeline_uses_union_sources_and_excludes_outbox(repo: Any) -> None:
    observed_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    _seed_public_timeline_sources(repo.engine, observed_at)
    _insert_outbox_event(repo.engine, "outbox-should-not-leak", observed_at)

    page = repo.list_public_timeline_events(
        page=repositories.PageRequest(page_size=20)
    )

    source_tables = {event.source_table for event in page.items}
    assert source_tables == set(repositories.PUBLIC_TIMELINE_SOURCE_TABLES)
    assert "system.outbox_event" not in source_tables
    assert [event.timeline_event_id for event in page.items] == sorted(
        [event.timeline_event_id for event in page.items],
        reverse=True,
    )


def test_storage_failures_are_redacted() -> None:
    from tradingx.persistence.repositories.postgres import (
        PostgresControlPlaneRepository,
    )

    raw_dsn = (
        "postgresql://tradingx:super-secret@127.0.0.1:5432/tradingx_test"
    )

    class BrokenEngine:
        def connect(self) -> object:
            raise RuntimeError(f"connection failed for {raw_dsn} super-secret")

    repo = PostgresControlPlaneRepository(engine=BrokenEngine(), dsn=raw_dsn)

    with pytest.raises(repositories.RepositoryStorageError) as exc_info:
        repo.list_runtime_heartbeats()

    inspected = (
        str(exc_info.value),
        repr(exc_info.value),
        exc_info.value.args,
        exc_info.value.__cause__,
        exc_info.value.__context__,
    )
    for value in inspected:
        assert raw_dsn not in str(value)
        assert "super-secret" not in str(value)


@pytest.mark.parametrize(
    (
        "seed_initial",
        "fetch_page",
        "item_id",
        "insert_between",
        "expected_page2_prefix",
    ),
    (
        (
            lambda engine, base: [
                _insert_control_posture(
                    engine,
                    "posture-300",
                    base + timedelta(minutes=3),
                ),
                _insert_control_posture(
                    engine,
                    "posture-200",
                    base + timedelta(minutes=2),
                ),
                _insert_control_posture(
                    engine,
                    "posture-100",
                    base + timedelta(minutes=1),
                ),
            ],
            lambda repo, page: repo.list_control_posture_snapshots(page=page),
            lambda item: item.posture_id,
            lambda engine, base: [
                _insert_control_posture(
                    engine,
                    "posture-250",
                    base + timedelta(minutes=2),
                ),
                _insert_control_posture(
                    engine,
                    "posture-150",
                    base + timedelta(minutes=2),
                ),
            ],
            ("posture-150", "posture-100"),
        ),
        (
            lambda engine, base: [
                _insert_runtime_heartbeat(
                    engine,
                    "heartbeat-300",
                    base + timedelta(minutes=3),
                ),
                _insert_runtime_heartbeat(
                    engine,
                    "heartbeat-200",
                    base + timedelta(minutes=2),
                ),
                _insert_runtime_heartbeat(
                    engine,
                    "heartbeat-100",
                    base + timedelta(minutes=1),
                ),
            ],
            lambda repo, page: repo.list_runtime_heartbeats(page=page),
            lambda item: item.heartbeat_id,
            lambda engine, base: [
                _insert_runtime_heartbeat(
                    engine,
                    "heartbeat-250",
                    base + timedelta(minutes=2),
                ),
                _insert_runtime_heartbeat(
                    engine,
                    "heartbeat-150",
                    base + timedelta(minutes=2),
                ),
            ],
            ("heartbeat-150", "heartbeat-100"),
        ),
        (
            lambda engine, base: [
                _insert_incident(
                    engine,
                    "incident-300",
                    base + timedelta(minutes=3),
                ),
                _insert_incident(
                    engine,
                    "incident-200",
                    base + timedelta(minutes=2),
                ),
                _insert_incident(
                    engine,
                    "incident-100",
                    base + timedelta(minutes=1),
                ),
            ],
            lambda repo, page: repo.list_incidents(page=page),
            lambda item: item.incident_id,
            lambda engine, base: [
                _insert_incident(
                    engine,
                    "incident-250",
                    base + timedelta(minutes=2),
                ),
                _insert_incident(
                    engine,
                    "incident-150",
                    base + timedelta(minutes=2),
                ),
            ],
            ("incident-150", "incident-100"),
        ),
        (
            lambda engine, base: [
                _insert_incident(engine, "incident-events", base),
                _insert_incident_event(
                    engine,
                    "incident-event-300",
                    "incident-events",
                    "updated",
                    base + timedelta(minutes=3),
                ),
                _insert_incident_event(
                    engine,
                    "incident-event-200",
                    "incident-events",
                    "updated",
                    base + timedelta(minutes=2),
                ),
                _insert_incident_event(
                    engine,
                    "incident-event-100",
                    "incident-events",
                    "updated",
                    base + timedelta(minutes=1),
                ),
            ],
            lambda repo, page: repo.list_incident_events("incident-events", page=page),
            lambda item: item.incident_event_id,
            lambda engine, base: [
                _insert_incident_event(
                    engine,
                    "incident-event-250",
                    "incident-events",
                    "updated",
                    base + timedelta(minutes=2),
                ),
                _insert_incident_event(
                    engine,
                    "incident-event-150",
                    "incident-events",
                    "updated",
                    base + timedelta(minutes=2),
                ),
            ],
            ("incident-event-150", "incident-event-100"),
        ),
        (
            lambda engine, base: [
                _insert_projection_status(
                    engine,
                    "runtime-300",
                    base + timedelta(minutes=3),
                ),
                _insert_projection_status(
                    engine,
                    "runtime-200",
                    base + timedelta(minutes=2),
                ),
                _insert_projection_status(
                    engine,
                    "runtime-100",
                    base + timedelta(minutes=1),
                ),
            ],
            lambda repo, page: repo.list_projection_statuses(page=page),
            lambda item: item.domain_name,
            lambda engine, base: [
                _insert_projection_status(
                    engine,
                    "runtime-250",
                    base + timedelta(minutes=2),
                ),
                _insert_projection_status(
                    engine,
                    "runtime-150",
                    base + timedelta(minutes=2),
                ),
            ],
            ("runtime-150", "runtime-100"),
        ),
        (
            lambda engine, base: [
                _insert_runtime_heartbeat(
                    engine,
                    "timeline-300",
                    base + timedelta(minutes=3),
                ),
                _insert_runtime_heartbeat(
                    engine,
                    "timeline-200",
                    base + timedelta(minutes=2),
                ),
                _insert_runtime_heartbeat(
                    engine,
                    "timeline-100",
                    base + timedelta(minutes=1),
                ),
            ],
            lambda repo, page: repo.list_public_timeline_events(page=page),
            lambda item: item.timeline_event_id,
            lambda engine, base: [
                _insert_runtime_heartbeat(
                    engine,
                    "timeline-250",
                    base + timedelta(minutes=2),
                ),
                _insert_runtime_heartbeat(
                    engine,
                    "timeline-150",
                    base + timedelta(minutes=2),
                ),
            ],
            (
                "runtime.runtime_heartbeat:timeline-150",
                "runtime.runtime_heartbeat:timeline-100",
            ),
        ),
    ),
)
def test_sql_backed_list_methods_survive_mid_pagination_inserts(
    repo: Any,
    seed_initial: Callable[[Engine, datetime], object],
    fetch_page: Callable[[Any, repositories.PageRequest], repositories.Page[Any]],
    item_id: Callable[[Any], str],
    insert_between: Callable[[Engine, datetime], object],
    expected_page2_prefix: tuple[str, ...],
) -> None:
    base = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    seed_initial(repo.engine, base)

    page1 = fetch_page(repo, repositories.PageRequest(page_size=2))
    page1_ids = [item_id(item) for item in page1.items]
    assert page1.next_cursor is not None

    insert_between(repo.engine, base)
    page2 = fetch_page(
        repo,
        repositories.PageRequest(page_size=10, cursor=page1.next_cursor),
    )
    page2_ids = [item_id(item) for item in page2.items]

    assert page2_ids[: len(expected_page2_prefix)] == list(expected_page2_prefix)
    assert not set(page1_ids).intersection(page2_ids)


def _insert_control_posture(
    engine: Engine,
    posture_id: str,
    observed_at_utc: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
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
                    'paper',
                    'paper',
                    false,
                    'blocked',
                    0,
                    CAST(:explicit_blocker_codes AS JSONB),
                    CAST(:fail_closed_reason_codes AS JSONB),
                    1,
                    :state_fingerprint,
                    :payload_hash,
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "posture_id": posture_id,
                "observed_at_utc": observed_at_utc,
                "explicit_blocker_codes": json.dumps(()),
                "fail_closed_reason_codes": json.dumps(()),
                "state_fingerprint": f"fingerprint-{posture_id}",
                "payload_hash": f"hash-{posture_id}",
                "payload_json": json.dumps({"posture_id": posture_id}),
            },
        )


def _insert_control_posture_blocker(
    engine: Engine,
    blocker_id: str,
    posture_id: str,
) -> None:
    with engine.begin() as connection:
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
                    'operator_hold',
                    'warning',
                    'Operator hold is active.',
                    'operator://hold',
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "blocker_id": blocker_id,
                "posture_id": posture_id,
                "payload_json": json.dumps({"blocker": blocker_id}),
            },
        )


def _insert_runtime_heartbeat(
    engine: Engine,
    heartbeat_id: str,
    observed_at_utc: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
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
                    NULL,
                    :observed_at_utc,
                    'healthy',
                    60,
                    'open',
                    :stale_after_utc,
                    'runtime://heartbeat',
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "heartbeat_id": heartbeat_id,
                "observed_at_utc": observed_at_utc,
                "stale_after_utc": observed_at_utc + timedelta(minutes=5),
                "payload_json": json.dumps({"heartbeat_id": heartbeat_id}),
            },
        )


def _insert_incident(
    engine: Engine,
    incident_id: str,
    updated_at_utc: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO incidents.incident (
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
                ) VALUES (
                    :incident_id,
                    'critical',
                    'open',
                    :summary,
                    :opened_at_utc,
                    :updated_at_utc,
                    NULL,
                    1,
                    :state_fingerprint,
                    'incident://source',
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "incident_id": incident_id,
                "summary": f"Incident {incident_id}",
                "opened_at_utc": updated_at_utc - timedelta(minutes=5),
                "updated_at_utc": updated_at_utc,
                "state_fingerprint": f"fingerprint-{incident_id}",
                "payload_json": json.dumps({"incident_id": incident_id}),
            },
        )


def _insert_incident_event(
    engine: Engine,
    incident_event_id: str,
    incident_id: str,
    event_type: str,
    occurred_at_utc: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO incidents.incident_event (
                    incident_event_id,
                    incident_id,
                    event_id,
                    event_type,
                    occurred_at_utc,
                    payload_json
                ) VALUES (
                    :incident_event_id,
                    :incident_id,
                    :event_id,
                    :event_type,
                    :occurred_at_utc,
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "incident_event_id": incident_event_id,
                "incident_id": incident_id,
                "event_id": f"event-{incident_event_id}",
                "event_type": event_type,
                "occurred_at_utc": occurred_at_utc,
                "payload_json": json.dumps({"incident_event_id": incident_event_id}),
            },
        )


def _insert_projection_status(
    engine: Engine,
    domain_name: str,
    checked_at_utc: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
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
                    'postgres',
                    'running',
                    'caught_up',
                    'source-10',
                    'outbox-10',
                    2,
                    true,
                    :checked_at_utc,
                    CAST(:metadata_json AS JSONB)
                )
                """
            ),
            {
                "domain_name": domain_name,
                "checked_at_utc": checked_at_utc,
                "metadata_json": json.dumps({"domain": domain_name}),
            },
        )


def _seed_public_timeline_sources(engine: Engine, observed_at: datetime) -> None:
    _insert_incident(engine, "timeline-incident", observed_at)
    _insert_incident_event(
        engine,
        "timeline-incident-event",
        "timeline-incident",
        "opened",
        observed_at,
    )
    _insert_command_event(engine, "timeline-command-event", observed_at)
    _insert_command_session_event(engine, "timeline-session-event", observed_at)
    _insert_control_posture(engine, "timeline-posture", observed_at)
    _insert_runtime_heartbeat(engine, "timeline-heartbeat", observed_at)
    _insert_replay_event(engine, "timeline-replay-event", observed_at)


def _insert_command_event(
    engine: Engine,
    event_id: str,
    occurred_at_utc: datetime,
) -> None:
    command_id = f"command-{event_id}"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO commanding.command (
                    command_id,
                    command_type,
                    lifecycle_state,
                    target_resource_type,
                    target_resource_id,
                    requested_by,
                    created_at_utc,
                    payload_json
                ) VALUES (
                    :command_id,
                    'acknowledge_incident',
                    'accepted',
                    'incident',
                    'timeline-incident',
                    'operator',
                    :occurred_at_utc,
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "command_id": command_id,
                "occurred_at_utc": occurred_at_utc,
                "payload_json": json.dumps({"command_id": command_id}),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO commanding.command_event (
                    event_id,
                    command_id,
                    event_seq,
                    event_type,
                    occurred_at_utc,
                    message,
                    payload_json
                ) VALUES (
                    :event_id,
                    :command_id,
                    1,
                    'accepted',
                    :occurred_at_utc,
                    'Command accepted.',
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "event_id": event_id,
                "command_id": command_id,
                "occurred_at_utc": occurred_at_utc,
                "payload_json": json.dumps({"event_id": event_id}),
            },
        )


def _insert_command_session_event(
    engine: Engine,
    event_id: str,
    occurred_at_utc: datetime,
) -> None:
    session_id = f"session-{event_id}"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO access.command_session (
                    command_session_id,
                    status,
                    issued_at_utc,
                    expires_at_utc,
                    session_token_hash,
                    metadata_json
                ) VALUES (
                    :session_id,
                    'active',
                    :issued_at_utc,
                    :expires_at_utc,
                    'token-hash',
                    CAST(:metadata_json AS JSONB)
                )
                """
            ),
            {
                "session_id": session_id,
                "issued_at_utc": occurred_at_utc - timedelta(minutes=5),
                "expires_at_utc": occurred_at_utc + timedelta(hours=1),
                "metadata_json": json.dumps({"session_id": session_id}),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO access.command_session_event (
                    event_id,
                    command_session_id,
                    event_type,
                    occurred_at_utc,
                    actor_ref,
                    reason,
                    metadata_json
                ) VALUES (
                    :event_id,
                    :session_id,
                    'issued',
                    :occurred_at_utc,
                    'operator',
                    'test',
                    CAST(:metadata_json AS JSONB)
                )
                """
            ),
            {
                "event_id": event_id,
                "session_id": session_id,
                "occurred_at_utc": occurred_at_utc,
                "metadata_json": json.dumps({"event_id": event_id}),
            },
        )


def _insert_replay_event(
    engine: Engine,
    replay_event_id: str,
    occurred_at_utc: datetime,
) -> None:
    replay_run_id = f"run-{replay_event_id}"
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO investigations.replay_run (
                    replay_run_id,
                    started_at_utc,
                    completed_at_utc,
                    source_ref,
                    status,
                    payload_json
                ) VALUES (
                    :replay_run_id,
                    :started_at_utc,
                    NULL,
                    'replay://source',
                    'running',
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "replay_run_id": replay_run_id,
                "started_at_utc": occurred_at_utc - timedelta(minutes=5),
                "payload_json": json.dumps({"replay_run_id": replay_run_id}),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO investigations.replay_event (
                    replay_event_id,
                    replay_run_id,
                    event_seq,
                    event_type,
                    occurred_at_utc,
                    payload_json
                ) VALUES (
                    :replay_event_id,
                    :replay_run_id,
                    1,
                    'started',
                    :occurred_at_utc,
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "replay_event_id": replay_event_id,
                "replay_run_id": replay_run_id,
                "occurred_at_utc": occurred_at_utc,
                "payload_json": json.dumps({"replay_event_id": replay_event_id}),
            },
        )


def _insert_outbox_event(
    engine: Engine,
    outbox_event_id: str,
    occurred_at_utc: datetime,
) -> None:
    with engine.begin() as connection:
        connection.execute(
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
                    'runtime',
                    'runtime-1',
                    'internal',
                    1,
                    :occurred_at_utc,
                    :dedupe_key,
                    CAST(:payload_json AS JSONB),
                    :created_at_utc,
                    NULL
                )
                """
            ),
            {
                "outbox_event_id": outbox_event_id,
                "occurred_at_utc": occurred_at_utc,
                "dedupe_key": f"dedupe-{outbox_event_id}",
                "payload_json": json.dumps({"outbox_event_id": outbox_event_id}),
                "created_at_utc": occurred_at_utc,
            },
        )
