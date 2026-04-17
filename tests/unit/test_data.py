from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.data import AlpacaMarketDataGateway


class FakeQuote:
    bid_price = 599.90
    ask_price = 600.10
    timestamp = datetime(2026, 4, 17, 17, 0, tzinfo=UTC)


class FakeDataClient:
    def __init__(self) -> None:
        self.last_request = None

    def get_stock_latest_quote(self, request):
        self.last_request = request
        return {"SPY": FakeQuote()}


def test_latest_quote_uses_symbol_key_and_decimal_prices() -> None:
    client = FakeDataClient()
    gateway = AlpacaMarketDataGateway(client=client)

    quote = gateway.get_latest_quote("SPY")

    assert client.last_request.symbol_or_symbols == "SPY"
    assert quote.symbol == "SPY"
    assert quote.bid_price == Decimal("599.9")
    assert quote.ask_price == Decimal("600.1")
