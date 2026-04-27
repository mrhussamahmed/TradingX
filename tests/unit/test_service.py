from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from prometheus_client import CollectorRegistry

from tradingx import service as service_module
from tradingx.config import TradingConfig
from tradingx.live_enablement import BrokerModeDecision
from tradingx.monitoring import StageMetrics
from tradingx.operator_control import OperatorControlStore
from tradingx.persistence import FilesystemArtifactStore
from tradingx.runtime_logging import StructuredRuntimeLogger
from tradingx.runtime_portfolio import RuntimePortfolioPlan, RuntimePortfolioTrade
from tradingx.service import PaperTradingService
from tradingx.types import (
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    MarketSnapshot,
    PortfolioState,
    PositionSnapshot,
    ReconciliationSnapshot,
    RiskControlEvent,
    ServiceSymbolResult,
    SleeveTargetWeights,
    TradeIntent,
    TradingLoopResult,
)


class FakeLoopController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Decimal]] = []
        self.intent_calls: list[tuple[str, str, Decimal | None]] = []

    def run_trading_cycle(self, symbol: str, quantity: Decimal) -> TradingLoopResult:
        self.calls.append((symbol, quantity))
        timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
        return TradingLoopResult(
            terminal_state="reconciled_trade" if symbol == "SPY" else "blocked_trade",
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

    def execute_trade_intent(
        self,
        trade_intent: TradeIntent,
        *,
        market_snapshot: MarketSnapshot,
        universe_snapshot_id: str | None = None,
    ) -> TradingLoopResult:
        del market_snapshot, universe_snapshot_id
        self.intent_calls.append(
            (trade_intent.symbol, trade_intent.side, trade_intent.quantity)
        )
        timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
        return TradingLoopResult(
            terminal_state=(
                "reconciled_trade"
                if trade_intent.side in {"buy", "sell", "reduce"}
                else "no_action"
            ),
            trade_intent=trade_intent,
            order_record=None,
            risk_event=None,
            reconciliation=ReconciliationSnapshot(
                reconciliation_id=f"reconcile-{trade_intent.symbol.lower()}",
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
            artifact_paths=(Path(f"artifacts/{trade_intent.symbol.lower()}.json"),),
        )


class FakeRecoveryLoopController(FakeLoopController):
    def run_trading_cycle(self, symbol: str, quantity: Decimal) -> TradingLoopResult:
        self.calls.append((symbol, quantity))
        timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
        return TradingLoopResult(
            terminal_state="recovery_required",
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
                differences=("broker_position_unknown_to_journal",),
                resolved=False,
            ),
            artifact_paths=(Path(f"artifacts/{symbol.lower()}.json"),),
        )


class FakeStaleDataLoopController(FakeLoopController):
    def run_trading_cycle(self, symbol: str, quantity: Decimal) -> TradingLoopResult:
        self.calls.append((symbol, quantity))
        timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
        return TradingLoopResult(
            terminal_state="blocked_trade",
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
            risk_event=RiskControlEvent(
                event_id=f"risk-{symbol.lower()}",
                intent_id=f"intent-{symbol.lower()}",
                severity="warning",
                control_type="stale_market_data",
                blocked=True,
                recorded_at_utc=timestamp,
                operator_visible=True,
            ),
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


class FakePortfolio:
    def get_portfolio_state(self) -> PortfolioState:
        timestamp = datetime(2026, 4, 17, 18, 5, tzinfo=UTC)
        return PortfolioState(
            as_of_utc=timestamp,
            cash=Decimal("10025.00"),
            equity=Decimal("10030.00"),
            buying_power=Decimal("20030.00"),
            positions=(
                PositionSnapshot(
                    symbol="SPY",
                    quantity=Decimal("1"),
                    average_entry_price=Decimal("100.00"),
                    market_value=Decimal("101.00"),
                ),
            ),
            open_orders=(),
        )


class FakeStalePortfolio:
    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 17, 17, 58, tzinfo=UTC),
            cash=Decimal("10025.00"),
            equity=Decimal("10030.00"),
            buying_power=Decimal("20030.00"),
            positions=(),
            open_orders=(),
        )


class FakeFailingPortfolio:
    def __init__(self) -> None:
        self.calls = 0

    def get_portfolio_state(self) -> PortfolioState:
        self.calls += 1
        raise RuntimeError("broker gateway unavailable")


