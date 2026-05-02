from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Protocol, cast

import pandas as pd  # type: ignore[import-untyped]

from tradingx.drift.sleeve_ledger import RESIDUAL_RESERVE_OWNER_ID
from tradingx.features.regime import classify_regime
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    StrategyAllocationLimit,
    portfolio_blueprint_from_activation,
)
from tradingx.portfolio.live_construction import build_portfolio_cycle_target_weights
from tradingx.portfolio.sleeve_runtime import (
    DriftAlarmGatewayProtocol,
    LiveDailyReturnsSourceProtocol,
    SleeveOperatorHaltStoreProtocol,
    SleeveRuntimeConfig,
    SleeveRuntimeController,
    TrialsLedgerReadProtocol,
)
from tradingx.portfolio_construction import (
    CandidateRuntimeWeights,
    build_candidate_runtime_weights,
)
from tradingx.risk_free import (
    DEFAULT_TREASURY_YIELD_CACHE_PATH,
    DEFAULT_VIX_CACHE_PATH,
    vix_close_for_date,
    yield_curve_spread_for_date_pit,
)
from tradingx.sizing import (
    RuntimeSizingPolicy,
    build_runtime_sizing_budget,
    cap_entry_quantity,
    entry_marketable_limit_price,
)
from tradingx.sleeves.base import SleeveProtocol, build_sleeve_from_candidate
from tradingx.strategy import build_runtime_candidate_registry
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    MarketSnapshot,
    PortfolioState,
    RegimeSnapshot,
    SleeveContext,
    SleeveFailureReason,
    SleeveTargetWeights,
    SleeveTrade,
    StrategyActivationRecord,
    StrategyCandidate,
    TradeIntent,
)

HISTORY_LOOKBACK_DAYS = 1200


class UnsupportedRuntimePortfolioPlanError(ValueError):
    """Raised when an activated research strategy cannot be executed safely."""


class MarketDataGatewayProtocol(Protocol):
    def get_daily_bar_history(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> Any: ...

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot: ...


class ActivationGatewayProtocol(Protocol):
    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ApprovedWeightSnapshot]: ...

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None: ...

    def get_strategy_allocation_limits(
        self,
        blueprint: PortfolioBlueprint,
    ) -> tuple[StrategyAllocationLimit, ...]: ...


@dataclass(frozen=True)
class RuntimePortfolioTrade:
    symbol: str
    side: str
    reason_code: str
    last_trade_price: Decimal
    current_weight: Decimal
    target_weight: Decimal
    current_quantity: Decimal
    target_quantity: Decimal
    delta_quantity: Decimal
    no_trade_band_applied: bool


@dataclass(frozen=True)
class RuntimePortfolioPlan:
    plan_id: str
    generated_at_utc: datetime
    strategy_id: str
    universe_snapshot_id: str
    benchmark_symbol: str
    crash_overlay_active: bool
    symbols_considered: tuple[str, ...]
    current_weights: dict[str, Decimal]
    target_weights: dict[str, Decimal]
    trade_intents: tuple[TradeIntent, ...]
    planned_trades: tuple[RuntimePortfolioTrade, ...]
    market_snapshots: dict[str, MarketSnapshot]
    per_sleeve_target_weights: tuple[SleeveTargetWeights, ...] = ()
    sleeve_failure_reasons: tuple[tuple[str, str], ...] = ()


