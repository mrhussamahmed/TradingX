from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from tradingx.controlplane import projections, projectors, repositories

FIXED_NOW = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)


def test_projector_uses_family_version_checkpoints_so_deferred_rows_replay() -> None:
    service_event = _event(
        outbox_event_id="outbox-200",
        source_family="service_cycles",
        source_identity="artifact:paper_loop/service_cycles",
        source_event_id="cycle-1",
        source_watermark="cycle-1:hash",
        created_at_utc=FIXED_NOW + timedelta(seconds=2),
    )
    deferred_event = _event(
        outbox_event_id="outbox-100",
        source_family="market_sessions",
        source_identity="artifact:operator_platform/market_sessions",
        source_event_id="session-1",
        source_watermark="session-1:hash",
        created_at_utc=FIXED_NOW + timedelta(seconds=1),
    )
    uow = FakeRuntimeProjectorUnitOfWork(
        events=(service_event, deferred_event),
        statuses=(
            _status(
                source_family="service_cycles",
                source_identity="artifact:paper_loop/service_cycles",
                source_watermark="cycle-1:hash",
            ),
            _status(
                source_family="market_sessions",
                source_identity="artifact:operator_platform/market_sessions",
                source_watermark="session-1:hash",
            ),
        ),
        requirements=(),
    )

    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
        full_requirements=uow.projection_repo.requirements,
    )
    runtime_projector.run_once(batch_size=10)

    assert (
        "runtime_projection:runtime:service_cycles:v1"
        in uow.projection_repo.checkpoints
    )
    assert (
        "runtime_projection:runtime:market_sessions:v1"
        not in uow.projection_repo.checkpoints
    )
    assert all(
        call["source_families"] != ("market_sessions",)
        for call in uow.projection_repo.outbox_read_calls
    )

    later_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
        supported_source_families_by_domain={
            "runtime": ("market_sessions",),
            "control_posture": (),
        },
    )
    later_projector.run_once(batch_size=10)

    assert (
        "runtime_projection:runtime:market_sessions:v1"
        in uow.projection_repo.checkpoints
    )
    assert any(
        call["source_families"] == ("market_sessions",)
        and call["cursor_created_at_utc"] is None
        for call in uow.projection_repo.outbox_read_calls
    )
    market_status = uow.projection_repo.statuses[
        ("runtime", "market_sessions", "artifact:operator_platform/market_sessions")
    ]
    assert market_status.projected_watermark == "session-1:hash"


