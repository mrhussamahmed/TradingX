from __future__ import annotations

from tradingx import live_enablement
from tradingx.config import TradingConfig
from tradingx.live_enablement import (
    LiveModeDisabledError,
    build_trading_client_for_mode,
    resolve_broker_mode,
)


def _live_ready_config() -> TradingConfig:
    return TradingConfig.from_mapping(
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


def test_resolve_broker_mode_defaults_to_paper() -> None:
    decision = resolve_broker_mode(TradingConfig.from_mapping({}))

    assert decision.requested_mode == "paper"
    assert decision.effective_mode == "paper"
    assert decision.live_requested is False
    assert decision.live_allowed is False
    assert decision.disable_reasons == ()


def test_resolve_broker_mode_blocks_when_live_credentials_are_missing() -> None:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
            "TRADINGX_ENABLE_LIVE_TRADING": "true",
            "TRADINGX_WEB_WRITE_SIGNING_SECRET": "local-secret",
        }
    )

    decision = resolve_broker_mode(config)

    assert decision.live_requested is True
    assert decision.live_allowed is False
    assert "missing_live_credentials" in decision.disable_reasons


def test_resolve_broker_mode_blocks_when_live_controls_are_incomplete() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
        }
    )

    decision = resolve_broker_mode(config)

    assert decision.live_requested is True
    assert decision.live_allowed is False
    assert "env_layer_disabled" in decision.disable_reasons
    assert "web_write_signing_unconfigured" in decision.disable_reasons


def test_resolve_broker_mode_allows_live_when_all_layers_are_complete() -> None:
    decision = resolve_broker_mode(_live_ready_config())

    assert decision.live_requested is True
    assert decision.live_allowed is True
    assert decision.effective_mode == "live"
    assert decision.disable_reasons == ()


def test_build_trading_client_for_mode_uses_paper_credentials(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeTradingClient:
        def __init__(self, api_key: str, api_secret: str, *, paper: bool) -> None:
            captured["api_key"] = api_key
            captured["api_secret"] = api_secret
            captured["paper"] = paper

    monkeypatch.setattr(live_enablement, "TradingClient", _FakeTradingClient)

    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )
    decision = resolve_broker_mode(config)

    build_trading_client_for_mode(config, decision)

    assert captured == {
        "api_key": "pk-paper",
        "api_secret": "sk-paper",
        "paper": True,
    }


def test_build_trading_client_for_mode_uses_live_credentials(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeTradingClient:
        def __init__(self, api_key: str, api_secret: str, *, paper: bool) -> None:
            captured["api_key"] = api_key
            captured["api_secret"] = api_secret
            captured["paper"] = paper

    monkeypatch.setattr(live_enablement, "TradingClient", _FakeTradingClient)

    config = _live_ready_config()
    decision = resolve_broker_mode(config)

    build_trading_client_for_mode(config, decision)

    assert captured == {
        "api_key": "pk-live",
        "api_secret": "sk-live",
        "paper": False,
    }


def test_build_trading_client_for_mode_fails_closed_when_live_mode_is_blocked() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
            "TRADINGX_BROKER_MODE": "live",
        }
    )
    decision = resolve_broker_mode(config)

    try:
        build_trading_client_for_mode(config, decision)
    except LiveModeDisabledError as error:
        assert "config_layer_disabled" in error.reasons
        assert "env_layer_disabled" in error.reasons
    else:
        raise AssertionError("Expected live mode to fail closed.")
