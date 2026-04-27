"""Portfolio target-weight construction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.backtest import DailyBarBacktestResult, run_daily_bar_backtest
from tradingx.costs import CostModelConfig
from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    SleeveRiskBudget,
    StrategyAllocationLimit,
    resolve_blueprint_allocation_limits,
    validate_blueprint_allocation_limits,
)
from tradingx.sleeves.base import SleeveProtocol
from tradingx.sleeves.evaluation import build_sleeve_target_weight_history
from tradingx.types import RegimeSnapshot


@dataclass(frozen=True)
class PortfolioSimulationResult:
    backtest_result: DailyBarBacktestResult
    combined_target_weights: pd.DataFrame
    throttle_scale_series: pd.Series | None = None


def build_portfolio_target_weight_history(
    sleeves: tuple[SleeveProtocol, ...],
    *,
    blueprint: PortfolioBlueprint,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    allocation_limits: tuple[StrategyAllocationLimit, ...] | None = None,
) -> pd.DataFrame:
    if not sleeves:
        raise ValueError("sleeves must not be empty")
    effective_limits = resolve_blueprint_allocation_limits(
        blueprint,
        allocation_limits,
    )
    validate_blueprint_allocation_limits(
        blueprint,
        allocation_limits=effective_limits,
    )

    budget_by_sleeve = {
        sleeve_budget.sleeve_id: sleeve_budget
        for sleeve_budget in blueprint.sleeve_budgets
    }
    missing = tuple(
        sleeve.sleeve_id
        for sleeve in sleeves
        if sleeve.sleeve_id not in budget_by_sleeve
    )
    if missing:
        raise ValueError(f"sleeves {missing!r} missing from blueprint.sleeve_budgets")

    sleeve_frames: list[tuple[SleeveProtocol, SleeveRiskBudget, pd.DataFrame]] = []
    union_symbols: set[str] = set()
    for sleeve in sleeves:
        frame = build_sleeve_target_weight_history(
            sleeve,
            bars_by_symbol=bars_by_symbol,
            regime_snapshots_by_date=regime_snapshots_by_date,
            sleeve_budget_equity=Decimal("1.0"),
        )
        budget = budget_by_sleeve[sleeve.sleeve_id]
        sleeve_frames.append((sleeve, budget, frame))
        union_symbols.update(str(column) for column in frame.columns)

    reference_index = sleeve_frames[0][2].index
    columns = sorted(union_symbols)
    rows: list[dict[str, float]] = []
    for timestamp in reference_index:
        contributions: dict[str, dict[str, Decimal]] = {}
        for sleeve, _budget, frame in sleeve_frames:
            row = frame.loc[timestamp]
            contributions[sleeve.sleeve_id] = {
                str(symbol): Decimal(str(float(weight)))
                for symbol, weight in row.items()
                if float(weight) != 0.0
            }
        combined_row = _combine_sleeve_weights(
            blueprint=blueprint,
            contributions=contributions,
            allocation_limits=effective_limits,
        )
        rows.append(
            {
                symbol: float(combined_row.get(symbol, Decimal("0")))
                for symbol in columns
            }
        )
    return pd.DataFrame(rows, index=reference_index, columns=columns, dtype=float)


def simulate_portfolio_returns(
    sleeves: tuple[SleeveProtocol, ...],
    *,
    blueprint: PortfolioBlueprint,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    cost_model_config: CostModelConfig | None = None,
    allocation_limits: tuple[StrategyAllocationLimit, ...] | None = None,
) -> PortfolioSimulationResult:
    combined = build_portfolio_target_weight_history(
        sleeves,
        blueprint=blueprint,
        bars_by_symbol=bars_by_symbol,
        regime_snapshots_by_date=regime_snapshots_by_date,
        allocation_limits=allocation_limits,
    )
    traded_symbols = tuple(str(column) for column in combined.columns)
    result = run_daily_bar_backtest(
        {symbol: bars_by_symbol[symbol] for symbol in traded_symbols},
        target_weights=combined,
        cost_model_config=cost_model_config or CostModelConfig(),
    )
    return PortfolioSimulationResult(
        backtest_result=result,
        combined_target_weights=combined,
        throttle_scale_series=None,
    )


def _apply_symbol_overlap_caps(
    *,
    combined: pd.DataFrame,
    sleeve_frames: list[tuple[_ContributionSleeve, SleeveRiskBudget, pd.DataFrame]],
    blueprint: PortfolioBlueprint,
) -> None:
    holders_by_symbol: dict[str, list[SleeveRiskBudget]] = {}
    for _sleeve, budget, frame in sleeve_frames:
        for symbol in frame.columns:
            holders_by_symbol.setdefault(str(symbol), []).append(budget)

    for symbol, budgets in holders_by_symbol.items():
        if len(budgets) < 2:
            continue
        strictest_corr_cap = min(
            float(budget.max_correlation_with_other_sleeves) for budget in budgets
        )
        symbol_cap = float(blueprint.max_gross_exposure) * strictest_corr_cap
        over_cap = combined[symbol].abs() > symbol_cap
        if over_cap.any():
            combined.loc[over_cap, symbol] = combined.loc[over_cap, symbol].clip(
                lower=-symbol_cap,
                upper=symbol_cap,
            )


def _combine_sleeve_weights(
    *,
    blueprint: PortfolioBlueprint,
    contributions: dict[str, dict[str, Decimal]],
    allocation_limits: tuple[StrategyAllocationLimit, ...] | None = None,
) -> dict[str, Decimal]:
    effective_limits = resolve_blueprint_allocation_limits(
        blueprint,
        allocation_limits,
    )
    validate_blueprint_allocation_limits(
        blueprint,
        allocation_limits=effective_limits,
    )
    budget_by_sleeve = {
        sleeve_budget.sleeve_id: sleeve_budget
        for sleeve_budget in blueprint.sleeve_budgets
    }
    missing = tuple(
        sleeve_id for sleeve_id in contributions if sleeve_id not in budget_by_sleeve
    )
    if missing:
        raise ValueError(f"sleeves {missing!r} missing from blueprint.sleeve_budgets")

    union_symbols = sorted(
        {symbol for per_sleeve in contributions.values() for symbol in per_sleeve}
    )
    if not union_symbols:
        return {}

    combined = pd.DataFrame(0.0, index=[0], columns=union_symbols, dtype=float)
    sleeve_frames: list[tuple[_ContributionSleeve, SleeveRiskBudget, pd.DataFrame]] = []
    for sleeve_id in sorted(contributions):
        budget = budget_by_sleeve[sleeve_id]
        row = {
            symbol: float(weight) for symbol, weight in contributions[sleeve_id].items()
        }
        frame = pd.DataFrame(
            [row],
            index=[0],
            columns=union_symbols,
            dtype=float,
        ).fillna(0.0)
        sleeve_frames.append((_ContributionSleeve(sleeve_id=sleeve_id), budget, frame))
        combined = combined + frame * float(budget.budget_fraction_of_equity)

    _apply_symbol_overlap_caps(
        combined=combined,
        sleeve_frames=sleeve_frames,
        blueprint=blueprint,
    )
    combined = _apply_row_caps(combined=combined, blueprint=blueprint)
    row = combined.iloc[0]
    return {
        str(symbol): Decimal(str(float(weight)))
        for symbol, weight in row.items()
        if float(weight) != 0.0
    }


def _apply_row_caps(
    *,
    combined: pd.DataFrame,
    blueprint: PortfolioBlueprint,
) -> pd.DataFrame:
    result = combined.copy()
    gross = result.abs().sum(axis=1)
    max_gross = float(blueprint.max_gross_exposure)
    gross_over = gross > max_gross
    if gross_over.any():
        gross_scale = max_gross / gross.where(gross_over, 1.0)
        result.loc[gross_over, :] = result.loc[gross_over, :].multiply(
            gross_scale[gross_over],
            axis=0,
        )

    net = result.sum(axis=1).abs()
    max_net = float(blueprint.max_net_exposure)
    net_over = net > max_net
    if net_over.any():
        net_scale = max_net / net.where(net_over, 1.0)
        result.loc[net_over, :] = result.loc[net_over, :].multiply(
            net_scale[net_over],
            axis=0,
        )
    return result


@dataclass(frozen=True)
class _ContributionSleeve:
    sleeve_id: str
    family: str = "portfolio_composition"
    allowed_instruments: tuple[str, ...] = ()


__all__ = (
    "PortfolioSimulationResult",
    "_combine_sleeve_weights",
    "build_portfolio_target_weight_history",
    "simulate_portfolio_returns",
)
