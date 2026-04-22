from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tradingx.runtime_portfolio import (
    RuntimePortfolioPlanner,
    UnsupportedRuntimePortfolioPlanError,
)
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    MarketSnapshot,
    PortfolioState,
    PositionSnapshot,
    SleeveFailureReason,
    SleeveTrade,
    StrategyActivationRecord,
    TrialRecord,
)


class FakeActivationGateway:
    def __init__(
        self,
        *,
        strategy_id: str,
        blueprint_activation: BlueprintActivationRecord | None = None,
    ) -> None:
        self._activation = StrategyActivationRecord(
            activation_id="activation-1",
            strategy_id=strategy_id,
            strategy_version="1.0.0",
            approved_symbols=("SPY", "QQQ"),
            deploy_threshold=Decimal("0.50"),
            allow_fallback_weights=True,
            status="approved",
            activated_at_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
            notes="Test activation.",
        )
        self._snapshot = ApprovedWeightSnapshot(
            snapshot_id=f"approved-{strategy_id}",
            strategy_id=strategy_id,
            status="approved",
            generated_at_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
            minimum_supporting_trades=5,
            weights={"signal": Decimal("1.0")},
        )
        self._blueprint_activation = blueprint_activation

    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ApprovedWeightSnapshot]:
        del symbols
        return self._activation, self._snapshot

    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        return self._blueprint_activation


class FakeMarketData:
    def get_daily_bar_history(self, symbol: str, *, start_utc, end_utc):
        del start_utc, end_utc
        index = pd.date_range("2026-04-14", periods=5, freq="B", tz="UTC")
        prices = [100.0, 101.0, 102.0, 103.0, 104.0]
        base = 100.0 if symbol != "QQQ" else 200.0
        return pd.DataFrame(
            {
                "open": [base + value - 100.0 for value in prices],
                "high": [base + value - 99.0 for value in prices],
                "low": [base + value - 101.0 for value in prices],
                "close": [base + value - 100.0 for value in prices],
                "bid": [base + value - 100.05 for value in prices],
                "ask": [base + value - 99.95 for value in prices],
                "volume": [1_000_000] * len(index),
            },
            index=index,
        )

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("100.00"),
            bid_price=Decimal("99.95"),
            ask_price=Decimal("100.05"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=datetime(2026, 4, 19, 13, 30, tzinfo=UTC),
        )


class _HaltStore:
    def __init__(self, halted_ids: set[str]) -> None:
        self._halted_ids = halted_ids

    def is_halted(self, *, sleeve_id: str) -> bool:
        return sleeve_id in self._halted_ids


class _DriftGateway:
    def __init__(self, alarmed_ids: set[str]) -> None:
        self._alarmed_ids = alarmed_ids

    def has_alarm(self, *, sleeve_id: str) -> bool:
        return sleeve_id in self._alarmed_ids


class _TrialsLedger:
    def __init__(self, records: tuple[TrialRecord, ...]) -> None:
        self._records = records

    def records_for_candidate(self, candidate_id: str) -> tuple[TrialRecord, ...]:
        return tuple(
            record for record in self._records if record.candidate_id == candidate_id
        )


class _NoopSleeve:
    def __init__(self, *, sleeve_id: str) -> None:
        self.sleeve_id = sleeve_id
        self.family = "test"
        self.allowed_instruments = ("SPY",)

    def plan_for_bar(self, context) -> tuple[SleeveTrade, ...]:
        del context
        return (
            SleeveTrade(
                sleeve_id=self.sleeve_id,
                symbol="SPY",
                side="buy",
                target_weight_of_sleeve_budget=Decimal("0.6"),
                rationale="test_signal",
                regime="risk_on",
            ),
        )


