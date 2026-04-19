from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.config import TradingConfig
from tradingx.runtime_host import LocalRuntimeHostManager
from tradingx.types import (
    ApprovedWeightSnapshot,
    HistoricalWarmupRecord,
    OpportunityScore,
    OpportunitySelectionRecord,
    PortfolioState,
    ReconciliationSnapshot,
    StrategyActivationRecord,
)


class FakeServiceManager:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Decimal, int, int | None]] = []

    def start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
    ):
        from tradingx.types import WebActionResult

        self.calls.append((symbols, quantity, interval_seconds, max_cycles))
        return WebActionResult(
            action_id="action-start",
            action_type="paper_service_start",
            status="accepted",
            message="Service started.",
            evidence_refs=(),
        )

    def stop(self):
        from tradingx.types import WebActionResult

        return WebActionResult(
            action_id="action-stop",
            action_type="paper_service_stop",
            status="accepted",
            message="Stop requested.",
            evidence_refs=(),
        )


class FakeBlockedServiceManager(FakeServiceManager):
    def start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
    ):
        from tradingx.types import WebActionResult

        self.calls.append((symbols, quantity, interval_seconds, max_cycles))
        return WebActionResult(
            action_id="action-start-blocked",
            action_type="paper_service_start",
            status="blocked",
            message="Paper service is already running.",
            evidence_refs=(),
        )


class FakeWarmupService:
    def __init__(self, warmup: HistoricalWarmupRecord) -> None:
        self._warmup = warmup

    def build_warmup(
        self,
        *,
        symbols: tuple[str, ...],
        benchmark_symbol: str,
        warmup_days: int,
        required_bar_count: int,
    ) -> HistoricalWarmupRecord:
        return self._warmup


class FakePortfolioGateway:
    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            buying_power=Decimal("200000"),
            positions=(),
            open_orders=(),
        )


class FakeActivationGateway:
    def __init__(
        self,
        activation: StrategyActivationRecord,
        snapshot: ApprovedWeightSnapshot,
    ) -> None:
        self._activation = activation
        self._snapshot = snapshot

    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ApprovedWeightSnapshot]:
        return self._activation, self._snapshot

    def get_latest_activation(self) -> StrategyActivationRecord | None:
        return self._activation

    def get_latest_snapshot(self, *, strategy_id: str) -> ApprovedWeightSnapshot | None:
        del strategy_id
        return self._snapshot


class FakeReconciliationGateway:
    def __init__(self, snapshots: list[ReconciliationSnapshot]) -> None:
        self._snapshots = snapshots
        self.calls = 0

    def reconcile(self) -> ReconciliationSnapshot:
        self.calls += 1
        if not self._snapshots:
            raise AssertionError("No reconciliation snapshot available.")
        return self._snapshots.pop(0)


