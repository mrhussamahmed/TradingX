from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alpaca.trading.enums import OrderSide, TimeInForce

from tradingx.execution import (
    AlpacaPaperExecutionGateway,
    OrderRejected,
    sum_per_sleeve_notional,
)
from tradingx.types import ExecutionLifecycleRecord


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
        self.order_by_client_id: FakeOrder | None = None

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

    def get_order_by_client_id(self, client_order_id):
        if self.order_by_client_id is None:
            raise RuntimeError('{"message":"order not found"}')
        return self.order_by_client_id


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


def test_submit_marketable_limit_order_uses_limit_order_request() -> None:
    client = FakeTradingClient()
    gateway = AlpacaPaperExecutionGateway(trading_client=client)

    submitted = gateway.submit_marketable_limit_order(
        "SPY",
        Decimal("1"),
        OrderSide.BUY,
        limit_price=Decimal("600.16"),
        time_in_force=TimeInForce.DAY,
        client_order_id="cid-limit",
    )

    assert client.submitted.symbol == "SPY"
    assert client.submitted.limit_price == 600.16
    assert client.submitted.time_in_force == TimeInForce.DAY
    assert submitted.client_order_id == "cid-limit"


def test_find_order_by_client_id_returns_none_when_broker_has_no_match() -> None:
    client = FakeTradingClient()
    gateway = AlpacaPaperExecutionGateway(trading_client=client)

    existing = gateway.find_order_by_client_id("cid-missing")

    assert existing is None


def test_find_order_by_client_id_returns_existing_order_when_present() -> None:
    client = FakeTradingClient()
    client.order_by_client_id = FakeOrder(
        order_id="order-existing",
        status="accepted",
        client_order_id="cid-existing",
    )
    gateway = AlpacaPaperExecutionGateway(trading_client=client)

    existing = gateway.find_order_by_client_id("cid-existing")

    assert existing is not None
    assert existing.order_id == "order-existing"
    assert existing.client_order_id == "cid-existing"


def test_submit_oco_exit_order_uses_complex_exit_group() -> None:
    client = FakeTradingClient()
    gateway = AlpacaPaperExecutionGateway(trading_client=client)

    submitted = gateway.submit_oco_exit_order(
        "SPY",
        Decimal("1"),
        take_profit_limit=Decimal("599.90"),
        stop_price=Decimal("599.65"),
    )

    assert client.submitted.symbol == "SPY"
    assert client.submitted.order_class.value == "oco"
    assert client.submitted.take_profit.limit_price == 599.9
    assert client.submitted.stop_loss.stop_price == 599.65
    assert submitted.status == "accepted"


class FakeClosePositionTradingClient:
    def __init__(self) -> None:
        self.closed_symbol = None
        self.order_reads = [
            FakeOrder(order_id="close-order-1", status="new", side="sell"),
            FakeOrder(order_id="close-order-1", status="filled", side="sell"),
        ]

    def close_position(self, symbol):
        self.closed_symbol = symbol
        return FakeOrder(
            order_id="close-order-1",
            status="accepted",
            symbol=symbol,
            side="sell",
            client_order_id="close-order-1-client",
            filled_qty="0",
            filled_avg_price="0",
        )

    def get_order_by_id(self, order_id, filter=None):
        return self.order_reads.pop(0)


def test_close_position_submits_and_waits_for_fill() -> None:
    client = FakeClosePositionTradingClient()
    gateway = AlpacaPaperExecutionGateway(trading_client=client)

    submitted = gateway.close_position("SPY")
    filled = gateway.wait_for_fill(
        submitted.order_id,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert client.closed_symbol == "SPY"
    assert submitted.status == "accepted"
    assert filled.status == "filled"
    assert filled.side == "sell"


class ErrorTradingClient:
    def submit_order(self, order_data):
        raise RuntimeError('{"message":"potential wash trade detected"}')


def test_submit_order_sanitizes_broker_error_details() -> None:
    gateway = AlpacaPaperExecutionGateway(trading_client=ErrorTradingClient())

    with pytest.raises(OrderRejected, match="potential wash trade detected"):
        gateway.submit_market_order("SPY", Decimal("1"), OrderSide.BUY)


class FakeNestedTradingClient:
    def get_order_by_id(self, order_id, filter=None):
        canceled_leg = FakeOrder(order_id="order-2", status="canceled", side="sell")
        filled_leg = FakeOrder(order_id="order-3", status="filled", side="sell")
        parent = FakeOrder(order_id="order-1", status="accepted", side="sell")
        parent.legs = [canceled_leg, filled_leg]
        return parent


def test_wait_for_oco_exit_fill_ignores_canceled_sibling_when_other_leg_fills() -> None:
    gateway = AlpacaPaperExecutionGateway(trading_client=FakeNestedTradingClient())

    filled = gateway.wait_for_oco_exit_fill(
        "order-1",
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert filled.order_id == "order-3"
    assert filled.status == "filled"


class FakeFilledParentOcoTradingClient:
    def get_order_by_id(self, order_id, filter=None):
        canceled_leg = FakeOrder(order_id="order-2", status="canceled", side="sell")
        parent = FakeOrder(order_id="order-1", status="filled", side="sell")
        parent.legs = [canceled_leg]
        return parent


def test_wait_for_oco_exit_fill_returns_filled_parent_order() -> None:
    gateway = AlpacaPaperExecutionGateway(
        trading_client=FakeFilledParentOcoTradingClient()
    )

    filled = gateway.wait_for_oco_exit_fill(
        "order-1",
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert filled.order_id == "order-1"
    assert filled.status == "filled"


def test_sum_per_sleeve_notional_skips_legacy_records_without_attributions() -> None:
    records = (
        ExecutionLifecycleRecord(
            execution_id="execution-1",
            intent_id="intent-1",
            symbol="SPY",
            side="buy",
            reason_code="baseline_long_entry",
            reference_price=Decimal("100.00"),
            fill_price=Decimal("100.00"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("0"),
            submitted_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
            filled_at_utc=datetime(2026, 4, 22, 13, 1, tzinfo=UTC),
            recovered=False,
        ),
    )

    assert sum_per_sleeve_notional(records) == {}
