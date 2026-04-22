from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingx.types import (
    BootstrapPositionAllocation,
    ClosedTradeRecord,
    ExecutionLifecycleRecord,
    PortfolioState,
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
