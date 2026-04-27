from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from tradingx.features.regime import classify_regime
from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    SleeveRiskBudget,
    StrategyAllocationLimit,
)
from tradingx.portfolio.construction import build_portfolio_target_weight_history
from tradingx.portfolio.live_construction import (
    UnsupportedPortfolioCycleTargetWeights,
    build_portfolio_cycle_target_weights,
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
) -> dict[date, RegimeSnapshot]:
    closes = bars["close"].astype(float)
    sma_200 = closes.rolling(200).mean()
    regimes: dict[date, RegimeSnapshot] = {}
    for timestamp in bars.index:
        if pd.isna(sma_200.loc[timestamp]):
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


def _build_per_sleeve_contexts(
    sleeves,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    timestamp,
    position: int,
    running_weights_by_sleeve_id: dict[str, dict[str, Decimal]],
) -> dict[str, SleeveContext]:
    regime = regime_snapshots_by_date[timestamp.date()]
    return {
        sleeve.sleeve_id: SleeveContext(
            observation_date=timestamp.date(),
            bars_by_symbol={
                symbol: bars.iloc[: position + 1]
                for symbol, bars in bars_by_symbol.items()
            },
            regime=regime,
            current_weights_by_symbol=dict(
                running_weights_by_sleeve_id[sleeve.sleeve_id]
            ),
            sleeve_budget_equity=Decimal("1.0"),
        )
        for sleeve in sleeves
    }


def test_cycle_and_batch_parity_element_wise() -> None:
    spy_bars = _bars(400)
    qqq_bars = _bars(400, seed=11)
    bars_by_symbol = {"SPY": spy_bars, "QQQ": qqq_bars}
    regimes = _regimes(spy_bars)
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    batch_frame = build_portfolio_target_weight_history(
        sleeves,
        blueprint=_blueprint(),
        bars_by_symbol=bars_by_symbol,
        regime_snapshots_by_date=regimes,
    )

    running_weights_by_sleeve_id = {
        sleeve.sleeve_id: {
            symbol: Decimal("0") for symbol in sleeve.allowed_instruments
        }
        for sleeve in sleeves
    }
    cycle_rows: list[dict[str, float]] = []
    for position, timestamp in enumerate(batch_frame.index):
        if timestamp.date() not in regimes:
            cycle_rows.append(
                {
                    symbol: float(batch_frame.loc[timestamp, symbol])
                    for symbol in batch_frame.columns
                }
            )
            continue
        context_by_sleeve_id = _build_per_sleeve_contexts(
            sleeves,
            bars_by_symbol,
            regimes,
            timestamp,
            position,
            running_weights_by_sleeve_id,
        )
        aggregate, _decomposition = build_portfolio_cycle_target_weights(
            blueprint=_blueprint(),
            sleeves_by_id={sleeve.sleeve_id: sleeve for sleeve in sleeves},
            context_by_sleeve_id=context_by_sleeve_id,
        )
        cycle_rows.append(
            {symbol: float(weight) for symbol, weight in aggregate.items()}
        )

        for sleeve in sleeves:
            trades = sleeve.plan_for_bar(context_by_sleeve_id[sleeve.sleeve_id])
            for trade in trades:
                if trade.symbol in running_weights_by_sleeve_id[sleeve.sleeve_id]:
                    running_weights_by_sleeve_id[sleeve.sleeve_id][
                        trade.symbol
                    ] = trade.target_weight_of_sleeve_budget

    cycle_frame = pd.DataFrame(cycle_rows, index=batch_frame.index).fillna(0.0)
    cycle_frame = cycle_frame.reindex(columns=batch_frame.columns, fill_value=0.0)

    for column in batch_frame.columns:
        assert (batch_frame[column] - cycle_frame[column]).abs().max() < 1e-9


