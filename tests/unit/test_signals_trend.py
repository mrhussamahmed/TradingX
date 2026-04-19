from __future__ import annotations

import importlib

import pandas as pd


def _ohlcv_frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2024-01-02", periods=len(closes), freq="B", tz="UTC")
    close_series = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close_series,
            "high": close_series * 1.01,
            "low": close_series * 0.99,
            "close": close_series,
            "volume": 1_000_000.0,
        },
        index=index,
    )


def test_trend_signal_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.signals.trend")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_generate_trend_signal_uses_only_t_minus_1_data() -> None:
    module = importlib.import_module("tradingx.signals.trend")
    closes = [100.0] * 40
    closes.extend(100.0 + (0.35 * float(index)) for index in range(220))
    closes.extend((40.0, 39.0))
    frame = _ohlcv_frame(closes)

    signal = module.generate_trend_signal(frame)

    assert signal.index.equals(frame.index)
    assert signal.iloc[:252].eq(0.0).all()
    assert signal.iloc[-2] == 1.0
    assert signal.iloc[-1] == 0.0
