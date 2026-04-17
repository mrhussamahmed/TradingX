from __future__ import annotations

from decimal import Decimal
from typing import Any

from alpaca.trading.client import TradingClient

from tradingx.types import AccountSnapshot


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


class AlpacaPortfolioGateway:
    """Read account and position state from Alpaca.

    source: https://alpaca.markets/sdks/python/trading.html
        (retrieved 2026-04-17)
    source: https://alpaca.markets/sdks/python/api_reference/trading/account.html
        (retrieved 2026-04-17)
    """

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