class RuntimePortfolioPlanner:
    def __init__(
        self,
        *,
        market_data: MarketDataGatewayProtocol,
        activation_gateway: ActivationGatewayProtocol | None = None,
        strategy_id: str | None = None,
        artifact_store: FilesystemArtifactStore | None = None,
        runtime_state_store: FilesystemArtifactStore | None = None,
        operator_halt_store: SleeveOperatorHaltStoreProtocol | None = None,
        drift_alarm_gateway: DriftAlarmGatewayProtocol | None = None,
        trials_ledger: TrialsLedgerReadProtocol | None = None,
        live_daily_returns_source: LiveDailyReturnsSourceProtocol | None = None,
        vix_cache_path: Path | None = None,
        treasury_cache_path: Path | None = None,
        history_lookback_days: int = HISTORY_LOOKBACK_DAYS,
        now_provider: Callable[[], datetime] | None = None,
        applied_blueprint_activation: BlueprintActivationRecord | None = None,
    ) -> None:
        self._market_data = market_data
        self._activation_gateway = activation_gateway
        self._strategy_id = strategy_id
        self._artifact_store = artifact_store
        self._runtime_state_store = runtime_state_store or artifact_store
        self._operator_halt_store = operator_halt_store
        self._drift_alarm_gateway = drift_alarm_gateway
        self._trials_ledger = trials_ledger
        self._live_daily_returns_source = live_daily_returns_source
        self._vix_cache_path = vix_cache_path or DEFAULT_VIX_CACHE_PATH
        self._treasury_cache_path = (
            treasury_cache_path or DEFAULT_TREASURY_YIELD_CACHE_PATH
        )
        self._history_lookback_days = history_lookback_days
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._applied_blueprint_activation = applied_blueprint_activation

    def set_run_scoped_blueprint_activation(
        self,
        activation: BlueprintActivationRecord | None,
    ) -> None:
        self._applied_blueprint_activation = activation

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        if self._applied_blueprint_activation is not None:
            return self._applied_blueprint_activation
        if self._activation_gateway is None:
            return None
        return self._activation_gateway.get_active_blueprint_activation()

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal = Decimal("0"),
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> RuntimePortfolioPlan | None:
        del default_quantity
        blueprint_activation = self._applied_blueprint_activation
        if blueprint_activation is None and self._activation_gateway is not None:
            blueprint_activation = (
                self._activation_gateway.get_active_blueprint_activation()
            )
        if blueprint_activation is not None:
            return self._plan_for_blueprint(
                blueprint_activation=blueprint_activation,
                symbols=symbols,
                portfolio_state=portfolio_state,
                sizing_policy=sizing_policy,
            )

        runtime_symbols = symbols
        strategy_id = self._strategy_id
        if self._activation_gateway is not None:
            activation, _snapshot = (
                self._activation_gateway.load_or_create_active_records(symbols)
            )
            runtime_symbols = activation.approved_symbols or symbols
            strategy_id = activation.strategy_id
        if strategy_id is None:
            return None
        generated_at = self._now_provider()
        candidate = self._candidate_for_strategy(
            strategy_id=strategy_id,
            symbols=runtime_symbols,
        )
        if candidate is None:
            return None
        if candidate.status == "reference":
            return None

        bars_by_symbol = self._load_bars(
            symbols=tuple(
                sorted(
                    {candidate.benchmark_symbol, *candidate.universe}
                    | {
                        position.symbol
                        for position in portfolio_state.positions
                        if position.quantity != Decimal("0")
                    }
                )
            )
        )
        current_weights = _current_weights(portfolio_state)
        runtime_weights = build_candidate_runtime_weights(
            candidate,
            bars_by_symbol=bars_by_symbol,
            current_positions=current_weights,
            account_equity=portfolio_state.equity,
        )
        if any(
            weight < Decimal("0") for weight in runtime_weights.target_weights.values()
        ):
            raise UnsupportedRuntimePortfolioPlanError(
                "Runtime portfolio planner only supports non-negative target weights "
                f"for {candidate.candidate_id}."
            )
        tracked_symbols = tuple(
            sorted(set(runtime_weights.target_weights) | set(current_weights))
        )
        market_snapshots: dict[str, MarketSnapshot] = {}
        planned_trade_rows: list[RuntimePortfolioTrade] = []
        for symbol in tracked_symbols:
            current_quantity = _current_quantity(portfolio_state, symbol)
            last_trade_price = _position_price_hint(portfolio_state, symbol)
            if last_trade_price is None:
                snapshot = self._market_data.get_market_snapshot(symbol)
                market_snapshots[symbol] = snapshot
                last_trade_price = snapshot.last_trade_price
            trade = self._build_planned_trade(
                symbol=symbol,
                current_weight=current_weights.get(symbol, Decimal("0")),
                target_weight=runtime_weights.target_weights.get(symbol, Decimal("0")),
                raw_target_weight=runtime_weights.raw_weights.get(symbol, Decimal("0")),
                current_quantity=current_quantity,
                last_trade_price=last_trade_price,
                candidate_id=candidate.candidate_id,
                generated_at=generated_at,
                account_equity=portfolio_state.equity,
            )
            if (
                trade.side in {"buy", "sell", "reduce"}
                and symbol not in market_snapshots
            ):
                snapshot = self._market_data.get_market_snapshot(symbol)
                market_snapshots[symbol] = snapshot
                trade = self._build_planned_trade(
                    symbol=symbol,
                    current_weight=current_weights.get(symbol, Decimal("0")),
                    target_weight=runtime_weights.target_weights.get(
                        symbol,
                        Decimal("0"),
                    ),
                    raw_target_weight=runtime_weights.raw_weights.get(
                        symbol,
                        Decimal("0"),
                    ),
                    current_quantity=current_quantity,
                    last_trade_price=snapshot.last_trade_price,
                    candidate_id=candidate.candidate_id,
                    generated_at=generated_at,
                    account_equity=portfolio_state.equity,
                )
            planned_trade_rows.append(trade)
        planned_trades = _apply_runtime_sizing_policy_to_buys(
            planned_trades=tuple(planned_trade_rows),
            portfolio_state=portfolio_state,
            sizing_policy=sizing_policy,
            market_snapshots=market_snapshots,
        )
        ordered_trades = tuple(
            sorted(
                planned_trades,
                key=lambda trade: (_side_priority(trade.side), trade.symbol),
            )
        )
        plan_target_weights = _target_weights_for_plan(
            tracked_symbols=tracked_symbols,
            original_target_weights=runtime_weights.target_weights,
            planned_trades=ordered_trades,
            sizing_policy=sizing_policy,
        )
        trade_intents = tuple(
            _trade_intent_for_plan_item(
                trade,
                candidate_id=candidate.candidate_id,
                generated_at=generated_at,
                decomposition=(),
                registry_order_by_sleeve_id=None,
            )
            for trade in ordered_trades
        )
        return RuntimePortfolioPlan(
            plan_id=f"runtime-plan-{uuid.uuid4()}",
            generated_at_utc=generated_at,
            strategy_id=candidate.candidate_id,
            universe_snapshot_id=_universe_snapshot_id(runtime_symbols),
            benchmark_symbol=candidate.benchmark_symbol,
            crash_overlay_active=runtime_weights.crash_overlay_active,
            symbols_considered=tracked_symbols,
            current_weights={
                symbol: current_weights.get(symbol, Decimal("0"))
                for symbol in tracked_symbols
            },
            target_weights=plan_target_weights,
            trade_intents=trade_intents,
            planned_trades=ordered_trades,
            market_snapshots=market_snapshots,
        )

    def _plan_for_blueprint(
        self,
        *,
        blueprint_activation: BlueprintActivationRecord,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        sizing_policy: RuntimeSizingPolicy | None,
    ) -> RuntimePortfolioPlan:
        blueprint = portfolio_blueprint_from_activation(blueprint_activation)
        binding_by_sleeve_id = {
            binding.sleeve_id: binding
            for binding in blueprint_activation.sleeve_activation_bindings
        }
        active_sleeve_ids = tuple(binding_by_sleeve_id)
        if not active_sleeve_ids:
            raise ValueError("Blueprint activation must bind at least one sleeve.")
        blueprint = dataclasses.replace(
            blueprint,
            blueprint_id=blueprint_activation.blueprint_id,
            sleeve_budgets=tuple(
                budget
                for budget in blueprint.sleeve_budgets
                if budget.sleeve_id in binding_by_sleeve_id
            ),
        )
        if len(blueprint.sleeve_budgets) != len(binding_by_sleeve_id):
            raise ValueError(
                "Active blueprint activation references sleeves that are missing from "
                "the source blueprint file."
            )

        generated_at = self._now_provider()
        registry_candidates = build_runtime_candidate_registry(symbols)
        candidate_by_strategy_id = {
            candidate.candidate_id: candidate for candidate in registry_candidates
        }
        registry_order_by_strategy_id = {
            candidate.candidate_id: index
            for index, candidate in enumerate(registry_candidates)
        }
        sleeves_by_id: dict[str, SleeveProtocol] = {}
        benchmark_symbol_by_sleeve_id: dict[str, str] = {}
        benchmark_symbols: set[str] = set()
        required_symbols: set[str] = set()
        for budget in blueprint.sleeve_budgets:
            binding = binding_by_sleeve_id.get(budget.sleeve_id)
            if binding is None:
                raise ValueError(
                    f"No activation binding exists for sleeve {budget.sleeve_id!r}."
                )
            candidate = candidate_by_strategy_id.get(binding.strategy_id)
            if candidate is None or candidate.sleeve_class_path is None:
                raise ValueError(
                    f"Strategy {binding.strategy_id!r} cannot be resolved as a sleeve."
                )
            sleeve = build_sleeve_from_candidate(candidate)
            if sleeve.sleeve_id != budget.sleeve_id:
                sleeve = _RelabeledSleeve(
                    sleeve_id=budget.sleeve_id,
                    delegate=sleeve,
                )
            sleeve = self._wrap_runtime_sleeve(
                sleeve=sleeve,
                blueprint=blueprint,
                trial_candidate_id=binding.strategy_id,
            )
            sleeves_by_id[budget.sleeve_id] = sleeve
            benchmark_symbol_by_sleeve_id[budget.sleeve_id] = candidate.benchmark_symbol
            benchmark_symbols.add(candidate.benchmark_symbol)
            required_symbols.update(candidate.universe)
            required_symbols.add(candidate.benchmark_symbol)
        required_symbols.update(
            position.symbol
            for position in portfolio_state.positions
            if position.quantity != Decimal("0")
        )

        bars_by_symbol = self._load_bars(symbols=tuple(sorted(required_symbols)))
        benchmark_symbol = next(iter(sorted(benchmark_symbols)))
        benchmark_candidate = next(
            candidate
            for candidate in candidate_by_strategy_id.values()
            if candidate.benchmark_symbol == benchmark_symbol
        )
        regimes = _build_regime_snapshots(
            benchmark_candidate=benchmark_candidate,
            bars_by_symbol=bars_by_symbol,
            vix_cache_path=self._vix_cache_path,
            treasury_cache_path=self._treasury_cache_path,
        )
        current_weights_by_sleeve_id = self._current_weights_by_sleeve_id(
            blueprint=blueprint
        )
        context_by_sleeve_id = {
            sleeve_id: _build_sleeve_context(
                sleeve_id=sleeve_id,
                sleeve=sleeve,
                benchmark_symbol=benchmark_symbol_by_sleeve_id.get(sleeve_id),
                bars_by_symbol=bars_by_symbol,
                regimes=regimes,
                current_weights_by_symbol=current_weights_by_sleeve_id.get(
                    sleeve_id,
                    {},
                ),
                generated_at=generated_at,
            )
            for sleeve_id, sleeve in sleeves_by_id.items()
        }
        sleeve_trades_by_id = {
            sleeve_id: sleeve.plan_for_bar(context_by_sleeve_id[sleeve_id])
            for sleeve_id, sleeve in sleeves_by_id.items()
        }
        allocation_limits = self._strategy_allocation_limits_for_blueprint(blueprint)
        aggregate_target_weights, decomposition = build_portfolio_cycle_target_weights(
            blueprint=blueprint,
            sleeves_by_id={
                sleeve_id: _PrecomputedSleeve(
                    sleeve_id=sleeve_id,
                    trades=trades,
                )
                for sleeve_id, trades in sleeve_trades_by_id.items()
            },
            context_by_sleeve_id=context_by_sleeve_id,
            allocation_limits=allocation_limits,
        )
        sleeve_failure_reasons = _structural_failure_reasons(
            sleeve_trades_by_id=sleeve_trades_by_id
        )
        current_weights = _current_weights(portfolio_state)
        reserve_liquidation_quantities = self._reserve_liquidation_quantities()
        tracked_symbols = tuple(
            sorted(
                set(aggregate_target_weights)
                | set(current_weights)
                | set(reserve_liquidation_quantities)
            )
        )
        market_snapshots: dict[str, MarketSnapshot] = {}
        planned_trade_rows: list[RuntimePortfolioTrade] = []
        for symbol in tracked_symbols:
            current_quantity = _current_quantity(portfolio_state, symbol)
            last_trade_price = _position_price_hint(portfolio_state, symbol)
            if last_trade_price is None:
                snapshot = self._market_data.get_market_snapshot(symbol)
                market_snapshots[symbol] = snapshot
                last_trade_price = snapshot.last_trade_price
            reserve_quantity = reserve_liquidation_quantities.get(symbol)
            if reserve_quantity is not None:
                trade = self._build_reserve_liquidation_trade(
                    symbol=symbol,
                    reserve_quantity=reserve_quantity,
                    current_quantity=current_quantity,
                    current_weight=current_weights.get(symbol, Decimal("0")),
                    last_trade_price=last_trade_price,
                    account_equity=portfolio_state.equity,
                )
            else:
                trade = self._build_planned_trade(
                    symbol=symbol,
                    current_weight=current_weights.get(symbol, Decimal("0")),
                    target_weight=aggregate_target_weights.get(symbol, Decimal("0")),
                    raw_target_weight=aggregate_target_weights.get(
                        symbol, Decimal("0")
                    ),
                    current_quantity=current_quantity,
                    last_trade_price=last_trade_price,
                    candidate_id=blueprint.blueprint_id,
                    generated_at=generated_at,
                    account_equity=portfolio_state.equity,
                )
            if (
                trade.side in {"buy", "sell", "reduce"}
                and symbol not in market_snapshots
            ):
                snapshot = self._market_data.get_market_snapshot(symbol)
                market_snapshots[symbol] = snapshot
                if reserve_quantity is not None:
                    trade = self._build_reserve_liquidation_trade(
                        symbol=symbol,
                        reserve_quantity=reserve_quantity,
                        current_quantity=current_quantity,
                        current_weight=current_weights.get(symbol, Decimal("0")),
                        last_trade_price=snapshot.last_trade_price,
                        account_equity=portfolio_state.equity,
                    )
                else:
                    trade = self._build_planned_trade(
                        symbol=symbol,
                        current_weight=current_weights.get(symbol, Decimal("0")),
                        target_weight=aggregate_target_weights.get(
                            symbol, Decimal("0")
                        ),
                        raw_target_weight=aggregate_target_weights.get(
                            symbol,
                            Decimal("0"),
                        ),
                        current_quantity=current_quantity,
                        last_trade_price=snapshot.last_trade_price,
                        candidate_id=blueprint.blueprint_id,
                        generated_at=generated_at,
                        account_equity=portfolio_state.equity,
                    )
            planned_trade_rows.append(trade)
        planned_trades = _apply_runtime_sizing_policy_to_buys(
            planned_trades=tuple(planned_trade_rows),
            portfolio_state=portfolio_state,
            sizing_policy=sizing_policy,
            market_snapshots=market_snapshots,
        )
        ordered_trades = tuple(
            sorted(
                planned_trades,
                key=lambda trade: (_side_priority(trade.side), trade.symbol),
            )
        )
        plan_target_weights = _target_weights_for_plan(
            tracked_symbols=tracked_symbols,
            original_target_weights=aggregate_target_weights,
            planned_trades=ordered_trades,
            sizing_policy=sizing_policy,
        )
        registry_order_by_sleeve_id = {
            binding.sleeve_id: index
            for binding, index in (
                (
                    binding,
                    registry_order_by_strategy_id.get(binding.strategy_id, 1_000_000),
                )
                for binding in blueprint_activation.sleeve_activation_bindings
            )
        }
        trade_intents = tuple(
            (
                _reserve_trade_intent_for_plan_item(
                    trade,
                    generated_at=generated_at,
                )
                if trade.reason_code == "residual_reserve_liquidation"
                else _trade_intent_for_plan_item(
                    trade,
                    candidate_id=blueprint.blueprint_id,
                    generated_at=generated_at,
                    decomposition=decomposition,
                    registry_order_by_sleeve_id=registry_order_by_sleeve_id,
                )
            )
            for trade in ordered_trades
        )
        return RuntimePortfolioPlan(
            plan_id=f"runtime-plan-{uuid.uuid4()}",
            generated_at_utc=generated_at,
            strategy_id=blueprint.blueprint_id,
            universe_snapshot_id=_universe_snapshot_id(tracked_symbols),
            benchmark_symbol=benchmark_symbol,
            crash_overlay_active=False,
            symbols_considered=tracked_symbols,
            current_weights={
                symbol: current_weights.get(symbol, Decimal("0"))
                for symbol in tracked_symbols
            },
            target_weights=plan_target_weights,
            trade_intents=trade_intents,
            planned_trades=ordered_trades,
            market_snapshots=market_snapshots,
            per_sleeve_target_weights=decomposition,
            sleeve_failure_reasons=sleeve_failure_reasons,
        )

    def _strategy_allocation_limits_for_blueprint(
        self,
        blueprint: PortfolioBlueprint,
    ) -> tuple[StrategyAllocationLimit, ...] | None:
        if self._activation_gateway is None:
            return None
        limit_provider = cast(
            Callable[[PortfolioBlueprint], tuple[StrategyAllocationLimit, ...]] | None,
            getattr(
                self._activation_gateway,
                "get_strategy_allocation_limits",
                None,
            ),
        )
        if limit_provider is None:
            return None
        return limit_provider(blueprint)

    def _candidate_for_strategy(
        self,
        *,
        strategy_id: str,
        symbols: tuple[str, ...],
    ) -> StrategyCandidate | None:
        for candidate in build_runtime_candidate_registry(symbols):
            if candidate.candidate_id == strategy_id:
                return candidate
        return None

    def _load_bars(self, *, symbols: tuple[str, ...]) -> dict[str, Any]:
        end_utc = self._now_provider()
        start_utc = end_utc - timedelta(days=self._history_lookback_days)
        return {
            symbol: self._market_data.get_daily_bar_history(
                symbol,
                start_utc=start_utc,
                end_utc=end_utc,
            )
            for symbol in symbols
        }

    def _wrap_runtime_sleeve(
        self,
        *,
        sleeve: SleeveProtocol,
        blueprint: PortfolioBlueprint,
        trial_candidate_id: str,
    ) -> SleeveProtocol:
        if (
            self._operator_halt_store is None
            and self._drift_alarm_gateway is None
            and self._trials_ledger is None
            and self._live_daily_returns_source is None
        ):
            return sleeve
        return SleeveRuntimeController(
            wrapped_sleeve=sleeve,
            operator_halt_store=self._operator_halt_store or _NullHaltStore(),
            drift_alarm_gateway=self._drift_alarm_gateway,
            trials_ledger=self._trials_ledger,
            config=SleeveRuntimeConfig(
                three_month_sharpe_floor=blueprint.sleeve_three_month_sharpe_floor,
            ),
            live_daily_returns_source=self._live_daily_returns_source,
            trial_candidate_id=trial_candidate_id,
        )

    def _current_weights_by_sleeve_id(
        self,
        *,
        blueprint: PortfolioBlueprint,
    ) -> dict[str, dict[str, Decimal]]:
        default: dict[str, dict[str, Decimal]] = {
            budget.sleeve_id: {} for budget in blueprint.sleeve_budgets
        }
        if self._runtime_state_store is None:
            return default
        latest = self._runtime_state_store.latest_sleeve_decomposition_record()
        if latest is None:
            return default
        weights: dict[str, dict[str, Decimal]] = {}
        for entry in latest.per_sleeve_target_weights:
            weights[entry.sleeve_id] = dict(entry.target_weights_by_symbol)
        for budget in blueprint.sleeve_budgets:
            weights.setdefault(budget.sleeve_id, {})
        return weights

    def _build_planned_trade(
        self,
        *,
        symbol: str,
        current_weight: Decimal,
        target_weight: Decimal,
        raw_target_weight: Decimal,
        current_quantity: Decimal,
        last_trade_price: Decimal,
        candidate_id: str,
        generated_at: datetime,
        account_equity: Decimal,
    ) -> RuntimePortfolioTrade:
        del candidate_id, generated_at
        target_quantity = _target_quantity(
            target_weight=target_weight,
            account_equity=account_equity,
            last_trade_price=last_trade_price,
        )
        delta_quantity = target_quantity - current_quantity
        if delta_quantity > Decimal("0"):
            side = "buy"
            reason_code = "target_weight_entry"
        elif delta_quantity < Decimal("0"):
            side = "sell" if target_quantity == Decimal("0") else "reduce"
            reason_code = (
                "target_weight_exit"
                if target_quantity == Decimal("0")
                else "target_weight_reduce"
            )
        else:
            side = "hold"
            reason_code = "target_weight_hold"

        return RuntimePortfolioTrade(
            symbol=symbol,
            side=side,
            reason_code=reason_code,
            last_trade_price=last_trade_price,
            current_weight=current_weight,
            target_weight=target_weight,
            current_quantity=current_quantity,
            target_quantity=target_quantity,
            delta_quantity=delta_quantity,
            no_trade_band_applied=target_weight != raw_target_weight,
        )

    def _build_reserve_liquidation_trade(
        self,
        *,
        symbol: str,
        reserve_quantity: Decimal,
        current_quantity: Decimal,
        current_weight: Decimal,
        last_trade_price: Decimal,
        account_equity: Decimal,
    ) -> RuntimePortfolioTrade:
        target_quantity = max(Decimal("0"), current_quantity - reserve_quantity)
        target_weight = (
            Decimal("0")
            if account_equity <= Decimal("0")
            else (target_quantity * last_trade_price) / account_equity
        )
        side = "sell" if target_quantity == Decimal("0") else "reduce"
        reason_code = "residual_reserve_liquidation"
        return RuntimePortfolioTrade(
            symbol=symbol,
            side=side,
            reason_code=reason_code,
            last_trade_price=last_trade_price,
            current_weight=current_weight,
            target_weight=target_weight,
            current_quantity=current_quantity,
            target_quantity=target_quantity,
            delta_quantity=-reserve_quantity,
            no_trade_band_applied=False,
        )

    def _reserve_liquidation_quantities(self) -> dict[str, Decimal]:
        if self._runtime_state_store is None:
            return {}
        latest = self._runtime_state_store.latest_residual_reserve_snapshot()
        if latest is None:
            return {}
        return {
            position.symbol: position.quantity
            for position in latest.positions
            if position.quantity > Decimal("0")
        }


