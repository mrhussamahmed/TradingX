from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd


def _load_script_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "compare_vol_forecasts.py"
    spec = importlib.util.spec_from_file_location(
        "compare_vol_forecasts_script",
        script_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_constant_vol_bars(
    target_daily_vol: float,
    n: int = 600,
) -> dict[str, pd.DataFrame]:
    returns = np.array(
        [target_daily_vol if idx % 2 == 0 else -target_daily_vol for idx in range(n)],
        dtype=float,
    )
    closes = 100.0 * np.cumprod(1.0 + returns)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    return {
        "SPY": pd.DataFrame({"close": closes, "volume": [1e7] * n}, index=dates),
    }


def test_forecast_error_metric_is_volatility_not_variance() -> None:
    module = _load_script_module()
    target_daily_vol = 0.012
    expected_annual_vol = target_daily_vol * math.sqrt(252)
    bars = _build_constant_vol_bars(target_daily_vol, n=600)
    forecasts_by_symbol = pd.Series(
        [expected_annual_vol] * len(bars["SPY"]),
        index=bars["SPY"].index,
    )

    metrics = module._forecast_error_metrics(
        bars,
        {"perfect": {"SPY": forecasts_by_symbol}},
    )
    perfect = metrics["perfect"]

    assert perfect["pooled_rmse_vol"] < 0.02
    assert "SPY" in perfect["symbols"]
    assert abs(
        perfect["symbols"]["SPY"]["rmse_vol"] - perfect["pooled_rmse_vol"]
    ) < 1e-9


def test_forecast_metrics_preserve_method_keyed_top_level_shape() -> None:
    module = _load_script_module()
    bars = _build_constant_vol_bars(0.01, n=400)
    forecasts = {
        "realized": {
            "SPY": pd.Series([0.15] * len(bars["SPY"]), index=bars["SPY"].index)
        },
        "ewma": {"SPY": pd.Series([0.20] * len(bars["SPY"]), index=bars["SPY"].index)},
    }

    metrics = module._forecast_error_metrics(bars, forecasts)

    assert set(metrics.keys()) == {"realized", "ewma"}
    for method_name in metrics:
        assert "symbols" in metrics[method_name]
        assert "SPY" in metrics[method_name]["symbols"]
        assert "pooled_rmse_vol" in metrics[method_name]
        assert "prediction_count" in metrics[method_name]


def test_forward_realized_vol_alignment_is_not_backward_looking() -> None:
    module = _load_script_module()
    n = 400
    lookback = 20
    rng = np.random.default_rng(seed=7)
    first_half = rng.normal(scale=0.005, size=n // 2)
    second_half = rng.normal(scale=0.030, size=n // 2)
    returns = np.concatenate([first_half, second_half])
    closes = 100.0 * np.cumprod(1.0 + returns)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    bars = {"SPY": pd.DataFrame({"close": closes, "volume": [1e7] * n}, index=dates)}

    series_returns = pd.Series(returns, index=dates)
    clairvoyant = (
        series_returns.rolling(lookback).std(ddof=1).shift(-lookback)
        * math.sqrt(252)
    )

    metrics = module._forecast_error_metrics(
        bars,
        {"clairvoyant": {"SPY": clairvoyant}},
        lookback_days=lookback,
    )

    assert metrics["clairvoyant"]["pooled_rmse_vol"] < 0.01


def test_method_forecasts_includes_har_rv() -> None:
    module = _load_script_module()
    bars = _build_constant_vol_bars(0.012, n=600)
    forecasts = module._method_forecasts(
        bars,
        realized_window=20,
        ewma_lambda=0.94,
        garch_train_size=252,
    )

    assert "har_rv" in forecasts
    assert set(forecasts["har_rv"].keys()) == {"SPY"}


def test_forecast_metrics_cover_har_rv_method() -> None:
    module = _load_script_module()
    bars = _build_constant_vol_bars(0.012, n=600)
    forecasts = module._method_forecasts(
        bars,
        realized_window=20,
        ewma_lambda=0.94,
        garch_train_size=252,
    )
    metrics = module._forecast_error_metrics(bars, forecasts)

    assert "har_rv" in metrics
    assert "pooled_rmse_vol" in metrics["har_rv"]


def test_pick_aggregate_winner_returns_lowest_pooled_rmse_method() -> None:
    module = _load_script_module()
    metrics = {
        "realized": {"pooled_rmse_vol": 0.08, "symbols": {}, "prediction_count": 100},
        "ewma": {"pooled_rmse_vol": 0.05, "symbols": {}, "prediction_count": 100},
        "garch": {"pooled_rmse_vol": 0.07, "symbols": {}, "prediction_count": 100},
        "har_rv": {"pooled_rmse_vol": 0.04, "symbols": {}, "prediction_count": 100},
    }

    assert module._pick_aggregate_winner(metrics) == "har_rv"


def test_pick_aggregate_winner_skips_methods_with_zero_predictions() -> None:
    module = _load_script_module()
    metrics = {
        "realized": {"pooled_rmse_vol": 0.01, "symbols": {}, "prediction_count": 0},
        "ewma": {"pooled_rmse_vol": 0.05, "symbols": {}, "prediction_count": 100},
    }

    assert module._pick_aggregate_winner(metrics) == "ewma"
