from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from alpaca.trading.enums import OrderSide, TimeInForce
from prometheus_client import CollectorRegistry

from tradingx.controller import PaperTradingLoopController, RoundTripController
from tradingx.execution import OrderRejected
from tradingx.journal import SqliteOmsJournal, build_client_order_id
from tradingx.monitoring import StageMetrics
from tradingx.persistence import FilesystemArtifactStore
from tradingx.policy import PolicySnapshotStore, build_week1_policy_snapshot
from tradingx.risk import PreTradeRiskContext, RiskDecision
from tradingx.snapshots import ContentAddressedSnapshotStore
from tradingx.strategy import DeterministicBaselineStrategy
from tradingx.types import (
    AccountSnapshot,
    LatestQuote,
    MarketSnapshot,
    OrderRecord,
    PortfolioState,
)


class FakeRiskEngine:
    def __init__(self) -> None:
        self.calls = []

    def assert_order_allowed(
        self, context: PreTradeRiskContext, *, is_live_order: bool
    ) -> None:
        self.calls.append((context, is_live_order))


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


class FrozenMarketData(FakeMarketData):
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("600.00"),
            bid_price=Decimal("599.90"),
            ask_price=Decimal("600.10"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        )


class FakeExecution:
    def __init__(self) -> None:
        self.submissions = []
        self.fill_count = 0
        self.orders_by_client_id: dict[str, OrderRecord] = {}

    def submit_market_order(
        self,
        symbol: str,
        quantity: Decimal,
        side: OrderSide,
        *,
        client_order_id: str | None = None,
    ) -> OrderRecord:
        order_id = f"order-{len(self.submissions) + 1}"
        self.submissions.append((symbol, quantity, side, client_order_id))
        return OrderRecord(
            order_id=order_id,
            client_order_id=client_order_id or f"{order_id}-client",
            symbol=symbol,
            side=side.value,
            status="accepted",
            filled_qty=Decimal("0"),
            filled_avg_price=Decimal("0"),
        )

    def submit_marketable_limit_order(
        self,
        symbol: str,
        quantity: Decimal,
        side: OrderSide,
        *,
        limit_price: Decimal,
        time_in_force: TimeInForce,
        client_order_id: str | None = None,
    ) -> OrderRecord:
        order_id = f"order-{len(self.submissions) + 1}"
        self.submissions.append(
            (
                symbol,
                quantity,
                side,
                limit_price,
                time_in_force,
                client_order_id,
            )
        )
        return OrderRecord(
            order_id=order_id,
            client_order_id=client_order_id or f"{order_id}-client",
            symbol=symbol,
            side=side.value,
            status="accepted",
            filled_qty=Decimal("0"),
            filled_avg_price=Decimal("0"),
        )

    def find_order_by_client_id(self, client_order_id: str) -> OrderRecord | None:
        return self.orders_by_client_id.get(client_order_id)

    def submit_oco_exit_order(
        self,
        symbol: str,
        quantity: Decimal,
        *,
        take_profit_limit: Decimal,
        stop_price: Decimal,
    ) -> OrderRecord:
        order_id = f"order-{len(self.submissions) + 1}"
        self.submissions.append(
            (symbol, quantity, "oco", take_profit_limit, stop_price)
        )
        return OrderRecord(
            order_id=order_id,
            client_order_id=f"{order_id}-client",
            symbol=symbol,
            side="sell",
            status="accepted",
            filled_qty=Decimal("0"),
            filled_avg_price=Decimal("0"),
        )

    def close_position(self, symbol: str) -> OrderRecord:
        order_id = f"order-{len(self.submissions) + 1}"
        self.submissions.append((symbol, "close_position"))
        return OrderRecord(
            order_id=order_id,
            client_order_id=f"{order_id}-client",
            symbol=symbol,
            side="sell",
            status="accepted",
            filled_qty=Decimal("0"),
            filled_avg_price=Decimal("0"),
        )

    def wait_for_fill(
        self,
        order_id: str,
        *,
        timeout_seconds: float = 30,
        poll_interval_seconds: float = 1,
    ) -> OrderRecord:
        self.fill_count += 1
        side = "buy" if self.fill_count == 1 else "sell"
        return OrderRecord(
            order_id=order_id,
            client_order_id=f"{order_id}-client",
            symbol="SPY",
            side=side,
            status="filled",
            filled_qty=Decimal("1"),
            filled_avg_price=Decimal("600.00"),
        )

    def wait_for_oco_exit_fill(
        self,
        order_id: str,
        *,
        timeout_seconds: float = 30,
        poll_interval_seconds: float = 1,
    ) -> OrderRecord:
        return OrderRecord(
            order_id=order_id,
            client_order_id=f"{order_id}-client",
            symbol="SPY",
            side="sell",
            status="filled",
            filled_qty=Decimal("1"),
            filled_avg_price=Decimal("599.90"),
        )


