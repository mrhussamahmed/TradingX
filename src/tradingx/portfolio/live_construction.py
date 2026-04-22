"""Per-cycle live portfolio composition."""

from __future__ import annotations

from decimal import Decimal

from tradingx.portfolio.blueprint import PortfolioBlueprint
from tradingx.portfolio.construction import _combine_sleeve_weights
from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import SleeveContext, SleeveTargetWeights, SleeveTrade


def build_portfolio_cycle_target_weights(
    *,
    blueprint: PortfolioBlueprint,
    sleeves_by_id: dict[str, SleeveProtocol],
    context_by_sleeve_id: dict[str, SleeveContext],
) -> tuple[dict[str, Decimal], tuple[SleeveTargetWeights, ...]]:
    sleeve_trades_by_id = {
        sleeve_id: sleeve.plan_for_bar(context_by_sleeve_id[sleeve_id])
        for sleeve_id, sleeve in sleeves_by_id.items()
    }
    return _build_portfolio_cycle_target_weights_from_trades(
        blueprint=blueprint,
        sleeve_trades_by_id=sleeve_trades_by_id,
    )


def _build_portfolio_cycle_target_weights_from_trades(
    *,
    blueprint: PortfolioBlueprint,
    sleeve_trades_by_id: dict[str, tuple[SleeveTrade, ...]],
) -> tuple[dict[str, Decimal], tuple[SleeveTargetWeights, ...]]:
    budget_by_sleeve_id = {
        budget.sleeve_id: budget.budget_fraction_of_equity
        for budget in blueprint.sleeve_budgets
    }
    contributions: dict[str, dict[str, Decimal]] = {}
    for sleeve_id, trades in sleeve_trades_by_id.items():
        contributions[sleeve_id] = {
            trade.symbol: trade.target_weight_of_sleeve_budget
            for trade in trades
            if trade.target_weight_of_sleeve_budget > Decimal("0")
        }
    aggregate = _combine_sleeve_weights(
        blueprint=blueprint,
        contributions=contributions,
    )
    all_contributions_scaled = {
        sleeve_id: {
            symbol: raw_weight * budget_by_sleeve_id[sleeve_id]
            for symbol, raw_weight in sleeve_contributions.items()
        }
        for sleeve_id, sleeve_contributions in contributions.items()
    }

    decomposition_entries: list[SleeveTargetWeights] = []
    for sleeve_id in sorted(sleeve_trades_by_id):
        scaled = _rescale_to_aggregate(
            sleeve_contribution=all_contributions_scaled.get(sleeve_id, {}),
            all_contributions_scaled=all_contributions_scaled,
            aggregate=aggregate,
        )
        decomposition_entries.append(
            SleeveTargetWeights(
                sleeve_id=sleeve_id,
                target_weights_by_symbol=tuple(
                    sorted(
                        (symbol, weight)
                        for symbol, weight in scaled.items()
                        if weight > Decimal("0")
                    )
                ),
            )
        )

    return aggregate, tuple(decomposition_entries)


def _rescale_to_aggregate(
    *,
    sleeve_contribution: dict[str, Decimal],
    all_contributions_scaled: dict[str, dict[str, Decimal]],
    aggregate: dict[str, Decimal],
) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for symbol, sleeve_raw in sleeve_contribution.items():
        raw_sum = sum(
            (
                per_sleeve_map.get(symbol, Decimal("0"))
                for per_sleeve_map in all_contributions_scaled.values()
            ),
            start=Decimal("0"),
        )
        aggregate_weight = aggregate.get(symbol, Decimal("0"))
        if raw_sum <= Decimal("0"):
            result[symbol] = Decimal("0")
            continue
        scale = aggregate_weight / raw_sum
        result[symbol] = sleeve_raw * scale
    return result


__all__ = ("build_portfolio_cycle_target_weights",)
