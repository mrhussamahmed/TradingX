from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.opportunity import OpportunitySelector
from tradingx.types import (
    ApprovedWeightSnapshot,
    HistoricalWarmupRecord,
    MarketSnapshot,
    PortfolioState,
    StrategyActivationRecord,
)


def _snapshot(
    symbol: str,
    *,
    last_trade_price: str,
    bid_price: str,
    ask_price: str,
    average_daily_volume_30d: str,
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        last_trade_price=Decimal(last_trade_price),
        bid_price=Decimal(bid_price),
        ask_price=Decimal(ask_price),
        average_daily_volume_30d=Decimal(average_daily_volume_30d),
        timestamp=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
    )


def test_opportunity_selector_ranks_and_selects_best_candidate() -> None:
    selector = OpportunitySelector()
    warmup = HistoricalWarmupRecord(
        warmup_id="warmup-1",
        generated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        benchmark_symbol="IVV",
        symbols=("SPY", "QQQ"),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY", "QQQ"),
        symbols_blocked={},
        return_summary={
            "SPY": {
                "cumulative_return": Decimal("0.06"),
                "mean_return": Decimal("0.002"),
                "volatility": Decimal("0.01"),
            },
            "QQQ": {
                "cumulative_return": Decimal("0.04"),
                "mean_return": Decimal("0.0015"),
                "volatility": Decimal("0.015"),
            },
            "IVV": {
                "cumulative_return": Decimal("0.03"),
                "mean_return": Decimal("0.001"),
                "volatility": Decimal("0.012"),
            },
        },
    )
    activation = StrategyActivationRecord(
        activation_id="activation-1",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY", "QQQ"),
        deploy_threshold=Decimal("0.50"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        notes="Baseline activation.",
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-1",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 45, tzinfo=UTC),
        minimum_supporting_trades=10,
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
    portfolio = PortfolioState(
        as_of_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        buying_power=Decimal("200000"),
        positions=(),
        open_orders=(),
    )

    selection = selector.select(
        symbols=("SPY", "QQQ"),
        portfolio_state=portfolio,
        market_snapshots={
            "SPY": _snapshot(
                "SPY",
                last_trade_price="505",
                bid_price="504.95",
                ask_price="505.05",
                average_daily_volume_30d="1500000",
            ),
            "QQQ": _snapshot(
                "QQQ",
                last_trade_price="430",
                bid_price="429.80",
                ask_price="430.20",
                average_daily_volume_30d="1900000",
            ),
        },
        warmup=warmup,
        activation=activation,
        model_snapshot=snapshot,
    )

    assert selection.decision == "selected"
    assert selection.selected_symbol == "SPY"
    assert selection.ranked_opportunities[0].symbol == "SPY"
    assert selection.ranked_opportunities[0].final_score > Decimal("0.50")


def test_opportunity_selector_returns_no_trade_when_threshold_is_not_met() -> None:
    selector = OpportunitySelector()
    warmup = HistoricalWarmupRecord(
        warmup_id="warmup-2",
        generated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        benchmark_symbol="IVV",
        symbols=("SPY",),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY",),
        symbols_blocked={},
        return_summary={
            "SPY": {
                "cumulative_return": Decimal("0.001"),
                "mean_return": Decimal("0.0001"),
                "volatility": Decimal("0.02"),
            },
            "IVV": {
                "cumulative_return": Decimal("-0.01"),
                "mean_return": Decimal("-0.001"),
                "volatility": Decimal("0.02"),
            },
        },
    )
    activation = StrategyActivationRecord(
        activation_id="activation-2",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY",),
        deploy_threshold=Decimal("2.00"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        notes="Strict threshold.",
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-2",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 45, tzinfo=UTC),
        minimum_supporting_trades=10,
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
    portfolio = PortfolioState(
        as_of_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        buying_power=Decimal("200000"),
        positions=(),
        open_orders=(),
    )

    selection = selector.select(
        symbols=("SPY",),
        portfolio_state=portfolio,
        market_snapshots={
            "SPY": _snapshot(
                "SPY",
                last_trade_price="505",
                bid_price="504.70",
                ask_price="505.30",
                average_daily_volume_30d="1200000",
            ),
        },
        warmup=warmup,
        activation=activation,
        model_snapshot=snapshot,
    )

    assert selection.decision == "no_trade"
    assert selection.selected_symbol == ""
    assert selection.decision_reason


def test_opportunity_selector_uses_benchmark_symbol_key_for_regime_weight() -> None:
    selector = OpportunitySelector()
    warmup = HistoricalWarmupRecord(
        warmup_id="warmup-3",
        generated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        benchmark_symbol="IVV",
        symbols=("SPY",),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY",),
        symbols_blocked={},
        return_summary={
            "SPY": {
                "cumulative_return": Decimal("0.03"),
                "mean_return": Decimal("0.001"),
                "volatility": Decimal("0.01"),
            },
            "IVV": {
                "cumulative_return": Decimal("0.05"),
                "mean_return": Decimal("0.001"),
                "volatility": Decimal("0.01"),
            },
        },
    )
    activation = StrategyActivationRecord(
        activation_id="activation-3",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY",),
        deploy_threshold=Decimal("0.10"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        notes="Baseline activation.",
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-3",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 45, tzinfo=UTC),
        minimum_supporting_trades=10,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("2.0"),
            "liquidity": Decimal("1.0"),
            "spread_penalty": Decimal("1.0"),
            "volatility_penalty": Decimal("1.0"),
            "portfolio_overlap_penalty": Decimal("1.0"),
            "execution_cost_penalty": Decimal("1.0"),
        },
    )
    portfolio = PortfolioState(
        as_of_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        buying_power=Decimal("200000"),
        positions=(),
        open_orders=(),
    )

    selection = selector.select(
        symbols=("SPY",),
        portfolio_state=portfolio,
        market_snapshots={
            "SPY": _snapshot(
                "SPY",
                last_trade_price="505",
                bid_price="504.95",
                ask_price="505.05",
                average_daily_volume_30d="1500000",
            )
        },
        warmup=warmup,
        activation=activation,
        model_snapshot=snapshot,
    )

    assert selection.ranked_opportunities[0].regime_weight == Decimal("2.10")


def _minimal_portfolio_state() -> PortfolioState:
    return PortfolioState(
        as_of_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        buying_power=Decimal("200000"),
        positions=(),
        open_orders=(),
    )


def _minimal_activation() -> StrategyActivationRecord:
    return StrategyActivationRecord(
        activation_id="activation-runtime",
        strategy_id="baseline-long-only-v1",
        strategy_version="1.0.0",
        approved_symbols=("SPY",),
        deploy_threshold=Decimal("0.10"),
        allow_fallback_weights=True,
        status="approved",
        activated_at_utc=datetime(2026, 4, 19, 11, 30, tzinfo=UTC),
        notes="Runtime planner fixture.",
    )


def _minimal_snapshot() -> ApprovedWeightSnapshot:
    return ApprovedWeightSnapshot(
        snapshot_id="snapshot-runtime",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 11, 45, tzinfo=UTC),
        minimum_supporting_trades=10,
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


def _minimal_warmup() -> HistoricalWarmupRecord:
    return HistoricalWarmupRecord(
        warmup_id="warmup-runtime",
        generated_at_utc=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        benchmark_symbol="IVV",
        symbols=("SPY",),
        window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 18, tzinfo=UTC),
        required_bar_count=30,
        symbols_ready=("SPY",),
        symbols_blocked={},
        return_summary={
            "SPY": {
                "cumulative_return": Decimal("0.03"),
                "mean_return": Decimal("0.001"),
                "volatility": Decimal("0.01"),
            },
            "IVV": {
                "cumulative_return": Decimal("0.02"),
                "mean_return": Decimal("0.001"),
                "volatility": Decimal("0.01"),
            },
        },
    )


def test_runtime_planner_short_circuits_when_hard_halt_gate_is_true() -> None:
    from tradingx.opportunity import RuntimeOpportunityPlanner

    calls: list[str] = []

    class _MarketDataGateway:
        def get_market_snapshot(self, symbol):
            calls.append(symbol)
            raise AssertionError("gateway must not be called during halt")

    planner = RuntimeOpportunityPlanner(
        market_data_gateway=_MarketDataGateway(),
        hard_halt_gate=lambda: True,
    )

    selection = planner.plan(
        symbols=("SPY",),
        portfolio_state=_minimal_portfolio_state(),
        activation=_minimal_activation(),
        model_snapshot=_minimal_snapshot(),
        warmup=_minimal_warmup(),
    )

    assert selection.decision_reason == "hard_halt_active"
    assert selection.ranked_opportunities == ()
    assert selection.selected_symbol == ""
    assert calls == []


def test_runtime_planner_passes_through_when_hard_halt_gate_is_false() -> None:
    from tradingx.opportunity import RuntimeOpportunityPlanner

    class _MarketDataGateway:
        def get_market_snapshot(self, symbol):
            return _snapshot(
                symbol,
                last_trade_price="505",
                bid_price="504.95",
                ask_price="505.05",
                average_daily_volume_30d="1500000",
            )

    planner = RuntimeOpportunityPlanner(
        market_data_gateway=_MarketDataGateway(),
        hard_halt_gate=lambda: False,
    )

    selection = planner.plan(
        symbols=("SPY",),
        portfolio_state=_minimal_portfolio_state(),
        activation=_minimal_activation(),
        model_snapshot=_minimal_snapshot(),
        warmup=_minimal_warmup(),
    )

    assert selection.decision_reason != "hard_halt_active"
