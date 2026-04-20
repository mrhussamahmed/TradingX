from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest


def _ohlcv_frame(*, opens: list[float], closes: list[float]) -> pd.DataFrame:
    if len(opens) != len(closes):
        raise AssertionError("opens and closes must have the same length.")
    index = pd.date_range("2026-04-13", periods=len(opens), freq="B", tz="UTC")
    open_series = pd.Series(opens, index=index, dtype=float)
    close_series = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": open_series,
            "high": pd.concat((open_series, close_series), axis=1).max(axis=1),
            "low": pd.concat((open_series, close_series), axis=1).min(axis=1),
            "close": close_series,
            "volume": 1_000_000.0,
        },
        index=index,
    )


def _quote_enriched_ohlcv_frame(
    *,
    opens: list[float],
    closes: list[float],
) -> pd.DataFrame:
    frame = _ohlcv_frame(opens=opens, closes=closes)
    frame["bid"] = frame["open"] - 0.02
    frame["ask"] = frame["open"] + 0.02
    return frame


def _risk_free_cache(path: Path) -> Path:
    pd.DataFrame(
        {
            "date": ["2026-04-13", "2026-04-14", "2026-04-15", "2026-04-16"],
            "annualized_rate": [0.0, 0.0, 0.0, 0.0],
            "daily_rate": [0.0, 0.0, 0.0, 0.0],
        }
    ).to_csv(path, index=False)
    return path


def test_backtest_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.backtest")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_daily_bar_backtest_enters_at_next_open_without_prior_overnight_gap() -> None:
    module = importlib.import_module("tradingx.backtest")
    bars = _ohlcv_frame(
        opens=[100.0, 90.0, 99.0],
        closes=[110.0, 99.0, 108.9],
    )
    target_weights = pd.DataFrame(
        {"SPY": [0.0, 1.0, 1.0]},
        index=bars.index,
        dtype=float,
    )

    result = module.run_daily_bar_backtest(
        {"SPY": bars},
        target_weights=target_weights,
    )

    assert result.portfolio_returns.index.equals(bars.index)
    assert result.portfolio_returns.iloc[0] == pytest.approx(0.0)
    assert result.portfolio_returns.iloc[1] == pytest.approx(0.1)
    assert result.applied_weights.iloc[1]["SPY"] == pytest.approx(1.0)


def test_daily_bar_backtest_exit_realizes_overnight_gap_before_flattening() -> None:
    module = importlib.import_module("tradingx.backtest")
    bars = _ohlcv_frame(
        opens=[100.0, 110.0, 100.0],
        closes=[110.0, 121.0, 100.0],
    )
    target_weights = pd.DataFrame(
        {"SPY": [1.0, 1.0, 0.0]},
        index=bars.index,
        dtype=float,
    )

    result = module.run_daily_bar_backtest(
        {"SPY": bars},
        target_weights=target_weights,
        initial_weights={"SPY": 1.0},
    )

    expected_gap_return = (100.0 / 121.0) - 1.0

    assert result.portfolio_returns.iloc[0] == pytest.approx(0.1)
    assert result.portfolio_returns.iloc[1] == pytest.approx(0.1)
    assert result.portfolio_returns.iloc[2] == pytest.approx(expected_gap_return)
    assert result.applied_weights.iloc[2]["SPY"] == pytest.approx(0.0)


def test_daily_bar_backtest_applies_same_day_open_weight_when_signal_is_actionable(
    ) -> None:
    module = importlib.import_module("tradingx.backtest")
    bars = _ohlcv_frame(
        opens=[100.0, 110.0, 121.0],
        closes=[110.0, 121.0, 121.0],
    )
    target_weights = pd.DataFrame(
        {"SPY": [0.0, 1.0, 1.0]},
        index=bars.index,
        dtype=float,
    )

    result = module.run_daily_bar_backtest(
        {"SPY": bars},
        target_weights=target_weights,
    )

    assert result.portfolio_returns.tolist() == pytest.approx([0.0, 0.1, 0.0])
    assert result.equity_curve.iloc[-1] == pytest.approx(1.1)
    assert result.applied_weights["SPY"].tolist() == pytest.approx([0.0, 1.0, 1.0])


