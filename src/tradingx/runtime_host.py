from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast

from tradingx.config import TradingConfig
from tradingx.learning import PostTradeLearningService
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    BotRuntimeState,
    HistoricalWarmupRecord,
    ModelWeightSnapshot,
    OpportunitySelectionRecord,
    PortfolioState,
    StrategyActivationRecord,
    WebActionResult,
)


class ServiceManagerProtocol(Protocol):
    def start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult: ...

    def stop(self) -> WebActionResult: ...


class WarmupServiceProtocol(Protocol):
    def build_warmup(
        self,
        *,
        symbols: tuple[str, ...],
        benchmark_symbol: str,
        warmup_days: int,
        required_bar_count: int,
    ) -> HistoricalWarmupRecord: ...


class ActivationGatewayProtocol(Protocol):
    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ModelWeightSnapshot]: ...

    def get_latest_activation(self) -> StrategyActivationRecord | None: ...

    def get_latest_snapshot(
        self, *, strategy_id: str
    ) -> ModelWeightSnapshot | None: ...


class OpportunityPlannerProtocol(Protocol):
    def plan(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        activation: StrategyActivationRecord,
        model_snapshot: ModelWeightSnapshot,
        warmup: HistoricalWarmupRecord,
    ) -> OpportunitySelectionRecord: ...


class PortfolioGatewayProtocol(Protocol):
    def get_portfolio_state(self) -> PortfolioState: ...


