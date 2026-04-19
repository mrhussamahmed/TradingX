from __future__ import annotations

import importlib

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
