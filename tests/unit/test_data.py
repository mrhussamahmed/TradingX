from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tradingx import data as market_data_module
from tradingx.config import TradingConfig
from tradingx.data import build_market_data_gateway_for_mode
from tradingx.live_probe_governance import build_authority_boundary


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


def test_market_data_gateway_uses_live_credentials_for_live_mode(
    monkeypatch,
    tmp_path,
) -> None:
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
            "TRADINGX_GATE4_OPERATOR_SIGNOFF": "true",
            "TRADINGX_GATE4_CHECKLIST_APPROVED": "true",
            "TRADINGX_GATE4_APPROVAL_FILE": str(
                _write_gate4_approval(tmp_path / "gate4-approval.json")
            ),
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


def test_market_data_gateway_fails_closed_for_incomplete_live_controls() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_LIVE_API_KEY": "pk-live",
            "ALPACA_LIVE_API_SECRET": "sk-live",
            "TRADINGX_BROKER_MODE": "live",
            "TRADINGX_LIVE_CONFIG_ENABLED": "true",
        }
    )

    with pytest.raises(RuntimeError, match="env_layer_disabled"):
        build_market_data_gateway_for_mode(config, broker_mode="live")
