from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import pandas as pd  # type: ignore[import-untyped]

from tradingx.activation import LocalActivationGateway
from tradingx.config import TradingConfig
from tradingx.data import build_market_data_gateway_for_mode
from tradingx.drift.attribution import SleeveAttributionRecorder
from tradingx.drift.backtest_reference import (
    artifact_path as backtest_reference_artifact_path,
)
from tradingx.drift.backtest_reference import (
    write_backtest_reference_returns,
)
from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.drift.gateway import (
    ArtifactBacktestReferenceReturnsReader,
    DriftAlarmGateway,
    MarketDataFeatureSampleReader,
    MarketDataHistoryProtocol,
    MarketDataSignalSampleReader,
    StoreBackedAttributionRecordsReader,
    StoreBackedReplayRecordsReader,
)
from tradingx.drift.reference import (
    ReferenceDistributionSnapshot,
    build_reference_distribution_snapshot,
    load_reference_distribution_snapshot,
    write_reference_distribution_snapshot,
)
from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.live_enablement import (
    build_trading_client_for_mode,
    resolve_broker_mode,
)
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.promotion import (
    PromotionState,
    build_artifact_promotion_decision_provider,
)
from tradingx.replay_slippage import generate_replay_slippage_evidence
from tradingx.risk_free import DEFAULT_TREASURY_YIELD_CACHE_PATH, DEFAULT_VIX_CACHE_PATH
from tradingx.runtime_host import PortfolioGatewayProtocol
from tradingx.runtime_strategy_registry import build_default_runtime_registry
from tradingx.service import PaperTradingService, build_default_trading_service
from tradingx.sleeves.base import build_sleeve_from_candidate
from tradingx.sleeves.evaluation import simulate_sleeve_returns
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.types import (
    DailySessionDigest,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    MarketAutomationRunRecord,
    MarketAutomationRunResult,
    MarketSessionRecord,
    OperatorAlert,
    PortfolioState,
    ReplaySlippageGenerationResult,
    SessionOpenPortfolioStateRecord,
    WebActionResult,
)
from tradingx.validation import _build_default_regime_snapshots

REFERENCE_SNAPSHOT_FILENAME = "reference_distribution_snapshot.json"
DEFAULT_REFERENCE_WINDOW_DAYS = 365


class ServiceBuilderProtocol(Protocol):
    def __call__(self) -> PaperTradingService: ...


@dataclass(frozen=True)
class _AutomationStepArtifacts:
    action_result: WebActionResult
    session_record: MarketSessionRecord
    session_path: Path
    digest: DailySessionDigest
    digest_path: Path
    replay_summary_path: Path | None = None
    replay_summary_id: str = ""
    gate3_report_path: Path | None = None
    gate3_report_id: str = ""
    gate3_package_path: Path | None = None
    gate3_package_id: str = ""


