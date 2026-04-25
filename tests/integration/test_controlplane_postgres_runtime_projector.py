from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tradingx.controlplane import projections, projectors, repositories
from tradingx.persistence import postgres
from tradingx.persistence.repositories.postgres import PostgresControlPlaneRepository

pytestmark = pytest.mark.skipif(
    not os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip(),
    reason="TRADINGX_TEST_POSTGRES_DSN is not configured",
)

FIXED_NOW = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)


def _postgres_dsn() -> str:
    dsn = os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("TRADINGX_TEST_POSTGRES_DSN is not configured")
    return dsn


@pytest.fixture()
def engine() -> Iterator[Engine]:
    dsn = _postgres_dsn()
    engine = postgres.build_postgres_engine(postgres.PostgresSettings(dsn=dsn))
    postgres.reset_postgres_test_database(engine, dsn=dsn)
    postgres.run_postgres_migrations(dsn, revision="head")
    try:
        yield engine
    finally:
        engine.dispose()


def test_runtime_projector_materializes_heartbeat_and_full_blocked_status(
    engine: Engine,
) -> None:
    from tradingx.persistence.repositories.projection_state import (
        PostgresProjectionStateRepository,
    )
    from tradingx.persistence.repositories.runtime_projection import (
        PostgresRuntimeProjectorUnitOfWork,
    )

    dsn = _postgres_dsn()
    projection_repo = PostgresProjectionStateRepository(
        engine=engine,
        dsn=dsn,
        id_provider=_sequential_id_provider(),
        clock=lambda: FIXED_NOW,
    )
    projection_repo.upsert_projection_source_status(
        _status(
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
            source_watermark="cycle-1:hash",
        )
    )
    projection_repo.upsert_projection_source_status(
        _status(
            source_family="market_sessions",
            source_identity="artifact:operator_platform/market_sessions",
            source_watermark="session-1:hash",
        )
    )
    projection_repo.append_outbox_event(
        _append_request(
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
            source_event_id="cycle-1",
            source_watermark="cycle-1:hash",
            payload={"cycle_id": "cycle-1"},
        )
    )

    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=PostgresRuntimeProjectorUnitOfWork(
            engine=engine,
            dsn=dsn,
            id_provider=_sequential_id_provider(start=100),
            clock=lambda: FIXED_NOW,
        ),
        clock=lambda: FIXED_NOW,
        full_requirements=(
            _requirement(
                source_family="service_cycles",
                source_identity="artifact:paper_loop/service_cycles",
            ),
            _requirement(
                source_family="market_sessions",
                source_identity="artifact:operator_platform/market_sessions",
            ),
        ),
    )

    runtime_projector.run_once(batch_size=10)
    runtime_projector.run_once(batch_size=10)

    read_repo = PostgresControlPlaneRepository(engine=engine, dsn=dsn)
    heartbeats = read_repo.list_runtime_heartbeats().items
    service_status = projection_repo.get_projection_source_status(
        domain_name="runtime",
        source_family="service_cycles",
        source_identity="artifact:paper_loop/service_cycles",
    )
    domain_status = _domain_projection_status(engine, "runtime")

    assert len(heartbeats) == 1
    assert heartbeats[0].heartbeat_state == "unknown"
    assert service_status is not None
    assert service_status.projected_watermark == "cycle-1:hash"
    assert domain_status["ready_for_postgres"] is False
    assert domain_status["projection_status"] == "unprojected_sources"


