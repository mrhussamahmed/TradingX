from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from tradingx.config import TradingConfig
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


class MarketDataGatewayProtocol(Protocol):
    def get_daily_close_series(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
        feed: str,
        adjustment: str,
    ): ...


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


@dataclass(frozen=True)
class _MarketDataClosesAdapter:
    market_data_gateway: MarketDataGatewayProtocol

    def get_closes(
        self,
        symbol: str,
        *,
        session_dates: Sequence[date],
    ) -> tuple[Decimal, ...]:
        if not session_dates:
            raise ValueError("session_dates must be non-empty.")
        series = self.market_data_gateway.get_daily_close_series(
            symbol,
            start_utc=datetime.combine(session_dates[0], datetime.min.time(), UTC),
            end_utc=datetime.combine(session_dates[-1], datetime.min.time(), UTC)
            + timedelta(days=1),
            feed="iex",
            adjustment="dividend",
        )
        return series.closes


def build_default_benchmark_stack(
    config: TradingConfig,
    *,
    market_data_gateway: MarketDataGatewayProtocol,
    risk_free_series: RiskFreeSeriesProtocol,
) -> BenchmarkStack:
    del config
    return BenchmarkStack(
        hurdle=CashHurdle(risk_free_series=risk_free_series),
        opportunity_cost=PassiveOpportunityCost(
            closes_provider=_MarketDataClosesAdapter(market_data_gateway),
            weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
        ),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal("0.15"),
            max_drawdown_halt=Decimal("0.25"),
            cdar_threshold=Decimal("0.08"),
            cdar_confidence=Decimal("0.95"),
        ),
    )


__all__ = (
    "BenchmarkStack",
    "CashHurdle",
    "ClosesProviderProtocol",
    "PassiveOpportunityCost",
    "RiskFreeSeriesProtocol",
    "build_default_benchmark_stack",
)
