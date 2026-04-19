from __future__ import annotations

import importlib
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.strategy import (
    DeterministicBaselineStrategy,
    build_mandatory_candidate_registry,
)
from tradingx.types import MarketSnapshot, PortfolioState, PositionSnapshot


def test_strategy_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.strategy")

    assert module.__doc__
    assert hasattr(module, "__all__")


def make_market_snapshot(**overrides: object) -> MarketSnapshot:
    values: dict[str, object] = {
        "symbol": "SPY",
        "last_trade_price": Decimal("101.00"),
        "bid_price": Decimal("100.90"),
        "ask_price": Decimal("101.10"),
        "average_daily_volume_30d": Decimal("1500000"),
        "timestamp": datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return MarketSnapshot(**values)


def make_portfolio_state(
    *, positions: tuple[PositionSnapshot, ...] = ()
) -> PortfolioState:
    return PortfolioState(
        as_of_utc=datetime(2026, 4, 17, 17, 0, tzinfo=UTC),
        cash=Decimal("10000.00"),
        equity=Decimal("10000.00"),
        buying_power=Decimal("20000.00"),
        positions=positions,
        open_orders=(),
    )


def test_baseline_strategy_generates_buy_intent_for_flat_portfolio() -> None:
    strategy = DeterministicBaselineStrategy(
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC)
    )

    intent = strategy.generate_trade_intent(
        market_snapshot=make_market_snapshot(),
        portfolio_state=make_portfolio_state(),
        quantity=Decimal("2"),
    )

    assert intent.candidate_id == "baseline-long-only-v1"
    assert intent.symbol == "SPY"
    assert intent.side == "buy"
    assert intent.quantity == Decimal("2")
    assert intent.reason_code == "baseline_long_entry"
    assert intent.intent_id


def test_baseline_strategy_holds_when_symbol_position_is_already_open() -> None:
    strategy = DeterministicBaselineStrategy(
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC)
    )
    portfolio_state = make_portfolio_state(
        positions=(
            PositionSnapshot(
                symbol="SPY",
                quantity=Decimal("1"),
                average_entry_price=Decimal("100.00"),
                market_value=Decimal("101.00"),
            ),
        )
    )

    intent = strategy.generate_trade_intent(
        market_snapshot=make_market_snapshot(last_trade_price=Decimal("100.50")),
        portfolio_state=portfolio_state,
        quantity=Decimal("1"),
    )

    assert intent.side == "hold"
    assert intent.quantity is None
    assert intent.reason_code == "existing_position_hold"


def test_baseline_strategy_exits_on_take_profit_threshold() -> None:
    strategy = DeterministicBaselineStrategy(
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC)
    )
    portfolio_state = make_portfolio_state(
        positions=(
            PositionSnapshot(
                symbol="SPY",
                quantity=Decimal("2"),
                average_entry_price=Decimal("100.00"),
                market_value=Decimal("202.00"),
            ),
        )
    )

    intent = strategy.generate_trade_intent(
        market_snapshot=make_market_snapshot(
            last_trade_price=Decimal("101.50"),
            bid_price=Decimal("101.45"),
            ask_price=Decimal("101.55"),
        ),
        portfolio_state=portfolio_state,
        quantity=Decimal("1"),
    )

    assert intent.side == "sell"
    assert intent.quantity == Decimal("2")
    assert intent.reason_code == "take_profit_exit"


def test_baseline_strategy_exits_on_stop_loss_threshold() -> None:
    strategy = DeterministicBaselineStrategy(
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC)
    )
    portfolio_state = make_portfolio_state(
        positions=(
            PositionSnapshot(
                symbol="SPY",
                quantity=Decimal("2"),
                average_entry_price=Decimal("100.00"),
                market_value=Decimal("196.00"),
            ),
        )
    )

    intent = strategy.generate_trade_intent(
        market_snapshot=make_market_snapshot(
            last_trade_price=Decimal("98.50"),
            bid_price=Decimal("98.45"),
            ask_price=Decimal("98.55"),
        ),
        portfolio_state=portfolio_state,
        quantity=Decimal("1"),
    )

    assert intent.side == "sell"
    assert intent.quantity == Decimal("2")
    assert intent.reason_code == "stop_loss_exit"


def test_mandatory_candidate_registry_contains_required_families() -> None:
    candidates = build_mandatory_candidate_registry(("SPY", "QQQ"))

    assert [candidate.family for candidate in candidates] == [
        "trend_following",
        "vol_target",
        "mean_reversion",
    ]
    assert all(candidate.benchmark_symbol == "SPY" for candidate in candidates)
    assert all(candidate.universe == ("SPY", "QQQ") for candidate in candidates)


def test_mandatory_candidate_registry_uses_canonical_parameters() -> None:
    candidates = {
        candidate.family: candidate
        for candidate in build_mandatory_candidate_registry(("SPY",))
    }

    assert candidates["trend_following"].parameter_set == {
        "lookback_days": 252,
        "sma_window_days": 200,
        "skip_recent_days": 1,
        "signal": "long_only",
    }
    assert candidates["vol_target"].parameter_set == {
        "target_volatility": Decimal("0.12"),
        "realized_vol_window_days": 20,
        "max_gross_leverage": Decimal("1.0"),
    }
    assert candidates["mean_reversion"].parameter_set == {
        "beta_window_days": 60,
        "residual_sum_days": 5,
        "zscore_window_days": 60,
        "zscore_threshold": Decimal("2.0"),
    }