def test_daily_bar_backtest_full_exposure_toy_path_compounds_to_twenty_one_percent(
    ) -> None:
    module = importlib.import_module("tradingx.backtest")
    bars = _ohlcv_frame(
        opens=[100.0, 110.0, 121.0],
        closes=[110.0, 121.0, 121.0],
    )
    target_weights = pd.DataFrame(
        {"SPY": [1.0, 1.0, 1.0]},
        index=bars.index,
        dtype=float,
    )

    result = module.run_daily_bar_backtest(
        {"SPY": bars},
        target_weights=target_weights,
    )

    assert result.portfolio_returns.tolist() == pytest.approx([0.1, 0.1, 0.0])
    assert result.equity_curve.iloc[-1] == pytest.approx(1.21)


def test_smoke_summary_reports_zero_active_metrics_for_buy_and_hold_vs_benchmark(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("tradingx.backtest")
    bars = _ohlcv_frame(
        opens=[100.0, 110.0, 121.0, 118.0],
        closes=[110.0, 121.0, 118.0, 130.0],
    )
    risk_free_cache = _risk_free_cache(tmp_path / "risk_free_daily.csv")

    summary = module.run_buy_and_hold_smoke_backtest(
        symbol="SPY",
        bars=bars,
        risk_free_cache_path=risk_free_cache,
    )

    assert summary["symbol"] == "SPY"
    assert summary["window_start_utc"] == datetime(2026, 4, 13, tzinfo=UTC)
    assert summary["window_end_utc"] == datetime(2026, 4, 16, tzinfo=UTC)
    assert summary["strategy"]["max_drawdown"] == pytest.approx(
        summary["benchmark"]["max_drawdown"]
    )
    assert summary["active"]["excess_cagr"] == pytest.approx(0.0)
    assert summary["active"]["excess_sharpe"] == pytest.approx(0.0)


def test_daily_bar_backtest_applies_costs_on_rebalance_trades() -> None:
    module = importlib.import_module("tradingx.backtest")
    bars = _quote_enriched_ohlcv_frame(
        opens=[100.0, 100.0, 100.0],
        closes=[100.0, 100.0, 100.0],
    )
    target_weights = pd.DataFrame(
        {"SPY": [1.0, 0.0, 0.0]},
        index=bars.index,
        dtype=float,
    )

    result = module.run_daily_bar_backtest(
        {"SPY": bars},
        target_weights=target_weights,
        cost_model_config=module.CostModelConfig(),
    )

    assert result.portfolio_returns.iloc[0] < 0.0
    assert result.portfolio_returns.iloc[1] < 0.0


def test_daily_bar_backtest_rebalances_drifted_weights_before_costing() -> None:
    module = importlib.import_module("tradingx.backtest")
    bars_by_symbol = {
        "SPY": _quote_enriched_ohlcv_frame(
            opens=[100.0, 110.0],
            closes=[100.0, 110.0],
        ),
        "QQQ": _quote_enriched_ohlcv_frame(
            opens=[100.0, 100.0],
            closes=[100.0, 100.0],
        ),
    }
    target_weights = pd.DataFrame(
        {"SPY": [0.5, 0.5], "QQQ": [0.5, 0.5]},
        index=bars_by_symbol["SPY"].index,
        dtype=float,
    )

    without_costs = module.run_daily_bar_backtest(
        bars_by_symbol,
        target_weights=target_weights,
        initial_weights={"SPY": 0.5, "QQQ": 0.5},
    )
    with_costs = module.run_daily_bar_backtest(
        bars_by_symbol,
        target_weights=target_weights,
        initial_weights={"SPY": 0.5, "QQQ": 0.5},
        cost_model_config=module.CostModelConfig(),
    )

    assert without_costs.portfolio_returns.iloc[1] == pytest.approx(0.05)
    assert (
        with_costs.portfolio_returns.iloc[1]
        < without_costs.portfolio_returns.iloc[1]
    )
