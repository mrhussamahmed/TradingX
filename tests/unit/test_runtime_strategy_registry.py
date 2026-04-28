from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx import runtime_strategy_registry as registry_module
from tradingx.baseline_runtime_planner import BaselineLongOnlyPlanner
from tradingx.runtime_portfolio import RuntimePortfolioPlan
from tradingx.runtime_strategy_registry import (
    ActivatedRuntimePlanner,
    RuntimeStrategyRegistry,
)
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    MarketSnapshot,
    OpportunityScore,
    OpportunitySelectionRecord,
    PortfolioState,
    PositionSnapshot,
    StrategyActivationRecord,
)


class FakeMarketData:
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        prices = {
            "SPY": Decimal("100.50"),
            "QQQ": Decimal("200.00"),
            "IWM": Decimal("150.00"),
        }
        price = prices[symbol]
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=price,
            bid_price=price - Decimal("0.05"),
            ask_price=price + Decimal("0.05"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=datetime(2026, 4, 19, 13, 30, tzinfo=UTC),
        )


class FakeSelector:
    def __init__(self, *, selected_symbol: str) -> None:
        self.selected_symbol = selected_symbol
        self.calls: list[
            tuple[tuple[str, ...], PortfolioState, tuple[str, ...] | None]
        ] = []

    def select_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        decision_symbols: tuple[str, ...] | None = None,
    ) -> OpportunitySelectionRecord:
        self.calls.append((symbols, portfolio_state, decision_symbols))
        return OpportunitySelectionRecord(
            selection_id="selection-1",
            generated_at_utc=datetime(2026, 4, 19, 13, 30, tzinfo=UTC),
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="approved-baseline-long-only-v1",
            symbols_considered=symbols,
            ranked_opportunities=tuple(
                OpportunityScore(
                    symbol=symbol,
                    base_signal=Decimal("1.0"),
                    regime_weight=Decimal("1.0"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.0"),
                    spread_penalty=Decimal("0.0"),
                    volatility_penalty=Decimal("0.0"),
                    portfolio_overlap_penalty=Decimal("0.0"),
                    execution_cost_penalty=Decimal("0.0"),
                    final_score=Decimal("1.0"),
                    eligible=True,
                    ineligibility_reason="",
                )
                for symbol in symbols
            ),
            selected_symbol=self.selected_symbol,
            decision="selected",
            decision_reason="Top-ranked eligible opportunity.",
        )


class FakeActivationGateway:
    def __init__(
        self,
        *,
        strategy_id: str,
        approved_symbols: tuple[str, ...],
        blueprint_activation: BlueprintActivationRecord | None = None,
    ) -> None:
        self.strategy_id = strategy_id
        self.approved_symbols = approved_symbols
        self._blueprint_activation = blueprint_activation

    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ApprovedWeightSnapshot]:
        del symbols
        return (
            StrategyActivationRecord(
                activation_id="activation-1",
                strategy_id=self.strategy_id,
                strategy_version="1.0.0",
                approved_symbols=self.approved_symbols,
                deploy_threshold=Decimal("0.50"),
                allow_fallback_weights=True,
                status="approved",
                activated_at_utc=datetime(2026, 4, 19, 13, 0, tzinfo=UTC),
                notes="Runtime activation.",
            ),
            ApprovedWeightSnapshot(
                snapshot_id=f"approved-{self.strategy_id}",
                strategy_id=self.strategy_id,
                status="approved",
                generated_at_utc=datetime(2026, 4, 19, 13, 0, tzinfo=UTC),
                minimum_supporting_trades=5,
                weights={"signal": Decimal("1.0")},
            ),
        )

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        return self._blueprint_activation


class CapturingResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Decimal]] = []

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan | None:
        del portfolio_state
        self.calls.append((symbols, default_quantity))
        return None


class CapturingBlueprintPlanner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Decimal]] = []

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan | None:
        del portfolio_state
        self.calls.append((symbols, default_quantity))
        return None


def _portfolio_state(*, positions: tuple[PositionSnapshot, ...] = ()) -> PortfolioState:
    return PortfolioState(
        as_of_utc=datetime(2026, 4, 19, 13, 29, tzinfo=UTC),
        cash=Decimal("10000"),
        equity=Decimal("10000"),
        buying_power=Decimal("20000"),
        positions=positions,
        open_orders=(),
    )


