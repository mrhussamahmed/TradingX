from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest

from tradingx.config import TradingConfig
from tradingx.types import BenchmarkCloseSeries, LatestQuote, MarketSnapshot


@dataclass(frozen=True)
class RegularSessionWindow:
    trading_day: str
    open_at_utc: datetime
    close_at_utc: datetime


def _to_decimal(value: object) -> Decimal:
    return Decimal(str(value))


def close_to_close_returns(closes: Sequence[Decimal]) -> tuple[Decimal, ...]:
    if len(closes) < 2:
        return ()
    returns: list[Decimal] = []
    for previous_close, current_close in zip(
        closes[:-1],
        closes[1:],
        strict=False,
    ):
        if previous_close == Decimal("0"):
            returns.append(Decimal("0"))
            continue
        returns.append((current_close - previous_close) / previous_close)
    return tuple(returns)


def _normalize_feed(feed: str | DataFeed) -> DataFeed:
    return feed if isinstance(feed, DataFeed) else DataFeed(feed.lower())


def _normalize_adjustment(adjustment: str | Adjustment) -> Adjustment:
    return (
        adjustment
        if isinstance(adjustment, Adjustment)
        else Adjustment(adjustment.lower())
    )


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

    def get_daily_close_series(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
        feed: str | DataFeed = DataFeed.IEX,
        adjustment: str | Adjustment = Adjustment.DIVIDEND,
    ) -> BenchmarkCloseSeries:
        normalized_symbol = symbol.upper()
        normalized_feed = _normalize_feed(feed)
        normalized_adjustment = _normalize_adjustment(adjustment)
        bars_request = StockBarsRequest(
            symbol_or_symbols=normalized_symbol,
            timeframe=TimeFrame.Day,
            start=start_utc,
            end=end_utc,
            feed=normalized_feed,
            adjustment=normalized_adjustment,
        )
        bars_response = self._client.get_stock_bars(bars_request)
        if isinstance(bars_response, dict):
            bars = bars_response.get(normalized_symbol, [])
        else:
            bars = bars_response[normalized_symbol]
        if not bars:
            raise ValueError(
                f"No daily bars returned for {normalized_symbol} between "
                f"{start_utc.isoformat()} and {end_utc.isoformat()}."
            )
        return BenchmarkCloseSeries(
            symbol=normalized_symbol,
            closes=tuple(_to_decimal(bar.close) for bar in bars),
            window_start_utc=start_utc,
            window_end_utc=end_utc,
            generated_at_utc=datetime.now(UTC),
            feed=normalized_feed.value,
            adjustment=normalized_adjustment.value,
            series_is_adjusted=normalized_adjustment
            in {Adjustment.DIVIDEND, Adjustment.ALL},
        )


class AlpacaRegularHoursCalendar:
    def __init__(self, trading_client: TradingClient) -> None:
        self._trading_client = trading_client

    def is_open(self, observed_at_utc: datetime) -> bool:
        session_window = self.get_current_or_next_session(observed_at_utc)
        if session_window is None:
            return False
        return (
            session_window.open_at_utc <= observed_at_utc <= session_window.close_at_utc
        )

    def get_current_or_next_session(
        self,
        observed_at_utc: datetime,
    ) -> RegularSessionWindow | None:
        eastern = ZoneInfo("America/New_York")
        observed_at_eastern = observed_at_utc.astimezone(eastern)
        calendars = self._trading_client.get_calendar(
            GetCalendarRequest(
                start=observed_at_eastern.date(),
                end=(observed_at_eastern.date() + timedelta(days=14)),
            )
        )
        if isinstance(calendars, dict) or not calendars:
            return None
        for calendar_entry in calendars:
            session_open = calendar_entry.open
            session_close = calendar_entry.close
            if session_open.tzinfo is None:
                session_open = session_open.replace(tzinfo=eastern)
            else:
                session_open = session_open.astimezone(eastern)
            if session_close.tzinfo is None:
                session_close = session_close.replace(tzinfo=eastern)
            else:
                session_close = session_close.astimezone(eastern)
            if session_close < observed_at_eastern:
                continue
            return RegularSessionWindow(
                trading_day=session_open.date().isoformat(),
                open_at_utc=session_open.astimezone(UTC),
                close_at_utc=session_close.astimezone(UTC),
            )
        return None


def build_default_market_data_gateway(config: TradingConfig) -> AlpacaMarketDataGateway:
    return AlpacaMarketDataGateway.from_credentials(
        api_key=config.paper_credentials.api_key,
        api_secret=config.paper_credentials.api_secret,
    )
