from __future__ import annotations

import pytest

from tradingx import data as market_data_module
from tradingx.config import TradingConfig
from tradingx.data import build_market_data_gateway_for_mode


def test_market_data_gateway_uses_paper_credentials_for_paper_mode(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _fake_from_credentials(*, api_key: str, api_secret: str):
        captured["api_key"] = api_key
        captured["api_secret"] = api_secret
        return object()

    monkeypatch.setattr(
        market_data_module.AlpacaMarketDataGateway,
        "from_credentials",
        staticmethod(_fake_from_credentials),
    )

    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )

    build_market_data_gateway_for_mode(config, broker_mode="paper")

    assert captured == {"api_key": "pk-paper", "api_secret": "sk-paper"}


def test_market_data_gateway_uses_live_credentials_for_live_mode(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _fake_from_credentials(*, api_key: str, api_secret: str):
        captured["api_key"] = api_key
        captured["api_secret"] = api_secret
        return object()

    monkeypatch.setattr(
        market_data_module.AlpacaMarketDataGateway,
        "from_credentials",
        staticmethod(_fake_from_credentials),
    )

    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
            "TRADINGX_ENABLE_LIVE_TRADING": "true",
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "local-secret",
        }
    )

    build_market_data_gateway_for_mode(config, broker_mode="live")

    assert captured == {"api_key": "pk-live", "api_secret": "sk-live"}


def test_market_data_gateway_fails_closed_for_live_mode_without_live_credentials() -> (
    None
):
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
            "TRADINGX_ENABLE_LIVE_TRADING": "true",
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "local-secret",
        }
    )

    with pytest.raises(RuntimeError, match="missing_live_credentials"):
        build_market_data_gateway_for_mode(config, broker_mode="live")