def test_persisted_domain_status_uses_full_requirements_not_filtered_subset() -> None:
    uow = FakeRuntimeProjectorUnitOfWork(
        events=(
            _event(
                source_family="service_cycles",
                source_identity="artifact:paper_loop/service_cycles",
                source_event_id="cycle-1",
                source_watermark="cycle-1:hash",
            ),
        ),
        statuses=(
            _status(
                source_family="service_cycles",
                source_identity="artifact:paper_loop/service_cycles",
                source_watermark="cycle-1:hash",
            ),
            _status(
                source_family="market_sessions",
                source_identity="artifact:operator_platform/market_sessions",
                source_watermark="session-1:hash",
            ),
        ),
        requirements=(
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

    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
        full_requirements=uow.projection_repo.requirements,
    )
    result = runtime_projector.run_once(batch_size=10)

    assert result.filtered_readiness_by_domain["runtime"].ready_for_postgres is True
    persisted = uow.projection_repo.domain_statuses["runtime"]
    assert persisted.ready_for_postgres is False
    assert persisted.projection_status == "unprojected_sources"
    assert persisted.metadata["requirement_count"] == 2


def test_control_posture_status_is_evaluated_as_its_own_domain() -> None:
    uow = FakeRuntimeProjectorUnitOfWork(
        events=(
            _event(
                domain_name="control_posture",
                outbox_event_id="outbox-control-1",
                aggregate_id="control_posture/live_config",
                event_type="legacy.live_config.observed",
                source_family="live_config_env",
                source_identity="config:local",
                source_event_id="live-config",
                source_watermark="live-config:hash",
                payload={"requested_mode": "live"},
            ),
        ),
        statuses=(
            _status(
                domain_name="control_posture",
                source_family="live_config_env",
                source_identity="config:local",
                source_watermark="live-config:hash",
            ),
            _status(
                domain_name="control_posture",
                source_family="operator_control_state",
                source_identity="data:control/state",
                source_watermark="control-state:hash",
            ),
        ),
        requirements=(
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

    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
        full_requirements=uow.projection_repo.requirements,
    )
    runtime_projector.run_once(batch_size=10)

    assert "runtime" not in uow.projection_repo.domain_statuses
    persisted = uow.projection_repo.domain_statuses["control_posture"]
    assert persisted.ready_for_postgres is False
    assert persisted.projection_status == "unprojected_sources"
    live_status = uow.projection_repo.statuses[
        ("control_posture", "live_config_env", "config:local")
    ]
    assert live_status.projected_watermark == "live-config:hash"


def test_control_posture_maps_legacy_config_safe_summary_live_ready_fields() -> None:
    uow = FakeRuntimeProjectorUnitOfWork(
        events=(
            _event(
                domain_name="control_posture",
                outbox_event_id="outbox-control-1",
                aggregate_id="control_posture/live_config",
                event_type="legacy.live_config.observed",
                source_family="live_config_env",
                source_identity="config:local",
                source_event_id="local-config",
                source_watermark="local-config:hash",
                payload={
                    "requested_broker_mode": "live",
                    "live_trading_enabled": True,
                    "manual_kill_switch_active": False,
                    "dry_run": False,
                },
            ),
        ),
        statuses=(
            _status(
                domain_name="control_posture",
                source_family="live_config_env",
                source_identity="config:local",
                source_watermark="local-config:hash",
            ),
        ),
        requirements=(),
    )

    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )
    runtime_projector.run_once(batch_size=10)

    snapshots = tuple(uow.runtime_repo.control_posture_snapshots.values())
    assert len(snapshots) == 1
    assert snapshots[0].requested_mode == "live"
    assert snapshots[0].effective_mode == "live"
    assert snapshots[0].live_allowed is True
    assert snapshots[0].governance_status == "live_allowed"
    assert snapshots[0].blockers == ()


def test_control_posture_noop_fingerprint_ignores_source_family() -> None:
    first = _event(
        domain_name="control_posture",
        outbox_event_id="outbox-control-1",
        aggregate_id="control_posture/live_config",
        event_type="legacy.live_config.observed",
        source_family="live_config_env",
        source_identity="config:local",
        source_event_id="local-config",
        source_watermark="local-config:hash",
        payload={"requested_mode": "live"},
        created_at_utc=FIXED_NOW,
    )
    second = _event(
        domain_name="control_posture",
        outbox_event_id="outbox-control-2",
        aggregate_id="control_posture/market_data",
        event_type="legacy.market_data_posture.observed",
        source_family="market_data_posture",
        source_identity="runtime:market_data",
        source_event_id="market-data-posture",
        source_watermark="market-data-posture:hash",
        payload={"requested_mode": "live"},
        created_at_utc=FIXED_NOW + timedelta(seconds=1),
    )
    uow = FakeRuntimeProjectorUnitOfWork(
        events=(first, second),
        statuses=(
            _status(
                domain_name="control_posture",
                source_family="live_config_env",
                source_identity="config:local",
                source_watermark="local-config:hash",
            ),
            _status(
                domain_name="control_posture",
                source_family="market_data_posture",
                source_identity="runtime:market_data",
                source_watermark="market-data-posture:hash",
            ),
        ),
        requirements=(),
    )

    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )
    runtime_projector.run_once(batch_size=10)

    snapshots = tuple(uow.runtime_repo.control_posture_snapshots.values())
    assert len(snapshots) == 1
    assert snapshots[0].resource_version == 1


