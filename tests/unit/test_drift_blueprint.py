from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from tradingx.drift.blueprint import DriftMonitorBlueprint, DriftThresholds


def test_defaults_match_design_0016() -> None:
    thresholds = DriftThresholds()
    assert thresholds.psi_warning == Decimal("0.10")
    assert thresholds.psi_critical == Decimal("0.25")
    assert thresholds.ks_p_value_critical == Decimal("0.05")
    assert thresholds.execution_drift_warning == Decimal("1.5")
    assert thresholds.execution_drift_critical == Decimal("2.0")
    assert thresholds.pnl_absolute_warning == Decimal("0.02")
    assert thresholds.pnl_absolute_critical == Decimal("0.04")
    assert thresholds.pnl_sharpe_warning == Decimal("0.30")
    assert thresholds.pnl_sharpe_critical == Decimal("0.50")


def test_blueprint_accepts_empty_feature_monitor_names() -> None:
    blueprint = DriftMonitorBlueprint(
        blueprint_id="bp-empty",
        feature_monitor_names=(),
    )
    assert blueprint.feature_monitor_names == ()


def test_blueprint_accepts_empty_signal_monitor_sleeve_ids() -> None:
    blueprint = DriftMonitorBlueprint(
        blueprint_id="bp-empty",
        signal_monitor_sleeve_ids=(),
    )
    assert blueprint.signal_monitor_sleeve_ids == ()


def test_blueprint_rejects_zero_rolling_window() -> None:
    with pytest.raises(ValueError, match="execution_drift_rolling_window_days"):
        DriftMonitorBlueprint(
            blueprint_id="bp",
            execution_drift_rolling_window_days=0,
        )


def test_blueprint_rejects_zero_pnl_window() -> None:
    with pytest.raises(ValueError, match="pnl_divergence_rolling_window_days"):
        DriftMonitorBlueprint(
            blueprint_id="bp",
            pnl_divergence_rolling_window_days=0,
        )


def test_blueprint_rejects_zero_minimum_live_days() -> None:
    with pytest.raises(ValueError, match="minimum_live_days_for_alarm"):
        DriftMonitorBlueprint(
            blueprint_id="bp",
            minimum_live_days_for_alarm=0,
        )


def test_blueprint_is_frozen() -> None:
    blueprint = DriftMonitorBlueprint(blueprint_id="bp")
    with pytest.raises(dataclasses.FrozenInstanceError):
        blueprint.blueprint_id = "bp-2"  # type: ignore[misc]
