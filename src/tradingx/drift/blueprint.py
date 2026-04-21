"""Drift-monitor blueprint and threshold configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class DriftThresholds:
    psi_warning: Decimal = Decimal("0.10")
    psi_critical: Decimal = Decimal("0.25")
    ks_p_value_critical: Decimal = Decimal("0.05")
    execution_drift_warning: Decimal = Decimal("1.5")
    execution_drift_critical: Decimal = Decimal("2.0")
    pnl_absolute_warning: Decimal = Decimal("0.02")
    pnl_absolute_critical: Decimal = Decimal("0.04")
    pnl_sharpe_warning: Decimal = Decimal("0.30")
    pnl_sharpe_critical: Decimal = Decimal("0.50")


@dataclass(frozen=True)
class DriftMonitorBlueprint:
    blueprint_id: str
    thresholds: DriftThresholds = field(default_factory=DriftThresholds)
    feature_monitor_names: tuple[str, ...] = (
        "spy_close_over_sma_200",
        "vix_level",
        "yield_curve_spread_bps",
        "trend_signal_strength",
        "vol_forecast_ewma",
    )
    signal_monitor_sleeve_ids: tuple[str, ...] = (
        "trend-following-v1",
        "vol-target-v1",
    )
    execution_drift_rolling_window_days: int = 30
    pnl_divergence_rolling_window_days: int = 60
    minimum_live_days_for_alarm: int = 30

    def __post_init__(self) -> None:
        if self.execution_drift_rolling_window_days <= 0:
            raise ValueError("execution_drift_rolling_window_days must be > 0")
        if self.pnl_divergence_rolling_window_days <= 0:
            raise ValueError("pnl_divergence_rolling_window_days must be > 0")
        if self.minimum_live_days_for_alarm <= 0:
            raise ValueError("minimum_live_days_for_alarm must be > 0")


__all__ = ("DriftMonitorBlueprint", "DriftThresholds")
