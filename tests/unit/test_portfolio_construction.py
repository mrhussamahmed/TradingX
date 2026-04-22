from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from tradingx.features.regime import classify_regime
from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.construction import (
    PortfolioSimulationResult,
    _combine_sleeve_weights,
    build_portfolio_target_weight_history,
    simulate_portfolio_returns,
)
from tradingx.sleeves.trend import TrendSleeve
from tradingx.sleeves.vol_managed_beta import VolManagedBetaSleeve
from tradingx.types import RegimeSnapshot, SleeveContext, SleeveTrade


def _bars(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed=seed)
    returns = rng.normal(scale=0.01, size=n)
    closes = 100.0 * np.cumprod(1.0 + returns)
    bids = closes * 0.999
    asks = closes * 1.001
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "bid": bids,
            "ask": asks,
            "volume": [1e7] * n,
        },
        index=dates,
    )


def _regimes(
    bars: pd.DataFrame,
    *,
    force_state: str | None = None,
) -> dict[date, RegimeSnapshot]:
    closes = bars["close"].astype(float)
    sma_200 = closes.rolling(200).mean()
    regimes: dict[date, RegimeSnapshot] = {}
    for timestamp in bars.index:
        if pd.isna(sma_200.loc[timestamp]):
            continue
        if force_state is not None:
            regimes[timestamp.date()] = RegimeSnapshot(
                observation_date=timestamp.date(),
                regime=force_state,
                above_sma_200=True,
                vix_elevated=False,
                vix_stressed=False,
                yield_curve_inverted=False,
                spy_close=Decimal(str(float(closes.loc[timestamp]))),
                spy_sma_200=Decimal(str(float(sma_200.loc[timestamp]))),
                vix_close=None,
                yield_curve_spread_bps=None,
            )
            continue
        regimes[timestamp.date()] = classify_regime(
            observation_date=timestamp.date(),
            spy_close=Decimal(str(float(closes.loc[timestamp]))),
            spy_sma_200=Decimal(str(float(sma_200.loc[timestamp]))),
            vix_close=None,
            yield_curve_spread_bps=None,
        )
    return regimes


def _blueprint() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="bp-1",
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


def test_combines_two_sleeves_with_equal_budgets() -> None:
    spy_bars = _bars(400)
    qqq_bars = _bars(400, seed=11)
    regimes = _regimes(spy_bars)
    target_weights = build_portfolio_target_weight_history(
        (
            TrendSleeve(allowed_instruments=("SPY", "QQQ")),
            VolManagedBetaSleeve(),
        ),
        blueprint=_blueprint(),
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )

    assert isinstance(target_weights, pd.DataFrame)
    assert set(target_weights.columns) == {"SPY", "QQQ"}
    assert target_weights.shape[0] == spy_bars.shape[0]
    assert float(target_weights.abs().sum(axis=1).max()) <= 1.0 + 1e-9


def test_stressed_regime_zeros_vol_managed_beta_and_does_not_redistribute() -> None:
    spy_bars = _bars(300)
    qqq_bars = _bars(300, seed=13)
    regimes = _regimes(spy_bars, force_state="stressed")
    target_weights = build_portfolio_target_weight_history(
        (
            TrendSleeve(allowed_instruments=("SPY", "QQQ")),
            VolManagedBetaSleeve(),
        ),
        blueprint=_blueprint(),
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )

    latest = target_weights.iloc[-1]
    assert float(latest["SPY"]) == 0.0
    assert float(latest["QQQ"]) == 0.0


@dataclass(frozen=True)
class _ConstantWeightSleeve:
    sleeve_id: str
    family: str = "dummy"
    allowed_instruments: tuple[str, ...] = ("SPY",)
    target_weight: Decimal = Decimal("1.0")

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        return (
            SleeveTrade(
                sleeve_id=self.sleeve_id,
                symbol="SPY",
                side="buy",
                target_weight_of_sleeve_budget=self.target_weight,
                rationale="constant",
                regime=context.regime.regime,
            ),
        )


def test_gross_exposure_cap_scales_uniformly_when_exceeded() -> None:
    bars = _bars(300)
    regimes = _regimes(bars, force_state="risk_on")
    sleeves = (
        _ConstantWeightSleeve(sleeve_id="a"),
        _ConstantWeightSleeve(sleeve_id="b"),
    )
    blueprint = PortfolioBlueprint(
        blueprint_id="bp-over",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="a",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
            SleeveRiskBudget(
                sleeve_id="b",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
        ),
        max_gross_exposure=Decimal("0.8"),
    )

    target_weights = build_portfolio_target_weight_history(
        sleeves,
        blueprint=blueprint,
        bars_by_symbol={"SPY": bars},
        regime_snapshots_by_date=regimes,
    )

    assert float(target_weights.iloc[-1]["SPY"]) == pytest.approx(0.8)


