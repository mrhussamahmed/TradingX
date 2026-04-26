"""Wave-8 deferred runtime red test (Defect 2).

Verifies that any code path constructing :class:`AlpacaPaperExecutionGateway`
without an authority guard AND without an explicit ``legacy_paper_non_authority``
flag fails closed. After Defect 2 the production builders no longer set the
legacy flag, so a direct construction with just a trading client must
refuse to submit orders.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from alpaca.trading.enums import OrderSide, TimeInForce

from tradingx.execution import (
    AlpacaPaperExecutionGateway,
    OrderRouteAuthorityError,
)


class _FakeOrder:
    def __init__(self, *, order_id: str, status: str, symbol: str = "SPY") -> None:
        self.id = order_id
        self.status = status
        self.symbol = symbol
        self.side = "buy"
        self.client_order_id = "cid-1"
        self.filled_qty = "0"
        self.filled_avg_price = "0"


class _FakeTradingClient:
    def submit_order(self, order_data):  # noqa: D401, ANN001 - test stub
        return _FakeOrder(
            order_id="order-1",
            status="accepted",
            symbol=order_data.symbol,
        )

    def close_position(self, symbol):  # noqa: D401, ANN001 - test stub
        return _FakeOrder(order_id="close-1", status="accepted", symbol=symbol)


def test_direct_trading_client_route_blocked_by_default() -> None:
    """Direct gateway construction without a guard must refuse all orders."""

    gateway = AlpacaPaperExecutionGateway(trading_client=_FakeTradingClient())

    assert not gateway.v5_order_authorized
    with pytest.raises(OrderRouteAuthorityError):
        gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)
    with pytest.raises(OrderRouteAuthorityError):
        gateway.submit_marketable_limit_order(
            "SPY",
            Decimal("1"),
            OrderSide.BUY,
            limit_price=Decimal("600"),
            time_in_force=TimeInForce.DAY,
        )
    with pytest.raises(OrderRouteAuthorityError):
        gateway.submit_oco_exit_order(
            "SPY",
            Decimal("1"),
            take_profit_limit=Decimal("610"),
            stop_price=Decimal("590"),
        )
    with pytest.raises(OrderRouteAuthorityError):
        gateway.close_position("SPY")
