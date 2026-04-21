from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget


def _sleeve(sleeve_id: str, budget: str, corr: str = "0.85") -> SleeveRiskBudget:
    return SleeveRiskBudget(
        sleeve_id=sleeve_id,
        budget_fraction_of_equity=Decimal(budget),
        max_correlation_with_other_sleeves=Decimal(corr),
    )


def test_blueprint_accepts_budgets_summing_to_one() -> None:
    blueprint = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(_sleeve("a", "0.5"), _sleeve("b", "0.5")),
    )
    assert sum(
        (item.budget_fraction_of_equity for item in blueprint.sleeve_budgets),
        Decimal("0"),
    ) == Decimal("1")


def test_blueprint_accepts_budgets_summing_below_one() -> None:
    blueprint = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(_sleeve("a", "0.4"), _sleeve("b", "0.4")),
    )
    total = sum(
        (item.budget_fraction_of_equity for item in blueprint.sleeve_budgets),
        Decimal("0"),
    )
    assert total == Decimal("0.8")


def test_blueprint_rejects_budgets_summing_above_one() -> None:
    with pytest.raises(ValueError, match="sleeve budgets sum to"):
        PortfolioBlueprint(
            blueprint_id="bp-1",
            sleeve_budgets=(_sleeve("a", "0.6"), _sleeve("b", "0.6")),
        )


def test_blueprint_defaults_match_adr_0021() -> None:
    blueprint = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(_sleeve("a", "1.0"),),
    )
    assert blueprint.mdd_design_target == Decimal("0.15")
    assert blueprint.mdd_hard_halt == Decimal("0.25")
    assert blueprint.cdar_confidence == Decimal("0.95")
    assert blueprint.cdar_soft_throttle_threshold == Decimal("0.08")
    assert blueprint.annualized_turnover_budget == Decimal("3.0")


def test_blueprint_is_frozen() -> None:
    blueprint = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(_sleeve("a", "0.5"), _sleeve("b", "0.5")),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        blueprint.blueprint_id = "bp-2"  # type: ignore[misc]
