from __future__ import annotations

from pathlib import Path

from tradingx.config import TradingConfig


def test_placeholder_credentials_are_not_treated_as_real() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "your-paper-key-here",
            "ALPACA_PAPER_API_SECRET": "your-paper-secret-here",
        }
    )

    assert not config.has_real_paper_credentials()
    assert not config.live_controls.all_layers_enabled()


def test_real_paper_credentials_enable_paper_mode_only() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
            "ALPACA_PAPER_ACCOUNT_ID": "paper-account",
        }
    )

    assert config.has_real_paper_credentials()
    assert config.paper_credentials.account_id == "paper-account"
    assert not config.live_controls.all_layers_enabled()


def test_runtime_config_defaults_are_safe() -> None:
    config = TradingConfig.from_mapping({})

    assert config.runtime.artifact_root == Path("artifacts")
    assert config.runtime.metrics_namespace == "tradingx"
    assert config.runtime.enforce_regular_hours is True


def test_runtime_config_overrides_are_parsed_from_mapping() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_ARTIFACT_ROOT": "custom-artifacts",
            "TRADINGX_METRICS_NAMESPACE": "paperbot",
            "TRADINGX_ENFORCE_REGULAR_HOURS": "false",
            "TRADINGX_COMMAND_TIMEOUT_SECONDS": "45",
        }
    )

    assert config.runtime.artifact_root == Path("custom-artifacts")
    assert config.runtime.metrics_namespace == "paperbot"
    assert config.runtime.enforce_regular_hours is False
    assert config.runtime.command_timeout_seconds == 45