class MarketDayAutomationRunner:
    def __init__(
        self,
        *,
        paper_store: FilesystemArtifactStore,
        validation_store: FilesystemArtifactStore,
        operator_store: FilesystemArtifactStore,
        service_builder: ServiceBuilderProtocol,
        runtime_store: FilesystemArtifactStore | None = None,
        portfolio_gateway: PortfolioGatewayProtocol | None = None,
        drift_alarm_gateway: DriftAlarmGateway | None = None,
        attribution_recorder: SleeveAttributionRecorder | None = None,
        replay_generator: Callable[..., ReplaySlippageGenerationResult] = (
            generate_replay_slippage_evidence
        ),
        gate3_report_builder: Callable[..., Gate3ReadinessReport] = (
            build_gate3_readiness_report
        ),
        gate3_package_builder: Callable[
            [Gate3ReadinessReport], Gate3PromotionPackage
        ] = build_gate3_promotion_package,
        now_provider: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[int], None] | None = None,
    ) -> None:
        self._paper_store = paper_store
        self._validation_store = validation_store
        self._operator_store = operator_store
        self._runtime_store = runtime_store or operator_store
        self._service_builder = service_builder
        self._portfolio_gateway = portfolio_gateway
        self._drift_alarm_gateway = drift_alarm_gateway
        self._attribution_recorder = attribution_recorder
        self._replay_generator = replay_generator
        self._gate3_report_builder = gate3_report_builder
        self._gate3_package_builder = gate3_package_builder
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._sleep_fn = sleep_fn or (lambda seconds: __import__("time").sleep(seconds))
        self._session_open_portfolio_state: PortfolioState | None = None

    def run_preopen(self) -> WebActionResult:
        try:
            return self._execute_preopen().action_result
        except Exception as error:
            return self._failure_result(
                action_type="session_preopen",
                message=f"Pre-open automation failed: {error}",
            )

    def run_heartbeat(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
    ) -> WebActionResult:
        try:
            return self._execute_heartbeat(
                symbols=symbols,
                quantity=quantity,
                interval_seconds=interval_seconds,
            ).action_result
        except Exception as error:
            return self._failure_result(
                action_type="session_heartbeat",
                message=f"Heartbeat automation failed: {error}",
            )

    def run_close(self) -> WebActionResult:
        try:
            return self._execute_close().action_result
        except Exception as error:
            return self._failure_result(
                action_type="session_close",
                message=f"Session close automation failed: {error}",
            )

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_heartbeats: int | None,
        stop_event: threading.Event | None = None,
    ) -> MarketAutomationRunResult:
        started_at = self._now_provider()
        preopen_step: _AutomationStepArtifacts | None = None
        heartbeat_steps: list[_AutomationStepArtifacts] = []
        close_step: _AutomationStepArtifacts | None = None
        failed = False
        failure_reason = ""

        try:
            preopen_step = self._execute_preopen()
            heartbeats_remaining = max_heartbeats
            while heartbeats_remaining is None or heartbeats_remaining > 0:
                if stop_event is not None and stop_event.is_set():
                    break
                heartbeat_step = self._execute_heartbeat(
                    symbols=symbols,
                    quantity=quantity,
                    interval_seconds=interval_seconds,
                )
                heartbeat_steps.append(heartbeat_step)
                if heartbeat_step.action_result.status == "skipped":
                    break
                if heartbeats_remaining is not None:
                    heartbeats_remaining -= 1
                    if heartbeats_remaining <= 0:
                        break
                if stop_event is not None and stop_event.is_set():
                    break
                self._sleep_fn(interval_seconds)
            if stop_event is None or not stop_event.is_set():
                close_step = self._execute_close()
        except Exception as error:
            failed = True
            failure_reason = str(error)

        heartbeat_count = len(heartbeat_steps)
        executed_heartbeats = sum(
            1 for step in heartbeat_steps if step.action_result.status == "completed"
        )
        run_status = (
            "failed"
            if failed
            else (
                "stopped"
                if stop_event is not None and stop_event.is_set()
                else (
                    "skipped"
                    if heartbeat_steps
                    and executed_heartbeats == 0
                    and heartbeat_steps[-1].action_result.status == "skipped"
                    else "completed"
                )
            )
        )
        run_summary = self._run_summary(
            failed=failed,
            failure_reason=failure_reason,
            heartbeat_count=heartbeat_count,
            executed_heartbeats=executed_heartbeats,
        )
        latest_replay_summary_id, replay_summary_path = self._latest_replay(
            heartbeat_steps,
            close_step,
        )
        latest_gate3_report_id, gate3_report_path = self._latest_gate3_report(
            heartbeat_steps,
            close_step,
        )
        latest_gate3_package_id, gate3_package_path = self._latest_gate3_package(
            close_step
        )
        run_record = MarketAutomationRunRecord(
            run_id=f"automation-{uuid.uuid4()}",
            started_at_utc=started_at,
            completed_at_utc=self._now_provider(),
            trading_day=started_at.date().isoformat(),
            status=run_status,
            heartbeat_count=heartbeat_count,
            preopen_session_id=(
                preopen_step.session_record.session_id
                if preopen_step is not None
                else ""
            ),
            heartbeat_session_ids=tuple(
                step.session_record.session_id for step in heartbeat_steps
            ),
            close_session_id=(
                close_step.session_record.session_id if close_step is not None else ""
            ),
            latest_replay_summary_id=latest_replay_summary_id,
            latest_gate3_report_id=latest_gate3_report_id,
            latest_gate3_package_id=latest_gate3_package_id,
            summary=run_summary,
            evidence_refs=self._run_evidence_refs(
                preopen_step,
                heartbeat_steps,
                close_step,
            ),
        )
        run_record_path = self._operator_store.write_market_automation_run_record(
            run_record
        )

        return MarketAutomationRunResult(
            run_record=run_record,
            run_record_path=run_record_path,
            session_paths=tuple(
                path
                for path in (
                    preopen_step.session_path if preopen_step is not None else None,
                    *(step.session_path for step in heartbeat_steps),
                    close_step.session_path if close_step is not None else None,
                )
                if path is not None
            ),
            daily_digest_paths=tuple(
                path
                for path in (
                    preopen_step.digest_path if preopen_step is not None else None,
                    *(step.digest_path for step in heartbeat_steps),
                    close_step.digest_path if close_step is not None else None,
                )
                if path is not None
            ),
            replay_summary_path=replay_summary_path,
            gate3_report_path=gate3_report_path,
            gate3_package_path=gate3_package_path,
        )

    def _execute_preopen(self) -> _AutomationStepArtifacts:
        if self._portfolio_gateway is not None:
            self._session_open_portfolio_state = (
                self._portfolio_gateway.get_portfolio_state()
            )
            trading_day = self._now_provider().date().isoformat()
            self._runtime_store.write_session_open_portfolio_state_record(
                SessionOpenPortfolioStateRecord(
                    record_id=f"session-open-{trading_day}",
                    trading_day=trading_day,
                    recorded_at_utc=self._now_provider(),
                    portfolio_state=self._session_open_portfolio_state,
                )
            )
        return self._write_checkpoint(
            session_label="session_preopen",
            service_status="idle",
            action_type="session_preopen",
            action_status="completed",
            message="Pre-open checklist captured.",
        )

    def _execute_heartbeat(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
    ) -> _AutomationStepArtifacts:
        service_result = self._service_builder().run(
            symbols=symbols,
            quantity=quantity,
            interval_seconds=interval_seconds,
            max_cycles=1,
        )
        replay_result = self._replay_generator(
            paper_store=self._paper_store,
            validation_store=self._validation_store,
        )
        report = self._gate3_report_builder(
            paper_store=self._paper_store,
            validation_store=self._validation_store,
        )
        report_path = self._validation_store.write_gate3_readiness_report(report)
        service_status = service_result.last_cycle.cycle_status
        return self._write_checkpoint(
            session_label="session_heartbeat",
            service_status=service_status,
            action_type="session_heartbeat",
            action_status="completed" if service_status == "executed" else "skipped",
            message=(
                "Heartbeat executed and Gate 3 evidence refreshed."
                if service_status == "executed"
                else "Heartbeat skipped because the market is closed."
            ),
            extra_evidence_refs=(
                *(str(path) for path in service_result.artifact_paths),
                str(replay_result.summary_path),
                str(report_path),
            ),
            replay_summary_path=replay_result.summary_path,
            replay_summary_id=replay_result.summary.summary_id,
            gate3_report_path=report_path,
            gate3_report_id=report.report_id,
        )

    def _execute_close(self) -> _AutomationStepArtifacts:
        trading_day = self._now_provider().date().isoformat()
        if (
            self._attribution_recorder is not None
            and self._portfolio_gateway is not None
        ):
            open_state = self._session_open_portfolio_state
            if open_state is None:
                persisted_open = (
                    self._runtime_store.read_session_open_portfolio_state_record(
                        trading_day=trading_day
                    )
                )
                open_state = (
                    persisted_open.portfolio_state
                    if persisted_open is not None
                    else None
                )
            if open_state is not None:
                close_state = self._portfolio_gateway.get_portfolio_state()
                self._attribution_recorder.record_session(
                    trading_day=trading_day,
                    open_portfolio_state=open_state,
                    close_portfolio_state=close_state,
                )
                self._session_open_portfolio_state = None
        if self._drift_alarm_gateway is not None:
            self._drift_alarm_gateway.refresh()
        replay_result = self._replay_generator(
            paper_store=self._paper_store,
            validation_store=self._validation_store,
        )
        report = self._gate3_report_builder(
            paper_store=self._paper_store,
            validation_store=self._validation_store,
        )
        report_path = self._validation_store.write_gate3_readiness_report(report)
        package = self._gate3_package_builder(report)
        package_path = self._validation_store.write_gate3_promotion_package(package)
        return self._write_checkpoint(
            session_label="session_close",
            service_status="stopped",
            action_type="session_close",
            action_status="completed",
            message="Session close digest generated.",
            extra_evidence_refs=(
                str(replay_result.summary_path),
                str(report_path),
                str(package_path),
            ),
            replay_summary_path=replay_result.summary_path,
            replay_summary_id=replay_result.summary.summary_id,
            gate3_report_path=report_path,
            gate3_report_id=report.report_id,
            gate3_package_path=package_path,
            gate3_package_id=package.package_id,
        )

    def _write_checkpoint(
        self,
        *,
        session_label: str,
        service_status: str,
        action_type: str,
        action_status: str,
        message: str,
        extra_evidence_refs: tuple[str, ...] = (),
        replay_summary_path: Path | None = None,
        replay_summary_id: str = "",
        gate3_report_path: Path | None = None,
        gate3_report_id: str = "",
        gate3_package_path: Path | None = None,
        gate3_package_id: str = "",
    ) -> _AutomationStepArtifacts:
        generated_at = self._now_provider()
        checkpoint_suffix = uuid.uuid4().hex[:8]
        paper_report = self._paper_store.build_operator_evidence_report()
        summary_payload = paper_report.get("summary", {})
        paper_summary = summary_payload if isinstance(summary_payload, dict) else {}
        latest_positions = self._string_items(
            paper_summary.get("latest_open_positions", ())
        )
        latest_alerts = self._paper_store.list_artifact_payloads("operator_alerts")[-3:]
        top_incidents = tuple(
            f"incident-{payload.get('alert_id', '')}"
            for payload in latest_alerts
            if str(payload.get("alert_id", "")).strip()
        )
        recommended_actions = self._recommended_actions(
            session_label=session_label,
            service_status=service_status,
        )
        digest = DailySessionDigest(
            digest_id=(
                f"digest-{generated_at.strftime('%Y%m%d%H%M%S')}-"
                f"{session_label}-{checkpoint_suffix}"
            ),
            generated_at_utc=generated_at,
            session_label=session_label,
            service_status=service_status,
            blocked_trade_count=int(paper_summary.get("blocked_trade_count", 0)),
            reconciliation_failure_count=int(
                paper_summary.get("reconciliation_failure_count", 0)
            ),
            latest_positions=tuple(latest_positions),
            top_incidents=top_incidents,
            recommended_actions=recommended_actions,
            evidence_refs=extra_evidence_refs,
        )
        digest_path = self._operator_store.write_daily_session_digest(digest)
        session_record = MarketSessionRecord(
            session_id=(
                f"session-{generated_at.strftime('%Y%m%d%H%M%S')}-"
                f"{session_label}-{checkpoint_suffix}"
            ),
            session_label=session_label,
            recorded_at_utc=generated_at,
            service_status=service_status,
            blocked_trade_count=digest.blocked_trade_count,
            reconciliation_failure_count=digest.reconciliation_failure_count,
            open_positions=digest.latest_positions,
            top_incidents=digest.top_incidents,
            recommended_actions=digest.recommended_actions,
            evidence_refs=extra_evidence_refs,
        )
        session_path = self._operator_store.write_market_session_record(session_record)
        return _AutomationStepArtifacts(
            action_result=WebActionResult(
                action_id=f"action-{uuid.uuid4()}",
                action_type=action_type,
                status=action_status,
                message=message,
                evidence_refs=(
                    str(digest_path),
                    str(session_path),
                    *extra_evidence_refs,
                ),
            ),
            session_record=session_record,
            session_path=session_path,
            digest=digest,
            digest_path=digest_path,
            replay_summary_path=replay_summary_path,
            replay_summary_id=replay_summary_id,
            gate3_report_path=gate3_report_path,
            gate3_report_id=gate3_report_id,
            gate3_package_path=gate3_package_path,
            gate3_package_id=gate3_package_id,
        )

    def _recommended_actions(
        self,
        *,
        session_label: str,
        service_status: str,
    ) -> tuple[str, ...]:
        recommendations: list[str] = []
        gate_reports = self._validation_store.list_artifact_payloads("gate3_reports")
        if gate_reports:
            latest = max(
                gate_reports,
                key=lambda payload: str(payload.get("generated_at_utc", "")),
            )
            summary = str(latest.get("summary", "")).strip()
            if summary:
                recommendations.append(summary)
        if session_label == "session_heartbeat" and service_status == "market_closed":
            recommendations.append(
                "Market is closed; wait for the next regular session."
            )
        if session_label == "session_close":
            recommendations.append(
                "Review the latest Gate 3 package before the next session."
            )
        if not recommendations:
            recommendations.append(
                "Continue collecting paper evidence and review incidents."
            )
        return tuple(recommendations)

    def _run_summary(
        self,
        *,
        failed: bool,
        failure_reason: str,
        heartbeat_count: int,
        executed_heartbeats: int,
    ) -> str:
        if failed:
            if failure_reason:
                return (
                    "Market-day automation failed before completing all checkpoints: "
                    f"{failure_reason}"
                )
            return "Market-day automation failed before completing all checkpoints."
        if heartbeat_count and executed_heartbeats == 0:
            return (
                "Automation completed with no executed heartbeats because the "
                "market was closed."
            )
        return (
            f"Automation completed with {heartbeat_count} heartbeat checkpoints and "
            "fresh Gate 3 evidence."
        )

    def _latest_replay(
        self,
        heartbeat_steps: list[_AutomationStepArtifacts],
        close_step: _AutomationStepArtifacts | None,
    ) -> tuple[str, Path | None]:
        if close_step is not None and close_step.replay_summary_path is not None:
            return close_step.replay_summary_id, close_step.replay_summary_path
        for step in reversed(heartbeat_steps):
            if step.replay_summary_path is not None:
                return step.replay_summary_id, step.replay_summary_path
        return "", None

    def _latest_gate3_report(
        self,
        heartbeat_steps: list[_AutomationStepArtifacts],
        close_step: _AutomationStepArtifacts | None,
    ) -> tuple[str, Path | None]:
        if close_step is not None and close_step.gate3_report_path is not None:
            return close_step.gate3_report_id, close_step.gate3_report_path
        for step in reversed(heartbeat_steps):
            if step.gate3_report_path is not None:
                return step.gate3_report_id, step.gate3_report_path
        return "", None

    def _latest_gate3_package(
        self,
        close_step: _AutomationStepArtifacts | None,
    ) -> tuple[str, Path | None]:
        if close_step is None or close_step.gate3_package_path is None:
            return "", None
        return close_step.gate3_package_id, close_step.gate3_package_path

    def _run_evidence_refs(
        self,
        preopen_step: _AutomationStepArtifacts | None,
        heartbeat_steps: list[_AutomationStepArtifacts],
        close_step: _AutomationStepArtifacts | None,
    ) -> tuple[str, ...]:
        refs: list[str] = []
        for step in (
            *((preopen_step,) if preopen_step is not None else ()),
            *heartbeat_steps,
            *((close_step,) if close_step is not None else ()),
        ):
            refs.extend(step.action_result.evidence_refs)
        return tuple(dict.fromkeys(refs))

    def _string_items(self, value: object) -> list[str]:
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        return []

    def _failure_result(self, *, action_type: str, message: str) -> WebActionResult:
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type=action_type,
            status="failed",
            message=message,
            evidence_refs=(),
        )


