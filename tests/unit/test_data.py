from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.data import AlpacaMarketDataGateway


class FakeQuote:
    bid_price = 599.90
    ask_price = 600.10
    timestamp = datetime(2026, 4, 17, 17, 0, tzinfo=UTC)


class FakeSnapshotQuote:
    bid_price = 599.90
    ask_price = 600.10
    timestamp = datetime(2026, 4, 17, 17, 0, 1, tzinfo=UTC)


class FakeTrade:
    price = 600.00
    timestamp = datetime(2026, 4, 17, 17, 0, tzinfo=UTC)


class FakeSnapshot:
    latest_trade = FakeTrade()
    latest_quote = FakeSnapshotQuote()


class FakeBar:
    volume = 1_500_000


class FakeDataClient:
    def __init__(self) -> None:
        self.last_request = None

    def get_stock_latest_quote(self, request):
        self.last_request = request
        return {"SPY": FakeQuote()}

    def get_stock_snapshot(self, request):
        self.last_request = request
        return {"SPY": FakeSnapshot()}

    def get_stock_bars(self, request):
        self.last_request = request
        return {"SPY": [FakeBar() for _ in range(30)]}


def test_latest_quote_uses_symbol_key_and_decimal_prices() -> None:
    client = FakeDataClient()
    gateway = AlpacaMarketDataGateway(client=client)

    quote = gateway.get_latest_quote("SPY")

    assert client.last_request.symbol_or_symbols == "SPY"
    assert quote.symbol == "SPY"
    assert quote.bid_price == Decimal("599.9")
    assert quote.ask_price == Decimal("600.1")


def test_market_snapshot_includes_last_trade_and_trailing_adv() -> None:
    client = FakeDataClient()
    gateway = AlpacaMarketDataGateway(client=client)

    snapshot = gateway.get_market_snapshot("SPY")

    assert snapshot.symbol == "SPY"
    assert snapshot.last_trade_price == Decimal("600.0")
    assert snapshot.bid_price == Decimal("599.9")
    assert snapshot.ask_price == Decimal("600.1")
    assert snapshot.average_daily_volume_30d == Decimal("1500000")
    assert snapshot.timestamp == datetime(2026, 4, 17, 17, 0, 1, tzinfo=UTC)
