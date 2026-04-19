from __future__ import annotations

import importlib

import pandas as pd
import pytest


def _ohlcv_frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2025-01-02", periods=len(closes), freq="B", tz="UTC")
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


def test_sizing_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.sizing")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_apply_position_sizing_passes_pre_sized_signals_through() -> None:
    module = importlib.import_module("tradingx.sizing")
    frame = _ohlcv_frame([100.0 + (0.2 * float(index)) for index in range(70)])
    signal = pd.Series(0.75, index=frame.index, dtype=float)

    sized = module.apply_position_sizing(
        frame,
        signal=signal,
        pre_sized=True,
    )

    assert sized.equals(signal)


def test_apply_position_sizing_uses_kelly_fraction_and_t_minus_1_volatility() -> None:
    module = importlib.import_module("tradingx.sizing")
    closes = [100.0 + (0.2 * float(index)) for index in range(25)]
    closes.extend((140.0, 141.0))
    frame = _ohlcv_frame(closes)
    signal = pd.Series(1.0, index=frame.index, dtype=float)

    sized = module.apply_position_sizing(frame, signal=signal, pre_sized=False)

    assert sized.iloc[:20].eq(0.0).all()
    assert sized.iloc[-2] == pytest.approx(0.33)
    assert 0.0 < sized.iloc[-1] < 0.33
