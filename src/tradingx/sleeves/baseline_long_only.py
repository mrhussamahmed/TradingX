"""Baseline long-only sleeve for blueprint runtime."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradingx.sleeves.trend import _derive_side
from tradingx.strategy import DEFAULT_CANDIDATE_ID
from tradingx.types import SleeveContext, SleeveTrade


@dataclass(frozen=True)
class BaselineLongOnlySleeve:
    sleeve_id: str = DEFAULT_CANDIDATE_ID
    family: str = "baseline_long_only"
    benchmark_symbol: str = "SPY"
    target_weight: Decimal = Decimal("1")
    allowed_instruments: tuple[str, ...] = ("SPY",)

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        if not self.allowed_instruments:
            return ()
        symbol = self.benchmark_symbol
        if symbol not in self.allowed_instruments:
            symbol = self.allowed_instruments[0]
        current_weight = context.current_weights_by_symbol.get(symbol, Decimal("0"))
        target_weight = min(max(self.target_weight, Decimal("0")), Decimal("1"))
        return (
            SleeveTrade(
                sleeve_id=self.sleeve_id,
                symbol=symbol,
                side=_derive_side(current_weight, target_weight),
                target_weight_of_sleeve_budget=target_weight,
                rationale="baseline_long_only_target",
                regime=context.regime.regime,
            ),
        )


__all__ = ("BaselineLongOnlySleeve",)