def _current_weights(portfolio_state: PortfolioState) -> dict[str, Decimal]:
    if portfolio_state.equity <= Decimal("0"):
        return {}
    return {
        position.symbol: position.market_value / portfolio_state.equity
        for position in portfolio_state.positions
        if position.quantity != Decimal("0")
    }


def _current_quantity(portfolio_state: PortfolioState, symbol: str) -> Decimal:
    for position in portfolio_state.positions:
        if position.symbol == symbol:
            return position.quantity
    return Decimal("0")


def _position_price_hint(
    portfolio_state: PortfolioState,
    symbol: str,
) -> Decimal | None:
    for position in portfolio_state.positions:
        if (
            position.symbol == symbol
            and position.quantity != Decimal("0")
            and position.market_value > Decimal("0")
        ):
            return position.market_value / position.quantity
    return None


def _target_quantity(
    *,
    target_weight: Decimal,
    account_equity: Decimal,
    last_trade_price: Decimal,
) -> Decimal:
    if (
        target_weight <= Decimal("0")
        or account_equity <= Decimal("0")
        or last_trade_price <= Decimal("0")
    ):
        return Decimal("0")
    raw_quantity = (target_weight * account_equity) / last_trade_price
    return raw_quantity.quantize(Decimal("1"), rounding=ROUND_DOWN)


