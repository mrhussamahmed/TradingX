from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from tradingx.types import OrderRecord

REJECTED_STATUSES = {"canceled", "expired", "rejected", "suspended"}


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value or "0"))


def _normalize_enum(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).lower()


def _to_order_record(order: Any) -> OrderRecord:
    return OrderRecord(
        order_id=str(order.id),
        client_order_id=str(getattr(order, "client_order_id", "")),
        symbol=str(order.symbol),
        side=_normalize_enum(order.side),
        status=_normalize_enum(order.status),
        filled_qty=_to_decimal(getattr(order, "filled_qty", "0")),
        filled_avg_price=_to_decimal(getattr(order, "filled_avg_price", "0")),
    )


class OrderRejected(RuntimeError):
    """Raised when Alpaca rejects or cancels an order before fill."""


class OrderTimeout(RuntimeError):
    """Raised when an order does not fill before the timeout expires."""


class AlpacaPaperExecutionGateway:
    """Submit and monitor Alpaca paper orders.

    source: https://alpaca.markets/sdks/python/trading.html
        (retrieved 2026-04-17)
    source: https://alpaca.markets/sdks/python/api_reference/trading/orders.html
        (retrieved 2026-04-17)
    """

    def __init__(self, trading_client: TradingClient) -> None:
        self._trading_client = trading_client

    def submit_market_order(
        self,
        symbol: str,
        quantity: Decimal,
        side: OrderSide,
    ) -> OrderRecord:
        order_request = MarketOrderRequest(
            symbol=symbol,
            qty=float(quantity),
            side=side,
            time_in_force=TimeInForce.DAY,
            client_order_id=f"tradingx-{uuid.uuid4()}",
        )
        order = _to_order_record(self._trading_client.submit_order(order_request))
        if order.status in REJECTED_STATUSES:
            raise OrderRejected(
                f"Order {order.order_id} ended with status {order.status}."
            )
        return order

    def wait_for_fill(
        self,
        order_id: str,
        *,
        timeout_seconds: float = 30,
        poll_interval_seconds: float = 1,
    ) -> OrderRecord:
        deadline = time.monotonic() + timeout_seconds
        while True:
            order = _to_order_record(self._trading_client.get_order_by_id(order_id))
            if order.status == "filled":
                return order
            if order.status in REJECTED_STATUSES:
                raise OrderRejected(
                    f"Order {order_id} ended with status {order.status}."
                )
            if time.monotonic() >= deadline:
                raise OrderTimeout(f"Timed out waiting for order {order_id} to fill.")
            time.sleep(poll_interval_seconds)
