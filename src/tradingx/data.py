from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import exchange_calendars as xcals  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame

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

    def get_daily_bar_history(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
        feed: str | DataFeed = DataFeed.IEX,
        adjustment: str | Adjustment = Adjustment.DIVIDEND,
    ) -> pd.DataFrame:
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
        index = []
        rows: list[dict[str, float]] = []
        for bar in bars:
            timestamp = bar.timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            else:
                timestamp = timestamp.astimezone(UTC)
            index.append(timestamp)
            rows.append(
                {
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(bar.volume),
                }
            )
        return pd.DataFrame(rows, index=index, dtype=float).sort_index(kind="stable")


class AlpacaRegularHoursCalendar:
    def __init__(self, calendar_name: object = "XNYS") -> None:
        # Backward compatibility: older call sites passed an Alpaca TradingClient
        # into this boundary even though the exchange-calendar implementation
        # no longer needs it. Any non-string argument falls back to XNYS.
        resolved_calendar_name = (
            calendar_name if isinstance(calendar_name, str) else "XNYS"
        )
        self._calendar = xcals.get_calendar(resolved_calendar_name)

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
        calendars = self._calendar.sessions_in_range(
            observed_at_utc.date(),
            observed_at_utc.date() + timedelta(days=14),
        )
        if len(calendars) == 0:
            return None
        for session_label in calendars:
            session = self._calendar.schedule.loc[session_label]
            session_open = session["open"].to_pydatetime().astimezone(UTC)
            session_close = session["close"].to_pydatetime().astimezone(UTC)
            if session_close < observed_at_utc:
                continue
            return RegularSessionWindow(
                trading_day=session_label.date().isoformat(),
                open_at_utc=session_open,
                close_at_utc=session_close,
            )
        return None

    def session_dates_between(
        self,
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[date, ...]:
        if end_utc < start_utc:
            raise ValueError("end_utc must be on or after start_utc.")
        sessions = self._calendar.sessions_in_range(
            start_utc.date(),
            end_utc.date(),
        )
        return tuple(session_label.date() for session_label in sessions)


def build_market_data_gateway_for_mode(
    config: TradingConfig,
    *,
    broker_mode: str | None = None,
) -> AlpacaMarketDataGateway:
    requested_mode = (broker_mode or config.broker_mode).strip().lower() or "paper"
    if requested_mode == "live":
        if not config.has_real_live_credentials():
            raise RuntimeError(
                "Live market data requested while live mode is disabled: "
                "missing_live_credentials"
            )
        return AlpacaMarketDataGateway.from_credentials(
            api_key=config.live_credentials.api_key,
            api_secret=config.live_credentials.api_secret,
        )
    return AlpacaMarketDataGateway.from_credentials(
        api_key=config.paper_credentials.api_key,
        api_secret=config.paper_credentials.api_secret,
    )


def build_default_market_data_gateway(config: TradingConfig) -> AlpacaMarketDataGateway:
    return build_market_data_gateway_for_mode(config)


__all__ = (
    "AlpacaMarketDataGateway",
    "AlpacaRegularHoursCalendar",
    "RegularSessionWindow",
    "build_default_market_data_gateway",
    "build_market_data_gateway_for_mode",
    "close_to_close_returns",
)
