from __future__ import annotations

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
