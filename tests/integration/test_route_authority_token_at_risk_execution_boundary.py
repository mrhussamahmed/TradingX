"""Wave-8 deferred runtime red test (Defect 2).

Verifies the V5 OrderRouteAuthorityGuard rejects an order when the
promotion decision is capped below the required state — a route at the
"token-at-risk" boundary cannot bypass authority by returning a
falsely-elevated max_state.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from alpaca.trading.enums import OrderSide

from tradingx.execution import (
    AlpacaPaperExecutionGateway,
    OrderRouteAuthorityError,
    OrderRouteAuthorityGuard,
)
from tradingx.promotion import Blocker, PromotionDecision, PromotionState


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


def _decision_with_at_risk_blockers(
    strategy_id: str,
) -> PromotionDecision:
    """Decision capped at PAPER_TRADING with token-at-risk blockers.

    The bundle promised production but the authority record reports
    PAPER_TRADING with two outstanding blockers — exactly the
    "token-at-risk" boundary scenario where production routes must NOT
    submit live orders.
    """

    return PromotionDecision(
        strategy_id=strategy_id,
        requested_state=PromotionState.PRODUCTION,
        max_state=PromotionState.PAPER_TRADING,
        blockers=(
            Blocker("recertification_report_missing"),
            Blocker("drift_monitor_spec_missing"),
        ),
        artifact_refs=("sha256:" + "a" * 64,),
        ledger_sequence=1,
        ledger_hash="sha256:" + "b" * 64,
    )


def test_route_authority_token_at_risk_execution_boundary() -> None:
    """A production route fails closed when the decision is below required state."""

    guard = OrderRouteAuthorityGuard(
        decision_provider=_decision_with_at_risk_blockers,
        required_state=PromotionState.PRODUCTION,
        route_label="live_order",
    )
    gateway = AlpacaPaperExecutionGateway(
        trading_client=_FakeTradingClient(),
        authority_guard=guard,
        strategy_id="trend-following-v1",
    )

    with pytest.raises(OrderRouteAuthorityError) as excinfo:
        gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)
    message = str(excinfo.value)
    assert "live_order" in message
    assert "paper_trading" in message
    assert "production" in message
    assert "recertification_report_missing" in message
    assert "drift_monitor_spec_missing" in message
