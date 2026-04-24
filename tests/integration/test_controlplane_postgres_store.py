from __future__ import annotations

import os

import pytest

from tradingx.persistence import postgres

MANAGED_SCHEMAS = (
    "access",
    "commanding",
    "runtime",
    "incidents",
    "portfolio",
    "validation",
    "investigations",
    "documents",
    "system",
)

REQUIRED_TABLES = (
    ("access", "operator_account"),
    ("access", "operator_role_binding"),
    ("access", "command_session"),
    ("access", "command_session_event"),
    ("commanding", "command"),
    ("commanding", "command_attempt"),
    ("commanding", "command_idempotency_record"),
    ("commanding", "command_event"),
    ("commanding", "command_result_snapshot"),
    ("runtime", "runtime_instance"),
    ("runtime", "runtime_state_snapshot"),
    ("runtime", "runtime_heartbeat"),
    ("runtime", "scheduler_run"),
    ("runtime", "market_day_run"),
    ("runtime", "control_posture_snapshot"),
    ("runtime", "control_posture_blocker"),
    ("incidents", "incident"),
    ("incidents", "incident_event"),
    ("incidents", "incident_acknowledgement"),
    ("portfolio", "portfolio_snapshot"),
    ("portfolio", "portfolio_timeseries_point"),
    ("portfolio", "position_snapshot"),
    ("portfolio", "exposure_snapshot"),
    ("portfolio", "benchmark_timeseries_point"),
    ("portfolio", "attribution_snapshot"),
    ("portfolio", "execution_quality_snapshot"),
    ("validation", "validation_run"),
    ("validation", "validation_candidate"),
    ("validation", "validation_criterion_result"),
    ("validation", "validation_readiness_blocker"),
    ("validation", "pbo_report"),
    ("validation", "cpcv_cohort"),
    ("investigations", "replay_run"),
    ("investigations", "replay_event"),
    ("investigations", "investigation_workspace"),
    ("investigations", "drift_analysis_snapshot"),
    ("documents", "document"),
    ("documents", "document_revision"),
    ("documents", "document_object_ref"),
    ("system", "outbox_event"),
    ("system", "projection_checkpoint"),
    ("system", "domain_projection_source_status"),
    ("system", "domain_projection_status"),
)


def _postgres_dsn() -> str:
    dsn = os.environ.get("TRADINGX_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("TRADINGX_TEST_POSTGRES_DSN is not configured")
    return dsn


def test_reset_guard_rejects_non_test_database_names() -> None:
    with pytest.raises(postgres.PostgresResetSafetyError, match="tradingx_test"):
        postgres.assert_postgres_test_reset_allowed(
            "postgresql://tradingx:secret@127.0.0.1:5432/tradingx_prod"
        )


def test_initial_migration_upgrade_downgrade_reupgrade_and_catalog() -> None:
    dsn = _postgres_dsn()
    engine = postgres.build_postgres_engine(postgres.PostgresSettings(dsn=dsn))

    postgres.reset_postgres_test_database(engine, dsn=dsn)
    assert postgres.inspect_postgres_schemas(engine, MANAGED_SCHEMAS) == ()

    postgres.run_postgres_migrations(dsn, revision="head")
    assert set(postgres.inspect_postgres_schemas(engine, MANAGED_SCHEMAS)) == set(
        MANAGED_SCHEMAS
    )
    assert set(postgres.inspect_postgres_tables(engine, REQUIRED_TABLES)) == set(
        REQUIRED_TABLES
    )
    assert postgres.current_postgres_revision(dsn) == "20260424_0001"

    postgres.run_postgres_migrations(dsn, revision="head")
    assert set(postgres.inspect_postgres_tables(engine, REQUIRED_TABLES)) == set(
        REQUIRED_TABLES
    )

    postgres.downgrade_postgres_migrations(dsn, revision="base")
    assert postgres.current_postgres_revision(dsn) is None
    assert postgres.inspect_postgres_schemas(engine, MANAGED_SCHEMAS) == ()

    postgres.run_postgres_migrations(dsn, revision="head")
    assert set(postgres.inspect_postgres_tables(engine, REQUIRED_TABLES)) == set(
        REQUIRED_TABLES
    )
    constraint_checks = set(postgres.inspect_required_postgres_constraints(engine))
    assert {
        "pk:system.outbox_event",
        "uq:system.outbox_event:dedupe_key",
        "pk:system.projection_checkpoint",
        (
            "uq:system.domain_projection_source_status:"
            "domain_name,source_family,source_identity"
        ),
        "pk:system.domain_projection_status",
        "uq:commanding.command_event:command_id,event_seq",
        "fk:commanding.command_attempt:command_id",
        "fk:access.command_session_event:command_session_id",
    } <= constraint_checks

    index_checks = set(postgres.inspect_required_postgres_indexes(engine))
    assert {
        "idx:commanding.command:created_at_utc_desc",
        (
            "idx:commanding.command:"
            "target_resource_type,target_resource_id,created_at_utc_desc"
        ),
        "idx:system.domain_projection_status:checked_at_utc_desc",
    } <= index_checks
