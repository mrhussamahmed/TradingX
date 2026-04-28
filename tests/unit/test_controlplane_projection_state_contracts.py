from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from tradingx.controlplane import projections, repositories
from tradingx.persistence.repositories.postgres import PostgresControlPlaneRepository

SECRET_DSN = "postgresql://tradingx:super-secret@db.internal:5432/tradingx"


def test_slice3_dataclasses_expose_natural_keys() -> None:
    observed_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    append = repositories.OutboxEventAppendRequest(
        aggregate_type="runtime",
        aggregate_id="runtime-1",
        event_type="heartbeat_observed",
        event_version=1,
        dedupe_key="runtime-1:heartbeat-1",
        occurred_at_utc=observed_at,
        payload={"heartbeat_id": "heartbeat-1"},
    )
    checkpoint = repositories.ProjectionCheckpointRecord(
        projection_name="runtime_projection",
        last_outbox_event_id="outbox-1",
        last_processed_at_utc=observed_at,
        source_watermark="10",
        last_source_observed_at_utc=observed_at,
        lag_seconds=1,
        status="caught_up",
        metadata={"batch": 1},
    )
    source_status = _source_status(
        domain_name="runtime",
        source_family="heartbeat",
        source_identity="primary",
    )

    assert append.dedupe_key == "runtime-1:heartbeat-1"
    assert repositories.OUTBOX_APPEND_REPOSITORY_GENERATED_FIELDS == (
        "outbox_event_id",
        "created_at_utc",
    )
    assert "outbox_event_id" not in append.__dataclass_fields__
    assert "created_at_utc" not in append.__dataclass_fields__
    assert checkpoint.identity_key == "runtime_projection"
    assert source_status.identity_key == ("runtime", "heartbeat", "primary")


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("aggregate_id", ""),
        ("event_type", " "),
        ("dedupe_key", ""),
        ("event_version", 0),
        ("event_version", -1),
    ),
)
def test_outbox_append_request_rejects_invalid_identity_fields(
    field_name: str,
    bad_value: object,
) -> None:
    values: dict[str, object] = {
        "aggregate_type": "runtime",
        "aggregate_id": "runtime-1",
        "event_type": "heartbeat_observed",
        "event_version": 1,
        "dedupe_key": "runtime-1:heartbeat-1",
        "occurred_at_utc": datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        "payload": {"heartbeat_id": "heartbeat-1"},
    }
    values[field_name] = bad_value

    with pytest.raises(ValueError, match=field_name):
        repositories.OutboxEventAppendRequest(**values)  # type: ignore[arg-type]


def test_projection_source_status_boundary_lists_by_domain() -> None:
    assert hasattr(
        repositories.ProjectionSourceStatusBoundary,
        "list_projection_source_statuses",
    )


def test_empty_source_requirement_registry_blocks_readiness() -> None:
    report = projections.evaluate_projection_readiness(
        domain_name="runtime",
        requirements=(),
        source_statuses=(),
        evaluated_at_utc=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        source_registry_version="registry-1",
        outbox_dedupe_constraint_present=True,
    )

    assert report.ready_for_postgres is False
    assert _blocker_codes(report.blockers) == ("missing_requirements",)


@pytest.mark.parametrize(
    ("status_factory", "requirement_factory", "expected_code"),
    (
        (
            lambda: None,
            lambda: _requirement(),
            "missing_sources",
        ),
        (
            lambda: _source_status(ready_for_postgres=False),
            lambda: _requirement(),
            "not_ready_sources",
        ),
        (
            lambda: _source_status(source_watermark="10", projected_watermark="9"),
            lambda: _requirement(),
            "unprojected_sources",
        ),
        (
            lambda: _source_status(lag_seconds=31),
            lambda: _requirement(max_lag_seconds=30),
            "lagging_sources",
        ),
        (
            lambda: _source_status(
                checked_at_utc=datetime(2026, 4, 24, 11, 58, tzinfo=UTC)
            ),
            lambda: _requirement(max_freshness_seconds=60),
            "stale_sources",
        ),
        (
            lambda: _source_status(metadata={"initial_import_complete": False}),
            lambda: _requirement(requires_initial_import_complete=True),
            "initial_import_incomplete",
        ),
        (
            lambda: _source_status(metadata={"initial_import_complete": True}),
            lambda: _requirement(requires_active_write_path=True),
            "write_path_inactive",
        ),
    ),
)
def test_readiness_blocks_each_source_failure_mode(
    status_factory: Callable[
        [],
        repositories.ProjectionSourceStatusRecord | None,
    ],
    requirement_factory: Callable[[], projections.ProjectionSourceRequirement],
    expected_code: str,
) -> None:
    status = status_factory()
    requirement = requirement_factory()
    source_statuses = () if status is None else (status,)

    report = projections.evaluate_projection_readiness(
        domain_name="runtime",
        requirements=(requirement,),
        source_statuses=source_statuses,
        evaluated_at_utc=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        source_registry_version="registry-1",
        outbox_dedupe_constraint_present=True,
    )

    assert expected_code in _blocker_codes(report.blockers)
    assert report.ready_for_postgres is False


