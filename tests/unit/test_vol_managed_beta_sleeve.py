from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.sleeves.vol_managed_beta import VolManagedBetaSleeve
from tradingx.types import RegimeSnapshot, SleeveContext


def _bars(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed=13)
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


def _regime(state: str, observation_date: date) -> RegimeSnapshot:
    return RegimeSnapshot(
        observation_date=observation_date,
        regime=state,
        above_sma_200=(state in {"risk_on", "neutral"}),
        vix_elevated=(state in {"risk_off", "stressed"}),
        vix_stressed=(state == "stressed"),
        yield_curve_inverted=False,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=Decimal("15"),
        yield_curve_spread_bps=Decimal("35"),
    )


def test_vol_managed_beta_only_emits_for_spy() -> None:
    bars = _bars()
    trades = VolManagedBetaSleeve().plan_for_bar(
        SleeveContext(
            observation_date=bars.index[-1].date(),
            bars_by_symbol={"SPY": bars, "QQQ": bars},
            regime=_regime("risk_on", bars.index[-1].date()),
            current_weights_by_symbol={"SPY": Decimal("0"), "QQQ": Decimal("0")},
            sleeve_budget_equity=Decimal("100000"),
        )
    )

    assert len(trades) == 1
    assert trades[0].symbol == "SPY"


def test_vol_managed_beta_emits_non_zero_weight_in_calm_regime() -> None:
    bars = _bars()
    trades = VolManagedBetaSleeve().plan_for_bar(
        SleeveContext(
            observation_date=bars.index[-1].date(),
            bars_by_symbol={"SPY": bars},
            regime=_regime("risk_on", bars.index[-1].date()),
            current_weights_by_symbol={"SPY": Decimal("0")},
            sleeve_budget_equity=Decimal("100000"),
        )
    )

    assert trades[0].target_weight_of_sleeve_budget > Decimal("0")


def test_vol_managed_beta_emits_hold_with_insufficient_history() -> None:
    bars = _bars(n=30)
    trades = VolManagedBetaSleeve().plan_for_bar(
        SleeveContext(
            observation_date=bars.index[-1].date(),
            bars_by_symbol={"SPY": bars},
            regime=_regime("risk_on", bars.index[-1].date()),
            current_weights_by_symbol={"SPY": Decimal("0")},
            sleeve_budget_equity=Decimal("100000"),
        )
    )

    assert len(trades) == 1
    assert trades[0].side == "hold"
    assert trades[0].rationale == "insufficient_history"


def test_vol_managed_beta_liquidates_in_stressed() -> None:
    bars = _bars()
    trades = VolManagedBetaSleeve().plan_for_bar(
        SleeveContext(
            observation_date=bars.index[-1].date(),
            bars_by_symbol={"SPY": bars},
            regime=_regime("stressed", bars.index[-1].date()),
            current_weights_by_symbol={"SPY": Decimal("0.5")},
            sleeve_budget_equity=Decimal("100000"),
        )
    )

    assert trades[0].side == "sell"
    assert trades[0].target_weight_of_sleeve_budget == Decimal("0")
    assert trades[0].rationale == "regime_stressed_liquidate"