def _apply_runtime_sizing_policy_to_buys(
    *,
    planned_trades: tuple[RuntimePortfolioTrade, ...],
    portfolio_state: PortfolioState,
    sizing_policy: RuntimeSizingPolicy | None,
    market_snapshots: dict[str, MarketSnapshot],
) -> tuple[RuntimePortfolioTrade, ...]:
    if sizing_policy is None:
        return planned_trades

    sizing_budget = build_runtime_sizing_budget(
        policy=sizing_policy,
        portfolio_state=portfolio_state,
    )
    adjusted_trades: list[RuntimePortfolioTrade] = []
    for trade in planned_trades:
        if trade.side != "buy" or trade.delta_quantity <= Decimal("0"):
            adjusted_trades.append(trade)
            continue

        market_snapshot = market_snapshots.get(trade.symbol)
        entry_price = (
            entry_marketable_limit_price(
                market_snapshot,
                buffer_bps=sizing_policy.entry_marketable_limit_bps,
            )
            if market_snapshot is not None
            else trade.last_trade_price
        )
        capped_delta = cap_entry_quantity(
            policy=sizing_policy,
            portfolio_state=portfolio_state,
            last_trade_price=trade.last_trade_price,
            entry_price=entry_price,
            requested_quantity=trade.delta_quantity,
            sizing_budget=sizing_budget,
        )
        target_quantity = trade.current_quantity + capped_delta
        target_weight = _weight_for_quantity(
            account_equity=portfolio_state.equity,
            quantity=target_quantity,
            last_trade_price=trade.last_trade_price,
        )
        if capped_delta <= Decimal("0"):
            adjusted_trade = dataclasses.replace(
                trade,
                side="hold",
                reason_code="entry_size_below_minimum",
                target_weight=target_weight,
                target_quantity=target_quantity,
                delta_quantity=Decimal("0"),
            )
        else:
            adjusted_trade = dataclasses.replace(
                trade,
                target_weight=target_weight,
                target_quantity=target_quantity,
                delta_quantity=capped_delta,
            )
            sizing_budget.consume(capped_delta * entry_price)
        adjusted_trades.append(adjusted_trade)
    return tuple(adjusted_trades)


