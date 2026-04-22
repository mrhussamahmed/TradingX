"""Live daily returns source for sleeve runtime gating."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from tradingx.types import SleeveDailyAttributionRecord


class AttributionRecordsReaderProtocol(Protocol):
    def records_for_sleeve(
        self,
        sleeve_id: str,
        *,
        window_days: int,
    ) -> tuple[SleeveDailyAttributionRecord, ...]: ...

    def has_gap_for_sleeve(self, sleeve_id: str, *, window_days: int) -> bool: ...


class SleeveDailyReturnsReader:
    def __init__(
        self,
        *,
        attribution_records_reader: AttributionRecordsReaderProtocol,
    ) -> None:
        self._reader = attribution_records_reader

    def live_daily_returns(
        self,
        *,
        sleeve_id: str,
        window_days: int,
    ) -> tuple[Decimal, ...]:
        has_gap_for_sleeve = getattr(
            self._reader,
            "has_gap_for_sleeve",
            lambda sleeve_id, *, window_days: False,
        )
        if has_gap_for_sleeve(sleeve_id, window_days=window_days):
            return ()
        records = self._reader.records_for_sleeve(sleeve_id, window_days=window_days)
        if not records:
            return ()
        ordered = sorted(records, key=lambda record: record.trading_day)
        return tuple(record.daily_return for record in ordered)


__all__ = ("AttributionRecordsReaderProtocol", "SleeveDailyReturnsReader")
