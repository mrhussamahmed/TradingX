from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from decimal import Decimal

from tradingx import supervisor as supervisor_module
from tradingx.config import TradingConfig
from tradingx.live_enablement import BrokerModeDecision
from tradingx.operator_control import OperatorControlStore
from tradingx.supervisor import MultiprocessingChildHandle, OperatorSupervisor


class FakeChildProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.alive = True
        self.stop_requested = False
        self.terminated = False
        self.killed = False
        self.exitcode: int | None = None

    def is_alive(self) -> bool:
        return self.alive

    def request_stop(self) -> None:
        self.stop_requested = True

    def terminate(self) -> None:
        self.terminated = True
        self.alive = False
        self.exitcode = -15

    def kill(self) -> None:
        self.killed = True
        self.alive = False
        self.exitcode = -9


class FakeChildFactory:
    def __init__(self) -> None:
        self.children: list[FakeChildProcess] = []

    def start(self) -> FakeChildProcess:
        child = FakeChildProcess(pid=100 + len(self.children))
        self.children.append(child)
        return child


class FakeBrokerOperator:
    def __init__(self) -> None:
        self.flatten_calls = 0

    def get_positions_summary(self) -> str:
        return "SPY 1 share"

    def flatten_all(self) -> dict[str, int]:
        self.flatten_calls += 1
        return {"canceled_order_count": 1, "flattened_position_count": 1}


def test_operator_supervisor_starts_child_and_persists_state(tmp_path) -> None:
    factory = FakeChildFactory()
    supervisor = OperatorSupervisor(
        control_store=OperatorControlStore(tmp_path / "data" / "control"),
        artifact_root=tmp_path / "artifacts" / "operator_platform",
        child_factory=factory,
        broker_operator=FakeBrokerOperator(),
        today_summary_provider=lambda: {"cycle_count": 1},
        now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
    )

    supervisor.run_once()

    state = supervisor.get_state()
    assert state.child_status == "running"
    assert state.child_pid == 100
    assert (
        tmp_path / "artifacts" / "operator_platform" / "supervisor" / "state.json"
    ).exists()


def test_operator_supervisor_status_command_is_read_only(tmp_path) -> None:
    factory = FakeChildFactory()
    supervisor = OperatorSupervisor(
        control_store=OperatorControlStore(tmp_path / "data" / "control"),
        artifact_root=tmp_path / "artifacts" / "operator_platform",
        child_factory=factory,
        broker_operator=FakeBrokerOperator(),
        today_summary_provider=lambda: {"cycle_count": 1},
        now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
    )

    result = supervisor.execute_command("status")

    assert result["status"] == "completed"
    assert factory.children == []


def test_operator_supervisor_kill_and_resume_cycle(tmp_path) -> None:
    factory = FakeChildFactory()
    supervisor = OperatorSupervisor(
        control_store=OperatorControlStore(tmp_path / "data" / "control"),
        artifact_root=tmp_path / "artifacts" / "operator_platform",
        child_factory=factory,
        broker_operator=FakeBrokerOperator(),
        today_summary_provider=lambda: {"cycle_count": 1},
        now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
    )
    supervisor.run_once()

    kill_result = supervisor.execute_command("kill")

    assert kill_result["status"] == "completed"
    assert factory.children[0].stop_requested is True
    assert factory.children[0].terminated is False
    assert supervisor.get_state().kill_requested is True

    factory.children[0].alive = False
    factory.children[0].exitcode = 0

    resume_result = supervisor.execute_command("resume")
    supervisor.run_once()

    assert resume_result["status"] == "completed"
    assert supervisor.get_state().kill_requested is False
    assert len(factory.children) == 2


def test_operator_supervisor_restarts_child_when_enabled(tmp_path) -> None:
    factory = FakeChildFactory()
    supervisor = OperatorSupervisor(
        control_store=OperatorControlStore(tmp_path / "data" / "control"),
        artifact_root=tmp_path / "artifacts" / "operator_platform",
        child_factory=factory,
        broker_operator=FakeBrokerOperator(),
        today_summary_provider=lambda: {"cycle_count": 1},
        now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
        restart_policy_enabled=True,
        max_restart_attempts=1,
    )
    supervisor.run_once()
    factory.children[0].alive = False
    factory.children[0].exitcode = 1

    supervisor.run_once()

    assert len(factory.children) == 2
    assert supervisor.get_state().restart_count == 1


def test_operator_supervisor_does_not_restart_unexpected_exit_when_disabled(
    tmp_path,
) -> None:
    factory = FakeChildFactory()
    supervisor = OperatorSupervisor(
        control_store=OperatorControlStore(tmp_path / "data" / "control"),
        artifact_root=tmp_path / "artifacts" / "operator_platform",
        child_factory=factory,
        broker_operator=FakeBrokerOperator(),
        today_summary_provider=lambda: {"cycle_count": 1},
        now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
        restart_policy_enabled=False,
        max_restart_attempts=0,
    )
    supervisor.run_once()
    factory.children[0].alive = False
    factory.children[0].exitcode = 1

    supervisor.run_once()

    assert len(factory.children) == 1
    assert supervisor.get_state().child_status == "stopped"


def test_operator_supervisor_flatten_uses_broker_operator(tmp_path) -> None:
    broker = FakeBrokerOperator()
    supervisor = OperatorSupervisor(
        control_store=OperatorControlStore(tmp_path / "data" / "control"),
        artifact_root=tmp_path / "artifacts" / "operator_platform",
        child_factory=FakeChildFactory(),
        broker_operator=broker,
        today_summary_provider=lambda: {"cycle_count": 1},
        now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
    )

    result = supervisor.execute_command("flatten")

    deadline = time.perf_counter() + 0.2
    while broker.flatten_calls == 0 and time.perf_counter() < deadline:
        time.sleep(0.01)

    assert result["status"] == "accepted"
    assert broker.flatten_calls == 1