class FakeOpportunityPlanner:
    def plan(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        activation: StrategyActivationRecord,
        model_snapshot: ApprovedWeightSnapshot,
        warmup: HistoricalWarmupRecord,
    ) -> OpportunitySelectionRecord:
        return OpportunitySelectionRecord(
            selection_id="selection-1",
            generated_at_utc=datetime(2026, 4, 19, 12, 1, tzinfo=UTC),
            strategy_id=activation.strategy_id,
            model_snapshot_id=model_snapshot.snapshot_id,
            symbols_considered=symbols,
            ranked_opportunities=(
                OpportunityScore(
                    symbol="SPY",
                    base_signal=Decimal("1.0"),
                    regime_weight=Decimal("1.0"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.0"),
                    spread_penalty=Decimal("0.1"),
                    volatility_penalty=Decimal("0.1"),
                    portfolio_overlap_penalty=Decimal("0.0"),
                    execution_cost_penalty=Decimal("0.0"),
                    final_score=Decimal("0.8"),
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="SPY",
            decision="selected",
            decision_reason="Top-ranked eligible opportunity.",
        )


def _wait_for(predicate, *, timeout_seconds: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Condition did not become true within the timeout.")


def test_runtime_host_bootstraps_to_trading_ready_and_starts_service(tmp_path) -> None:
    activation = StrategyActivationRecord(
        activation_id="activation-1",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY", "QQQ"),
        deploy_threshold=Decimal("0.5"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        notes="Baseline activation.",
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-1",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 15, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("1.0"),
            "liquidity": Decimal("1.0"),
            "spread_penalty": Decimal("1.0"),
            "volatility_penalty": Decimal("1.0"),
            "portfolio_overlap_penalty": Decimal("1.0"),
            "execution_cost_penalty": Decimal("1.0"),
        },
    )
    warmup = HistoricalWarmupRecord(
        warmup_id="warmup-1",
        generated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        benchmark_symbol="SPY",
        symbols=("SPY", "QQQ"),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY", "QQQ"),
        symbols_blocked={},
        return_summary={"benchmark": {"cumulative_return": Decimal("0.02")}},
    )
    service_manager = FakeServiceManager()
    manager = LocalRuntimeHostManager(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        operator_store_root=tmp_path / "artifacts" / "operator_platform",
        service_manager=service_manager,
        warmup_service=FakeWarmupService(warmup),
        activation_gateway=FakeActivationGateway(activation, snapshot),
        opportunity_planner=FakeOpportunityPlanner(),
        portfolio_gateway=FakePortfolioGateway(),
    )

    result = manager.start(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    _wait_for(lambda: manager.get_state().status == "trading_ready")
    state = manager.get_state()

    assert result.status == "accepted"
    assert state.active_strategy_id == "baseline-long-only-v1"
    assert state.active_model_snapshot_id == "snapshot-1"
    assert service_manager.calls == [(("SPY", "QQQ"), Decimal("1"), 300, 1)]
    assert (tmp_path / "artifacts" / "operator_platform" / "runtime_host").exists()


def test_runtime_host_halts_when_warmup_is_incomplete(tmp_path) -> None:
    activation = StrategyActivationRecord(
        activation_id="activation-2",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY", "QQQ"),
        deploy_threshold=Decimal("0.5"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        notes="Baseline activation.",
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-2",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 15, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("1.0"),
            "liquidity": Decimal("1.0"),
            "spread_penalty": Decimal("1.0"),
            "volatility_penalty": Decimal("1.0"),
            "portfolio_overlap_penalty": Decimal("1.0"),
            "execution_cost_penalty": Decimal("1.0"),
        },
    )
    incomplete_warmup = HistoricalWarmupRecord(
        warmup_id="warmup-2",
        generated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        benchmark_symbol="SPY",
        symbols=("SPY", "QQQ"),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY",),
        symbols_blocked={"QQQ": "insufficient_bars"},
        return_summary={"benchmark": {"cumulative_return": Decimal("0.02")}},
    )
    service_manager = FakeServiceManager()
    manager = LocalRuntimeHostManager(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        operator_store_root=tmp_path / "artifacts" / "operator_platform",
        service_manager=service_manager,
        warmup_service=FakeWarmupService(incomplete_warmup),
        activation_gateway=FakeActivationGateway(activation, snapshot),
        opportunity_planner=FakeOpportunityPlanner(),
        portfolio_gateway=FakePortfolioGateway(),
    )

    manager.start(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    _wait_for(lambda: manager.get_state().status == "halted")
    state = manager.get_state()

    assert state.last_error == "Warmup incomplete for symbols: QQQ"
    assert service_manager.calls == []


def test_runtime_host_halts_when_service_manager_rejects_start(tmp_path) -> None:
    activation = StrategyActivationRecord(
        activation_id="activation-3",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY", "QQQ"),
        deploy_threshold=Decimal("0.5"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        notes="Baseline activation.",
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-3",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 15, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("1.0"),
            "liquidity": Decimal("1.0"),
            "spread_penalty": Decimal("1.0"),
            "volatility_penalty": Decimal("1.0"),
            "portfolio_overlap_penalty": Decimal("1.0"),
            "execution_cost_penalty": Decimal("1.0"),
        },
    )
    warmup = HistoricalWarmupRecord(
        warmup_id="warmup-3",
        generated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        benchmark_symbol="SPY",
        symbols=("SPY", "QQQ"),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY", "QQQ"),
        symbols_blocked={},
        return_summary={"SPY": {"cumulative_return": Decimal("0.02")}},
    )
    service_manager = FakeBlockedServiceManager()
    manager = LocalRuntimeHostManager(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        operator_store_root=tmp_path / "artifacts" / "operator_platform",
        service_manager=service_manager,
        warmup_service=FakeWarmupService(warmup),
        activation_gateway=FakeActivationGateway(activation, snapshot),
        opportunity_planner=FakeOpportunityPlanner(),
        portfolio_gateway=FakePortfolioGateway(),
    )

    manager.start(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    _wait_for(lambda: manager.get_state().status == "halted")
    state = manager.get_state()

    assert state.last_error == "Paper service is already running."


def test_runtime_host_enters_recovery_required_when_startup_reconciliation_fails(
    tmp_path,
) -> None:
    activation = StrategyActivationRecord(
        activation_id="activation-3",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY",),
        deploy_threshold=Decimal("0.5"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        notes="Baseline activation.",
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-3",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 15, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("1.0"),
            "liquidity": Decimal("1.0"),
            "spread_penalty": Decimal("1.0"),
            "volatility_penalty": Decimal("1.0"),
            "portfolio_overlap_penalty": Decimal("1.0"),
            "execution_cost_penalty": Decimal("1.0"),
        },
    )
    warmup = HistoricalWarmupRecord(
        warmup_id="warmup-3",
        generated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        benchmark_symbol="SPY",
        symbols=("SPY",),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY",),
        symbols_blocked={},
        return_summary={"benchmark": {"cumulative_return": Decimal("0.02")}},
    )
    reconciliation_gateway = FakeReconciliationGateway(
        [
            ReconciliationSnapshot(
                reconciliation_id="reconcile-start",
                portfolio_state=FakePortfolioGateway().get_portfolio_state(),
                broker_state_age_seconds=0,
                differences=("broker_position_unknown_to_journal",),
                resolved=False,
            )
        ]
    )
    service_manager = FakeServiceManager()
    manager = LocalRuntimeHostManager(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        operator_store_root=tmp_path / "artifacts" / "operator_platform",
        service_manager=service_manager,
        warmup_service=FakeWarmupService(warmup),
        activation_gateway=FakeActivationGateway(activation, snapshot),
        opportunity_planner=FakeOpportunityPlanner(),
        portfolio_gateway=FakePortfolioGateway(),
        reconciliation_gateway=reconciliation_gateway,
    )

    manager.start(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )

    _wait_for(lambda: manager.get_state().status == "recovery_required")
    state = manager.get_state()

    assert reconciliation_gateway.calls == 1
    assert service_manager.calls == []
    assert "broker_position_unknown_to_journal" in state.last_error


def test_runtime_host_clearance_request_reconciles_back_to_nominal(tmp_path) -> None:
    activation = StrategyActivationRecord(
        activation_id="activation-4",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY",),
        deploy_threshold=Decimal("0.5"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        notes="Baseline activation.",
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-4",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 15, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("1.0"),
            "liquidity": Decimal("1.0"),
            "spread_penalty": Decimal("1.0"),
            "volatility_penalty": Decimal("1.0"),
            "portfolio_overlap_penalty": Decimal("1.0"),
            "execution_cost_penalty": Decimal("1.0"),
        },
    )
    warmup = HistoricalWarmupRecord(
        warmup_id="warmup-4",
        generated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        benchmark_symbol="SPY",
        symbols=("SPY",),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY",),
        symbols_blocked={},
        return_summary={"benchmark": {"cumulative_return": Decimal("0.02")}},
    )
    reconciliation_gateway = FakeReconciliationGateway(
        [
            ReconciliationSnapshot(
                reconciliation_id="reconcile-start",
                portfolio_state=FakePortfolioGateway().get_portfolio_state(),
                broker_state_age_seconds=0,
                differences=("broker_position_unknown_to_journal",),
                resolved=False,
            ),
            ReconciliationSnapshot(
                reconciliation_id="reconcile-clearance",
                portfolio_state=FakePortfolioGateway().get_portfolio_state(),
                broker_state_age_seconds=0,
                differences=(),
                resolved=True,
            ),
        ]
    )
    service_manager = FakeServiceManager()
    manager = LocalRuntimeHostManager(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        operator_store_root=tmp_path / "artifacts" / "operator_platform",
        service_manager=service_manager,
        warmup_service=FakeWarmupService(warmup),
        activation_gateway=FakeActivationGateway(activation, snapshot),
        opportunity_planner=FakeOpportunityPlanner(),
        portfolio_gateway=FakePortfolioGateway(),
        reconciliation_gateway=reconciliation_gateway,
    )

    manager.start(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )
    _wait_for(lambda: manager.get_state().status == "recovery_required")

    result = manager.request_clearance()

    _wait_for(lambda: manager.get_state().status == "nominal")
    state = manager.get_state()

    assert result.status == "accepted"
    assert reconciliation_gateway.calls == 2
    assert state.last_error == ""
    assert service_manager.calls == [(("SPY",), Decimal("1"), 300, 1)]
