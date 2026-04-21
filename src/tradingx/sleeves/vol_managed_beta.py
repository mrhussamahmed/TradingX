"""Vol-managed beta sleeve for SPY."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.signals.vol_target_spy import generate_vol_target_spy_signal
from tradingx.sleeves.regime_gate import apply_regime_exposure_floor
from tradingx.sleeves.trend import _derive_side
from tradingx.types import SleeveContext, SleeveFailureReason, SleeveTrade


@dataclass(frozen=True)
class VolManagedBetaSleeve:
    sleeve_id: str = "vol-target-v1"
    family: str = "vol_target"
    target_volatility: float = 0.12
    realized_vol_window_days: int = 60
    max_gross_leverage: float = 1.0
    forecast_method: str = "garch"
    allowed_instruments: tuple[str, ...] = ("SPY",)

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        current_weight = context.current_weights_by_symbol.get("SPY", Decimal("0"))
        spy_bars = context.bars_by_symbol.get("SPY")
        min_required = self.realized_vol_window_days + 20
        if spy_bars is None or len(spy_bars) < min_required:
            return (
                SleeveTrade(
                    sleeve_id=self.sleeve_id,
                    symbol="SPY",
                    side="hold",
                    target_weight_of_sleeve_budget=current_weight,
                    rationale=SleeveFailureReason.INSUFFICIENT_HISTORY,
                    regime=context.regime.regime,
                ),
            )

        signal_series = generate_vol_target_spy_signal(
            spy_bars,
            target_volatility=float(self.target_volatility),
            realized_vol_window_days=self.realized_vol_window_days,
            max_gross_leverage=float(self.max_gross_leverage),
            forecast_method=self.forecast_method,
        )
        signal_value = signal_series.iloc[-1]
        if pd.isna(signal_value):
            return (
                SleeveTrade(
                    sleeve_id=self.sleeve_id,
                    symbol="SPY",
                    side="hold",
                    target_weight_of_sleeve_budget=current_weight,
                    rationale=SleeveFailureReason.INSUFFICIENT_HISTORY,
                    regime=context.regime.regime,
                ),
            )

        raw_weight = Decimal(str(float(signal_value)))
        adjusted_weight, regime_rationale = apply_regime_exposure_floor(
            sleeve_id=self.sleeve_id,
            proposed_target_weight=raw_weight,
            current_position_weight=current_weight,
            regime=context.regime,
            sleeve_family=self.family,
        )
        return (
            SleeveTrade(
                sleeve_id=self.sleeve_id,
                symbol="SPY",
                side=_derive_side(current_weight, adjusted_weight),
                target_weight_of_sleeve_budget=adjusted_weight,
                rationale=regime_rationale or "moreira_muir_vol_managed",
                regime=context.regime.regime,
            ),
        )


__all__ = ("VolManagedBetaSleeve",)
