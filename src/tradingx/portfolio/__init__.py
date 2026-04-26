"""Portfolio construction and drawdown defense package."""

from __future__ import annotations

from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    SleeveRiskBudget,
    StrategyAllocationLimit,
    resolve_blueprint_allocation_limits,
    validate_blueprint_allocation_limits,
)
from tradingx.portfolio.construction import (
    PortfolioSimulationResult,
    build_portfolio_target_weight_history,
    simulate_portfolio_returns,
)
from tradingx.portfolio.gateway import AlpacaPortfolioGateway
from tradingx.portfolio.hard_halt import (
    HALT_CATEGORY,
    HALT_REASON_PREFIX,
    PortfolioHardHaltController,
    is_portfolio_hard_halted,
)
from tradingx.portfolio.sleeve_runtime import (
    LiveDailyReturnsSourceProtocol,
    RollingWindowSource,
    SleeveRuntimeConfig,
    SleeveRuntimeController,
)
from tradingx.portfolio.throttle import (
    CDAR_SOFT_THROTTLE_FLOOR,
    MDD_DESIGN_THROTTLE_FLOOR,
    apply_cdar_soft_throttle,
    apply_mdd_design_throttle,
)

__all__ = (
    "CDAR_SOFT_THROTTLE_FLOOR",
    "HALT_CATEGORY",
    "HALT_REASON_PREFIX",
    "LiveDailyReturnsSourceProtocol",
    "MDD_DESIGN_THROTTLE_FLOOR",
    "AlpacaPortfolioGateway",
    "PortfolioBlueprint",
    "PortfolioHardHaltController",
    "PortfolioSimulationResult",
    "RollingWindowSource",
    "SleeveRiskBudget",
    "SleeveRuntimeConfig",
    "SleeveRuntimeController",
    "StrategyAllocationLimit",
    "apply_cdar_soft_throttle",
    "apply_mdd_design_throttle",
    "build_portfolio_target_weight_history",
    "is_portfolio_hard_halted",
    "resolve_blueprint_allocation_limits",
    "simulate_portfolio_returns",
    "validate_blueprint_allocation_limits",
)
