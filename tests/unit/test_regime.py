from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from tradingx.features.regime import classify_regime
from tradingx.validation import _build_default_regime_snapshots


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


def test_validation_regime_snapshots_use_pit_vix_and_yield_curve(
    tmp_path,
) -> None:
    from tradingx.types import StrategyCandidate

    candidate = StrategyCandidate(
        candidate_id="macro-test-v1",
        family="test",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="under_evaluation",
    )
    index = pd.date_range("2025-07-14", periods=203, freq="B", tz="UTC")
    closes = [100.0 + index_value for index_value in range(203)]
    bars = {
        "SPY": pd.DataFrame(
            {
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [1_000_000] * len(closes),
            },
            index=index,
        )
    }
    vix_path = tmp_path / "vix_daily.csv"
    treasury_path = tmp_path / "treasury_yields.csv"
    decision_day = date(2026, 4, 20)
    execution_day = date(2026, 4, 21)
    pd.DataFrame(
        {
            "date": [decision_day.isoformat()],
            "vix_close": [36.0],
        }
    ).to_csv(vix_path, index=False)
    pd.DataFrame(
        {
            "date": [decision_day.isoformat()],
            "dgs2": [4.6],
            "dgs10": [4.2],
            "spread_2s10s_bps": [-40.0],
        }
    ).to_csv(treasury_path, index=False)

    regimes = _build_default_regime_snapshots(
        candidate,
        bars_by_symbol=bars,
        vix_cache_path=vix_path,
        treasury_cache_path=treasury_path,
    )

    assert regimes[execution_day].vix_close == Decimal("36.0")
    assert regimes[execution_day].yield_curve_spread_bps == Decimal("-40.0")
    assert regimes[execution_day].regime == "stressed"


def test_validation_regime_snapshots_produce_risk_off_from_pit_vix(
    tmp_path,
) -> None:
    from tradingx.types import StrategyCandidate

    candidate = StrategyCandidate(
        candidate_id="macro-risk-off-v1",
        family="test",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="under_evaluation",
    )
    index = pd.date_range("2025-07-14", periods=203, freq="B", tz="UTC")
    closes = [100.0 + index_value for index_value in range(203)]
    bars = {
        "SPY": pd.DataFrame(
            {
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [1_000_000] * len(closes),
            },
            index=index,
        )
    }
    vix_path = tmp_path / "vix_daily.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-20"],
            "vix_close": [28.0],
        }
    ).to_csv(vix_path, index=False)

    regimes = _build_default_regime_snapshots(
        candidate,
        bars_by_symbol=bars,
        vix_cache_path=vix_path,
    )

    assert regimes[date(2026, 4, 21)].above_sma_200 is True
    assert regimes[date(2026, 4, 21)].vix_close == Decimal("28.0")
    assert regimes[date(2026, 4, 21)].regime == "risk_off"


def test_validation_regime_snapshots_produce_stressed_from_pit_curve_inversion(
    tmp_path,
) -> None:
    from tradingx.types import StrategyCandidate

    candidate = StrategyCandidate(
        candidate_id="macro-curve-v1",
        family="test",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="under_evaluation",
    )
    index = pd.date_range("2025-07-14", periods=203, freq="B", tz="UTC")
    closes = [300.0 - index_value for index_value in range(203)]
    bars = {
        "SPY": pd.DataFrame(
            {
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [1_000_000] * len(closes),
            },
            index=index,
        )
    }
    treasury_path = tmp_path / "treasury_yields.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-20"],
            "dgs2": [4.5],
            "dgs10": [4.4],
            "spread_2s10s_bps": [-10.0],
        }
    ).to_csv(treasury_path, index=False)

    regimes = _build_default_regime_snapshots(
        candidate,
        bars_by_symbol=bars,
        treasury_cache_path=treasury_path,
    )

    assert regimes[date(2026, 4, 21)].above_sma_200 is False
    assert regimes[date(2026, 4, 21)].yield_curve_spread_bps == Decimal("-10.0")
    assert regimes[date(2026, 4, 21)].regime == "stressed"
