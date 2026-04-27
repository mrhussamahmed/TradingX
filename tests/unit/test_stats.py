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

    # BLDP (2012) appendix uses RAW γ4 = 5.78 (excess γ4 = 2.78).
    # The function takes excess kurtosis; pass the converted value.
    psr = module.probabilistic_sharpe_ratio(
        observed_sharpe=2.0 / math.sqrt(12.0),
        benchmark_sharpe=1.0 / math.sqrt(12.0),
        sample_size=59.895,
        skewness=-0.72,
        excess_kurtosis=2.78,
    )

    assert psr == pytest.approx(0.95, abs=2e-3)


def test_expected_max_sharpe_reproduces_bailey_2014_threshold() -> None:
    module = importlib.import_module("tradingx.stats")

    threshold = module.expected_max_sharpe(
        n_trials=100,
        trial_sharpe_variance=0.5,
    )

    assert threshold == pytest.approx(0.1132, abs=1e-4)


def test_deflated_sharpe_ratio_reproduces_bailey_2014_example() -> None:
    module = importlib.import_module("tradingx.stats")

    # Bailey (2014) worked example uses RAW γ4 = 10 (excess γ4 = 7).
    dsr = module.deflated_sharpe_ratio(
        observed_sharpe=2.5 / math.sqrt(250.0),
        sample_size=1250,
        skewness=-3.0,
        excess_kurtosis=7.0,
        n_trials=100,
        trial_sharpe_variance=0.5,
    )

    assert dsr == pytest.approx(0.9004, abs=1e-4)


def test_deflated_sharpe_ratio_reproduces_bailey_2014_normal_case() -> None:
    module = importlib.import_module("tradingx.stats")

    # Normal returns: skew=0, excess γ4 = 0 (raw γ4 = 3).
    dsr = module.deflated_sharpe_ratio(
        observed_sharpe=2.5 / math.sqrt(250.0),
        sample_size=1250,
        skewness=0.0,
        excess_kurtosis=0.0,
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
    """Pin ESS to the closed-form Newey-West value with signed lags.

    Earlier this test only asserted ``eff >= n``, which the upper clamp
    in ``effective_sample_size_lo_signed`` (``min(n, ...)``) satisfies
    trivially. To actually pin the math, this test rebuilds the
    Bartlett-weighted signed-autocorrelation sum by hand and asserts the
    function returns the same denominator (modulo the clamp). A buggy
    implementation that used absolute autocorrelations or the wrong
    weight would produce a materially different value.
    """

    from tradingx.stats import _lagged_autocorrelation, effective_sample_size_lo_signed

    # Construct an AR(1)-like series with a small positive drift so the
    # autocorrelation pattern is non-trivial and well-defined.
    rng_seed = 7
    import random as _r

    rng = _r.Random(rng_seed)
    series: list[float] = [0.0]
    for _ in range(199):
        series.append(0.6 * series[-1] + 0.01 * rng.gauss(0.0, 1.0))

    max_lag = 5
    n = len(series)
    weighted_signed_sum = 0.0
    import numpy as _np

    arr = _np.asarray(series, dtype=float)
    for lag in range(1, max_lag + 1):
        rho = _lagged_autocorrelation(arr, lag)
        assert rho is not None
        bartlett = 1.0 - (lag / (max_lag + 1.0))
        weighted_signed_sum += bartlett * float(rho)
    expected_denominator = 1.0 + (2.0 * weighted_signed_sum)
    expected_eff = float(n) if expected_denominator <= 0 else n / expected_denominator
    expected_eff_clamped = min(float(n), max(0.0, expected_eff))

    eff, _ = effective_sample_size_lo_signed(series, max_lag=max_lag)
    assert eff == pytest.approx(expected_eff_clamped, abs=1e-9)

    # And the signedness must matter: a negatively-autocorrelated series
    # produces a strictly larger denominator inverse than its
    # absolute-correlation counterpart would. Verify by mirroring sign:
    pos_neg_alternating = [0.01, -0.01] * 60
    eff_signed, _ = effective_sample_size_lo_signed(pos_neg_alternating, max_lag=5)
    # A buggy absolute-value implementation would collapse ESS toward
    # zero. The signed implementation either fires the
    # ``denominator <= 0`` fallback (returns n) or yields ESS > n which
    # is clamped to n. Either way ESS equals n exactly for this series.
    assert eff_signed == pytest.approx(float(len(pos_neg_alternating)))


def test_lo_adjusted_sharpe_uses_newey_west_window_weight() -> None:
    """Pin Sharpe HAC to ``1 - k/(M+1)`` to match ``effective_sample_size_lo_signed``.

    Review finding bug_001: ``lo_adjusted_sharpe_ratio`` used the Lo
    (2002) ``1 - k/M`` form (last lag weight = 0) while the ESS path
    used the Newey-West ``1 - k/(M+1)`` form (last lag weight =
    ``1/(M+1)``). The two paths therefore reported different
    autocorrelation penalties for the same series. The Defect 4 fix
    chose the Newey-West convention for ESS; this test pins the same
    convention for the Sharpe path.
    """

    import math
    import random as _r

    import numpy as _np

    from tradingx.stats import (
        DEFAULT_AUTOCORRELATION_LAGS,
        DEFAULT_PERIODS_PER_YEAR,
        _excess_returns,
        _lagged_autocorrelation,
        lo_adjusted_sharpe_ratio,
    )

    rng = _r.Random(7)
    returns: list[float] = [0.0]
    for _ in range(199):
        returns.append(0.6 * returns[-1] + 0.01 * rng.gauss(0.0, 1.0))
    risk_free = [0.0] * len(returns)

    excess = _excess_returns(returns=returns, risk_free_daily_rates=risk_free)
    volatility = float(_np.std(excess, ddof=1))
    base_sharpe = float(_np.mean(excess)) / volatility

    lag_count = DEFAULT_AUTOCORRELATION_LAGS
    adjustment = 1.0
    for lag in range(1, lag_count + 1):
        rho = _lagged_autocorrelation(excess, lag)
        assert rho is not None
        # MUST match ESS convention: 1 - k/(M+1).
        weight = 1.0 - (lag / (lag_count + 1.0))
        adjustment += 2.0 * weight * float(rho)
    expected = math.sqrt(DEFAULT_PERIODS_PER_YEAR) * base_sharpe / math.sqrt(adjustment)

    actual = lo_adjusted_sharpe_ratio(
        returns=returns,
        risk_free_daily_rates=risk_free,
    )
    assert actual is not None
    assert actual == pytest.approx(expected, rel=1e-9)


def test_psr_normal_returns_collapses_to_lo_2002_variance() -> None:
    """For normal returns, Var[SR] must collapse to (1 + SR²/2)/(n-1).

    This is the Lo (2002) canonical result and is the primary sanity
    check on the Bailey & López de Prado denominator. Any rename of the
    ``kurtosis``/``excess_kurtosis`` parameter must preserve this
    identity. The earlier ``(excess_kurtosis - 1)/4`` form failed it
    by producing a NEGATIVE contribution for excess γ4 = 0.
    """

    from scipy.stats import norm

    from tradingx.stats import probabilistic_sharpe_ratio

    observed_sharpe = 1.0
    benchmark_sharpe = 0.0
    sample_size = 252.0
    skewness = 0.0
    excess_kurtosis = 0.0  # Normal distribution.

    # Lo (2002) closed form for normal returns:
    #   z = (SR - SR*) * sqrt(n - 1) / sqrt(1 + SR²/2)
    #   PSR = Φ(z)
    expected_z = (
        (observed_sharpe - benchmark_sharpe)
        * math.sqrt(sample_size - 1.0)
        / math.sqrt(1.0 + (observed_sharpe**2) / 2.0)
    )
    expected_psr = float(norm.cdf(expected_z))

    psr = probabilistic_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        benchmark_sharpe=benchmark_sharpe,
        sample_size=sample_size,
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
    )
    assert psr == pytest.approx(expected_psr, abs=1e-12)


