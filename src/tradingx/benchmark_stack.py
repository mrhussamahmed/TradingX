from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from tradingx.types import BenchmarkStackPayload, OperatingConstraintBudget


class RiskFreeSeriesProtocol(Protocol):
    def get_daily_rate(self, session_date: date) -> Decimal: ...


class ClosesProviderProtocol(Protocol):
    def get_closes(
        self,
        symbol: str,
        *,
        session_dates: Sequence[date],
    ) -> tuple[Decimal, ...]: ...


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


@dataclass(frozen=True)
class PassiveOpportunityCost:
    closes_provider: ClosesProviderProtocol
    weights: tuple[tuple[str, Decimal], ...]

    def __post_init__(self) -> None:
        if sum(weight for _, weight in self.weights) != Decimal("1"):
            raise ValueError("weights must sum to 1.")

    def daily_returns(self, *, session_dates: Sequence[date]) -> tuple[Decimal, ...]:
        if len(session_dates) < 2:
            raise ValueError("session_dates must contain at least two dates.")

        closes_by_symbol = {
            symbol: self.closes_provider.get_closes(symbol, session_dates=session_dates)
            for symbol, _ in self.weights
        }
        current_weights = {symbol: weight for symbol, weight in self.weights}
        blended_returns: list[Decimal] = []

        for index in range(1, len(session_dates)):
            previous_date = session_dates[index - 1]
            current_date = session_dates[index]
            if current_date.month != previous_date.month:
                current_weights = {symbol: weight for symbol, weight in self.weights}

            day_return = Decimal("0")
            next_weights: dict[str, Decimal] = {}
            total_weight = Decimal("0")
            for symbol, weight in current_weights.items():
                closes = closes_by_symbol[symbol]
                previous_close = closes[index - 1]
                current_close = closes[index]
                if previous_close == Decimal("0"):
                    raise ValueError(f"previous close for {symbol} must be non-zero.")
                symbol_return = (current_close / previous_close) - Decimal("1")
                day_return += weight * symbol_return
                drifted_weight = weight * (Decimal("1") + symbol_return)
                next_weights[symbol] = drifted_weight
                total_weight += drifted_weight

            if total_weight > Decimal("0"):
                current_weights = {
                    symbol: weight / total_weight
                    for symbol, weight in next_weights.items()
                }
            blended_returns.append(day_return)

        return tuple(blended_returns)


@dataclass(frozen=True)
class BenchmarkStack:
    hurdle: CashHurdle
    opportunity_cost: PassiveOpportunityCost
    operating_constraint: OperatingConstraintBudget

    def materialize(self, *, session_dates: Sequence[date]) -> BenchmarkStackPayload:
        return BenchmarkStackPayload(
            hurdle_returns=self.hurdle.daily_returns(session_dates=session_dates),
            opportunity_cost_returns=self.opportunity_cost.daily_returns(
                session_dates=session_dates
            ),
            opportunity_cost_weights=self.opportunity_cost.weights,
            operating_constraint=self.operating_constraint,
        )


__all__ = (
    "BenchmarkStack",
    "CashHurdle",
    "ClosesProviderProtocol",
    "PassiveOpportunityCost",
    "RiskFreeSeriesProtocol",
)