def test_runtime_heartbeat_projection_is_idempotent_and_conservative() -> None:
    event = _event(
        source_family="service_cycles",
        source_identity="artifact:paper_loop/service_cycles",
        source_event_id="cycle-1",
        source_watermark="cycle-1:hash",
        payload={"cycle_id": "cycle-1"},
    )
    uow = FakeRuntimeProjectorUnitOfWork(
        events=(event,),
        statuses=(
            _status(
                source_family="service_cycles",
                source_identity="artifact:paper_loop/service_cycles",
                source_watermark="cycle-1:hash",
            ),
        ),
        requirements=(),
    )
    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )

    runtime_projector.run_once(batch_size=10)
    runtime_projector.run_once(batch_size=10)

    heartbeats = tuple(uow.runtime_repo.heartbeats.values())
    assert len(heartbeats) == 1
    assert heartbeats[0].heartbeat_state == "unknown"
    assert heartbeats[0].observed_at_utc == event.occurred_at_utc
    assert heartbeats[0].source_ref == (
        "artifact:paper_loop/service_cycles:cycle-1"
    )


def test_control_posture_fails_closed_and_noop_refresh_does_not_churn() -> None:
    first = _event(
        domain_name="control_posture",
        outbox_event_id="outbox-control-1",
        aggregate_id="control_posture/live_config",
        event_type="legacy.live_config.observed",
        source_family="live_config_env",
        source_identity="config:local",
        source_event_id="live-config-1",
        source_watermark="live-config-1:hash",
        payload={"requested_mode": "live"},
        created_at_utc=FIXED_NOW,
    )
    second = _event(
        domain_name="control_posture",
        outbox_event_id="outbox-control-2",
        aggregate_id="control_posture/live_config",
        event_type="legacy.live_config.observed",
        source_family="live_config_env",
        source_identity="config:local",
        source_event_id="live-config-2",
        source_watermark="live-config-2:hash",
        payload={"requested_mode": "live"},
        created_at_utc=FIXED_NOW + timedelta(seconds=1),
    )
    uow = FakeRuntimeProjectorUnitOfWork(
        events=(first, second),
        statuses=(
            _status(
                domain_name="control_posture",
                source_family="live_config_env",
                source_identity="config:local",
                source_watermark="live-config-2:hash",
            ),
        ),
        requirements=(),
    )
    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )

    runtime_projector.run_once(batch_size=1)
    runtime_projector.run_once(batch_size=1)

    snapshots = tuple(uow.runtime_repo.control_posture_snapshots.values())
    assert len(snapshots) == 1
    assert snapshots[0].live_allowed is False
    assert snapshots[0].governance_status == "blocked"
    assert snapshots[0].resource_version == 1
    assert uow.runtime_repo.blockers[snapshots[0].posture_id]
    checkpoint = uow.projection_repo.checkpoints[
        "runtime_projection:control_posture:live_config_env:v1"
    ]
    assert checkpoint.last_outbox_event_id == "outbox-control-2"


def test_materialization_failure_rolls_back_checkpoint_and_projected_status() -> None:
    uow = FakeRuntimeProjectorUnitOfWork(
        events=(
            _event(
                source_family="service_cycles",
                source_identity="artifact:paper_loop/service_cycles",
                source_event_id="cycle-1",
                source_watermark="cycle-1:hash",
            ),
        ),
        statuses=(
            _status(
                source_family="service_cycles",
                source_identity="artifact:paper_loop/service_cycles",
                source_watermark="cycle-1:hash",
            ),
        ),
        requirements=(),
        fail_on_heartbeat=True,
    )
    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(RuntimeError, match="heartbeat write failed"):
        runtime_projector.run_once(batch_size=10)

    assert uow.projection_repo.checkpoints == {}
    status = uow.projection_repo.statuses[
        ("runtime", "service_cycles", "artifact:paper_loop/service_cycles")
    ]
    assert status.projected_watermark is None
    assert uow.runtime_repo.heartbeats == {}