class LocalRuntimeHostManager:
    def __init__(
        self,
        *,
        config: TradingConfig,
        operator_store_root: Path,
        service_manager: ServiceManagerProtocol,
        warmup_service: WarmupServiceProtocol,
        activation_gateway: ActivationGatewayProtocol,
        opportunity_planner: OpportunityPlannerProtocol,
        portfolio_gateway: PortfolioGatewayProtocol,
        learning_service: PostTradeLearningService | None = None,
        paper_store_root: Path | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._operator_store = FilesystemArtifactStore(operator_store_root)
        self._paper_store = FilesystemArtifactStore(
            paper_store_root or (config.runtime.artifact_root / "paper_loop")
        )
        self._service_manager = service_manager
        self._warmup_service = warmup_service
        self._activation_gateway = activation_gateway
        self._opportunity_planner = opportunity_planner
        self._portfolio_gateway = portfolio_gateway
        self._learning_service = learning_service or PostTradeLearningService()
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._state = BotRuntimeState(
            status="idle",
            status_reason="Runtime host is idle.",
            active_symbols=(),
            started_at_utc=None,
            updated_at_utc=self._now_provider(),
            last_error="",
            active_strategy_id="",
            active_model_snapshot_id="",
            latest_selection_id="",
        )

    def get_state(self) -> BotRuntimeState:
        with self._lock:
            return self._state

    def start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return WebActionResult(
                    action_id=f"action-{uuid.uuid4()}",
                    action_type="runtime_host_start",
                    status="blocked",
                    message="Runtime host is already starting or running.",
                    evidence_refs=(),
                )
            self._set_state(
                status="bootstrapping",
                status_reason="Runtime host boot sequence started.",
                active_symbols=symbols,
                started_at_utc=self._now_provider(),
                last_error="",
            )
            self._thread = threading.Thread(
                target=self._bootstrap_and_start,
                kwargs={
                    "symbols": symbols,
                    "quantity": quantity,
                    "interval_seconds": interval_seconds,
                    "max_cycles": max_cycles,
                },
                daemon=True,
            )
            self._thread.start()
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="runtime_host_start",
            status="accepted",
            message="Runtime host start accepted.",
            evidence_refs=(),
        )

    def stop(self) -> WebActionResult:
        self._set_state(
            status="stopping",
            status_reason="Runtime host stop requested.",
        )
        result = self._service_manager.stop()
        self._set_state(
            status="idle",
            status_reason="Runtime host stopped.",
        )
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="runtime_host_stop",
            status=result.status,
            message="Runtime host stop requested.",
            evidence_refs=result.evidence_refs,
        )

    def generate_learning_proposal(self) -> WebActionResult:
        activation = self._activation_gateway.get_latest_activation()
        if activation is None:
            return WebActionResult(
                action_id=f"action-{uuid.uuid4()}",
                action_type="runtime_host_learn",
                status="blocked",
                message="No active strategy activation record is available.",
                evidence_refs=(),
            )
        snapshot = self._activation_gateway.get_latest_snapshot(
            strategy_id=activation.strategy_id
        )
        if snapshot is None:
            return WebActionResult(
                action_id=f"action-{uuid.uuid4()}",
                action_type="runtime_host_learn",
                status="blocked",
                message="No approved model-weight snapshot is available.",
                evidence_refs=(),
            )
        proposal = self._learning_service.generate_from_artifact_store(
            paper_store=self._paper_store,
            activation=activation,
            baseline_snapshot=snapshot,
            minimum_supporting_trades=snapshot.minimum_supporting_trades,
        )
        if proposal is None:
            return WebActionResult(
                action_id=f"action-{uuid.uuid4()}",
                action_type="runtime_host_learn",
                status="completed",
                message=(
                    "No statistically significant learning proposal is available yet."
                ),
                evidence_refs=(),
            )
        proposal_path = self._operator_store.write_model_weight_proposal(proposal)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="runtime_host_learn",
            status="completed",
            message="Learning proposal generated.",
            evidence_refs=(str(proposal_path),),
        )

    def _bootstrap_and_start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None,
    ) -> None:
        try:
            activation, snapshot = (
                self._activation_gateway.load_or_create_active_records(symbols)
            )
            self._set_state(
                status="historical_warmup",
                status_reason="Building historical warmup.",
                active_strategy_id=activation.strategy_id,
                active_model_snapshot_id=snapshot.snapshot_id,
            )
            warmup = self._warmup_service.build_warmup(
                symbols=symbols,
                benchmark_symbol="SPY",
                warmup_days=60,
                required_bar_count=30,
            )
            self._operator_store.write_historical_warmup_record(warmup)
            missing_symbols = tuple(
                symbol for symbol in symbols if symbol not in warmup.symbols_ready
            )
            if missing_symbols:
                raise RuntimeError(
                    "Warmup incomplete for symbols: " + ", ".join(missing_symbols)
                )
            self._set_state(
                status="broker_sync",
                status_reason="Broker state synchronized.",
            )
            portfolio_state = self._portfolio_gateway.get_portfolio_state()
            self._set_state(
                status="feature_ready",
                status_reason="Warmup and market features are ready.",
            )
            selection = self._opportunity_planner.plan(
                symbols=symbols,
                portfolio_state=portfolio_state,
                activation=activation,
                model_snapshot=snapshot,
                warmup=warmup,
            )
            self._operator_store.write_opportunity_selection_record(selection)
            self._set_state(
                status="strategy_ready",
                status_reason="Strategy activation is loaded.",
                latest_selection_id=selection.selection_id,
            )
            service_result = self._service_manager.start(
                symbols=symbols,
                quantity=quantity,
                interval_seconds=interval_seconds,
                max_cycles=max_cycles,
            )
            if service_result.status not in {"accepted", "completed"}:
                raise RuntimeError(service_result.message)
            self._set_state(
                status="trading_ready",
                status_reason="Runtime boot complete.",
            )
        except Exception as exc:
            self._set_state(
                status="halted",
                status_reason="Runtime host halted.",
                last_error=str(exc),
            )

    def _set_state(self, **changes: object) -> None:
        with self._lock:
            self._state = replace(
                self._state,
                updated_at_utc=self._now_provider(),
                **cast(Any, changes),
            )
            self._operator_store.write_runtime_host_state(self._state)


__all__ = ("LocalRuntimeHostManager",)
