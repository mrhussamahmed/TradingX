from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.engine import make_url

from tradingx.config import TradingConfig
from tradingx.persistence import postgres

_SECRET_PASSWORD = "super" + "-secret"
_ENCODED_PASSWORD = "p%40" + "ss"
_DECODED_PASSWORD = "p" + "@ss"
_ENCODED_QUERY_SECRET = "a%2F" + "b"
_DECODED_QUERY_SECRET = "a" + "/b"
_PLUS_ENCODED_QUERY_SECRET = "secret+with+space"
_PLUS_DECODED_QUERY_SECRET = "secret" + " with " + "space"


def _assert_no_secret_leak(value: str, *secrets: str) -> None:
    for secret in secrets:
        if secret in value:
            raise AssertionError("diagnostic leaked a raw secret")


def _secret_dsn() -> str:
    return f"postgresql://tradingx:{_SECRET_PASSWORD}@db.internal:5432/tradingx"


def test_settings_from_config_carries_redacted_dsn_and_safe_defaults() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_POSTGRES_DSN": (
                "postgresql://tradingx:example-password@db.internal:5432/tradingx"
            ),
        }
    )

    settings = postgres.settings_from_control_plane(config)

    assert settings.dsn == (
        "postgresql://tradingx:example-password@db.internal:5432/tradingx"
    )
    assert settings.redacted_dsn == (
        "postgresql://tradingx:***@db.internal:5432/tradingx"
    )
    assert settings.connect_timeout_seconds == 5
    assert settings.statement_timeout_milliseconds == 30_000


def test_settings_repr_redacts_raw_dsn() -> None:
    settings = postgres.PostgresSettings(dsn=_secret_dsn())

    representation = repr(settings)

    _assert_no_secret_leak(representation, _SECRET_PASSWORD)
    assert "PostgresSettings" in representation
    assert "postgresql://tradingx:***@db.internal:5432/tradingx" in representation


@pytest.mark.parametrize(
    "values",
    (
        {"TRADINGX_CONTROL_PLANE_STORE": "postgres"},
        {"TRADINGX_CONTROL_PLANE_STORE": "hybrid"},
        {"TRADINGX_CONTROL_PLANE_DOMAIN_STORES": "runtime=postgres"},
        {"TRADINGX_POSTGRES_REQUIRED": "true"},
    ),
)
def test_require_postgres_dsn_fails_when_postgres_is_requested_without_dsn(
    values: dict[str, str],
) -> None:
    config = TradingConfig.from_mapping(
        values
    )

    with pytest.raises(postgres.PostgresConfigurationError) as exc_info:
        postgres.require_postgres_dsn(config)

    message = str(exc_info.value)
    assert "TRADINGX_POSTGRES_DSN" in message
    assert "postgresql://" not in message


def test_build_postgres_engine_is_explicit_and_uses_safe_connect_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_create_engine(dsn: str, **kwargs: object) -> object:
        calls.append((dsn, kwargs))
        return object()

    monkeypatch.setattr(postgres, "create_engine", fake_create_engine)

    engine = postgres.build_postgres_engine(
        postgres.PostgresSettings(
            dsn="postgresql://tradingx:example-password@db.internal:5432/tradingx"
        )
    )

    assert engine is not None
    assert calls == [
        (
            "postgresql+psycopg://tradingx:example-password@db.internal:5432/tradingx",
            {
                "connect_args": {
                    "connect_timeout": 5,
                    "options": "-c statement_timeout=30000",
                },
                "pool_pre_ping": True,
            },
        )
    ]


def test_build_postgres_engine_redacts_dsn_when_creation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dsn = _secret_dsn()

    def fake_create_engine(_dsn: str, **_kwargs: object) -> object:
        raise RuntimeError(f"could not use {_dsn}")

    monkeypatch.setattr(postgres, "create_engine", fake_create_engine)

    with pytest.raises(postgres.PostgresConfigurationError) as exc_info:
        postgres.build_postgres_engine(postgres.PostgresSettings(dsn=raw_dsn))

    message = str(exc_info.value)
    _assert_no_secret_leak(message, raw_dsn, _SECRET_PASSWORD)
    assert "postgresql://tradingx:***@db.internal:5432/tradingx" in message


def test_build_postgres_engine_redacts_encoded_secret_fragments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dsn = (
        f"postgresql://tradingx:{_ENCODED_PASSWORD}@db.internal:5432/tradingx"
        f"?sslpassword={_ENCODED_QUERY_SECRET}"
    )

    def fake_create_engine(_dsn: str, **_kwargs: object) -> object:
        raise RuntimeError(
            "could not use "
            f"{_ENCODED_PASSWORD}, {_DECODED_PASSWORD}, "
            f"{_ENCODED_QUERY_SECRET}, or {_DECODED_QUERY_SECRET}"
        )

    monkeypatch.setattr(postgres, "create_engine", fake_create_engine)

    with pytest.raises(postgres.PostgresConfigurationError) as exc_info:
        postgres.build_postgres_engine(postgres.PostgresSettings(dsn=raw_dsn))

    _assert_no_secret_leak(
        str(exc_info.value),
        _ENCODED_PASSWORD,
        _DECODED_PASSWORD,
        _ENCODED_QUERY_SECRET,
        _DECODED_QUERY_SECRET,
    )


def test_build_postgres_engine_redacts_plus_decoded_query_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dsn = (
        "postgresql://tradingx@db.internal:5432/tradingx"
        f"?password={_PLUS_ENCODED_QUERY_SECRET}"
    )

    def fake_create_engine(_dsn: str, **_kwargs: object) -> object:
        raise RuntimeError(f"driver decoded {_PLUS_DECODED_QUERY_SECRET}")

    monkeypatch.setattr(postgres, "create_engine", fake_create_engine)

    with pytest.raises(postgres.PostgresConfigurationError) as exc_info:
        postgres.build_postgres_engine(postgres.PostgresSettings(dsn=raw_dsn))

    _assert_no_secret_leak(
        str(exc_info.value),
        _PLUS_ENCODED_QUERY_SECRET,
        _PLUS_DECODED_QUERY_SECRET,
    )


def test_reset_requires_engine_database_to_match_guarded_dsn() -> None:
    class MismatchedEngine:
        url = make_url("postgresql+psycopg://tradingx@127.0.0.1/tradingx_prod")

        def begin(self) -> Any:
            raise AssertionError("reset attempted despite mismatched database")

    with pytest.raises(postgres.PostgresResetSafetyError, match="does not match"):
        postgres.reset_postgres_test_database(
            cast(Any, MismatchedEngine()),
            dsn="postgresql://tradingx@127.0.0.1/tradingx_test",
        )


def test_reset_redacts_connection_failure_diagnostics() -> None:
    raw_dsn = (
        f"postgresql://tradingx:{_SECRET_PASSWORD}@127.0.0.1:5432/tradingx_test"
    )

    class UnreachableEngine:
        url = make_url(raw_dsn)

        def begin(self) -> Any:
            raise RuntimeError(f"connection failed for {raw_dsn} password=super-secret")

    with pytest.raises(postgres.PostgresMigrationError) as exc_info:
        postgres.reset_postgres_test_database(
            cast(Any, UnreachableEngine()),
            dsn=raw_dsn,
        )

    message = str(exc_info.value)
    _assert_no_secret_leak(message, raw_dsn, _SECRET_PASSWORD)
    assert "postgresql://tradingx:***@127.0.0.1:5432/tradingx_test" in message