class _ArtifactAlertGateway:
    def __init__(self, *, store: FilesystemArtifactStore) -> None:
        self._store = store

    def publish(self, alert: OperatorAlert) -> None:
        self._store.write_operator_alert(alert)


def _reference_snapshot_path(*, artifact_root: Path) -> Path:
    return artifact_root / "drift" / REFERENCE_SNAPSHOT_FILENAME


def _load_or_build_reference_snapshot(
    *,
    artifact_root: Path,
    blueprint: DriftMonitorBlueprint,
    feature_reader: MarketDataFeatureSampleReader,
    signal_reader: MarketDataSignalSampleReader,
    now_provider: Callable[[], datetime],
    force_rebuild: bool = False,
) -> ReferenceDistributionSnapshot:
    path = _reference_snapshot_path(artifact_root=artifact_root)
    if path.exists() and not force_rebuild:
        return load_reference_distribution_snapshot(path)

    now_utc = now_provider()
    feature_samples: dict[str, pd.Series] = {}
    for feature_name in blueprint.feature_monitor_names:
        try:
            samples = feature_reader.live_samples(
                feature_name,
                window_days=DEFAULT_REFERENCE_WINDOW_DAYS,
            )
        except LookupError:
            continue
        if len(samples) > 0:
            feature_samples[feature_name] = samples

    signal_samples: dict[str, pd.Series] = {}
    for sleeve_id in blueprint.signal_monitor_sleeve_ids:
        try:
            samples = signal_reader.live_samples(
                sleeve_id,
                window_days=DEFAULT_REFERENCE_WINDOW_DAYS,
            )
        except LookupError:
            continue
        if len(samples) > 0:
            signal_samples[sleeve_id] = samples

    snapshot = build_reference_distribution_snapshot(
        reference_snapshot_id=f"drift-ref-{now_utc.strftime('%Y%m%d%H%M%S')}",
        blueprint_id=blueprint.blueprint_id,
        feature_samples_by_name=feature_samples,
        signal_samples_by_sleeve_id=signal_samples,
        reference_window_start_utc=now_utc
        - timedelta(days=DEFAULT_REFERENCE_WINDOW_DAYS),
        reference_window_end_utc=now_utc,
        generated_at_utc=now_utc,
    )
    write_reference_distribution_snapshot(path, snapshot)
    return snapshot


