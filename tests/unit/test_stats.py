from __future__ import annotations

import importlib
import math

import pytest

from tradingx.stats import (
    calmar_ratio,
    conditional_drawdown_at_risk,
    max_drawdown,
)


def test_stats_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.stats")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_lo_adjusted_sharpe_ratio_returns_none_for_constant_series(caplog) -> None:
    module = importlib.import_module("tradingx.stats")

    with caplog.at_level("WARNING"):
        result = module.lo_adjusted_sharpe_ratio(
            returns=[0.01] * 40,
            risk_free_daily_rates=[0.0] * 40,
        )

    assert result is None
    assert "variance is zero" in caplog.text


def test_lo_adjusted_sharpe_ratio_avoids_warnings_for_constant_lag_windows(
    recwarn,
) -> None:
    module = importlib.import_module("tradingx.stats")

    result = module.lo_adjusted_sharpe_ratio(
        returns=[0.0003] * 252,
        risk_free_daily_rates=[0.0002] * 252,
    )

    assert result is None
    assert [warning for warning in recwarn if warning.category is RuntimeWarning] == []


def test_lo_adjusted_sharpe_ratio_penalizes_positive_autocorrelation() -> None:
    module = importlib.import_module("tradingx.stats")
    returns = (
        ([0.03] * 10)
        + ([0.02] * 10)
        + ([0.01] * 10)
        + ([0.0] * 10)
        + ([0.01] * 10)
        + ([0.02] * 10)
    )

    adjusted = module.lo_adjusted_sharpe_ratio(
        returns=returns,
        risk_free_daily_rates=[0.0] * len(returns),
    )
    naive = module.naive_annualized_sharpe_ratio(
        returns=returns,
        risk_free_daily_rates=[0.0] * len(returns),
    )

    assert adjusted is not None
    assert naive is not None
    assert adjusted < naive


def test_probabilistic_sharpe_ratio_reproduces_bailey_2012_appendix_example() -> None:
    module = importlib.import_module("tradingx.stats")

    psr = module.probabilistic_sharpe_ratio(
        observed_sharpe=2.0 / math.sqrt(12.0),
        benchmark_sharpe=1.0 / math.sqrt(12.0),
        sample_size=59.895,
        skewness=-0.72,
        kurtosis=5.78,
    )

    assert psr == pytest.approx(0.95, abs=1e-4)


def test_expected_max_sharpe_reproduces_bailey_2014_threshold() -> None:
    module = importlib.import_module("tradingx.stats")

    threshold = module.expected_max_sharpe(
        n_trials=100,
        trial_sharpe_variance=0.5,
    )

    assert threshold == pytest.approx(0.1132, abs=1e-4)


def test_deflated_sharpe_ratio_reproduces_bailey_2014_example() -> None:
    module = importlib.import_module("tradingx.stats")

    dsr = module.deflated_sharpe_ratio(
        observed_sharpe=2.5 / math.sqrt(250.0),
        sample_size=1250,
        skewness=-3.0,
        kurtosis=10.0,
        n_trials=100,
        trial_sharpe_variance=0.5,
    )

    assert dsr == pytest.approx(0.9004, abs=1e-4)


def test_deflated_sharpe_ratio_reproduces_bailey_2014_normal_case() -> None:
    module = importlib.import_module("tradingx.stats")

    dsr = module.deflated_sharpe_ratio(
        observed_sharpe=2.5 / math.sqrt(250.0),
        sample_size=1250,
        skewness=0.0,
        kurtosis=3.0,
        n_trials=88,
        trial_sharpe_variance=0.5,
    )

    assert dsr == pytest.approx(0.9505, abs=1e-4)


def test_max_drawdown_flat_series_is_zero() -> None:
    returns = [0.0, 0.0, 0.0, 0.0]

    assert max_drawdown(returns) == 0.0


def test_max_drawdown_monotone_up_is_zero() -> None:
    returns = [0.01, 0.02, 0.005, 0.01]

    assert max_drawdown(returns) == 0.0


def test_max_drawdown_single_dip() -> None:
    returns = [0.10, -0.20]

    assert abs(max_drawdown(returns) - 0.20) < 1e-9


def test_max_drawdown_recovers_then_deeper_drop() -> None:
    returns = [0.10, -0.05, 0.15, -0.30, 0.05]

    result = max_drawdown(returns)

    assert abs(result - 0.30) < 1e-9


def test_max_drawdown_empty_returns_is_zero() -> None:
    assert max_drawdown([]) == 0.0


def test_conditional_drawdown_at_risk_flat_series_is_zero() -> None:
    returns = [0.0] * 10

    assert conditional_drawdown_at_risk(returns, confidence=0.95) == 0.0


def test_conditional_drawdown_at_risk_matches_worst_tail_average() -> None:
    returns = [
        0.10,
        -0.10,
        -(1.0 / 9.0),
        -0.125,
    ]

    result = conditional_drawdown_at_risk(returns, confidence=0.5)

    assert result == pytest.approx(0.25, abs=1e-9)


def test_conditional_drawdown_at_risk_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        conditional_drawdown_at_risk([0.01, -0.02], confidence=0.0)

    with pytest.raises(ValueError):
        conditional_drawdown_at_risk([0.01, -0.02], confidence=1.0)


def test_conditional_drawdown_at_risk_empty_returns_is_zero() -> None:
    assert conditional_drawdown_at_risk([], confidence=0.95) == 0.0


def test_calmar_ratio_returns_zero_for_empty_series() -> None:
    assert calmar_ratio([]) == 0.0


def test_calmar_ratio_returns_infinity_for_positive_zero_drawdown() -> None:
    returns = [0.01, 0.02, 0.005]

    assert math.isinf(calmar_ratio(returns))


def test_calmar_ratio_matches_annualized_return_divided_by_max_drawdown() -> None:
    returns = [0.10, -0.05, 0.02]

    result = calmar_ratio(returns, periods_per_year=3)

    assert result == pytest.approx(1.318, abs=1e-3)
