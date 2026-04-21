"""Shared regime-to-exposure gate for sleeves."""

from __future__ import annotations

from decimal import Decimal

from tradingx.types import RegimeSnapshot


def apply_regime_exposure_floor(
    *,
    sleeve_id: str,
    proposed_target_weight: Decimal,
    current_position_weight: Decimal,
    regime: RegimeSnapshot,
    sleeve_family: str,
) -> tuple[Decimal, str]:
    del sleeve_id

    if regime.regime == "stressed":
        return Decimal("0"), "regime_stressed_liquidate"

    if regime.regime == "risk_off" and sleeve_family == "trend_following":
        if current_position_weight == Decimal("0") and proposed_target_weight > Decimal(
            "0"
        ):
            return Decimal("0"), "regime_risk_off_suppress_entry"

    return proposed_target_weight, ""


__all__ = ("apply_regime_exposure_floor",)
