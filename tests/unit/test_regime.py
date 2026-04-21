from __future__ import annotations

from datetime import date
from decimal import Decimal

from tradingx.features.regime import classify_regime


def _call(
    *,
    spy_close: str,
    spy_sma_200: str,
    vix_close: str | None,
    spread_bps: str | None,
):
    return classify_regime(
        observation_date=date(2026, 4, 21),
        spy_close=Decimal(spy_close),
        spy_sma_200=Decimal(spy_sma_200),
        vix_close=Decimal(vix_close) if vix_close is not None else None,
        yield_curve_spread_bps=(
            Decimal(spread_bps) if spread_bps is not None else None
        ),
    )


def test_risk_on_when_above_sma_and_vix_low_and_curve_normal() -> None:
    snap = _call(
        spy_close="500",
        spy_sma_200="480",
        vix_close="15",
        spread_bps="35",
    )
    assert snap.regime == "risk_on"
    assert snap.above_sma_200 is True
    assert snap.vix_elevated is False
    assert snap.vix_stressed is False
    assert snap.yield_curve_inverted is False


def test_risk_off_when_below_sma() -> None:
    snap = _call(
        spy_close="470",
        spy_sma_200="480",
        vix_close="18",
        spread_bps="20",
    )
    assert snap.regime == "risk_off"


def test_risk_off_when_vix_elevated() -> None:
    snap = _call(
        spy_close="500",
        spy_sma_200="480",
        vix_close="28",
        spread_bps="20",
    )
    assert snap.regime == "risk_off"


def test_stressed_when_vix_above_stress_threshold() -> None:
    snap = _call(
        spy_close="500",
        spy_sma_200="480",
        vix_close="40",
        spread_bps="20",
    )
    assert snap.regime == "stressed"


def test_stressed_when_curve_inverted_and_below_sma() -> None:
    snap = _call(
        spy_close="470",
        spy_sma_200="480",
        vix_close="20",
        spread_bps="-15",
    )
    assert snap.regime == "stressed"


def test_inverted_curve_alone_is_risk_on_not_stressed() -> None:
    snap = _call(
        spy_close="500",
        spy_sma_200="480",
        vix_close="18",
        spread_bps="-10",
    )
    assert snap.regime == "risk_on"


def test_regime_handles_missing_vix_gracefully() -> None:
    snap = _call(
        spy_close="500",
        spy_sma_200="480",
        vix_close=None,
        spread_bps="20",
    )
    assert snap.vix_elevated is None
    assert snap.vix_stressed is None
    assert snap.regime == "risk_on"


def test_regime_handles_missing_yield_curve_gracefully() -> None:
    snap = _call(
        spy_close="500",
        spy_sma_200="480",
        vix_close="15",
        spread_bps=None,
    )
    assert snap.yield_curve_inverted is None
    assert snap.regime == "risk_on"


def test_regime_handles_all_optional_inputs_missing() -> None:
    snap = _call(
        spy_close="500",
        spy_sma_200="480",
        vix_close=None,
        spread_bps=None,
    )
    assert snap.regime == "risk_on"


def test_regime_below_sma_with_no_vix_and_no_curve() -> None:
    snap = _call(
        spy_close="470",
        spy_sma_200="480",
        vix_close=None,
        spread_bps=None,
    )
    assert snap.regime == "risk_off"