class FakePortfolioPlanner:
    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan:
        del symbols, portfolio_state, default_quantity
        timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
        market_snapshot = MarketSnapshot(
            symbol="SPY",
            last_trade_price=Decimal("100"),
            bid_price=Decimal("99.95"),
            ask_price=Decimal("100.05"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=timestamp,
        )
        qqq_snapshot = MarketSnapshot(
            symbol="QQQ",
            last_trade_price=Decimal("100"),
            bid_price=Decimal("99.95"),
            ask_price=Decimal("100.05"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=timestamp,
        )
        return RuntimePortfolioPlan(
            plan_id="plan-1",
            generated_at_utc=timestamp,
            strategy_id="trend-following-v1",
            universe_snapshot_id="universe-qqq-spy",
            benchmark_symbol="SPY",
            crash_overlay_active=False,
            symbols_considered=("SPY", "QQQ"),
            current_weights={"SPY": Decimal("0.30"), "QQQ": Decimal("0")},
            target_weights={"SPY": Decimal("0.10"), "QQQ": Decimal("0.20")},
            trade_intents=(
                TradeIntent(
                    intent_id="intent-spy",
                    candidate_id="trend-following-v1",
                    symbol="SPY",
                    side="reduce",
                    quantity=Decimal("20"),
                    reason_code="target_weight_reduce",
                    generated_at_utc=timestamp,
                ),
                TradeIntent(
                    intent_id="intent-qqq",
                    candidate_id="trend-following-v1",
                    symbol="QQQ",
                    side="buy",
                    quantity=Decimal("20"),
                    reason_code="target_weight_entry",
                    generated_at_utc=timestamp,
                ),
            ),
            planned_trades=(
                RuntimePortfolioTrade(
                    symbol="SPY",
                    side="reduce",
                    reason_code="target_weight_reduce",
                    last_trade_price=Decimal("100"),
                    current_weight=Decimal("0.30"),
                    target_weight=Decimal("0.10"),
                    current_quantity=Decimal("30"),
                    target_quantity=Decimal("10"),
                    delta_quantity=Decimal("20"),
                    no_trade_band_applied=False,
                ),
                RuntimePortfolioTrade(
                    symbol="QQQ",
                    side="buy",
                    reason_code="target_weight_entry",
                    last_trade_price=Decimal("100"),
                    current_weight=Decimal("0"),
                    target_weight=Decimal("0.20"),
                    current_quantity=Decimal("0"),
                    target_quantity=Decimal("20"),
                    delta_quantity=Decimal("20"),
                    no_trade_band_applied=False,
                ),
            ),
            market_snapshots={
                "SPY": market_snapshot,
                "QQQ": qqq_snapshot,
            },
        )


class FakeFailingPortfolioPlanner:
    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan:
        del symbols, portfolio_state, default_quantity
        raise RuntimeError("unsupported runtime weights")


class FakeNonePortfolioPlanner:
    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan | None:
        del symbols, portfolio_state, default_quantity
        return None


class FakeBlueprintPortfolioPlanner(FakePortfolioPlanner):
    def get_active_blueprint_activation(self) -> BlueprintActivationRecord:
        return BlueprintActivationRecord(
            activation_id="bp-activation-1",
            blueprint_id="bp-runtime",
            sleeve_activation_bindings=(
                BlueprintSleeveBinding(
                    sleeve_id="trend-following-v1",
                    strategy_id="trend-following-v1",
                    captured_snapshot_id="approved-trend",
                ),
                BlueprintSleeveBinding(
                    sleeve_id="vol-target-v1",
                    strategy_id="vol-target-v1",
                    captured_snapshot_id="approved-vol",
                ),
            ),
            status="active",
            approved_at_utc=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
            approved_by="operator",
            source_blueprint_path=Path("/tmp/bp-runtime.yaml"),
        )

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan:
        plan = super().plan_for_service(
            symbols=symbols,
            portfolio_state=portfolio_state,
            default_quantity=default_quantity,
        )
        return RuntimePortfolioPlan(
            plan_id=plan.plan_id,
            generated_at_utc=plan.generated_at_utc,
            strategy_id=plan.strategy_id,
            universe_snapshot_id=plan.universe_snapshot_id,
            benchmark_symbol=plan.benchmark_symbol,
            crash_overlay_active=plan.crash_overlay_active,
            symbols_considered=plan.symbols_considered,
            current_weights=plan.current_weights,
            target_weights=plan.target_weights,
            trade_intents=plan.trade_intents,
            planned_trades=plan.planned_trades,
            market_snapshots=plan.market_snapshots,
            per_sleeve_target_weights=(
                SleeveTargetWeights(
                    sleeve_id="trend-following-v1",
                    target_weights_by_symbol=(
                        ("SPY", Decimal("0.10")),
                        ("QQQ", Decimal("0.20")),
                    ),
                ),
                SleeveTargetWeights(
                    sleeve_id="vol-target-v1",
                    target_weights_by_symbol=(("SPY", Decimal("0.10")),),
                ),
            ),
        )


class FakeStructuralFailureBlueprintPlanner(FakeBlueprintPortfolioPlanner):
    def __init__(self, *, blueprint_path: Path, failure_reason: str) -> None:
        self._blueprint_path = blueprint_path
        self._failure_reason = failure_reason
        self._active_activation = BlueprintActivationRecord(
            activation_id="bp-activation-1",
            blueprint_id="bp-runtime",
            sleeve_activation_bindings=(
                BlueprintSleeveBinding(
                    sleeve_id="trend-following-v1",
                    strategy_id="trend-following-v1",
                    captured_snapshot_id="approved-trend",
                ),
                BlueprintSleeveBinding(
                    sleeve_id="vol-target-v1",
                    strategy_id="vol-target-v1",
                    captured_snapshot_id="approved-vol",
                ),
            ),
            status="active",
            approved_at_utc=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
            approved_by="operator",
            source_blueprint_path=blueprint_path,
        )

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord:
        return self._active_activation

    def supersede_active_blueprint(
        self,
        *,
        new_activation: BlueprintActivationRecord,
        now: datetime,
    ) -> BlueprintActivationRecord:
        previous = self._active_activation
        self._active_activation = new_activation
        return BlueprintActivationRecord(
            activation_id=previous.activation_id,
            blueprint_id=previous.blueprint_id,
            sleeve_activation_bindings=previous.sleeve_activation_bindings,
            status="superseded",
            approved_at_utc=previous.approved_at_utc,
            approved_by=previous.approved_by,
            source_blueprint_path=previous.source_blueprint_path,
            superseded_at_utc=now,
            supersedes_activation_id=new_activation.activation_id,
        )

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan:
        plan = super().plan_for_service(
            symbols=symbols,
            portfolio_state=portfolio_state,
            default_quantity=default_quantity,
        )
        return RuntimePortfolioPlan(
            plan_id=plan.plan_id,
            generated_at_utc=plan.generated_at_utc,
            strategy_id=plan.strategy_id,
            universe_snapshot_id=plan.universe_snapshot_id,
            benchmark_symbol=plan.benchmark_symbol,
            crash_overlay_active=plan.crash_overlay_active,
            symbols_considered=plan.symbols_considered,
            current_weights=plan.current_weights,
            target_weights=plan.target_weights,
            trade_intents=plan.trade_intents,
            planned_trades=plan.planned_trades,
            market_snapshots=plan.market_snapshots,
            per_sleeve_target_weights=plan.per_sleeve_target_weights,
            sleeve_failure_reasons=(("vol-target-v1", self._failure_reason),),
        )


def test_paper_trading_service_runs_multi_symbol_cycles_and_persists_summary(
    tmp_path,
) -> None:
    loop_controller = FakeLoopController()
    sleep_calls: list[int] = []
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    result = service.run(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=2,
    )

    assert loop_controller.calls == [
        ("SPY", Decimal("1")),
        ("QQQ", Decimal("1")),
        ("SPY", Decimal("1")),
        ("QQQ", Decimal("1")),
    ]
    assert sleep_calls == [300]
    assert result.cycles_completed == 2
    assert result.last_cycle.cycle_status == "executed"
    assert [entry.symbol for entry in result.last_cycle.symbol_results] == [
        "SPY",
        "QQQ",
    ]
    assert result.last_cycle.blocked_trade_count == 1
    assert result.last_cycle.open_position_symbols == ("SPY",)
    assert (tmp_path / "service_cycles").exists()


def test_paper_trading_service_records_closed_market_cycles_without_trading(
    tmp_path,
) -> None:
    loop_controller = FakeLoopController()
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: False,
        now_provider=lambda: datetime(2026, 4, 17, 22, 30, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
    )

    result = service.run(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert loop_controller.calls == []
    assert result.cycles_completed == 1
    assert result.last_cycle.cycle_status == "market_closed"
    assert result.last_cycle.symbol_results == ()


def test_paper_trading_service_marks_cycle_recovery_required_on_divergence(
    tmp_path,
) -> None:
    loop_controller = FakeRecoveryLoopController()
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
    )

    result = service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert result.last_cycle.cycle_status == "recovery_required"
    assert result.last_cycle.reconciliation_failure_count == 1


def test_paper_trading_service_marks_cycle_overrun_when_budget_is_exceeded(
    tmp_path,
) -> None:
    loop_controller = FakeLoopController()
    monotonic_values = iter((0.0, 35.0))
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        monotonic_fn=lambda: next(monotonic_values),
        cycle_budget_seconds=30,
    )

    result = service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert result.last_cycle.cycle_status == "cycle_overrun"


def test_paper_trading_service_marks_broker_unavailable_when_state_is_stale(
    tmp_path,
) -> None:
    loop_controller = FakeLoopController()
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakeStalePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        broker_staleness_seconds=60,
    )

    result = service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert loop_controller.calls == []
    assert result.last_cycle.cycle_status == "broker_unavailable"