def _ensure_backtest_reference_returns(
    *,
    config: TradingConfig,
    market_data_gateway: MarketDataHistoryProtocol,
    now_provider: Callable[[], datetime],
    force_rebuild: bool = False,
) -> None:
    end_utc = now_provider()
    start_utc = end_utc - timedelta(days=400)
    for candidate in build_mandatory_candidate_registry(config.runtime.symbol_universe):
        if candidate.sleeve_class_path is None:
            continue
        path = backtest_reference_artifact_path(
            artifact_root=config.runtime.artifact_root,
            sleeve_id=candidate.candidate_id,
        )
        if path.exists() and not force_rebuild:
            continue
        bars_by_symbol = {
            symbol: market_data_gateway.get_daily_bar_history(
                symbol,
                start_utc=start_utc,
                end_utc=end_utc,
            )
            for symbol in tuple(
                sorted({candidate.benchmark_symbol, *candidate.universe})
            )
        }
        sleeve = build_sleeve_from_candidate(candidate)
        regimes = _build_default_regime_snapshots(
            candidate,
            bars_by_symbol=bars_by_symbol,
        )
        returns, _ = simulate_sleeve_returns(
            sleeve,
            bars_by_symbol=bars_by_symbol,
            regime_snapshots_by_date=regimes,
            sleeve_budget_equity=Decimal("1.0"),
        )
        write_backtest_reference_returns(
            artifact_root=config.runtime.artifact_root,
            sleeve_id=candidate.candidate_id,
            returns=returns,
        )


