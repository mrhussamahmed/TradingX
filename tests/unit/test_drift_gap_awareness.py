from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.drift.blueprint import DriftThresholds
from tradingx.drift.gateway import StoreBackedAttributionRecordsReader
from tradingx.drift.live_returns_source import SleeveDailyReturnsReader
from tradingx.drift.pnl_divergence import compute_live_vs_backtest_pnl_divergence
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import SleeveAttributionGapRecord, SleeveDailyAttributionRecord


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
