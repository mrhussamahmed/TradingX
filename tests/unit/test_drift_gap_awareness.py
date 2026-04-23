from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.drift.blueprint import DriftThresholds
from tradingx.drift.gateway import StoreBackedAttributionRecordsReader
from tradingx.drift.live_returns_source import SleeveDailyReturnsReader
from tradingx.drift.pnl_divergence import compute_live_vs_backtest_pnl_divergence
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    ResidualPositionAllocation,
    ResidualReserveSnapshot,
    SleeveAttributionGapRecord,
    SleeveDailyAttributionRecord,
)


def _record(day: str, value: str) -> SleeveDailyAttributionRecord:
    return SleeveDailyAttributionRecord(
        attribution_id=f"trend-following-v1__{day}",
        sleeve_id="trend-following-v1",
        trading_day=day,
        recorded_at_utc=datetime.fromisoformat(f"{day}T20:00:00+00:00"),
        starting_equity=Decimal("100"),
        ending_equity=Decimal("101"),
        daily_return=Decimal(value),
        per_symbol_open_weight=(("SPY", Decimal("1")),),
        per_symbol_close_weight=(("SPY", Decimal("1")),),
    )


def _record_for_sleeve(
    *,
    sleeve_id: str,
    day: str,
    ending_equity: str,
    daily_return: str,
) -> SleeveDailyAttributionRecord:
    return SleeveDailyAttributionRecord(
        attribution_id=f"{sleeve_id}__{day}",
        sleeve_id=sleeve_id,
        trading_day=day,
        recorded_at_utc=datetime.fromisoformat(f"{day}T20:00:00+00:00"),
        starting_equity=Decimal("100"),
        ending_equity=Decimal(ending_equity),
        daily_return=Decimal(daily_return),
        per_symbol_open_weight=(("SPY", Decimal("1")),),
        per_symbol_close_weight=(("SPY", Decimal("1")),),
    )


def _reserve_snapshot(
    *,
    day: str,
    cash_balance: str,
    positions: tuple[tuple[str, str, str, str], ...] = (),
    snapshot_id: str | None = None,
    recorded_at_utc: datetime | None = None,
) -> ResidualReserveSnapshot:
    return ResidualReserveSnapshot(
        snapshot_id=snapshot_id or f"reserve-{day}",
        ledger_genesis_id="ledger-1",
        active_blueprint_activation_id="activation-1",
        trading_day=day,
        recorded_at_utc=recorded_at_utc
        or datetime.fromisoformat(f"{day}T20:00:00+00:00"),
        cash_balance=Decimal(cash_balance),
        positions=tuple(
            ResidualPositionAllocation(
                symbol=symbol,
                quantity=Decimal(quantity),
                average_cost=Decimal(average_cost),
                market_value=Decimal(market_value),
                reason="bootstrap",
                evidence_refs=(),
            )
            for symbol, quantity, average_cost, market_value in positions
        ),
        bootstrap_id="bootstrap-1",
    )


