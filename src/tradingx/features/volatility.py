"""Volatility feature primitives shared by research signals.

These helpers are pure math utilities with no strategy semantics.
"""

from __future__ import annotations

import math
import warnings

import pandas as pd  # type: ignore[import-untyped]
from arch import arch_model

TRADING_DAYS_PER_YEAR = 252


def realized_vol(
    returns: pd.Series,
    *,
    lookback_days: int,
) -> pd.Series:
    return returns.astype(float).shift(1).rolling(lookback_days).std(
        ddof=1
    ) * math.sqrt(TRADING_DAYS_PER_YEAR)


def forecast_volatility(
    returns: pd.Series,
    *,
    lookback_days: int,
    forecast_method: str = "realized",
    ewma_lambda: float = 0.94,
    garch_train_size: int = 252,
) -> pd.Series:
    realized = realized_vol(returns, lookback_days=lookback_days)
    if forecast_method == "realized":
        return realized
    if forecast_method == "ewma":
        return _ewma_vol(returns, ewma_lambda=ewma_lambda)
    if forecast_method == "garch":
        garch = _garch_vol(returns, garch_train_size=garch_train_size)
        return garch.combine_first(realized)
    raise ValueError(f"Unsupported forecast_method: {forecast_method}")


def _ewma_vol(returns: pd.Series, *, ewma_lambda: float) -> pd.Series:
    variance = returns.astype(float).pow(2.0).shift(1).ewm(
        alpha=1.0 - ewma_lambda,
        adjust=False,
    ).mean()
    return variance.pow(0.5) * math.sqrt(TRADING_DAYS_PER_YEAR)


def _garch_vol(returns: pd.Series, *, garch_train_size: int) -> pd.Series:
    clean_returns = returns.dropna().astype(float)
    if len(clean_returns) <= garch_train_size:
        return pd.Series(index=returns.index, dtype=float)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = arch_model(
            clean_returns * 100.0,
            vol="GARCH",
            p=1,
            q=1,
            mean="Zero",
            dist="normal",
            rescale=False,
        )
        fitted = model.fit(last_obs=garch_train_size - 1, disp="off")
        forecast = fitted.forecast(horizon=1, start=garch_train_size, reindex=True)

    variance = forecast.variance["h.1"] / 10_000.0
    return variance.pow(0.5).reindex(returns.index) * math.sqrt(TRADING_DAYS_PER_YEAR)


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
    "forecast_volatility",
    "realized_vol",
    "volatility_scale",
)
