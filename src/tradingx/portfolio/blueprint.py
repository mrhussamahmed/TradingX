"""Portfolio-level blueprint primitives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from tradingx.types import (
    BlueprintActivationRecord,
    PortfolioBlueprintSleeveSummary,
    PortfolioBlueprintSummary,
)


@dataclass(frozen=True)
class SleeveRiskBudget:
    sleeve_id: str
    budget_fraction_of_equity: Decimal
    max_correlation_with_other_sleeves: Decimal
    strategy_id: str | None = None


@dataclass(frozen=True)
class StrategyAllocationLimit:
    strategy_id: str
    max_strategy_allocation: Decimal


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
    strategy_allocation_limits: tuple[StrategyAllocationLimit, ...] = ()

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


def effective_strategy_id(budget: SleeveRiskBudget) -> str:
    return budget.strategy_id or budget.sleeve_id


def validate_blueprint_allocation_limits(
    blueprint: PortfolioBlueprint,
    *,
    allocation_limits: tuple[StrategyAllocationLimit, ...],
) -> None:
    if not allocation_limits:
        return
    limit_by_strategy = {
        limit.strategy_id: limit.max_strategy_allocation for limit in allocation_limits
    }
    budget_by_strategy: dict[str, Decimal] = {}
    for budget in blueprint.sleeve_budgets:
        strategy_id = effective_strategy_id(budget)
        budget_by_strategy[strategy_id] = (
            budget_by_strategy.get(strategy_id, Decimal("0"))
            + budget.budget_fraction_of_equity
        )
    for strategy_id, budget_fraction in budget_by_strategy.items():
        limit = limit_by_strategy.get(strategy_id)
        if limit is not None and budget_fraction > limit:
            raise ValueError(
                "allocation_policy_limit_exceeded: "
                f"{strategy_id} blueprint budget {budget_fraction} exceeds {limit}"
            )


def resolve_blueprint_allocation_limits(
    blueprint: PortfolioBlueprint,
    allocation_limits: tuple[StrategyAllocationLimit, ...] | None,
) -> tuple[StrategyAllocationLimit, ...]:
    if allocation_limits is not None:
        return allocation_limits
    return blueprint.strategy_allocation_limits


def resolve_portfolio_blueprint_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / path


def load_portfolio_blueprint(path: Path) -> PortfolioBlueprint:
    resolved = resolve_portfolio_blueprint_path(path)
    raw_text = resolved.read_text(encoding="utf-8")
    stripped = raw_text.lstrip()
    if stripped.startswith("{"):
        payload = json.loads(raw_text)
    else:
        payload = _parse_blueprint_yaml(raw_text, path=resolved)
    return portfolio_blueprint_from_payload(payload)


def portfolio_blueprint_from_payload(payload: dict[str, object]) -> PortfolioBlueprint:
    return _portfolio_blueprint_from_payload(payload)


def portfolio_blueprint_to_payload(blueprint: PortfolioBlueprint) -> dict[str, object]:
    return {
        "blueprint_id": blueprint.blueprint_id,
        "sleeve_budgets": [
            {
                "sleeve_id": budget.sleeve_id,
                "strategy_id": budget.strategy_id,
                "budget_fraction_of_equity": str(budget.budget_fraction_of_equity),
                "max_correlation_with_other_sleeves": str(
                    budget.max_correlation_with_other_sleeves
                ),
            }
            for budget in blueprint.sleeve_budgets
        ],
        "max_gross_exposure": str(blueprint.max_gross_exposure),
        "max_net_exposure": str(blueprint.max_net_exposure),
        "mdd_design_target": str(blueprint.mdd_design_target),
        "mdd_hard_halt": str(blueprint.mdd_hard_halt),
        "cdar_confidence": str(blueprint.cdar_confidence),
        "cdar_soft_throttle_threshold": str(
            blueprint.cdar_soft_throttle_threshold
        ),
        "annualized_turnover_budget": str(blueprint.annualized_turnover_budget),
        "sleeve_three_month_sharpe_floor": str(
            blueprint.sleeve_three_month_sharpe_floor
        ),
        "strategy_allocation_limits": [
            {
                "strategy_id": limit.strategy_id,
                "max_strategy_allocation": str(limit.max_strategy_allocation),
            }
            for limit in blueprint.strategy_allocation_limits
        ],
    }


def portfolio_blueprint_content_hash(blueprint: PortfolioBlueprint) -> str:
    payload = portfolio_blueprint_to_payload(blueprint)
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def portfolio_blueprint_from_activation(
    activation: BlueprintActivationRecord,
) -> PortfolioBlueprint:
    if activation.blueprint_payload is not None:
        return portfolio_blueprint_from_payload(activation.blueprint_payload)
    return load_portfolio_blueprint(activation.source_blueprint_path)


def list_portfolio_blueprints(root: Path) -> tuple[PortfolioBlueprintSummary, ...]:
    if not root.exists():
        return ()
    rows: list[PortfolioBlueprintSummary] = []
    for path in sorted((*root.glob("*.yaml"), *root.glob("*.json"))):
        try:
            blueprint = load_portfolio_blueprint(path)
        except Exception as exc:
            rows.append(
                PortfolioBlueprintSummary(
                    blueprint_id=path.stem,
                    source_path=path,
                    sleeve_budgets=(),
                    max_gross_exposure=Decimal("0"),
                    max_net_exposure=Decimal("0"),
                    status="invalid",
                    detail=str(exc),
                )
            )
            continue
        rows.append(
            PortfolioBlueprintSummary(
                blueprint_id=blueprint.blueprint_id,
                source_path=path,
                sleeve_budgets=tuple(
                    PortfolioBlueprintSleeveSummary(
                        sleeve_id=budget.sleeve_id,
                        strategy_id=effective_strategy_id(budget),
                        budget_fraction_of_equity=budget.budget_fraction_of_equity,
                        max_correlation_with_other_sleeves=budget.max_correlation_with_other_sleeves,
                    )
                    for budget in blueprint.sleeve_budgets
                ),
                max_gross_exposure=blueprint.max_gross_exposure,
                max_net_exposure=blueprint.max_net_exposure,
            )
        )
    return tuple(rows)


def _portfolio_blueprint_from_payload(payload: dict[str, object]) -> PortfolioBlueprint:
    sleeve_budgets_payload = payload.get("sleeve_budgets")
    if not isinstance(sleeve_budgets_payload, list):
        raise ValueError("sleeve_budgets must be a list.")
    allocation_limits_payload = payload.get("strategy_allocation_limits", [])
    if not isinstance(allocation_limits_payload, list):
        raise ValueError("strategy_allocation_limits must be a list.")
    return PortfolioBlueprint(
        blueprint_id=str(payload["blueprint_id"]),
        sleeve_budgets=tuple(
            SleeveRiskBudget(
                sleeve_id=str(item["sleeve_id"]),
                budget_fraction_of_equity=Decimal(
                    str(item["budget_fraction_of_equity"])
                ),
                max_correlation_with_other_sleeves=Decimal(
                    str(item["max_correlation_with_other_sleeves"])
                ),
                strategy_id=(
                    None
                    if item.get("strategy_id") in {None, ""}
                    else str(item["strategy_id"])
                ),
            )
            for item in sleeve_budgets_payload
            if isinstance(item, dict)
        ),
        max_gross_exposure=Decimal(str(payload.get("max_gross_exposure", "1.0"))),
        max_net_exposure=Decimal(str(payload.get("max_net_exposure", "1.0"))),
        mdd_design_target=Decimal(str(payload.get("mdd_design_target", "0.15"))),
        mdd_hard_halt=Decimal(str(payload.get("mdd_hard_halt", "0.25"))),
        cdar_confidence=Decimal(str(payload.get("cdar_confidence", "0.95"))),
        cdar_soft_throttle_threshold=Decimal(
            str(payload.get("cdar_soft_throttle_threshold", "0.08"))
        ),
        annualized_turnover_budget=Decimal(
            str(payload.get("annualized_turnover_budget", "3.0"))
        ),
        sleeve_three_month_sharpe_floor=Decimal(
            str(payload.get("sleeve_three_month_sharpe_floor", "0.0"))
        ),
        strategy_allocation_limits=tuple(
            StrategyAllocationLimit(
                strategy_id=str(item["strategy_id"]),
                max_strategy_allocation=Decimal(str(item["max_strategy_allocation"])),
            )
            for item in allocation_limits_payload
            if isinstance(item, dict)
        ),
    )


def _parse_blueprint_yaml(text: str, *, path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    current_list_key: str | None = None
    current_item: dict[str, object] | None = None
    list_items: list[dict[str, object]] | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line.startswith(" "):
            current_item = None
            if line.endswith(":"):
                current_list_key = stripped[:-1]
                list_items = []
                result[current_list_key] = list_items
                continue
            key, value = _split_key_value(line, path=path)
            result[key] = value
            current_list_key = None
            list_items = None
            continue
        if current_list_key is None or list_items is None:
            raise ValueError(f"Unexpected indented line in {path}: {raw_line}")
        if stripped.startswith("- "):
            current_item = {}
            list_items.append(current_item)
            item_line = stripped[2:].strip()
            if item_line:
                key, value = _split_key_value(item_line, path=path)
                current_item[key] = value
            continue
        if current_item is None:
            raise ValueError(f"Unexpected nested mapping in {path}: {raw_line}")
        key, value = _split_key_value(stripped, path=path)
        current_item[key] = value

    return result


def _split_key_value(line: str, *, path: Path) -> tuple[str, str]:
    key, separator, value = line.partition(":")
    if not separator:
        raise ValueError(f"Malformed YAML line in {path}: {line}")
    return key.strip(), value.strip()


__all__ = (
    "PortfolioBlueprint",
    "SleeveRiskBudget",
    "StrategyAllocationLimit",
    "effective_strategy_id",
    "load_portfolio_blueprint",
    "resolve_portfolio_blueprint_path",
    "resolve_blueprint_allocation_limits",
    "validate_blueprint_allocation_limits",
)
