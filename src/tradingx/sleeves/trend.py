"""Trend sleeve with vol-targeted sizing and regime gating."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.features.volatility import forecast_volatility
from tradingx.signals.trend import generate_trend_signal
from tradingx.sleeves.regime_gate import apply_regime_exposure_floor
from tradingx.strategy import CANONICAL_STAGE1_UNIVERSE
from tradingx.types import SleeveContext, SleeveFailureReason, SleeveTrade


@dataclass(frozen=True)
class TrendSleeve:
    sleeve_id: str = "trend-following-v1"
    family: str = "trend_following"
    target_sleeve_vol: Decimal = Decimal("0.12")
    lookback_days: int = 252
    sma_window_days: int = 200
    skip_recent_days: int = 1
    vol_forecast_lookback: int = 20
    forecast_method: str = "ewma"
    allowed_instruments: tuple[str, ...] = CANONICAL_STAGE1_UNIVERSE

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        trades: list[SleeveTrade] = []
        for symbol in self.allowed_instruments:
            bars = context.bars_by_symbol.get(symbol)
            current_weight = context.current_weights_by_symbol.get(symbol, Decimal("0"))
            if bars is None or len(bars) < self.lookback_days:
                trades.append(
                    SleeveTrade(
                        sleeve_id=self.sleeve_id,
                        symbol=symbol,
                        side="hold",
                        target_weight_of_sleeve_budget=current_weight,
                        rationale=SleeveFailureReason.INSUFFICIENT_HISTORY,
                        regime=context.regime.regime,
                    )
                )
                continue

            signal_series = generate_trend_signal(
                bars,
                lookback_days=self.lookback_days,
                sma_window_days=self.sma_window_days,
                skip_recent_days=self.skip_recent_days,
            )
            signal_value = float(signal_series.iloc[-1])

            returns = bars["close"].astype(float).pct_change()
            vol_forecast_series = forecast_volatility(
                returns,
                lookback_days=self.vol_forecast_lookback,
                forecast_method=self.forecast_method,
            )
            vol_forecast = float(vol_forecast_series.iloc[-1])
            if pd.isna(vol_forecast) or vol_forecast <= 0.0:
                trades.append(
                    SleeveTrade(
                        sleeve_id=self.sleeve_id,
                        symbol=symbol,
                        side="hold",
                        target_weight_of_sleeve_budget=current_weight,
                        rationale=SleeveFailureReason.INSUFFICIENT_HISTORY,
                        regime=context.regime.regime,
                    )
                )
                continue

            raw_weight = Decimal("0")
            if signal_value > 0.0:
                leverage = float(self.target_sleeve_vol) / vol_forecast
                raw_weight = Decimal(str(min(leverage, 1.0)))

            adjusted_weight, regime_rationale = apply_regime_exposure_floor(
                sleeve_id=self.sleeve_id,
                proposed_target_weight=raw_weight,
                current_position_weight=current_weight,
                regime=context.regime,
                sleeve_family=self.family,
            )
            trades.append(
                SleeveTrade(
                    sleeve_id=self.sleeve_id,
                    symbol=symbol,
                    side=_derive_side(current_weight, adjusted_weight),
                    target_weight_of_sleeve_budget=adjusted_weight,
                    rationale=regime_rationale
                    or _signal_rationale(signal_value, adjusted_weight),
                    regime=context.regime.regime,
                )
            )
        return tuple(trades)


def _derive_side(current: Decimal, target: Decimal) -> str:
    if target > current:
        return "buy"
    if target < current and target == Decimal("0"):
        return "sell"
    if target < current:
        return "reduce"
    return "hold"


def _signal_rationale(signal_value: float, adjusted_weight: Decimal) -> str:
    if signal_value > 0.0 and adjusted_weight > Decimal("0"):
        return "tsmom_long_vol_targeted"
    if signal_value <= 0.0:
        return "tsmom_no_signal"
    return "tsmom_long_regime_suppressed"


__all__ = ("TrendSleeve",)
