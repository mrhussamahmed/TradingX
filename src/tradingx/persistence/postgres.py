"""Postgres persistence helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import (
    parse_qsl,
    unquote,
    unquote_plus,
    urlencode,
    urlsplit,
    urlunsplit,
)

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from tradingx.config import TradingConfig

_SECRET_QUERY_PARAMETERS = frozenset(
    {
        "pass",
        "passwd",
        "password",
        "pwd",
        "sslpassword",
    }
)
_ALEMBIC_SCRIPT_LOCATION = "tradingx.persistence:migrations"
_DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
_DEFAULT_STATEMENT_TIMEOUT_MILLISECONDS = 30_000
_MANAGED_SCHEMAS = (
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


class PostgresConfigurationError(RuntimeError):
    """Raised when Postgres is required but cannot be configured safely."""


class PostgresMigrationError(RuntimeError):
    """Raised when an Alembic migration command fails."""


class PostgresResetSafetyError(RuntimeError):
    """Raised before test cleanup can touch an unsafe database."""


@dataclass(frozen=True)
class PostgresSettings:
    dsn: str = field(repr=False)
    connect_timeout_seconds: int = _DEFAULT_CONNECT_TIMEOUT_SECONDS
    statement_timeout_milliseconds: int = _DEFAULT_STATEMENT_TIMEOUT_MILLISECONDS

    @property
    def redacted_dsn(self) -> str:
        return redact_postgres_dsn(self.dsn)

    def __repr__(self) -> str:
        return (
            "PostgresSettings("
            f"dsn={self.redacted_dsn!r}, "
            f"connect_timeout_seconds={self.connect_timeout_seconds!r}, "
            "statement_timeout_milliseconds="
            f"{self.statement_timeout_milliseconds!r})"
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


def redact_postgres_dsn(dsn: str) -> str:
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
    redacted = message.replace(dsn, redact_postgres_dsn(dsn))
    for secret in _dsn_secret_values(dsn):
        redacted = redacted.replace(secret, "***")
    return redacted


def _sqlalchemy_dsn(dsn: str) -> str:
    parsed = urlsplit(dsn.strip())
    if parsed.scheme in {"postgres", "postgresql"}:
        return urlunsplit(
            (
                "postgresql+psycopg",
                parsed.netloc,
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )
    return dsn


def settings_from_control_plane(config: TradingConfig) -> PostgresSettings:
    return PostgresSettings(dsn=config.control_plane.postgres_dsn)


def _control_plane_requests_postgres(config: TradingConfig) -> bool:
    return (
        config.control_plane.store in {"hybrid", "postgres"}
        or config.control_plane.postgres_required
        or any(
            store == "postgres"
            for _domain, store in config.control_plane.domain_stores
        )
    )


def require_postgres_dsn(config: TradingConfig) -> str:
    settings = settings_from_control_plane(config)
    if settings.dsn:
        return settings.dsn

    if _control_plane_requests_postgres(config):
        raise PostgresConfigurationError(
            "TRADINGX_POSTGRES_DSN must be configured when Postgres control-plane "
            "storage is requested or required."
        )

    return ""


def build_postgres_engine(settings: PostgresSettings) -> Engine:
    try:
        return create_engine(
            _sqlalchemy_dsn(settings.dsn),
            connect_args={
                "connect_timeout": settings.connect_timeout_seconds,
                "options": (
                    "-c statement_timeout="
                    f"{settings.statement_timeout_milliseconds}"
                ),
            },
            pool_pre_ping=True,
        )
    except Exception as exc:
        message = _redact_exception_message(str(exc), settings.dsn)
        raise PostgresConfigurationError(
            "Could not create Postgres engine for "
            f"{settings.redacted_dsn}: {message}"
        ) from None


def build_alembic_config(dsn: str) -> Config:
    config = Config()
    config.set_main_option("script_location", _ALEMBIC_SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", _sqlalchemy_dsn(dsn))
    return config


def run_postgres_migrations(dsn: str, *, revision: str = "head") -> None:
    config = build_alembic_config(dsn)
    try:
        command.upgrade(config, revision)
    except Exception as exc:
        message = _redact_exception_message(str(exc), dsn)
        raise PostgresMigrationError(
            "Postgres migration upgrade failed for "
            f"{redact_postgres_dsn(dsn)}: {message}"
        ) from None


def downgrade_postgres_migrations(dsn: str, *, revision: str = "base") -> None:
    config = build_alembic_config(dsn)
    try:
        command.downgrade(config, revision)
    except Exception as exc:
        message = _redact_exception_message(str(exc), dsn)
        raise PostgresMigrationError(
            "Postgres migration downgrade failed for "
            f"{redact_postgres_dsn(dsn)}: {message}"
        ) from None


def current_postgres_revision(dsn: str) -> str | None:
    engine = build_postgres_engine(PostgresSettings(dsn=dsn))
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            heads = context.get_current_heads()
            if not heads:
                return None
            return heads[0] if len(heads) == 1 else ",".join(heads)
    except Exception as exc:
        message = _redact_exception_message(str(exc), dsn)
        raise PostgresMigrationError(
            "Postgres migration revision inspection failed for "
            f"{redact_postgres_dsn(dsn)}: {message}"
        ) from None
    finally:
        engine.dispose()


def _postgres_database_name(dsn: str) -> str:
    parsed = urlsplit(dsn.strip())
    return unquote(parsed.path.lstrip("/"))


def _engine_database_name(engine: Engine) -> str:
    database = getattr(engine.url, "database", "") or ""
    return unquote(str(database))


def assert_postgres_test_reset_allowed(dsn: str) -> None:
    database_name = _postgres_database_name(dsn)
    explicit_override = os.environ.get("TRADINGX_ALLOW_POSTGRES_TEST_RESET", "")
    if database_name == "tradingx_test" or explicit_override.lower() == "true":
        return

    raise PostgresResetSafetyError(
        "Refusing to reset Postgres schemas. Expected database name exactly "
        "'tradingx_test' or TRADINGX_ALLOW_POSTGRES_TEST_RESET=true; got "
        f"{database_name!r}."
    )


def reset_postgres_test_database(engine: Engine, *, dsn: str) -> None:
    dsn_database_name = _postgres_database_name(dsn)
    engine_database_name = _engine_database_name(engine)
    if engine_database_name != dsn_database_name:
        raise PostgresResetSafetyError(
            "Refusing to reset Postgres schemas. Engine database "
            f"{engine_database_name!r} does not match guarded DSN database "
            f"{dsn_database_name!r}."
    )

    assert_postgres_test_reset_allowed(dsn)
    try:
        with engine.begin() as connection:
            for schema in _MANAGED_SCHEMAS:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.execute(text("DROP TABLE IF EXISTS public.alembic_version"))
    except Exception as exc:
        message = _redact_exception_message(str(exc), dsn)
        raise PostgresMigrationError(
            "Postgres test reset failed for "
            f"{redact_postgres_dsn(dsn)}: {message}"
        ) from None


def inspect_postgres_schemas(
    engine: Engine,
    schemas: tuple[str, ...],
) -> tuple[str, ...]:
    inspector = inspect(engine)
    existing = set(inspector.get_schema_names())
    return tuple(schema for schema in schemas if schema in existing)


def inspect_postgres_tables(
    engine: Engine,
    tables: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    inspector = inspect(engine)
    schema_tables: dict[str, set[str]] = {}
    for schema, _table in tables:
        if schema not in schema_tables:
            schema_tables[schema] = set(inspector.get_table_names(schema=schema))
    return tuple(
        (schema, table)
        for schema, table in tables
        if table in schema_tables.get(schema, set())
    )


def _unique_column_sets(
    inspector: Any,
    *,
    schema: str,
    table: str,
) -> set[tuple[str, ...]]:
    return {
        tuple(str(column) for column in constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(table, schema=schema)
    }


def _primary_key_columns(
    inspector: Any,
    *,
    schema: str,
    table: str,
) -> tuple[str, ...]:
    primary_key = inspector.get_pk_constraint(table, schema=schema)
    return tuple(str(column) for column in primary_key.get("constrained_columns") or ())


def _has_unique_key(
    inspector: Any,
    *,
    schema: str,
    table: str,
    columns: tuple[str, ...],
) -> bool:
    return columns == _primary_key_columns(
        inspector,
        schema=schema,
        table=table,
    ) or columns in _unique_column_sets(inspector, schema=schema, table=table)


def _foreign_key_column_sets(
    inspector: Any,
    *,
    schema: str,
    table: str,
) -> set[tuple[str, ...]]:
    return {
        tuple(str(column) for column in constraint.get("constrained_columns") or ())
        for constraint in inspector.get_foreign_keys(table, schema=schema)
    }


def inspect_required_postgres_constraints(engine: Engine) -> tuple[str, ...]:
    inspector = inspect(engine)
    checks: list[str] = []

    for schema, table in (
        ("system", "outbox_event"),
        ("system", "projection_checkpoint"),
        ("system", "domain_projection_status"),
    ):
        primary_key = inspector.get_pk_constraint(table, schema=schema)
        if primary_key.get("constrained_columns"):
            checks.append(f"pk:{schema}.{table}")

    unique_checks = (
        ("system", "outbox_event", ("dedupe_key",)),
        (
            "system",
            "domain_projection_source_status",
            ("domain_name", "source_family", "source_identity"),
        ),
        ("commanding", "command_event", ("command_id", "event_seq")),
    )
    for schema, table, columns in unique_checks:
        if _has_unique_key(inspector, schema=schema, table=table, columns=columns):
            checks.append(f"uq:{schema}.{table}:{','.join(columns)}")

    foreign_key_checks = (
        ("commanding", "command_attempt", ("command_id",)),
        ("access", "command_session_event", ("command_session_id",)),
    )
    for schema, table, columns in foreign_key_checks:
        if columns in _foreign_key_column_sets(inspector, schema=schema, table=table):
            checks.append(f"fk:{schema}.{table}:{','.join(columns)}")

    return tuple(checks)


def _normalized_index_definitions(engine: Engine) -> dict[str, str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT schemaname, tablename, indexname, indexdef
                FROM pg_indexes
                WHERE schemaname IN (
                    'access',
                    'commanding',
                    'runtime',
                    'incidents',
                    'portfolio',
                    'validation',
                    'investigations',
                    'documents',
                    'system'
                )
                """
            )
        ).mappings()
        return {
            f"{row['schemaname']}.{row['tablename']}.{row['indexname']}": " ".join(
                str(row["indexdef"]).lower().split()
            )
            for row in rows
        }


