from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.runtime_portfolio import RuntimePortfolioPlan, RuntimePortfolioPlanner
from tradingx.service import PaperTradingService
from tradingx.types import (
    BlueprintActivationRecord,
    MarketSnapshot,
    PortfolioState,
    SleeveDecompositionRecord,
    SleeveTargetWeights,
)


class _FakeMarketData:
    def get_daily_bar_history(self, symbol: str, *, start_utc, end_utc):
        del symbol, start_utc, end_utc
        return object()

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("100"),
            bid_price=Decimal("99"),
            ask_price=Decimal("101"),
            average_daily_volume_30d=Decimal("1000000"),
            timestamp=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
        )


class _RuntimeStateStore:
    def __init__(self, latest: SleeveDecompositionRecord | None = None) -> None:
        self.latest = latest
        self.written: list[SleeveDecompositionRecord] = []

    def latest_sleeve_decomposition_record(self) -> SleeveDecompositionRecord | None:
        return self.latest

    def write_sleeve_decomposition_record(
        self,
        record: SleeveDecompositionRecord,
    ) -> Path:
        self.written.append(record)
        return Path("/tmp/decomposition.json")


class _ArtifactStore:
    def latest_sleeve_decomposition_record(self) -> SleeveDecompositionRecord | None:
        raise AssertionError("planner should read continuity from runtime_state_store")


class _LoopController:
    pass


class _Portfolio:
    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
            cash=Decimal("1000"),
            equity=Decimal("1000"),
            buying_power=Decimal("1000"),
            positions=(),
            open_orders=(),
        )


class _Metrics:
    def record_service_cycle(self, cycle_status: str) -> None:
        del cycle_status

    def record_symbols_scanned(self, count: int) -> None:
        del count

    def record_open_positions(self, count: int) -> None:
        del count

    def record_account_snapshot(
        self,
        *,
        cash: Decimal,
        equity: Decimal,
        daily_pnl: Decimal,
    ) -> None:
        del cash, equity, daily_pnl


class _PlannerWithActivation:
    def __init__(self) -> None:
        self.activation = BlueprintActivationRecord(
            activation_id="activation-1",
            blueprint_id="bp-test",
            sleeve_activation_bindings=(),
            status="active",
            approved_at_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
            approved_by="operator",
            source_blueprint_path=Path("bp.yaml"),
        )

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord:
        return self.activation


def test_runtime_portfolio_planner_reads_continuity_from_runtime_state_store():
    latest = SleeveDecompositionRecord(
        decomposition_id="decomp-1",
        cycle_id="cycle-1",
        trading_day="2026-04-22",
        recorded_at_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
        blueprint_activation_id="activation-1",
        per_sleeve_target_weights=(
            SleeveTargetWeights(
                sleeve_id="trend",
                target_weights_by_symbol=(("SPY", Decimal("0.5")),),
            ),
        ),
    )
    planner = RuntimePortfolioPlanner(
        market_data=_FakeMarketData(),
        artifact_store=_ArtifactStore(),  # type: ignore[arg-type]
        runtime_state_store=_RuntimeStateStore(latest),
    )

    result = planner._current_weights_by_sleeve_id(  # type: ignore[attr-defined]
        blueprint=type(
            "_Blueprint",
            (),
            {"sleeve_budgets": (type("_Budget", (), {"sleeve_id": "trend"})(),)},
        )()
    )

    assert result == {"trend": {"SPY": Decimal("0.5")}}


def test_paper_trading_service_writes_decomposition_to_runtime_state_store() -> None:
    runtime_state_store = _RuntimeStateStore()
    service = PaperTradingService(
        loop_controller=_LoopController(),
        portfolio=_Portfolio(),
        artifacts=runtime_state_store,  # type: ignore[arg-type]
        runtime_state_store=runtime_state_store,  # type: ignore[arg-type]
        metrics=_Metrics(),  # type: ignore[arg-type]
        regular_hours_checker=lambda _: True,
        portfolio_planner=_PlannerWithActivation(),  # type: ignore[arg-type]
    )
    plan = RuntimePortfolioPlan(
        plan_id="plan-1",
        generated_at_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
        strategy_id="bp-test",
        universe_snapshot_id="universe-spy",
        benchmark_symbol="SPY",
        crash_overlay_active=False,
        symbols_considered=("SPY",),
        current_weights={"SPY": Decimal("0")},
        target_weights={"SPY": Decimal("1")},
        trade_intents=(),
        planned_trades=(),
        market_snapshots={},
        per_sleeve_target_weights=(
            SleeveTargetWeights(
                sleeve_id="trend",
                target_weights_by_symbol=(("SPY", Decimal("1")),),
            ),
        ),
    )

    service._write_sleeve_decomposition_record_if_available(  # type: ignore[attr-defined]
        plan=plan,
        cycle_id="cycle-1",
        started_at=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
    )

    assert len(runtime_state_store.written) == 1
    assert runtime_state_store.written[0].cycle_id == "cycle-1"
