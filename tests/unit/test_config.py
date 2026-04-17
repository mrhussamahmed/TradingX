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
            "TRADINGX_SERVICE_INTERVAL_SECONDS": "600",
            "TRADINGX_SYMBOL_UNIVERSE": "SPY,QQQ,IWM",
        }
    )

    assert config.runtime.artifact_root == Path("custom-artifacts")
    assert config.runtime.metrics_namespace == "paperbot"
    assert config.runtime.enforce_regular_hours is False
    assert config.runtime.command_timeout_seconds == 45
    assert config.runtime.service_interval_seconds == 600
    assert config.runtime.symbol_universe == ("SPY", "QQQ", "IWM")


def test_alert_transport_config_is_parsed_from_mapping() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_TELEGRAM_BOT_TOKEN": "bot-token",
            "TRADINGX_TELEGRAM_CHAT_ID": "chat-id",
            "TRADINGX_SMTP_HOST": "smtp.example.com",
            "TRADINGX_SMTP_PORT": "587",
            "TRADINGX_SMTP_USERNAME": "mailer",
            "TRADINGX_SMTP_PASSWORD": "secret",
            "TRADINGX_SMTP_FROM_EMAIL": "bot@example.com",
            "TRADINGX_SMTP_TO_EMAIL": "ops@example.com",
        }
    )

    assert config.alerting.telegram_bot_token == "bot-token"
    assert config.alerting.telegram_chat_id == "chat-id"
    assert config.alerting.smtp_host == "smtp.example.com"
    assert config.alerting.smtp_port == 587
    assert config.alerting.smtp_username == "mailer"
    assert config.alerting.smtp_password == "secret"
    assert config.alerting.smtp_from_email == "bot@example.com"
    assert config.alerting.smtp_to_email == "ops@example.com"
