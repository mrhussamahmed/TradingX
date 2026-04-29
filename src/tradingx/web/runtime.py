from __future__ import annotations

import json
import threading
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from tradingx.activation import LocalActivationGateway
from tradingx.alerts import (
    OperatorAlertDispatcher,
    SmtpAlertTransport,
    TelegramAlertTransport,
    build_gate_decision_alert,
)
from tradingx.automation import (
    MarketDayAutomationRunner,
    build_default_market_day_automation_runner,
)
from tradingx.benchmark_stack import build_default_benchmark_stack
from tradingx.config import TradingConfig
from tradingx.controller import (
    build_default_gate_validation_controller,
    build_default_paper_trading_controller,
)
from tradingx.data import AlpacaRegularHoursCalendar, build_market_data_gateway_for_mode
from tradingx.experiments import ExperimentLedger, resolve_metric_visibility_context
from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.historical import HistoricalWarmupService
from tradingx.live_enablement import (
    build_trading_client_for_mode,
    resolve_broker_mode,
)
from tradingx.opportunity import RuntimeOpportunityPlanner
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.promotion import (
    LEGACY_NON_AUTHORITY_STATUS,
    PromotionState,
    build_artifact_promotion_decision_provider,
)
from tradingx.replay_slippage import generate_replay_slippage_evidence
from tradingx.reporting import build_gate_decision_brief
from tradingx.risk_free import build_default_risk_free_series
from tradingx.runtime_host import LocalRuntimeHostManager
from tradingx.scheduler import MarketDayScheduler, build_default_market_day_scheduler
from tradingx.service import (
    PaperTradingService,
    build_default_trading_service,
    build_runtime_host_trading_service,
)
from tradingx.sizing import RuntimeSizingPolicy
from tradingx.types import (
    AlertDrillRecord,
    BotRuntimeState,
    ConfigProposal,
    MarketDaySchedulerState,
    MarketSessionRecord,
    OperatorAlert,
    RecoveryDrillRecord,
    WebActionResult,
    WebServiceState,
)
from tradingx.validation import (
    load_benchmark_stack_payload,
    write_benchmark_stack_payload,
)
from tradingx.web.readmodels import LocalWebReadModel


class ServiceBuilderProtocol(Protocol):
    def __call__(self) -> PaperTradingService: ...


class AutomationRunnerBuilderProtocol(Protocol):
    def __call__(self) -> MarketDayAutomationRunner: ...


class SchedulerBuilderProtocol(Protocol):
    def __call__(self) -> MarketDayScheduler: ...


class RuntimeHostManagerProtocol(Protocol):
    def get_state(self) -> BotRuntimeState: ...

    def start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> WebActionResult: ...

    def stop(self) -> WebActionResult: ...


