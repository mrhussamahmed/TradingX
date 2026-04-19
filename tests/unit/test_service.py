from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from prometheus_client import CollectorRegistry

from tradingx.monitoring import StageMetrics
from tradingx.persistence import FilesystemArtifactStore
from tradingx.service import PaperTradingService
from tradingx.types import (
    PortfolioState,
    PositionSnapshot,
    ReconciliationSnapshot,
    RiskControlEvent,
    TradeIntent,
    TradingLoopResult,
)


class FakeLoopController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Decimal]] = []

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
