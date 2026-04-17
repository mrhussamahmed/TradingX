from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from alpaca.trading.client import TradingClient

from tradingx.config import TradingConfig
from tradingx.controller import build_default_paper_trading_controller
from tradingx.data import AlpacaRegularHoursCalendar
from tradingx.monitoring import StageMetrics
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio import AlpacaPortfolioGateway
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
    ) -> None:
        self._loop_controller = loop_controller
        self._portfolio = portfolio
        self._artifacts = artifacts
        self._metrics = metrics
        self._regular_hours_checker = regular_hours_checker
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._sleep_fn = sleep_fn or (lambda seconds: __import__("time").sleep(seconds))
        self._session_start_equity: Decimal | None = None

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
        symbol_results: list[ServiceSymbolResult] = []
        blocked_trade_count = 0
        reconciliation_failure_count = 0
        cycle_status = "market_closed"
        if self._regular_hours_checker(started_at):
            cycle_status = "executed"
            for symbol in symbols:
                result = self._loop_controller.run_trading_cycle(symbol, quantity)
                symbol_results.append(
                    ServiceSymbolResult(
                        symbol=symbol,
                        terminal_state=result.terminal_state,
                        reason_code=result.trade_intent.reason_code,
                        recovered=result.recovered,
                    )
                )
                if result.terminal_state == "blocked_trade":
                    blocked_trade_count += 1
                if not result.reconciliation.resolved:
                    reconciliation_failure_count += 1
        portfolio_state = self._portfolio.get_portfolio_state()
        if self._session_start_equity is None:
            self._session_start_equity = portfolio_state.equity
        daily_pnl = portfolio_state.equity - self._session_start_equity
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

    def _open_position_symbols(
        self,
        portfolio_state: PortfolioState,
    ) -> tuple[str, ...]:
        return tuple(
            position.symbol
            for position in portfolio_state.positions
            if position.quantity != Decimal("0")
        )


def build_default_paper_service(config: TradingConfig) -> PaperTradingService:
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
        regular_hours_checker=AlpacaRegularHoursCalendar(trading_client).is_open,
    )


__all__ = ("PaperTradingService", "build_default_paper_service")
