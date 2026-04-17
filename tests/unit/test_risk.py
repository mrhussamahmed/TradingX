from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alpaca.trading.enums import OrderSide

from tradingx.config import TradingConfig
from tradingx.risk import PaperOnlyRiskEngine, PreTradeRiskContext, RiskViolation


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