def _target_weights_for_plan(
    *,
    tracked_symbols: tuple[str, ...],
    original_target_weights: dict[str, Decimal],
    planned_trades: tuple[RuntimePortfolioTrade, ...],
    sizing_policy: RuntimeSizingPolicy | None,
) -> dict[str, Decimal]:
    if sizing_policy is None:
        return {
            symbol: original_target_weights.get(symbol, Decimal("0"))
            for symbol in tracked_symbols
        }
    target_weight_by_symbol = {
        trade.symbol: trade.target_weight for trade in planned_trades
    }
    return {
        symbol: target_weight_by_symbol.get(
            symbol,
            original_target_weights.get(symbol, Decimal("0")),
        )
        for symbol in tracked_symbols
    }


def _weight_for_quantity(
    *,
    account_equity: Decimal,
    quantity: Decimal,
    last_trade_price: Decimal,
) -> Decimal:
    if (
        account_equity <= Decimal("0")
        or quantity <= Decimal("0")
        or last_trade_price <= Decimal("0")
    ):
        return Decimal("0")
    return (quantity * last_trade_price) / account_equity


def _trade_intent_for_plan_item(
    trade: RuntimePortfolioTrade,
    *,
    candidate_id: str,
    generated_at: datetime,
    decomposition: tuple[SleeveTargetWeights, ...],
    registry_order_by_sleeve_id: dict[str, int] | None,
) -> TradeIntent:
    payload = "|".join(
        (
            candidate_id,
            trade.symbol,
            trade.side,
            str(trade.delta_quantity),
            generated_at.astimezone(UTC).isoformat(),
        )
    )
    return TradeIntent(
        intent_id=str(uuid.uuid5(uuid.NAMESPACE_URL, payload)),
        candidate_id=candidate_id,
        symbol=trade.symbol,
        side=trade.side,
        quantity=(None if trade.side == "hold" else abs(trade.delta_quantity)),
        reason_code=trade.reason_code,
        generated_at_utc=generated_at,
        sleeve_attributions=_compute_sleeve_attributions(
            symbol=trade.symbol,
            decomposition=decomposition,
            registry_order_by_sleeve_id=registry_order_by_sleeve_id,
        ),
    )


