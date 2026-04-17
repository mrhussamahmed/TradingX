from __future__ import annotations

import json
import time
import uuid
from decimal import Decimal
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    GetOrderByIdRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

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


def _extract_broker_error_message(error: Exception) -> str:
    try:
        payload = json.loads(str(error))
    except json.JSONDecodeError:
        return str(error)
    if isinstance(payload, dict):
        for key in ("message", "reject_reason", "code"):
            value = payload.get(key)
            if value:
                return str(value)
    return str(error)


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
        *,
        client_order_id: str | None = None,
    ) -> OrderRecord:
        order_request = MarketOrderRequest(
            symbol=symbol,
            qty=float(quantity),
            side=side,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id or f"tradingx-{uuid.uuid4()}",
        )
        try:
            raw_order = self._trading_client.submit_order(order_request)
        except Exception as error:
            raise OrderRejected(_extract_broker_error_message(error)) from None
        order = _to_order_record(raw_order)
        if order.status in REJECTED_STATUSES:
            raise OrderRejected(
                f"Order {order.order_id} ended with status {order.status}."
            )
        return order

    def get_order_by_client_id(self, client_order_id: str) -> OrderRecord:
        try:
            raw_order = self._trading_client.get_order_by_client_id(client_order_id)
        except Exception as error:
            raise OrderRejected(_extract_broker_error_message(error)) from None
        return _to_order_record(raw_order)

    def submit_oco_exit_order(
        self,
        symbol: str,
        quantity: Decimal,
        *,
        take_profit_limit: Decimal,
        stop_price: Decimal,
    ) -> OrderRecord:
        order_request = LimitOrderRequest(
            symbol=symbol,
            qty=float(quantity),
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.OCO,
            take_profit=TakeProfitRequest(limit_price=float(take_profit_limit)),
            stop_loss=StopLossRequest(stop_price=float(stop_price)),
            client_order_id=f"tradingx-{uuid.uuid4()}",
        )
        try:
            raw_order = self._trading_client.submit_order(order_request)
        except Exception as error:
            raise OrderRejected(_extract_broker_error_message(error)) from None
        order = _to_order_record(raw_order)
        if order.status in REJECTED_STATUSES:
            raise OrderRejected(
                f"Order {order.order_id} ended with status {order.status}."
            )
        return order

    def close_position(self, symbol: str) -> OrderRecord:
        """Close an existing Alpaca paper position with the broker helper.

        source: https://alpaca.markets/sdks/python/api_reference/trading/positions.html
            (retrieved 2026-04-17)
        """
        try:
            raw_order = self._trading_client.close_position(symbol)
        except Exception as error:
            raise OrderRejected(_extract_broker_error_message(error)) from None
        order = _to_order_record(raw_order)
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
            try:
                raw_order = self._trading_client.get_order_by_id(order_id)
            except Exception as error:
                raise OrderRejected(_extract_broker_error_message(error)) from None
            order = _to_order_record(raw_order)
            if order.status == "filled":
                return order
            if order.status in REJECTED_STATUSES:
                raise OrderRejected(
                    f"Order {order_id} ended with status {order.status}."
                )
            if time.monotonic() >= deadline:
                raise OrderTimeout(f"Timed out waiting for order {order_id} to fill.")
            time.sleep(poll_interval_seconds)

    def wait_for_oco_exit_fill(
        self,
        order_id: str,
        *,
        timeout_seconds: float = 30,
        poll_interval_seconds: float = 1,
    ) -> OrderRecord:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                raw_order = self._trading_client.get_order_by_id(
                    order_id,
                    filter=GetOrderByIdRequest(nested=True),
                )
            except Exception as error:
                raise OrderRejected(_extract_broker_error_message(error)) from None
            parent_order = _to_order_record(raw_order)
            if parent_order.status == "filled":
                return parent_order
            filled_leg = self._find_filled_leg(raw_order)
            if filled_leg is not None:
                return filled_leg
            if parent_order.status in REJECTED_STATUSES:
                raise OrderRejected(
                    f"Order {order_id} ended with status {parent_order.status}."
                )
            if time.monotonic() >= deadline:
                raise OrderTimeout(
                    f"Timed out waiting for OCO exit order {order_id} to fill."
                )
            time.sleep(poll_interval_seconds)

    def _find_filled_leg(self, order: Any) -> OrderRecord | None:
        leg_records = [
            _to_order_record(leg) for leg in list(getattr(order, "legs", None) or [])
        ]
        for leg_record in leg_records:
            if leg_record.status == "filled":
                return leg_record
        for leg_record in leg_records:
            if leg_record.status in {"expired", "rejected", "suspended"}:
                raise OrderRejected(
                    "Order leg "
                    f"{leg_record.order_id} ended with status "
                    f"{leg_record.status}."
                )
        if leg_records and all(
            leg_record.status == "canceled" for leg_record in leg_records
        ):
            raise OrderRejected("All OCO exit legs were canceled before fill.")
        return None