def test_control_posture_projector_persists_own_domain_status(
    engine: Engine,
) -> None:
    from tradingx.persistence.repositories.projection_state import (
        PostgresProjectionStateRepository,
    )
    from tradingx.persistence.repositories.runtime_projection import (
        PostgresRuntimeProjectorUnitOfWork,
    )

    dsn = _postgres_dsn()
    projection_repo = PostgresProjectionStateRepository(
        engine=engine,
        dsn=dsn,
        id_provider=_sequential_id_provider(),
        clock=lambda: FIXED_NOW,
    )
    projection_repo.upsert_projection_source_status(
        _status(
            domain_name="control_posture",
            source_family="live_config_env",
            source_identity="config:local",
            source_watermark="live-config:hash",
        )
    )
    projection_repo.upsert_projection_source_status(
        _status(
            domain_name="control_posture",
            source_family="operator_control_state",
            source_identity="data:control/state",
            source_watermark="control-state:hash",
        )
    )
    projection_repo.append_outbox_event(
        _append_request(
            domain_name="control_posture",
            aggregate_id="control_posture/live_config",
            event_type="legacy.live_config.observed",
            source_family="live_config_env",
            source_identity="config:local",
            source_event_id="live-config",
            source_watermark="live-config:hash",
            payload={"requested_mode": "live"},
        )
    )

    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=PostgresRuntimeProjectorUnitOfWork(
            engine=engine,
            dsn=dsn,
            id_provider=_sequential_id_provider(start=100),
            clock=lambda: FIXED_NOW,
        ),
        clock=lambda: FIXED_NOW,
        full_requirements=(
            _requirement(
                domain_name="control_posture",
                source_family="live_config_env",
                source_identity="config:local",
            ),
            _requirement(
                domain_name="control_posture",
                source_family="operator_control_state",
                source_identity="data:control/state",
            ),
        ),
    )

    runtime_projector.run_once(batch_size=10)

    read_repo = PostgresControlPlaneRepository(engine=engine, dsn=dsn)
    snapshots = read_repo.list_control_posture_snapshots().items
    live_status = projection_repo.get_projection_source_status(
        domain_name="control_posture",
        source_family="live_config_env",
        source_identity="config:local",
    )
    control_status = _domain_projection_status(engine, "control_posture")

    assert len(snapshots) == 1
    assert snapshots[0].live_allowed is False
    assert snapshots[0].governance_status == "blocked"
    assert snapshots[0].blockers
    assert live_status is not None
    assert live_status.projected_watermark == "live-config:hash"
    assert control_status["ready_for_postgres"] is False
    assert control_status["projection_status"] == "unprojected_sources"
    assert _domain_projection_status(engine, "runtime") is None


def test_runtime_projector_conflict_rolls_back_status_and_checkpoint(
    engine: Engine,
) -> None:
    from tradingx.persistence.repositories.projection_state import (
        PostgresProjectionStateRepository,
    )
    from tradingx.persistence.repositories.runtime_projection import (
        PostgresRuntimeProjectorUnitOfWork,
    )

    dsn = _postgres_dsn()
    event = _projection_event(
        source_family="service_cycles",
        source_identity="artifact:paper_loop/service_cycles",
        source_event_id="cycle-1",
        source_watermark="cycle-1:hash",
    )
    heartbeat = projectors.runtime_heartbeat_from_event(event)
    _insert_conflicting_heartbeat(engine, heartbeat.heartbeat_id)

    projection_repo = PostgresProjectionStateRepository(
        engine=engine,
        dsn=dsn,
        id_provider=_sequential_id_provider(),
        clock=lambda: FIXED_NOW,
    )
    projection_repo.upsert_projection_source_status(
        _status(
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
            source_watermark="cycle-1:hash",
        )
    )
    projection_repo.append_outbox_event(
        _append_request(
            source_family="service_cycles",
            source_identity="artifact:paper_loop/service_cycles",
            source_event_id="cycle-1",
            source_watermark="cycle-1:hash",
        )
    )

    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=PostgresRuntimeProjectorUnitOfWork(
            engine=engine,
            dsn=dsn,
            id_provider=_sequential_id_provider(start=100),
            clock=lambda: FIXED_NOW,
        ),
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(repositories.RepositoryConflictError):
        runtime_projector.run_once(batch_size=10)

    status = projection_repo.get_projection_source_status(
        domain_name="runtime",
        source_family="service_cycles",
        source_identity="artifact:paper_loop/service_cycles",
    )
    checkpoint = projection_repo.load_projection_checkpoint(
        "runtime_projection:runtime:service_cycles:v1"
    )

    assert status is not None
    assert status.projected_watermark is None
    assert checkpoint is None


