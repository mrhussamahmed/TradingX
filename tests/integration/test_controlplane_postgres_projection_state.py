from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tradingx.controlplane import projections, repositories
from tradingx.persistence import postgres
from tradingx.persistence.repositories.postgres import PostgresControlPlaneRepository

pytestmark = pytest.mark.skipif(
    not os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip(),
    reason="TRADINGX_TEST_POSTGRES_DSN is not configured",
)

FIXED_NOW = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)


def _postgres_dsn() -> str:
    dsn = os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("TRADINGX_TEST_POSTGRES_DSN is not configured")
    return dsn


@pytest.fixture()
def repo() -> Iterator[Any]:
    from tradingx.persistence.repositories.projection_state import (
        PostgresProjectionStateRepository,
    )

    dsn = _postgres_dsn()
    engine = postgres.build_postgres_engine(postgres.PostgresSettings(dsn=dsn))
    postgres.reset_postgres_test_database(engine, dsn=dsn)
    postgres.run_postgres_migrations(dsn, revision="head")
    try:
        yield PostgresProjectionStateRepository(
            engine=engine,
            dsn=dsn,
            id_provider=_sequential_id_provider(),
            clock=lambda: FIXED_NOW,
        )
    finally:
        engine.dispose()


def test_postgres_projection_state_repository_owns_slice3_boundaries(
    repo: Any,
) -> None:
    assert isinstance(repo, repositories.OutboxAppendBoundary)
    assert isinstance(repo, repositories.OutboxProjectionReadBoundary)
    assert isinstance(repo, repositories.ProjectionCheckpointBoundary)
    assert isinstance(repo, repositories.ProjectionSourceStatusBoundary)

    read_repo = PostgresControlPlaneRepository(engine=repo.engine, dsn=_postgres_dsn())
    assert not isinstance(read_repo, repositories.OutboxAppendBoundary)
    assert not isinstance(read_repo, repositories.OutboxProjectionReadBoundary)
    assert not isinstance(read_repo, repositories.ProjectionCheckpointBoundary)
    assert not isinstance(read_repo, repositories.ProjectionSourceStatusBoundary)


def test_outbox_append_generates_fields_is_idempotent_and_keeps_internal_shape(
    repo: Any,
) -> None:
    first_id = repo.append_outbox_event(
        _append_request(payload={"heartbeat_id": "heartbeat-1", "nested": {"b": 2}})
    )
    repeat_id = repo.append_outbox_event(
        _append_request(payload={"nested": {"b": 2}, "heartbeat_id": "heartbeat-1"})
    )

    rows = _rows(
        repo.engine,
        """
        SELECT
            outbox_event_id,
            aggregate_type,
            aggregate_id,
            event_type,
            event_version,
            dedupe_key,
            occurred_at_utc,
            payload_json,
            created_at_utc,
            published_at_utc
        FROM system.outbox_event
        """,
    )

    assert first_id == "outbox-001"
    assert repeat_id == first_id
    assert len(rows) == 1
    assert rows[0]["outbox_event_id"] == "outbox-001"
    assert rows[0]["created_at_utc"] == FIXED_NOW
    assert rows[0]["published_at_utc"] is None
    assert rows[0]["payload_json"] == {
        "heartbeat_id": "heartbeat-1",
        "nested": {"b": 2},
    }


def test_outbox_conflicting_dedupe_key_raises_redacted_conflict(
    repo: Any,
) -> None:
    repo.append_outbox_event(_append_request(payload={"heartbeat_id": "heartbeat-1"}))

    with pytest.raises(repositories.OutboxAppendConflictError) as exc_info:
        repo.append_outbox_event(_append_request(payload={"heartbeat_id": "different"}))

    inspected = (
        str(exc_info.value),
        repr(exc_info.value),
        exc_info.value.args,
        exc_info.value.__cause__,
        exc_info.value.__context__,
    )
    raw_dsn = _postgres_dsn()
    for value in inspected:
        assert raw_dsn not in str(value)
        assert "tradingx@127.0.0.1" not in str(value)
    assert _count(repo.engine, "system.outbox_event") == 1


