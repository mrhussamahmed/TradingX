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
