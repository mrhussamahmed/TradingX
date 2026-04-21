from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.features.regime import classify_regime
from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.construction import (
    build_portfolio_target_weight_history,
    simulate_portfolio_returns,
)
from tradingx.portfolio.throttle import (
    apply_cdar_soft_throttle,
    apply_mdd_design_throttle,
)
from tradingx.sleeves.trend import TrendSleeve
from tradingx.sleeves.vol_managed_beta import VolManagedBetaSleeve
from tradingx.types import RegimeSnapshot


def _bars(n: int = 500, seed: int = 29) -> pd.DataFrame:
    rng = np.random.default_rng(seed=seed)
    returns = rng.normal(scale=0.01, size=n)
    closes = 100.0 * np.cumprod(1.0 + returns)
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "bid": closes * 0.999,
            "ask": closes * 1.001,
            "volume": [1e7] * n,
        },
        index=dates,
    )


def _regimes(bars: pd.DataFrame) -> dict[date, RegimeSnapshot]:
    closes = bars["close"].astype(float)
    sma = closes.rolling(200).mean()
    out: dict[date, RegimeSnapshot] = {}
    for ts in bars.index:
        if pd.isna(sma.loc[ts]):
            continue
        out[ts.date()] = classify_regime(
            observation_date=ts.date(),
            spy_close=Decimal(str(float(closes.loc[ts]))),
            spy_sma_200=Decimal(str(float(sma.loc[ts]))),
            vix_close=None,
            yield_curve_spread_bps=None,
        )
    return out


def _blueprint() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="portfolio-e2e",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )


def test_portfolio_end_to_end_builds_simulates_and_throttles() -> None:
    spy_bars = _bars()
    qqq_bars = _bars(seed=31)
    regimes = _regimes(spy_bars)
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    blueprint = _blueprint()

    target_weights = build_portfolio_target_weight_history(
        sleeves,
        blueprint=blueprint,
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )
    result = simulate_portfolio_returns(
        sleeves,
        blueprint=blueprint,
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )

    drawdown_series = pd.Series(0.0, index=target_weights.index, dtype=float)
    drawdown_series.iloc[-50:] = 0.20
    cdar_series = pd.Series(0.0, index=target_weights.index, dtype=float)
    cdar_series.iloc[-50:] = 0.12

    throttled_mdd, mdd_scale = apply_mdd_design_throttle(
        target_weights=target_weights,
        trailing_drawdown_series=drawdown_series,
        blueprint=blueprint,
    )
    throttled_both, cdar_scale = apply_cdar_soft_throttle(
        target_weights=throttled_mdd,
        trailing_cdar_series=cdar_series,
        blueprint=blueprint,
    )

    assert target_weights.shape == result.combined_target_weights.shape
    assert len(result.backtest_result.portfolio_returns) == len(target_weights)
    assert float(target_weights.abs().sum(axis=1).max()) <= 1.0 + 1e-9
    assert mdd_scale.iloc[-1] < 1.0
    assert cdar_scale.iloc[-1] < 1.0
    assert float(throttled_both.abs().sum(axis=1).iloc[-1]) < float(
        target_weights.abs().sum(axis=1).iloc[-1]
    )
