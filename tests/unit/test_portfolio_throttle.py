from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.throttle import (
    apply_cdar_soft_throttle,
    apply_mdd_design_throttle,
)


def _blueprint() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="s",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
        ),
    )


def _weights(n: int = 5) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({"SPY": [1.0] * n}, index=dates, dtype=float)


def test_no_throttle_below_design_target() -> None:
    weights = _weights(5)
    drawdown = pd.Series([0.05, 0.08, 0.10, 0.12, 0.14], index=weights.index)
    throttled, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=drawdown,
        blueprint=_blueprint(),
    )
    assert list(scale) == [1.0, 1.0, 1.0, 1.0, 1.0]
    pd.testing.assert_frame_equal(throttled, weights)


def test_scale_at_design_boundary_is_one() -> None:
    weights = _weights(1)
    drawdown = pd.Series([0.15], index=weights.index)
    _, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=drawdown,
        blueprint=_blueprint(),
    )
    assert list(scale) == [1.0]


def test_scale_midpoint_is_one_half() -> None:
    weights = _weights(1)
    drawdown = pd.Series([0.20], index=weights.index)
    _, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=drawdown,
        blueprint=_blueprint(),
    )
    assert list(scale) == pytest.approx([0.5])


def test_scale_at_halt_boundary_is_zero() -> None:
    weights = _weights(1)
    drawdown = pd.Series([0.25], index=weights.index)
    _, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=drawdown,
        blueprint=_blueprint(),
    )
    assert list(scale) == [0.0]


def test_scale_clamps_to_zero_above_halt() -> None:
    weights = _weights(1)
    drawdown = pd.Series([0.30], index=weights.index)
    _, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=drawdown,
        blueprint=_blueprint(),
    )
    assert list(scale) == [0.0]


def test_scale_applied_uniformly_across_symbols() -> None:
    dates = pd.date_range("2020-01-01", periods=2, freq="B", tz="UTC")
    weights = pd.DataFrame({"SPY": [0.6, 0.6], "QQQ": [0.4, 0.4]}, index=dates)
    drawdown = pd.Series([0.10, 0.20], index=dates)
    throttled, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=drawdown,
        blueprint=_blueprint(),
    )
    assert list(scale) == pytest.approx([1.0, 0.5])
    assert float(throttled.iloc[1]["SPY"]) == pytest.approx(0.3)
    assert float(throttled.iloc[1]["QQQ"]) == pytest.approx(0.2)


def test_cdar_no_throttle_below_threshold() -> None:
    weights = _weights(3)
    cdar = pd.Series([0.05, 0.06, 0.07], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == [1.0, 1.0, 1.0]


def test_cdar_at_threshold_boundary_is_one() -> None:
    weights = _weights(1)
    cdar = pd.Series([0.08], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == [1.0]


def test_cdar_midpoint_is_three_quarters() -> None:
    weights = _weights(1)
    cdar = pd.Series([0.12], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == pytest.approx([0.75])


def test_cdar_at_two_threshold_floor_half() -> None:
    weights = _weights(1)
    cdar = pd.Series([0.16], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == [0.5]


def test_cdar_above_two_threshold_clamped_to_half() -> None:
    weights = _weights(1)
    cdar = pd.Series([0.25], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == [0.5]


def test_mdd_and_cdar_compose_multiplicatively() -> None:
    weights = _weights(1)
    drawdown = pd.Series([0.20], index=weights.index)
    cdar = pd.Series([0.12], index=weights.index)
    mdd_throttled, mdd_scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=drawdown,
        blueprint=_blueprint(),
    )
    final_throttled, cdar_scale = apply_cdar_soft_throttle(
        target_weights=mdd_throttled,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(mdd_scale * cdar_scale) == pytest.approx([0.375])
    assert float(final_throttled.iloc[0]["SPY"]) == pytest.approx(0.375)
