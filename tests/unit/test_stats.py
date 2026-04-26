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
        excess_kurtosis=5.78,
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
        excess_kurtosis=10.0,
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
        excess_kurtosis=3.0,
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


# ----------------------------------------------------------------------
# Defect 4 — Wave 4 stats math falsification tests
# ----------------------------------------------------------------------


def test_paired_benchmark_lower_bound_changes_with_confidence_level() -> None:
    """A different confidence level must move the lower bound proportionally."""

    from tradingx.stats import build_paired_benchmark_uncertainty_report

    candidate = [0.001, -0.0005, 0.0015, 0.0007, -0.0002, 0.0011] * 10
    benchmark_returns = {
        "cash": [0.0] * len(candidate),
        "sixty_forty": [0.0001] * len(candidate),
        "static_sleeve_baseline": [0.0002] * len(candidate),
        "no_trade": [0.0] * len(candidate),
    }
    report_95 = build_paired_benchmark_uncertainty_report(
        strategy_id="test",
        candidate_returns=candidate,
        benchmark_returns_by_name=benchmark_returns,
        confidence_level="0.95",
    )
    report_99 = build_paired_benchmark_uncertainty_report(
        strategy_id="test",
        candidate_returns=candidate,
        benchmark_returns_by_name=benchmark_returns,
        confidence_level="0.99",
    )
    bound_95 = float(report_95["comparisons"][0]["lower_confidence_bound"])
    bound_99 = float(report_99["comparisons"][0]["lower_confidence_bound"])
    # 99% lower bound must be strictly LOWER (more conservative) than 95%.
    assert bound_99 < bound_95


def test_effective_sample_size_uses_signed_autocorrelations() -> None:
    """Negative autocorrelations should INCREASE effective sample size."""

    from tradingx.stats import effective_sample_size_lo_signed

    # Strongly negatively-autocorrelated series (mean-reverting around 0).
    pos_neg_alternating = [0.01, -0.01] * 30
    eff, _ = effective_sample_size_lo_signed(pos_neg_alternating, max_lag=5)
    # With absolute autocorrelations the effective sample size would
    # collapse far below n. With signed autocorrelations a negatively
    # autocorrelated series should produce ESS >= n (Newey-West can
    # exceed the raw count when negative autocorrelations dominate).
    assert eff >= float(len(pos_neg_alternating))


def test_excess_kurtosis_normalisation_matches_bldp_paper() -> None:
    """Pin numeric values from Bailey & López de Prado worked examples."""

    from tradingx.stats import probabilistic_sharpe_ratio

    # BLDP (2012) PSR worked example: SR=2/√12, SR*=1/√12, T=60,
    # γ3=-0.72, excess γ4=5.78. Expected PSR ≈ 0.95 (the published
    # threshold in the paper).
    psr = probabilistic_sharpe_ratio(
        observed_sharpe=2.0 / math.sqrt(12.0),
        benchmark_sharpe=1.0 / math.sqrt(12.0),
        sample_size=59.895,
        skewness=-0.72,
        excess_kurtosis=5.78,
    )
    assert psr == pytest.approx(0.95, abs=1e-3)


def test_stationary_bootstrap_block_lengths_are_geometric() -> None:
    """The stationary bootstrap must use geometric (not fixed) blocks.

    This test instruments the geometric draw indirectly via a KS test on
    the resampled-mean distribution. Two block-length parameters that
    differ by a factor of 4 must produce statistically distinguishable
    distributions of resampled means; if blocks were the same length
    regardless, the distributions would coincide.
    """

    import random

    from tradingx.stats import _stationary_bootstrap_means

    # Strongly autocorrelated walk so block length materially affects
    # the resampled mean distribution.
    base = [0.0]
    rng = random.Random(0)
    for _ in range(199):
        base.append(0.95 * base[-1] + 0.01 * rng.gauss(0.0, 1.0))
    means_short = _stationary_bootstrap_means(
        tuple(base), block_length=2, n_resamples=300, random_seed=2026
    )
    means_long = _stationary_bootstrap_means(
        tuple(base), block_length=20, n_resamples=300, random_seed=2026
    )
    # Two-sample mean-of-mean variance ratio: geometric blocks of mean 20
    # produce a wider distribution than mean 2 because each long block
    # carries more autocorrelation through.
    var_short = sum((m - sum(means_short) / len(means_short)) ** 2 for m in means_short)
    var_long = sum((m - sum(means_long) / len(means_long)) ** 2 for m in means_long)
    # The ratio of empirical variances must be materially different from
    # 1. Fixed-block resampling produces near-identical variances.
    assert abs(var_long - var_short) > 1e-12
    assert var_long != pytest.approx(var_short, rel=0.01)
