from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingx.runtime_portfolio import RuntimePortfolioPlan, RuntimePortfolioTrade
from tradingx.types import MarketSnapshot, SleeveTargetWeights, TradeIntent


def _make_minimal_plan(
    *,
    per_sleeve_target_weights: tuple[SleeveTargetWeights, ...] = (),
) -> RuntimePortfolioPlan:
    timestamp = datetime(2026, 4, 22, 14, 0, tzinfo=UTC)
    return RuntimePortfolioPlan(
        plan_id="runtime-plan-1",
        generated_at_utc=timestamp,
        strategy_id="trend-following-v1",
        universe_snapshot_id="universe-qqq-spy",
        benchmark_symbol="SPY",
        crash_overlay_active=False,
        symbols_considered=("SPY",),
        current_weights={"SPY": Decimal("0.0")},
        target_weights={"SPY": Decimal("0.1")},
        trade_intents=(
            TradeIntent(
                intent_id="intent-1",
                candidate_id="trend-following-v1",
                symbol="SPY",
                side="buy",
                quantity=Decimal("10"),
                reason_code="target_weight_entry",
                generated_at_utc=timestamp,
            ),
        ),
        planned_trades=(
            RuntimePortfolioTrade(
                symbol="SPY",
                side="buy",
                reason_code="target_weight_entry",
                last_trade_price=Decimal("100"),
                current_weight=Decimal("0"),
                target_weight=Decimal("0.1"),
                current_quantity=Decimal("0"),
                target_quantity=Decimal("10"),
                delta_quantity=Decimal("10"),
                no_trade_band_applied=False,
            ),
        ),
        market_snapshots={
            "SPY": MarketSnapshot(
                symbol="SPY",
                last_trade_price=Decimal("100"),
                bid_price=Decimal("99.95"),
                ask_price=Decimal("100.05"),
                average_daily_volume_30d=Decimal("1000000"),
                timestamp=timestamp,
            ),
        },
        per_sleeve_target_weights=per_sleeve_target_weights,
    )


def test_sleeve_target_weights_is_frozen() -> None:
    entry = SleeveTargetWeights(
        sleeve_id="trend-following-v1",
        target_weights_by_symbol=(("SPY", Decimal("0.4")),),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.sleeve_id = "x"  # type: ignore[misc]


def test_runtime_portfolio_plan_per_sleeve_defaults_to_empty_tuple() -> None:
    plan = _make_minimal_plan()
    assert plan.per_sleeve_target_weights == ()


def test_runtime_portfolio_plan_accepts_per_sleeve_target_weights() -> None:
    plan = _make_minimal_plan(
        per_sleeve_target_weights=(
            SleeveTargetWeights(
                sleeve_id="trend-following-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.3")),),
            ),
            SleeveTargetWeights(
                sleeve_id="vol-target-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.2")),),
            ),
        ),
    )
    assert len(plan.per_sleeve_target_weights) == 2


def test_decomposition_sums_to_aggregate_within_tolerance() -> None:
    plan = _make_minimal_plan(
        per_sleeve_target_weights=(
            SleeveTargetWeights(
                sleeve_id="trend-following-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.06")),),
            ),
            SleeveTargetWeights(
                sleeve_id="vol-target-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.04")),),
            ),
        ),
    )
    aggregate = plan.target_weights["SPY"]
    decomposition_sum = sum(
        (
            dict(entry.target_weights_by_symbol).get("SPY", Decimal("0"))
            for entry in plan.per_sleeve_target_weights
        ),
        start=Decimal("0"),
    )
    assert abs(aggregate - decomposition_sum) < Decimal("1e-9")


def test_legacy_single_strategy_plan_has_empty_decomposition() -> None:
    plan = _make_minimal_plan()
    assert plan.per_sleeve_target_weights == ()