def _reserve_trade_intent_for_plan_item(
    trade: RuntimePortfolioTrade,
    *,
    generated_at: datetime,
) -> TradeIntent:
    payload = "|".join(
        (
            "residual-reserve-bootstrap",
            trade.symbol,
            trade.side,
            str(trade.delta_quantity),
            generated_at.astimezone(UTC).isoformat(),
        )
    )
    return TradeIntent(
        intent_id=str(uuid.uuid5(uuid.NAMESPACE_URL, payload)),
        candidate_id="residual-reserve-bootstrap",
        symbol=trade.symbol,
        side=trade.side,
        quantity=(None if trade.side == "hold" else abs(trade.delta_quantity)),
        reason_code=trade.reason_code,
        generated_at_utc=generated_at,
        sleeve_attributions=((RESIDUAL_RESERVE_OWNER_ID, Decimal("1")),),
    )


def _compute_sleeve_attributions(
    *,
    symbol: str,
    decomposition: tuple[SleeveTargetWeights, ...],
    registry_order_by_sleeve_id: dict[str, int] | None,
) -> tuple[tuple[str, Decimal], ...]:
    if not decomposition:
        return ()
    contributions: dict[str, Decimal] = {}
    for entry in decomposition:
        contribution = dict(entry.target_weights_by_symbol).get(symbol, Decimal("0"))
        if contribution > Decimal("0"):
            contributions[entry.sleeve_id] = contribution
    total = sum(contributions.values(), start=Decimal("0"))
    if total <= Decimal("0"):
        return ()
    registry_order = (
        registry_order_by_sleeve_id
        if registry_order_by_sleeve_id is not None
        else {
            candidate.candidate_id: index
            for index, candidate in enumerate(build_runtime_candidate_registry())
        }
    )
    fractions = sorted(
        ((sleeve_id, value / total) for sleeve_id, value in contributions.items()),
        key=lambda item: (-item[1], registry_order.get(item[0], 1_000_000)),
    )
    return tuple(fractions)


