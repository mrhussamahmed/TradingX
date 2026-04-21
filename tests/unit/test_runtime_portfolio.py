from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingx.runtime_portfolio import (
    RuntimePortfolioPlanner,
    UnsupportedRuntimePortfolioPlanError,
)
from tradingx.types import (
    ApprovedWeightSnapshot,
    MarketSnapshot,
    PortfolioState,
    PositionSnapshot,
    StrategyActivationRecord,
)


class FakeActivationGateway:
    def __init__(self, *, strategy_id: str) -> None:
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

    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ApprovedWeightSnapshot]:
        del symbols
        return self._activation, self._snapshot


class FakeMarketData:
    def get_daily_bar_history(self, symbol: str, *, start_utc, end_utc):
        del symbol, start_utc, end_utc
        raise AssertionError("daily bars should be mocked at the portfolio helper seam")

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("100.00"),
            bid_price=Decimal("99.95"),
            ask_price=Decimal("100.05"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=datetime(2026, 4, 19, 13, 30, tzinfo=UTC),
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
