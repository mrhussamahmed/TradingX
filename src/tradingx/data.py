from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame

from tradingx.types import LatestQuote, MarketSnapshot


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

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        snapshot_request = StockSnapshotRequest(
            symbol_or_symbols=symbol,
            feed=DataFeed.IEX,
        )
        snapshots = self._client.get_stock_snapshot(snapshot_request)
        snapshot = snapshots[symbol]
        if snapshot.latest_trade is None or snapshot.latest_quote is None:
            raise ValueError(f"Market snapshot for {symbol} is incomplete.")

        bars_request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=datetime.now(UTC) - timedelta(days=60),
            limit=30,
            feed=DataFeed.IEX,
        )
        bars = self._client.get_stock_bars(bars_request)[symbol]
        if len(bars) < 30:
            raise ValueError(
                f"Need 30 daily bars to compute ADV for {symbol}; received {len(bars)}."
            )

        quote_timestamp = snapshot.latest_quote.timestamp
        if quote_timestamp.tzinfo is None:
            quote_timestamp = quote_timestamp.replace(tzinfo=UTC)
        else:
            quote_timestamp = quote_timestamp.astimezone(UTC)

        trade_timestamp = snapshot.latest_trade.timestamp
        if trade_timestamp.tzinfo is None:
            trade_timestamp = trade_timestamp.replace(tzinfo=UTC)
        else:
            trade_timestamp = trade_timestamp.astimezone(UTC)

        recent_bars = bars[-30:]
        average_daily_volume = sum(
            _to_decimal(bar.volume) for bar in recent_bars
        ) / Decimal(str(len(recent_bars)))

        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=_to_decimal(snapshot.latest_trade.price),
            bid_price=_to_decimal(snapshot.latest_quote.bid_price),
            ask_price=_to_decimal(snapshot.latest_quote.ask_price),
            average_daily_volume_30d=average_daily_volume,
            timestamp=max(trade_timestamp, quote_timestamp),
        )