class FakePortfolio:
    def __init__(self) -> None:
        self.snapshots = [
            AccountSnapshot(
                cash=Decimal("1000.00"),
                equity=Decimal("1000.00"),
                buying_power=Decimal("2000.00"),
            ),
            AccountSnapshot(
                cash=Decimal("1000.25"),
                equity=Decimal("1000.25"),
                buying_power=Decimal("2000.25"),
            ),
        ]
        self.position_quantities = [
            Decimal("0"),
            Decimal("1"),
            Decimal("0"),
        ]

    def get_account_snapshot(self) -> AccountSnapshot:
        return self.snapshots.pop(0)

    def get_position_quantity(self, symbol: str) -> Decimal:
        return self.position_quantities.pop(0)

    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            buying_power=Decimal("200000"),
            positions=(),
            open_orders=(),
        )


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
    ) -> RiskDecision:
        del intent, market_snapshot, portfolio_state, broker_state_timestamp
        return RiskDecision(decision="approved", control_code="passed", event=None)


class FakeRegularHours:
    def __call__(self, observed_at: datetime) -> bool:
        del observed_at
        return True


class RejectingExecution(FakeExecution):
    def submit_marketable_limit_order(
        self,
        symbol: str,
        quantity: Decimal,
        side: OrderSide,
        *,
        limit_price: Decimal,
        time_in_force: TimeInForce,
        client_order_id: str | None = None,
    ) -> OrderRecord:
        del symbol, quantity, side, limit_price, time_in_force, client_order_id
        raise OrderRejected(
            '{"message":"insufficient buying power for requested exposure"}'
        )


def test_round_trip_controller_writes_structured_log(tmp_path) -> None:
    controller = RoundTripController(
        market_data=FakeMarketData(),
        execution=FakeExecution(),
        portfolio=FakePortfolio(),
        risk=FakeRiskEngine(),
    )

    result = controller.run_paper_roundtrip("SPY", Decimal("1"), log_dir=tmp_path)

    assert result.buy_order.status == "filled"
    assert result.sell_order.status == "filled"
    assert result.final_position_quantity == Decimal("0")
    assert result.log_path.exists()
    assert controller._execution.submissions[0] == (
        "SPY",
        Decimal("1"),
        OrderSide.BUY,
        None,
    )
    assert controller._execution.submissions[1][1] == "close_position"

    payload = json.loads(result.log_path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "SPY"
    assert payload["final_position_quantity"] == "0"


def test_paper_trading_loop_controller_dry_run_persists_snapshot_and_journal(
    tmp_path: Path,
) -> None:
    execution = FakeExecution()
    policy_snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=tmp_path / "artifacts",
        git_sha="abc1234",
        dry_run=True,
    )
    controller = PaperTradingLoopController(
        market_data=FakeMarketData(),
        execution=execution,
        portfolio=FakePortfolio(),
        risk=FakeLoopRiskEngine(),
        strategy=DeterministicBaselineStrategy(
            now_provider=lambda: datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        ),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=FakeRegularHours(),
        now_provider=lambda: datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        policy_snapshot=policy_snapshot,
        policy_store=PolicySnapshotStore(tmp_path / "data" / "policy"),
        snapshot_store=ContentAddressedSnapshotStore(tmp_path / "data" / "snapshots"),
        journal=SqliteOmsJournal(tmp_path / "data" / "journal.db"),
        git_sha="abc1234",
        dry_run=True,
    )

    result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert result.terminal_state == "dry_run"
    assert execution.submissions == []
    snapshot_dir = tmp_path / "data" / "snapshots"
    assert any(snapshot_dir.glob("*.json"))
    journal_rows = SqliteOmsJournal(tmp_path / "data" / "journal.db").list_events()
    assert [row.event_type for row in journal_rows] == ["intent", "simulated"]
    assert journal_rows[-1].payload["reference_price"] == "600.10"
    assert journal_rows[-1].payload["would_submit_limit_price"] == "600.70"


