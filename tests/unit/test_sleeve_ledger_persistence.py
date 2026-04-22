from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    ApprovedWeightSnapshot,
    BootstrapPositionAllocation,
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
)


def test_sleeve_ledger_runtime_state_roundtrips_and_evidence_categories(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    now = datetime(2026, 4, 22, 20, 0, tzinfo=UTC)

    bootstrap = SleeveBootstrapAllocationRecord(
        bootstrap_id="bootstrap-1",
        ledger_genesis_id="genesis-1",
        bootstrapped_from_activation_id="activation-1",
        trading_day="2026-04-22",
        recorded_at_utc=now,
        position_allocations=(
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
        ),
        residual_cash_balance=Decimal("500"),
        residual_positions=(
            ResidualPositionAllocation(
                symbol="QQQ",
                quantity=Decimal("2"),
                average_cost=Decimal("200"),
                market_value=Decimal("390"),
                reason="unresolved_history",
                evidence_refs=("execution-2",),
            ),
        ),
        notes=("note-1",),
    )
    ledger = SleevePositionLedgerSnapshot(
        snapshot_id="snapshot-1",
        ledger_genesis_id="genesis-1",
        active_blueprint_activation_id="activation-1",
        trading_day="2026-04-22",
        recorded_at_utc=now,
        sleeve_id="trend",
        cash_balance=Decimal("125"),
        positions=(
            SleeveLedgerPosition(
                sleeve_id="trend",
                symbol="SPY",
                quantity=Decimal("10"),
                average_cost=Decimal("100"),
                realized_pnl_cumulative=Decimal("15"),
            ),
        ),
        bootstrap_id="bootstrap-1",
    )
    reserve = ResidualReserveSnapshot(
        snapshot_id="reserve-1",
        ledger_genesis_id="genesis-1",
        active_blueprint_activation_id="activation-1",
        trading_day="2026-04-22",
        recorded_at_utc=now,
        cash_balance=Decimal("500"),
        positions=bootstrap.residual_positions,
        bootstrap_id="bootstrap-1",
    )
    session_open = SessionOpenPortfolioStateRecord(
        record_id="open-1",
        trading_day="2026-04-22",
        recorded_at_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
        portfolio_state=PortfolioState(
            as_of_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
            cash=Decimal("1000"),
            equity=Decimal("2000"),
            buying_power=Decimal("3000"),
            positions=(
                PositionSnapshot(
                    symbol="SPY",
                    quantity=Decimal("10"),
                    average_entry_price=Decimal("100"),
                    market_value=Decimal("1000"),
                ),
            ),
            open_orders=(),
        ),
    )
    gap = SleeveAttributionGapRecord(
        gap_id="gap-1",
        sleeve_id="trend",
        trading_day="2026-04-22",
        recorded_at_utc=now,
        severity="warning",
        reason="irreconcilable_fill",
        evidence_refs=("execution-1",),
    )
    snapshot = ApprovedWeightSnapshot(
        snapshot_id="snapshot-abc",
        strategy_id="trend-following-v1",
        status="approved",
        generated_at_utc=now,
        minimum_supporting_trades=5,
        weights={"signal": Decimal("1")},
    )

    execution_early = ExecutionLifecycleRecord(
        execution_id="exec-2",
        intent_id="intent-2",
        symbol="SPY",
        side="buy",
        reason_code="target_weight_entry",
        reference_price=Decimal("100"),
        fill_price=Decimal("100"),
        filled_qty=Decimal("1"),
        slippage_bps=Decimal("0"),
        submitted_at_utc=datetime(2026, 4, 22, 13, 31, tzinfo=UTC),
        filled_at_utc=datetime(2026, 4, 22, 13, 32, tzinfo=UTC),
        recovered=False,
        sleeve_attributions=(("trend", Decimal("1")),),
    )
    execution_late = ExecutionLifecycleRecord(
        execution_id="exec-1",
        intent_id="intent-1",
        symbol="QQQ",
        side="sell",
        reason_code="target_weight_exit",
        reference_price=Decimal("200"),
        fill_price=Decimal("199"),
        filled_qty=Decimal("1"),
        slippage_bps=Decimal("-50"),
        submitted_at_utc=datetime(2026, 4, 22, 14, 31, tzinfo=UTC),
        filled_at_utc=datetime(2026, 4, 22, 14, 32, tzinfo=UTC),
        recovered=True,
        sleeve_attributions=(("trend", Decimal("1")),),
    )

    store.write_sleeve_bootstrap_allocation_record(bootstrap)
    store.write_sleeve_position_ledger_snapshot(ledger)
    store.write_residual_reserve_snapshot(reserve)
    store.write_session_open_portfolio_state_record(session_open)
    store.write_sleeve_attribution_gap_record(gap)
    store.write_model_weight_snapshot(snapshot)
    store.write_execution_lifecycle_record(execution_late)
    store.write_execution_lifecycle_record(execution_early)

    assert store.latest_sleeve_bootstrap_allocation() == bootstrap
    assert store.latest_sleeve_position_ledger_snapshot(sleeve_id="trend") == ledger
    assert store.latest_residual_reserve_snapshot() == reserve
    assert (
        store.read_session_open_portfolio_state_record(trading_day="2026-04-22")
        == session_open
    )
    assert store.list_sleeve_attribution_gap_records(sleeve_id="trend") == (gap,)
    assert (
        store.load_approved_weight_snapshot_by_snapshot_id(snapshot_id="snapshot-abc")
        == snapshot
    )
    assert store.list_execution_lifecycle_records(trading_day="2026-04-22") == (
        execution_early,
        execution_late,
    )

    report = store.build_operator_evidence_report()
    counts = report["counts"]
    assert counts["sleeve_bootstrap"] == 1
    assert counts["sleeve_position_ledger"] == 1
    assert counts["residual_reserve"] == 1
    assert counts["session_open_portfolio_state"] == 1
    assert counts["sleeve_attribution_gaps"] == 1
