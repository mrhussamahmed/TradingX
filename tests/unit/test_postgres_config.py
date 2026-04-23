from __future__ import annotations

import pytest

from tradingx.config import TradingConfig


def test_control_plane_config_defaults_are_legacy_safe() -> None:
    config = TradingConfig.from_mapping({})

    assert config.control_plane.postgres_dsn == ""
    assert config.control_plane.store == "legacy"
    assert config.control_plane.domain_stores == ()
    assert config.control_plane.postgres_required is False
    assert config.control_plane.projection_mode == "disabled"
    assert config.control_plane.projection_batch_size == 250
    assert config.control_plane.legacy_bridge_mode == "disabled"
    assert config.control_plane.legacy_backfill_enabled is False
    assert config.control_plane.legacy_backfill_batch_size == 500
    assert config.control_plane.projection_max_lag_seconds == 30


def test_control_plane_config_parses_mapping_overrides() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_POSTGRES_DSN": (
                "postgresql://tradingx:super-secret@db.internal:5432/tradingx"
            ),
            "TRADINGX_CONTROL_PLANE_STORE": "postgres",
            "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": (
                "documents=postgres,runtime=legacy,validation=postgres"
            ),
            "TRADINGX_POSTGRES_REQUIRED": "true",
            "TRADINGX_PROJECTION_MODE": "runner",
            "TRADINGX_PROJECTION_BATCH_SIZE": "1000",
            "TRADINGX_LEGACY_BRIDGE_MODE": "tail",
            "TRADINGX_LEGACY_BACKFILL_ENABLED": "true",
            "TRADINGX_LEGACY_BACKFILL_BATCH_SIZE": "750",
            "TRADINGX_PROJECTION_MAX_LAG_SECONDS": "90",
        }
    )

    assert (
        config.control_plane.postgres_dsn
        == "postgresql://tradingx:super-secret@db.internal:5432/tradingx"
    )
    assert config.control_plane.store == "postgres"
    assert config.control_plane.domain_stores == (
        ("documents", "postgres"),
        ("runtime", "legacy"),
        ("validation", "postgres"),
    )
    assert config.control_plane.postgres_required is True
    assert config.control_plane.projection_mode == "runner"
    assert config.control_plane.projection_batch_size == 1000
    assert config.control_plane.legacy_bridge_mode == "tail"
    assert config.control_plane.legacy_backfill_enabled is True
    assert config.control_plane.legacy_backfill_batch_size == 750
    assert config.control_plane.projection_max_lag_seconds == 90


def test_safe_summary_redacts_control_plane_postgres_dsn() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_POSTGRES_DSN": (
                "postgresql://tradingx:super-secret@db.internal:5432/tradingx"
            ),
        }
    )

    summary = config.to_safe_summary()

    assert summary["control_plane_postgres_configured"] is True
    assert (
        summary["control_plane_postgres_dsn_redacted"]
        == "postgresql://tradingx:***@db.internal:5432/tradingx"
    )
    assert "super-secret" not in str(summary)


@pytest.mark.parametrize(
    "domain_stores",
    (
        "documents=hybrid",
        "documents=unknown",
    ),
)
def test_control_plane_domain_store_overrides_reject_invalid_store_values(
    domain_stores: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="TRADINGX_CONTROL_PLANE_DOMAIN_STORES",
    ):
        TradingConfig.from_mapping(
            {
                "TRADINGX_CONTROL_PLANE_DOMAIN_STORES": domain_stores,
            }
        )


def test_safe_summary_redacts_query_passwords_in_control_plane_postgres_dsn() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_POSTGRES_DSN": (
                "postgresql://db.internal:5432/tradingx"
                "?user=tradingx&password=super-secret&sslmode=require"
            ),
        }
    )

    summary = config.to_safe_summary()

    assert summary["control_plane_postgres_configured"] is True
    assert (
        summary["control_plane_postgres_dsn_redacted"]
        == "postgresql://db.internal:5432/tradingx"
        "?user=tradingx&password=***&sslmode=require"
    )
    assert "super-secret" not in str(summary)