def test_cycle_returns_decomposition_per_sleeve() -> None:
    spy_bars = _bars(260)
    regimes = _regimes(spy_bars)
    timestamp = next(ts for ts in spy_bars.index if ts.date() in regimes)
    position = spy_bars.index.get_loc(timestamp)
    sleeves = {
        "trend-following-v1": TrendSleeve(allowed_instruments=("SPY",)),
        "vol-target-v1": VolManagedBetaSleeve(),
    }
    context_by_sleeve_id = {
        "trend-following-v1": SleeveContext(
            observation_date=timestamp.date(),
            bars_by_symbol={"SPY": spy_bars.iloc[: position + 1]},
            regime=regimes[timestamp.date()],
            current_weights_by_symbol={"SPY": Decimal("0")},
            sleeve_budget_equity=Decimal("1.0"),
        ),
        "vol-target-v1": SleeveContext(
            observation_date=timestamp.date(),
            bars_by_symbol={"SPY": spy_bars.iloc[: position + 1]},
            regime=regimes[timestamp.date()],
            current_weights_by_symbol={"SPY": Decimal("0")},
            sleeve_budget_equity=Decimal("1.0"),
        ),
    }
    _aggregate, decomposition = build_portfolio_cycle_target_weights(
        blueprint=_blueprint(),
        sleeves_by_id=sleeves,
        context_by_sleeve_id=context_by_sleeve_id,
    )
    sleeve_ids = {entry.sleeve_id for entry in decomposition}
    assert sleeve_ids == {"trend-following-v1", "vol-target-v1"}


def test_cycle_aggregate_equals_sum_of_decomposition_within_tolerance() -> None:
    spy_bars = _bars(260)
    regimes = _regimes(spy_bars)
    timestamp = next(ts for ts in spy_bars.index if ts.date() in regimes)
    position = spy_bars.index.get_loc(timestamp)
    sleeves = {
        "trend-following-v1": TrendSleeve(allowed_instruments=("SPY",)),
        "vol-target-v1": VolManagedBetaSleeve(),
    }
    context_by_sleeve_id = {
        "trend-following-v1": SleeveContext(
            observation_date=timestamp.date(),
            bars_by_symbol={"SPY": spy_bars.iloc[: position + 1]},
            regime=regimes[timestamp.date()],
            current_weights_by_symbol={"SPY": Decimal("0")},
            sleeve_budget_equity=Decimal("1.0"),
        ),
        "vol-target-v1": SleeveContext(
            observation_date=timestamp.date(),
            bars_by_symbol={"SPY": spy_bars.iloc[: position + 1]},
            regime=regimes[timestamp.date()],
            current_weights_by_symbol={"SPY": Decimal("0")},
            sleeve_budget_equity=Decimal("1.0"),
        ),
    }
    aggregate, decomposition = build_portfolio_cycle_target_weights(
        blueprint=_blueprint(),
        sleeves_by_id=sleeves,
        context_by_sleeve_id=context_by_sleeve_id,
    )
    for symbol, weight in aggregate.items():
        decomposition_sum = sum(
            (
                dict(entry.target_weights_by_symbol).get(symbol, Decimal("0"))
                for entry in decomposition
            ),
            start=Decimal("0"),
        )
        assert abs(weight - decomposition_sum) < Decimal("1e-9")


def test_negative_sleeve_target_fails_before_aggregation() -> None:
    from tradingx.portfolio.live_construction import (
        _build_portfolio_cycle_target_weights_from_trades,
    )

    blueprint = PortfolioBlueprint(
        blueprint_id="bp-short",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="mean-reversion-v1",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )

    with pytest.raises(
        UnsupportedPortfolioCycleTargetWeights,
        match="unsupported_side",
    ):
        _build_portfolio_cycle_target_weights_from_trades(
            blueprint=blueprint,
            sleeve_trades_by_id={
                "mean-reversion-v1": (
                    SleeveTrade(
                        sleeve_id="mean-reversion-v1",
                        symbol="SPY",
                        side="sell_short",
                        target_weight_of_sleeve_budget=Decimal("-0.25"),
                        rationale="short_signal",
                        regime="risk_on",
                    ),
                )
            },
        )


def test_live_cycle_uses_blueprint_allocation_limits() -> None:
    from tradingx.portfolio.live_construction import (
        _build_portfolio_cycle_target_weights_from_trades,
    )

    blueprint = PortfolioBlueprint(
        blueprint_id="bp-limited",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.10"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
        strategy_allocation_limits=(
            StrategyAllocationLimit(
                strategy_id="trend-following-v1",
                max_strategy_allocation=Decimal("0.05"),
            ),
        ),
    )

    with pytest.raises(ValueError, match="allocation_policy_limit_exceeded"):
        _build_portfolio_cycle_target_weights_from_trades(
            blueprint=blueprint,
            sleeve_trades_by_id={
                "trend-following-v1": (
                    SleeveTrade(
                        sleeve_id="trend-following-v1",
                        symbol="SPY",
                        side="buy",
                        target_weight_of_sleeve_budget=Decimal("0.5"),
                        rationale="long_signal",
                        regime="risk_on",
                    ),
                )
            },
        )