def _last_activation_bookkeeping_path(*, artifact_root: Path) -> Path:
    return artifact_root / "drift" / "last_activation.json"


def _read_last_seen_bookkeeping(path: Path) -> dict[str, str | None]:
    if not path.exists():
        return {"activation_id": None, "last_processed_recalibration_at": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"activation_id": None, "last_processed_recalibration_at": None}
    return {
        "activation_id": str(payload.get("activation_id") or "") or None,
        "last_processed_recalibration_at": (
            str(payload.get("last_processed_recalibration_at") or "") or None
        ),
    }


def _write_last_seen_bookkeeping(
    path: Path,
    *,
    activation_id: str | None,
    last_processed_recalibration_at: str | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str | None] = {
        "activation_id": activation_id,
        "last_processed_recalibration_at": last_processed_recalibration_at,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_operator_recalibration_marker_timestamp(
    *,
    control_store_root: Path,
) -> datetime | None:
    path = control_store_root / "drift_reference_recalibration.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = payload.get("at_utc")
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _parse_bookkeeping_timestamp(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _resolve_drift_reference_snapshot(
    *,
    config: TradingConfig,
    activation_gateway: LocalActivationGateway,
    blueprint: DriftMonitorBlueprint,
    feature_reader: MarketDataFeatureSampleReader,
    signal_reader: MarketDataSignalSampleReader,
    market_data_gateway: MarketDataHistoryProtocol,
    now_provider: Callable[[], datetime],
) -> ReferenceDistributionSnapshot:
    bookkeeping_path = _last_activation_bookkeeping_path(
        artifact_root=config.runtime.artifact_root
    )
    control_store_root = config.runtime.data_root / "control"
    current_activation = activation_gateway.get_active_blueprint_activation()
    last_seen = _read_last_seen_bookkeeping(bookkeeping_path)
    marker_at = _read_operator_recalibration_marker_timestamp(
        control_store_root=control_store_root
    )
    last_processed_recalibration_at = _parse_bookkeeping_timestamp(
        last_seen["last_processed_recalibration_at"]
    )

    activation_changed = (
        current_activation is not None
        and current_activation.activation_id != last_seen["activation_id"]
    )
    recalibration_fresh = marker_at is not None and (
        last_processed_recalibration_at is None
        or last_processed_recalibration_at < marker_at
    )
    force_rebuild = activation_changed or recalibration_fresh

    reference_snapshot = _load_or_build_reference_snapshot(
        artifact_root=config.runtime.artifact_root,
        blueprint=blueprint,
        feature_reader=feature_reader,
        signal_reader=signal_reader,
        now_provider=now_provider,
        force_rebuild=force_rebuild,
    )
    _ensure_backtest_reference_returns(
        config=config,
        market_data_gateway=market_data_gateway,
        now_provider=now_provider,
        force_rebuild=force_rebuild,
    )
    if force_rebuild:
        _write_last_seen_bookkeeping(
            bookkeeping_path,
            activation_id=(
                current_activation.activation_id
                if current_activation is not None
                else last_seen["activation_id"]
            ),
            last_processed_recalibration_at=(
                marker_at.isoformat().replace("+00:00", "Z")
                if marker_at is not None
                else last_seen["last_processed_recalibration_at"]
            ),
        )
    return reference_snapshot


def build_default_market_day_automation_runner(
    config: TradingConfig,
) -> MarketDayAutomationRunner:
    artifact_root = config.runtime.artifact_root
    paper_store = FilesystemArtifactStore(artifact_root / "paper_loop")
    validation_store = FilesystemArtifactStore(artifact_root / "validation")
    operator_store = FilesystemArtifactStore(artifact_root / "operator_platform")
    runtime_store = FilesystemArtifactStore(artifact_root)

    def now_provider() -> datetime:
        return datetime.now(UTC)

    decision = resolve_broker_mode(config)
    market_data_gateway = build_market_data_gateway_for_mode(
        config,
        broker_mode=decision.requested_mode,
    )
    runtime_registry = build_default_runtime_registry(
        market_data_gateway=market_data_gateway,
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
            config.runtime.artifact_root / "quant" / "promotion"
        ),
        required_promotion_state=PromotionState.PAPER_TRADING,
        projection_root=Path("config/strategy/promotion"),
    )
    trading_client = build_trading_client_for_mode(config, decision)
    portfolio_gateway = AlpacaPortfolioGateway(trading_client=trading_client)
    blueprint = DriftMonitorBlueprint(blueprint_id="drift-default-v1")
    treasury_cache_path = (
        config.runtime.data_root / "reference" / DEFAULT_TREASURY_YIELD_CACHE_PATH.name
    )
    feature_reader = MarketDataFeatureSampleReader(
        market_data_gateway=market_data_gateway,
        vix_cache_path=config.runtime.data_root
        / "reference"
        / DEFAULT_VIX_CACHE_PATH.name,
        treasury_cache_path=treasury_cache_path,
        now_provider=now_provider,
    )
    signal_reader = MarketDataSignalSampleReader(
        market_data_gateway=market_data_gateway,
        now_provider=now_provider,
    )
    reference_snapshot = _resolve_drift_reference_snapshot(
        config=config,
        activation_gateway=activation_gateway,
        blueprint=blueprint,
        feature_reader=feature_reader,
        signal_reader=signal_reader,
        market_data_gateway=market_data_gateway,
        now_provider=now_provider,
    )
    drift_alarm_gateway = DriftAlarmGateway(
        blueprint=blueprint,
        reference_snapshot=reference_snapshot,
        feature_sample_reader=feature_reader,
        signal_sample_reader=signal_reader,
        replay_records_reader=StoreBackedReplayRecordsReader(
            validation_store=validation_store,
        ),
        attribution_records_reader=StoreBackedAttributionRecordsReader(
            operator_store=runtime_store,
        ),
        backtest_reference_returns_reader=ArtifactBacktestReferenceReturnsReader(
            artifact_root=artifact_root,
        ),
        risk_control_event_sink=runtime_store,
        alert_gateway=_ArtifactAlertGateway(store=runtime_store),
        verdict_sink=runtime_store,
        now_provider=now_provider,
    )
    attribution_recorder = SleeveAttributionRecorder(
        activation_gateway=activation_gateway,
        attribution_store=runtime_store,
        now_provider=now_provider,
        decomposition_store=runtime_store,
        execution_store=paper_store,
    )
    return MarketDayAutomationRunner(
        paper_store=paper_store,
        validation_store=validation_store,
        operator_store=operator_store,
        runtime_store=runtime_store,
        service_builder=lambda: build_default_trading_service(config),
        portfolio_gateway=portfolio_gateway,
        drift_alarm_gateway=drift_alarm_gateway,
        attribution_recorder=attribution_recorder,
        now_provider=now_provider,
    )


__all__ = (
    "MarketDayAutomationRunner",
    "build_default_market_day_automation_runner",
)
