from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from tradingx.activation import LocalActivationGateway
from tradingx.baseline_runtime_planner import (
    BaselineLongOnlyPlanner,
    OpportunitySelectorProtocol,
)
from tradingx.runtime_portfolio import (
    MarketDataGatewayProtocol,
    RuntimePortfolioPlan,
    RuntimePortfolioPlanner,
)
from tradingx.sizing import RuntimeSizingPolicy
from tradingx.types import BlueprintActivationRecord, PortfolioState


class RuntimeStrategyResolver(Protocol):
    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> RuntimePortfolioPlan | None: ...


class RuntimeStrategyRegistry:
    def __init__(self) -> None:
        self._resolvers: dict[str, RuntimeStrategyResolver] = {}

    def register(self, strategy_id: str, resolver: RuntimeStrategyResolver) -> None:
        self._resolvers[strategy_id] = resolver

    def resolve(self, strategy_id: str) -> RuntimeStrategyResolver | None:
        return self._resolvers.get(strategy_id)

    def can_resolve(self, strategy_id: str) -> bool:
        return self.resolve(strategy_id) is not None


class ActivatedRuntimePlanner:
    def __init__(
        self,
        *,
        activation_gateway: LocalActivationGateway,
        registry: RuntimeStrategyRegistry,
        blueprint_planner: RuntimePortfolioPlanner | None = None,
    ) -> None:
        self._activation_gateway = activation_gateway
        self._registry = registry
        self._blueprint_planner = blueprint_planner
        self._applied_blueprint_activation = (
            activation_gateway.get_active_blueprint_activation()
        )
        self.last_strategy_id = ""

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> RuntimePortfolioPlan | None:
        active_blueprint = self._applied_blueprint_activation
        if self._blueprint_planner is not None and active_blueprint is not None:
            self.last_strategy_id = active_blueprint.blueprint_id
            return self._blueprint_planner.plan_for_service(
                symbols=symbols,
                portfolio_state=portfolio_state,
                default_quantity=default_quantity,
                sizing_policy=sizing_policy,
            )
        activation, _snapshot = self._activation_gateway.load_or_create_active_records(
            symbols
        )
        self.last_strategy_id = activation.strategy_id
        runtime_symbols = activation.approved_symbols or symbols
        resolver = self._registry.resolve(activation.strategy_id)
        if resolver is None:
            return None
        if sizing_policy is None:
            return resolver.plan_for_service(
                symbols=runtime_symbols,
                portfolio_state=portfolio_state,
                default_quantity=default_quantity,
            )
        return resolver.plan_for_service(
            symbols=runtime_symbols,
            portfolio_state=portfolio_state,
            default_quantity=default_quantity,
            sizing_policy=sizing_policy,
        )

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        return self._activation_gateway.get_active_blueprint_activation()

    def supersede_active_blueprint(
        self,
        *,
        new_activation: BlueprintActivationRecord,
        now: datetime,
    ) -> BlueprintActivationRecord:
        return self._activation_gateway.supersede_active_blueprint(
            new_activation=new_activation,
            now=now,
        )


def build_default_runtime_registry(
    *,
    market_data_gateway: MarketDataGatewayProtocol,
    baseline_selector: OpportunitySelectorProtocol | None = None,
    vix_cache_path: Path | None = None,
    treasury_cache_path: Path | None = None,
) -> RuntimeStrategyRegistry:
    registry = RuntimeStrategyRegistry()
    registry.register(
        "baseline-long-only-v1",
        BaselineLongOnlyPlanner(
            market_data=market_data_gateway,
            selector=baseline_selector,
        ),
    )
    for strategy_id in (
        "trend-following-v1",
        "vol-target-v1",
        "mean-reversion-v1",
    ):
        registry.register(
            strategy_id,
            RuntimePortfolioPlanner(
                market_data=market_data_gateway,
                strategy_id=strategy_id,
                vix_cache_path=vix_cache_path,
                treasury_cache_path=treasury_cache_path,
            ),
        )
    return registry


__all__ = (
    "ActivatedRuntimePlanner",
    "RuntimeStrategyRegistry",
    "RuntimeStrategyResolver",
    "build_default_runtime_registry",
)