def test_paper_trading_service_marks_broker_unavailable_after_failed_reads(
    tmp_path,
) -> None:
    loop_controller = FakeLoopController()
    portfolio = FakeFailingPortfolio()
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=portfolio,
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        broker_failure_threshold=2,
    )

    result = service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert portfolio.calls == 2
    assert loop_controller.calls == []
    assert result.last_cycle.cycle_status == "broker_unavailable"


def test_paper_trading_service_marks_data_unavailable_on_stale_market_veto(
    tmp_path,
) -> None:
    loop_controller = FakeStaleDataLoopController()
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
    )

    result = service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert result.last_cycle.cycle_status == "data_unavailable"
    assert result.last_cycle.symbol_results == (
        ServiceSymbolResult(
            symbol="SPY",
            terminal_state="blocked_trade",
            reason_code="baseline_long_entry",
            recovered=False,
            control_type="stale_market_data",
        ),
    )


def test_paper_trading_service_honors_kill_flag_at_cycle_boundary(tmp_path) -> None:
    loop_controller = FakeLoopController()
    control_store = OperatorControlStore(tmp_path / "data" / "control")
    control_store.request_kill(now=datetime(2026, 4, 17, 18, 0, tzinfo=UTC))
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        operator_control_store=control_store,
    )

    result = service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=2,
    )

    assert loop_controller.calls == []
    assert result.cycles_completed == 1
    assert result.last_cycle.cycle_status == "kill_requested"


