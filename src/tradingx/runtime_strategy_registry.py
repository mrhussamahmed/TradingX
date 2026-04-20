from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from tradingx.activation import LocalActivationGateway
from tradingx.baseline_runtime_planner import (
    BaselineLongOnlyPlanner,
    MarketDataGatewayProtocol,
    OpportunitySelectorProtocol,
)
from tradingx.runtime_portfolio import RuntimePortfolioPlan, RuntimePortfolioPlanner
from tradingx.types import PortfolioState


class RuntimeStrategyResolver(Protocol):
    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
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
    ) -> None:
        self._activation_gateway = activation_gateway
        self._registry = registry
        self.last_strategy_id = ""

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan | None:
        activation, _snapshot = self._activation_gateway.load_or_create_active_records(
            symbols
        )
        self.last_strategy_id = activation.strategy_id
        runtime_symbols = activation.approved_symbols or symbols
        resolver = self._registry.resolve(activation.strategy_id)
        if resolver is None:
            return None
        return resolver.plan_for_service(
            symbols=runtime_symbols,
            portfolio_state=portfolio_state,
            default_quantity=default_quantity,
        )


def build_default_runtime_registry(
    *,
    market_data_gateway: MarketDataGatewayProtocol,
    baseline_selector: OpportunitySelectorProtocol | None = None,
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
            ),
        )
    return registry


__all__ = (
    "ActivatedRuntimePlanner",
    "RuntimeStrategyRegistry",
    "RuntimeStrategyResolver",
    "build_default_runtime_registry",
)
