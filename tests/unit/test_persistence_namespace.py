from __future__ import annotations

import importlib

from tradingx.persistence import FilesystemArtifactStore


def test_existing_persistence_import_surface_still_exports_filesystem_store() -> None:
    module = importlib.import_module("tradingx.persistence")

    assert module.FilesystemArtifactStore is FilesystemArtifactStore


def test_postgres_helpers_are_available_from_persistence_package() -> None:
    postgres_module = importlib.import_module("tradingx.persistence.postgres")

    assert (
        postgres_module.redact_postgres_dsn(
            "postgresql://tradingx:super-secret@db.internal:5432/tradingx"
        )
        == "postgresql://tradingx:***@db.internal:5432/tradingx"
    )


def test_postgres_dsn_redaction_leaves_non_secret_segments_intact() -> None:
    from tradingx.persistence.postgres import redact_postgres_dsn

    assert (
        redact_postgres_dsn("postgresql://db.internal:5432/tradingx")
        == "postgresql://db.internal:5432/tradingx"
    )


def test_postgres_dsn_redaction_scrubs_query_passwords() -> None:
    from tradingx.persistence.postgres import redact_postgres_dsn

    assert (
        redact_postgres_dsn(
            "postgresql://db.internal:5432/tradingx"
            "?user=tradingx&password=super-secret&sslmode=require"
        )
        == "postgresql://db.internal:5432/tradingx"
        "?user=tradingx&password=***&sslmode=require"
    )