class LocalServiceManager:
    def __init__(
        self,
        *,
        config: TradingConfig,
        service_builder: ServiceBuilderProtocol | None = None,
    ) -> None:
        self._config = config
        self._service_builder = service_builder or (
            lambda: build_default_trading_service(config)
        )
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state = WebServiceState(
            status="idle",
            active_symbols=(),
            interval_seconds=config.runtime.service_interval_seconds,
            cycles_completed=0,
            started_at_utc=None,
            last_completed_at_utc=None,
            last_error="",
        )

    def get_state(self) -> WebServiceState:
        with self._lock:
            return self._state

    def start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> WebActionResult:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return WebActionResult(
                    action_id=f"action-{uuid.uuid4()}",
                    action_type="paper_service_start",
                    status="blocked",
                    message="Paper service is already running.",
                    evidence_refs=(),
                )
            self._stop_event.clear()
            self._state = WebServiceState(
                status="running",
                active_symbols=symbols,
                interval_seconds=interval_seconds,
                cycles_completed=self._state.cycles_completed,
                started_at_utc=datetime.now(UTC),
                last_completed_at_utc=self._state.last_completed_at_utc,
                last_error="",
            )
            self._thread = threading.Thread(
                target=self._run_service_loop,
                kwargs={
                    "symbols": symbols,
                    "quantity": quantity,
                    "interval_seconds": interval_seconds,
                    "max_cycles": max_cycles,
                    "sizing_policy": sizing_policy,
                },
                daemon=True,
            )
            self._thread.start()
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="paper_service_start",
            status="accepted",
            message="Paper service started.",
            evidence_refs=(),
        )

    def stop(self) -> WebActionResult:
        self._stop_event.set()
        with self._lock:
            self._state = replace(self._state, status="stopping")
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="paper_service_stop",
            status="accepted",
            message="Paper service stop requested.",
            evidence_refs=(),
        )

    def _run_service_loop(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> None:
        service = self._service_builder()
        cycles_completed = 0
        try:
            while not self._stop_event.is_set() and (
                max_cycles is None or cycles_completed < max_cycles
            ):
                if sizing_policy is None:
                    result = service.run(
                        symbols=symbols,
                        quantity=quantity,
                        interval_seconds=interval_seconds,
                        max_cycles=1,
                    )
                else:
                    result = service.run(
                        symbols=symbols,
                        quantity=quantity,
                        interval_seconds=interval_seconds,
                        max_cycles=1,
                        sizing_policy=sizing_policy,
                    )
                cycles_completed += result.cycles_completed
                with self._lock:
                    self._state = replace(
                        self._state,
                        cycles_completed=self._state.cycles_completed + 1,
                        last_completed_at_utc=result.last_cycle.completed_at_utc,
                    )
                if max_cycles is not None and cycles_completed >= max_cycles:
                    break
                if self._stop_event.wait(interval_seconds):
                    break
        except Exception as exc:
            with self._lock:
                self._state = replace(self._state, status="error", last_error=str(exc))
            return
        with self._lock:
            self._state = replace(
                self._state,
                status="stopped" if self._stop_event.is_set() else "idle",
            )


class LocalSchedulerManager:
    def __init__(
        self,
        *,
        config: TradingConfig,
        scheduler_builder: SchedulerBuilderProtocol | None = None,
    ) -> None:
        self._config = config
        self._scheduler_builder = scheduler_builder or (
            lambda: build_default_market_day_scheduler(config)
        )
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state = MarketDaySchedulerState(
            status="idle",
            poll_interval_seconds=config.runtime.scheduler_poll_seconds,
            active_symbols=(),
            next_run_at_utc=None,
            last_started_at_utc=None,
            last_completed_at_utc=None,
            active_trading_day="",
            last_error="",
        )

    def get_state(self) -> MarketDaySchedulerState:
        with self._lock:
            return self._state

    def start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        poll_interval_seconds: int,
        max_scheduled_days: int | None = None,
    ) -> WebActionResult:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return WebActionResult(
                    action_id=f"action-{uuid.uuid4()}",
                    action_type="market_scheduler_start",
                    status="blocked",
                    message="Market-day scheduler is already running.",
                    evidence_refs=(),
                )
            self._stop_event.clear()
            self._state = MarketDaySchedulerState(
                status="waiting",
                poll_interval_seconds=poll_interval_seconds,
                active_symbols=symbols,
                next_run_at_utc=None,
                last_started_at_utc=self._state.last_started_at_utc,
                last_completed_at_utc=self._state.last_completed_at_utc,
                active_trading_day=self._state.active_trading_day,
                last_error="",
            )
            self._thread = threading.Thread(
                target=self._run_scheduler_loop,
                kwargs={
                    "symbols": symbols,
                    "quantity": quantity,
                    "interval_seconds": interval_seconds,
                    "poll_interval_seconds": poll_interval_seconds,
                    "max_scheduled_days": max_scheduled_days,
                },
                daemon=True,
            )
            self._thread.start()
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="market_scheduler_start",
            status="accepted",
            message="Market-day scheduler started.",
            evidence_refs=(),
        )

    def stop(self) -> WebActionResult:
        self._stop_event.set()
        with self._lock:
            self._state = replace(self._state, status="stopping")
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="market_scheduler_stop",
            status="accepted",
            message="Market-day scheduler stop requested.",
            evidence_refs=(),
        )

    def _run_scheduler_loop(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        poll_interval_seconds: int,
        max_scheduled_days: int | None,
    ) -> None:
        scheduler = self._scheduler_builder()
        try:
            scheduler.run(
                symbols=symbols,
                quantity=quantity,
                interval_seconds=interval_seconds,
                poll_interval_seconds=poll_interval_seconds,
                max_scheduled_days=max_scheduled_days,
                stop_event=self._stop_event,
                state_callback=self._update_state,
            )
        except Exception as exc:
            with self._lock:
                self._state = replace(self._state, status="error", last_error=str(exc))
            return
        with self._lock:
            if self._stop_event.is_set():
                self._state = replace(self._state, status="stopped")
            elif self._state.status != "error":
                self._state = replace(self._state, status="idle")

    def _update_state(self, state: MarketDaySchedulerState) -> None:
        with self._lock:
            self._state = state


