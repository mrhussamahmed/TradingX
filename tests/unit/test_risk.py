from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alpaca.trading.enums import OrderSide

from tradingx.config import TradingConfig
from tradingx.live_probe_governance import build_authority_boundary
from tradingx.risk import (
    PaperOnlyRiskEngine,
    PreTradeRiskContext,
    RiskViolation,
)
from tradingx.types import MarketSnapshot, PortfolioState, TradeIntent


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


def make_engine() -> PaperOnlyRiskEngine:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )
    return PaperOnlyRiskEngine(
        config,
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    )


def make_live_ready_engine(tmp_path: Path) -> PaperOnlyRiskEngine:
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
    return PaperOnlyRiskEngine(
        config,
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    )


def make_context(**overrides: object) -> PreTradeRiskContext:
    values: dict[str, object] = {
        "symbol": "SPY",
        "side": OrderSide.BUY,
        "quantity": Decimal("1"),
        "last_trade_price": Decimal("600.00"),
        "average_daily_volume_30d": Decimal("1500000"),
        "market_data_timestamp": datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        "account_equity": Decimal("10000.00"),
        "buying_power": Decimal("20000.00"),
        "current_position_quantity": Decimal("0"),
        "broker_state_timestamp": datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        "kill_switch_active": False,
    }
    values.update(overrides)
    return PreTradeRiskContext(**values)


def test_rejects_live_orders_while_live_trading_is_disabled() -> None:
    engine = make_engine()

    with pytest.raises(RiskViolation, match="Live trading remains disabled"):
        engine.assert_order_allowed(make_context(), is_live_order=True)


def test_rejects_non_positive_quantities() -> None:
    engine = make_engine()

    with pytest.raises(RiskViolation, match="Quantity must be positive"):
        engine.assert_order_allowed(
            make_context(quantity=Decimal("0")),
            is_live_order=False,
        )


def test_allows_paper_order_for_positive_quantity() -> None:
    engine = make_engine()

    engine.assert_order_allowed(make_context(), is_live_order=False)


def test_allows_live_orders_when_live_controls_are_satisfied(tmp_path) -> None:
    engine = make_live_ready_engine(tmp_path)

    engine.assert_order_allowed(make_context(), is_live_order=True)


def test_rejects_stale_market_data() -> None:
    engine = make_engine()

    with pytest.raises(RiskViolation, match="Market data is stale"):
        engine.assert_order_allowed(
            make_context(
                market_data_timestamp=datetime(2026, 4, 17, 16, 58, 59, tzinfo=UTC)
            ),
            is_live_order=False,
        )


def test_rejects_stale_broker_state() -> None:
    engine = make_engine()

    with pytest.raises(RiskViolation, match="Broker state is stale"):
        engine.assert_order_allowed(
            make_context(
                broker_state_timestamp=datetime(2026, 4, 17, 16, 54, 59, tzinfo=UTC)
            ),
            is_live_order=False,
        )


def test_rejects_symbols_below_price_floor() -> None:
    engine = make_engine()

    with pytest.raises(RiskViolation, match="Price floor"):
        engine.assert_order_allowed(
            make_context(last_trade_price=Decimal("4.99")),
            is_live_order=False,
        )


def test_rejects_illiquid_symbols() -> None:
    engine = make_engine()

    with pytest.raises(RiskViolation, match="Liquidity filter"):
        engine.assert_order_allowed(
            make_context(average_daily_volume_30d=Decimal("999999")),
            is_live_order=False,
        )


def test_rejects_symbol_concentration_breach() -> None:
    engine = make_engine()

    with pytest.raises(RiskViolation, match="single-symbol concentration"):
        engine.assert_order_allowed(
            make_context(
                quantity=Decimal("5"),
                last_trade_price=Decimal("500.00"),
                account_equity=Decimal("10000.00"),
            ),
            is_live_order=False,
        )


def test_rejects_orders_that_exceed_buying_power() -> None:
    engine = make_engine()

    with pytest.raises(RiskViolation, match="Intraday margin"):
        engine.assert_order_allowed(
            make_context(
                quantity=Decimal("10"),
                last_trade_price=Decimal("300.00"),
                buying_power=Decimal("1000.00"),
                account_equity=Decimal("50000.00"),
            ),
            is_live_order=False,
        )


def test_allows_reducing_existing_exposure_even_with_low_buying_power() -> None:
    engine = make_engine()

    engine.assert_order_allowed(
        make_context(
            side=OrderSide.SELL,
            quantity=Decimal("1"),
            current_position_quantity=Decimal("1"),
            buying_power=Decimal("0"),
        ),
        is_live_order=False,
    )


def test_rejects_orders_when_kill_switch_is_active() -> None:
    engine = make_engine()

    with pytest.raises(RiskViolation, match="Kill switch"):
        engine.assert_order_allowed(
            make_context(kill_switch_active=True),
            is_live_order=False,
        )


def make_trade_intent(**overrides: object) -> TradeIntent:
    values: dict[str, object] = {
        "intent_id": "intent-1",
        "candidate_id": "baseline-long-only-v1",
        "symbol": "SPY",
        "side": "buy",
        "quantity": Decimal("1"),
        "reason_code": "baseline_long_entry",
        "generated_at_utc": datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return TradeIntent(**values)


def make_market_snapshot(**overrides: object) -> MarketSnapshot:
    values: dict[str, object] = {
        "symbol": "SPY",
        "last_trade_price": Decimal("101.00"),
        "bid_price": Decimal("100.95"),
        "ask_price": Decimal("101.05"),
        "average_daily_volume_30d": Decimal("1500000"),
        "timestamp": datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return MarketSnapshot(**values)


def make_portfolio_state(**overrides: object) -> PortfolioState:
    values: dict[str, object] = {
        "as_of_utc": datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        "cash": Decimal("10000.00"),
        "equity": Decimal("10000.00"),
        "buying_power": Decimal("20000.00"),
        "positions": (),
        "open_orders": (),
    }
    values.update(overrides)
    return PortfolioState(**values)


def test_evaluate_trade_intent_returns_approved_decision() -> None:
    engine = make_engine()

    decision = engine.evaluate_trade_intent(
        make_trade_intent(),
        make_market_snapshot(),
        make_portfolio_state(),
        broker_state_timestamp=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    )

    assert decision.decision == "approved"
    assert decision.control_code == "passed"
    assert decision.event is None


def test_evaluate_trade_intent_returns_blocked_event_with_control_code() -> None:
    engine = make_engine()

    decision = engine.evaluate_trade_intent(
        make_trade_intent(),
        make_market_snapshot(average_daily_volume_30d=Decimal("999999")),
        make_portfolio_state(),
        broker_state_timestamp=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    )

    assert decision.decision == "blocked"
    assert decision.control_code == "liquidity_filter"
    assert decision.event is not None
    assert decision.event.blocked is True
    assert decision.event.control_type == "liquidity_filter"
