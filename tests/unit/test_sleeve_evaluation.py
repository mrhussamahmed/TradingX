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
from tradingx.types import RegimeSnapshot, SleeveContext, SleeveTrade


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


class _LastCloseDecisionSleeve:
    sleeve_id = "last-close-decision"
    family = "test"
    allowed_instruments = ("SPY",)

    def __init__(self) -> None:
        self.observed_lengths: list[int] = []
        self.observed_last_dates: list[date | None] = []

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        bars = context.bars_by_symbol["SPY"]
        self.observed_lengths.append(len(bars))
        self.observed_last_dates.append(None if bars.empty else bars.index[-1].date())
        target = (
            Decimal("1")
            if not bars.empty and bars["close"].iloc[-1] > 100
            else Decimal("0")
        )
        return (
            SleeveTrade(
                sleeve_id=self.sleeve_id,
                symbol="SPY",
                side="buy" if target > Decimal("0") else "hold",
                target_weight_of_sleeve_budget=target,
                rationale="last_prior_close",
                regime=context.regime.regime,
            ),
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


def test_build_sleeve_target_weight_history_hides_execution_session_bars() -> None:
    bars = _ohlcv = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0],
            "high": [100.0, 100.0, 500.0],
            "low": [100.0, 100.0, 1.0],
            "close": [100.0, 100.0, 500.0],
            "volume": [1_000_000.0, 1_000_000.0, 99_000_000.0],
        },
        index=pd.date_range("2026-01-05", periods=3, freq="B", tz="UTC"),
    )
    del _ohlcv
    sleeve = _LastCloseDecisionSleeve()
    regimes = {timestamp.date(): _risk_on(timestamp.date()) for timestamp in bars.index}

    frame = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )

    assert frame["SPY"].tolist() == [0.0, 0.0, 0.0]
    assert sleeve.observed_lengths == [0, 1, 2]
    assert sleeve.observed_last_dates == [
        None,
        bars.index[0].date(),
        bars.index[1].date(),
    ]


def test_sleeve_target_weight_history_current_row_ohlcv_perturbation_safe() -> None:
    bars = _bars(5)
    baseline = bars.copy()
    perturbed = bars.copy()
    perturbed.iloc[3, perturbed.columns.get_loc("open")] = 1_000.0
    perturbed.iloc[3, perturbed.columns.get_loc("high")] = 2_000.0
    perturbed.iloc[3, perturbed.columns.get_loc("low")] = 10.0
    perturbed.iloc[3, perturbed.columns.get_loc("close")] = 1_500.0
    perturbed.iloc[3, perturbed.columns.get_loc("volume")] = 99_000_000.0
    sleeve = _LastCloseDecisionSleeve()
    regimes = {
        timestamp.date(): _risk_on(timestamp.date()) for timestamp in baseline.index
    }

    left = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol={"SPY": baseline},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )
    right = build_sleeve_target_weight_history(
        _LastCloseDecisionSleeve(),
        bars_by_symbol={"SPY": perturbed},
        regime_snapshots_by_date=regimes,
        sleeve_budget_equity=Decimal("100000"),
    )

    assert left.loc[baseline.index[3], "SPY"] == right.loc[baseline.index[3], "SPY"]


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
