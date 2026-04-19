from __future__ import annotations

from datetime import UTC, datetime

from tradingx.operator_control import OperatorControlStore
from tradingx.supervisor import OperatorSupervisor


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

    assert result["status"] == "completed"
    assert broker.flatten_calls == 1
