from __future__ import annotations

import importlib
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.strategy import (
    CANONICAL_STAGE1_UNIVERSE,
    DeterministicBaselineStrategy,
    build_baseline_reference_candidate,
    build_mandatory_candidate_registry,
    build_runtime_candidate_registry,
)
from tradingx.types import (
    MarketSnapshot,
    PortfolioState,
    PositionSnapshot,
    StrategyCandidate,
)


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


def test_baseline_strategy_holds_when_spread_is_too_wide() -> None:
    strategy = DeterministicBaselineStrategy(
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC)
    )

    intent = strategy.generate_trade_intent(
        market_snapshot=make_market_snapshot(
            bid_price=Decimal("100.00"),
            ask_price=Decimal("102.50"),
        ),
        portfolio_state=make_portfolio_state(),
        quantity=Decimal("2"),
    )

    assert intent.side == "hold"
    assert intent.quantity is None
    assert intent.reason_code == "spread_too_wide"


def test_baseline_strategy_holds_when_entry_sizing_is_below_one_share() -> None:
    strategy = DeterministicBaselineStrategy(
        now_provider=lambda: datetime(2026, 4, 17, 17, 0, tzinfo=UTC)
    )

    intent = strategy.generate_trade_intent(
        market_snapshot=make_market_snapshot(),
        portfolio_state=make_portfolio_state(),
        quantity=Decimal("0"),
    )

    assert intent.side == "hold"
    assert intent.quantity is None
    assert intent.reason_code == "entry_size_below_minimum"


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


def test_mandatory_candidate_registry_excludes_baseline_reference() -> None:
    candidates = build_mandatory_candidate_registry(("SPY", "QQQ"))

    assert [candidate.candidate_id for candidate in candidates] == [
        "trend-following-v1",
        "vol-target-v1",
        "mean-reversion-v1",
    ]
    assert "baseline-long-only-v1" not in {
        candidate.candidate_id for candidate in candidates
    }


def test_runtime_candidate_registry_includes_baseline_reference() -> None:
    candidates = build_runtime_candidate_registry(("SPY", "QQQ"))

    assert [candidate.candidate_id for candidate in candidates] == [
        "baseline-long-only-v1",
        "trend-following-v1",
        "vol-target-v1",
        "mean-reversion-v1",
    ]
    baseline = candidates[0]
    assert baseline.family == "baseline_long_only"
    assert baseline.status == "reference"


def test_baseline_reference_candidate_contract() -> None:
    baseline = build_baseline_reference_candidate()

    assert baseline.candidate_id == "baseline-long-only-v1"
    assert baseline.family == "baseline_long_only"
    assert baseline.universe == ("SPY",)
    assert baseline.status == "reference"


def test_mandatory_candidate_registry_contains_required_families() -> None:
    candidates = build_mandatory_candidate_registry(("SPY", "QQQ"))
    candidates_by_family = {candidate.family: candidate for candidate in candidates}

    assert [candidate.family for candidate in candidates] == [
        "trend_following",
        "vol_target",
        "mean_reversion",
    ]
    assert all(candidate.benchmark_symbol == "SPY" for candidate in candidates)
    assert candidates_by_family["trend_following"].universe == ("SPY", "QQQ")
    assert candidates_by_family["vol_target"].universe == ("SPY", "QQQ")
    assert candidates_by_family["mean_reversion"].universe == ("QQQ",)


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
        "forecast_method": "ewma",
    }
    assert candidates["vol_target"].parameter_set == {
        "target_volatility": Decimal("0.12"),
        "realized_vol_window_days": 60,
        "max_gross_leverage": Decimal("1.0"),
        "signal": "vol_target_spy",
        "forecast_method": "garch",
    }
    assert candidates["mean_reversion"].parameter_set == {
        "beta_window_days": 60,
        "residual_sum_days": 5,
        "zscore_window_days": 60,
        "zscore_threshold": Decimal("2.0"),
        "forecast_method": "garch",
    }


def test_strategy_candidate_accepts_sleeve_class_path() -> None:
    candidate = StrategyCandidate(
        candidate_id="x-v1",
        family="x",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={"forecast_method": "ewma"},
        status="under_evaluation",
        sleeve_class_path="tradingx.sleeves.trend.TrendSleeve",
    )

    assert candidate.sleeve_class_path == "tradingx.sleeves.trend.TrendSleeve"


def test_strategy_candidate_sleeve_class_path_defaults_to_none() -> None:
    candidate = StrategyCandidate(
        candidate_id="x-v1",
        family="x",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="under_evaluation",
    )

    assert candidate.sleeve_class_path is None


def test_runtime_registry_sets_sleeve_class_path_for_all_blueprint_strategies() -> None:
    candidates = build_runtime_candidate_registry(("SPY", "QQQ"))
    by_id = {candidate.candidate_id: candidate for candidate in candidates}

    assert by_id["baseline-long-only-v1"].sleeve_class_path == (
        "tradingx.sleeves.baseline_long_only.BaselineLongOnlySleeve"
    )
    assert by_id["trend-following-v1"].sleeve_class_path == (
        "tradingx.sleeves.trend.TrendSleeve"
    )
    assert by_id["vol-target-v1"].sleeve_class_path == (
        "tradingx.sleeves.vol_managed_beta.VolManagedBetaSleeve"
    )
    assert by_id["mean-reversion-v1"].sleeve_class_path == (
        "tradingx.sleeves.mean_reversion.MeanReversionSleeve"
    )


def test_candidate_registries_default_to_canonical_stage1_universe() -> None:
    mandatory = {
        candidate.family: candidate for candidate in build_mandatory_candidate_registry()
    }
    runtime = {
        candidate.family: candidate for candidate in build_runtime_candidate_registry()
    }

    assert runtime["baseline_long_only"].universe == ("SPY",)
    assert mandatory["trend_following"].universe == CANONICAL_STAGE1_UNIVERSE
    assert mandatory["vol_target"].universe == CANONICAL_STAGE1_UNIVERSE
    assert mandatory["mean_reversion"].universe == tuple(
        symbol for symbol in CANONICAL_STAGE1_UNIVERSE if symbol != "SPY"
    )
