from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.features.regime import classify_regime
from tradingx.sleeves.evaluation import simulate_sleeve_returns
from tradingx.sleeves.trend import TrendSleeve
from tradingx.sleeves.vol_managed_beta import VolManagedBetaSleeve
from tradingx.types import RegimeSnapshot


def _build_bars(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed=19)
    closes = 100.0 * np.cumprod(1.0 + rng.normal(scale=0.01, size=n))
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": [1e7] * n,
            "bid": closes - 0.05,
            "ask": closes + 0.05,
        },
        index=dates,
    )


def _build_regimes(bars: pd.DataFrame) -> dict[date, RegimeSnapshot]:
    closes = bars["close"].astype(float)
    sma_200 = closes.rolling(200, min_periods=1).mean()
    regimes: dict[date, RegimeSnapshot] = {}
    for timestamp in bars.index:
        regimes[timestamp.date()] = classify_regime(
            observation_date=timestamp.date(),
            spy_close=Decimal(str(float(closes.loc[timestamp]))),
            spy_sma_200=Decimal(str(float(sma_200.loc[timestamp]))),
            vix_close=None,
            yield_curve_spread_bps=None,
        )
    return regimes


def test_trend_sleeve_end_to_end_produces_return_series() -> None:
    bars = _build_bars()
    returns, drag = simulate_sleeve_returns(
        TrendSleeve(allowed_instruments=("SPY",)),
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=_build_regimes(bars),
        sleeve_budget_equity=Decimal("100000"),
    )

    assert len(returns) == len(bars)
    assert all(isinstance(value, Decimal) for value in returns)
    assert drag >= Decimal("0")


def test_vol_managed_beta_sleeve_end_to_end_produces_return_series() -> None:
    bars = _build_bars()
    returns, drag = simulate_sleeve_returns(
        VolManagedBetaSleeve(),
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=_build_regimes(bars),
        sleeve_budget_equity=Decimal("100000"),
    )

    assert len(returns) == len(bars)
    assert all(isinstance(value, Decimal) for value in returns)
    assert drag >= Decimal("0")
