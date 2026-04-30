from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.activation import BlueprintActivationValidationError
from tradingx.config import TradingConfig
from tradingx.service import ServiceRunResult
from tradingx.types import ServiceCycleSnapshot
from tradingx.web import runtime as web_runtime
from tradingx.web.runtime import (
    LocalServiceManager,
    LocalWebActionRunner,
    build_default_local_web_components,
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


class FakeGateController:
    def __init__(self) -> None:
        self.called_with = None

    def generate_gate_report(self, **kwargs):
        self.called_with = kwargs

        class Result:
            artifact_paths = (Path("artifacts/validation/gate-report.json"),)

        return Result()


def _write_benchmark_stack_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "hurdle_returns": ["0.0001"],
                "opportunity_cost_returns": ["0.0002"],
                "opportunity_cost_weights": [
                    {"symbol": "SPY", "weight": "0.6"},
                    {"symbol": "AGG", "weight": "0.4"},
                ],
                "operating_constraint": {
                    "max_drawdown_design": "0.15",
                    "max_drawdown_halt": "0.25",
                    "cdar_threshold": "0.08",
                    "cdar_confidence": "0.95",
                },
            }
        ),
        encoding="utf-8",
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


def test_local_service_manager_default_builder_uses_generic_service_builder(
    monkeypatch,
) -> None:
    fake_service = FakePaperService()
    captured: list[object] = []

    monkeypatch.setattr(
        web_runtime,
        "build_default_trading_service",
        lambda config: captured.append(config) or fake_service,
    )

    manager = LocalServiceManager(config=TradingConfig.from_mapping({}))

    assert manager._service_builder() is fake_service
    assert len(captured) == 1


def test_build_default_local_web_components_shares_runtime_service_manager(
    monkeypatch, tmp_path
) -> None:
    service_manager_instances: list[object] = []
    activation_kwargs: list[dict[str, object]] = []

    class RecordingServiceManager:
        def __init__(self, *, config, service_builder=None) -> None:
            self.config = config
            self.service_builder = service_builder
            service_manager_instances.append(self)

    class RecordingSchedulerManager:
        def __init__(self, *, config) -> None:
            self.config = config

    class RecordingRuntimeHostManager:
        def __init__(self, *, service_manager, **kwargs) -> None:
            self.service_manager = service_manager
            self.kwargs = kwargs

    monkeypatch.setattr(web_runtime, "LocalServiceManager", RecordingServiceManager)
    monkeypatch.setattr(
        web_runtime,
        "LocalSchedulerManager",
        RecordingSchedulerManager,
    )
    monkeypatch.setattr(
        web_runtime,
        "LocalRuntimeHostManager",
        RecordingRuntimeHostManager,
    )
    monkeypatch.setattr(
        web_runtime,
        "build_trading_client_for_mode",
        lambda config, decision: object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "build_market_data_gateway_for_mode",
        lambda config, *, broker_mode=None: object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "LocalActivationGateway",
        lambda *args, **kwargs: activation_kwargs.append(kwargs) or object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "HistoricalWarmupService",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "RuntimeOpportunityPlanner",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        web_runtime,
        "AlpacaPortfolioGateway",
        lambda *args, **kwargs: object(),
    )

    config = TradingConfig.from_mapping(
        {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
    )

    read_model, action_runner = build_default_local_web_components(config)

    assert len(service_manager_instances) == 1
    assert service_manager_instances[0].service_builder is not None
    assert read_model._service_manager is service_manager_instances[0]
    assert action_runner._service_manager is service_manager_instances[0]
    assert (
        action_runner._runtime_host_manager.service_manager
        is service_manager_instances[0]
    )
    assert activation_kwargs
    assert "legacy_non_authority_mode" not in activation_kwargs[0]
    assert "promotion_decision_provider" in activation_kwargs[0]
    assert "required_promotion_state" in activation_kwargs[0]


def test_activate_blueprint_returns_blocked_for_validation_error(
    monkeypatch,
    tmp_path,
) -> None:
    blueprint_dir = tmp_path / "config" / "portfolio" / "blueprints"
    blueprint_dir.mkdir(parents=True)
    (blueprint_dir / "bp-test-v1.yaml").write_text(
        "\n".join(
            (
                "blueprint_id: bp-test-v1",
                "sleeve_budgets:",
                "  - sleeve_id: trend-following-v1",
                "    budget_fraction_of_equity: 1.0",
                "    max_correlation_with_other_sleeves: 0.85",
            )
        ),
        encoding="utf-8",
    )

    class RejectingActivationGateway:
        def stage_blueprint_activation_for_next_start(self, **kwargs):
            del kwargs
            raise BlueprintActivationValidationError(
                "Blueprint activation preview is stale; rerun preflight."
            )

    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
    )
    monkeypatch.setattr(
        runner,
        "_blueprint_activation_gateway",
        lambda: RejectingActivationGateway(),
    )

    result = runner.activate_blueprint(
        blueprint_id="bp-test-v1",
        preview_hash="sha256:stale",
    )

    assert result.status == "blocked"
    assert result.action_type == "blueprint_activate"
    assert "stale" in result.message


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
    assert "legacy_non_authority" in report.message
    assert "legacy_non_authority" in package.message
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