def _trial(*, candidate_id: str, sharpe: str) -> TrialRecord:
    end = datetime(2026, 4, 22, 12, 0, tzinfo=UTC)
    return TrialRecord(
        trial_id=f"trial-{candidate_id}-{sharpe}",
        candidate_id=candidate_id,
        family="trend_following",
        window_start_utc=end.replace(day=1),
        window_end_utc=end,
        observed_sharpe_net_of_costs=Decimal(sharpe),
        observed_cagr_net_of_costs=Decimal("0.05"),
        observed_max_drawdown=Decimal("0.10"),
        observed_cdar_95=Decimal("0.05"),
        annualized_cost_drag_bps=Decimal("20"),
        passed=False,
        recorded_at_utc=end,
        git_sha="test",
        config_fingerprint="test",
    )


def test_runtime_portfolio_planner_returns_none_for_baseline_strategy() -> None:
    planner = RuntimePortfolioPlanner(
        market_data=FakeMarketData(),
        activation_gateway=FakeActivationGateway(strategy_id="baseline-long-only-v1"),
        now_provider=lambda: datetime(2026, 4, 19, 13, 30, tzinfo=UTC),
    )

    plan = planner.plan_for_service(
        symbols=("SPY", "QQQ"),
        portfolio_state=PortfolioState(
            as_of_utc=datetime(2026, 4, 19, 13, 29, tzinfo=UTC),
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            buying_power=Decimal("20000"),
            positions=(),
            open_orders=(),
        ),
        default_quantity=Decimal("0"),
    )

    # Baseline execution is handled by ActivatedRuntimePlanner and the
    # BaselineLongOnlyPlanner.
    assert plan is None


def test_runtime_portfolio_planner_builds_reduce_then_buy_trade_intents(
    monkeypatch,
) -> None:
    import tradingx.runtime_portfolio as module

    def fake_target_weights(*args, **kwargs):
        del args, kwargs
        return module.CandidateRuntimeWeights(
            raw_weights={
                "SPY": Decimal("0.10"),
                "QQQ": Decimal("0.20"),
            },
            target_weights={
                "SPY": Decimal("0.10"),
                "QQQ": Decimal("0.20"),
            },
            crash_overlay_active=True,
        )

    monkeypatch.setattr(module, "build_candidate_runtime_weights", fake_target_weights)
    monkeypatch.setattr(
        module.RuntimePortfolioPlanner,
        "_load_bars",
        lambda self, *, symbols: {symbol: object() for symbol in symbols},
    )

    planner = module.RuntimePortfolioPlanner(
        market_data=FakeMarketData(),
        activation_gateway=FakeActivationGateway(strategy_id="trend-following-v1"),
        now_provider=lambda: datetime(2026, 4, 19, 13, 30, tzinfo=UTC),
    )

    plan = planner.plan_for_service(
        symbols=("SPY", "QQQ"),
        portfolio_state=PortfolioState(
            as_of_utc=datetime(2026, 4, 19, 13, 29, tzinfo=UTC),
            cash=Decimal("7000"),
            equity=Decimal("10000"),
            buying_power=Decimal("20000"),
            positions=(
                PositionSnapshot(
                    symbol="SPY",
                    quantity=Decimal("30"),
                    average_entry_price=Decimal("90.00"),
                    market_value=Decimal("3000"),
                ),
            ),
            open_orders=(),
        ),
        default_quantity=Decimal("0"),
    )

    assert plan is not None
    assert plan.strategy_id == "trend-following-v1"
    assert plan.universe_snapshot_id == "universe-qqq-spy"
    assert plan.crash_overlay_active is True
    assert [intent.symbol for intent in plan.trade_intents] == ["SPY", "QQQ"]
    assert [intent.side for intent in plan.trade_intents] == ["reduce", "buy"]
    assert [intent.quantity for intent in plan.trade_intents] == [
        Decimal("20"),
        Decimal("20"),
    ]
    assert [trade.delta_quantity for trade in plan.planned_trades] == [
        Decimal("-20"),
        Decimal("20"),
    ]
    assert plan.target_weights == {
        "SPY": Decimal("0.10"),
        "QQQ": Decimal("0.20"),
    }