def test_list_outbox_events_after_filters_family_and_uses_ordered_cursor(
    repo: Any,
) -> None:
    _insert_outbox_projection_event(
        repo.engine,
        outbox_event_id="outbox-z",
        dedupe_key="dedupe-z",
        source_family="service_cycles",
        created_at_utc=FIXED_NOW,
    )
    _insert_outbox_projection_event(
        repo.engine,
        outbox_event_id="outbox-a",
        dedupe_key="dedupe-a",
        source_family="service_cycles",
        created_at_utc=FIXED_NOW,
    )
    _insert_outbox_projection_event(
        repo.engine,
        outbox_event_id="outbox-m",
        dedupe_key="dedupe-m",
        source_family="market_sessions",
        created_at_utc=FIXED_NOW - timedelta(seconds=1),
    )

    first_page = repo.list_outbox_events_after(
        cursor_created_at_utc=None,
        cursor_outbox_event_id=None,
        aggregate_types=("runtime",),
        source_families=("service_cycles",),
        batch_size=10,
    )
    second_page = repo.list_outbox_events_after(
        cursor_created_at_utc=FIXED_NOW,
        cursor_outbox_event_id="outbox-a",
        aggregate_types=("runtime",),
        source_families=("service_cycles",),
        batch_size=10,
    )

    assert [event.outbox_event_id for event in first_page] == [
        "outbox-a",
        "outbox-z",
    ]
    assert [event.outbox_event_id for event in second_page] == ["outbox-z"]
    assert first_page[0].payload["source_family"] == "service_cycles"


def test_get_outbox_event_cursor_resolves_legacy_checkpoint_position(
    repo: Any,
) -> None:
    _insert_outbox_projection_event(
        repo.engine,
        outbox_event_id="outbox-legacy",
        dedupe_key="dedupe-legacy",
        source_family="service_cycles",
        created_at_utc=FIXED_NOW,
    )

    assert repo.get_outbox_event_cursor("outbox-legacy") == (
        FIXED_NOW,
        "outbox-legacy",
    )
    assert repo.get_outbox_event_cursor("missing") is None


def test_checkpoint_load_save_and_upsert(repo: Any) -> None:
    assert repo.load_projection_checkpoint("runtime_projection") is None

    repo.save_projection_checkpoint(
        _checkpoint(
            last_outbox_event_id="outbox-001",
            status="running",
            metadata={"batch": 1},
        )
    )
    repo.save_projection_checkpoint(
        _checkpoint(
            last_outbox_event_id="outbox-002",
            status="caught_up",
            metadata={"batch": 2},
        )
    )

    loaded = repo.load_projection_checkpoint("runtime_projection")
    assert loaded == _checkpoint(
        last_outbox_event_id="outbox-002",
        status="caught_up",
        metadata={"batch": 2},
    )


def test_source_status_upsert_get_and_list_by_domain(repo: Any) -> None:
    assert (
        repo.get_projection_source_status(
            domain_name="runtime",
            source_family="heartbeat",
            source_identity="primary",
        )
        is None
    )

    repo.upsert_projection_source_status(
        _source_status(source_family="heartbeat", source_identity="primary")
    )
    repo.upsert_projection_source_status(
        _source_status(
            source_family="control_posture",
            source_identity="primary",
            source_watermark="30",
            projected_watermark="30",
        )
    )
    repo.upsert_projection_source_status(
        _source_status(
            source_family="heartbeat",
            source_identity="primary",
            source_watermark="40",
            projected_watermark="40",
            metadata={"last_projected_outbox_event_id": "outbox-040"},
        )
    )

    loaded = repo.get_projection_source_status(
        domain_name="runtime",
        source_family="heartbeat",
        source_identity="primary",
    )
    listed = repo.list_projection_source_statuses("runtime")

    assert loaded == _source_status(
        source_family="heartbeat",
        source_identity="primary",
        source_watermark="40",
        projected_watermark="40",
        metadata={"last_projected_outbox_event_id": "outbox-040"},
    )
    assert [item.identity_key for item in listed] == [
        ("runtime", "control_posture", "primary"),
        ("runtime", "heartbeat", "primary"),
    ]


