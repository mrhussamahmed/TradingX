from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.automation import MarketDayAutomationRunner
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    ReplaySlippageGenerationResult,
    ReplaySlippageSummary,
    ServiceCycleSnapshot,
    ServiceRunResult,
)


class FakePaperService:
    def __init__(self) -> None:
        self.calls = 0

    def run(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> ServiceRunResult:
        self.calls += 1
        timestamp = datetime(2026, 4, 18, 13, self.calls, tzinfo=UTC)
        return ServiceRunResult(
            cycles_completed=1,
            last_cycle=ServiceCycleSnapshot(
                cycle_id=f"cycle-{self.calls}",
                started_at_utc=timestamp,
                completed_at_utc=timestamp,
                cycle_status="executed",
                symbols=symbols,
                symbol_results=(),
                blocked_trade_count=0,
                reconciliation_failure_count=0,
                open_position_symbols=("SPY",),
                cash=Decimal("10025.00"),
                equity=Decimal("10030.00"),
                buying_power=Decimal("20030.00"),
            ),
            artifact_paths=(
                Path(f"artifacts/paper_loop/service_cycles/cycle-{self.calls}.json"),
            ),
        )


def test_market_day_automation_runner_writes_run_record_and_refreshes_gate3(
    tmp_path,
) -> None:
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    fake_service = FakePaperService()
    sleep_calls: list[int] = []

    def fake_replay_generator(
        *,
        paper_store: FilesystemArtifactStore,
        validation_store: FilesystemArtifactStore,
    ) -> ReplaySlippageGenerationResult:
        summary = ReplaySlippageSummary(
            summary_id="replay-summary-1",
            matched_execution_count=1,
            paper_mean_absolute_slippage_bps=Decimal("5.0"),
            replay_mean_absolute_slippage_bps=Decimal("7.5"),
            divergence_ratio=Decimal("1.5"),
            status="pass",
            details="Replay divergence is within the allowed bound.",
            generated_at_utc=datetime(2026, 4, 18, 13, 10, tzinfo=UTC),
        )
        path = validation_store.write_replay_slippage_summary(summary)
        return ReplaySlippageGenerationResult(
            summary=summary,
            record_paths=(),
            summary_path=path,
        )

    def fake_gate3_report_builder(
        *,
        paper_store: FilesystemArtifactStore,
        validation_store: FilesystemArtifactStore,
    ) -> Gate3ReadinessReport:
        return Gate3ReadinessReport(
            report_id="gate3-1",
            generated_at_utc=datetime(2026, 4, 18, 13, 11, tzinfo=UTC),
            status="pending",
            closed_trade_count=2,
            calendar_days_observed=12,
            criteria=(),
            summary="Gate 3 remains pending.",
            required_operator_action="Keep collecting evidence.",
            evidence_refs=(),
        )

    def fake_gate3_package_builder(
        report: Gate3ReadinessReport,
    ) -> Gate3PromotionPackage:
        return Gate3PromotionPackage(
            package_id="gate3-package-1",
            generated_at_utc=report.generated_at_utc,
            status=report.status,
            headline="Gate 3 still pending.",
            decision_summary=report.summary,
            criteria_statuses={},
            evidence_refs=(),
        )

    runner = MarketDayAutomationRunner(
        paper_store=paper_store,
        validation_store=validation_store,
        operator_store=operator_store,
        service_builder=lambda: fake_service,
        replay_generator=fake_replay_generator,
        gate3_report_builder=fake_gate3_report_builder,
        gate3_package_builder=fake_gate3_package_builder,
        now_provider=lambda: datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    result = runner.run_market_day(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_heartbeats=2,
    )

    assert fake_service.calls == 2
    assert sleep_calls == [300]
    assert result.run_record.status == "completed"
    assert result.run_record.heartbeat_count == 2
    assert result.run_record_path.exists()
    assert result.replay_summary_path is not None
    assert result.gate3_report_path is not None
    assert result.gate3_package_path is not None
    assert len(result.session_paths) == 4
    assert len({path.name for path in result.session_paths}) == 4
    assert len({path.name for path in result.daily_digest_paths}) == 4
    market_sessions = list(
        (tmp_path / "artifacts" / "operator_platform" / "market_sessions").glob(
            "*.json"
        )
    )
    assert len(market_sessions) == 4


def test_market_day_automation_runner_stops_before_next_heartbeat_when_requested(
    tmp_path,
) -> None:
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    fake_service = FakePaperService()
    stop_event = threading.Event()
    sleep_calls: list[int] = []

    runner = MarketDayAutomationRunner(
        paper_store=paper_store,
        validation_store=validation_store,
        operator_store=operator_store,
        service_builder=lambda: fake_service,
        now_provider=lambda: datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    stop_event.set()
    result = runner.run_market_day(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_heartbeats=2,
        stop_event=stop_event,
    )

    assert fake_service.calls == 0
    assert sleep_calls == []
    assert result.run_record.status == "stopped"
    assert result.run_record.heartbeat_count == 0