def test_runtime_portfolio_planner_uses_activation_approved_symbols_for_candidate_scope(
    monkeypatch,
) -> None:
    import tradingx.runtime_portfolio as module

    loaded_symbols: list[tuple[str, ...]] = []

    def fake_target_weights(*args, **kwargs):
        del args, kwargs
        return module.CandidateRuntimeWeights(
            raw_weights={"SPY": Decimal("0.10"), "QQQ": Decimal("0.20")},
            target_weights={"SPY": Decimal("0.10"), "QQQ": Decimal("0.20")},
            crash_overlay_active=False,
        )

    monkeypatch.setattr(module, "build_candidate_runtime_weights", fake_target_weights)

    def fake_load_bars(self, *, symbols):
        loaded_symbols.append(symbols)
        return {symbol: object() for symbol in symbols}

    monkeypatch.setattr(module.RuntimePortfolioPlanner, "_load_bars", fake_load_bars)

    planner = module.RuntimePortfolioPlanner(
        market_data=FakeMarketData(),
        activation_gateway=FakeActivationGateway(strategy_id="trend-following-v1"),
        now_provider=lambda: datetime(2026, 4, 19, 13, 30, tzinfo=UTC),
    )

    plan = planner.plan_for_service(
        symbols=("SPY",),
        portfolio_state=PortfolioState(
            as_of_utc=datetime(2026, 4, 19, 13, 29, tzinfo=UTC),
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            buying_power=Decimal("20000"),
            positions=(),
            open_orders=(),
        ),
        default_quantity=Decimal("0"),
    )

    assert plan is not None
    assert plan.universe_snapshot_id == "universe-qqq-spy"
    assert loaded_symbols == [("QQQ", "SPY")]


def test_runtime_portfolio_planner_rejects_negative_target_weights(
    monkeypatch,
) -> None:
    import tradingx.runtime_portfolio as module

    def fake_target_weights(*args, **kwargs):
        del args, kwargs
        return module.CandidateRuntimeWeights(
            raw_weights={"QQQ": Decimal("-0.10")},
            target_weights={"QQQ": Decimal("-0.10")},
            crash_overlay_active=False,
        )

    monkeypatch.setattr(module, "build_candidate_runtime_weights", fake_target_weights)
    monkeypatch.setattr(
        module.RuntimePortfolioPlanner,
        "_load_bars",
        lambda self, *, symbols: {symbol: object() for symbol in symbols},
    )

    planner = module.RuntimePortfolioPlanner(
        market_data=FakeMarketData(),
        activation_gateway=FakeActivationGateway(strategy_id="trend-following-v1"),
        now_provider=lambda: datetime(2026, 4, 19, 13, 30, tzinfo=UTC),
    )

    with pytest.raises(UnsupportedRuntimePortfolioPlanError):
        planner.plan_for_service(
            symbols=("SPY", "QQQ"),
            portfolio_state=PortfolioState(
                as_of_utc=datetime(2026, 4, 19, 13, 29, tzinfo=UTC),
                cash=Decimal("10000"),
                equity=Decimal("10000"),
                buying_power=Decimal("20000"),
                positions=(),
                open_orders=(),
            ),
            default_quantity=Decimal("0"),
        )


