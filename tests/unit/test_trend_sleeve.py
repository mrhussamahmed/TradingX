from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.sleeves.trend import TrendSleeve
from tradingx.types import RegimeSnapshot, SleeveContext


def _build_uptrend_bars(n: int = 400) -> pd.DataFrame:
    rng = np.random.default_rng(seed=11)
    noise = rng.normal(scale=0.01, size=n)
    drift = 0.0008
    closes = 100.0 * np.cumprod(1.0 + noise + drift)
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


def _risk_on_regime(observation_date: date) -> RegimeSnapshot:
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


def test_trend_sleeve_emits_long_on_uptrend_in_risk_on() -> None:
    bars = _build_uptrend_bars()
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    trades = sleeve.plan_for_bar(
        SleeveContext(
            observation_date=bars.index[-1].date(),
            bars_by_symbol={"SPY": bars},
            regime=_risk_on_regime(bars.index[-1].date()),
            current_weights_by_symbol={"SPY": Decimal("0")},
            sleeve_budget_equity=Decimal("100000"),
        )
    )

    spy_trade = next(t for t in trades if t.symbol == "SPY")
    assert spy_trade.side == "buy"
    assert spy_trade.target_weight_of_sleeve_budget > Decimal("0")
    assert spy_trade.rationale == "tsmom_long_vol_targeted"


def test_trend_sleeve_emits_hold_on_short_history() -> None:
    bars = _build_uptrend_bars(n=50)
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    trades = sleeve.plan_for_bar(
        SleeveContext(
            observation_date=bars.index[-1].date(),
            bars_by_symbol={"SPY": bars},
            regime=_risk_on_regime(bars.index[-1].date()),
            current_weights_by_symbol={"SPY": Decimal("0")},
            sleeve_budget_equity=Decimal("100000"),
        )
    )

    spy_trade = next(t for t in trades if t.symbol == "SPY")
    assert spy_trade.side == "hold"
    assert spy_trade.rationale == "insufficient_history"
    assert spy_trade.target_weight_of_sleeve_budget == Decimal("0")


def test_trend_sleeve_liquidates_in_stressed_regime() -> None:
    bars = _build_uptrend_bars()
    stressed_regime = RegimeSnapshot(
        observation_date=bars.index[-1].date(),
        regime="stressed",
        above_sma_200=False,
        vix_elevated=True,
        vix_stressed=True,
        yield_curve_inverted=True,
        spy_close=Decimal("400"),
        spy_sma_200=Decimal("500"),
        vix_close=Decimal("45"),
        yield_curve_spread_bps=Decimal("-25"),
    )
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    trades = sleeve.plan_for_bar(
        SleeveContext(
            observation_date=bars.index[-1].date(),
            bars_by_symbol={"SPY": bars},
            regime=stressed_regime,
            current_weights_by_symbol={"SPY": Decimal("0.5")},
            sleeve_budget_equity=Decimal("100000"),
        )
    )

    spy_trade = next(t for t in trades if t.symbol == "SPY")
    assert spy_trade.side == "sell"
    assert spy_trade.target_weight_of_sleeve_budget == Decimal("0")
    assert spy_trade.rationale == "regime_stressed_liquidate"


def test_trend_sleeve_suppresses_new_entry_in_risk_off() -> None:
    bars = _build_uptrend_bars()
    risk_off = RegimeSnapshot(
        observation_date=bars.index[-1].date(),
        regime="risk_off",
        above_sma_200=False,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("470"),
        spy_sma_200=Decimal("490"),
        vix_close=Decimal("18"),
        yield_curve_spread_bps=Decimal("20"),
    )
    sleeve = TrendSleeve(allowed_instruments=("SPY",))
    trades = sleeve.plan_for_bar(
        SleeveContext(
            observation_date=bars.index[-1].date(),
            bars_by_symbol={"SPY": bars},
            regime=risk_off,
            current_weights_by_symbol={"SPY": Decimal("0")},
            sleeve_budget_equity=Decimal("100000"),
        )
    )

    spy_trade = next(t for t in trades if t.symbol == "SPY")
    assert spy_trade.target_weight_of_sleeve_budget == Decimal("0")
    assert spy_trade.rationale == "regime_risk_off_suppress_entry"
