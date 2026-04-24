from __future__ import annotations

from importlib.resources import files
from typing import Any

import pytest

from tradingx.persistence import postgres

_SECRET_PASSWORD = "super" + "-secret"


def _assert_no_secret_leak(value: str, *secrets: str) -> None:
    for secret in secrets:
        if secret in value:
            raise AssertionError("diagnostic leaked a raw secret")


def _secret_dsn() -> str:
    return f"postgresql://tradingx:{_SECRET_PASSWORD}@db.internal:5432/tradingx"


def test_migration_package_resources_are_present() -> None:
    migration_root = files("tradingx.persistence.migrations")

    assert migration_root.joinpath("env.py").is_file()
    assert migration_root.joinpath("script.py.mako").is_file()
    assert migration_root.joinpath("versions").is_dir()
    assert migration_root.joinpath(
        "versions",
        "20260424_0001_control_plane_foundation.py",
    ).is_file()


def test_build_alembic_config_uses_package_script_location(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dsn = "postgresql://tradingx:example-password@db.internal:5432/tradingx"
    monkeypatch.chdir(tmp_path)

    config = postgres.build_alembic_config(raw_dsn)

    assert config.get_main_option("script_location") == (
        "tradingx.persistence:migrations"
    )
    assert config.get_main_option("sqlalchemy.url") == (
        "postgresql+psycopg://tradingx:example-password@db.internal:5432/tradingx"
    )
    assert str(tmp_path) not in config.get_main_option("script_location")


def test_migration_errors_redact_raw_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    raw_dsn = _secret_dsn()

    def fake_upgrade(_config: object, _revision: str) -> None:
        raise RuntimeError(f"failed for {raw_dsn}")

    monkeypatch.setattr(postgres.command, "upgrade", fake_upgrade)

    with pytest.raises(postgres.PostgresMigrationError) as exc_info:
        postgres.run_postgres_migrations(raw_dsn)

    message = str(exc_info.value)
    _assert_no_secret_leak(message, raw_dsn, _SECRET_PASSWORD)
    assert "postgresql://tradingx:***@db.internal:5432/tradingx" in message


def test_current_revision_errors_redact_raw_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dsn = _secret_dsn()

    class UnreachableEngine:
        def connect(self) -> Any:
            raise RuntimeError(f"failed for {raw_dsn} password=super-secret")

        def dispose(self) -> None:
            pass

    monkeypatch.setattr(
        postgres,
        "build_postgres_engine",
        lambda _settings: UnreachableEngine(),
    )

    with pytest.raises(postgres.PostgresMigrationError) as exc_info:
        postgres.current_postgres_revision(raw_dsn)

    message = str(exc_info.value)
    _assert_no_secret_leak(message, raw_dsn, _SECRET_PASSWORD)
    assert "postgresql://tradingx:***@db.internal:5432/tradingx" in message
