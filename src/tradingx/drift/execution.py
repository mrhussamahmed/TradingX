"""Execution-quality drift metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingx.types import ReplaySlippageRecord


def compute_execution_drift_ratio(
    *,
    replay_records: tuple[ReplaySlippageRecord, ...],
    symbol: str | None = None,
    rolling_window_days: int = 30,
    now_utc: datetime | None = None,
) -> Decimal:
    if not replay_records:
        return Decimal("0")
    now = now_utc or datetime.now(UTC)
    window_start = now - timedelta(days=rolling_window_days)
    filtered = tuple(
        record
        for record in replay_records
        if record.generated_at_utc >= window_start
        and (symbol is None or record.symbol == symbol)
    )
    if not filtered:
        return Decimal("0")
    total = sum(
        (abs(record.divergence_ratio) for record in filtered),
        start=Decimal("0"),
    )
    return total / Decimal(len(filtered))


__all__ = ("compute_execution_drift_ratio",)
