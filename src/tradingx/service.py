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
from tradingx.types import (
    OpportunitySelectionRecord,
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


class OpportunitySelectorProtocol(Protocol):
    def select_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
    ) -> OpportunitySelectionRecord: ...


class PaperTradingService:
    def __init__(
        self,
        *,
        loop_controller: TradingLoopControllerProtocol,
        portfolio: PortfolioGatewayProtocol,
        artifacts: FilesystemArtifactStore,
        metrics: StageMetrics,
        regular_hours_checker: Callable[[datetime], bool],
        opportunity_selector: OpportunitySelectorProtocol | None = None,
        now_provider: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[int], None] | None = None,
        monotonic_fn: Callable[[], float] | None = None,
        cycle_budget_seconds: int = 30,
        broker_failure_threshold: int = 2,
        broker_staleness_seconds: int = 60,
        operator_control_store: OperatorControlStore | None = None,
    ) -> None:
        self._loop_controller = loop_controller
        self._portfolio = portfolio
        self._artifacts = artifacts
        self._metrics = metrics
        self._regular_hours_checker = regular_hours_checker
        self._opportunity_selector = opportunity_selector
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._sleep_fn = sleep_fn or (lambda seconds: __import__("time").sleep(seconds))
        self._monotonic_fn = monotonic_fn or __import__("time").monotonic
        self._cycle_budget_seconds = cycle_budget_seconds
        self._broker_failure_threshold = broker_failure_threshold
        self._broker_staleness_seconds = broker_staleness_seconds
        self._operator_control_store = operator_control_store
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
        symbol_results: list[ServiceSymbolResult] = []
        blocked_trade_count = 0
        reconciliation_failure_count = 0
        cycle_status = "market_closed"
        if (
            self._operator_control_store is not None
            and self._operator_control_store.read_state().kill_requested
        ):
            portfolio_state = (
                self._last_known_portfolio_state or self._empty_portfolio_state()
            )
            cycle_status = "kill_requested"
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
            else:
                cycle_status = "executed"
                open_symbols = {
                    position.symbol
                    for position in initial_portfolio_state.positions
                    if position.quantity != Decimal("0")
                }
                for symbol in symbols:
                    if symbol not in open_symbols:
                        continue
                    result = self._loop_controller.run_trading_cycle(symbol, quantity)
                    reason_code = self._result_reason_code(result)
                    symbol_results.append(
                        ServiceSymbolResult(
                            symbol=symbol,
                            terminal_state=result.terminal_state,
                            reason_code=reason_code,
                            recovered=result.recovered,
                        )
                    )
                    if result.terminal_state == "blocked_trade":
                        blocked_trade_count += 1
                        if reason_code in {"stale_market_data", "stale_quote"}:
                            cycle_status = "data_unavailable"
                    if not result.reconciliation.resolved:
                        reconciliation_failure_count += 1
                        cycle_status = "recovery_required"
                candidate_symbols = tuple(
                    symbol for symbol in symbols if symbol not in open_symbols
                )
                if self._opportunity_selector is None:
                    for symbol in candidate_symbols:
                        result = self._loop_controller.run_trading_cycle(
                            symbol,
                            quantity,
                        )
                        reason_code = self._result_reason_code(result)
                        symbol_results.append(
                            ServiceSymbolResult(
                                symbol=symbol,
                                terminal_state=result.terminal_state,
                                reason_code=reason_code,
                                recovered=result.recovered,
                            )
                        )
                        if result.terminal_state == "blocked_trade":
                            blocked_trade_count += 1
                            if reason_code in {"stale_market_data", "stale_quote"}:
                                cycle_status = "data_unavailable"
                        if not result.reconciliation.resolved:
                            reconciliation_failure_count += 1
                            cycle_status = "recovery_required"
                elif candidate_symbols:
                    selection = self._opportunity_selector.select_for_service(
                        symbols=candidate_symbols,
                        portfolio_state=initial_portfolio_state,
                    )
                    if selection.decision == "selected" and selection.selected_symbol:
                        result = self._loop_controller.run_trading_cycle(
                            selection.selected_symbol,
                            quantity,
                        )
                        reason_code = self._result_reason_code(result)
                        symbol_results.append(
                            ServiceSymbolResult(
                                symbol=selection.selected_symbol,
                                terminal_state=result.terminal_state,
                                reason_code=reason_code,
                                recovered=result.recovered,
                            )
                        )
                        if result.terminal_state == "blocked_trade":
                            blocked_trade_count += 1
                            if reason_code in {"stale_market_data", "stale_quote"}:
                                cycle_status = "data_unavailable"
                        if not result.reconciliation.resolved:
                            reconciliation_failure_count += 1
                            cycle_status = "recovery_required"
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
        return ServiceCycleSnapshot(
            cycle_id=f"cycle-{uuid.uuid4()}",
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
        last_error: Exception | None = None
        for _ in range(self._broker_failure_threshold):
            try:
                portfolio_state = self._portfolio.get_portfolio_state()
            except Exception as error:
                last_error = error
                continue
            self._last_successful_broker_call_at = self._now_provider()
            self._last_known_portfolio_state = portfolio_state
            if (
                self._broker_state_age_seconds(portfolio_state)
                > self._broker_staleness_seconds
            ):
                return "broker_unavailable", portfolio_state
            return None, portfolio_state
        if last_error is not None:
            del last_error
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

    def _result_reason_code(self, result: TradingLoopResult) -> str:
        if result.risk_event is not None and result.risk_event.control_type:
            return result.risk_event.control_type
        return result.trade_intent.reason_code

    def _open_position_symbols(
        self,
        portfolio_state: PortfolioState,
    ) -> tuple[str, ...]:
        return tuple(
            position.symbol
            for position in portfolio_state.positions
            if position.quantity != Decimal("0")
        )


def build_default_paper_service(
    config: TradingConfig,
    *,
    opportunity_selector: OpportunitySelectorProtocol | None = None,
) -> PaperTradingService:
    trading_client = TradingClient(
        config.paper_credentials.api_key,
        config.paper_credentials.api_secret,
        paper=True,
    )
    return PaperTradingService(
        loop_controller=build_default_paper_trading_controller(config),
        portfolio=AlpacaPortfolioGateway(trading_client=trading_client),
        artifacts=FilesystemArtifactStore(config.runtime.artifact_root / "paper_loop"),
        metrics=StageMetrics(namespace=config.runtime.metrics_namespace),
        regular_hours_checker=AlpacaRegularHoursCalendar().is_open,
        opportunity_selector=opportunity_selector,
        operator_control_store=OperatorControlStore(
            config.runtime.data_root / "control"
        ),
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
