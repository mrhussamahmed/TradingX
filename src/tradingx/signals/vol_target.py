"""Volatility targeting for daily-bar portfolio signals.

The module scales an upstream signal to a target 20-day realized
volatility of 12% annualized while capping gross leverage at 1.0.
"""

from __future__ import annotations

import math

import pandas as pd  # type: ignore[import-untyped]

REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
TARGET_VOLATILITY = 0.12
REALIZED_VOL_WINDOW_DAYS = 20
MAX_GROSS_LEVERAGE = 1.0
TRADING_DAYS_PER_YEAR = 252


def generate_vol_target_signal(
    ohlcv: pd.DataFrame,
    *,
    upstream_signal: pd.Series,
    target_volatility: float = TARGET_VOLATILITY,
    realized_vol_window_days: int = REALIZED_VOL_WINDOW_DAYS,
    max_gross_leverage: float = MAX_GROSS_LEVERAGE,
) -> pd.Series:
    _validate_ohlcv(ohlcv)
    if not upstream_signal.index.equals(ohlcv.index):
        raise ValueError("upstream_signal must share the OHLCV index.")

    close_returns = ohlcv["close"].astype(float).pct_change()
    realized_volatility = close_returns.shift(1).rolling(realized_vol_window_days).std(
        ddof=1
    ) * math.sqrt(TRADING_DAYS_PER_YEAR)

    leverage = pd.Series(0.0, index=ohlcv.index, dtype=float)
    valid = realized_volatility > 0.0
    leverage.loc[valid.fillna(False)] = (
        target_volatility / realized_volatility.loc[valid.fillna(False)]
    ).clip(upper=max_gross_leverage)
    scaled_signal = (
        upstream_signal.astype(float).clip(
            lower=-max_gross_leverage,
            upper=max_gross_leverage,
        )
        * leverage
    )
    return scaled_signal.clip(
        lower=-max_gross_leverage,
        upper=max_gross_leverage,
    )


def _validate_ohlcv(ohlcv: pd.DataFrame) -> None:
    missing = tuple(column for column in REQUIRED_OHLCV_COLUMNS if column not in ohlcv)
    if missing:
        missing_columns = ", ".join(missing)
        raise ValueError(f"OHLCV frame is missing required columns: {missing_columns}.")


__all__ = (
    "MAX_GROSS_LEVERAGE",
    "REALIZED_VOL_WINDOW_DAYS",
    "REQUIRED_OHLCV_COLUMNS",
    "TARGET_VOLATILITY",
    "TRADING_DAYS_PER_YEAR",
    "generate_vol_target_signal",
)
