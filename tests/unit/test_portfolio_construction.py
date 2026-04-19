from __future__ import annotations

import importlib
from decimal import Decimal

import pandas as pd
import pytest


def _signal_frame(
    rows: list[dict[str, float]],
    *,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    index = pd.date_range(start, periods=len(rows), freq="B", tz="UTC")
    return pd.DataFrame(rows, index=index, dtype=float).fillna(0.0)


def _benchmark_bars(periods: int = 800) -> pd.DataFrame:
    index = pd.date_range("2021-01-04", periods=periods, freq="B", tz="UTC")
    closes: list[float] = []
    price = 100.0
    for position in range(periods):
        if position < periods - 20:
            daily_return = 0.001 if position % 2 == 0 else -0.001
        else:
            daily_return = 0.10 if position % 2 == 0 else -0.08
        price *= 1.0 + daily_return
        closes.append(price)
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


def test_portfolio_construction_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.portfolio_construction")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_build_target_weights_averages_active_sleeves_and_applies_caps() -> None:
    module = importlib.import_module("tradingx.portfolio_construction")
    config = module.PortfolioConstructionConfig()
    timestamp = pd.Timestamp("2026-04-17T00:00:00+00:00")
    sleeve_signals = {
        "trend_following": pd.DataFrame(
            [{"SPY": 0.30, "QQQ": 0.20}],
            index=[timestamp],
            dtype=float,
        ),
        "mean_reversion": pd.DataFrame(
            [{"IWM": 0.60, "QQQ": -0.10}],
            index=[timestamp],
            dtype=float,
        ),
    }

    weights = module.build_target_weights(
        sleeve_signals=sleeve_signals,
        current_positions={},
        account_equity=Decimal("100000"),
        config=config,
    )

    assert weights["SPY"] == Decimal("0.15")
    assert weights["QQQ"] == Decimal("0.05")
    assert weights["IWM"] == Decimal("0.2")


def test_build_target_weights_holds_small_changes_inside_no_trade_band() -> None:
    module = importlib.import_module("tradingx.portfolio_construction")
    config = module.PortfolioConstructionConfig(min_trade_notional=Decimal("50"))
    timestamp = pd.Timestamp("2026-04-17T00:00:00+00:00")
    sleeve_signals = {
        "trend_following": pd.DataFrame(
            [{"SPY": 0.1004, "QQQ": 0.1020}],
            index=[timestamp],
            dtype=float,
        )
    }

    weights = module.build_target_weights(
        sleeve_signals=sleeve_signals,
        current_positions={
            "SPY": Decimal("0.10"),
            "QQQ": Decimal("0.10"),
        },
        account_equity=Decimal("100000"),
        config=config,
    )

    assert weights["SPY"] == Decimal("0.10")
    assert weights["QQQ"] == Decimal("0.102")


def test_build_target_weights_limits_positions_and_rescales_gross() -> None:
    module = importlib.import_module("tradingx.portfolio_construction")
    config = module.PortfolioConstructionConfig(max_positions=10)
    timestamp = pd.Timestamp("2026-04-17T00:00:00+00:00")
    sleeve_signals = {
        "trend_following": pd.DataFrame(
            [
                {
                    f"S{index:02d}": 0.20
                    for index in range(11)
                }
            ],
            index=[timestamp],
            dtype=float,
        )
    }

    weights = module.build_target_weights(
        sleeve_signals=sleeve_signals,
        current_positions={},
        account_equity=Decimal("100000"),
        config=config,
    )

    non_zero_weights = {
        symbol: weight for symbol, weight in weights.items() if weight != Decimal("0")
    }

    assert len(non_zero_weights) == 10
    assert sum(abs(float(weight)) for weight in non_zero_weights.values()) == pytest.approx(
        1.0
    )


def test_build_target_weights_flattens_positions_when_all_sleeves_are_inactive() -> None:
    module = importlib.import_module("tradingx.portfolio_construction")
    config = module.PortfolioConstructionConfig(min_trade_notional=Decimal("50"))
    timestamp = pd.Timestamp("2026-04-17T00:00:00+00:00")
    sleeve_signals = {
        "trend_following": pd.DataFrame(
            [{"SPY": 0.0, "QQQ": 0.0}],
            index=[timestamp],
            dtype=float,
        )
    }

    weights = module.build_target_weights(
        sleeve_signals=sleeve_signals,
        current_positions={
            "SPY": Decimal("0.10"),
            "QQQ": Decimal("0.08"),
        },
        account_equity=Decimal("100000"),
        config=config,
    )

    assert weights["SPY"] == Decimal("0")
    assert weights["QQQ"] == Decimal("0")


def test_build_target_weight_history_scales_long_equity_sleeves_in_crash_overlay() -> (
    None
):
    module = importlib.import_module("tradingx.portfolio_construction")
    config = module.PortfolioConstructionConfig(crash_overlay_factor=0.5)
    benchmark_bars = _benchmark_bars()
    sleeve_signals = {
        "trend_following": _signal_frame(
            [{"SPY": 0.20}] * len(benchmark_bars),
            start="2021-01-04",
        ),
        "mean_reversion": _signal_frame(
            [{"EEM": -0.20}] * len(benchmark_bars),
            start="2021-01-04",
        ),
    }

    history = module.build_target_weight_history(
        sleeve_signals=sleeve_signals,
        account_equity=Decimal("100000"),
        config=config,
        benchmark_bars=benchmark_bars,
    )

    assert history.iloc[-30]["SPY"] == pytest.approx(0.10)
    assert history.iloc[-30]["EEM"] == pytest.approx(-0.10)
    assert history.iloc[-1]["SPY"] == pytest.approx(0.05)
    assert history.iloc[-1]["EEM"] == pytest.approx(-0.10)
