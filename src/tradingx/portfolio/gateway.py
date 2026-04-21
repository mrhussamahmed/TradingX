from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

from tradingx.types import AccountSnapshot, PortfolioState, PositionSnapshot


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


class AlpacaPortfolioGateway:
    """Read account and position state from Alpaca."""

    def __init__(self, trading_client: TradingClient) -> None:
        self._trading_client = trading_client

    def get_account_snapshot(self) -> AccountSnapshot:
        account: Any = self._trading_client.get_account()
        return AccountSnapshot(
            cash=_to_decimal(account.cash),
            equity=_to_decimal(account.equity),
            buying_power=_to_decimal(account.buying_power),
        )

    def get_position_quantity(self, symbol: str) -> Decimal:
        positions: list[Any] = list(self._trading_client.get_all_positions())
        for position in positions:
            if position.symbol == symbol:
                return _to_decimal(position.qty)
        return Decimal("0")

    def get_portfolio_state(self) -> PortfolioState:
        account_snapshot = self.get_account_snapshot()
        positions: list[Any] = list(self._trading_client.get_all_positions())
        open_orders: list[Any] = list(
            self._trading_client.get_orders(
                GetOrdersRequest(status=QueryOrderStatus.OPEN)
            )
        )
        return PortfolioState(
            as_of_utc=datetime.now(UTC),
            cash=account_snapshot.cash,
            equity=account_snapshot.equity,
            buying_power=account_snapshot.buying_power,
            positions=tuple(
                PositionSnapshot(
                    symbol=str(position.symbol),
                    quantity=_to_decimal(position.qty),
                    average_entry_price=_to_decimal(position.avg_entry_price),
                    market_value=_to_decimal(position.market_value),
                )
                for position in positions
            ),
            open_orders=tuple(str(order.id) for order in open_orders),
        )


__all__ = ("AlpacaPortfolioGateway",)