def _structural_failure_reasons(
    *,
    sleeve_trades_by_id: dict[str, tuple[SleeveTrade, ...]],
) -> tuple[tuple[str, str], ...]:
    structural = {
        SleeveFailureReason.HALT_BY_OPERATOR,
        SleeveFailureReason.DRIFT_ALARM_LIVE,
        SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M,
    }
    failures: list[tuple[str, str]] = []
    for sleeve_id, trades in sorted(sleeve_trades_by_id.items()):
        if not trades:
            continue
        rationales = {trade.rationale for trade in trades}
        if len(rationales) != 1:
            continue
        rationale = next(iter(rationales))
        if rationale not in structural:
            continue
        if any(
            trade.target_weight_of_sleeve_budget != Decimal("0") for trade in trades
        ):
            continue
        failures.append((sleeve_id, rationale))
    return tuple(failures)


def _side_priority(side: str) -> int:
    if side in {"sell", "reduce"}:
        return 0
    if side == "hold":
        return 1
    return 2


class _PrecomputedSleeve:
    def __init__(
        self,
        *,
        sleeve_id: str,
        trades: tuple[SleeveTrade, ...],
    ) -> None:
        self.sleeve_id = sleeve_id
        self.family = "runtime_portfolio"
        self.allowed_instruments: tuple[str, ...] = ()
        self._trades = trades

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        del context
        return self._trades