def test_legacy_checkpoint_without_cursor_metadata_resolves_last_event_cursor() -> None:
    first = _event(
        outbox_event_id="outbox-001",
        source_family="service_cycles",
        source_identity="artifact:paper_loop/service_cycles",
        source_event_id="cycle-1",
        source_watermark="cycle-1:hash",
        created_at_utc=FIXED_NOW,
    )
    second = _event(
        outbox_event_id="outbox-002",
        source_family="service_cycles",
        source_identity="artifact:paper_loop/service_cycles",
        source_event_id="cycle-2",
        source_watermark="cycle-2:hash",
        created_at_utc=FIXED_NOW + timedelta(seconds=1),
    )
    projection_name = "runtime_projection:runtime:service_cycles:v1"
    uow = FakeRuntimeProjectorUnitOfWork(
        events=(first, second),
        statuses=(
            _status(
                source_family="service_cycles",
                source_identity="artifact:paper_loop/service_cycles",
                source_watermark="cycle-2:hash",
            ),
        ),
        requirements=(),
    )
    uow.projection_repo.checkpoints[projection_name] = (
        repositories.ProjectionCheckpointRecord(
            projection_name=projection_name,
            last_outbox_event_id="outbox-001",
            last_processed_at_utc=FIXED_NOW,
            source_watermark="cycle-1:hash",
            last_source_observed_at_utc=FIXED_NOW - timedelta(seconds=5),
            lag_seconds=5,
            status="running",
            metadata={},
        )
    )

    runtime_projector = projectors.RuntimeProjector(
        unit_of_work=uow,
        clock=lambda: FIXED_NOW,
    )
    runtime_projector.run_once(batch_size=10)

    assert any(
        call["cursor_created_at_utc"] == FIXED_NOW
        and call["cursor_outbox_event_id"] == "outbox-001"
        for call in uow.projection_repo.outbox_read_calls
    )
    assert tuple(uow.runtime_repo.heartbeats.values())[0].source_ref == (
        "artifact:paper_loop/service_cycles:cycle-2"
    )


class FakeRuntimeProjectorUnitOfWork:
    def __init__(
        self,
        *,
        events: tuple[repositories.OutboxProjectionEvent, ...],
        statuses: tuple[repositories.ProjectionSourceStatusRecord, ...],
        requirements: tuple[projections.ProjectionSourceRequirement, ...],
        fail_on_heartbeat: bool = False,
    ) -> None:
        self.projection_repo = FakeProjectionRepository(
            events=events,
            statuses=statuses,
            requirements=requirements,
        )
        self.runtime_repo = FakeRuntimeProjectionRepository(
            fail_on_heartbeat=fail_on_heartbeat
        )

    @contextmanager
    def transaction(
        self,
    ) -> Iterator[
        tuple[FakeProjectionRepository, FakeRuntimeProjectionRepository]
    ]:
        projection_snapshot = self.projection_repo.snapshot()
        runtime_snapshot = self.runtime_repo.snapshot()
        try:
            yield self.projection_repo, self.runtime_repo
        except Exception:
            self.projection_repo.restore(projection_snapshot)
            self.runtime_repo.restore(runtime_snapshot)
            raise


