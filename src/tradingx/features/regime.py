"""Rule-based regime classifier."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tradingx.types import RegimeSnapshot

VIX_ELEVATED_THRESHOLD_DEFAULT = Decimal("25")
VIX_STRESS_THRESHOLD_DEFAULT = Decimal("35")


def classify_regime(
    *,
    observation_date: date,
    spy_close: Decimal,
    spy_sma_200: Decimal,
    vix_close: Decimal | None,
    yield_curve_spread_bps: Decimal | None,
    vix_elevated_threshold: Decimal = VIX_ELEVATED_THRESHOLD_DEFAULT,
    vix_stress_threshold: Decimal = VIX_STRESS_THRESHOLD_DEFAULT,
) -> RegimeSnapshot:
    above_sma_200: bool | None = spy_close > spy_sma_200
    vix_elevated: bool | None = (
        vix_close >= vix_elevated_threshold if vix_close is not None else None
    )
    vix_stressed: bool | None = (
        vix_close >= vix_stress_threshold if vix_close is not None else None
    )
    yield_curve_inverted: bool | None = (
        yield_curve_spread_bps < Decimal("0")
        if yield_curve_spread_bps is not None
        else None
    )

    if bool(vix_stressed) or (bool(yield_curve_inverted) and not bool(above_sma_200)):
        regime = "stressed"
    elif not bool(above_sma_200) or bool(vix_elevated):
        regime = "risk_off"
    elif bool(above_sma_200) and not bool(vix_elevated):
        regime = "risk_on"
    else:
        regime = "neutral"

    return RegimeSnapshot(
        observation_date=observation_date,
        regime=regime,
        above_sma_200=above_sma_200,
        vix_elevated=vix_elevated,
        vix_stressed=vix_stressed,
        yield_curve_inverted=yield_curve_inverted,
        spy_close=spy_close,
        spy_sma_200=spy_sma_200,
        vix_close=vix_close,
        yield_curve_spread_bps=yield_curve_spread_bps,
    )


__all__ = (
    "VIX_ELEVATED_THRESHOLD_DEFAULT",
    "VIX_STRESS_THRESHOLD_DEFAULT",
    "classify_regime",
)
