"""Create control-plane Postgres schemas and table skeletons.

Revision ID: 20260424_0001
Revises:
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260424_0001"
down_revision = None
branch_labels = None
depends_on = None

_SCHEMAS = (
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

_TABLES = (
    ("operator_account", "access"),
    ("operator_role_binding", "access"),
    ("command_session", "access"),
    ("command_session_event", "access"),
    ("command", "commanding"),
    ("command_attempt", "commanding"),
    ("command_idempotency_record", "commanding"),
    ("command_event", "commanding"),
    ("command_result_snapshot", "commanding"),
    ("runtime_instance", "runtime"),
    ("runtime_state_snapshot", "runtime"),
    ("runtime_heartbeat", "runtime"),
    ("scheduler_run", "runtime"),
    ("market_day_run", "runtime"),
    ("control_posture_snapshot", "runtime"),
    ("control_posture_blocker", "runtime"),
    ("incident", "incidents"),
    ("incident_event", "incidents"),
    ("incident_acknowledgement", "incidents"),
    ("portfolio_snapshot", "portfolio"),
    ("portfolio_timeseries_point", "portfolio"),
    ("position_snapshot", "portfolio"),
    ("exposure_snapshot", "portfolio"),
    ("benchmark_timeseries_point", "portfolio"),
    ("attribution_snapshot", "portfolio"),
    ("execution_quality_snapshot", "portfolio"),
    ("validation_run", "validation"),
    ("validation_candidate", "validation"),
    ("validation_criterion_result", "validation"),
    ("validation_readiness_blocker", "validation"),
    ("pbo_report", "validation"),
    ("cpcv_cohort", "validation"),
    ("replay_run", "investigations"),
    ("replay_event", "investigations"),
    ("investigation_workspace", "investigations"),
    ("drift_analysis_snapshot", "investigations"),
    ("document", "documents"),
    ("document_revision", "documents"),
    ("document_object_ref", "documents"),
    ("outbox_event", "system"),
    ("projection_checkpoint", "system"),
    ("domain_projection_source_status", "system"),
    ("domain_projection_status", "system"),
)


def _text_pk(name: str) -> sa.Column[str]:
    return sa.Column(name, sa.Text(), primary_key=True)


def _text(name: str, *, nullable: bool = True) -> sa.Column[str]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _integer(name: str, *, nullable: bool = True) -> sa.Column[int]:
    return sa.Column(name, sa.Integer(), nullable=nullable)


def _boolean(name: str, *, nullable: bool = True) -> sa.Column[bool]:
    return sa.Column(name, sa.Boolean(), nullable=nullable)


def _utc(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _numeric(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Numeric(20, 6), nullable=nullable)


def _json(name: str = "payload_json", *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, postgresql.JSONB(), nullable=nullable)


def _create_schemas() -> None:
    for schema in _SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')


def _drop_schemas() -> None:
    for schema in reversed(_SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}"')


def upgrade() -> None:
    _create_schemas()

    op.create_table(
        "operator_account",
        _text_pk("operator_account_id"),
        _text("display_name", nullable=False),
        _text("auth_subject", nullable=False),
        _text("status", nullable=False),
        _utc("created_at_utc", nullable=False),
        _utc("updated_at_utc", nullable=False),
        schema="access",
    )
    op.create_table(
        "operator_role_binding",
        _text_pk("binding_id"),
        sa.Column(
            "operator_account_id",
            sa.Text(),
            sa.ForeignKey("access.operator_account.operator_account_id"),
            nullable=False,
        ),
        _text("role_name", nullable=False),
        _text("scope", nullable=False),
        _utc("granted_at_utc", nullable=False),
        _utc("revoked_at_utc"),
        schema="access",
    )
    op.create_table(
        "command_session",
        _text_pk("command_session_id"),
        sa.Column(
            "operator_account_id",
            sa.Text(),
            sa.ForeignKey("access.operator_account.operator_account_id"),
        ),
        _text("status", nullable=False),
        _utc("issued_at_utc", nullable=False),
        _utc("expires_at_utc", nullable=False),
        _utc("refreshed_at_utc"),
        _utc("revoked_at_utc"),
        _text("session_token_hash", nullable=False),
        _text("proof_public_ref"),
        _json("metadata_json"),
        schema="access",
    )
    op.create_table(
        "command_session_event",
        _text_pk("event_id"),
        sa.Column(
            "command_session_id",
            sa.Text(),
            sa.ForeignKey("access.command_session.command_session_id"),
            nullable=False,
        ),
        _text("event_type", nullable=False),
        _utc("occurred_at_utc", nullable=False),
        _text("actor_ref"),
        _text("reason"),
        _json("metadata_json"),
        schema="access",
    )
    op.create_index(
        "ix_command_session_event_session_time",
        "command_session_event",
        ["command_session_id", "occurred_at_utc"],
        schema="access",
    )

    op.create_table(
        "command",
        _text_pk("command_id"),
        _text("job_id"),
        _text("command_type", nullable=False),
        _text("lifecycle_state", nullable=False),
        _text("target_resource_type", nullable=False),
        _text("target_resource_id", nullable=False),
        _integer("expected_resource_version"),
        _text("expected_state"),
        _text("expected_state_fingerprint"),
        _text("requested_transition"),
        _text("requested_by", nullable=False),
        sa.Column(
            "command_session_id",
            sa.Text(),
            sa.ForeignKey("access.command_session.command_session_id"),
        ),
        _text("idempotency_key_hash"),
        _text("request_hash"),
        _utc("created_at_utc", nullable=False),
        _utc("accepted_at_utc"),
        _utc("started_at_utc"),
        _utc("completed_at_utc"),
        _text("error_code"),
        _text("error_message"),
        _json(),
        schema="commanding",
    )
    op.create_index(
        "ix_command_created_at_desc",
        "command",
        [sa.text("created_at_utc DESC")],
        schema="commanding",
    )
    op.create_index(
        "ix_command_target_created_at_desc",
        "command",
        [
            "target_resource_type",
            "target_resource_id",
            sa.text("created_at_utc DESC"),
        ],
        schema="commanding",
    )
    op.create_table(
        "command_attempt",
        _text_pk("attempt_id"),
        sa.Column(
            "command_id",
            sa.Text(),
            sa.ForeignKey("commanding.command.command_id"),
            nullable=False,
        ),
        _integer("attempt_number", nullable=False),
        _utc("received_at_utc", nullable=False),
        _text("remote_addr_hash"),
        _text("verification_state", nullable=False),
        _text("rejection_reason"),
        _json("metadata_json"),
        sa.UniqueConstraint(
            "command_id",
            "attempt_number",
            name="uq_command_attempt_command_attempt_number",
        ),
        schema="commanding",
    )
    op.create_table(
        "command_idempotency_record",
        _text_pk("idempotency_key_hash"),
        sa.Column(
            "command_id",
            sa.Text(),
            sa.ForeignKey("commanding.command.command_id"),
            nullable=False,
        ),
        _text("request_hash", nullable=False),
        _utc("first_seen_at_utc", nullable=False),
        _utc("last_seen_at_utc", nullable=False),
        _integer("replay_count", nullable=False),
        sa.UniqueConstraint(
            "idempotency_key_hash",
            "request_hash",
            name="uq_command_idempotency_record_key_request",
        ),
        schema="commanding",
    )
    op.create_table(
        "command_event",
        _text_pk("event_id"),
        sa.Column(
            "command_id",
            sa.Text(),
            sa.ForeignKey("commanding.command.command_id"),
            nullable=False,
        ),
        _integer("event_seq", nullable=False),
        _text("event_type", nullable=False),
        _utc("occurred_at_utc", nullable=False),
        _text("message"),
        _json(),
        sa.UniqueConstraint(
            "command_id",
            "event_seq",
            name="uq_command_event_command_seq",
        ),
        schema="commanding",
    )
    op.create_table(
        "command_result_snapshot",
        _text_pk("snapshot_id"),
        sa.Column(
            "command_id",
            sa.Text(),
            sa.ForeignKey("commanding.command.command_id"),
            nullable=False,
        ),
        _utc("captured_at_utc", nullable=False),
        _text("lifecycle_state", nullable=False),
        _json("result_json"),
        schema="commanding",
    )

    op.create_table(
        "runtime_instance",
        _text_pk("runtime_instance_id"),
        _text("environment", nullable=False),
        _text("process_ref", nullable=False),
        _text("status", nullable=False),
        _utc("started_at_utc", nullable=False),
        _utc("stopped_at_utc"),
        _integer("lease_epoch", nullable=False),
        _json("metadata_json"),
        schema="runtime",
    )
    op.create_table(
        "runtime_state_snapshot",
        _text_pk("snapshot_id"),
        sa.Column(
            "runtime_instance_id",
            sa.Text(),
            sa.ForeignKey("runtime.runtime_instance.runtime_instance_id"),
        ),
        _utc("observed_at_utc", nullable=False),
        _text("status", nullable=False),
        _text("current_action"),
        _text("next_action"),
        _utc("next_evaluation_at_utc"),
        _integer("resource_version", nullable=False),
        _text("state_fingerprint", nullable=False),
        _text("source_ref"),
        _json(),
        schema="runtime",
    )
    op.create_table(
        "runtime_heartbeat",
        _text_pk("heartbeat_id"),
        sa.Column(
            "runtime_instance_id",
            sa.Text(),
            sa.ForeignKey("runtime.runtime_instance.runtime_instance_id"),
        ),
        _utc("observed_at_utc", nullable=False),
        _text("heartbeat_state", nullable=False),
        _integer("scheduler_cadence_seconds"),
        _text("stream_state"),
        _utc("stale_after_utc"),
        _text("source_ref"),
        _json(),
        schema="runtime",
    )
    op.create_table(
        "scheduler_run",
        _text_pk("scheduler_run_id"),
        _utc("started_at_utc", nullable=False),
        _utc("completed_at_utc"),
        _text("status", nullable=False),
        _json(),
        schema="runtime",
    )
    op.create_table(
        "market_day_run",
        _text_pk("market_day_run_id"),
        sa.Column("trading_day", sa.Date(), nullable=False),
        _utc("started_at_utc", nullable=False),
        _utc("completed_at_utc"),
        _text("status", nullable=False),
        _json(),
        schema="runtime",
    )
    op.create_table(
        "control_posture_snapshot",
        _text_pk("posture_id"),
        _utc("observed_at_utc", nullable=False),
        _text("requested_mode", nullable=False),
        _text("effective_mode", nullable=False),
        _boolean("live_allowed", nullable=False),
        _text("governance_status", nullable=False),
        _integer("blocker_count", nullable=False),
        _json("explicit_blocker_codes"),
        _json("fail_closed_reason_codes"),
        _integer("resource_version", nullable=False),
        _text("state_fingerprint", nullable=False),
        _text("payload_hash"),
        _json(),
        schema="runtime",
    )
    op.create_table(
        "control_posture_blocker",
        _text_pk("blocker_id"),
        sa.Column(
            "posture_id",
            sa.Text(),
            sa.ForeignKey("runtime.control_posture_snapshot.posture_id"),
            nullable=False,
        ),
        _text("blocker_code", nullable=False),
        _text("severity", nullable=False),
        _text("message", nullable=False),
        _text("source_ref"),
        _json(),
        sa.UniqueConstraint(
            "posture_id",
            "blocker_code",
            name="uq_control_posture_blocker_posture_code",
        ),
        schema="runtime",
    )

    op.create_table(
        "incident",
        _text_pk("incident_id"),
        _text("severity", nullable=False),
        _text("status", nullable=False),
        _text("summary", nullable=False),
        _utc("opened_at_utc", nullable=False),
        _utc("updated_at_utc", nullable=False),
        _utc("resolved_at_utc"),
        _integer("resource_version", nullable=False),
        _text("state_fingerprint", nullable=False),
        _text("source_ref"),
        _json(),
        schema="incidents",
    )
    op.create_table(
        "incident_event",
        _text_pk("incident_event_id"),
        sa.Column(
            "incident_id",
            sa.Text(),
            sa.ForeignKey("incidents.incident.incident_id"),
            nullable=False,
        ),
        _text("event_id", nullable=False),
        _text("event_type", nullable=False),
        _utc("occurred_at_utc", nullable=False),
        _json(),
        schema="incidents",
    )
    op.create_table(
        "incident_acknowledgement",
        _text_pk("acknowledgement_id"),
        sa.Column(
            "incident_id",
            sa.Text(),
            sa.ForeignKey("incidents.incident.incident_id"),
            nullable=False,
        ),
        sa.Column(
            "command_id",
            sa.Text(),
            sa.ForeignKey("commanding.command.command_id"),
        ),
        _text("acknowledged_by", nullable=False),
        _utc("acknowledged_at_utc", nullable=False),
        _integer("resource_version", nullable=False),
        _text("state_fingerprint", nullable=False),
        _json(),
        schema="incidents",
    )

    op.create_table(
        "portfolio_snapshot",
        _text_pk("snapshot_id"),
        _text("portfolio_id", nullable=False),
        _text("portfolio_slice", nullable=False),
        _utc("captured_at_utc", nullable=False),
        _numeric("market_value"),
        _numeric("cash"),
        _numeric("gross_exposure"),
        _numeric("net_exposure"),
        _numeric("realized_pnl"),
        _numeric("unrealized_pnl"),
        _json(),
        schema="portfolio",
    )
    op.create_table(
        "portfolio_timeseries_point",
        _text_pk("point_id"),
        _text("portfolio_id", nullable=False),
        _text("portfolio_slice", nullable=False),
        _text("symbol"),
        _utc("captured_at_utc", nullable=False),
        _text("metric_name", nullable=False),
        _numeric("metric_value", nullable=False),
        _json(),
        schema="portfolio",
    )
    op.create_table(
        "position_snapshot",
        _text_pk("position_snapshot_id"),
        sa.Column(
            "snapshot_id",
            sa.Text(),
            sa.ForeignKey("portfolio.portfolio_snapshot.snapshot_id"),
            nullable=False,
        ),
        _text("symbol", nullable=False),
        _numeric("quantity"),
        _numeric("market_value"),
        _numeric("cost_basis"),
        _numeric("realized_pnl"),
        _numeric("unrealized_pnl"),
        _numeric("weight"),
        _json(),
        schema="portfolio",
    )
    op.create_table(
        "exposure_snapshot",
        _text_pk("exposure_snapshot_id"),
        sa.Column(
            "snapshot_id",
            sa.Text(),
            sa.ForeignKey("portfolio.portfolio_snapshot.snapshot_id"),
            nullable=False,
        ),
        _text("dimension", nullable=False),
        _text("bucket", nullable=False),
        _numeric("gross_exposure"),
        _numeric("net_exposure"),
        _numeric("weight"),
        _json(),
        schema="portfolio",
    )
    op.create_table(
        "benchmark_timeseries_point",
        _text_pk("point_id"),
        _text("benchmark_id", nullable=False),
        _utc("captured_at_utc", nullable=False),
        _text("metric_name", nullable=False),
        _numeric("metric_value", nullable=False),
        _json(),
        schema="portfolio",
    )
    op.create_table(
        "attribution_snapshot",
        _text_pk("attribution_id"),
        sa.Column(
            "snapshot_id",
            sa.Text(),
            sa.ForeignKey("portfolio.portfolio_snapshot.snapshot_id"),
            nullable=False,
        ),
        _text("dimension", nullable=False),
        _text("bucket", nullable=False),
        _numeric("contribution_pnl"),
        _numeric("contribution_return"),
        _json(),
        schema="portfolio",
    )
    op.create_table(
        "execution_quality_snapshot",
        _text_pk("execution_quality_id"),
        _utc("captured_at_utc", nullable=False),
        _text("symbol"),
        _integer("order_count"),
        _integer("fill_count"),
        _numeric("average_slippage_bps"),
        _integer("reject_count"),
        _json(),
        schema="portfolio",
    )

    op.create_table(
        "validation_run",
        _text_pk("validation_run_id"),
        _utc("generated_at_utc", nullable=False),
        _text("source_ref"),
        _text("status", nullable=False),
        _json(),
        schema="validation",
    )
    op.create_table(
        "validation_candidate",
        _text_pk("validation_candidate_id"),
        sa.Column(
            "validation_run_id",
            sa.Text(),
            sa.ForeignKey("validation.validation_run.validation_run_id"),
            nullable=False,
        ),
        _utc("generated_at_utc", nullable=False),
        _text("source_ref"),
        _text("status", nullable=False),
        _json(),
        schema="validation",
    )
    op.create_table(
        "validation_criterion_result",
        _text_pk("criterion_result_id"),
        sa.Column(
            "validation_run_id",
            sa.Text(),
            sa.ForeignKey("validation.validation_run.validation_run_id"),
            nullable=False,
        ),
        _text("criterion_name", nullable=False),
        _text("tri_state_status", nullable=False),
        _utc("generated_at_utc", nullable=False),
        _text("source_ref"),
        _text("status", nullable=False),
        _json(),
        schema="validation",
    )
    op.create_table(
        "validation_readiness_blocker",
        _text_pk("readiness_blocker_id"),
        sa.Column(
            "validation_run_id",
            sa.Text(),
            sa.ForeignKey("validation.validation_run.validation_run_id"),
            nullable=False,
        ),
        _text("blocker_code", nullable=False),
        _utc("generated_at_utc", nullable=False),
        _text("source_ref"),
        _text("status", nullable=False),
        _json(),
        schema="validation",
    )
    op.create_table(
        "pbo_report",
        _text_pk("pbo_report_id"),
        _utc("generated_at_utc", nullable=False),
        _text("source_ref"),
        _text("status", nullable=False),
        _json(),
        schema="validation",
    )
    op.create_table(
        "cpcv_cohort",
        _text_pk("cpcv_cohort_id"),
        _utc("generated_at_utc", nullable=False),
        _text("source_ref"),
        _text("status", nullable=False),
        _json(),
        schema="validation",
    )

    op.create_table(
        "replay_run",
        _text_pk("replay_run_id"),
        _utc("started_at_utc", nullable=False),
        _utc("completed_at_utc"),
        _text("source_ref"),
        _text("status", nullable=False),
        _json(),
        schema="investigations",
    )
    op.create_table(
        "replay_event",
        _text_pk("replay_event_id"),
        sa.Column(
            "replay_run_id",
            sa.Text(),
            sa.ForeignKey("investigations.replay_run.replay_run_id"),
            nullable=False,
        ),
        _integer("event_seq", nullable=False),
        _text("event_type", nullable=False),
        _utc("occurred_at_utc", nullable=False),
        _json(),
        sa.UniqueConstraint(
            "replay_run_id",
            "event_seq",
            name="uq_replay_event_run_seq",
        ),
        schema="investigations",
    )
    op.create_table(
        "investigation_workspace",
        _text_pk("investigation_workspace_id"),
        _utc("generated_at_utc", nullable=False),
        _text("source_ref"),
        _text("status", nullable=False),
        _json(),
        schema="investigations",
    )
    op.create_table(
        "drift_analysis_snapshot",
        _text_pk("drift_analysis_snapshot_id"),
        _utc("generated_at_utc", nullable=False),
        _text("source_ref"),
        _text("status", nullable=False),
        _json(),
        schema="investigations",
    )

    op.create_table(
        "document",
        _text_pk("document_id"),
        _text("document_type", nullable=False),
        _text("title", nullable=False),
        _utc("created_at_utc", nullable=False),
        _utc("updated_at_utc", nullable=False),
        _text("source_ref"),
        _json("metadata_json"),
        schema="documents",
    )
    op.create_table(
        "document_revision",
        _text_pk("document_revision_id"),
        sa.Column(
            "document_id",
            sa.Text(),
            sa.ForeignKey("documents.document.document_id"),
            nullable=False,
        ),
        _integer("revision_number", nullable=False),
        _utc("created_at_utc", nullable=False),
        _text("source_ref"),
        _json("metadata_json"),
        sa.UniqueConstraint(
            "document_id",
            "revision_number",
            name="uq_document_revision_document_number",
        ),
        schema="documents",
    )
    op.create_table(
        "document_object_ref",
        _text_pk("document_object_ref_id"),
        sa.Column(
            "document_revision_id",
            sa.Text(),
            sa.ForeignKey("documents.document_revision.document_revision_id"),
            nullable=False,
        ),
        _text("object_uri", nullable=False),
        _text("content_type"),
        _text("sha256_hash"),
        _json("metadata_json"),
        schema="documents",
    )

    op.create_table(
        "outbox_event",
        _text_pk("outbox_event_id"),
        _text("aggregate_type", nullable=False),
        _text("aggregate_id", nullable=False),
        _text("event_type", nullable=False),
        _integer("event_version", nullable=False),
        _utc("occurred_at_utc", nullable=False),
        _text("dedupe_key", nullable=False),
        _json(),
        _utc("created_at_utc", nullable=False),
        _utc("published_at_utc"),
        sa.UniqueConstraint("dedupe_key", name="uq_outbox_event_dedupe_key"),
        schema="system",
    )
    op.create_index(
        "ix_outbox_event_aggregate_time",
        "outbox_event",
        ["aggregate_type", "aggregate_id", "occurred_at_utc"],
        schema="system",
    )
    op.create_table(
        "projection_checkpoint",
        _text_pk("projection_name"),
        _text("last_outbox_event_id"),
        _utc("last_processed_at_utc"),
        _text("source_watermark"),
        _utc("last_source_observed_at_utc"),
        _integer("lag_seconds"),
        _text("status", nullable=False),
        _json("metadata_json"),
        schema="system",
    )
    op.create_table(
        "domain_projection_source_status",
        _text("domain_name", nullable=False),
        _text("source_family", nullable=False),
        _text("source_identity", nullable=False),
        _text("source_watermark"),
        _text("projected_watermark"),
        _integer("lag_seconds"),
        _boolean("is_mutable", nullable=False),
        _boolean("ready_for_postgres", nullable=False),
        _utc("checked_at_utc", nullable=False),
        _json("metadata_json"),
        sa.PrimaryKeyConstraint(
            "domain_name",
            "source_family",
            "source_identity",
            name="pk_domain_projection_source_status",
        ),
        sa.UniqueConstraint(
            "domain_name",
            "source_family",
            "source_identity",
            name="uq_domain_projection_source_status_identity",
        ),
        schema="system",
    )
    op.create_index(
        "ix_domain_projection_source_status_readiness",
        "domain_projection_source_status",
        ["domain_name", "ready_for_postgres", "lag_seconds"],
        schema="system",
    )
    op.create_table(
        "domain_projection_status",
        _text_pk("domain_name"),
        _text("target_store", nullable=False),
        _text("bridge_status", nullable=False),
        _text("projection_status", nullable=False),
        _text("source_watermark"),
        _text("last_projected_outbox_event_id"),
        _integer("lag_seconds"),
        _boolean("ready_for_postgres", nullable=False),
        _utc("checked_at_utc", nullable=False),
        _json("metadata_json"),
        schema="system",
    )
    op.create_index(
        "ix_domain_projection_status_readiness_desc",
        "domain_projection_status",
        ["domain_name", "ready_for_postgres", sa.text("checked_at_utc DESC")],
        schema="system",
    )


def downgrade() -> None:
    for table, schema in reversed(_TABLES):
        op.drop_table(table, schema=schema)
    _drop_schemas()
