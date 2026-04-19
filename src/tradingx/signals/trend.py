"""Long-only time-series momentum using the canonical 12-1 formulation.

Source:
- Moskowitz, T. J., Y. H. Ooi, and L. H. Pedersen, "Time Series
  Momentum", Journal of Financial Economics 104(2), 2012.
"""

from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
LOOKBACK_DAYS = 252
SMA_WINDOW = 200
PRE_SIZED = False


def generate_trend_signal(
    ohlcv: pd.DataFrame,
    *,
    lookback_days: int = LOOKBACK_DAYS,
    sma_window_days: int = SMA_WINDOW,
    skip_recent_days: int = 1,
) -> pd.Series:
    _validate_ohlcv(ohlcv)

    closes = ohlcv["close"].astype(float)
    prior_close = closes.shift(skip_recent_days)
    prior_lookback_close = closes.shift(lookback_days)
    prior_sma = closes.shift(skip_recent_days).rolling(sma_window_days).mean()

    signal = pd.Series(0.0, index=ohlcv.index, dtype=float)
    long_mask = (prior_close / prior_lookback_close > 1.0) & (prior_close > prior_sma)
    signal.loc[long_mask.fillna(False)] = 1.0
    return signal


def _validate_ohlcv(ohlcv: pd.DataFrame) -> None:
    missing = tuple(column for column in REQUIRED_OHLCV_COLUMNS if column not in ohlcv)
    if missing:
        missing_columns = ", ".join(missing)
        raise ValueError(f"OHLCV frame is missing required columns: {missing_columns}.")


__all__ = (
    "LOOKBACK_DAYS",
    "PRE_SIZED",
    "REQUIRED_OHLCV_COLUMNS",
    "SMA_WINDOW",
    "generate_trend_signal",
)
