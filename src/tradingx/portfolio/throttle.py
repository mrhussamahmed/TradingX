"""Drawdown throttle helpers."""

from __future__ import annotations

from decimal import Decimal
from typing import Final

import pandas as pd  # type: ignore[import-untyped]

from tradingx.portfolio.blueprint import PortfolioBlueprint

MDD_DESIGN_THROTTLE_FLOOR: Final[Decimal] = Decimal("0.0")
CDAR_SOFT_THROTTLE_FLOOR: Final[Decimal] = Decimal("0.5")


def apply_mdd_design_throttle(
    *,
    target_weights: pd.DataFrame,
    trailing_drawdown_series: pd.Series,
    blueprint: PortfolioBlueprint,
) -> tuple[pd.DataFrame, pd.Series]:
    if not target_weights.index.equals(trailing_drawdown_series.index):
        raise ValueError("trailing_drawdown_series must share target_weights index")

    design_target = float(blueprint.mdd_design_target)
    hard_halt = float(blueprint.mdd_hard_halt)
    if hard_halt <= design_target:
        raise ValueError(
            "PortfolioBlueprint.mdd_hard_halt must exceed mdd_design_target"
        )
    drawdown = trailing_drawdown_series.astype(float).clip(lower=0.0)
    scale = ((hard_halt - drawdown) / (hard_halt - design_target)).clip(
        lower=float(MDD_DESIGN_THROTTLE_FLOOR),
        upper=1.0,
    )
    scale = scale.where(drawdown > design_target, 1.0)
    throttled = target_weights.multiply(scale, axis=0)
    return throttled, scale


def apply_cdar_soft_throttle(
    *,
    target_weights: pd.DataFrame,
    trailing_cdar_series: pd.Series,
    blueprint: PortfolioBlueprint,
) -> tuple[pd.DataFrame, pd.Series]:
    if not target_weights.index.equals(trailing_cdar_series.index):
        raise ValueError("trailing_cdar_series must share target_weights index")

    threshold = float(blueprint.cdar_soft_throttle_threshold)
    if threshold <= 0.0:
        raise ValueError("PortfolioBlueprint.cdar_soft_throttle_threshold must be > 0")
    cdar = trailing_cdar_series.astype(float).clip(lower=0.0)
    linear = 1.0 - 0.5 * ((cdar - threshold) / threshold)
    scale = linear.clip(lower=float(CDAR_SOFT_THROTTLE_FLOOR), upper=1.0)
    scale = scale.where(cdar > threshold, 1.0)
    throttled = target_weights.multiply(scale, axis=0)
    return throttled, scale


__all__ = (
    "CDAR_SOFT_THROTTLE_FLOOR",
    "MDD_DESIGN_THROTTLE_FLOOR",
    "apply_cdar_soft_throttle",
    "apply_mdd_design_throttle",
)
