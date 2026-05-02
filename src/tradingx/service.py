from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast

from tradingx.activation import LocalActivationGateway
from tradingx.config import TradingConfig
from tradingx.controller import (
    build_default_trading_loop_controller,
)
from tradingx.data import (
    AlpacaRegularHoursCalendar,
    build_market_data_gateway_for_mode,
)
from tradingx.drift.gateway import ArtifactBackedDriftAlarmStateReader
from tradingx.historical import HistoricalWarmupService
from tradingx.live_enablement import (
    build_trading_client_for_mode,
    resolve_broker_mode,
)
from tradingx.monitoring import StageMetrics
from tradingx.operator_control import OperatorControlStore
from tradingx.opportunity import LiveOpportunitySelector
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    portfolio_blueprint_from_activation,
)
from tradingx.portfolio.fallback import (
    ActivationGatewaySupersedeProtocol,
    BlueprintExhaustionError,
    narrow_blueprint_on_sleeve_failure,
)
from tradingx.promotion import (
    PromotionState,
    build_artifact_promotion_decision_provider,
)
from tradingx.risk_free import DEFAULT_TREASURY_YIELD_CACHE_PATH, DEFAULT_VIX_CACHE_PATH
from tradingx.runtime_logging import (
    StructuredRuntimeLogger,
    build_default_runtime_logger,
)
from tradingx.runtime_portfolio import RuntimePortfolioPlan, RuntimePortfolioPlanner
from tradingx.runtime_strategy_registry import (
    ActivatedRuntimePlanner,
    build_default_runtime_registry,
)
from tradingx.sizing import RuntimeSizingPolicy
from tradingx.strategy import DEFAULT_CANDIDATE_ID
from tradingx.trials import TrialsLedger
from tradingx.types import (
    BlueprintActivationRecord,
    BotBrainCycleExplanation,
    BotBrainSleeveCycleReason,
    OperatorAlert,
    PortfolioState,
    ServiceCycleSnapshot,
    ServiceRunResult,
    ServiceSymbolResult,
    SleeveDecompositionRecord,
    TradingLoopResult,
)


def _operator_promotion_root() -> Path:
    return Path("config/strategy/promotion")


class TradingLoopControllerProtocol(Protocol):
    def run_trading_cycle(
        self, symbol: str, quantity: Decimal
    ) -> TradingLoopResult: ...


class PortfolioGatewayProtocol(Protocol):
    def get_portfolio_state(self) -> PortfolioState: ...


class PortfolioPlannerProtocol(Protocol):
    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> RuntimePortfolioPlan | None: ...