def test_runtime_portfolio_planner_builds_blueprint_plan_with_attributions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import tradingx.runtime_portfolio as module

    blueprint_path = tmp_path / "bp-runtime.yaml"
    blueprint_path.write_text(
        "\n".join(
            (
                "blueprint_id: bp-runtime",
                "sleeve_budgets:",
                "  - sleeve_id: trend-following-v1",
                "    strategy_id: trend-following-v1",
                "    budget_fraction_of_equity: 0.5",
                "    max_correlation_with_other_sleeves: 0.85",
                "  - sleeve_id: vol-target-v1",
                "    strategy_id: vol-target-v1",
                "    budget_fraction_of_equity: 0.5",
                "    max_correlation_with_other_sleeves: 0.85",
            )
        ),
        encoding="utf-8",
    )
    blueprint_activation = BlueprintActivationRecord(
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
        approved_at_utc=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
        approved_by="operator",
        source_blueprint_path=blueprint_path,
    )

    def fake_cycle_target_weights(**kwargs):
        del kwargs
        return (
            {"QQQ": Decimal("0.20"), "SPY": Decimal("0.60")},
            (
                module.SleeveTargetWeights(
                    sleeve_id="trend-following-v1",
                    target_weights_by_symbol=(
                        ("QQQ", Decimal("0.20")),
                        ("SPY", Decimal("0.30")),
                    ),
                ),
                module.SleeveTargetWeights(
                    sleeve_id="vol-target-v1",
                    target_weights_by_symbol=(("SPY", Decimal("0.30")),),
                ),
            ),
        )

    monkeypatch.setattr(
        module,
        "build_portfolio_cycle_target_weights",
        fake_cycle_target_weights,
    )

    planner = module.RuntimePortfolioPlanner(
        market_data=FakeMarketData(),
        activation_gateway=FakeActivationGateway(
            strategy_id="baseline-long-only-v1",
            blueprint_activation=blueprint_activation,
        ),
        now_provider=lambda: datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
    )

    plan = planner.plan_for_service(
        symbols=("SPY", "QQQ"),
        portfolio_state=PortfolioState(
            as_of_utc=datetime(2026, 4, 22, 13, 29, tzinfo=UTC),
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            buying_power=Decimal("20000"),
            positions=(),
            open_orders=(),
        ),
        default_quantity=Decimal("0"),
    )

    assert plan is not None
    assert plan.strategy_id == "bp-runtime"
    assert len(plan.per_sleeve_target_weights) == 2
    spy_intent = next(intent for intent in plan.trade_intents if intent.symbol == "SPY")
    qqq_intent = next(intent for intent in plan.trade_intents if intent.symbol == "QQQ")
    assert spy_intent.sleeve_attributions == (
        ("trend-following-v1", Decimal("0.5")),
        ("vol-target-v1", Decimal("0.5")),
    )
    assert qqq_intent.sleeve_attributions == (("trend-following-v1", Decimal("1")),)


