"""Live-vs-backtest P&L divergence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradingx.drift.blueprint import DriftThresholds
from tradingx.types import SleeveDailyAttributionRecord


@dataclass(frozen=True)
class PnlDivergenceVerdict:
    sleeve_id: str
    live_daily_return_series: tuple[Decimal, ...]
    backtest_daily_return_series: tuple[Decimal, ...]
    absolute_delta: Decimal
    sharpe_delta_ratio: Decimal
    severity: str


def compute_live_vs_backtest_pnl_divergence(
    *,
    sleeve_id: str,
    live_attribution_records: tuple[SleeveDailyAttributionRecord, ...],
    backtest_returns_series: tuple[Decimal, ...],
    thresholds: DriftThresholds,
    rolling_window_days: int = 60,
    minimum_live_days: int = 30,
    has_gap: bool = False,
) -> PnlDivergenceVerdict:
    ordered_records = sorted(
        live_attribution_records,
        key=lambda item: item.trading_day,
    )
    filtered_records = tuple(
        record
        for record in ordered_records[-rolling_window_days:]
        if record.sleeve_id == sleeve_id
    )
    live_returns = tuple(record.daily_return for record in filtered_records)
    if has_gap:
        return PnlDivergenceVerdict(
            sleeve_id=sleeve_id,
            live_daily_return_series=live_returns,
            backtest_daily_return_series=(),
            absolute_delta=Decimal("0"),
            sharpe_delta_ratio=Decimal("0"),
            severity="pending",
        )
    if len(live_returns) < minimum_live_days:
        return PnlDivergenceVerdict(
            sleeve_id=sleeve_id,
            live_daily_return_series=live_returns,
            backtest_daily_return_series=(),
            absolute_delta=Decimal("0"),
            sharpe_delta_ratio=Decimal("0"),
            severity="pending",
        )
    backtest_tail = backtest_returns_series[-len(live_returns) :]
    if len(backtest_tail) < minimum_live_days:
        return PnlDivergenceVerdict(
            sleeve_id=sleeve_id,
            live_daily_return_series=live_returns,
            backtest_daily_return_series=backtest_tail,
            absolute_delta=Decimal("0"),
            sharpe_delta_ratio=Decimal("0"),
            severity="pending",
        )
    absolute_delta = _mean_abs_delta(live_returns, backtest_tail)
    sharpe_delta_ratio = _sharpe_delta_ratio(live_returns, backtest_tail)
    return PnlDivergenceVerdict(
        sleeve_id=sleeve_id,
        live_daily_return_series=live_returns,
        backtest_daily_return_series=backtest_tail,
        absolute_delta=absolute_delta,
        sharpe_delta_ratio=sharpe_delta_ratio,
        severity=_severity(
            absolute_delta=absolute_delta,
            sharpe_delta_ratio=sharpe_delta_ratio,
            thresholds=thresholds,
        ),
    )


def _mean_abs_delta(
    live: tuple[Decimal, ...],
    backtest: tuple[Decimal, ...],
) -> Decimal:
    pairs = list(zip(live, backtest, strict=False))
    if not pairs:
        return Decimal("0")
    total = sum((abs(left - right) for left, right in pairs), start=Decimal("0"))
    return total / Decimal(len(pairs))


def _sharpe_delta_ratio(
    live: tuple[Decimal, ...],
    backtest: tuple[Decimal, ...],
) -> Decimal:
    live_sharpe = _sample_sharpe(live)
    backtest_sharpe = _sample_sharpe(backtest)
    denominator = max(abs(backtest_sharpe), Decimal("0.3"))
    return (live_sharpe - backtest_sharpe) / denominator


def _sample_sharpe(returns: tuple[Decimal, ...]) -> Decimal:
    if len(returns) < 2:
        return Decimal("0")
    mean = sum(returns, start=Decimal("0")) / Decimal(len(returns))
    squared_deviation = sum(
        ((value - mean) ** 2 for value in returns),
        start=Decimal("0"),
    )
    variance = squared_deviation / Decimal(len(returns) - 1)
    if variance <= Decimal("0"):
        return Decimal("0")
    std = Decimal(str(float(variance) ** 0.5))
    return mean / std


def _severity(
    *,
    absolute_delta: Decimal,
    sharpe_delta_ratio: Decimal,
    thresholds: DriftThresholds,
) -> str:
    absolute_sharpe_delta = abs(sharpe_delta_ratio)
    if (
        absolute_delta >= thresholds.pnl_absolute_critical
        or absolute_sharpe_delta >= thresholds.pnl_sharpe_critical
    ):
        return "critical"
    if (
        absolute_delta >= thresholds.pnl_absolute_warning
        or absolute_sharpe_delta >= thresholds.pnl_sharpe_warning
    ):
        return "warning"
    return "info"


__all__ = (
    "PnlDivergenceVerdict",
    "compute_live_vs_backtest_pnl_divergence",
)