def test_transaction_rolls_back_projection_state_writes_together(repo: Any) -> None:
    requirement = _requirement()
    status = _source_status(metadata={"last_projected_outbox_event_id": "outbox-001"})
    report = projections.evaluate_projection_readiness(
        domain_name="runtime",
        requirements=(requirement,),
        source_statuses=(status,),
        evaluated_at_utc=FIXED_NOW,
        source_registry_version="registry-1",
        outbox_dedupe_constraint_present=True,
    )

    with pytest.raises(RuntimeError, match="batch failed"):
        with repo.transaction() as tx_repo:
            tx_repo.append_outbox_event(_append_request())
            tx_repo.save_projection_checkpoint(_checkpoint())
            tx_repo.upsert_projection_source_status(status)
            tx_repo.save_domain_projection_status_from_readiness(report)
            raise RuntimeError("batch failed")

    assert _count(repo.engine, "system.outbox_event") == 0
    assert _count(repo.engine, "system.projection_checkpoint") == 0
    assert _count(repo.engine, "system.domain_projection_source_status") == 0
    assert _count(repo.engine, "system.domain_projection_status") == 0


def test_derived_domain_status_mapping_is_persisted_from_readiness(repo: Any) -> None:
    requirements = (
        _requirement(
            source_family="orders",
            source_identity="primary",
            requires_initial_import_complete=True,
            requires_active_write_path=True,
        ),
        _requirement(
            source_family="balances",
            source_identity="primary",
            requires_initial_import_complete=True,
        ),
    )
    statuses = (
        _source_status(
            source_family="orders",
            source_identity="primary",
            source_watermark="20",
            projected_watermark="20",
            lag_seconds=4,
            checked_at_utc=FIXED_NOW - timedelta(seconds=1),
            metadata={
                "initial_import_complete": True,
                "write_path": "dual_write",
                "last_projected_outbox_event_id": "outbox-020",
            },
        ),
        _source_status(
            source_family="balances",
            source_identity="primary",
            source_watermark="10",
            projected_watermark="10",
            lag_seconds=2,
            checked_at_utc=FIXED_NOW,
            metadata={
                "initial_import_complete": True,
                "last_projected_outbox_event_id": "outbox-010",
            },
        ),
    )
    for status in statuses:
        repo.upsert_projection_source_status(status)

    report = projections.evaluate_projection_readiness(
        domain_name="runtime",
        requirements=requirements,
        source_statuses=repo.list_projection_source_statuses("runtime"),
        evaluated_at_utc=FIXED_NOW,
        source_registry_version="registry-1",
        outbox_dedupe_constraint_present=True,
    )
    summary = repo.save_domain_projection_status_from_readiness(report)
    row = _domain_projection_status(repo.engine, "runtime")

    assert summary.ready_for_postgres is True
    assert row["target_store"] == "postgres"
    assert row["bridge_status"] == "ready"
    assert row["projection_status"] == "ready"
    assert json.loads(row["source_watermark"]) == [
        {
            "projected_watermark": "10",
            "source_family": "balances",
            "source_identity": "primary",
        },
        {
            "projected_watermark": "20",
            "source_family": "orders",
            "source_identity": "primary",
        },
    ]
    assert row["last_projected_outbox_event_id"] == "outbox-010"
    assert row["lag_seconds"] == 4
    assert row["ready_for_postgres"] is True
    assert row["checked_at_utc"] == FIXED_NOW
    assert row["metadata_json"]["authoritative"] is False
    assert row["metadata_json"]["blocker_codes"] == []
    assert repositories.PROJECTION_STATUS_IS_ROUTER_READINESS_AUTHORITY is False


