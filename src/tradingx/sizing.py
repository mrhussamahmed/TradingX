"""Signal sizing for research backtests.

Non-pre-sized strategies use generic volatility targeting and a fixed
fractional Kelly multiplier. Pre-sized strategies pass through
unchanged.
"""

from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]

from tradingx.features.volatility import forecast_volatility, volatility_scale
from tradingx.signals.trend import REQUIRED_OHLCV_COLUMNS

KELLY_FRACTION = 0.33
TARGET_VOLATILITY = 0.12
REALIZED_VOL_WINDOW_DAYS = 20
MAX_GROSS_LEVERAGE = 1.0


def apply_position_sizing(
    ohlcv: pd.DataFrame,
    *,
    signal: pd.Series,
    pre_sized: bool,
    kelly_fraction: float = KELLY_FRACTION,
    target_volatility: float = TARGET_VOLATILITY,
    realized_vol_window_days: int = REALIZED_VOL_WINDOW_DAYS,
    max_gross_leverage: float = MAX_GROSS_LEVERAGE,
    forecast_method: str = "realized",
) -> pd.Series:
    _validate_ohlcv(ohlcv)
    if not signal.index.equals(ohlcv.index):
        raise ValueError("signal must share the OHLCV index.")
    if pre_sized:
        return signal.astype(float).copy()

    close_returns = ohlcv["close"].astype(float).pct_change()
    leverage = volatility_scale(
        target_vol=target_volatility,
        realized_vol=forecast_volatility(
            close_returns,
            lookback_days=realized_vol_window_days,
            forecast_method=forecast_method,
        ),
        max_gross_leverage=max_gross_leverage,
    )
    sized_signal = signal.astype(float) * kelly_fraction * leverage
    return sized_signal.clip(
        lower=-max_gross_leverage,
        upper=max_gross_leverage,
    )


def _validate_ohlcv(ohlcv: pd.DataFrame) -> None:
    missing = tuple(column for column in REQUIRED_OHLCV_COLUMNS if column not in ohlcv)
    if missing:
        missing_columns = ", ".join(missing)
        raise ValueError(f"OHLCV frame is missing required columns: {missing_columns}.")


__all__ = (
    "KELLY_FRACTION",
    "MAX_GROSS_LEVERAGE",
    "REALIZED_VOL_WINDOW_DAYS",
    "TARGET_VOLATILITY",
    "apply_position_sizing",
)