class FakeProjectionRepository:
    def __init__(
        self,
        *,
        events: tuple[repositories.OutboxProjectionEvent, ...],
        statuses: tuple[repositories.ProjectionSourceStatusRecord, ...],
        requirements: tuple[projections.ProjectionSourceRequirement, ...],
    ) -> None:
        self.events = events
        self.statuses = {status.identity_key: status for status in statuses}
        self.requirements = requirements
        self.checkpoints: dict[str, repositories.ProjectionCheckpointRecord] = {}
        self.domain_statuses: dict[str, repositories.ProjectionStatusSummary] = {}
        self.outbox_read_calls: list[dict[str, object]] = []

    def snapshot(self) -> dict[str, object]:
        return {
            "statuses": deepcopy(self.statuses),
            "checkpoints": deepcopy(self.checkpoints),
            "domain_statuses": deepcopy(self.domain_statuses),
            "outbox_read_calls": deepcopy(self.outbox_read_calls),
        }

    def restore(self, snapshot: Mapping[str, object]) -> None:
        self.statuses = deepcopy(snapshot["statuses"])
        self.checkpoints = deepcopy(snapshot["checkpoints"])
        self.domain_statuses = deepcopy(snapshot["domain_statuses"])
        self.outbox_read_calls = deepcopy(snapshot["outbox_read_calls"])

    def load_projection_checkpoint(
        self,
        projection_name: str,
    ) -> repositories.ProjectionCheckpointRecord | None:
        return self.checkpoints.get(projection_name)

    def save_projection_checkpoint(
        self,
        record: repositories.ProjectionCheckpointRecord,
    ) -> None:
        self.checkpoints[record.projection_name] = record

    def list_outbox_events_after(
        self,
        *,
        cursor_created_at_utc: datetime | None,
        cursor_outbox_event_id: str | None,
        aggregate_types: tuple[str, ...],
        source_families: tuple[str, ...],
        batch_size: int,
    ) -> tuple[repositories.OutboxProjectionEvent, ...]:
        self.outbox_read_calls.append(
            {
                "cursor_created_at_utc": cursor_created_at_utc,
                "cursor_outbox_event_id": cursor_outbox_event_id,
                "aggregate_types": aggregate_types,
                "source_families": source_families,
                "batch_size": batch_size,
            }
        )
        rows = tuple(
            event
            for event in sorted(
                self.events,
                key=lambda item: (item.created_at_utc, item.outbox_event_id),
            )
            if event.aggregate_type in aggregate_types
            and str(event.payload["source_family"]) in source_families
            and _after_cursor(event, cursor_created_at_utc, cursor_outbox_event_id)
        )
        return rows[:batch_size]

    def get_outbox_event_cursor(
        self,
        outbox_event_id: str,
    ) -> tuple[datetime, str] | None:
        for event in self.events:
            if event.outbox_event_id == outbox_event_id:
                return (event.created_at_utc, event.outbox_event_id)
        return None

    def get_projection_source_status(
        self,
        *,
        domain_name: str,
        source_family: str,
        source_identity: str,
    ) -> repositories.ProjectionSourceStatusRecord | None:
        return self.statuses.get((domain_name, source_family, source_identity))

    def upsert_projection_source_status(
        self,
        record: repositories.ProjectionSourceStatusRecord,
    ) -> None:
        self.statuses[record.identity_key] = record

    def list_projection_source_statuses(
        self,
        domain_name: str,
    ) -> tuple[repositories.ProjectionSourceStatusRecord, ...]:
        return tuple(
            status
            for status in self.statuses.values()
            if status.domain_name == domain_name
        )

    def save_domain_projection_status_from_readiness(
        self,
        report: projections.ProjectionReadinessReport,
    ) -> repositories.ProjectionStatusSummary:
        summary = projections.projection_status_from_readiness(report)
        self.domain_statuses[summary.domain_name] = summary
        return summary


