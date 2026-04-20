from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


class RiskFreeSeriesProtocol(Protocol):
    def get_daily_rate(self, session_date: date) -> Decimal: ...


@dataclass(frozen=True)
class CashHurdle:
    risk_free_series: RiskFreeSeriesProtocol

    def daily_returns(self, *, session_dates: Sequence[date]) -> tuple[Decimal, ...]:
        if not session_dates:
            raise ValueError("session_dates must be non-empty.")
        return tuple(
            self.risk_free_series.get_daily_rate(session_date)
            for session_date in session_dates
        )


__all__ = ("CashHurdle", "RiskFreeSeriesProtocol")