class _RelabeledSleeve:
    def __init__(
        self,
        *,
        sleeve_id: str,
        delegate: SleeveProtocol,
    ) -> None:
        self.sleeve_id = sleeve_id
        self.family = delegate.family
        self.allowed_instruments = delegate.allowed_instruments
        self._delegate = delegate

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        return self._delegate.plan_for_bar(context)


class _NullHaltStore:
    def is_halted(self, *, sleeve_id: str) -> bool:
        del sleeve_id
        return False


def _universe_snapshot_id(symbols: tuple[str, ...]) -> str:
    normalized = tuple(
        sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    )
    if not normalized:
        return "universe-empty"
    return "universe-" + "-".join(symbol.lower() for symbol in normalized)


def _build_regime_snapshots(
    *,
    benchmark_candidate: StrategyCandidate,
    bars_by_symbol: dict[str, Any],
    vix_cache_path: Path | None = DEFAULT_VIX_CACHE_PATH,
    treasury_cache_path: Path | None = DEFAULT_TREASURY_YIELD_CACHE_PATH,
) -> dict[date, RegimeSnapshot]:
    benchmark_bars = bars_by_symbol.get(benchmark_candidate.benchmark_symbol)
    if benchmark_bars is None:
        raise ValueError(
            f"Missing benchmark bars for {benchmark_candidate.benchmark_symbol!r}."
        )
    closes = benchmark_bars["close"].astype(float)
    prior_closes = closes.shift(1)
    sma_200 = prior_closes.rolling(200, min_periods=200).mean()
    regimes: dict[date, RegimeSnapshot] = {}
    for timestamp in benchmark_bars.index:
        prior_close = prior_closes.loc[timestamp]
        prior_sma = sma_200.loc[timestamp]
        if pd.isna(prior_close) or pd.isna(prior_sma):
            continue
        snapshot_date = timestamp.date()
        regimes[timestamp.date()] = classify_regime(
            observation_date=snapshot_date,
            spy_close=Decimal(str(float(prior_close))),
            spy_sma_200=Decimal(str(float(prior_sma))),
            vix_close=_vix_close_for_snapshot(
                vix_cache_path,
                as_of_date=snapshot_date,
            ),
            yield_curve_spread_bps=_yield_curve_spread_for_snapshot(
                treasury_cache_path,
                as_of_date=snapshot_date,
            ),
        )
    return regimes


def _vix_close_for_snapshot(
    cache_path: Path | None,
    *,
    as_of_date: date,
) -> Decimal | None:
    if cache_path is None or not cache_path.exists():
        return None
    return vix_close_for_date(cache_path, as_of_date=as_of_date)


def _yield_curve_spread_for_snapshot(
    cache_path: Path | None,
    *,
    as_of_date: date,
) -> Decimal | None:
    if cache_path is None or not cache_path.exists():
        return None
    return yield_curve_spread_for_date_pit(cache_path, as_of_date=as_of_date)


def _build_sleeve_context(
    *,
    sleeve_id: str,
    sleeve: SleeveProtocol,
    benchmark_symbol: str | None = None,
    bars_by_symbol: dict[str, Any],
    regimes: dict[date, RegimeSnapshot],
    current_weights_by_symbol: dict[str, Decimal],
    generated_at: datetime,
) -> SleeveContext:
    context_symbol = benchmark_symbol
    if context_symbol is None and sleeve.allowed_instruments:
        context_symbol = sleeve.allowed_instruments[0]
    if context_symbol is None:
        raise ValueError(f"Missing benchmark symbol for sleeve {sleeve_id!r}.")
    benchmark_bars = bars_by_symbol.get(context_symbol)
    if benchmark_bars is None or benchmark_bars.empty:
        raise ValueError(f"Missing bars for sleeve {sleeve_id!r}.")
    timestamp = benchmark_bars.index[-1]
    regime = regimes.get(timestamp.date())
    if regime is None:
        raise UnsupportedRuntimePortfolioPlanError(
            f"Insufficient prior SMA(200) history for sleeve {sleeve_id!r}."
        )
    execution_position = len(benchmark_bars) - 1
    return SleeveContext(
        observation_date=timestamp.date(),
        bars_by_symbol={
            symbol: bars.iloc[:execution_position]
            for symbol, bars in bars_by_symbol.items()
        },
        regime=regime,
        current_weights_by_symbol=dict(current_weights_by_symbol),
        sleeve_budget_equity=Decimal("1.0"),
    )


__all__ = (
    "CandidateRuntimeWeights",
    "RuntimePortfolioPlan",
    "RuntimePortfolioPlanner",
    "RuntimePortfolioTrade",
    "UnsupportedRuntimePortfolioPlanError",
)
