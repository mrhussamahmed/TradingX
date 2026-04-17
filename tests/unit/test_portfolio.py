from __future__ import annotations

from decimal import Decimal

from tradingx.portfolio import AlpacaPortfolioGateway


class FakeAccount:
    cash = "1000.50"
    equity = "1001.50"
    buying_power = "2000.00"


class FakePosition:
    def __init__(self, symbol: str, qty: str) -> None:
        self.symbol = symbol
        self.qty = qty


class FakeTradingClient:
    def get_account(self):
        return FakeAccount()

    def get_all_positions(self):
        return [FakePosition("SPY", "1")]


def test_account_snapshot_and_position_lookup_use_decimals() -> None:
    gateway = AlpacaPortfolioGateway(trading_client=FakeTradingClient())

    snapshot = gateway.get_account_snapshot()

    assert snapshot.cash == Decimal("1000.50")
    assert snapshot.equity == Decimal("1001.50")
    assert gateway.get_position_quantity("SPY") == Decimal("1")
    assert gateway.get_position_quantity("QQQ") == Decimal("0")