def test_missing_outbox_dedupe_constraint_blocks_domain() -> None:
    requirement = _requirement(
        requires_initial_import_complete=True,
        requires_active_write_path=True,
    )
    status = _source_status(
        metadata={
            "initial_import_complete": True,
            "write_path": "active_bridge",
        },
    )

    report = projections.evaluate_projection_readiness(
        domain_name="runtime",
        requirements=(requirement,),
        source_statuses=(status,),
        evaluated_at_utc=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        source_registry_version="registry-1",
        outbox_dedupe_constraint_present=False,
    )

    assert _blocker_codes(report.blockers) == ("outbox_dedupe_constraint_missing",)


def test_ready_report_maps_to_deterministic_projection_status_summary() -> None:
    evaluated_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
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
            checked_at_utc=evaluated_at - timedelta(seconds=1),
            metadata={
                "initial_import_complete": True,
                "write_path": "dual_write",
                "last_projected_outbox_event_id": "outbox-20",
            },
        ),
        _source_status(
            source_family="balances",
            source_identity="primary",
            source_watermark="10",
            projected_watermark="10",
            lag_seconds=2,
            checked_at_utc=evaluated_at,
            metadata={
                "initial_import_complete": True,
                "last_projected_outbox_event_id": "outbox-10",
            },
        ),
    )

    report = projections.evaluate_projection_readiness(
        domain_name="runtime",
        requirements=requirements,
        source_statuses=statuses,
        evaluated_at_utc=evaluated_at,
        source_registry_version="registry-1",
        outbox_dedupe_constraint_present=True,
    )
    summary = projections.projection_status_from_readiness(report)

    assert report.ready_for_postgres is True
    assert summary.domain_name == "runtime"
    assert summary.target_store == "postgres"
    assert summary.bridge_status == "ready"
    assert summary.projection_status == "ready"
    assert json.loads(summary.source_watermark or "[]") == [
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
    assert summary.last_projected_outbox_event_id == "outbox-10"
    assert summary.lag_seconds == 4
    assert summary.ready_for_postgres is True
    assert summary.checked_at_utc == evaluated_at
    assert summary.metadata["authoritative"] is False
    assert summary.metadata["blocker_codes"] == ()
    assert summary.metadata["requirement_count"] == 2
    assert summary.metadata["ready_source_count"] == 2
    assert summary.metadata["source_registry_version"] == "registry-1"
    assert repositories.PROJECTION_STATUS_IS_ROUTER_READINESS_AUTHORITY is False


def test_blocked_report_uses_priority_projection_status_and_metadata() -> None:
    report = projections.evaluate_projection_readiness(
        domain_name="runtime",
        requirements=(_requirement(),),
        source_statuses=(
            _source_status(
                ready_for_postgres=False,
                source_watermark="10",
                projected_watermark="9",
            ),
        ),
        evaluated_at_utc=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        source_registry_version="registry-1",
        outbox_dedupe_constraint_present=True,
    )

    summary = projections.projection_status_from_readiness(report)

    assert summary.ready_for_postgres is False
    assert summary.bridge_status == "not_required"
    assert summary.projection_status == "unprojected_sources"
    assert summary.source_watermark == "9"
    assert summary.metadata["authoritative"] is False
    assert summary.metadata["blocker_codes"] == (
        "unprojected_sources",
        "not_ready_sources",
    )


def test_source_summary_ready_flag_uses_full_readiness_rules() -> None:
    report = projections.evaluate_projection_readiness(
        domain_name="runtime",
        requirements=(_requirement(),),
        source_statuses=(
            _source_status(
                ready_for_postgres=True,
                source_watermark="10",
                projected_watermark="9",
            ),
        ),
        evaluated_at_utc=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        source_registry_version="registry-1",
        outbox_dedupe_constraint_present=True,
    )

    summary = projections.projection_status_from_readiness(report)
    source_summary = summary.metadata["source_summaries"][0]

    assert source_summary["row_ready_for_postgres"] is True
    assert source_summary["ready_for_postgres"] is False
    assert source_summary["blocker_codes"] == ("unprojected_sources",)


def test_postgres_read_repository_remains_read_side_only() -> None:
    repo = PostgresControlPlaneRepository(engine=object(), dsn=SECRET_DSN)

    assert not isinstance(repo, repositories.OutboxAppendBoundary)
    assert not isinstance(repo, repositories.ProjectionCheckpointBoundary)
    assert not isinstance(repo, repositories.ProjectionSourceStatusBoundary)


def test_outbox_conflict_error_redacts_details() -> None:
    error = repositories.OutboxAppendConflictError.from_conflict(
        dedupe_key="runtime-1:heartbeat-1",
        dsn=SECRET_DSN,
        details=f"conflict from {SECRET_DSN} super-secret",
    )

    inspected = (
        str(error),
        repr(error),
        error.args,
        error.__cause__,
        error.__context__,
    )
    for value in inspected:
        assert SECRET_DSN not in str(value)
        assert "super-secret" not in str(value)


def test_repository_public_exports_include_projection_state_contract_names() -> None:
    assert "OUTBOX_APPEND_REPOSITORY_GENERATED_FIELDS" in repositories.__all__
    assert "RepositoryConflictError" in repositories.__all__
    assert "OutboxAppendConflictError" in repositories.__all__


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
    checked_at_utc: datetime | None = None,
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
        checked_at_utc=checked_at_utc or datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        metadata=metadata or {},
    )


def _blocker_codes(
    blockers: Sequence[projections.ProjectionReadinessBlocker],
) -> tuple[str, ...]:
    return tuple(blocker.code for blocker in blockers)
