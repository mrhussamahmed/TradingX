"""Portfolio-level blueprint primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class SleeveRiskBudget:
    sleeve_id: str
    budget_fraction_of_equity: Decimal
    max_correlation_with_other_sleeves: Decimal
    strategy_id: str | None = None


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


def effective_strategy_id(budget: SleeveRiskBudget) -> str:
    return budget.strategy_id or budget.sleeve_id


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
    return _portfolio_blueprint_from_payload(payload)


def _portfolio_blueprint_from_payload(payload: dict[str, object]) -> PortfolioBlueprint:
    sleeve_budgets_payload = payload.get("sleeve_budgets")
    if not isinstance(sleeve_budgets_payload, list):
        raise ValueError("sleeve_budgets must be a list.")
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
    "effective_strategy_id",
    "load_portfolio_blueprint",
    "resolve_portfolio_blueprint_path",
)