def test_default_runtime_registry_passes_macro_cache_paths_to_single_strategy_planners(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: list[dict[str, object]] = []

    class FakeRuntimePortfolioPlanner:
        def __init__(self, **kwargs: object) -> None:
            captured.append(kwargs)

    monkeypatch.setattr(
        registry_module,
        "RuntimePortfolioPlanner",
        FakeRuntimePortfolioPlanner,
    )

    registry_module.build_default_runtime_registry(
        market_data_gateway=FakeMarketData(),
        vix_cache_path=tmp_path / "data" / "reference" / "vix_daily.csv",
        treasury_cache_path=tmp_path
        / "data"
        / "reference"
        / "treasury_yields_daily.csv",
    )

    strategy_planners = [
        kwargs for kwargs in captured if kwargs.get("strategy_id") is not None
    ]
    assert len(strategy_planners) == 3
    for kwargs in strategy_planners:
        assert kwargs["vix_cache_path"] == (
            tmp_path / "data" / "reference" / "vix_daily.csv"
        )
        assert kwargs["treasury_cache_path"] == (
            tmp_path / "data" / "reference" / "treasury_yields_daily.csv"
        )


def test_baseline_long_only_planner_builds_open_position_and_entry_intents() -> None:
    planner = BaselineLongOnlyPlanner(
        market_data=FakeMarketData(),
    )

    plan = planner.plan_for_service(
        symbols=("SPY", "QQQ"),
        portfolio_state=_portfolio_state(
            positions=(
                PositionSnapshot(
                    symbol="SPY",
                    quantity=Decimal("1"),
                    average_entry_price=Decimal("100.00"),
                    market_value=Decimal("100.50"),
                ),
            )
        ),
        default_quantity=Decimal("2"),
    )

    assert plan.strategy_id == "baseline-long-only-v1"
    assert [intent.symbol for intent in plan.trade_intents] == ["SPY", "QQQ"]
    assert [intent.side for intent in plan.trade_intents] == ["hold", "buy"]
    assert [intent.quantity for intent in plan.trade_intents] == [None, Decimal("2")]


def test_baseline_long_only_planner_uses_selector_for_entry_symbol() -> None:
    selector = FakeSelector(selected_symbol="IWM")
    planner = BaselineLongOnlyPlanner(
        market_data=FakeMarketData(),
        selector=selector,
    )

    plan = planner.plan_for_service(
        symbols=("SPY", "QQQ", "IWM"),
        portfolio_state=_portfolio_state(
            positions=(
                PositionSnapshot(
                    symbol="SPY",
                    quantity=Decimal("1"),
                    average_entry_price=Decimal("100.00"),
                    market_value=Decimal("100.50"),
                ),
            )
        ),
        default_quantity=Decimal("1"),
    )

    assert selector.calls
    assert selector.calls[0][0] == ("SPY", "QQQ", "IWM")
    assert selector.calls[0][2] == ("QQQ", "IWM")
    assert [intent.symbol for intent in plan.trade_intents] == ["SPY", "IWM"]
    assert [intent.side for intent in plan.trade_intents] == ["hold", "buy"]


def test_activated_runtime_planner_passes_activation_quantity() -> None:
    resolver = CapturingResolver()
    registry = RuntimeStrategyRegistry()
    registry.register("baseline-long-only-v1", resolver)
    planner = ActivatedRuntimePlanner(
        activation_gateway=FakeActivationGateway(
            strategy_id="baseline-long-only-v1",
            approved_symbols=("SPY", "QQQ"),
        ),
        registry=registry,
    )

    plan = planner.plan_for_service(
        symbols=("SPY",),
        portfolio_state=_portfolio_state(),
        default_quantity=Decimal("3"),
    )

    assert plan is None
    assert resolver.calls == [(("SPY", "QQQ"), Decimal("3"))]


def test_activated_runtime_planner_uses_blueprint_planner_when_active() -> None:
    resolver = CapturingResolver()
    blueprint_planner = CapturingBlueprintPlanner()
    registry = RuntimeStrategyRegistry()
    registry.register("baseline-long-only-v1", resolver)
    planner = ActivatedRuntimePlanner(
        activation_gateway=FakeActivationGateway(
            strategy_id="baseline-long-only-v1",
            approved_symbols=("SPY", "QQQ"),
            blueprint_activation=BlueprintActivationRecord(
                activation_id="bp-activation-1",
                blueprint_id="bp-runtime",
                sleeve_activation_bindings=(
                    BlueprintSleeveBinding(
                        sleeve_id="trend-following-v1",
                        strategy_id="trend-following-v1",
                        captured_snapshot_id="approved-trend",
                    ),
                ),
                status="active",
                approved_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
                approved_by="operator",
                source_blueprint_path=Path("/tmp/bp-runtime.yaml"),
            ),
        ),
        registry=registry,
        blueprint_planner=blueprint_planner,
    )

    plan = planner.plan_for_service(
        symbols=("SPY",),
        portfolio_state=_portfolio_state(),
        default_quantity=Decimal("3"),
    )

    assert plan is None
    assert resolver.calls == []
    assert blueprint_planner.calls == [(("SPY",), Decimal("3"))]
    assert planner.last_strategy_id == "bp-runtime"
