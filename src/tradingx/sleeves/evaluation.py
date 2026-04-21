"""Sleeve-to-backtest evaluation bridge."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.backtest import run_daily_bar_backtest
from tradingx.costs import CostModelConfig
from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import RegimeSnapshot, SleeveContext


def build_sleeve_target_weight_history(
    sleeve: SleeveProtocol,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    sleeve_budget_equity: Decimal,
) -> pd.DataFrame:
    if not bars_by_symbol:
        raise ValueError("bars_by_symbol must not be empty.")

    index_symbol = next(iter(bars_by_symbol))
    bar_index = bars_by_symbol[index_symbol].index
    allowed = tuple(sleeve.allowed_instruments)
    running_weights: dict[str, Decimal] = {symbol: Decimal("0") for symbol in allowed}
    rows: list[dict[str, float]] = []

    for position, timestamp in enumerate(bar_index):
        regime = regime_snapshots_by_date.get(timestamp.date())
        if regime is None:
            rows.append(
                {symbol: float(weight) for symbol, weight in running_weights.items()}
            )
            continue

        context = SleeveContext(
            observation_date=timestamp.date(),
            bars_by_symbol={
                symbol: bars.iloc[: position + 1]
                for symbol, bars in bars_by_symbol.items()
            },
            regime=regime,
            current_weights_by_symbol=dict(running_weights),
            sleeve_budget_equity=sleeve_budget_equity,
        )
        trades = sleeve.plan_for_bar(context)
        for trade in trades:
            if trade.symbol not in allowed:
                continue
            running_weights[trade.symbol] = trade.target_weight_of_sleeve_budget
        rows.append(
            {symbol: float(weight) for symbol, weight in running_weights.items()}
        )

    return pd.DataFrame(rows, index=bar_index, columns=list(allowed), dtype=float)


def simulate_sleeve_returns(
    sleeve: SleeveProtocol,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    sleeve_budget_equity: Decimal,
    cost_model_config: CostModelConfig | None = None,
) -> tuple[tuple[Decimal, ...], Decimal]:
    target_weights = build_sleeve_target_weight_history(
        sleeve,
        bars_by_symbol=bars_by_symbol,
        regime_snapshots_by_date=regime_snapshots_by_date,
        sleeve_budget_equity=sleeve_budget_equity,
    )
    traded_symbols = tuple(str(symbol) for symbol in target_weights.columns)
    resolved_cost_config = cost_model_config or CostModelConfig()
    result = run_daily_bar_backtest(
        {symbol: bars_by_symbol[symbol] for symbol in traded_symbols},
        target_weights=target_weights,
        cost_model_config=resolved_cost_config,
    )
    returns = tuple(Decimal(str(value)) for value in result.portfolio_returns.tolist())
    return returns, result.annualized_cost_drag_bps


__all__ = ("build_sleeve_target_weight_history", "simulate_sleeve_returns")