def test_local_web_action_runner_rejects_gate_report_benchmark_outside_artifact_root(
    tmp_path, monkeypatch
) -> None:
    benchmark_file = tmp_path / "outside.json"
    benchmark_file.write_text(
        json.dumps(
            {
                "hurdle_returns": ["0.0001", "0.0001"],
                "opportunity_cost_returns": ["0.0002", "0.0002"],
                "opportunity_cost_weights": [
                    {"symbol": "SPY", "weight": "0.6"},
                    {"symbol": "AGG", "weight": "0.4"},
                ],
                "operating_constraint": {
                    "max_drawdown_design": "0.15",
                    "max_drawdown_halt": "0.25",
                    "cdar_threshold": "0.08",
                    "cdar_confidence": "0.95",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tradingx.web.runtime.build_default_gate_validation_controller",
        lambda config, artifact_root: None,
    )
    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
    )

    with pytest.raises(ValueError, match="artifact root"):
        runner.generate_gate_report(
            gate="1",
            benchmark_stack_file=str(benchmark_file),
            window_start="2026-04-01",
            window_end="2026-04-17",
        )


def test_local_web_action_runner_fake_metric_context_fails_closed(
    tmp_path,
    monkeypatch,
) -> None:
    artifact_root = tmp_path / "artifacts"
    benchmark_file = artifact_root / "benchmark-stack.json"
    _write_benchmark_stack_file(benchmark_file)
    fake_controller = FakeGateController()
    monkeypatch.setattr(
        "tradingx.web.runtime.build_default_gate_validation_controller",
        lambda config, artifact_root: fake_controller,
    )
    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(artifact_root)}
        ),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
    )

    result = runner.generate_gate_report(
        gate="1",
        benchmark_stack_file=str(benchmark_file),
        window_start="2026-04-01",
        window_end="2026-04-17",
        experiment_id="exp-fake",
        run_id="run-fake",
        promotion_decision_scope="scope-prod-001",
        metric_release_token="sha256:" + "9" * 64,
        dataset_manifest_id="dataset-fake",
    )

    assert result.status == "completed"
    context = fake_controller.called_with["metric_visibility_context"]
    assert context.is_released is False
    assert "trial_lineage_contaminated" in context.blocker_codes
    assert "point_in_time_data_incomplete" in context.blocker_codes


def test_local_web_action_runner_resolves_released_metric_context(
    tmp_path,
    monkeypatch,
) -> None:
    from tradingx.experiments import ExperimentLedger

    artifact_root = tmp_path / "artifacts"
    benchmark_file = artifact_root / "benchmark-stack.json"
    _write_benchmark_stack_file(benchmark_file)
    dataset_file = artifact_root / "datasets" / "dataset-spy-v1.json"
    dataset_file.parent.mkdir(parents=True, exist_ok=True)
    dataset_file.write_text(
        Path(
            "tests/fixtures/data_fingerprints/dataset_manifest_complete.json"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ledger = ExperimentLedger(ledger_root=artifact_root / "experiments")
    registration = json.loads(
        Path(
            "tests/fixtures/experiments/experiment_registration_pre_result.json"
        ).read_text(encoding="utf-8")
    )
    completed_run = json.loads(
        Path("tests/fixtures/experiments/experiment_run_completed.json").read_text(
            encoding="utf-8"
        )
    )
    started_run = dict(completed_run)
    started_run["lifecycle_status"] = "started"
    started_run["termination_reason_code"] = "started"
    ledger.append_registration(registration)
    ledger.append_run_record(started_run)
    ledger.append_run_record(completed_run)
    fake_controller = FakeGateController()
    monkeypatch.setattr(
        "tradingx.web.runtime.build_default_gate_validation_controller",
        lambda config, artifact_root: fake_controller,
    )
    runner = LocalWebActionRunner(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(artifact_root)}
        ),
        repo_root=tmp_path,
        service_manager=LocalServiceManager(config=TradingConfig.from_mapping({})),
    )

    runner.generate_gate_report(
        gate="1",
        benchmark_stack_file=str(benchmark_file),
        window_start="2026-04-01",
        window_end="2026-04-17",
        experiment_id="exp-001",
        run_id="run-001",
        promotion_decision_scope="scope-prod-001",
        metric_release_token="sha256:" + "b" * 64,
        dataset_manifest_id="dataset-spy-v1",
        dataset_manifest_file=str(dataset_file),
    )

    context = fake_controller.called_with["metric_visibility_context"]
    assert context.is_released is True
    assert fake_controller.called_with["dataset_manifest_id"] == "dataset-spy-v1"
