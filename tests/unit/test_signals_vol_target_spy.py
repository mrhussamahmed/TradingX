from __future__ import annotations

import importlib

import pandas as pd


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


def test_vol_target_spy_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.signals.vol_target_spy")

    assert module.__doc__
    assert hasattr(module, "__all__")
    assert module.PRE_SIZED is True


def test_generate_vol_target_spy_signal_uses_only_t_minus_1_volatility() -> None:
    module = importlib.import_module("tradingx.signals.vol_target_spy")
    closes = [100.0 + (0.2 * float(index)) for index in range(65)]
    closes.extend((140.0, 141.0))
    frame = _ohlcv_frame(closes)

    signal = module.generate_vol_target_spy_signal(frame)

    assert signal.index.equals(frame.index)
    assert signal.iloc[:60].eq(0.0).all()
    assert signal.iloc[-2] == 1.0
    assert 0.0 < signal.iloc[-1] < 1.0