def inspect_required_postgres_indexes(engine: Engine) -> tuple[str, ...]:
    index_definitions = _normalized_index_definitions(engine)
    checks: list[str] = []

    command_created_at = index_definitions.get(
        "commanding.command.ix_command_created_at_desc",
        "",
    )
    if "(created_at_utc desc)" in command_created_at:
        checks.append("idx:commanding.command:created_at_utc_desc")

    command_target_created_at = index_definitions.get(
        "commanding.command.ix_command_target_created_at_desc",
        "",
    )
    if (
        "(target_resource_type, target_resource_id, created_at_utc desc)"
        in command_target_created_at
    ):
        checks.append(
            "idx:commanding.command:"
            "target_resource_type,target_resource_id,created_at_utc_desc"
        )

    domain_status_readiness = index_definitions.get(
        "system.domain_projection_status.ix_domain_projection_status_readiness_desc",
        "",
    )
    if (
        "(domain_name, ready_for_postgres, checked_at_utc desc)"
        in domain_status_readiness
    ):
        checks.append("idx:system.domain_projection_status:checked_at_utc_desc")

    return tuple(checks)


__all__ = (
    "PostgresConfigurationError",
    "PostgresMigrationError",
    "PostgresResetSafetyError",
    "PostgresSettings",
    "assert_postgres_test_reset_allowed",
    "build_alembic_config",
    "build_postgres_engine",
    "command",
    "current_postgres_revision",
    "downgrade_postgres_migrations",
    "inspect_postgres_schemas",
    "inspect_postgres_tables",
    "inspect_required_postgres_indexes",
    "inspect_required_postgres_constraints",
    "redact_postgres_dsn",
    "require_postgres_dsn",
    "reset_postgres_test_database",
    "run_postgres_migrations",
    "settings_from_control_plane",
)
