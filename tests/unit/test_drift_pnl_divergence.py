from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingx.drift.blueprint import DriftThresholds
from tradingx.drift.pnl_divergence import compute_live_vs_backtest_pnl_divergence
from tradingx.types import SleeveDailyAttributionRecord


def _record(
    *,
    daily_return: str,
    days_ago: int,
) -> SleeveDailyAttributionRecord:
    recorded = datetime.now(UTC) - timedelta(days=days_ago)
    return SleeveDailyAttributionRecord(
        attribution_id=f"attr-{days_ago}",
        sleeve_id="trend-following-v1",
        trading_day=recorded.date().isoformat(),
        recorded_at_utc=recorded,
        starting_equity=Decimal("100000"),
        ending_equity=Decimal("100000") * (Decimal("1") + Decimal(daily_return)),
        daily_return=Decimal(daily_return),
        per_symbol_open_weight=(),
        per_symbol_close_weight=(),
    )


def test_pending_when_fewer_than_minimum_live_days() -> None:
    verdict = compute_live_vs_backtest_pnl_divergence(
        sleeve_id="trend-following-v1",
        live_attribution_records=tuple(
            _record(daily_return="0.01", days_ago=index) for index in range(10)
        ),
        backtest_returns_series=tuple(Decimal("0.01") for _ in range(60)),
        thresholds=DriftThresholds(),
        minimum_live_days=30,
    )
    assert verdict.severity == "pending"


def test_info_when_matching_series() -> None:
    verdict = compute_live_vs_backtest_pnl_divergence(
        sleeve_id="trend-following-v1",
        live_attribution_records=tuple(
            _record(daily_return="0.01", days_ago=index) for index in range(60)
        ),
        backtest_returns_series=tuple(Decimal("0.01") for _ in range(60)),
        thresholds=DriftThresholds(),
        minimum_live_days=30,
    )
    assert verdict.severity == "info"


def test_warning_when_absolute_delta_breaches_warning_threshold() -> None:
    verdict = compute_live_vs_backtest_pnl_divergence(
        sleeve_id="trend-following-v1",
        live_attribution_records=tuple(
            _record(daily_return="0.03", days_ago=index) for index in range(60)
        ),
        backtest_returns_series=tuple(Decimal("0.005") for _ in range(60)),
        thresholds=DriftThresholds(),
        minimum_live_days=30,
    )
    assert verdict.severity == "warning"


def test_critical_when_absolute_delta_breaches_critical_threshold() -> None:
    verdict = compute_live_vs_backtest_pnl_divergence(
        sleeve_id="trend-following-v1",
        live_attribution_records=tuple(
            _record(daily_return="0.05", days_ago=index) for index in range(60)
        ),
        backtest_returns_series=tuple(Decimal("0.0") for _ in range(60)),
        thresholds=DriftThresholds(),
        minimum_live_days=30,
    )
    assert verdict.severity == "critical"
