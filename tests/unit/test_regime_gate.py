from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from tradingx.sleeves.regime_gate import apply_regime_exposure_floor
from tradingx.types import RegimeSnapshot


def _regime(state: str) -> RegimeSnapshot:
    return RegimeSnapshot(
        observation_date=date(2026, 4, 21),
        regime=state,
        above_sma_200=None,
        vix_elevated=None,
        vix_stressed=None,
        yield_curve_inverted=None,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=None,
        yield_curve_spread_bps=None,
    )


@pytest.mark.parametrize("state", ["risk_on", "neutral"])
@pytest.mark.parametrize("family", ["trend_following", "vol_target"])
def test_regime_gate_passes_through_in_risk_on_and_neutral(
    state: str,
    family: str,
) -> None:
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="s-1",
        proposed_target_weight=Decimal("0.65"),
        current_position_weight=Decimal("0.40"),
        regime=_regime(state),
        sleeve_family=family,
    )

    assert adjusted == Decimal("0.65")
    assert rationale == ""


def test_regime_gate_suppresses_trend_entry_in_risk_off_when_no_position() -> None:
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="trend-following-v1",
        proposed_target_weight=Decimal("0.8"),
        current_position_weight=Decimal("0"),
        regime=_regime("risk_off"),
        sleeve_family="trend_following",
    )

    assert adjusted == Decimal("0")
    assert rationale == "regime_risk_off_suppress_entry"


def test_regime_gate_passes_through_trend_in_risk_off_when_holding() -> None:
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="trend-following-v1",
        proposed_target_weight=Decimal("0.5"),
        current_position_weight=Decimal("0.4"),
        regime=_regime("risk_off"),
        sleeve_family="trend_following",
    )

    assert adjusted == Decimal("0.5")
    assert rationale == ""


def test_regime_gate_passes_through_vol_target_in_risk_off() -> None:
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="vol-target-v1",
        proposed_target_weight=Decimal("0.7"),
        current_position_weight=Decimal("0"),
        regime=_regime("risk_off"),
        sleeve_family="vol_target",
    )

    assert adjusted == Decimal("0.7")
    assert rationale == ""


@pytest.mark.parametrize("family", ["trend_following", "vol_target"])
@pytest.mark.parametrize("current", ["0", "0.5"])
def test_regime_gate_zeros_both_families_in_stressed(
    family: str,
    current: str,
) -> None:
    adjusted, rationale = apply_regime_exposure_floor(
        sleeve_id="s-1",
        proposed_target_weight=Decimal("0.9"),
        current_position_weight=Decimal(current),
        regime=_regime("stressed"),
        sleeve_family=family,
    )

    assert adjusted == Decimal("0")
    assert rationale == "regime_stressed_liquidate"
