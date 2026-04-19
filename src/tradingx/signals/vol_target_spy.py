"""Volatility-managed long-only SPY exposure.

Source:
- Moreira, A., and T. Muir, "Volatility-Managed Portfolios",
  Journal of Finance 72(4), 2017.
"""

from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from tradingx.features.volatility import realized_vol, volatility_scale
from tradingx.signals.trend import REQUIRED_OHLCV_COLUMNS

TARGET_VOLATILITY = 0.12
REALIZED_VOL_WINDOW_DAYS = 60
MAX_GROSS_LEVERAGE = 1.0
PRE_SIZED = True


def generate_vol_target_spy_signal(
    ohlcv: pd.DataFrame,
    *,
    target_volatility: float = TARGET_VOLATILITY,
    realized_vol_window_days: int = REALIZED_VOL_WINDOW_DAYS,
    max_gross_leverage: float = MAX_GROSS_LEVERAGE,
) -> pd.Series:
    _validate_ohlcv(ohlcv)

    close_returns = ohlcv["close"].astype(float).pct_change()
    leverage = volatility_scale(
        target_vol=target_volatility,
        realized_vol=realized_vol(
            close_returns,
            lookback_days=realized_vol_window_days,
        ),
        max_gross_leverage=max_gross_leverage,
    )
    return leverage.clip(lower=0.0, upper=max_gross_leverage)


def _validate_ohlcv(ohlcv: pd.DataFrame) -> None:
    missing = tuple(column for column in REQUIRED_OHLCV_COLUMNS if column not in ohlcv)
    if missing:
        missing_columns = ", ".join(missing)
        raise ValueError(f"OHLCV frame is missing required columns: {missing_columns}.")


__all__ = (
    "MAX_GROSS_LEVERAGE",
    "PRE_SIZED",
    "REALIZED_VOL_WINDOW_DAYS",
    "TARGET_VOLATILITY",
    "generate_vol_target_spy_signal",
)
