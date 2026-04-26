"""Defect 7 — runtime sizing monotonicity tests.

Verifies that the runtime sizing engine refuses to ship a decision that
increases position size while the underlying inputs (cost / capacity /
drawdown / uncertainty) have worsened. Without runtime enforcement,
offline artifacts could declare ``sizing_property_violated`` while the
runtime kept routing larger orders.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tradingx.forecasts import (
    SizingPolicyViolation,
    enforce_sizing_monotonicity_runtime,
)


def test_sizing_engine_blocks_higher_cost_increasing_size_in_runtime() -> None:
    """Cost worsens, candidate increases size — runtime must refuse."""

    prior = {"size": "10"}
    candidate = {
        "size": "15",
        "higher_cost": True,
    }
    with pytest.raises(SizingPolicyViolation) as excinfo:
        enforce_sizing_monotonicity_runtime(
            prior_decision=prior,
            candidate_decision=candidate,
        )
    assert "sizing_property_violated" in excinfo.value.violations


def test_sizing_engine_blocks_lower_capacity_increasing_size_in_runtime() -> None:
    """Capacity tightens, candidate increases size — runtime must refuse."""

    prior = {"size": "10"}
    candidate = {
        "size": "15",
        "lower_capacity": True,
    }
    with pytest.raises(SizingPolicyViolation) as excinfo:
        enforce_sizing_monotonicity_runtime(
            prior_decision=prior,
            candidate_decision=candidate,
        )
    assert "sizing_property_violated" in excinfo.value.violations


def test_sizing_engine_allows_decreasing_size_with_worse_inputs() -> None:
    """Sanity: shrinking the position with worse inputs is fine."""

    prior = {"size": "15"}
    candidate = {
        "size": "10",
        "higher_cost": True,
        "lower_capacity": True,
    }
    decision, violations = enforce_sizing_monotonicity_runtime(
        prior_decision=prior,
        candidate_decision=candidate,
    )
    assert decision is candidate
    assert violations == ()


def test_sizing_engine_allows_growth_when_inputs_unchanged() -> None:
    """Sanity: growing the position when inputs are stable is fine."""

    prior = {"size": "10"}
    candidate = {"size": Decimal("12")}
    decision, violations = enforce_sizing_monotonicity_runtime(
        prior_decision=prior,
        candidate_decision=candidate,
    )
    assert decision is candidate
    assert violations == ()
