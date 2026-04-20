from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.data import AlpacaMarketDataGateway, AlpacaRegularHoursCalendar


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
    close = 600.25
    timestamp = datetime(2026, 4, 16, 20, 0, tzinfo=UTC)


class FakeHistoricalBar:
    def __init__(self, close: float, timestamp: datetime) -> None:
        self.close = close
        self.timestamp = timestamp


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


def test_daily_close_series_uses_adjusted_daily_bars() -> None:
    class HistoricalBarsClient(FakeDataClient):
        def get_stock_bars(self, request):
            self.last_request = request
            return {
                "SPY": [
                    FakeHistoricalBar(
                        close=598.25,
                        timestamp=datetime(2026, 4, 15, 20, 0, tzinfo=UTC),
                    ),
                    FakeHistoricalBar(
                        close=600.75,
                        timestamp=datetime(2026, 4, 16, 20, 0, tzinfo=UTC),
                    ),
                ]
            }

    client = HistoricalBarsClient()
    gateway = AlpacaMarketDataGateway(client=client)

    series = gateway.get_daily_close_series(
        "SPY",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        feed="iex",
        adjustment="dividend",
    )

    assert client.last_request.symbol_or_symbols == "SPY"
    assert str(client.last_request.feed) == "DataFeed.IEX"
    assert str(client.last_request.adjustment) == "Adjustment.DIVIDEND"
    assert series.symbol == "SPY"
    assert series.series_is_adjusted is True
    assert series.closes == (Decimal("598.25"), Decimal("600.75"))
    assert series.window_start_utc == datetime(2026, 4, 1, tzinfo=UTC)
    assert series.window_end_utc == datetime(2026, 4, 17, tzinfo=UTC)


def test_regular_hours_calendar_reports_open_session() -> None:
    calendar = AlpacaRegularHoursCalendar()

    assert calendar.is_open(datetime(2026, 4, 20, 14, 0, tzinfo=UTC)) is True


def test_regular_hours_calendar_reports_closed_session() -> None:
    calendar = AlpacaRegularHoursCalendar()

    assert calendar.is_open(datetime(2026, 4, 20, 20, 30, tzinfo=UTC)) is False


def test_regular_hours_calendar_returns_next_session_window_after_close() -> None:
    calendar = AlpacaRegularHoursCalendar()

    session = calendar.get_current_or_next_session(
        datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
    )

    assert session is not None
    assert session.trading_day == "2026-04-20"
    assert session.open_at_utc == datetime(2026, 4, 20, 13, 30, tzinfo=UTC)
    assert session.close_at_utc == datetime(2026, 4, 20, 20, 0, tzinfo=UTC)


def test_regular_hours_calendar_returns_session_dates_between_bounds() -> None:
    calendar = AlpacaRegularHoursCalendar()

    session_dates = calendar.session_dates_between(
        datetime(2026, 4, 20, 0, 0, tzinfo=UTC),
        datetime(2026, 4, 22, 23, 59, tzinfo=UTC),
    )

    assert session_dates == (
        datetime(2026, 4, 20, tzinfo=UTC).date(),
        datetime(2026, 4, 21, tzinfo=UTC).date(),
        datetime(2026, 4, 22, tzinfo=UTC).date(),
    )
