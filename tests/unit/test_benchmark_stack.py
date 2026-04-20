from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tradingx.benchmark_stack import CashHurdle


class _FakeRiskFreeSeries:
    def __init__(self, daily_rates: dict[date, Decimal]) -> None:
        self._daily_rates = daily_rates

    def get_daily_rate(self, session_date: date) -> Decimal:
        return self._daily_rates[session_date]


def test_cash_hurdle_daily_returns_uses_cached_daily_rates() -> None:
    daily_rates = {
        date(2026, 1, 5): Decimal("0.0002"),
        date(2026, 1, 6): Decimal("0.0002"),
        date(2026, 1, 7): Decimal("0.0002"),
    }
    hurdle = CashHurdle(risk_free_series=_FakeRiskFreeSeries(daily_rates))

    returns = hurdle.daily_returns(
        session_dates=(
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
        )
    )

    assert returns == (
        Decimal("0.0002"),
        Decimal("0.0002"),
        Decimal("0.0002"),
    )


def test_cash_hurdle_rejects_empty_session_dates() -> None:
    hurdle = CashHurdle(risk_free_series=_FakeRiskFreeSeries({}))

    with pytest.raises(ValueError):
        hurdle.daily_returns(session_dates=())
