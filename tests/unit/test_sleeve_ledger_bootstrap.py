from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingx.drift.sleeve_ledger import build_bootstrap_allocation
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    SleeveRiskBudget,
    portfolio_blueprint_content_hash,
    portfolio_blueprint_to_payload,
)
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    BootstrapPositionAllocation,
    ClosedTradeRecord,
    ExecutionLifecycleRecord,
    PortfolioState,
    PositionSnapshot,
    ResidualPositionAllocation,
    ResidualReserveSnapshot,
    SessionOpenPortfolioStateRecord,
    SleeveAttributionGapRecord,
    SleeveBootstrapAllocationRecord,
    SleeveLedgerPosition,
    SleevePositionLedgerSnapshot,
    TradeIntent,
)


@pytest.mark.parametrize(
    "record",
    (
        BootstrapPositionAllocation(
            sleeve_id="trend",
            symbol="SPY",
            quantity=Decimal("10"),
            average_cost=Decimal("100"),
            market_value=Decimal("1020"),
            allocation_source="history_exact",
            confidence="high",
            evidence_refs=("execution-1",),
        ),
        ResidualPositionAllocation(
            symbol="QQQ",
            quantity=Decimal("5"),
            average_cost=Decimal("200"),
            market_value=Decimal("980"),
            reason="unresolved_history",
            evidence_refs=("gap-1",),
        ),
        SleeveBootstrapAllocationRecord(
            bootstrap_id="bootstrap-1",
            ledger_genesis_id="genesis-1",
            bootstrapped_from_activation_id="activation-1",
            trading_day="2026-04-22",
            recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
            position_allocations=(),
            residual_cash_balance=Decimal("1000"),
            residual_positions=(),
            notes=("bootstrap note",),
        ),
        SleeveLedgerPosition(
            sleeve_id="trend",
            symbol="SPY",
            quantity=Decimal("10"),
            average_cost=Decimal("100"),
            realized_pnl_cumulative=Decimal("15"),
        ),
        SleevePositionLedgerSnapshot(
            snapshot_id="snapshot-1",
            ledger_genesis_id="genesis-1",
            active_blueprint_activation_id="activation-1",
            trading_day="2026-04-22",
            recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
            sleeve_id="trend",
            cash_balance=Decimal("250"),
            positions=(),
            bootstrap_id="bootstrap-1",
        ),
        ResidualReserveSnapshot(
            snapshot_id="reserve-1",
            ledger_genesis_id="genesis-1",
            active_blueprint_activation_id="activation-1",
            trading_day="2026-04-22",
            recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
            cash_balance=Decimal("5000"),
            positions=(),
            bootstrap_id="bootstrap-1",
        ),
        SessionOpenPortfolioStateRecord(
            record_id="open-1",
            trading_day="2026-04-22",
            recorded_at_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
            portfolio_state=PortfolioState(
                as_of_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
                cash=Decimal("1000"),
                equity=Decimal("1000"),
                buying_power=Decimal("2000"),
                positions=(),
                open_orders=(),
            ),
        ),
        SleeveAttributionGapRecord(
            gap_id="gap-1",
            sleeve_id="trend",
            trading_day="2026-04-22",
            recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
            severity="warning",
            reason="irreconcilable_fill",
            evidence_refs=("execution-1",),
        ),
    ),
)
def test_new_ledger_records_are_frozen(record: object) -> None:
    assert dataclasses.is_dataclass(record)
    frozen_field = dataclasses.fields(record)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(record, frozen_field, "mutated")


def test_sleeve_ledger_bootstrap_allocates_baseline_activation_to_owner(
    tmp_path,
) -> None:
    runtime_store = FilesystemArtifactStore(tmp_path / "runtime")
    runtime_store.write_model_weight_snapshot(
        ApprovedWeightSnapshot(
            snapshot_id="approved-baseline-long-only-v1",
            strategy_id="baseline-long-only-v1",
            status="approved",
            generated_at_utc=datetime(2026, 5, 2, 13, 0, tzinfo=UTC),
            minimum_supporting_trades=0,
            weights={"signal": Decimal("1")},
        )
    )
    approved_blueprint = PortfolioBlueprint(
        blueprint_id="baseline-blueprint",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="baseline-long-only-v1",
                strategy_id="baseline-long-only-v1",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    activation = BlueprintActivationRecord(
        activation_id="activation-baseline",
        blueprint_id="baseline-blueprint",
        sleeve_activation_bindings=(
            BlueprintSleeveBinding(
                sleeve_id="baseline-long-only-v1",
                strategy_id="baseline-long-only-v1",
                captured_snapshot_id="approved-baseline-long-only-v1",
            ),
        ),
        status="active",
        approved_at_utc=datetime(2026, 5, 2, 13, 0, tzinfo=UTC),
        approved_by="test",
        source_blueprint_path=tmp_path / "baseline-blueprint.yaml",
        blueprint_content_hash=portfolio_blueprint_content_hash(approved_blueprint),
        blueprint_payload=portfolio_blueprint_to_payload(approved_blueprint),
    )
    portfolio = PortfolioState(
        as_of_utc=datetime(2026, 5, 2, 13, 30, tzinfo=UTC),
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        buying_power=Decimal("100000"),
        positions=(
            PositionSnapshot(
                symbol="SPY",
                quantity=Decimal("1"),
                market_value=Decimal("500"),
                average_entry_price=Decimal("500"),
            ),
        ),
        open_orders=(),
    )

    result = build_bootstrap_allocation(
        active_activation=activation,
        snapshot_store=runtime_store,
        open_portfolio_state=portfolio,
        historical_execution_records=(),
        recorded_at_utc=datetime(2026, 5, 2, 20, 0, tzinfo=UTC),
    )

    assert result.bootstrap_record.residual_positions == ()
    assert result.bootstrap_record.position_allocations[0].sleeve_id == (
        "baseline-long-only-v1"
    )


def test_trade_execution_and_closed_trade_shapes_remain_unchanged() -> None:
    assert [field.name for field in dataclasses.fields(TradeIntent)] == [
        "intent_id",
        "candidate_id",
        "symbol",
        "side",
        "quantity",
        "reason_code",
        "generated_at_utc",
        "sleeve_attributions",
    ]
    assert [field.name for field in dataclasses.fields(ExecutionLifecycleRecord)] == [
        "execution_id",
        "intent_id",
        "symbol",
        "side",
        "reason_code",
        "reference_price",
        "fill_price",
        "filled_qty",
        "slippage_bps",
        "submitted_at_utc",
        "filled_at_utc",
        "recovered",
        "bid_price",
        "ask_price",
        "average_daily_volume_30d",
        "sleeve_attributions",
    ]
    assert [field.name for field in dataclasses.fields(ClosedTradeRecord)] == [
        "trade_id",
        "symbol",
        "entry_intent_id",
        "exit_intent_id",
        "opened_at_utc",
        "closed_at_utc",
        "quantity",
        "entry_price",
        "exit_price",
        "gross_pnl",
        "return_pct",
        "outcome",
        "holding_period_seconds",
        "entry_sleeve_attributions",
        "exit_sleeve_attributions",
    ]