@pytest.mark.parametrize(
    (
        "requirements_factory",
        "statuses_factory",
        "outbox_dedupe",
        "expected_status",
    ),
    (
        (lambda: (), lambda: (), True, "missing_requirements"),
        (lambda: (_requirement(),), lambda: (), True, "missing_sources"),
        (
            lambda: (_requirement(),),
            lambda: (_source_status(source_watermark="10", projected_watermark="9"),),
            True,
            "unprojected_sources",
        ),
        (
            lambda: (_requirement(max_lag_seconds=3),),
            lambda: (_source_status(lag_seconds=4),),
            True,
            "lagging_sources",
        ),
        (
            lambda: (_requirement(max_freshness_seconds=60),),
            lambda: (_source_status(checked_at_utc=FIXED_NOW - timedelta(minutes=2)),),
            True,
            "stale_sources",
        ),
        (
            lambda: (_requirement(requires_initial_import_complete=True),),
            lambda: (_source_status(metadata={"initial_import_complete": False}),),
            True,
            "initial_import_incomplete",
        ),
        (
            lambda: (_requirement(requires_active_write_path=True),),
            lambda: (_source_status(metadata={"write_path": "legacy_poll"}),),
            True,
            "write_path_inactive",
        ),
        (
            lambda: (_requirement(),),
            lambda: (_source_status(),),
            False,
            "outbox_dedupe_constraint_missing",
        ),
        (
            lambda: (_requirement(),),
            lambda: (_source_status(ready_for_postgres=False),),
            True,
            "not_ready_sources",
        ),
    ),
)
def test_derived_domain_status_blocks_each_readiness_failure_mode(
    repo: Any,
    requirements_factory: Callable[
        [],
        tuple[projections.ProjectionSourceRequirement, ...],
    ],
    statuses_factory: Callable[
        [],
        tuple[repositories.ProjectionSourceStatusRecord, ...],
    ],
    outbox_dedupe: bool,
    expected_status: str,
) -> None:
    requirements = requirements_factory()
    statuses = statuses_factory()
    for status in statuses:
        repo.upsert_projection_source_status(status)

    report = projections.evaluate_projection_readiness(
        domain_name="runtime",
        requirements=requirements,
        source_statuses=repo.list_projection_source_statuses("runtime"),
        evaluated_at_utc=FIXED_NOW,
        source_registry_version="registry-1",
        outbox_dedupe_constraint_present=outbox_dedupe,
    )
    repo.save_domain_projection_status_from_readiness(report)
    row = _domain_projection_status(repo.engine, "runtime")

    assert row["ready_for_postgres"] is False
    assert row["projection_status"] == expected_status
    assert expected_status in row["metadata_json"]["blocker_codes"]
    assert row["metadata_json"]["authoritative"] is False


def test_projection_state_storage_failures_are_redacted() -> None:
    from tradingx.persistence.repositories.projection_state import (
        PostgresProjectionStateRepository,
    )

    raw_dsn = "postgresql://tradingx:super-secret@127.0.0.1:5432/tradingx_test"

    class BrokenEngine:
        def connect(self) -> object:
            raise RuntimeError(f"connection failed for {raw_dsn} super-secret")

    broken_repo = PostgresProjectionStateRepository(engine=BrokenEngine(), dsn=raw_dsn)

    with pytest.raises(repositories.RepositoryStorageError) as exc_info:
        broken_repo.load_projection_checkpoint("runtime_projection")

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


def _append_request(
    *,
    dedupe_key: str = "runtime-1:heartbeat-1",
    payload: dict[str, object] | None = None,
) -> repositories.OutboxEventAppendRequest:
    return repositories.OutboxEventAppendRequest(
        aggregate_type="runtime",
        aggregate_id="runtime-1",
        event_type="heartbeat_observed",
        event_version=1,
        dedupe_key=dedupe_key,
        occurred_at_utc=FIXED_NOW - timedelta(seconds=5),
        payload=payload or {"heartbeat_id": "heartbeat-1"},
    )


def _checkpoint(
    *,
    last_outbox_event_id: str | None = "outbox-001",
    status: str = "caught_up",
    metadata: dict[str, object] | None = None,
) -> repositories.ProjectionCheckpointRecord:
    return repositories.ProjectionCheckpointRecord(
        projection_name="runtime_projection",
        last_outbox_event_id=last_outbox_event_id,
        last_processed_at_utc=FIXED_NOW,
        source_watermark="source-10",
        last_source_observed_at_utc=FIXED_NOW - timedelta(seconds=1),
        lag_seconds=1,
        status=status,
        metadata=metadata or {"batch": 1},
    )


