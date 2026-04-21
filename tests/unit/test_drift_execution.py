from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingx.drift.execution import compute_execution_drift_ratio
from tradingx.types import ReplaySlippageRecord


def _record(
    *,
    symbol: str = "SPY",
    divergence_ratio: str = "1.0",
    days_ago: int = 1,
) -> ReplaySlippageRecord:
    now = datetime.now(UTC) - timedelta(days=days_ago)
    return ReplaySlippageRecord(
        replay_id=f"replay-{days_ago}",
        execution_id=f"exec-{days_ago}",
        intent_id=f"intent-{days_ago}",
        symbol=symbol,
        side="buy",
        filled_qty=Decimal("1"),
        reference_price=Decimal("100"),
        paper_fill_price=Decimal("100.1"),
        paper_slippage_bps=Decimal("10"),
        simulated_fill_price=Decimal("100.05"),
        simulated_slippage_bps=Decimal("5"),
        divergence_ratio=Decimal(divergence_ratio),
        quoted_spread_bps=Decimal("4"),
        participation_rate=Decimal("0.01"),
        generated_at_utc=now,
    )


def test_empty_records_returns_zero() -> None:
    assert compute_execution_drift_ratio(replay_records=()) == Decimal("0")


def test_mean_abs_divergence_ratio() -> None:
    records = (
        _record(divergence_ratio="1.5", days_ago=1),
        _record(divergence_ratio="-2.0", days_ago=2),
        _record(divergence_ratio="1.0", days_ago=3),
    )
    assert compute_execution_drift_ratio(replay_records=records) == Decimal("1.5")


def test_rolling_window_filter_excludes_stale_records() -> None:
    records = (
        _record(divergence_ratio="1.5", days_ago=1),
        _record(divergence_ratio="2.0", days_ago=100),
    )
    assert compute_execution_drift_ratio(
        replay_records=records, rolling_window_days=30
    ) == Decimal("1.5")


def test_symbol_filter_narrows() -> None:
    records = (
        _record(symbol="SPY", divergence_ratio="1.5", days_ago=1),
        _record(symbol="QQQ", divergence_ratio="3.0", days_ago=2),
    )
    assert compute_execution_drift_ratio(
        replay_records=records, symbol="SPY"
    ) == Decimal("1.5")