class LocalWebActionRunner:
    def __init__(
        self,
        *,
        config: TradingConfig,
        repo_root: Path,
        service_manager: LocalServiceManager,
        runtime_host_manager: RuntimeHostManagerProtocol | None = None,
        scheduler_manager: LocalSchedulerManager | None = None,
        automation_runner_builder: AutomationRunnerBuilderProtocol | None = None,
    ) -> None:
        self._config = config
        self._repo_root = repo_root
        self._service_manager = service_manager
        self._runtime_host_manager = runtime_host_manager
        self._scheduler_manager = scheduler_manager or LocalSchedulerManager(
            config=config
        )
        self._automation_runner_builder = automation_runner_builder or (
            lambda: build_default_market_day_automation_runner(config)
        )
        self._paper_store = FilesystemArtifactStore(
            self._config.runtime.artifact_root / "paper_loop"
        )
        self._validation_store = FilesystemArtifactStore(
            self._config.runtime.artifact_root / "validation"
        )
        self._operator_platform_root = (
            self._config.runtime.artifact_root / "operator_platform"
        )
        self._operator_platform_store = FilesystemArtifactStore(
            self._operator_platform_root
        )

    def run_paper_loop(self, *, symbol: str, quantity: str) -> WebActionResult:
        controller = build_default_paper_trading_controller(self._config)
        result = controller.run_trading_cycle(symbol, Decimal(quantity))
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="paper_loop",
            status="completed",
            message=f"Ran a paper trading cycle for {symbol}.",
            evidence_refs=tuple(str(path) for path in result.artifact_paths),
        )

    def run_paper_recover(self, *, symbol: str) -> WebActionResult:
        controller = build_default_paper_trading_controller(self._config)
        result = controller.recover_trading_cycle(symbol)
        evidence_refs: tuple[str, ...] = ()
        if result is not None:
            evidence_refs = tuple(str(path) for path in result.artifact_paths)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="paper_recover",
            status="completed",
            message=f"Recovery check completed for {symbol}.",
            evidence_refs=evidence_refs,
        )

    def start_service(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> WebActionResult:
        if sizing_policy is None:
            return self._service_manager.start(
                symbols=symbols,
                quantity=Decimal(quantity),
                interval_seconds=interval_seconds,
                max_cycles=max_cycles,
            )
        return self._service_manager.start(
            symbols=symbols,
            quantity=Decimal(quantity),
            interval_seconds=interval_seconds,
            max_cycles=max_cycles,
            sizing_policy=sizing_policy,
        )

    def stop_service(self) -> WebActionResult:
        return self._service_manager.stop()

    def start_runtime_host(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> WebActionResult:
        if self._runtime_host_manager is None:
            return WebActionResult(
                action_id=f"action-{uuid.uuid4()}",
                action_type="runtime_host_start",
                status="blocked",
                message="Runtime host manager is unavailable.",
                evidence_refs=(),
            )
        if sizing_policy is None:
            return self._runtime_host_manager.start(
                symbols=symbols,
                quantity=Decimal(quantity),
                interval_seconds=interval_seconds,
                max_cycles=max_cycles,
            )
        return self._runtime_host_manager.start(
            symbols=symbols,
            quantity=Decimal(quantity),
            interval_seconds=interval_seconds,
            max_cycles=max_cycles,
            sizing_policy=sizing_policy,
        )

    def stop_runtime_host(self) -> WebActionResult:
        if self._runtime_host_manager is None:
            return WebActionResult(
                action_id=f"action-{uuid.uuid4()}",
                action_type="runtime_host_stop",
                status="blocked",
                message="Runtime host manager is unavailable.",
                evidence_refs=(),
            )
        return self._runtime_host_manager.stop()

    def start_market_scheduler(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        poll_interval_seconds: int,
        max_scheduled_days: int | None = None,
    ) -> WebActionResult:
        return self._scheduler_manager.start(
            symbols=symbols,
            quantity=Decimal(quantity),
            interval_seconds=interval_seconds,
            poll_interval_seconds=poll_interval_seconds,
            max_scheduled_days=max_scheduled_days,
        )

    def stop_market_scheduler(self) -> WebActionResult:
        return self._scheduler_manager.stop()

    def prepare_benchmark(
        self,
        *,
        window_start: str,
        window_end: str,
    ) -> WebActionResult:
        decision = resolve_broker_mode(self._config)
        market_data_gateway = build_market_data_gateway_for_mode(
            self._config,
            broker_mode=decision.requested_mode,
        )
        risk_free_series = build_default_risk_free_series(self._config)
        stack = build_default_benchmark_stack(
            self._config,
            market_data_gateway=market_data_gateway,
            risk_free_series=risk_free_series,
        )
        window_start_utc = datetime.fromisoformat(window_start).replace(tzinfo=UTC)
        window_end_utc = datetime.fromisoformat(window_end).replace(tzinfo=UTC)
        session_dates = AlpacaRegularHoursCalendar().session_dates_between(
            window_start_utc,
            window_end_utc,
        )
        payload = stack.materialize(session_dates=session_dates)
        output_file = (
            self._config.runtime.artifact_root
            / "validation"
            / "benchmark_stacks"
            / (
                "stack-"
                f"{window_start_utc.date().isoformat()}-"
                f"{window_end_utc.date().isoformat()}.json"
            )
        )
        write_benchmark_stack_payload(output_file, payload)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="prepare_benchmark",
            status="completed",
            message=(
                "Prepared benchmark stack "
                "(cash hurdle + 60/40 + operating constraint)."
            ),
            evidence_refs=(str(output_file),),
        )

    def generate_gate_report(
        self,
        *,
        gate: str,
        benchmark_stack_file: str,
        window_start: str,
        window_end: str,
        universe: tuple[str, ...] = (),
        experiment_id: str | None = None,
        run_id: str | None = None,
        promotion_decision_scope: str | None = None,
        metric_release_token: str | None = None,
        dataset_manifest_id: str | None = None,
        dataset_manifest_file: str | None = None,
    ) -> WebActionResult:
        benchmark_path = self._resolve_artifact_path(Path(benchmark_stack_file))
        controller = build_default_gate_validation_controller(
            self._config,
            artifact_root=self._config.runtime.artifact_root / "validation",
        )
        window_start_utc = datetime.fromisoformat(window_start).replace(tzinfo=UTC)
        window_end_utc = datetime.fromisoformat(window_end).replace(tzinfo=UTC)
        benchmark_stack_payload = load_benchmark_stack_payload(benchmark_path)
        metric_visibility_context = None
        if experiment_id:
            metric_visibility_context, resolved_dataset_manifest_id = (
                resolve_metric_visibility_context(
                    experiment_id=experiment_id,
                    run_id=run_id or "",
                    promotion_decision_scope=promotion_decision_scope or "",
                    metric_release_token_ref=metric_release_token or "",
                    ledger=ExperimentLedger(
                        ledger_root=self._config.runtime.artifact_root / "experiments"
                    ),
                    dataset_manifest_path=(
                        self._resolve_artifact_path(Path(dataset_manifest_file))
                        if dataset_manifest_file
                        else None
                    ),
                    dataset_manifest_id=dataset_manifest_id,
                )
            )
            if resolved_dataset_manifest_id:
                dataset_manifest_id = resolved_dataset_manifest_id
        result = controller.generate_gate_report(
            gate_id=gate,
            benchmark_stack_payload=benchmark_stack_payload,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            universe=universe or self._config.runtime.symbol_universe,
            metric_visibility_context=metric_visibility_context,
            dataset_manifest_id=dataset_manifest_id,
        )
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="gate_report",
            status="completed",
            message=(
                f"Generated Gate {gate} report " f"({LEGACY_NON_AUTHORITY_STATUS})."
            ),
            evidence_refs=tuple(str(path) for path in result.artifact_paths),
        )

    def _resolve_artifact_path(self, candidate: Path) -> Path:
        artifact_root = self._config.runtime.artifact_root
        if not artifact_root.is_absolute():
            artifact_root = (self._repo_root / artifact_root).resolve()
        else:
            artifact_root = artifact_root.resolve()
        resolved = candidate.expanduser()
        if not resolved.is_absolute():
            resolved = (self._repo_root / resolved).resolve()
        else:
            resolved = resolved.resolve()
        try:
            resolved.relative_to(artifact_root)
        except ValueError as error:
            raise ValueError(
                "Benchmark closes file must resolve under the artifact root."
            ) from error
        return resolved

    def generate_decision_report(self, *, gate: str | None) -> WebActionResult:
        brief = build_gate_decision_brief(
            validation_store=FilesystemArtifactStore(
                self._config.runtime.artifact_root / "validation"
            ),
            paper_store=FilesystemArtifactStore(
                self._config.runtime.artifact_root / "paper_loop"
            ),
            gate_id=gate,
        )
        alert = build_gate_decision_alert(brief)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="decision_report",
            status="completed",
            message=f"{alert.summary} ({LEGACY_NON_AUTHORITY_STATUS}).",
            evidence_refs=brief.evidence_refs,
        )

    def create_config_proposal(
        self,
        *,
        target_area: str,
        proposed_values: dict[str, object],
        rationale: str,
    ) -> ConfigProposal:
        proposal_id = f"proposal-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        proposal_dir = self._repo_root / "config" / "proposals"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        output_path = proposal_dir / f"{proposal_id}.md"
        diff_preview = "\n".join(
            f"+ {key}={value}" for key, value in proposed_values.items()
        )
        output_path.write_text(
            "\n".join(
                [
                    f"# {proposal_id}",
                    "",
                    f"Target area: {target_area}",
                    "",
                    "## Rationale",
                    rationale,
                    "",
                    "## Proposed values",
                    diff_preview,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return ConfigProposal(
            proposal_id=proposal_id,
            target_area=target_area,
            proposed_values=proposed_values,
            diff_preview=diff_preview,
            output_path=output_path,
        )

    def run_session_preopen(self) -> WebActionResult:
        return self._automation_runner_builder().run_preopen()

    def run_session_heartbeat(self) -> WebActionResult:
        return self._automation_runner_builder().run_heartbeat(
            symbols=self._config.runtime.symbol_universe,
            quantity=Decimal("1"),
            interval_seconds=self._config.runtime.service_interval_seconds,
        )

    def run_session_close(self) -> WebActionResult:
        return self._automation_runner_builder().run_close()

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_heartbeats: int | None,
    ) -> WebActionResult:
        result = self._automation_runner_builder().run_market_day(
            symbols=symbols,
            quantity=Decimal(quantity),
            interval_seconds=interval_seconds,
            max_heartbeats=max_heartbeats,
        )
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="market_day_run",
            status=result.run_record.status,
            message=f"Market-day automation: {result.run_record.summary}",
            evidence_refs=(str(result.run_record_path),),
        )

    def run_recovery_drill(self, *, symbol: str) -> WebActionResult:
        started_at = datetime.now(UTC)
        result = None
        status = "pending"
        summary = f"No recoverable cycle was found for {symbol}."
        evidence_refs: tuple[str, ...] = ()
        try:
            controller = build_default_paper_trading_controller(self._config)
            result = controller.recover_trading_cycle(symbol)
        except Exception:
            summary = f"Recovery drill could not run for {symbol}."
        else:
            if result is not None:
                status = "completed"
                summary = f"Recovery drill completed for {symbol}."
                evidence_refs = tuple(str(path) for path in result.artifact_paths)
        recovery = RecoveryDrillRecord(
            drill_id=f"recovery-{started_at.strftime('%Y%m%d%H%M%S')}",
            symbol=symbol,
            started_at_utc=started_at,
            completed_at_utc=datetime.now(UTC),
            status=status,
            summary=summary,
            evidence_refs=evidence_refs,
        )
        output_path = self._paper_store.write_recovery_drill_record(recovery)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="recovery_drill",
            status=status,
            message=summary,
            evidence_refs=(str(output_path),) + evidence_refs,
        )

    def run_alert_drill(self, *, channel: str) -> WebActionResult:
        recorded_at = datetime.now(UTC)
        channel_normalized = channel.strip().lower() or "smtp"
        dispatcher = self._dispatcher_for_channel(channel_normalized)
        evidence_refs: tuple[str, ...] = ()
        status = "pending"
        summary = f"{channel_normalized.upper()} alert drill is not configured."
        if dispatcher is not None:
            alert = dispatcher.dispatch(
                OperatorAlert(
                    alert_id=f"alert-drill-{channel_normalized}-{recorded_at.strftime('%Y%m%d%H%M%S')}",
                    severity="critical",
                    category="operations",
                    summary=f"Gate 3 {channel_normalized.upper()} alert drill",
                    evidence_refs=(),
                    delivery_targets=(),
                    sent_at_utc=recorded_at,
                )
            )
            if channel_normalized in alert.delivery_targets:
                alert_path = self._paper_store.write_operator_alert(alert)
                evidence_refs = (str(alert_path),)
                status = "completed"
                summary = f"{channel_normalized.upper()} alert drill completed."
            else:
                status = "fail"
                summary = f"{channel_normalized.upper()} alert drill did not deliver."
        drill = AlertDrillRecord(
            drill_id=f"alert-{channel_normalized}-{recorded_at.strftime('%Y%m%d%H%M%S')}",
            channel=channel_normalized,
            recorded_at_utc=recorded_at,
            status=status,
            summary=summary,
            evidence_refs=evidence_refs,
        )
        output_path = self._paper_store.write_alert_drill_record(drill)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="alert_drill",
            status=status,
            message=summary,
            evidence_refs=(str(output_path),) + evidence_refs,
        )

    def generate_gate3_report(self) -> WebActionResult:
        report = build_gate3_readiness_report(
            paper_store=self._paper_store,
            validation_store=self._validation_store,
        )
        output_path = self._validation_store.write_gate3_readiness_report(report)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="gate3_report",
            status="completed",
            message=(
                "Gate 3 readiness report generated " f"({LEGACY_NON_AUTHORITY_STATUS})."
            ),
            evidence_refs=(str(output_path),),
        )

    def generate_gate3_package(self) -> WebActionResult:
        report = build_gate3_readiness_report(
            paper_store=self._paper_store,
            validation_store=self._validation_store,
        )
        report_path = self._validation_store.write_gate3_readiness_report(report)
        package = build_gate3_promotion_package(report)
        package_path = self._validation_store.write_gate3_promotion_package(package)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="gate3_package",
            status="completed",
            message=(
                "Gate 3 promotion package generated "
                f"({LEGACY_NON_AUTHORITY_STATUS})."
            ),
            evidence_refs=(str(report_path), str(package_path)),
        )

    def generate_replay_slippage_report(self) -> WebActionResult:
        result = generate_replay_slippage_evidence(
            paper_store=self._paper_store,
            validation_store=self._validation_store,
        )
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="replay_slippage_report",
            status=result.summary.status,
            message="Replay slippage report generated.",
            evidence_refs=(
                *(str(path) for path in result.record_paths),
                str(result.summary_path),
            ),
        )

    def acknowledge_incident(self, *, incident_id: str) -> WebActionResult:
        acknowledgement_dir = self._operator_platform_root / "incident_acknowledgements"
        acknowledgement_dir.mkdir(parents=True, exist_ok=True)
        output_path = acknowledgement_dir / f"{incident_id}.json"
        payload = {
            "incident_id": incident_id,
            "acknowledged_at_utc": datetime.now(UTC).isoformat(),
            "acknowledged_by": "local-operator",
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="incident_acknowledge",
            status="completed",
            message=f"Acknowledged {incident_id}.",
            evidence_refs=(str(output_path),),
        )

    def _write_daily_digest(self, *, session_label: str) -> WebActionResult:
        daily_digest_dir = self._operator_platform_root / "daily_digests"
        daily_digest_dir.mkdir(parents=True, exist_ok=True)
        generated_at = datetime.now(UTC)
        digest_id = f"digest-{generated_at.strftime('%Y%m%d%H%M%S')}-{session_label}"
        paper_report = self._paper_store.build_operator_evidence_report()
        summary_payload = paper_report.get("summary", {})
        paper_summary = summary_payload if isinstance(summary_payload, dict) else {}
        latest_alerts = self._paper_store.list_artifact_payloads("operator_alerts")[-3:]
        payload = {
            "digest_id": digest_id,
            "generated_at_utc": generated_at.isoformat(),
            "session_label": session_label,
            "service_status": self._service_manager.get_state().status,
            "blocked_trade_count": int(paper_summary.get("blocked_trade_count", 0)),
            "reconciliation_failure_count": int(
                paper_summary.get("reconciliation_failure_count", 0)
            ),
            "latest_positions": list(paper_summary.get("latest_open_positions", ())),
            "top_incidents": [
                f"incident-{payload.get('alert_id', '')}"
                for payload in latest_alerts
                if str(payload.get("alert_id", "")).strip()
            ],
            "recommended_actions": self._recommended_actions(),
            "evidence_refs": self._digest_evidence_refs(),
        }
        blocked_trade_count = int(str(payload["blocked_trade_count"]))
        reconciliation_failure_count = int(str(payload["reconciliation_failure_count"]))
        latest_positions = self._string_items(payload["latest_positions"])
        top_incidents = self._string_items(payload["top_incidents"])
        recommended_actions = self._string_items(payload["recommended_actions"])
        evidence_refs = self._string_items(payload["evidence_refs"])
        output_path = daily_digest_dir / f"{digest_id}.json"
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._operator_platform_store.write_market_session_record(
            MarketSessionRecord(
                session_id=digest_id,
                session_label=session_label,
                recorded_at_utc=generated_at,
                service_status=str(payload["service_status"]),
                blocked_trade_count=blocked_trade_count,
                reconciliation_failure_count=reconciliation_failure_count,
                open_positions=tuple(latest_positions),
                top_incidents=tuple(top_incidents),
                recommended_actions=tuple(recommended_actions),
                evidence_refs=tuple(evidence_refs),
            )
        )
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type=session_label,
            status="completed",
            message=self._digest_message(session_label),
            evidence_refs=(str(output_path),),
        )

    def _dispatcher_for_channel(
        self,
        channel: str,
    ) -> OperatorAlertDispatcher | None:
        if channel == "smtp" and self._config.alerting.smtp_enabled():
            return OperatorAlertDispatcher(
                transports=(
                    SmtpAlertTransport(
                        host=self._config.alerting.smtp_host,
                        port=self._config.alerting.smtp_port,
                        username=self._config.alerting.smtp_username,
                        password=self._config.alerting.smtp_password,
                        from_email=self._config.alerting.smtp_from_email,
                        to_email=self._config.alerting.smtp_to_email,
                        use_starttls=self._config.alerting.smtp_use_starttls,
                    ),
                )
            )
        if channel == "telegram" and self._config.alerting.telegram_enabled():
            return OperatorAlertDispatcher(
                transports=(
                    TelegramAlertTransport(
                        bot_token=self._config.alerting.telegram_bot_token,
                        chat_id=self._config.alerting.telegram_chat_id,
                    ),
                )
            )
        return None

    def _recommended_actions(self) -> list[str]:
        recommendations: list[str] = []
        gate_assessments = self._validation_store.list_artifact_payloads(
            "gate_assessments"
        )
        latest_gate = gate_assessments[-1] if gate_assessments else None
        if latest_gate is not None:
            recommendations.append(str(latest_gate.get("decision_summary", "")))
        service_state = self._service_manager.get_state()
        if service_state.last_error:
            recommendations.append(
                "Review the latest service error before the next cycle."
            )
        if not recommendations:
            recommendations.append(
                "Continue collecting paper evidence and review incidents."
            )
        return recommendations

    def _digest_evidence_refs(self) -> list[str]:
        refs: list[str] = []
        paper_cycles = self._paper_store.list_artifact_payloads("service_cycles")
        if paper_cycles:
            latest_cycle = paper_cycles[-1]
            cycle_id = str(latest_cycle.get("cycle_id", "")).strip()
            if cycle_id:
                refs.append(
                    str(
                        self._config.runtime.artifact_root
                        / "paper_loop"
                        / "service_cycles"
                        / f"{cycle_id}.json"
                    )
                )
        gate_assessments = self._validation_store.list_artifact_payloads(
            "gate_assessments"
        )
        if gate_assessments:
            gate_id = str(gate_assessments[-1].get("gate_id", "")).strip()
            if gate_id:
                refs.append(
                    str(
                        self._config.runtime.artifact_root
                        / "validation"
                        / "gate_assessments"
                        / f"gate-{gate_id}.json"
                    )
                )
        return refs

    def _digest_message(self, session_label: str) -> str:
        messages = {
            "session_preopen": "Pre-open checklist captured.",
            "session_heartbeat": "Heartbeat captured.",
            "session_close": "Session close digest generated.",
        }
        return messages.get(session_label, "Session digest generated.")

    def _string_items(self, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value]
        return []