def test_store_backed_reader_exposes_gap_presence_and_live_returns_reader_hardens(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_sleeve_daily_attribution_record(_record("2026-04-20", "0.01"))
    store.write_sleeve_daily_attribution_record(_record("2026-04-21", "0.02"))
    store.write_sleeve_attribution_gap_record(
        SleeveAttributionGapRecord(
            gap_id="gap-1",
            sleeve_id="trend-following-v1",
            trading_day="2026-04-22",
            recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
            severity="warning",
            reason="irreconcilable_fill",
            evidence_refs=("exec-1",),
        )
    )
    reader = StoreBackedAttributionRecordsReader(operator_store=store)

    assert reader.has_gap_for_sleeve("trend-following-v1", window_days=60) is True
    assert (
        SleeveDailyReturnsReader(attribution_records_reader=reader).live_daily_returns(
            sleeve_id="trend-following-v1",
            window_days=60,
        )
        == ()
    )


def test_pnl_divergence_stays_pending_when_gap_flagged() -> None:
    verdict = compute_live_vs_backtest_pnl_divergence(
        sleeve_id="trend-following-v1",
        live_attribution_records=(
            _record("2026-04-20", "0.01"),
            _record("2026-04-21", "0.02"),
        ),
        backtest_returns_series=(Decimal("0.01"), Decimal("0.01")),
        thresholds=DriftThresholds(
            psi_warning=Decimal("0.2"),
            psi_critical=Decimal("0.3"),
            ks_p_value_critical=Decimal("0.01"),
            execution_drift_warning=Decimal("0.1"),
            execution_drift_critical=Decimal("0.2"),
            pnl_absolute_warning=Decimal("0.05"),
            pnl_absolute_critical=Decimal("0.10"),
            pnl_sharpe_warning=Decimal("0.2"),
            pnl_sharpe_critical=Decimal("0.4"),
        ),
        minimum_live_days=2,
        has_gap=True,
    )

    assert verdict.severity == "pending"


def test_store_backed_reader_blocks_pnl_activation_on_unresolved_reserve_positions(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_sleeve_daily_attribution_record(
        _record_for_sleeve(
            sleeve_id="trend-following-v1",
            day="2026-04-22",
            ending_equity="500",
            daily_return="0.01",
        )
    )
    store.write_sleeve_daily_attribution_record(
        _record_for_sleeve(
            sleeve_id="vol-target-v1",
            day="2026-04-22",
            ending_equity="400",
            daily_return="0.01",
        )
    )
    store.write_residual_reserve_snapshot(
        _reserve_snapshot(
            day="2026-04-22",
            cash_balance="10",
            positions=(("QQQ", "1", "100", "105"),),
        )
    )

    reader = StoreBackedAttributionRecordsReader(
        operator_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 20, 0, tzinfo=UTC),
    )

    assert "unresolved reserve positions" in str(
        reader.pnl_activation_blocker(window_days=60)
    )


def test_store_backed_reader_blocks_pnl_activation_on_reserve_cash_threshold(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_sleeve_daily_attribution_record(
        _record_for_sleeve(
            sleeve_id="trend-following-v1",
            day="2026-04-22",
            ending_equity="400",
            daily_return="0.01",
        )
    )
    store.write_sleeve_daily_attribution_record(
        _record_for_sleeve(
            sleeve_id="vol-target-v1",
            day="2026-04-22",
            ending_equity="400",
            daily_return="0.01",
        )
    )
    store.write_residual_reserve_snapshot(
        _reserve_snapshot(
            day="2026-04-22",
            cash_balance="60",
        )
    )

    reader = StoreBackedAttributionRecordsReader(
        operator_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 20, 0, tzinfo=UTC),
    )

    assert "reserve cash above activation threshold" in str(
        reader.pnl_activation_blocker(window_days=60)
    )


def test_store_backed_reader_blocks_when_equity_reconstruction_is_incomplete(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_residual_reserve_snapshot(
        _reserve_snapshot(
            day="2026-04-22",
            cash_balance="10",
        )
    )

    reader = StoreBackedAttributionRecordsReader(
        operator_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 20, 0, tzinfo=UTC),
    )

    assert "incomplete equity reconstruction" in str(
        reader.pnl_activation_blocker(window_days=60)
    )


def test_store_backed_reader_allows_pnl_activation_when_reserve_window_is_clean(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_sleeve_daily_attribution_record(
        _record_for_sleeve(
            sleeve_id="trend-following-v1",
            day="2026-04-22",
            ending_equity="500",
            daily_return="0.01",
        )
    )
    store.write_sleeve_daily_attribution_record(
        _record_for_sleeve(
            sleeve_id="vol-target-v1",
            day="2026-04-22",
            ending_equity="500",
            daily_return="0.01",
        )
    )
    store.write_residual_reserve_snapshot(
        _reserve_snapshot(
            day="2026-04-22",
            cash_balance="20",
        )
    )

    reader = StoreBackedAttributionRecordsReader(
        operator_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 20, 0, tzinfo=UTC),
    )

    assert reader.pnl_activation_blocker(window_days=60) is None


def test_store_backed_reader_uses_latest_reserve_snapshot_per_trading_day(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_sleeve_daily_attribution_record(
        _record_for_sleeve(
            sleeve_id="trend-following-v1",
            day="2026-04-22",
            ending_equity="500",
            daily_return="0.01",
        )
    )
    store.write_sleeve_daily_attribution_record(
        _record_for_sleeve(
            sleeve_id="vol-target-v1",
            day="2026-04-22",
            ending_equity="500",
            daily_return="0.01",
        )
    )
    store.write_residual_reserve_snapshot(
        _reserve_snapshot(
            day="2026-04-22",
            cash_balance="80",
            positions=(("QQQ", "1", "100", "105"),),
            snapshot_id="bootstrap-ledger-1__reserve",
            recorded_at_utc=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
        )
    )
    store.write_residual_reserve_snapshot(
        _reserve_snapshot(
            day="2026-04-22",
            cash_balance="20",
            positions=(),
            snapshot_id="close-ledger-1__reserve__2026-04-22",
            recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
        )
    )

    reader = StoreBackedAttributionRecordsReader(
        operator_store=store,
        now_provider=lambda: datetime(2026, 4, 23, 20, 0, tzinfo=UTC),
    )

    assert reader.pnl_activation_blocker(window_days=60) is None