class FakeRuntimeProjectionRepository:
    def __init__(self, *, fail_on_heartbeat: bool = False) -> None:
        self.fail_on_heartbeat = fail_on_heartbeat
        self.heartbeats: dict[str, repositories.RuntimeHeartbeat] = {}
        self.control_posture_snapshots: dict[
            str,
            repositories.ControlPostureSnapshot,
        ] = {}
        self.blockers: dict[str, tuple[repositories.ControlPostureBlocker, ...]] = {}

    def snapshot(self) -> dict[str, object]:
        return {
            "heartbeats": deepcopy(self.heartbeats),
            "control_posture_snapshots": deepcopy(self.control_posture_snapshots),
            "blockers": deepcopy(self.blockers),
        }

    def restore(self, snapshot: Mapping[str, object]) -> None:
        self.heartbeats = deepcopy(snapshot["heartbeats"])
        self.control_posture_snapshots = deepcopy(
            snapshot["control_posture_snapshots"]
        )
        self.blockers = deepcopy(snapshot["blockers"])

    def upsert_runtime_heartbeat(
        self,
        record: repositories.RuntimeHeartbeat,
    ) -> None:
        if self.fail_on_heartbeat:
            raise RuntimeError("heartbeat write failed")
        existing = self.heartbeats.get(record.heartbeat_id)
        if existing is not None and existing != record:
            raise repositories.RepositoryConflictError("heartbeat conflict")
        self.heartbeats[record.heartbeat_id] = record

    def get_latest_control_posture_snapshot(
        self,
    ) -> repositories.ControlPostureSnapshot | None:
        if not self.control_posture_snapshots:
            return None
        return sorted(
            self.control_posture_snapshots.values(),
            key=lambda item: (item.observed_at_utc, item.posture_id),
            reverse=True,
        )[0]

    def upsert_control_posture_snapshot(
        self,
        record: repositories.ControlPostureSnapshot,
    ) -> None:
        existing = self.control_posture_snapshots.get(record.posture_id)
        if existing is not None and existing != record:
            raise repositories.RepositoryConflictError("posture conflict")
        self.control_posture_snapshots[record.posture_id] = record

    def replace_control_posture_blockers(
        self,
        posture_id: str,
        blockers: tuple[repositories.ControlPostureBlocker, ...],
    ) -> None:
        self.blockers[posture_id] = blockers


def _event(
    *,
    domain_name: str = "runtime",
    outbox_event_id: str = "outbox-001",
    aggregate_id: str = "service_cycle/cycle-1",
    event_type: str = "legacy.service_cycle.observed",
    source_family: str = "service_cycles",
    source_identity: str = "artifact:paper_loop/service_cycles",
    source_event_id: str = "cycle-1",
    source_watermark: str = "cycle-1:hash",
    payload: dict[str, object] | None = None,
    created_at_utc: datetime = FIXED_NOW,
) -> repositories.OutboxProjectionEvent:
    occurred_at = created_at_utc - timedelta(seconds=5)
    return repositories.OutboxProjectionEvent(
        outbox_event_id=outbox_event_id,
        aggregate_type=domain_name,
        aggregate_id=aggregate_id,
        event_type=event_type,
        event_version=1,
        occurred_at_utc=occurred_at,
        dedupe_key=(
            f"legacy:{domain_name}:{source_family}:"
            f"{source_identity}:{source_event_id}"
        ),
        payload={
            "domain_name": domain_name,
            "source_family": source_family,
            "source_identity": source_identity,
            "source_event_id": source_event_id,
            "source_watermark": source_watermark,
            "event_family": domain_name,
            "event_type": event_type,
            "resource_type": aggregate_id.split("/", 1)[0],
            "resource_id": aggregate_id.split("/", 1)[-1],
            "source_ref": f"{source_identity}:{source_event_id}",
            "payload": payload or {},
            "metadata": {"source_path": f"{source_event_id}.json"},
        },
        created_at_utc=created_at_utc,
    )


def _status(
    *,
    domain_name: str = "runtime",
    source_family: str,
    source_identity: str,
    source_watermark: str,
    projected_watermark: str | None = None,
    checked_at_utc: datetime = FIXED_NOW,
) -> repositories.ProjectionSourceStatusRecord:
    return repositories.ProjectionSourceStatusRecord(
        domain_name=domain_name,
        source_family=source_family,
        source_identity=source_identity,
        source_watermark=source_watermark,
        projected_watermark=projected_watermark,
        lag_seconds=None,
        is_mutable=True,
        ready_for_postgres=True,
        checked_at_utc=checked_at_utc,
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


def _after_cursor(
    event: repositories.OutboxProjectionEvent,
    cursor_created_at_utc: datetime | None,
    cursor_outbox_event_id: str | None,
) -> bool:
    if cursor_created_at_utc is None:
        return True
    return event.created_at_utc > cursor_created_at_utc or (
        event.created_at_utc == cursor_created_at_utc
        and cursor_outbox_event_id is not None
        and event.outbox_event_id > cursor_outbox_event_id
    )