def test_stationary_bootstrap_block_lengths_are_geometric() -> None:
    """The stationary bootstrap must draw block lengths from Geom(1/L).

    To verify the *distribution* (not just that two block lengths give
    different variance), we instrument the random number generator and
    compare the empirical block-length distribution against the
    Geom(1/L) CDF using a one-sample KS test. A fixed-block
    implementation would produce a degenerate distribution that fails
    the KS test at any reasonable significance level.
    """

    import random
    from unittest.mock import patch

    from scipy.stats import geom, kstest

    from tradingx.stats import _stationary_bootstrap_means

    # Capture every block length the implementation draws by patching
    # ``random.Random.expovariate`` (the function the agent's fix
    # documented as the geometric-block source).
    rng = random.Random(2026)
    block_length = 8
    captured: list[float] = []
    real_expovariate = random.Random.expovariate

    def spy(self: random.Random, lambd: float) -> float:
        value = real_expovariate(self, lambd)
        captured.append(value)
        return value

    with patch.object(random.Random, "expovariate", spy):
        _stationary_bootstrap_means(
            tuple(0.01 * i for i in range(120)),
            block_length=block_length,
            n_resamples=200,
            random_seed=2026,
        )

    # Fail-fast guard: if the function silently reverted to fixed
    # blocks, no expovariate calls would happen.
    assert len(captured) > 0, (
        "stationary bootstrap must draw geometric block lengths via "
        "random.Random.expovariate; no draws observed"
    )

    # ``random.expovariate(1/L)`` returns continuous Exp(1/L) draws.
    # The implementation rounds these to integer block lengths via
    # ``max(1, int(...))``. Test the underlying continuous draws against
    # the Exp(1/L) CDF, which is the canonical Politis-Romano (1994)
    # construction.
    rate = 1.0 / float(block_length)
    statistic, p_value = kstest(captured, "expon", args=(0.0, 1.0 / rate))
    # Reject only at very low p-values (1e-3) so randomness across CI
    # runs does not flake; a fixed-block implementation would yield
    # p ≈ 0 because all draws would be identical.
    assert p_value > 1e-3, (
        f"block-length distribution does not match Exp(1/{block_length}); "
        f"KS p-value={p_value:.6f}"
    )

    # Sanity: keep the original variance check as a secondary signal so
    # a regression to fixed blocks would fail two assertions, not one.
    base = [0.0]
    rng2 = random.Random(0)
    for _ in range(199):
        base.append(0.95 * base[-1] + 0.01 * rng2.gauss(0.0, 1.0))
    means_short = _stationary_bootstrap_means(
        tuple(base), block_length=2, n_resamples=300, random_seed=2026
    )
    means_long = _stationary_bootstrap_means(
        tuple(base), block_length=20, n_resamples=300, random_seed=2026
    )
    var_short = sum((m - sum(means_short) / len(means_short)) ** 2 for m in means_short)
    var_long = sum((m - sum(means_long) / len(means_long)) ** 2 for m in means_long)
    assert var_long != pytest.approx(var_short, rel=0.01)
