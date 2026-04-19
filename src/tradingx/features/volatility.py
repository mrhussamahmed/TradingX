"""Volatility feature primitives shared by research signals.

These helpers are pure math utilities with no strategy semantics.
"""

from __future__ import annotations

import math

import pandas as pd  # type: ignore[import-untyped]

TRADING_DAYS_PER_YEAR = 252


def realized_vol(
    returns: pd.Series,
    *,
    lookback_days: int,
) -> pd.Series:
    return returns.astype(float).shift(1).rolling(lookback_days).std(
        ddof=1
    ) * math.sqrt(TRADING_DAYS_PER_YEAR)


def volatility_scale(
    *,
    target_vol: float,
    realized_vol: pd.Series,
    max_gross_leverage: float,
) -> pd.Series:
    scale = pd.Series(0.0, index=realized_vol.index, dtype=float)
    valid = realized_vol > 0.0
    scale.loc[valid.fillna(False)] = (
        target_vol / realized_vol.loc[valid.fillna(False)]
    ).clip(upper=max_gross_leverage)
    return scale.clip(lower=0.0, upper=max_gross_leverage)


__all__ = (
    "TRADING_DAYS_PER_YEAR",
    "realized_vol",
    "volatility_scale",
)