def test_paper_trading_service_fails_closed_when_planner_errors(
    tmp_path,
) -> None:
    loop_controller = FakeLoopController()
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        portfolio_planner=FakeFailingPortfolioPlanner(),
    )

    result = service.run(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert loop_controller.calls == []
    assert loop_controller.intent_calls == []
    assert result.last_cycle.cycle_status == "recovery_required"
    assert result.last_cycle.symbol_results == ()


def test_paper_trading_service_executes_runtime_portfolio_plan_when_available(
    tmp_path,
) -> None:
    loop_controller = FakeLoopController()
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        portfolio_planner=FakePortfolioPlanner(),
    )

    result = service.run(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert loop_controller.calls == []
    assert loop_controller.intent_calls == [
        ("SPY", "reduce", Decimal("20")),
        ("QQQ", "buy", Decimal("20")),
    ]
    assert result.last_cycle.cycle_status == "executed"


def test_paper_trading_service_writes_decomposition_sidecar_when_present(
    tmp_path,
) -> None:
    loop_controller = FakeLoopController()
    store = FilesystemArtifactStore(tmp_path)
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=store,
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        portfolio_planner=FakeBlueprintPortfolioPlanner(),
    )

    result = service.run(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    plans = store.list_runtime_portfolio_plans()
    decompositions = store.list_sleeve_decomposition_records(trading_day="2026-04-17")

    assert len(plans) == 1
    assert len(decompositions) == 1
    assert decompositions[0].cycle_id == result.last_cycle.cycle_id
    assert {
        entry.sleeve_id for entry in decompositions[0].per_sleeve_target_weights
    } == {
        "trend-following-v1",
        "vol-target-v1",
    }


def test_paper_trading_service_narrows_blueprint_after_three_structural_failures(
    tmp_path,
) -> None:
    blueprint_path = tmp_path / "bp-runtime.json"
    blueprint_path.write_text(
        (
            "{\n"
            '  "blueprint_id": "bp-runtime",\n'
            '  "sleeve_budgets": [\n'
            "    {\n"
            '      "sleeve_id": "trend-following-v1",\n'
            '      "budget_fraction_of_equity": "0.5",\n'
            '      "max_correlation_with_other_sleeves": "0.85"\n'
            "    },\n"
            "    {\n"
            '      "sleeve_id": "vol-target-v1",\n'
            '      "budget_fraction_of_equity": "0.5",\n'
            '      "max_correlation_with_other_sleeves": "0.85"\n'
            "    }\n"
            "  ]\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    loop_controller = FakeLoopController()
    store = FilesystemArtifactStore(tmp_path)
    planner = FakeStructuralFailureBlueprintPlanner(
        blueprint_path=blueprint_path,
        failure_reason="halt_by_operator",
    )
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=store,
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        portfolio_planner=planner,
    )

    result = service.run(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=3,
    )

    assert result.last_cycle.cycle_status == "executed"
    active = planner.get_active_blueprint_activation()
    assert active is not None
    assert {binding.sleeve_id for binding in active.sleeve_activation_bindings} == {
        "trend-following-v1"
    }
    alerts = store.list_artifact_payloads("operator_alerts")
    risk_events = store.list_artifact_payloads("risk_events")
    assert any(payload.get("category") == "blueprint_narrowed" for payload in alerts)
    assert any(
        payload.get("control_type") == "blueprint_narrowed" for payload in risk_events
    )


def test_paper_trading_service_fails_closed_when_planner_returns_none(
    tmp_path,
) -> None:
    loop_controller = FakeLoopController()
    service = PaperTradingService(
        loop_controller=loop_controller,
        portfolio=FakePortfolio(),
        artifacts=FilesystemArtifactStore(tmp_path),
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
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    assert loop_controller.calls == []
    assert loop_controller.intent_calls == []
    assert result.last_cycle.cycle_status == "recovery_required"


def test_build_default_trading_service_uses_mode_aware_helpers(
    monkeypatch, tmp_path
) -> None:
    helper_calls: dict[str, object] = {}

    def fake_resolve_broker_mode(config, *, explicit_mode=None):
        del config
        helper_calls["explicit_mode"] = explicit_mode
        return BrokerModeDecision(
            requested_mode="live",
            effective_mode="live",
            live_requested=True,
            live_allowed=True,
            disable_reasons=(),
        )

    def fake_build_trading_client(config, decision):
        del config
        helper_calls["client_mode"] = decision.requested_mode
        return object()

    def fake_build_market_data_gateway(config, *, broker_mode=None):
        del config
        helper_calls["market_data_mode"] = broker_mode
        return object()

    class FakeRuntimeRegistry:
        def can_resolve(self, strategy_id: str) -> bool:
            del strategy_id
            return True

    activation_kwargs: list[dict[str, object]] = []

    monkeypatch.setattr(service_module, "resolve_broker_mode", fake_resolve_broker_mode)
    monkeypatch.setattr(
        service_module,
        "build_trading_client_for_mode",
        fake_build_trading_client,
    )
    monkeypatch.setattr(
        service_module,
        "build_market_data_gateway_for_mode",
        fake_build_market_data_gateway,
    )
    monkeypatch.setattr(
        service_module,
        "build_default_trading_loop_controller",
        lambda config, *, broker_mode=None: ("loop", broker_mode),
    )
    monkeypatch.setattr(
        service_module,
        "build_default_runtime_registry",
        lambda **kwargs: FakeRuntimeRegistry(),
    )
    monkeypatch.setattr(
        service_module,
        "LocalActivationGateway",
        lambda **kwargs: activation_kwargs.append(kwargs) or object(),
    )
    monkeypatch.setattr(
        service_module,
        "RuntimePortfolioPlanner",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        service_module,
        "ActivatedRuntimePlanner",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        service_module,
        "AlpacaPortfolioGateway",
        lambda trading_client: ("portfolio", trading_client),
    )

    service = service_module.build_default_trading_service(
        TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
                "ALPACA_LIVE_API_KEY": "pk-live",
                "ALPACA_LIVE_API_SECRET": "sk-live",
                "TRADINGX_BROKER_MODE": "live",
            }
        )
    )

    assert isinstance(service, PaperTradingService)
    assert helper_calls == {
        "explicit_mode": None,
        "client_mode": "live",
        "market_data_mode": "live",
    }
    assert activation_kwargs
    assert activation_kwargs[0]["promotion_decision_provider"] is not None
    assert str(activation_kwargs[0]["required_promotion_state"]) == "paper_trading"
