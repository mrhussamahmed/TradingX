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