def build_default_local_web_components(
    config: TradingConfig,
) -> tuple[LocalWebReadModel, LocalWebActionRunner]:
    repo_root = Path(__file__).resolve().parents[3]
    service_manager = LocalServiceManager(
        config=config,
        service_builder=lambda: build_runtime_host_trading_service(config),
    )
    scheduler_manager = LocalSchedulerManager(config=config)
    operator_store_root = config.runtime.artifact_root / "operator_platform"
    runtime_store_root = config.runtime.artifact_root
    decision = resolve_broker_mode(config)
    market_data_gateway = build_market_data_gateway_for_mode(
        config,
        broker_mode=decision.requested_mode,
    )
    trading_client = build_trading_client_for_mode(config, decision)
    activation_gateway = (
        LocalActivationGateway(
            store=FilesystemArtifactStore(operator_store_root),
            runtime_snapshot_store=FilesystemArtifactStore(runtime_store_root),
            legacy_non_authority_mode=True,
        )
        if decision.requested_mode == "paper"
        else LocalActivationGateway(
            store=FilesystemArtifactStore(operator_store_root),
            runtime_snapshot_store=FilesystemArtifactStore(runtime_store_root),
            promotion_decision_provider=build_artifact_promotion_decision_provider(
                config.runtime.artifact_root / "quant" / "promotion"
            ),
            required_promotion_state=PromotionState.PAPER_TRADING,
            projection_root=Path("config/strategy/promotion"),
        )
    )
    runtime_host_manager = LocalRuntimeHostManager(
        config=config,
        operator_store_root=operator_store_root,
        service_manager=service_manager,
        warmup_service=HistoricalWarmupService(
            market_data_gateway=market_data_gateway,
        ),
        activation_gateway=activation_gateway,
        opportunity_planner=RuntimeOpportunityPlanner(
            market_data_gateway=market_data_gateway,
        ),
        portfolio_gateway=AlpacaPortfolioGateway(trading_client=trading_client),
    )
    return (
        LocalWebReadModel(
            config=config,
            paper_store=FilesystemArtifactStore(
                config.runtime.artifact_root / "paper_loop"
            ),
            validation_store=FilesystemArtifactStore(
                config.runtime.artifact_root / "validation"
            ),
            docs_root=repo_root / "docs",
            repo_root=repo_root,
            service_manager=service_manager,
            runtime_host_manager=runtime_host_manager,
            scheduler_manager=scheduler_manager,
        ),
        LocalWebActionRunner(
            config=config,
            repo_root=repo_root,
            service_manager=service_manager,
            runtime_host_manager=runtime_host_manager,
            scheduler_manager=scheduler_manager,
        ),
    )


__all__ = (
    "LocalSchedulerManager",
    "LocalServiceManager",
    "LocalWebActionRunner",
    "build_default_local_web_components",
)
