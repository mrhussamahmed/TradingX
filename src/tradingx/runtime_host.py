from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Protocol, cast

from tradingx.config import TradingConfig
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    ApprovedWeightSnapshot,
    BotRuntimeState,
    HistoricalWarmupRecord,
    OpportunitySelectionRecord,
    PortfolioState,
    ReconciliationSnapshot,
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
    ) -> tuple[StrategyActivationRecord, ApprovedWeightSnapshot]: ...

    def get_latest_activation(self) -> StrategyActivationRecord | None: ...

    def get_latest_snapshot(
        self, *, strategy_id: str
    ) -> ApprovedWeightSnapshot | None: ...


class OpportunityPlannerProtocol(Protocol):
    def plan(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        activation: StrategyActivationRecord,
        model_snapshot: ApprovedWeightSnapshot,
        warmup: HistoricalWarmupRecord,
    ) -> OpportunitySelectionRecord: ...


class PortfolioGatewayProtocol(Protocol):
    def get_portfolio_state(self) -> PortfolioState: ...


class ReconciliationGatewayProtocol(Protocol):
    def reconcile(self) -> ReconciliationSnapshot: ...


@dataclass(frozen=True)
class _PendingStartRequest:
    symbols: tuple[str, ...]
    quantity: Decimal
    interval_seconds: int
    max_cycles: int | None


SERVICE_STOP_SUCCESS_STATUSES: Final[frozenset[str]] = frozenset(
    {"accepted", "completed"}
)
ACTIVE_RUNTIME_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "bootstrapping",
        "historical_warmup",
        "broker_sync",
        "feature_ready",
        "strategy_ready",
        "trading_ready",
        "recovery_required",
        "clearance_requested",
        "reconciling",
        "nominal",
        "stopping",
    }
)


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
        reconciliation_gateway: ReconciliationGatewayProtocol | None = None,
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
        self._reconciliation_gateway = reconciliation_gateway
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._pending_start_request: _PendingStartRequest | None = None
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
            if self._state.status in ACTIVE_RUNTIME_STATUSES:
                return WebActionResult(
                    action_id=f"action-{uuid.uuid4()}",
                    action_type="runtime_host_start",
                    status="blocked",
                    message="Runtime host is already active.",
                    evidence_refs=(),
                )
            self._set_state(
                status="bootstrapping",
                status_reason="Runtime host boot sequence started.",
                active_symbols=symbols,
                started_at_utc=self._now_provider(),
                last_error="",
            )
            self._pending_start_request = _PendingStartRequest(
                symbols=symbols,
                quantity=quantity,
                interval_seconds=interval_seconds,
                max_cycles=max_cycles,
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

    def request_clearance(self) -> WebActionResult:
        with self._lock:
            if self._state.status != "recovery_required":
                return WebActionResult(
                    action_id=f"action-{uuid.uuid4()}",
                    action_type="runtime_host_clearance",
                    status="blocked",
                    message=(
                        "Runtime host is not currently awaiting operator clearance."
                    ),
                    evidence_refs=(),
                )
            self._set_state(
                status="clearance_requested",
                status_reason="Operator clearance requested. Preparing reconciliation.",
            )
            self._thread = threading.Thread(
                target=self._run_clearance_reconciliation,
                daemon=True,
            )
            self._thread.start()
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="runtime_host_clearance",
            status="accepted",
            message="Clearance request accepted. Reconciliation is running.",
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

    def trigger_hard_halt(self, *, reason: str) -> WebActionResult:
        with self._lock:
            if self._state.status == "recovery_required":
                return WebActionResult(
                    action_id=f"action-{uuid.uuid4()}",
                    action_type="runtime_host_hard_halt",
                    status="noop",
                    message="Runtime host already in recovery_required.",
                    evidence_refs=(),
                )
            try:
                stop_result = self._service_manager.stop()
            except Exception as exc:
                self._set_state(
                    status="halted",
                    status_reason="Hard halt requested; service stop raised.",
                    last_error=f"{reason}; service stop error: {exc}",
                )
                return WebActionResult(
                    action_id=f"action-{uuid.uuid4()}",
                    action_type="runtime_host_hard_halt",
                    status="error",
                    message=f"Hard halt service stop raised: {exc}",
                    evidence_refs=(),
                )
            if stop_result.status not in SERVICE_STOP_SUCCESS_STATUSES:
                self._set_state(
                    status="halted",
                    status_reason=(
                        "Hard halt requested; service stop returned "
                        f"{stop_result.status!r}."
                    ),
                    last_error=(
                        f"{reason}; service stop returned "
                        f"{stop_result.status}: {stop_result.message}"
                    ),
                )
                return WebActionResult(
                    action_id=f"action-{uuid.uuid4()}",
                    action_type="runtime_host_hard_halt",
                    status="error",
                    message=(
                        "Hard halt service stop did not succeed "
                        f"({stop_result.status}): {stop_result.message}"
                    ),
                    evidence_refs=stop_result.evidence_refs,
                )
            self._set_state(
                status="recovery_required",
                status_reason=(
                    f"Hard halt triggered: {reason}. "
                    "Service stopped; operator clearance required."
                ),
                last_error=reason,
            )
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="runtime_host_hard_halt",
            status="accepted",
            message=f"Hard halt: {reason}",
            evidence_refs=stop_result.evidence_refs,
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
            if not self._reconcile_current_state():
                return
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

    def _run_clearance_reconciliation(self) -> None:
        self._set_state(
            status="reconciling",
            status_reason="Running operator-cleared reconciliation.",
        )
        try:
            if not self._reconcile_current_state():
                return
            pending_start = self._pending_start_request
            if pending_start is not None:
                service_result = self._service_manager.start(
                    symbols=pending_start.symbols,
                    quantity=pending_start.quantity,
                    interval_seconds=pending_start.interval_seconds,
                    max_cycles=pending_start.max_cycles,
                )
                if service_result.status not in {"accepted", "completed"}:
                    raise RuntimeError(service_result.message)
            self._set_state(
                status="nominal",
                status_reason="Reconciliation cleared after operator clearance.",
                last_error="",
            )
        except Exception as exc:
            self._set_state(
                status="halted",
                status_reason="Runtime host halted during operator clearance.",
                last_error=str(exc),
            )

    def _reconcile_current_state(self) -> bool:
        if self._reconciliation_gateway is None:
            return True
        snapshot = self._reconciliation_gateway.reconcile()
        self._operator_store.write_reconciliation_snapshot(snapshot)
        if snapshot.resolved:
            self._set_state(last_error="")
            return True
        self._set_state(
            status="recovery_required",
            status_reason=(
                "Reconciliation divergence detected. New entries are blocked until "
                "operator clearance succeeds."
            ),
            last_error=self._format_reconciliation_differences(snapshot),
        )
        return False

    def _format_reconciliation_differences(
        self,
        snapshot: ReconciliationSnapshot,
    ) -> str:
        if not snapshot.differences:
            return "Reconciliation divergence detected."
        return "Reconciliation divergence detected: " + ", ".join(snapshot.differences)

    def _set_state(self, **changes: object) -> None:
        with self._lock:
            self._state = replace(
                self._state,
                updated_at_utc=self._now_provider(),
                **cast(Any, changes),
            )
            self._operator_store.write_runtime_host_state(self._state)


__all__ = ("LocalRuntimeHostManager", "SERVICE_STOP_SUCCESS_STATUSES")
