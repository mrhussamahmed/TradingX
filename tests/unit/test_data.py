from __future__ import annotations

from datetime import UTC, date, datetime
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


class FakeCalendarEntry:
    def __init__(self, open_at: datetime, close_at: datetime) -> None:
        self.date = date(2026, 4, 17)
        self.open = open_at
        self.close = close_at


class FakeCalendarClient:
    def __init__(self, calendars) -> None:
        self._calendars = calendars

    def get_calendar(self, filters):
        return self._calendars


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


def test_regular_hours_calendar_reports_open_session() -> None:
    calendar = AlpacaRegularHoursCalendar(
        FakeCalendarClient(
            [
                FakeCalendarEntry(
                    open_at=datetime(2026, 4, 17, 9, 30),
                    close_at=datetime(2026, 4, 17, 16, 0),
                )
            ]
        )
    )

    assert calendar.is_open(datetime(2026, 4, 17, 15, 0, tzinfo=UTC)) is True


def test_regular_hours_calendar_reports_closed_session() -> None:
    calendar = AlpacaRegularHoursCalendar(
        FakeCalendarClient(
            [
                FakeCalendarEntry(
                    open_at=datetime(2026, 4, 17, 9, 30),
                    close_at=datetime(2026, 4, 17, 16, 0),
                )
            ]
        )
    )

    assert calendar.is_open(datetime(2026, 4, 17, 20, 30, tzinfo=UTC)) is False
