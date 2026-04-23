from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from prometheus_client import CollectorRegistry

from tradingx.controller import PaperTradingLoopController
from tradingx.journal import SqliteOmsJournal
from tradingx.monitoring import StageMetrics
from tradingx.operator_control import OperatorControlStore
from tradingx.persistence import FilesystemArtifactStore
from tradingx.policy import PolicySnapshotStore, build_week1_policy_snapshot
from tradingx.runtime_logging import StructuredRuntimeLogger
from tradingx.service import PaperTradingService
from tradingx.snapshots import ContentAddressedSnapshotStore
from tradingx.strategy import DeterministicBaselineStrategy
from tradingx.supervisor import OperatorSupervisor
from tradingx.types import (
    AccountSnapshot,
    LatestQuote,
    MarketSnapshot,
    PortfolioState,
    ReconciliationSnapshot,
    TradeIntent,
    TradingLoopResult,
)


class FakeMarketData:
    def __init__(self) -> None:
        self.calls = 0

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        self.calls += 1
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("600.00"),
            bid_price=Decimal("599.90"),
            ask_price=Decimal("600.10"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=datetime(2026, 4, 17, 17, 0, self.calls, tzinfo=UTC),
        )

    def get_latest_quote(self, symbol: str) -> LatestQuote:
        return LatestQuote(
            symbol=symbol,
            bid_price=Decimal("599.90"),
            ask_price=Decimal("600.10"),
            timestamp=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        )


class FakeExecution:
    def submit_market_order(self, *args, **kwargs):  # pragma: no cover - not used
        raise AssertionError("dry-run path should not submit market orders")

    def submit_marketable_limit_order(  # pragma: no cover - not used
        self,
        *args,
        **kwargs,
    ):
        raise AssertionError("dry-run path should not submit limit orders")

    def find_order_by_client_id(self, client_order_id: str):
        return None


class FakePortfolio:
    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            buying_power=Decimal("200000"),
            positions=(),
            open_orders=(),
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            cash=Decimal("1000.00"),
            equity=Decimal("1000.00"),
            buying_power=Decimal("2000.00"),
        )

    def get_position_quantity(self, symbol: str) -> Decimal:
        return Decimal("0")


class FakeLoopRiskEngine:
    class Config:
        class Runtime:
            manual_kill_switch_active = False

        runtime = Runtime()

    _config = Config()

    def evaluate_trade_intent(
        self,
        intent,
        market_snapshot,
        portfolio_state,
        *,
        broker_state_timestamp,
        is_live_order=False,
    ):
        del market_snapshot, portfolio_state, broker_state_timestamp
        del is_live_order
        return type(
            "RiskResult",
            (),
            {
                "allowed": True,
                "blocked": False,
                "event": None,
                "control_type": "",
                "control_severity": "",
                "control_reason": "",
            },
        )()


class FakeRegularHours:
    def __call__(self, observed_at) -> bool:
        del observed_at
        return True


class FakeLoopController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Decimal]] = []

    def run_trading_cycle(self, symbol: str, quantity: Decimal) -> TradingLoopResult:
        self.calls.append((symbol, quantity))
        timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
        return TradingLoopResult(
            terminal_state="reconciled_trade",
            trade_intent=TradeIntent(
                intent_id=f"intent-{symbol.lower()}",
                candidate_id="baseline-long-only-v1",
                symbol=symbol,
                side="buy",
                quantity=quantity,
                reason_code="baseline_long_entry",
                generated_at_utc=timestamp,
            ),
            order_record=None,
            risk_event=None,
            reconciliation=ReconciliationSnapshot(
                reconciliation_id=f"reconcile-{symbol.lower()}",
                portfolio_state=PortfolioState(
                    as_of_utc=timestamp,
                    cash=Decimal("10000.00"),
                    equity=Decimal("10010.00"),
                    buying_power=Decimal("20000.00"),
                    positions=(),
                    open_orders=(),
                ),
                broker_state_age_seconds=0,
                differences=(),
                resolved=True,
            ),
            artifact_paths=(Path(f"artifacts/{symbol.lower()}.json"),),
        )


class FakeNonePortfolioPlanner:
    last_strategy_id = "baseline-long-only-v1"

    def plan_for_service(
        self,
        *,
        symbols,
        portfolio_state,
        default_quantity,
    ):
        del symbols, portfolio_state, default_quantity
        return None


class FakeChildProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.alive = True
        self.stop_requested = False
        self.exitcode: int | None = None

    def is_alive(self) -> bool:
        return self.alive

    def request_stop(self) -> None:
        self.stop_requested = True

    def terminate(self) -> None:
        self.alive = False
        self.exitcode = -15

    def kill(self) -> None:
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


def test_paper_trading_loop_controller_writes_runtime_log_for_dry_run(tmp_path) -> None:
    controller = PaperTradingLoopController(
        market_data=FakeMarketData(),
        execution=FakeExecution(),
        portfolio=FakePortfolio(),
        risk=FakeLoopRiskEngine(),
        strategy=DeterministicBaselineStrategy(
            now_provider=lambda: datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        ),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=FakeRegularHours(),
        now_provider=lambda: datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        policy_snapshot=build_week1_policy_snapshot(
            generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
            artifact_root=tmp_path / "artifacts",
            git_sha="abc1234",
            dry_run=True,
        ),
        policy_store=PolicySnapshotStore(tmp_path / "data" / "policy"),
        snapshot_store=ContentAddressedSnapshotStore(tmp_path / "data" / "snapshots"),
        journal=SqliteOmsJournal(tmp_path / "data" / "journal.db"),
        git_sha="abc1234",
        dry_run=True,
        runtime_logger=StructuredRuntimeLogger(
            component="controller",
            root_dir=tmp_path / "data" / "logs",
            now_provider=lambda: datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        ),
    )

    result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert result.terminal_state == "dry_run"
    log_lines = (
        (tmp_path / "data" / "logs" / "controller.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    payloads = [json.loads(line) for line in log_lines]
    assert any(
        payload["event_type"] == "decision_recorded"
        and payload["decision_snapshot_id"]
        and payload["cycle_correlation_id"].startswith("cycle-")
        for payload in payloads
    )
    assert any(
        payload["event_type"] == "dry_run_simulated"
        and payload["decision_snapshot_id"]
        and payload["cycle_correlation_id"].startswith("cycle-")
        for payload in payloads
    )


def test_paper_trading_service_writes_cycle_logs(tmp_path) -> None:
    service = PaperTradingService(
        loop_controller=FakeLoopController(),
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        runtime_logger=StructuredRuntimeLogger(
            component="service",
            root_dir=tmp_path / "data" / "logs",
            now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        ),
    )

    result = service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert result.last_cycle.cycle_status == "executed"
    payloads = [
        json.loads(line)
        for line in (tmp_path / "data" / "logs" / "service.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(payload["event_type"] == "cycle_started" for payload in payloads)
    assert any(
        payload["event_type"] == "cycle_completed"
        and payload["cycle_correlation_id"]
        and payload["fields"]["cycle_status"] == "executed"
        for payload in payloads
    )


def test_paper_trading_service_logs_planner_no_candidate_event(tmp_path) -> None:
    service = PaperTradingService(
        loop_controller=FakeLoopController(),
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        portfolio_planner=FakeNonePortfolioPlanner(),
        runtime_logger=StructuredRuntimeLogger(
            component="service",
            root_dir=tmp_path / "data" / "logs",
            now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        ),
    )

    result = service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert result.last_cycle.cycle_status == "recovery_required"
    payloads = [
        json.loads(line)
        for line in (tmp_path / "data" / "logs" / "service.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(
        payload["event_type"] == "planner_no_candidate"
        and payload["severity"] == "warning"
        and payload["fields"]["reason"] == "planner_returned_none"
        and payload["fields"]["strategy_id"] == "baseline-long-only-v1"
        for payload in payloads
    )


def test_operator_supervisor_writes_command_logs(tmp_path) -> None:
    supervisor = OperatorSupervisor(
        control_store=OperatorControlStore(tmp_path / "data" / "control"),
        artifact_root=tmp_path / "artifacts" / "operator_platform",
        child_factory=FakeChildFactory(),
        broker_operator=FakeBrokerOperator(),
        today_summary_provider=lambda: {"cycle_count": 1},
        now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
        runtime_logger=StructuredRuntimeLogger(
            component="supervisor",
            root_dir=tmp_path / "data" / "logs",
            now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
        ),
    )

    supervisor.execute_command("halt")

    payloads = [
        json.loads(line)
        for line in (tmp_path / "data" / "logs" / "supervisor.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(
        payload["event_type"] == "operator_command"
        and payload["fields"]["command"] == "halt"
        and payload["fields"]["status"] == "completed"
        for payload in payloads
    )
