from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from tradingx.config import TradingConfig
from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.persistence import FilesystemArtifactStore
from tradingx.replay_slippage import generate_replay_slippage_evidence
from tradingx.service import PaperTradingService, build_default_paper_service
from tradingx.types import (
    DailySessionDigest,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    MarketAutomationRunRecord,
    MarketAutomationRunResult,
    MarketSessionRecord,
    ReplaySlippageGenerationResult,
    WebActionResult,
)


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
        self._service_builder = service_builder
        self._replay_generator = replay_generator
        self._gate3_report_builder = gate3_report_builder
        self._gate3_package_builder = gate3_package_builder
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._sleep_fn = sleep_fn or (lambda seconds: __import__("time").sleep(seconds))

    def run_preopen(self) -> WebActionResult:
        try:
            return self._execute_preopen().action_result
        except Exception:
            return self._failure_result(
                action_type="session_preopen",
                message="Pre-open automation failed.",
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
        except Exception:
            return self._failure_result(
                action_type="session_heartbeat",
                message="Heartbeat automation failed.",
            )

    def run_close(self) -> WebActionResult:
        try:
            return self._execute_close().action_result
        except Exception:
            return self._failure_result(
                action_type="session_close",
                message="Session close automation failed.",
            )

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_heartbeats: int | None,
    ) -> MarketAutomationRunResult:
        started_at = self._now_provider()
        preopen_step: _AutomationStepArtifacts | None = None
        heartbeat_steps: list[_AutomationStepArtifacts] = []
        close_step: _AutomationStepArtifacts | None = None
        failed = False

        try:
            preopen_step = self._execute_preopen()
            heartbeats_remaining = max_heartbeats
            while heartbeats_remaining is None or heartbeats_remaining > 0:
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
                self._sleep_fn(interval_seconds)
            close_step = self._execute_close()
        except Exception:
            failed = True

        heartbeat_count = len(heartbeat_steps)
        executed_heartbeats = sum(
            1 for step in heartbeat_steps if step.action_result.status == "completed"
        )
        run_status = (
            "failed"
            if failed
            else (
                "skipped"
                if heartbeat_steps
                and executed_heartbeats == 0
                and heartbeat_steps[-1].action_result.status == "skipped"
                else "completed"
            )
        )
        run_summary = self._run_summary(
            failed=failed,
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
        heartbeat_count: int,
        executed_heartbeats: int,
    ) -> str:
        if failed:
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


def build_default_market_day_automation_runner(
    config: TradingConfig,
) -> MarketDayAutomationRunner:
    artifact_root = config.runtime.artifact_root
    return MarketDayAutomationRunner(
        paper_store=FilesystemArtifactStore(artifact_root / "paper_loop"),
        validation_store=FilesystemArtifactStore(artifact_root / "validation"),
        operator_store=FilesystemArtifactStore(artifact_root / "operator_platform"),
        service_builder=lambda: build_default_paper_service(config),
    )


__all__ = (
    "MarketDayAutomationRunner",
    "build_default_market_day_automation_runner",
)
