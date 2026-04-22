from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.drift.sleeve_ledger import (
    RESIDUAL_RESERVE_OWNER_ID,
    build_bootstrap_allocation,
    build_daily_ledger_result,
)
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    ExecutionLifecycleRecord,
    PortfolioState,
    PositionSnapshot,
)


def _active_activation(blueprint_path: Path) -> BlueprintActivationRecord:
    return BlueprintActivationRecord(
        activation_id="activation-1",
        blueprint_id="bp-test-v1",
        sleeve_activation_bindings=(
            BlueprintSleeveBinding(
                sleeve_id="trend-following-v1",
                strategy_id="trend-following-v1",
                captured_snapshot_id="snap-trend-1",
            ),
            BlueprintSleeveBinding(
                sleeve_id="vol-target-v1",
                strategy_id="vol-target-v1",
                captured_snapshot_id="snap-vol-1",
            ),
        ),
        status="active",
        approved_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
        approved_by="operator",
        source_blueprint_path=blueprint_path,
    )


def _write_blueprint(path: Path) -> None:
    path.write_text(
        "\n".join(
            (
                "blueprint_id: bp-test-v1",
                "sleeve_budgets:",
                "  - sleeve_id: trend-following-v1",
                "    budget_fraction_of_equity: 0.6",
                "    max_correlation_with_other_sleeves: 0.85",
                "  - sleeve_id: vol-target-v1",
                "    budget_fraction_of_equity: 0.4",
                "    max_correlation_with_other_sleeves: 0.85",
            )
        ),
        encoding="utf-8",
    )


def test_bootstrap_uses_exact_history_before_blueprint_fallback(tmp_path) -> None:
    runtime_store = FilesystemArtifactStore(tmp_path / "runtime")
    blueprint_path = tmp_path / "bp.yaml"
    _write_blueprint(blueprint_path)
    runtime_store.write_model_weight_snapshot(
        ApprovedWeightSnapshot(
            snapshot_id="snap-trend-1",
            strategy_id="trend-following-v1",
            status="approved",
            generated_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
            minimum_supporting_trades=5,
            weights={"signal": Decimal("1")},
        )
    )
    runtime_store.write_model_weight_snapshot(
        ApprovedWeightSnapshot(
            snapshot_id="snap-vol-1",
            strategy_id="vol-target-v1",
            status="approved",
            generated_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
            minimum_supporting_trades=5,
            weights={"signal": Decimal("1")},
        )
    )
    open_state = PortfolioState(
        as_of_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
        cash=Decimal("1000"),
        equity=Decimal("2000"),
        buying_power=Decimal("3000"),
        positions=(
            PositionSnapshot(
                symbol="SPY",
                quantity=Decimal("10"),
                average_entry_price=Decimal("100"),
                market_value=Decimal("1050"),
            ),
        ),
        open_orders=(),
    )
    history = (
        ExecutionLifecycleRecord(
            execution_id="exec-1",
            intent_id="intent-1",
            symbol="SPY",
            side="buy",
            reason_code="entry",
            reference_price=Decimal("100"),
            fill_price=Decimal("100"),
            filled_qty=Decimal("10"),
            slippage_bps=Decimal("0"),
            submitted_at_utc=datetime(2026, 4, 20, 13, 30, tzinfo=UTC),
            filled_at_utc=datetime(2026, 4, 20, 13, 31, tzinfo=UTC),
            recovered=False,
            sleeve_attributions=(("trend-following-v1", Decimal("1")),),
        ),
    )

    result = build_bootstrap_allocation(
        active_activation=_active_activation(blueprint_path),
        snapshot_store=runtime_store,
        open_portfolio_state=open_state,
        historical_execution_records=history,
        recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
    )

    allocation = result.bootstrap_record.position_allocations[0]
    assert allocation.sleeve_id == "trend-following-v1"
    assert allocation.allocation_source == "history_exact"
    assert allocation.confidence == "high"
    assert result.residual_reserve_snapshot.cash_balance == Decimal("1000")


def test_reserve_domain_sell_books_no_sleeve_realized_pnl(tmp_path) -> None:
    runtime_store = FilesystemArtifactStore(tmp_path / "runtime")
    blueprint_path = tmp_path / "bp.yaml"
    _write_blueprint(blueprint_path)
    runtime_store.write_model_weight_snapshot(
        ApprovedWeightSnapshot(
            snapshot_id="snap-trend-1",
            strategy_id="trend-following-v1",
            status="approved",
            generated_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
            minimum_supporting_trades=5,
            weights={"signal": Decimal("1")},
        )
    )
    runtime_store.write_model_weight_snapshot(
        ApprovedWeightSnapshot(
            snapshot_id="snap-vol-1",
            strategy_id="vol-target-v1",
            status="approved",
            generated_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
            minimum_supporting_trades=5,
            weights={"signal": Decimal("1")},
        )
    )
    open_state = PortfolioState(
        as_of_utc=datetime(2026, 4, 22, 13, 30, tzinfo=UTC),
        cash=Decimal("1000"),
        equity=Decimal("2000"),
        buying_power=Decimal("3000"),
        positions=(
            PositionSnapshot(
                symbol="XYZ",
                quantity=Decimal("5"),
                average_entry_price=Decimal("200"),
                market_value=Decimal("1000"),
            ),
        ),
        open_orders=(),
    )
    bootstrap = build_bootstrap_allocation(
        active_activation=_active_activation(blueprint_path),
        snapshot_store=runtime_store,
        open_portfolio_state=open_state,
        historical_execution_records=(),
        recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
    )
    reserve_execution = ExecutionLifecycleRecord(
        execution_id="exec-reserve",
        intent_id="intent-reserve",
        symbol="XYZ",
        side="sell",
        reason_code="residual_reserve_liquidation",
        reference_price=Decimal("200"),
        fill_price=Decimal("198"),
        filled_qty=Decimal("5"),
        slippage_bps=Decimal("-100"),
        submitted_at_utc=datetime(2026, 4, 22, 15, 0, tzinfo=UTC),
        filled_at_utc=datetime(2026, 4, 22, 15, 1, tzinfo=UTC),
        recovered=False,
        sleeve_attributions=((RESIDUAL_RESERVE_OWNER_ID, Decimal("1")),),
    )
    close_state = PortfolioState(
        as_of_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
        cash=Decimal("1990"),
        equity=Decimal("1990"),
        buying_power=Decimal("1990"),
        positions=(),
        open_orders=(),
    )

    result = build_daily_ledger_result(
        opening_snapshots=bootstrap.sleeve_snapshots,
        opening_reserve_snapshot=bootstrap.residual_reserve_snapshot,
        bootstrap_record=bootstrap.bootstrap_record,
        execution_records=(reserve_execution,),
        open_portfolio_state=open_state,
        close_portfolio_state=close_state,
        trading_day="2026-04-22",
        recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
        active_blueprint_activation_id="activation-1",
    )

    assert all(
        record.realized_pnl == Decimal("0") for record in result.attribution_records
    )
    assert all(
        record.ending_equity == Decimal("0") for record in result.attribution_records
    )
    assert result.residual_reserve_snapshot.positions == ()
    assert result.residual_reserve_snapshot.cash_balance == Decimal("1990")
