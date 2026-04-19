from __future__ import annotations

import importlib

import pandas as pd
import pytest


def _basket_ohlcv(closes_by_symbol: dict[str, list[float]]) -> pd.DataFrame:
    lengths = {len(values) for values in closes_by_symbol.values()}
    if len(lengths) != 1:
        raise AssertionError("All symbols must have the same number of bars.")
    index = pd.date_range(
        "2025-01-02",
        periods=next(iter(lengths)),
        freq="B",
        tz="UTC",
    )
    columns: dict[tuple[str, str], pd.Series] = {}
    for symbol, closes in closes_by_symbol.items():
        close_series = pd.Series(closes, index=index, dtype=float)
        columns[(symbol, "open")] = close_series
        columns[(symbol, "high")] = close_series * 1.01
        columns[(symbol, "low")] = close_series * 0.99
        columns[(symbol, "close")] = close_series
        columns[(symbol, "volume")] = pd.Series(1_000_000.0, index=index, dtype=float)
    return pd.DataFrame(columns, index=index)


def test_mean_revert_signal_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.signals.mean_revert")

    assert module.__doc__
    assert hasattr(module, "__all__")
    assert module.PRE_SIZED is False


def test_generate_mean_revert_signal_uses_only_t_minus_1_residuals() -> None:
    module = importlib.import_module("tradingx.signals.mean_revert")
    frame = _basket_ohlcv(
        {
            "SPY": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "QQQ": [100.0, 101.0, 102.0, 103.0, 104.0, 96.0, 90.0, 91.0],
            "IWM": [100.0, 101.0, 102.0, 103.0, 104.0, 113.0, 120.0, 119.0],
        }
    )

    signal = module.generate_mean_revert_signal(
        frame,
        benchmark_symbol="SPY",
        tradable_symbols=("QQQ", "IWM"),
        beta_window_days=3,
        residual_sum_days=2,
        zscore_window_days=3,
        zscore_threshold=0.5,
    )

    assert list(signal.columns) == ["QQQ", "IWM"]
    assert signal.index.equals(frame.index)
    assert signal.iloc[:-1].abs().sum().sum() == 0.0
    assert signal.iloc[-1]["QQQ"] == 1.0
    assert signal.iloc[-1]["IWM"] == -1.0


def test_generate_mean_revert_signal_rejects_benchmark_as_tradable_symbol() -> None:
    module = importlib.import_module("tradingx.signals.mean_revert")
    frame = _basket_ohlcv(
        {
            "SPY": [100.0, 101.0, 102.0, 103.0],
            "QQQ": [100.0, 101.0, 100.0, 101.0],
        }
    )

    with pytest.raises(
        ValueError,
        match="tradable_symbols must not include the benchmark symbol",
    ):
        module.generate_mean_revert_signal(
            frame,
            benchmark_symbol="SPY",
            tradable_symbols=("SPY", "QQQ"),
            beta_window_days=2,
            residual_sum_days=2,
            zscore_window_days=2,
            zscore_threshold=0.5,
        )