def test_paper_trading_loop_controller_uses_deterministic_client_order_id(
    tmp_path: Path,
) -> None:
    execution = FakeExecution()
    policy_snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=tmp_path / "artifacts",
        git_sha="abc1234",
        dry_run=False,
    )
    controller = PaperTradingLoopController(
        market_data=FakeMarketData(),
        execution=execution,
        portfolio=FakePortfolio(),
        risk=FakeLoopRiskEngine(),
        strategy=DeterministicBaselineStrategy(
            now_provider=lambda: datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        ),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=FakeRegularHours(),
        now_provider=lambda: datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        policy_snapshot=policy_snapshot,
        policy_store=PolicySnapshotStore(tmp_path / "data" / "policy"),
        snapshot_store=ContentAddressedSnapshotStore(tmp_path / "data" / "snapshots"),
        journal=SqliteOmsJournal(tmp_path / "data" / "journal.db"),
        git_sha="abc1234",
        dry_run=False,
    )

    result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert result.terminal_state == "reconciled_trade"
    snapshot_path = next((tmp_path / "data" / "snapshots").glob("*.json"))
    expected_client_order_id = build_client_order_id(
        decision_snapshot_id=snapshot_path.stem,
        symbol="SPY",
        side="buy",
        intent_seq=0,
    )
    assert execution.submissions[0][0] == "SPY"
    assert execution.submissions[0][1] == Decimal("1")
    assert execution.submissions[0][2] == OrderSide.BUY
    assert execution.submissions[0][3] == Decimal("600.70")
    assert execution.submissions[0][4] == TimeInForce.DAY
    assert execution.submissions[0][5] == expected_client_order_id
    journal_rows = SqliteOmsJournal(tmp_path / "data" / "journal.db").list_events()
    assert journal_rows[0].client_order_id == expected_client_order_id
    assert journal_rows[-1].event_type == "fill"


def test_paper_trading_loop_controller_queries_broker_before_resubmit(
    tmp_path: Path,
) -> None:
    execution = FakeExecution()
    policy_snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=tmp_path / "artifacts",
        git_sha="abc1234",
        dry_run=False,
    )
    expected_now = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
    controller = PaperTradingLoopController(
        market_data=FrozenMarketData(),
        execution=execution,
        portfolio=FakePortfolio(),
        risk=FakeLoopRiskEngine(),
        strategy=DeterministicBaselineStrategy(now_provider=lambda: expected_now),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=FakeRegularHours(),
        now_provider=lambda: expected_now,
        policy_snapshot=policy_snapshot,
        policy_store=PolicySnapshotStore(tmp_path / "data" / "policy"),
        snapshot_store=ContentAddressedSnapshotStore(tmp_path / "data" / "snapshots"),
        journal=SqliteOmsJournal(tmp_path / "data" / "journal.db"),
        git_sha="abc1234",
        dry_run=False,
    )

    preview_result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert preview_result.terminal_state == "reconciled_trade"
    expected_client_order_id = execution.submissions[0][5]
    execution.submissions.clear()
    execution.orders_by_client_id[expected_client_order_id] = OrderRecord(
        order_id="order-existing",
        client_order_id=expected_client_order_id,
        symbol="SPY",
        side="buy",
        status="accepted",
        filled_qty=Decimal("0"),
        filled_avg_price=Decimal("0"),
    )
    artifacts = FilesystemArtifactStore(tmp_path / "artifacts")
    trade_intent = artifacts.find_latest_trade_intent("SPY")
    assert trade_intent is not None
    order_path = artifacts.order_record_path(trade_intent.intent_id)
    order_path.unlink()

    result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert result.terminal_state == "reconciled_trade"
    assert execution.submissions == []
    recovered_order = artifacts.read_order_record(trade_intent.intent_id)
    assert recovered_order is not None
    assert recovered_order.order_id == "order-existing"


def test_paper_trading_loop_controller_records_rejected_order_and_forces_reconciliation(
    tmp_path: Path,
) -> None:
    execution = RejectingExecution()
    policy_snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=tmp_path / "artifacts",
        git_sha="abc1234",
        dry_run=False,
    )
    controller = PaperTradingLoopController(
        market_data=FakeMarketData(),
        execution=execution,
        portfolio=FakePortfolio(),
        risk=FakeLoopRiskEngine(),
        strategy=DeterministicBaselineStrategy(
            now_provider=lambda: datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        ),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=FakeRegularHours(),
        now_provider=lambda: datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        policy_snapshot=policy_snapshot,
        policy_store=PolicySnapshotStore(tmp_path / "data" / "policy"),
        snapshot_store=ContentAddressedSnapshotStore(tmp_path / "data" / "snapshots"),
        journal=SqliteOmsJournal(tmp_path / "data" / "journal.db"),
        git_sha="abc1234",
        dry_run=False,
    )

    result = controller.run_trading_cycle("SPY", Decimal("1"))

    assert result.terminal_state == "rejected"
    assert result.order_record is None
    assert result.reconciliation.resolved is False
    assert result.reconciliation.differences == ("insufficient_buying_power",)
    journal_rows = SqliteOmsJournal(tmp_path / "data" / "journal.db").list_events()
    assert [row.event_type for row in journal_rows] == [
        "intent",
        "submit_attempt",
        "reject",
    ]
    assert journal_rows[-1].payload["reason_code"] == "insufficient_buying_power"