def _append_request(
    *,
    domain_name: str = "runtime",
    aggregate_id: str = "service_cycle/cycle-1",
    event_type: str = "legacy.service_cycle.observed",
    source_family: str,
    source_identity: str,
    source_event_id: str,
    source_watermark: str,
    payload: dict[str, object] | None = None,
) -> repositories.OutboxEventAppendRequest:
    return repositories.OutboxEventAppendRequest(
        aggregate_type=domain_name,
        aggregate_id=aggregate_id,
        event_type=event_type,
        event_version=1,
        dedupe_key=(
            f"legacy:{domain_name}:{source_family}:"
            f"{source_identity}:{source_event_id}"
        ),
        occurred_at_utc=FIXED_NOW - timedelta(seconds=5),
        payload=_envelope(
            domain_name=domain_name,
            event_type=event_type,
            source_family=source_family,
            source_identity=source_identity,
            source_event_id=source_event_id,
            source_watermark=source_watermark,
            payload=payload,
        ),
    )


def _projection_event(
    *,
    source_family: str,
    source_identity: str,
    source_event_id: str,
    source_watermark: str,
) -> repositories.OutboxProjectionEvent:
    return repositories.OutboxProjectionEvent(
        outbox_event_id="outbox-001",
        aggregate_type="runtime",
        aggregate_id=f"{source_family}/{source_event_id}",
        event_type="legacy.service_cycle.observed",
        event_version=1,
        occurred_at_utc=FIXED_NOW - timedelta(seconds=5),
        dedupe_key=(
            f"legacy:runtime:{source_family}:{source_identity}:{source_event_id}"
        ),
        payload=_envelope(
            domain_name="runtime",
            event_type="legacy.service_cycle.observed",
            source_family=source_family,
            source_identity=source_identity,
            source_event_id=source_event_id,
            source_watermark=source_watermark,
        ),
        created_at_utc=FIXED_NOW,
    )


def _envelope(
    *,
    domain_name: str,
    event_type: str,
    source_family: str,
    source_identity: str,
    source_event_id: str,
    source_watermark: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "domain_name": domain_name,
        "source_family": source_family,
        "source_identity": source_identity,
        "source_event_id": source_event_id,
        "source_watermark": source_watermark,
        "event_family": domain_name,
        "event_type": event_type,
        "resource_type": source_family,
        "resource_id": source_event_id,
        "source_ref": f"{source_identity}:{source_event_id}",
        "payload": payload or {},
        "metadata": {},
    }


def _status(
    *,
    domain_name: str = "runtime",
    source_family: str,
    source_identity: str,
    source_watermark: str,
) -> repositories.ProjectionSourceStatusRecord:
    return repositories.ProjectionSourceStatusRecord(
        domain_name=domain_name,
        source_family=source_family,
        source_identity=source_identity,
        source_watermark=source_watermark,
        projected_watermark=None,
        lag_seconds=None,
        is_mutable=True,
        ready_for_postgres=True,
        checked_at_utc=FIXED_NOW,
        metadata={
            "initial_import_complete": True,
            "write_path": "active_bridge",
        },
    )


def _requirement(
    *,
    domain_name: str = "runtime",
    source_family: str,
    source_identity: str,
) -> projections.ProjectionSourceRequirement:
    return projections.ProjectionSourceRequirement(
        domain_name=domain_name,
        source_family=source_family,
        source_identity=source_identity,
        is_mutable=True,
        requires_initial_import_complete=True,
        requires_active_write_path=True,
    )


def _domain_projection_status(
    engine: Engine,
    domain_name: str,
) -> dict[str, Any] | None:
    with engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    """
                    SELECT
                        domain_name,
                        projection_status,
                        ready_for_postgres,
                        metadata_json
                    FROM system.domain_projection_status
                    WHERE domain_name = :domain_name
                    """
                ),
                {"domain_name": domain_name},
            )
            .mappings()
            .first()
        )
    return None if row is None else dict(row)


def _insert_conflicting_heartbeat(engine: Engine, heartbeat_id: str) -> None:
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
                    'conflicting',
                    NULL,
                    NULL,
                    NULL,
                    'conflict',
                    CAST(:payload_json AS JSONB)
                )
                """
            ),
            {
                "heartbeat_id": heartbeat_id,
                "observed_at_utc": FIXED_NOW - timedelta(seconds=30),
                "payload_json": '{"conflict": true}',
            },
        )


def _sequential_id_provider(start: int = 0) -> Any:
    next_id = start

    def provide_id() -> str:
        nonlocal next_id
        next_id += 1
        return f"outbox-{next_id:03d}"

    return provide_id
