from __future__ import annotations

from decimal import Decimal

from alpaca.trading.enums import OrderSide

from tradingx.execution import AlpacaPaperExecutionGateway


class FakeOrder:
    def __init__(
        self,
        *,
        order_id: str,
        status: str,
        symbol: str = "SPY",
        side: str = "buy",
        client_order_id: str = "cid-1",
        filled_qty: str = "1",
        filled_avg_price: str = "600.00",
    ) -> None:
        self.id = order_id
        self.status = status
        self.symbol = symbol
        self.side = side
        self.client_order_id = client_order_id
        self.filled_qty = filled_qty
        self.filled_avg_price = filled_avg_price


class FakeTradingClient:
    def __init__(self) -> None:
        self.submitted = None
        self.order_reads = [
            FakeOrder(order_id="order-1", status="new"),
            FakeOrder(order_id="order-1", status="filled"),
        ]

    def submit_order(self, order_data):
        self.submitted = order_data
        return FakeOrder(
            order_id="order-1",
            status="accepted",
            symbol=order_data.symbol,
            side=order_data.side.value,
            client_order_id=order_data.client_order_id,
            filled_qty="0",
            filled_avg_price="0",
        )

    def get_order_by_id(self, order_id, filter=None):
        return self.order_reads.pop(0)


def test_submit_and_wait_for_fill() -> None:
    client = FakeTradingClient()
    gateway = AlpacaPaperExecutionGateway(trading_client=client)

    submitted = gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)
    filled = gateway.wait_for_fill(
        submitted.order_id,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert client.submitted.symbol == "SPY"
    assert submitted.status == "accepted"
    assert filled.status == "filled"
    assert filled.filled_qty == Decimal("1")
