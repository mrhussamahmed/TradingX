from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.config import TradingConfig
from tradingx.service import ServiceRunResult
from tradingx.types import ServiceCycleSnapshot
from tradingx.web.runtime import LocalServiceManager, LocalWebActionRunner


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
        timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
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
            artifact_paths=(Path("artifacts/paper_loop/service_cycles/cycle-1.json"),),
        )


class FakeAutomationRunner:
    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    def run_preopen(self):
        from tradingx.types import WebActionResult

        path = (
            self._artifact_root
            / "operator_platform"
            / "market_sessions"
            / "session-preopen-1.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

        return WebActionResult(
            action_id="action-preopen",
            action_type="session_preopen",
            status="completed",
            message="Pre-open checklist captured.",
            evidence_refs=("artifacts/operator_platform/daily_digests/preopen.json",),
        )

    def run_heartbeat(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
    ):
        from tradingx.types import WebActionResult

        path = (
            self._artifact_root
            / "operator_platform"
            / "market_sessions"
            / "session-heartbeat-1.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

        return WebActionResult(
            action_id="action-heartbeat",
            action_type="session_heartbeat",
            status="completed",
            message=f"Heartbeat executed for {','.join(symbols)}.",
            evidence_refs=("artifacts/operator_platform/daily_digests/heartbeat.json",),
        )

    def run_close(self):
        from tradingx.types import WebActionResult

        path = (
            self._artifact_root
            / "operator_platform"
            / "market_sessions"
            / "session-close-1.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

        return WebActionResult(
            action_id="action-close",
            action_type="session_close",
            status="completed",
            message="Session close digest generated.",
            evidence_refs=("artifacts/operator_platform/daily_digests/close.json",),
        )

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_heartbeats: int | None,
    ):
        from tradingx.types import MarketAutomationRunRecord, MarketAutomationRunResult

        return MarketAutomationRunResult(
            run_record=MarketAutomationRunRecord(
                run_id="automation-1",
                started_at_utc=datetime(2026, 4, 18, 8, 0, tzinfo=UTC),
                completed_at_utc=datetime(2026, 4, 18, 8, 30, tzinfo=UTC),
                trading_day="2026-04-18",
                status="completed",
                heartbeat_count=max_heartbeats or 1,
                preopen_session_id="session-preopen-1",
                heartbeat_session_ids=("session-heartbeat-1",),
                close_session_id="session-close-1",
                latest_replay_summary_id="replay-summary-1",
                latest_gate3_report_id="gate3-1",
                latest_gate3_package_id="gate3-package-1",
                summary="Automation completed.",
                evidence_refs=(
                    "artifacts/operator_platform/market_automation_runs/automation-1.json",
                ),
            ),
            run_record_path=Path(
                "artifacts/operator_platform/market_automation_runs/automation-1.json"
            ),
            session_paths=(),
            daily_digest_paths=(),
            replay_summary_path=Path(
                "artifacts/validation/replay_slippage_summaries/replay-summary-1.json"
            ),
            gate3_report_path=Path("artifacts/validation/gate3_reports/gate3-1.json"),
            gate3_package_path=Path(
                "artifacts/validation/gate3_packages/gate3-package-1.json"
            ),
        )


def _wait_for(predicate, *, timeout_seconds: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Condition did not become true within the timeout.")


def test_local_service_manager_runs_background_cycles_and_updates_state() -> None:
    fake_service = FakePaperService()
    manager = LocalServiceManager(
        config=TradingConfig.from_mapping({}),
        service_builder=lambda: fake_service,
    )

    result = manager.start(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=1,
        max_cycles=1,
    )

    _wait_for(lambda: manager.get_state().cycles_completed == 1)
    state = manager.get_state()

    assert result.status == "accepted"
    assert state.active_symbols == ("SPY", "QQQ")
    assert state.cycles_completed == 1
    assert state.status == "idle"


def test_local_service_manager_stops_running_service() -> None:
    fake_service = FakePaperService()
    manager = LocalServiceManager(
        config=TradingConfig.from_mapping({}),
        service_builder=lambda: fake_service,
    )

    manager.start(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=60,
    )
    _wait_for(lambda: manager.get_state().cycles_completed >= 1)

    result = manager.stop()

    _wait_for(lambda: manager.get_state().status == "stopped")
    assert result.status == "accepted"


def test_local_web_action_runner_writes_config_proposal(tmp_path) -> None:
    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping({}),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
    )

    proposal = runner.create_config_proposal(
        target_area="runtime",
        proposed_values={"TRADINGX_SYMBOL_UNIVERSE": ["SPY", "QQQ"]},
        rationale="Expand the monitored universe.",
    )

    assert proposal.output_path.exists()
    assert "TRADINGX_SYMBOL_UNIVERSE" in proposal.output_path.read_text(
        encoding="utf-8"
    )


def test_local_web_action_runner_generates_session_digests_and_acknowledges_incidents(
    tmp_path,
) -> None:
    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
            }
        ),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
        automation_runner_builder=lambda: FakeAutomationRunner(tmp_path / "artifacts"),
    )

    preopen = runner.run_session_preopen()
    heartbeat = runner.run_session_heartbeat()
    close_result = runner.run_session_close()
    acknowledge = runner.acknowledge_incident(incident_id="incident-alert-1")

    assert preopen.status == "completed"
    assert heartbeat.status == "completed"
    assert close_result.status == "completed"
    assert acknowledge.status == "completed"
    assert (
        tmp_path
        / "artifacts"
        / "operator_platform"
        / "incident_acknowledgements"
        / "incident-alert-1.json"
    ).exists()
    assert (tmp_path / "artifacts" / "operator_platform" / "market_sessions").exists()


def test_local_web_action_runner_generates_gate3_artifacts(tmp_path) -> None:
    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
            }
        ),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
    )

    report = runner.generate_gate3_report()
    package = runner.generate_gate3_package()
    recovery = runner.run_recovery_drill(symbol="SPY")
    alert = runner.run_alert_drill(channel="smtp")

    assert report.status == "completed"
    assert package.status == "completed"
    assert recovery.status in {"completed", "pending"}
    assert alert.status in {"completed", "pending"}
    assert (tmp_path / "artifacts" / "validation" / "gate3_reports").exists()
    assert (tmp_path / "artifacts" / "validation" / "gate3_packages").exists()


def test_local_web_action_runner_generates_replay_slippage_artifacts(tmp_path) -> None:
    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
            }
        ),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
    )

    result = runner.generate_replay_slippage_report()

    assert result.status in {"completed", "pending"}
    assert (
        tmp_path / "artifacts" / "validation" / "replay_slippage_summaries"
    ).exists()


def test_local_web_action_runner_runs_market_day_automation(tmp_path) -> None:
    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
            }
        ),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
        automation_runner_builder=lambda: FakeAutomationRunner(tmp_path / "artifacts"),
    )

    result = runner.run_market_day(
        symbols=("SPY", "QQQ"),
        quantity="1",
        interval_seconds=300,
        max_heartbeats=2,
    )

    assert result.status == "completed"
    assert "market-day" in result.message.lower()


def test_local_web_action_runner_exposes_market_scheduler_controls(tmp_path) -> None:
    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
            }
        ),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
    )

    assert hasattr(runner, "start_market_scheduler")
    assert hasattr(runner, "stop_market_scheduler")