def test_combine_sleeve_weights_applies_strictest_overlap_cap() -> None:
    blueprint = PortfolioBlueprint(
        blueprint_id="bp",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="a",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.50"),
            ),
            SleeveRiskBudget(
                sleeve_id="b",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
        max_gross_exposure=Decimal("1.0"),
        max_net_exposure=Decimal("1.0"),
    )
    contributions = {
        "a": {"SPY": Decimal("0.8"), "IWM": Decimal("0.4")},
        "b": {"SPY": Decimal("0.6")},
    }
    result = _combine_sleeve_weights(blueprint=blueprint, contributions=contributions)
    assert result["SPY"] <= Decimal("0.50") + Decimal("1e-9")
    assert result["IWM"] <= Decimal("0.40") + Decimal("1e-9")


def test_combine_sleeve_weights_applies_row_gross_cap() -> None:
    blueprint = PortfolioBlueprint(
        blueprint_id="bp",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="a",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
        ),
        max_gross_exposure=Decimal("1.0"),
        max_net_exposure=Decimal("1.0"),
    )
    contributions = {
        "a": {"SPY": Decimal("0.6"), "QQQ": Decimal("0.6")},
    }
    result = _combine_sleeve_weights(blueprint=blueprint, contributions=contributions)
    gross = sum(abs(weight) for weight in result.values())
    assert abs(gross - Decimal("1.0")) < Decimal("1e-9")


def test_combine_sleeve_weights_applies_row_net_cap_when_gross_does_not_bind() -> None:
    blueprint = PortfolioBlueprint(
        blueprint_id="bp",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="a",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
        ),
        max_gross_exposure=Decimal("1.2"),
        max_net_exposure=Decimal("0.1"),
    )
    contributions = {
        "a": {"SPY": Decimal("0.6"), "HEDGE": Decimal("-0.4")},
    }
    result = _combine_sleeve_weights(blueprint=blueprint, contributions=contributions)
    net = abs(sum(result.values(), start=Decimal("0")))
    assert net <= Decimal("0.1") + Decimal("1e-9")
    gross = sum(abs(weight) for weight in result.values())
    assert gross <= Decimal("1.2") + Decimal("1e-9")
    ratio_raw = Decimal("0.6") / Decimal("0.4")
    ratio_scaled = abs(result["SPY"]) / abs(result["HEDGE"])
    assert abs(ratio_raw - ratio_scaled) < Decimal("1e-9")


def test_combine_sleeve_weights_is_pure() -> None:
    blueprint = PortfolioBlueprint(
        blueprint_id="bp",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="a",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="b",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    contributions = {
        "a": {"SPY": Decimal("0.4"), "QQQ": Decimal("0.2")},
        "b": {"SPY": Decimal("0.2")},
    }
    first = _combine_sleeve_weights(blueprint=blueprint, contributions=contributions)
    second = _combine_sleeve_weights(blueprint=blueprint, contributions=contributions)
    assert first == second


def test_output_dataframe_passes_backtest_validation() -> None:
    from tradingx.backtest import _validate_inputs  # type: ignore[attr-defined]

    spy_bars = _bars(300)
    qqq_bars = _bars(300, seed=17)
    regimes = _regimes(spy_bars)
    target_weights = build_portfolio_target_weight_history(
        (
            TrendSleeve(allowed_instruments=("SPY", "QQQ")),
            VolManagedBetaSleeve(),
        ),
        blueprint=_blueprint(),
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )
    _validate_inputs({"SPY": spy_bars, "QQQ": qqq_bars}, target_weights)


def test_simulate_portfolio_returns_delegates_to_run_daily_bar_backtest() -> None:
    from tradingx.backtest import run_daily_bar_backtest
    from tradingx.costs import CostModelConfig

    spy_bars = _bars(300)
    qqq_bars = _bars(300, seed=23)
    regimes = _regimes(spy_bars)
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    result = simulate_portfolio_returns(
        sleeves,
        blueprint=_blueprint(),
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )
    assert isinstance(result, PortfolioSimulationResult)

    combined = build_portfolio_target_weight_history(
        sleeves,
        blueprint=_blueprint(),
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )
    direct = run_daily_bar_backtest(
        {"SPY": spy_bars, "QQQ": qqq_bars},
        target_weights=combined,
        cost_model_config=CostModelConfig(),
    )

    assert list(result.backtest_result.portfolio_returns) == list(
        direct.portfolio_returns
    )
    assert (
        result.backtest_result.annualized_cost_drag_bps
        == direct.annualized_cost_drag_bps
    )
