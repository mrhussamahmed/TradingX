from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.backtest import run_daily_bar_backtest
from tradingx.costs import CostModelConfig
from tradingx.sleeves.evaluation import (
    build_sleeve_target_weight_history,
    simulate_sleeve_returns,
)
from tradingx.sleeves.trend import TrendSleeve
from tradingx.types import RegimeSnapshot


def _bars(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed=17)
    closes = 100.0 * np.cumprod(1.0 + rng.normal(scale=0.01, size=n))
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": [1e7] * n,
        },
        index=dates,
    )


def _risk_on(observation_date: date) -> RegimeSnapshot:
    return RegimeSnapshot(
        observation_date=observation_date,
        regime="risk_on",
        above_sma_200=True,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=Decimal("15"),
        yield_curve_spread_bps=Decimal("35"),
    )


def test_build_sleeve_target_weight_history_is_pure_dataframe() -> None:
    bars = _bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    regimes = {timestamp.date(): _risk_on(timestamp.date()) for timestamp in bars.index}
    frame = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )

    assert isinstance(frame, pd.DataFrame)
    assert "SPY" in frame.columns
    assert (frame["SPY"].dropna() >= 0.0).all()
    assert (frame["SPY"].dropna() <= 1.0).all()


def test_build_sleeve_target_weight_history_deterministic() -> None:
    bars = _bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    regimes = {timestamp.date(): _risk_on(timestamp.date()) for timestamp in bars.index}
    left = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    right = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )

    pd.testing.assert_frame_equal(left, right)


def test_simulate_sleeve_returns_matches_direct_backtest_on_same_weights() -> None:
    bars = _bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    regimes = {timestamp.date(): _risk_on(timestamp.date()) for timestamp in bars.index}
    resolved_cost_config = CostModelConfig()

    sleeve_returns, sleeve_drag = simulate_sleeve_returns(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
        cost_model_config=resolved_cost_config,
    )

    target_weights = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    direct_result = run_daily_bar_backtest(
        {"SPY": bars},
        target_weights=target_weights,
        cost_model_config=resolved_cost_config,
    )
    direct_returns = tuple(
        Decimal(str(value)) for value in direct_result.portfolio_returns.tolist()
    )

    assert sleeve_returns == direct_returns
    assert sleeve_drag == direct_result.annualized_cost_drag_bps