class PaperTradingService:
    def __init__(
        self,
        *,
        loop_controller: TradingLoopControllerProtocol,
        portfolio: PortfolioGatewayProtocol,
        artifacts: FilesystemArtifactStore,
        metrics: StageMetrics,
        regular_hours_checker: Callable[[datetime], bool],
        runtime_state_store: FilesystemArtifactStore | None = None,
        now_provider: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[int], None] | None = None,
        monotonic_fn: Callable[[], float] | None = None,
        cycle_budget_seconds: int = 30,
        broker_failure_threshold: int = 2,
        broker_staleness_seconds: int = 60,
        portfolio_planner: PortfolioPlannerProtocol | None = None,
        operator_control_store: OperatorControlStore | None = None,
        runtime_logger: StructuredRuntimeLogger | None = None,
    ) -> None:
        self._loop_controller = loop_controller
        self._portfolio = portfolio
        self._artifacts = artifacts
        self._runtime_state_store = runtime_state_store or artifacts
        self._metrics = metrics
        self._regular_hours_checker = regular_hours_checker
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._sleep_fn = sleep_fn or (lambda seconds: __import__("time").sleep(seconds))
        self._monotonic_fn = monotonic_fn or __import__("time").monotonic
        self._cycle_budget_seconds = cycle_budget_seconds
        self._broker_failure_threshold = broker_failure_threshold
        self._broker_staleness_seconds = broker_staleness_seconds
        self._portfolio_planner = portfolio_planner
        self._operator_control_store = operator_control_store
        self._runtime_logger = runtime_logger
        self._session_start_equity: Decimal | None = None
        self._last_successful_broker_call_at: datetime | None = None
        self._last_known_portfolio_state: PortfolioState | None = None
        self._sleeve_failure_streaks: dict[str, tuple[str, int]] = {}

    def run(
        self,
        *,
        symbols: Sequence[str],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> ServiceRunResult:
        cycles_completed = 0
        artifact_paths = []
        last_cycle: ServiceCycleSnapshot | None = None
        while max_cycles is None or cycles_completed < max_cycles:
            last_cycle = self._run_single_cycle(
                symbols=tuple(symbols),
                quantity=quantity,
                sizing_policy=sizing_policy,
            )
            artifact_paths.append(
                self._artifacts.write_service_cycle_snapshot(last_cycle)
            )
            cycles_completed += 1
            if last_cycle.cycle_status == "kill_requested":
                break
            if max_cycles is not None and cycles_completed >= max_cycles:
                break
            self._sleep_fn(interval_seconds)
        if last_cycle is None:
            raise RuntimeError("Service must execute at least one cycle.")
        return ServiceRunResult(
            cycles_completed=cycles_completed,
            last_cycle=last_cycle,
            artifact_paths=tuple(artifact_paths),
        )

    def _run_single_cycle(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> ServiceCycleSnapshot:
        started_at = self._now_provider()
        cycle_started_at = self._monotonic_fn()
        service_cycle_id = f"service-{uuid.uuid4()}"
        symbol_results: list[ServiceSymbolResult] = []
        blocked_trade_count = 0
        reconciliation_failure_count = 0
        cycle_status = "market_closed"
        portfolio_plan_for_explanation: RuntimePortfolioPlan | None = None
        self._log_cycle_event(
            event_type="cycle_started",
            severity="info",
            message="Paper trading service cycle started.",
            cycle_correlation_id=service_cycle_id,
            fields={"symbols": symbols},
        )
        if (
            self._operator_control_store is not None
            and self._operator_control_store.read_state().kill_requested
        ):
            portfolio_state = (
                self._last_known_portfolio_state or self._empty_portfolio_state()
            )
            cycle_status = "kill_requested"
            self._log_cycle_event(
                event_type="kill_requested",
                severity="warning",
                message="Kill request detected at cycle boundary.",
                cycle_correlation_id=service_cycle_id,
                fields={},
            )
        elif not self._regular_hours_checker(started_at):
            initial_portfolio_state = (
                self._last_known_portfolio_state or self._empty_portfolio_state()
            )
            portfolio_state = initial_portfolio_state
        else:
            broker_status, initial_portfolio_state = self._get_portfolio_state_guarded()
            if broker_status is not None:
                cycle_status = broker_status
                portfolio_state = initial_portfolio_state
                self._log_cycle_event(
                    event_type=broker_status,
                    severity="warning",
                    message="Service cycle blocked by broker or data guardrail.",
                    cycle_correlation_id=service_cycle_id,
                    fields={},
                )
            else:
                cycle_status = "executed"
                planner_failed = False
                try:
                    if self._portfolio_planner is None:
                        portfolio_plan = None
                    elif sizing_policy is None:
                        portfolio_plan = self._portfolio_planner.plan_for_service(
                            symbols=symbols,
                            portfolio_state=initial_portfolio_state,
                            default_quantity=quantity,
                        )
                    else:
                        portfolio_plan = self._portfolio_planner.plan_for_service(
                            symbols=symbols,
                            portfolio_state=initial_portfolio_state,
                            default_quantity=quantity,
                            sizing_policy=sizing_policy,
                        )
                except Exception as error:
                    cycle_status = "recovery_required"
                    planner_failed = True
                    self._log_cycle_event(
                        event_type="planner_failed",
                        severity="warning",
                        message="Runtime portfolio planner failed for this cycle.",
                        cycle_correlation_id=service_cycle_id,
                        fields={"error": str(error)},
                    )
                    portfolio_plan = None
                if portfolio_plan is not None:
                    portfolio_plan_for_explanation = portfolio_plan
                    self._artifacts.write_runtime_portfolio_plan(portfolio_plan)
                    self._write_sleeve_decomposition_record_if_available(
                        plan=portfolio_plan,
                        cycle_id=service_cycle_id,
                        started_at=started_at,
                    )
                    executor = getattr(
                        self._loop_controller,
                        "execute_trade_intent",
                        None,
                    )
                    if not callable(executor):
                        raise AttributeError(
                            "Loop controller must implement execute_trade_intent "
                            "when a portfolio planner is configured."
                        )
                    for trade_intent in portfolio_plan.trade_intents:
                        result = executor(
                            trade_intent,
                            market_snapshot=portfolio_plan.market_snapshots.get(
                                trade_intent.symbol
                            ),
                            universe_snapshot_id=portfolio_plan.universe_snapshot_id,
                        )
                        reason_code = result.trade_intent.reason_code
                        control_type = self._result_control_type(result)
                        symbol_results.append(
                            ServiceSymbolResult(
                                symbol=trade_intent.symbol,
                                terminal_state=result.terminal_state,
                                reason_code=reason_code,
                                recovered=result.recovered,
                                control_type=control_type,
                            )
                        )
                        if result.terminal_state == "blocked_trade":
                            blocked_trade_count += 1
                            if control_type in {"stale_market_data", "stale_quote"}:
                                cycle_status = "data_unavailable"
                                self._log_cycle_event(
                                    event_type="data_unavailable",
                                    severity="warning",
                                    message="Cycle blocked by stale market data.",
                                    cycle_correlation_id=service_cycle_id,
                                    fields={"symbol": trade_intent.symbol},
                                )
                        if not result.reconciliation.resolved:
                            reconciliation_failure_count += 1
                            cycle_status = "recovery_required"
                    fallback_cycle_status = (
                        self._maybe_narrow_blueprint_after_structural_failures(
                            plan=portfolio_plan,
                            started_at=started_at,
                            cycle_correlation_id=service_cycle_id,
                        )
                    )
                    if fallback_cycle_status is not None:
                        cycle_status = fallback_cycle_status
                elif self._portfolio_planner is None:
                    self._sleeve_failure_streaks.clear()
                    (
                        symbol_results,
                        blocked_trade_count,
                        reconciliation_failure_count,
                        cycle_status,
                    ) = self._run_legacy_symbol_cycles(
                        symbols=symbols,
                        quantity=quantity,
                        portfolio_state=initial_portfolio_state,
                        cycle_correlation_id=service_cycle_id,
                        initial_cycle_status=cycle_status,
                    )
                elif not planner_failed:
                    cycle_status = "no_trade"
                    self._log_cycle_event(
                        event_type="planner_no_candidate",
                        severity="info",
                        message="Runtime planner returned no executable trade plan.",
                        cycle_correlation_id=service_cycle_id,
                        fields={
                            "reason": "planner_returned_none",
                            "strategy_id": getattr(
                                self._portfolio_planner,
                                "last_strategy_id",
                                "",
                            ),
                        },
                    )
                    self._sleeve_failure_streaks.clear()
                broker_status_after_cycle, portfolio_state = (
                    self._get_portfolio_state_guarded()
                )
                if (
                    broker_status_after_cycle is not None
                    and cycle_status != "recovery_required"
                ):
                    cycle_status = broker_status_after_cycle
        if self._session_start_equity is None:
            self._session_start_equity = portfolio_state.equity
        daily_pnl = portfolio_state.equity - self._session_start_equity
        cycle_duration_seconds = self._monotonic_fn() - cycle_started_at
        if (
            cycle_duration_seconds > self._cycle_budget_seconds
            and cycle_status != "recovery_required"
        ):
            cycle_status = "cycle_overrun"
            self._log_cycle_event(
                event_type="cycle_overrun",
                severity="warning",
                message="Service cycle exceeded the hard time budget.",
                cycle_correlation_id=service_cycle_id,
                fields={"cycle_duration_seconds": cycle_duration_seconds},
            )
        self._metrics.record_service_cycle(cycle_status)
        self._metrics.record_symbols_scanned(len(symbol_results))
        self._metrics.record_open_positions(
            len(
                [
                    position
                    for position in portfolio_state.positions
                    if position.quantity != Decimal("0")
                ]
            )
        )
        self._metrics.record_account_snapshot(
            cash=portfolio_state.cash,
            equity=portfolio_state.equity,
            daily_pnl=daily_pnl,
        )
        self._log_cycle_event(
            event_type="cycle_completed",
            severity="info",
            message="Paper trading service cycle completed.",
            cycle_correlation_id=service_cycle_id,
            fields={
                "cycle_status": cycle_status,
                "blocked_trade_count": blocked_trade_count,
                "reconciliation_failure_count": reconciliation_failure_count,
            },
        )
        return ServiceCycleSnapshot(
            cycle_id=service_cycle_id,
            started_at_utc=started_at,
            completed_at_utc=self._now_provider(),
            cycle_status=cycle_status,
            symbols=symbols,
            symbol_results=tuple(symbol_results),
            blocked_trade_count=blocked_trade_count,
            reconciliation_failure_count=reconciliation_failure_count,
            open_position_symbols=self._open_position_symbols(portfolio_state),
            cash=portfolio_state.cash,
            equity=portfolio_state.equity,
            buying_power=portfolio_state.buying_power,
            cycle_explanation=self._build_cycle_explanation(
                cycle_status=cycle_status,
                symbol_results=tuple(symbol_results),
                blocked_trade_count=blocked_trade_count,
                portfolio_plan=portfolio_plan_for_explanation,
            ),
        )

    def _build_cycle_explanation(
        self,
        *,
        cycle_status: str,
        symbol_results: tuple[ServiceSymbolResult, ...],
        blocked_trade_count: int,
        portfolio_plan: RuntimePortfolioPlan | None,
    ) -> BotBrainCycleExplanation:
        if cycle_status == "market_closed":
            return BotBrainCycleExplanation(
                summary="No trade because the market is closed.",
                primary_reason_code="market_closed",
                market_state="closed",
                planner_status="not_run",
                risk_status="not_evaluated",
                sleeve_reasons=(),
            )
        if cycle_status == "kill_requested":
            return BotBrainCycleExplanation(
                summary="No trade because the operator kill switch is active.",
                primary_reason_code="kill_requested",
                market_state="open_or_unknown",
                planner_status="not_run",
                risk_status="operator_blocked",
                sleeve_reasons=(),
            )
        sleeve_reasons: list[BotBrainSleeveCycleReason] = []
        if portfolio_plan is not None:
            for entry in portfolio_plan.per_sleeve_target_weights:
                if entry.target_weights_by_symbol:
                    reason = ", ".join(
                        f"{symbol} {weight}"
                        for symbol, weight in entry.target_weights_by_symbol
                    )
                    sleeve_reasons.append(
                        BotBrainSleeveCycleReason(
                            sleeve_id=entry.sleeve_id,
                            status="targeted",
                            reason=reason,
                        )
                    )
                else:
                    sleeve_reasons.append(
                        BotBrainSleeveCycleReason(
                            sleeve_id=entry.sleeve_id,
                            status="zero_target",
                            reason="Sleeve produced no positive target weight.",
                        )
                    )
            for sleeve_id, reason in portfolio_plan.sleeve_failure_reasons:
                sleeve_reasons.append(
                    BotBrainSleeveCycleReason(
                        sleeve_id=sleeve_id,
                        status="held",
                        reason=reason,
                    )
                )
        if cycle_status == "broker_unavailable":
            return BotBrainCycleExplanation(
                summary=(
                    "No trade because broker/account state was unavailable or stale."
                ),
                primary_reason_code="broker_unavailable",
                market_state="open_or_unknown",
                planner_status="not_run",
                risk_status="broker_unavailable",
                sleeve_reasons=tuple(sleeve_reasons),
            )
        if cycle_status == "data_unavailable":
            return BotBrainCycleExplanation(
                summary="No trade because market data was unavailable or stale.",
                primary_reason_code="data_unavailable",
                market_state="open_or_unknown",
                planner_status="planned" if portfolio_plan is not None else "not_run",
                risk_status="data_unavailable",
                sleeve_reasons=tuple(sleeve_reasons),
            )
        if cycle_status == "recovery_required":
            return BotBrainCycleExplanation(
                summary="No trade because recovery controls require intervention.",
                primary_reason_code="recovery_required",
                market_state="open_or_unknown",
                planner_status="planned" if portfolio_plan is not None else "not_run",
                risk_status="recovery_required",
                sleeve_reasons=tuple(sleeve_reasons),
            )
        if blocked_trade_count > 0:
            summary = "No trade because risk or execution controls blocked the order."
            risk_status = "blocked"
        elif portfolio_plan is None:
            summary = "No trade because the runtime planner did not return a plan."
            risk_status = "not_evaluated"
        elif all(
            result.terminal_state in {"held", "skipped"} for result in symbol_results
        ):
            summary = (
                "No order was submitted because the planner held or skipped every "
                "trade."
            )
            risk_status = "not_blocked"
        else:
            summary = f"Latest cycle ended as {cycle_status}."
            risk_status = "not_blocked"
        return BotBrainCycleExplanation(
            summary=summary,
            primary_reason_code=cycle_status,
            market_state="open_or_unknown",
            planner_status="planned" if portfolio_plan is not None else "no_plan",
            risk_status=risk_status,
            sleeve_reasons=tuple(sleeve_reasons),
        )

    def _get_portfolio_state_guarded(self) -> tuple[str | None, PortfolioState]:
        for _ in range(self._broker_failure_threshold):
            try:
                portfolio_state = self._portfolio.get_portfolio_state()
            except Exception as error:
                del error
                continue
            self._last_successful_broker_call_at = self._now_provider()
            self._last_known_portfolio_state = portfolio_state
            if (
                self._broker_state_age_seconds(portfolio_state)
                > self._broker_staleness_seconds
            ):
                return "broker_unavailable", portfolio_state
            return None, portfolio_state
        fallback = self._last_known_portfolio_state or self._empty_portfolio_state()
        if self._last_successful_broker_call_at is not None:
            age_seconds = int(
                (
                    self._now_provider() - self._last_successful_broker_call_at
                ).total_seconds()
            )
            if age_seconds > self._broker_staleness_seconds:
                return "broker_unavailable", fallback
        return "broker_unavailable", fallback

    def _run_legacy_symbol_cycles(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        portfolio_state: PortfolioState,
        cycle_correlation_id: str,
        initial_cycle_status: str,
    ) -> tuple[list[ServiceSymbolResult], int, int, str]:
        symbol_results: list[ServiceSymbolResult] = []
        blocked_trade_count = 0
        reconciliation_failure_count = 0
        cycle_status = initial_cycle_status
        open_symbols = {
            position.symbol
            for position in portfolio_state.positions
            if position.quantity != Decimal("0")
        }
        for symbol in symbols:
            if symbol not in open_symbols:
                continue
            result = self._loop_controller.run_trading_cycle(symbol, quantity)
            self._record_loop_result(
                result=result,
                symbol_results=symbol_results,
                cycle_correlation_id=cycle_correlation_id,
            )
            blocked_trade_count, reconciliation_failure_count, cycle_status = (
                self._accumulate_cycle_outcome(
                    result=result,
                    blocked_trade_count=blocked_trade_count,
                    reconciliation_failure_count=reconciliation_failure_count,
                    cycle_status=cycle_status,
                    cycle_correlation_id=cycle_correlation_id,
                )
            )
        for symbol in tuple(symbol for symbol in symbols if symbol not in open_symbols):
            result = self._loop_controller.run_trading_cycle(symbol, quantity)
            self._record_loop_result(
                result=result,
                symbol_results=symbol_results,
                cycle_correlation_id=cycle_correlation_id,
            )
            blocked_trade_count, reconciliation_failure_count, cycle_status = (
                self._accumulate_cycle_outcome(
                    result=result,
                    blocked_trade_count=blocked_trade_count,
                    reconciliation_failure_count=reconciliation_failure_count,
                    cycle_status=cycle_status,
                    cycle_correlation_id=cycle_correlation_id,
                )
            )
        return (
            symbol_results,
            blocked_trade_count,
            reconciliation_failure_count,
            cycle_status,
        )

    def _record_loop_result(
        self,
        *,
        result: TradingLoopResult,
        symbol_results: list[ServiceSymbolResult],
        cycle_correlation_id: str,
    ) -> None:
        del cycle_correlation_id
        symbol_results.append(
            ServiceSymbolResult(
                symbol=result.trade_intent.symbol,
                terminal_state=result.terminal_state,
                reason_code=result.trade_intent.reason_code,
                recovered=result.recovered,
                control_type=self._result_control_type(result),
            )
        )

    def _accumulate_cycle_outcome(
        self,
        *,
        result: TradingLoopResult,
        blocked_trade_count: int,
        reconciliation_failure_count: int,
        cycle_status: str,
        cycle_correlation_id: str,
    ) -> tuple[int, int, str]:
        control_type = self._result_control_type(result)
        if result.terminal_state == "blocked_trade":
            blocked_trade_count += 1
            if control_type in {"stale_market_data", "stale_quote"}:
                cycle_status = "data_unavailable"
                self._log_cycle_event(
                    event_type="data_unavailable",
                    severity="warning",
                    message="Cycle blocked by stale market data.",
                    cycle_correlation_id=cycle_correlation_id,
                    fields={"symbol": result.trade_intent.symbol},
                )
        if not result.reconciliation.resolved:
            reconciliation_failure_count += 1
            cycle_status = "recovery_required"
        return blocked_trade_count, reconciliation_failure_count, cycle_status

    def _broker_state_age_seconds(self, portfolio_state: PortfolioState) -> int:
        return max(
            0,
            int((self._now_provider() - portfolio_state.as_of_utc).total_seconds()),
        )

    def _empty_portfolio_state(self) -> PortfolioState:
        timestamp = self._now_provider()
        return PortfolioState(
            as_of_utc=timestamp,
            cash=Decimal("0"),
            equity=Decimal("0"),
            buying_power=Decimal("0"),
            positions=(),
            open_orders=(),
        )

    def _result_control_type(self, result: TradingLoopResult) -> str | None:
        if result.risk_event is not None and result.risk_event.control_type:
            return result.risk_event.control_type
        return None

    def _open_position_symbols(
        self,
        portfolio_state: PortfolioState,
    ) -> tuple[str, ...]:
        return tuple(
            position.symbol
            for position in portfolio_state.positions
            if position.quantity != Decimal("0")
        )

    def _log_cycle_event(
        self,
        *,
        event_type: str,
        severity: str,
        message: str,
        cycle_correlation_id: str,
        fields: dict[str, object],
    ) -> None:
        if self._runtime_logger is None:
            return
        self._runtime_logger.log(
            event_type=event_type,
            severity=severity,
            message=message,
            decision_snapshot_id="",
            cycle_correlation_id=cycle_correlation_id,
            fields=fields,
        )

    def _write_sleeve_decomposition_record_if_available(
        self,
        *,
        plan: RuntimePortfolioPlan,
        cycle_id: str,
        started_at: datetime,
    ) -> None:
        if not plan.per_sleeve_target_weights:
            return
        activation_getter = getattr(
            self._portfolio_planner,
            "get_active_blueprint_activation",
            None,
        )
        if not callable(activation_getter):
            return
        active_blueprint = activation_getter()
        if active_blueprint is None:
            return
        record = SleeveDecompositionRecord(
            decomposition_id=f"decomposition-{cycle_id}",
            cycle_id=cycle_id,
            trading_day=started_at.date().isoformat(),
            recorded_at_utc=self._now_provider(),
            blueprint_activation_id=active_blueprint.activation_id,
            per_sleeve_target_weights=plan.per_sleeve_target_weights,
        )
        self._runtime_state_store.write_sleeve_decomposition_record(record)

    def _maybe_narrow_blueprint_after_structural_failures(
        self,
        *,
        plan: RuntimePortfolioPlan,
        started_at: datetime,
        cycle_correlation_id: str,
    ) -> str | None:
        activation_getter = getattr(
            self._portfolio_planner,
            "get_active_blueprint_activation",
            None,
        )
        if not callable(activation_getter):
            self._sleeve_failure_streaks.clear()
            return None
        active_activation = activation_getter()
        if active_activation is None:
            self._sleeve_failure_streaks.clear()
            return None
        supersede_method = getattr(
            self._portfolio_planner,
            "supersede_active_blueprint",
            None,
        )
        if not callable(supersede_method):
            self._sleeve_failure_streaks.clear()
            return None

        failure_by_sleeve = dict(plan.sleeve_failure_reasons)
        active_sleeve_ids = {
            binding.sleeve_id
            for binding in active_activation.sleeve_activation_bindings
        }
        for sleeve_id in tuple(self._sleeve_failure_streaks):
            if sleeve_id not in active_sleeve_ids or sleeve_id not in failure_by_sleeve:
                self._sleeve_failure_streaks.pop(sleeve_id, None)

        for sleeve_id, failure_reason in failure_by_sleeve.items():
            current_reason, current_count = self._sleeve_failure_streaks.get(
                sleeve_id,
                ("", 0),
            )
            next_count = current_count + 1 if current_reason == failure_reason else 1
            self._sleeve_failure_streaks[sleeve_id] = (failure_reason, next_count)
            if next_count < 3:
                continue
            try:
                narrow_blueprint_on_sleeve_failure(
                    active_blueprint=self._active_blueprint_for_activation(
                        active_activation
                    ),
                    active_activation=active_activation,
                    failed_sleeve_id=sleeve_id,
                    failure_reason=failure_reason,
                    operator_identifier="system:service-fallback",
                    now=started_at,
                    activation_gateway=cast(
                        ActivationGatewaySupersedeProtocol,
                        self._portfolio_planner,
                    ),
                    risk_control_event_sink=self._artifacts,
                    alert_gateway=_ArtifactAlertGateway(store=self._artifacts),
                )
            except BlueprintExhaustionError as error:
                if self._operator_control_store is not None:
                    self._operator_control_store.request_halt(now=started_at)
                self._log_cycle_event(
                    event_type="blueprint_exhausted",
                    severity="warning",
                    message="Blueprint narrowing would leave zero surviving sleeves.",
                    cycle_correlation_id=cycle_correlation_id,
                    fields={
                        "error": str(error),
                        "failed_sleeve_id": sleeve_id,
                    },
                )
                self._sleeve_failure_streaks.clear()
                return "recovery_required"
            self._log_cycle_event(
                event_type="blueprint_narrowed",
                severity="warning",
                message="Blueprint narrowed after structural sleeve failure.",
                cycle_correlation_id=cycle_correlation_id,
                fields={
                    "failed_sleeve_id": sleeve_id,
                    "failure_reason": failure_reason,
                },
            )
            self._sleeve_failure_streaks.clear()
            return None
        return None

    def _active_blueprint_for_activation(
        self,
        activation: BlueprintActivationRecord,
    ) -> PortfolioBlueprint:
        blueprint = portfolio_blueprint_from_activation(activation)
        active_sleeve_ids = {
            binding.sleeve_id for binding in activation.sleeve_activation_bindings
        }
        narrowed_budgets = tuple(
            budget
            for budget in blueprint.sleeve_budgets
            if budget.sleeve_id in active_sleeve_ids
        )
        if len(narrowed_budgets) != len(active_sleeve_ids):
            raise ValueError(
                "Active blueprint activation references sleeves missing from the "
                "source blueprint file."
            )
        return dataclasses.replace(
            blueprint,
            blueprint_id=activation.blueprint_id,
            sleeve_budgets=narrowed_budgets,
        )


class _ArtifactAlertGateway:
    def __init__(self, *, store: FilesystemArtifactStore) -> None:
        self._store = store

    def publish(self, alert: OperatorAlert) -> None:
        self._store.write_operator_alert(alert)


def build_default_paper_service(
    config: TradingConfig,
    *,
    opportunity_selector: LiveOpportunitySelector | None = None,
) -> PaperTradingService:
    return build_default_trading_service(
        config,
        broker_mode="paper",
        opportunity_selector=opportunity_selector,
    )


def build_default_trading_service(
    config: TradingConfig,
    *,
    broker_mode: str | None = None,
    opportunity_selector: LiveOpportunitySelector | None = None,
) -> PaperTradingService:
    decision = resolve_broker_mode(config, explicit_mode=broker_mode)
    trading_client = build_trading_client_for_mode(config, decision)
    operator_store = FilesystemArtifactStore(
        config.runtime.artifact_root / "operator_platform"
    )
    paper_store = FilesystemArtifactStore(config.runtime.artifact_root / "paper_loop")
    runtime_store = FilesystemArtifactStore(config.runtime.artifact_root)
    market_data_gateway = build_market_data_gateway_for_mode(
        config,
        broker_mode=decision.requested_mode,
    )
    runtime_registry = build_default_runtime_registry(
        market_data_gateway=market_data_gateway,
        baseline_selector=opportunity_selector,
        vix_cache_path=config.runtime.data_root
        / "reference"
        / DEFAULT_VIX_CACHE_PATH.name,
        treasury_cache_path=config.runtime.data_root
        / "reference"
        / DEFAULT_TREASURY_YIELD_CACHE_PATH.name,
    )
    activation_gateway = LocalActivationGateway(
        store=operator_store,
        runtime_snapshot_store=runtime_store,
        strategy_id_validator=runtime_registry.can_resolve,
        promotion_decision_provider=build_artifact_promotion_decision_provider(
            _operator_promotion_root()
        ),
        required_promotion_state=PromotionState.PAPER_TRADING,
        projection_root=Path("config/strategy/promotion"),
    )
    operator_control_store = OperatorControlStore(config.runtime.data_root / "control")
    blueprint_planner = RuntimePortfolioPlanner(
        market_data=market_data_gateway,
        activation_gateway=activation_gateway,
        artifact_store=paper_store,
        runtime_state_store=runtime_store,
        operator_halt_store=operator_control_store,
        drift_alarm_gateway=ArtifactBackedDriftAlarmStateReader(store=runtime_store),
        trials_ledger=TrialsLedger(
            database_path=config.runtime.data_root / "validation" / "trials.db"
        ),
        vix_cache_path=config.runtime.data_root
        / "reference"
        / DEFAULT_VIX_CACHE_PATH.name,
        treasury_cache_path=config.runtime.data_root
        / "reference"
        / DEFAULT_TREASURY_YIELD_CACHE_PATH.name,
    )
    return PaperTradingService(
        loop_controller=build_default_trading_loop_controller(
            config,
            broker_mode=decision.requested_mode,
            strategy_id=DEFAULT_CANDIDATE_ID,
        ),
        portfolio=AlpacaPortfolioGateway(trading_client=trading_client),
        artifacts=paper_store,
        runtime_state_store=runtime_store,
        metrics=StageMetrics(namespace=config.runtime.metrics_namespace),
        regular_hours_checker=AlpacaRegularHoursCalendar().is_open,
        portfolio_planner=ActivatedRuntimePlanner(
            activation_gateway=activation_gateway,
            registry=runtime_registry,
            blueprint_planner=blueprint_planner,
        ),
        operator_control_store=operator_control_store,
        runtime_logger=build_default_runtime_logger(config, component="service"),
    )


def build_runtime_host_paper_service(config: TradingConfig) -> PaperTradingService:
    return build_runtime_host_trading_service(config, broker_mode="paper")


def build_runtime_host_trading_service(
    config: TradingConfig,
    *,
    broker_mode: str | None = None,
) -> PaperTradingService:
    operator_store = FilesystemArtifactStore(
        config.runtime.artifact_root / "operator_platform"
    )
    runtime_store = FilesystemArtifactStore(config.runtime.artifact_root)
    decision = resolve_broker_mode(config, explicit_mode=broker_mode)
    market_data_gateway = build_market_data_gateway_for_mode(
        config,
        broker_mode=decision.requested_mode,
    )
    return build_default_trading_service(
        config,
        broker_mode=decision.requested_mode,
        opportunity_selector=LiveOpportunitySelector(
            market_data_gateway=market_data_gateway,
            warmup_service=HistoricalWarmupService(
                market_data_gateway=market_data_gateway,
            ),
            activation_gateway=(
                LocalActivationGateway(
                    store=operator_store,
                    runtime_snapshot_store=runtime_store,
                    legacy_non_authority_mode=True,
                )
                if decision.requested_mode == "paper"
                else LocalActivationGateway(
                    store=operator_store,
                    runtime_snapshot_store=runtime_store,
                    promotion_decision_provider=build_artifact_promotion_decision_provider(
                        _operator_promotion_root()
                    ),
                    required_promotion_state=PromotionState.PAPER_TRADING,
                    projection_root=Path("config/strategy/promotion"),
                )
            ),
            operator_store=operator_store,
        ),
    )


__all__ = (
    "PaperTradingService",
    "build_default_trading_service",
    "build_default_paper_service",
    "build_runtime_host_trading_service",
    "build_runtime_host_paper_service",
)