class _StopEvent:
    def __init__(self) -> None:
        self.set_called = False

    def set(self) -> None:
        self.set_called = True


class _HandleProcess:
    def __init__(self) -> None:
        self.pid = 123
        self.exitcode: int | None = None
        self.join_calls: list[int] = []
        self.terminate_called = False
        self.kill_called = False
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: int) -> None:
        self.join_calls.append(timeout)

    def terminate(self) -> None:
        self.terminate_called = True

    def kill(self) -> None:
        self.kill_called = True
        self._alive = False
        self.exitcode = -9


def test_multiprocessing_child_handle_terminate_escalates_to_kill() -> None:
    process = _HandleProcess()
    handle = MultiprocessingChildHandle(process=process, stop_event=_StopEvent())

    handle.terminate()

    assert process.terminate_called is True
    assert process.kill_called is True
    assert process.join_calls == [5, 5, 5]


def test_multiprocessing_child_handle_kill_raises_if_process_survives() -> None:
    process = _HandleProcess()

    def stubborn_kill() -> None:
        process.kill_called = True

    process.kill = stubborn_kill  # type: ignore[assignment]
    handle = MultiprocessingChildHandle(process=process, stop_event=_StopEvent())

    try:
        handle.kill()
    except RuntimeError as error:
        assert "still alive" in str(error)
    else:
        raise AssertionError("Expected kill() to raise when the child survives.")


def test_operator_supervisor_flattens_asynchronously(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingBroker(FakeBrokerOperator):
        def flatten_all(self) -> dict[str, int]:
            self.flatten_calls += 1
            started.set()
            release.wait(timeout=1.0)
            return {"canceled_order_count": 1, "flattened_position_count": 1}

    supervisor = OperatorSupervisor(
        control_store=OperatorControlStore(tmp_path / "data" / "control"),
        artifact_root=tmp_path / "artifacts" / "operator_platform",
        child_factory=FakeChildFactory(),
        broker_operator=BlockingBroker(),
        today_summary_provider=lambda: {"cycle_count": 1},
        now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
    )

    started_at = time.perf_counter()
    result = supervisor.execute_command("flatten")
    elapsed = time.perf_counter() - started_at

    assert result["status"] == "accepted"
    assert elapsed < 0.05
    assert started.wait(timeout=0.2) is True
    release.set()


def test_operator_supervisor_waits_for_restart_cooldown(tmp_path) -> None:
    factory = FakeChildFactory()
    timestamps = iter(
        (
            datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 1, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 5, tzinfo=UTC),
            datetime(2026, 4, 20, 12, 0, 6, tzinfo=UTC),
        )
    )
    supervisor = OperatorSupervisor(
        control_store=OperatorControlStore(tmp_path / "data" / "control"),
        artifact_root=tmp_path / "artifacts" / "operator_platform",
        child_factory=factory,
        broker_operator=FakeBrokerOperator(),
        today_summary_provider=lambda: {"cycle_count": 1},
        now_provider=lambda: next(timestamps),
        restart_policy_enabled=True,
        max_restart_attempts=2,
        restart_cooldown_seconds=5,
    )

    supervisor.run_once()
    factory.children[0].alive = False
    factory.children[0].exitcode = 1

    supervisor.run_once()
    assert len(factory.children) == 1

    supervisor.run_once()
    assert len(factory.children) == 1

    supervisor.run_once()
    assert len(factory.children) == 2


def test_build_default_operator_supervisor_uses_mode_aware_helpers(
    monkeypatch, tmp_path
) -> None:
    helper_calls: dict[str, object] = {}

    class RecordingSupervisor:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(
        supervisor_module,
        "resolve_broker_mode",
        lambda config: BrokerModeDecision(
            requested_mode="live",
            effective_mode="live",
            live_requested=True,
            live_allowed=True,
            disable_reasons=(),
        ),
    )

    def fake_build_trading_client(config, decision):
        del config
        helper_calls["client_mode"] = decision.requested_mode
        return object()

    def fake_build_market_data(config, *, broker_mode=None):
        del config
        helper_calls["market_data_mode"] = broker_mode
        return object()

    monkeypatch.setattr(
        supervisor_module,
        "build_trading_client_for_mode",
        fake_build_trading_client,
    )
    monkeypatch.setattr(
        supervisor_module,
        "build_market_data_gateway_for_mode",
        fake_build_market_data,
    )
    monkeypatch.setattr(
        supervisor_module,
        "MultiprocessingChildFactory",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        supervisor_module,
        "AlpacaPaperBrokerOperator",
        lambda trading_client, market_data: (trading_client, market_data),
    )
    monkeypatch.setattr(
        supervisor_module,
        "OperatorSupervisor",
        RecordingSupervisor,
    )

    supervisor = supervisor_module.build_default_operator_supervisor(
        TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
                "ALPACA_LIVE_API_KEY": "pk-live",
                "ALPACA_LIVE_API_SECRET": "sk-live",
                "TRADINGX_BROKER_MODE": "live",
            }
        ),
        env_file=tmp_path / ".env",
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        poll_interval_seconds=30,
    )

    assert helper_calls == {
        "client_mode": "live",
        "market_data_mode": "live",
    }
    assert isinstance(supervisor, RecordingSupervisor)
