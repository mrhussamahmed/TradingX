from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from prometheus_client import CollectorRegistry

from tradingx.activation import LocalActivationGateway
from tradingx.monitoring import StageMetrics
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.runtime_portfolio import RuntimePortfolioPlan
from tradingx.service import PaperTradingService
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    MarketSnapshot,
    PortfolioState,
    PositionSnapshot,
    ReconciliationSnapshot,
    SleeveFailureReason,
    SleeveTargetWeights,
    TradeIntent,
    TradingLoopResult,
)


class _SnapshotStore:
    def load_by_strategy_id(self, strategy_id: str) -> ApprovedWeightSnapshot:
        return ApprovedWeightSnapshot(
            snapshot_id=f"snap-{strategy_id}",
            strategy_id=strategy_id,
            status="approved",
            generated_at_utc=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
            minimum_supporting_trades=20,
            weights={"SPY": Decimal("1.0")},
        )


class _LoopController:
    def execute_trade_intent(
        self,
        trade_intent: TradeIntent,
        *,
        market_snapshot: MarketSnapshot,
        universe_snapshot_id: str | None = None,
    ) -> TradingLoopResult:
        del market_snapshot, universe_snapshot_id
        return TradingLoopResult(
            terminal_state=(
                "no_action" if trade_intent.side == "hold" else "reconciled_trade"
            ),
            trade_intent=trade_intent,
            order_record=None,
            risk_event=None,
            reconciliation=ReconciliationSnapshot(
                reconciliation_id=f"reconcile-{trade_intent.symbol}",
                portfolio_state=_portfolio_state(),
                broker_state_age_seconds=0,
                differences=(),
                resolved=True,
            ),
            artifact_paths=(),
        )


class _PortfolioGateway:
    def get_portfolio_state(self) -> PortfolioState:
        return _portfolio_state()


class _FailingBlueprintPlanner:
    def __init__(self, *, activation_gateway: LocalActivationGateway) -> None:
        self._activation_gateway = activation_gateway

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        return self._activation_gateway.get_active_blueprint_activation()

    def supersede_active_blueprint(
        self,
        *,
        new_activation: BlueprintActivationRecord,
        now: datetime,
    ) -> BlueprintActivationRecord:
        return self._activation_gateway.supersede_active_blueprint(
            new_activation=new_activation,
            now=now,
        )

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan:
        del symbols, portfolio_state, default_quantity
        timestamp = datetime(2026, 4, 22, 14, 0, tzinfo=UTC)
        return RuntimePortfolioPlan(
            plan_id="plan-1",
            generated_at_utc=timestamp,
            strategy_id="bp-default-v1",
            universe_snapshot_id="universe-spy",
            benchmark_symbol="SPY",
            crash_overlay_active=False,
            symbols_considered=("SPY",),
            current_weights={"SPY": Decimal("0.5")},
            target_weights={"SPY": Decimal("0.5")},
            trade_intents=(
                TradeIntent(
                    intent_id="intent-spy",
                    candidate_id="bp-default-v1",
                    symbol="SPY",
                    side="hold",
                    quantity=None,
                    reason_code="target_weight_hold",
                    generated_at_utc=timestamp,
                    sleeve_attributions=(
                        ("trend-following-v1", Decimal("0.5")),
                        ("vol-target-v1", Decimal("0.5")),
                    ),
                ),
            ),
            planned_trades=(),
            market_snapshots={},
            per_sleeve_target_weights=(
                SleeveTargetWeights(
                    sleeve_id="trend-following-v1",
                    target_weights_by_symbol=(("SPY", Decimal("0.25")),),
                ),
                SleeveTargetWeights(
                    sleeve_id="vol-target-v1",
                    target_weights_by_symbol=(("SPY", Decimal("0.25")),),
                ),
            ),
            sleeve_failure_reasons=(
                ("vol-target-v1", SleeveFailureReason.HALT_BY_OPERATOR),
            ),
        )


def _portfolio_state() -> PortfolioState:
    timestamp = datetime(2026, 4, 22, 14, 0, tzinfo=UTC)
    return PortfolioState(
        as_of_utc=timestamp,
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        buying_power=Decimal("200000"),
        positions=(
            PositionSnapshot(
                symbol="SPY",
                quantity=Decimal("1"),
                average_entry_price=Decimal("500"),
                market_value=Decimal("500"),
            ),
        ),
        open_orders=(),
    )


def _blueprint() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="bp-default-v1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )


def _write_blueprint(path: Path) -> None:
    path.write_text(
        (
            "{\n"
            '  "blueprint_id": "bp-default-v1",\n'
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


def test_operator_halt_narrows_blueprint_after_three_cycles(tmp_path) -> None:
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    activation_gateway = LocalActivationGateway(
        store=operator_store,
        snapshot_store=_SnapshotStore(),
        now_provider=lambda: datetime(2026, 4, 22, 15, 0, tzinfo=UTC),
        strategy_id_validator=lambda _: True,
    )
    blueprint_path = tmp_path / "bp-default.json"
    _write_blueprint(blueprint_path)
    original_blueprint = _blueprint()
    activation_gateway.load_or_activate_blueprint(
        blueprint=original_blueprint,
        operator_identifier="operator:test",
        source_blueprint_path=blueprint_path,
    )
    service = PaperTradingService(
        loop_controller=_LoopController(),
        portfolio=_PortfolioGateway(),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        portfolio_planner=_FailingBlueprintPlanner(
            activation_gateway=activation_gateway
        ),
    )

    result = service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=3,
    )

    assert result.last_cycle.cycle_status == "executed"
    active = activation_gateway.get_active_blueprint_activation()
    assert active is not None
    assert {binding.sleeve_id for binding in active.sleeve_activation_bindings} == {
        "trend-following-v1"
    }
    records = operator_store.list_blueprint_activation_records()
    superseded = tuple(record for record in records if record.status == "superseded")
    assert len(superseded) == 1
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    assert any(
        payload.get("control_type") == "blueprint_narrowed"
        for payload in paper_store.list_artifact_payloads("risk_events")
    )
    assert any(
        payload.get("category") == "blueprint_narrowed"
        for payload in paper_store.list_artifact_payloads("operator_alerts")
    )


def test_rollback_reactivates_original_blueprint_after_narrowing(tmp_path) -> None:
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    activation_gateway = LocalActivationGateway(
        store=operator_store,
        snapshot_store=_SnapshotStore(),
        now_provider=lambda: datetime(2026, 4, 22, 15, 0, tzinfo=UTC),
        strategy_id_validator=lambda _: True,
    )
    blueprint_path = tmp_path / "bp-default.json"
    _write_blueprint(blueprint_path)
    original_blueprint = _blueprint()
    activation_gateway.load_or_activate_blueprint(
        blueprint=original_blueprint,
        operator_identifier="operator:test",
        source_blueprint_path=blueprint_path,
    )
    service = PaperTradingService(
        loop_controller=_LoopController(),
        portfolio=_PortfolioGateway(),
        artifacts=FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
        sleep_fn=lambda seconds: None,
        portfolio_planner=_FailingBlueprintPlanner(
            activation_gateway=activation_gateway
        ),
    )
    service.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=3,
    )

    activation_gateway.load_or_activate_blueprint(
        blueprint=original_blueprint,
        operator_identifier="operator:rollback",
        source_blueprint_path=blueprint_path,
    )
    active = activation_gateway.get_active_blueprint_activation()

    assert active is not None
    assert {binding.sleeve_id for binding in active.sleeve_activation_bindings} == {
        "trend-following-v1",
        "vol-target-v1",
    }
