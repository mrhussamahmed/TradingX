from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from alpaca.trading.client import TradingClient

from tradingx.activation import LocalActivationGateway
from tradingx.config import TradingConfig
from tradingx.controller import build_default_paper_trading_controller
from tradingx.data import AlpacaRegularHoursCalendar, build_default_market_data_gateway
from tradingx.historical import HistoricalWarmupService
from tradingx.monitoring import StageMetrics
from tradingx.operator_control import OperatorControlStore
from tradingx.opportunity import LiveOpportunitySelector
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.runtime_logging import (
    StructuredRuntimeLogger,
    build_default_runtime_logger,
)
from tradingx.runtime_portfolio import RuntimePortfolioPlan
from tradingx.runtime_strategy_registry import (
    ActivatedRuntimePlanner,
    build_default_runtime_registry,
)
from tradingx.types import (
    PortfolioState,
    ServiceCycleSnapshot,
    ServiceRunResult,
    ServiceSymbolResult,
    TradingLoopResult,
)


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

    def run(
        self,
        *,
        symbols: Sequence[str],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> ServiceRunResult:
        cycles_completed = 0
        artifact_paths = []
        last_cycle: ServiceCycleSnapshot | None = None
        while max_cycles is None or cycles_completed < max_cycles:
            last_cycle = self._run_single_cycle(
                symbols=tuple(symbols),
                quantity=quantity,
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
    ) -> ServiceCycleSnapshot:
        started_at = self._now_provider()
        cycle_started_at = self._monotonic_fn()
        service_cycle_id = f"service-{uuid.uuid4()}"
        symbol_results: list[ServiceSymbolResult] = []
        blocked_trade_count = 0
        reconciliation_failure_count = 0
        cycle_status = "market_closed"
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
                    portfolio_plan = (
                        self._portfolio_planner.plan_for_service(
                            symbols=symbols,
                            portfolio_state=initial_portfolio_state,
                            default_quantity=quantity,
                        )
                        if self._portfolio_planner is not None
                        else None
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
                    self._artifacts.write_runtime_portfolio_plan(portfolio_plan)
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
                elif self._portfolio_planner is None:
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
                    cycle_status = "recovery_required"
                    self._log_cycle_event(
                        event_type="planner_no_candidate",
                        severity="warning",
                        message="Runtime planner returned no executable plan.",
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


def build_default_paper_service(
    config: TradingConfig,
    *,
    opportunity_selector: LiveOpportunitySelector | None = None,
) -> PaperTradingService:
    trading_client = TradingClient(
        config.paper_credentials.api_key,
        config.paper_credentials.api_secret,
        paper=True,
    )
    operator_store = FilesystemArtifactStore(
        config.runtime.artifact_root / "operator_platform"
    )
    market_data_gateway = build_default_market_data_gateway(config)
    runtime_registry = build_default_runtime_registry(
        market_data_gateway=market_data_gateway,
        baseline_selector=opportunity_selector,
    )
    activation_gateway = LocalActivationGateway(
        store=operator_store,
        strategy_id_validator=runtime_registry.can_resolve,
    )
    return PaperTradingService(
        loop_controller=build_default_paper_trading_controller(config),
        portfolio=AlpacaPortfolioGateway(trading_client=trading_client),
        artifacts=FilesystemArtifactStore(config.runtime.artifact_root / "paper_loop"),
        metrics=StageMetrics(namespace=config.runtime.metrics_namespace),
        regular_hours_checker=AlpacaRegularHoursCalendar().is_open,
        portfolio_planner=ActivatedRuntimePlanner(
            activation_gateway=activation_gateway,
            registry=runtime_registry,
        ),
        operator_control_store=OperatorControlStore(
            config.runtime.data_root / "control"
        ),
        runtime_logger=build_default_runtime_logger(config, component="service"),
    )


def build_runtime_host_paper_service(config: TradingConfig) -> PaperTradingService:
    operator_store = FilesystemArtifactStore(
        config.runtime.artifact_root / "operator_platform"
    )
    market_data_gateway = build_default_market_data_gateway(config)
    return build_default_paper_service(
        config,
        opportunity_selector=LiveOpportunitySelector(
            market_data_gateway=market_data_gateway,
            warmup_service=HistoricalWarmupService(
                market_data_gateway=market_data_gateway,
            ),
            activation_gateway=LocalActivationGateway(store=operator_store),
            operator_store=operator_store,
        ),
    )


__all__ = (
    "PaperTradingService",
    "build_default_paper_service",
    "build_runtime_host_paper_service",
)
