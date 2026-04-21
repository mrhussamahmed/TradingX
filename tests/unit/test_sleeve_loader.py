from __future__ import annotations

import pytest

from tradingx.sleeves.base import build_sleeve_from_candidate
from tradingx.sleeves.trend import TrendSleeve
from tradingx.types import StrategyCandidate


def _trend_candidate() -> StrategyCandidate:
    return StrategyCandidate(
        candidate_id="trend-test-v1",
        family="trend_following",
        benchmark_symbol="SPY",
        universe=("SPY", "QQQ"),
        parameter_set={
            "lookback_days": 100,
            "sma_window_days": 50,
            "signal": "long_only",
            "forecast_method": "ewma",
        },
        status="under_evaluation",
        sleeve_class_path="tradingx.sleeves.trend.TrendSleeve",
    )


def test_build_sleeve_from_candidate_imports_class() -> None:
    sleeve = build_sleeve_from_candidate(_trend_candidate())

    assert isinstance(sleeve, TrendSleeve)


def test_build_sleeve_from_candidate_overrides_defaults_from_parameter_set() -> None:
    sleeve = build_sleeve_from_candidate(_trend_candidate())

    assert sleeve.lookback_days == 100
    assert sleeve.sma_window_days == 50
    assert sleeve.forecast_method == "ewma"


def test_build_sleeve_from_candidate_uses_candidate_universe() -> None:
    sleeve = build_sleeve_from_candidate(_trend_candidate())

    assert sleeve.allowed_instruments == ("SPY", "QQQ")


def test_build_sleeve_from_candidate_uses_candidate_id() -> None:
    sleeve = build_sleeve_from_candidate(_trend_candidate())

    assert sleeve.sleeve_id == "trend-test-v1"


def test_build_sleeve_from_candidate_silently_drops_unknown_keys() -> None:
    sleeve = build_sleeve_from_candidate(_trend_candidate())

    assert sleeve is not None


def test_build_sleeve_from_candidate_raises_on_null_path() -> None:
    candidate = StrategyCandidate(
        candidate_id="mean-reversion-v1",
        family="mean_reversion",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="under_evaluation",
        sleeve_class_path=None,
    )

    with pytest.raises(ValueError, match="sleeve_class_path"):
        build_sleeve_from_candidate(candidate)


def test_build_sleeve_from_candidate_raises_on_bad_import() -> None:
    candidate = StrategyCandidate(
        candidate_id="x",
        family="x",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="under_evaluation",
        sleeve_class_path="tradingx.sleeves.nonexistent.Nothing",
    )

    with pytest.raises((ValueError, ImportError, AttributeError, TypeError)):
        build_sleeve_from_candidate(candidate)
