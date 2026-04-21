"""Portfolio-level blueprint primitives."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SleeveRiskBudget:
    sleeve_id: str
    budget_fraction_of_equity: Decimal
    max_correlation_with_other_sleeves: Decimal


@dataclass(frozen=True)
class PortfolioBlueprint:
    blueprint_id: str
    sleeve_budgets: tuple[SleeveRiskBudget, ...]
    max_gross_exposure: Decimal = Decimal("1.0")
    max_net_exposure: Decimal = Decimal("1.0")
    mdd_design_target: Decimal = Decimal("0.15")
    mdd_hard_halt: Decimal = Decimal("0.25")
    cdar_confidence: Decimal = Decimal("0.95")
    cdar_soft_throttle_threshold: Decimal = Decimal("0.08")
    annualized_turnover_budget: Decimal = Decimal("3.0")
    sleeve_three_month_sharpe_floor: Decimal = Decimal("0.0")

    def __post_init__(self) -> None:
        total_budget = sum(
            (
                sleeve_budget.budget_fraction_of_equity
                for sleeve_budget in self.sleeve_budgets
            ),
            start=Decimal("0"),
        )
        if total_budget > Decimal("1.0"):
            raise ValueError(f"sleeve budgets sum to {total_budget}, must be <= 1.0")


__all__ = ("PortfolioBlueprint", "SleeveRiskBudget")
