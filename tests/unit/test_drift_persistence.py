from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import SleeveDailyAttributionRecord


def test_sleeve_daily_attribution_record_roundtrip(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    record = SleeveDailyAttributionRecord(
        attribution_id="attr-a",
        sleeve_id="trend-following-v1",
        trading_day="2026-04-21",
        recorded_at_utc=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
        starting_equity=Decimal("100000"),
        ending_equity=Decimal("100500"),
        daily_return=Decimal("0.005"),
        per_symbol_open_weight=(("SPY", Decimal("0.4")),),
        per_symbol_close_weight=(("SPY", Decimal("0.42")),),
    )

    path = store.write_sleeve_daily_attribution_record(record)

    assert path.exists()
    assert record in store.list_sleeve_daily_attribution_records(
        sleeve_id="trend-following-v1"
    )