def _requirement(
    *,
    domain_name: str = "runtime",
    source_family: str = "heartbeat",
    source_identity: str = "primary",
    is_mutable: bool = True,
    max_freshness_seconds: int | None = None,
    max_lag_seconds: int | None = None,
    requires_initial_import_complete: bool = False,
    requires_active_write_path: bool = False,
) -> projections.ProjectionSourceRequirement:
    return projections.ProjectionSourceRequirement(
        domain_name=domain_name,
        source_family=source_family,
        source_identity=source_identity,
        is_mutable=is_mutable,
        max_freshness_seconds=max_freshness_seconds,
        max_lag_seconds=max_lag_seconds,
        requires_initial_import_complete=requires_initial_import_complete,
        requires_active_write_path=requires_active_write_path,
    )


def _source_status(
    *,
    domain_name: str = "runtime",
    source_family: str = "heartbeat",
    source_identity: str = "primary",
    source_watermark: str | None = "10",
    projected_watermark: str | None = "10",
    lag_seconds: int | None = 1,
    is_mutable: bool = True,
    ready_for_postgres: bool = True,
    checked_at_utc: datetime = FIXED_NOW,
    metadata: dict[str, object] | None = None,
) -> repositories.ProjectionSourceStatusRecord:
    return repositories.ProjectionSourceStatusRecord(
        domain_name=domain_name,
        source_family=source_family,
        source_identity=source_identity,
        source_watermark=source_watermark,
        projected_watermark=projected_watermark,
        lag_seconds=lag_seconds,
        is_mutable=is_mutable,
        ready_for_postgres=ready_for_postgres,
        checked_at_utc=checked_at_utc,
        metadata=metadata or {},
    )


def _sequential_id_provider() -> Any:
    next_id = 0

    def provide_id() -> str:
        nonlocal next_id
        next_id += 1
        return f"outbox-{next_id:03d}"

    return provide_id


def _rows(
    engine: Engine,
    sql: str,
    params: dict[str, object] | None = None,
) -> tuple[dict[str, Any], ...]:
    with engine.connect() as connection:
        rows = connection.execute(text(sql), params or {}).mappings().all()
        return tuple(dict(row) for row in rows)


def _count(engine: Engine, table_name: str) -> int:
    rows = _rows(engine, f"SELECT count(*) AS count FROM {table_name}")
    return int(rows[0]["count"])


def _insert_outbox_projection_event(
    engine: Engine,
    *,
    outbox_event_id: str,
    dedupe_key: str,
    source_family: str,
    created_at_utc: datetime,
) -> None:
    payload = {
        "domain_name": "runtime",
        "source_family": source_family,
        "source_identity": f"artifact:{source_family}",
        "source_event_id": outbox_event_id,
        "source_watermark": f"{outbox_event_id}:hash",
        "event_family": "runtime",
        "event_type": "legacy.runtime.observed",
        "resource_type": source_family,
        "resource_id": outbox_event_id,
        "source_ref": f"artifact:{source_family}:{outbox_event_id}",
        "payload": {"status": "ok"},
        "metadata": {},
    }
    with engine.begin() as connection:
        connection.execute(
            text("""
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
                    :aggregate_id,
                    'legacy.runtime.observed',
                    1,
                    :occurred_at_utc,
                    :dedupe_key,
                    CAST(:payload_json AS JSONB),
                    :created_at_utc,
                    NULL
                )
                """),
            {
                "outbox_event_id": outbox_event_id,
                "aggregate_id": f"{source_family}/{outbox_event_id}",
                "occurred_at_utc": created_at_utc - timedelta(seconds=5),
                "dedupe_key": dedupe_key,
                "payload_json": json.dumps(payload, sort_keys=True),
                "created_at_utc": created_at_utc,
            },
        )


def _domain_projection_status(engine: Engine, domain_name: str) -> dict[str, Any]:
    rows = _rows(
        engine,
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
    assert len(rows) == 1
    return rows[0]
