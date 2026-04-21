from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingx.drift.live_returns_source import SleeveDailyReturnsReader
from tradingx.types import SleeveDailyAttributionRecord


def _record(
    sleeve_id: str,
    daily_return: str,
    days_ago: int,
) -> SleeveDailyAttributionRecord:
    recorded = datetime.now(UTC) - timedelta(days=days_ago)
    return SleeveDailyAttributionRecord(
        attribution_id=f"attr-{sleeve_id}-{days_ago}",
        sleeve_id=sleeve_id,
        trading_day=recorded.date().isoformat(),
        recorded_at_utc=recorded,
        starting_equity=Decimal("100000"),
        ending_equity=Decimal("100000"),
        daily_return=Decimal(daily_return),
        per_symbol_open_weight=(),
        per_symbol_close_weight=(),
    )


class _FakeReader:
    def __init__(self, records) -> None:
        self._records = records

    def records_for_sleeve(self, sleeve_id, *, window_days):
        del window_days
        return tuple(
            record for record in self._records if record.sleeve_id == sleeve_id
        )


def test_reader_returns_daily_returns_in_trading_day_order() -> None:
    reader = SleeveDailyReturnsReader(
        attribution_records_reader=_FakeReader(
            (
                _record("trend-following-v1", "0.01", 3),
                _record("trend-following-v1", "0.02", 2),
                _record("trend-following-v1", "0.03", 1),
                _record("other", "0.99", 1),
            )
        )
    )

    assert reader.live_daily_returns(
        sleeve_id="trend-following-v1",
        window_days=60,
    ) == (Decimal("0.01"), Decimal("0.02"), Decimal("0.03"))


def test_reader_returns_empty_when_no_records() -> None:
    reader = SleeveDailyReturnsReader(
        attribution_records_reader=_FakeReader(records=())
    )
    assert reader.live_daily_returns(sleeve_id="x", window_days=60) == ()
