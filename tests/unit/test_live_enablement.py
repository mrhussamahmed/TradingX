from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tradingx import live_enablement
from tradingx.config import TradingConfig
from tradingx.live_enablement import (
    LiveModeDisabledError,
    build_trading_client_for_mode,
    resolve_broker_mode,
)
from tradingx.live_probe_governance import build_authority_boundary


def _live_technical_ready_config() -> TradingConfig:
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


def _write_gate4_approval(path: Path) -> Path:
    payload = build_authority_boundary(
        boundary_id="gate4-approval-001",
        approval_type="gate4_live_trading",
        identity_provider="local-ops",
        operator_identity_ids=["operator:local-a"],
        role_registry_version="gate4-v1",
        role="gate4-operator",
        scope="live_trading",
        write_authorization_status="authorized",
        max_exception_duration_seconds=0,
        second_approver_required=False,
        approvers=["operator:local-a"],
        canonical_approval_payload_hash="sha256:" + "a" * 64,
        signatures=["signature-ref"],
        checklist_evidence_refs=["artifact://gate4/checklist"],
        approved_at_utc=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        expires_at_utc=datetime(2099, 1, 1, 0, 0, tzinfo=UTC),
    )
    path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return path


def _live_gate4_signed_config(tmp_path: Path) -> TradingConfig:
    approval_file = _write_gate4_approval(tmp_path / "gate4-approval.json")
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
            "TRADINGX_GATE4_OPERATOR_SIGNOFF": "true",
            "TRADINGX_GATE4_CHECKLIST_APPROVED": "true",
            "TRADINGX_GATE4_APPROVAL_FILE": str(approval_file),
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


def test_resolve_broker_mode_blocks_without_gate4_signoff() -> None:
    decision = resolve_broker_mode(_live_technical_ready_config())

    assert decision.live_requested is True
    assert decision.live_allowed is False
    assert decision.effective_mode == "paper"
    assert "operator_signoff_missing" in decision.disable_reasons
    assert "gate4_checklist_missing" in decision.disable_reasons


def test_resolve_broker_mode_allows_live_when_all_layers_are_complete(
    tmp_path,
) -> None:
    decision = resolve_broker_mode(_live_gate4_signed_config(tmp_path))

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


def test_build_trading_client_for_mode_uses_live_credentials(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}

    class _FakeTradingClient:
        def __init__(self, api_key: str, api_secret: str, *, paper: bool) -> None:
            captured["api_key"] = api_key
            captured["api_secret"] = api_secret
            captured["paper"] = paper

    monkeypatch.setattr(live_enablement, "TradingClient", _FakeTradingClient)

    config = _live_gate4_signed_config(tmp_path)
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
