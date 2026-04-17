from __future__ import annotations

from datetime import UTC
from decimal import Decimal

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

from tradingx.types import LatestQuote


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


class AlpacaMarketDataGateway:
    """Fetch latest stock quotes from Alpaca market data.

    source: https://alpaca.markets/sdks/python/market_data.html
        (retrieved 2026-04-17)
    source: https://docs.alpaca.markets/reference/stocklatestquotes-1
        (retrieved 2026-04-17)
    """

    def __init__(self, client: StockHistoricalDataClient) -> None:
        self._client = client

    @classmethod
    def from_credentials(
        cls,
        *,
        api_key: str,
        api_secret: str,
    ) -> AlpacaMarketDataGateway:
        return cls(
            StockHistoricalDataClient(
                api_key=api_key,
                secret_key=api_secret,
            )
        )

    def get_latest_quote(self, symbol: str) -> LatestQuote:
        request = StockLatestQuoteRequest(
            symbol_or_symbols=symbol,
            feed=DataFeed.IEX,
        )
        quotes = self._client.get_stock_latest_quote(request)
        quote = quotes[symbol]
        timestamp = quote.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        else:
            timestamp = timestamp.astimezone(UTC)

        return LatestQuote(
            symbol=symbol,
            bid_price=_to_decimal(quote.bid_price),
            ask_price=_to_decimal(quote.ask_price),
            timestamp=timestamp,
        )