def test_runtime_portfolio_planner_surfaces_structural_failure_from_runtime_controller(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import tradingx.runtime_portfolio as module

    blueprint_path = tmp_path / "bp-runtime.yaml"
    blueprint_path.write_text(
        "\n".join(
            (
                "blueprint_id: bp-runtime",
                "sleeve_budgets:",
                "  - sleeve_id: custom-trend",
                "    strategy_id: trend-following-v1",
                "    budget_fraction_of_equity: 1.0",
                "    max_correlation_with_other_sleeves: 0.85",
            )
        ),
        encoding="utf-8",
    )
    blueprint_activation = BlueprintActivationRecord(
        activation_id="bp-activation-1",
        blueprint_id="bp-runtime",
        sleeve_activation_bindings=(
            BlueprintSleeveBinding(
                sleeve_id="custom-trend",
                strategy_id="trend-following-v1",
                captured_snapshot_id="approved-trend",
            ),
        ),
        status="active",
        approved_at_utc=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
        approved_by="operator",
        source_blueprint_path=blueprint_path,
    )

    monkeypatch.setattr(
        module,
        "build_sleeve_from_candidate",
        lambda candidate: _NoopSleeve(sleeve_id=candidate.candidate_id),
    )
    monkeypatch.setattr(
        module,
        "build_portfolio_cycle_target_weights",
        lambda **kwargs: ({"SPY": Decimal("0")}, ()),
    )

    planner = module.RuntimePortfolioPlanner(
        market_data=FakeMarketData(),
        activation_gateway=FakeActivationGateway(
            strategy_id="baseline-long-only-v1",
            blueprint_activation=blueprint_activation,
        ),
        operator_halt_store=_HaltStore({"custom-trend"}),
        drift_alarm_gateway=_DriftGateway(set()),
        trials_ledger=_TrialsLedger(()),
        now_provider=lambda: datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
    )

    plan = planner.plan_for_service(
        symbols=("SPY",),
        portfolio_state=PortfolioState(
            as_of_utc=datetime(2026, 4, 22, 13, 29, tzinfo=UTC),
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            buying_power=Decimal("20000"),
            positions=(),
            open_orders=(),
        ),
        default_quantity=Decimal("0"),
    )

    assert plan is not None
    assert plan.sleeve_failure_reasons == (
        ("custom-trend", SleeveFailureReason.HALT_BY_OPERATOR),
    )


def test_runtime_portfolio_planner_tie_breaks_equal_fractions_by_bound_strategy_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import tradingx.runtime_portfolio as module

    blueprint_path = tmp_path / "bp-runtime.yaml"
    blueprint_path.write_text(
        "\n".join(
            (
                "blueprint_id: bp-runtime",
                "sleeve_budgets:",
                "  - sleeve_id: alpha-sleeve",
                "    strategy_id: trend-following-v1",
                "    budget_fraction_of_equity: 0.5",
                "    max_correlation_with_other_sleeves: 0.85",
                "  - sleeve_id: beta-sleeve",
                "    strategy_id: vol-target-v1",
                "    budget_fraction_of_equity: 0.5",
                "    max_correlation_with_other_sleeves: 0.85",
            )
        ),
        encoding="utf-8",
    )
    blueprint_activation = BlueprintActivationRecord(
        activation_id="bp-activation-1",
        blueprint_id="bp-runtime",
        sleeve_activation_bindings=(
            BlueprintSleeveBinding(
                sleeve_id="alpha-sleeve",
                strategy_id="trend-following-v1",
                captured_snapshot_id="approved-trend",
            ),
            BlueprintSleeveBinding(
                sleeve_id="beta-sleeve",
                strategy_id="vol-target-v1",
                captured_snapshot_id="approved-vol",
            ),
        ),
        status="active",
        approved_at_utc=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
        approved_by="operator",
        source_blueprint_path=blueprint_path,
    )

    monkeypatch.setattr(
        module,
        "build_portfolio_cycle_target_weights",
        lambda **kwargs: (
            {"SPY": Decimal("0.50")},
            (
                module.SleeveTargetWeights(
                    sleeve_id="beta-sleeve",
                    target_weights_by_symbol=(("SPY", Decimal("0.25")),),
                ),
                module.SleeveTargetWeights(
                    sleeve_id="alpha-sleeve",
                    target_weights_by_symbol=(("SPY", Decimal("0.25")),),
                ),
            ),
        ),
    )

    planner = module.RuntimePortfolioPlanner(
        market_data=FakeMarketData(),
        activation_gateway=FakeActivationGateway(
            strategy_id="baseline-long-only-v1",
            blueprint_activation=blueprint_activation,
        ),
        now_provider=lambda: datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
    )

    plan = planner.plan_for_service(
        symbols=("SPY", "QQQ"),
        portfolio_state=PortfolioState(
            as_of_utc=datetime(2026, 4, 22, 13, 29, tzinfo=UTC),
            cash=Decimal("10000"),
            equity=Decimal("10000"),
            buying_power=Decimal("20000"),
            positions=(),
            open_orders=(),
        ),
        default_quantity=Decimal("0"),
    )

    assert plan is not None
    spy_intent = next(intent for intent in plan.trade_intents if intent.symbol == "SPY")
    assert spy_intent.sleeve_attributions == (
        ("alpha-sleeve", Decimal("0.5")),
        ("beta-sleeve", Decimal("0.5")),
    )
