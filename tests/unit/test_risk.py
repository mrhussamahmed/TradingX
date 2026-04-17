from __future__ import annotations

from decimal import Decimal

import pytest

from tradingx.config import TradingConfig
from tradingx.risk import PaperOnlyRiskEngine, RiskViolation


def test_rejects_live_orders_while_live_trading_is_disabled() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )
    engine = PaperOnlyRiskEngine(config)

    with pytest.raises(RiskViolation, match="Live trading remains disabled"):
        engine.assert_order_allowed("SPY", Decimal("1"), is_live_order=True)


def test_rejects_non_positive_quantities() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )
    engine = PaperOnlyRiskEngine(config)

    with pytest.raises(RiskViolation, match="Quantity must be positive"):
        engine.assert_order_allowed("SPY", Decimal("0"), is_live_order=False)


def test_allows_paper_order_for_positive_quantity() -> None:
    config = TradingConfig.from_mapping(
        {
            "ALPACA_PAPER_API_KEY": "pk-paper",
            "ALPACA_PAPER_API_SECRET": "sk-paper",
        }
    )
    engine = PaperOnlyRiskEngine(config)

    engine.assert_order_allowed("SPY", Decimal("1"), is_live_order=False)
