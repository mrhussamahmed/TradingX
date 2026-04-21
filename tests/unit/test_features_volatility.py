from __future__ import annotations

import importlib
import math

import numpy as np
import pandas as pd
import pytest


def test_volatility_feature_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.features.volatility")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_realized_volatility_uses_only_t_minus_1_returns() -> None:
    module = importlib.import_module("tradingx.features.volatility")
    returns = pd.Series(
        [0.01] * 60 + [0.25, 0.0],
        index=pd.date_range("2026-01-02", periods=62, freq="B", tz="UTC"),
        dtype=float,
    )

    realized = module.realized_vol(returns, lookback_days=60)

    assert realized.iloc[60] == pytest.approx(0.0)
    assert realized.iloc[61] > 0.0


def test_volatility_scale_caps_leverage_at_one() -> None:
    module = importlib.import_module("tradingx.features.volatility")
    realized = pd.Series([0.03, 0.08, 0.50], dtype=float)

    scale = module.volatility_scale(
        target_vol=0.12,
        realized_vol=realized,
        max_gross_leverage=1.0,
    )

    assert scale.tolist() == pytest.approx([1.0, 1.0, 0.24])


def test_forecast_volatility_garch_preserves_shape_and_falls_back() -> None:
    module = importlib.import_module("tradingx.features.volatility")
    returns = pd.Series(
        [0.01, -0.008, 0.012, -0.006, 0.009] * 40,
        index=pd.date_range("2024-01-02", periods=200, freq="B", tz="UTC"),
        dtype=float,
    )

    forecast = module.forecast_volatility(
        returns,
        lookback_days=20,
        forecast_method="garch",
        garch_train_size=60,
    )
    fallback = module.realized_vol(returns, lookback_days=20)

    assert forecast.index.equals(returns.index)
    assert forecast.iloc[40] == pytest.approx(fallback.iloc[40])
    assert forecast.dropna().shape[0] >= fallback.dropna().shape[0]


def test_har_rv_returns_series_aligned_to_input() -> None:
    module = importlib.import_module("tradingx.features.volatility")
    rng = np.random.default_rng(seed=42)
    returns = pd.Series(
        rng.normal(scale=0.01, size=500),
        index=pd.date_range("2020-01-01", periods=500, freq="B"),
    )

    forecast = module.forecast_volatility(
        returns,
        lookback_days=20,
        forecast_method="har_rv",
    )

    assert isinstance(forecast, pd.Series)
    assert len(forecast) == len(returns)
    assert forecast.index.equals(returns.index)


def test_har_rv_has_nan_prefix_then_valid_forecasts() -> None:
    module = importlib.import_module("tradingx.features.volatility")
    rng = np.random.default_rng(seed=42)
    returns = pd.Series(
        rng.normal(scale=0.01, size=500),
        index=pd.date_range("2020-01-01", periods=500, freq="B"),
    )

    forecast = module.forecast_volatility(
        returns,
        lookback_days=20,
        forecast_method="har_rv",
        har_rv_components=(1, 5, 22),
    )

    required_prefix = 22 + 20
    assert forecast.iloc[:required_prefix].isna().all()
    tail = forecast.dropna()
    assert len(tail) > 0
    assert (tail > 0).all()


def test_har_rv_is_deterministic_for_same_seed() -> None:
    module = importlib.import_module("tradingx.features.volatility")
    rng = np.random.default_rng(seed=7)
    returns = pd.Series(
        rng.normal(scale=0.01, size=300),
        index=pd.date_range("2020-01-01", periods=300, freq="B"),
    )

    a = module.forecast_volatility(
        returns,
        lookback_days=20,
        forecast_method="har_rv",
    )
    b = module.forecast_volatility(
        returns,
        lookback_days=20,
        forecast_method="har_rv",
    )

    pd.testing.assert_series_equal(a, b)


def test_har_rv_recovers_constant_vol_on_stationary_series() -> None:
    module = importlib.import_module("tradingx.features.volatility")
    target_daily_vol = 0.012
    expected_annual_vol = target_daily_vol * math.sqrt(252)
    rng = np.random.default_rng(seed=99)
    returns = pd.Series(
        rng.normal(scale=target_daily_vol, size=800),
        index=pd.date_range("2020-01-01", periods=800, freq="B"),
    )

    forecast = module.forecast_volatility(
        returns,
        lookback_days=20,
        forecast_method="har_rv",
    )
    final_half = forecast.dropna().iloc[-200:]

    assert len(final_half) > 0
    mean_forecast = float(final_half.mean())
    assert abs(mean_forecast - expected_annual_vol) / expected_annual_vol < 0.25
