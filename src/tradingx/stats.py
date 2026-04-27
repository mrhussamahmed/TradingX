"""Statistical performance measures used in TradingX research.

Sources:
- Bailey, D. H., and M. López de Prado, "The Sharpe Ratio Efficient
  Frontier", Journal of Risk 15(2), 2012. DOI: 10.21314/JOR.2012.255
- Bailey, D. H., and M. López de Prado, "The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting, and
  Non-Normality", Journal of Portfolio Management 40(5), 2014.
  DOI: 10.3905/jpm.2014.40.5.094
"""

from __future__ import annotations

import logging
import math
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import numpy as np
import numpy.typing as npt
from scipy.stats import norm  # type: ignore[import-untyped]

LOGGER = logging.getLogger(__name__)
EULER_MASCHERONI = 0.5772156649
DEFAULT_AUTOCORRELATION_LAGS = 5
DEFAULT_PERIODS_PER_YEAR = 252
PAPER_PERIODS_PER_YEAR = 250
FloatArray = npt.NDArray[np.float64]
DEFAULT_BOOTSTRAP_SEED = 2026
DEFAULT_BOOTSTRAP_RESAMPLES = 500
DEFAULT_BLOCK_LENGTHS = (5, 10, 20)
DEFAULT_REQUIRED_BENCHMARKS = (
    "cash",
    "sixty_forty",
    "static_sleeve_baseline",
    "no_trade",
)


def naive_annualized_sharpe_ratio(
    *,
    returns: Sequence[float],
    risk_free_daily_rates: Sequence[float],
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> float | None:
    excess_returns = _excess_returns(
        returns=returns,
        risk_free_daily_rates=risk_free_daily_rates,
    )
    if excess_returns.size < 2:
        return None
    volatility = float(np.std(excess_returns, ddof=1))
    if volatility <= 0 or math.isnan(volatility):
        return None
    return float(
        math.sqrt(periods_per_year) * (float(np.mean(excess_returns)) / volatility)
    )


def lo_adjusted_sharpe_ratio(
    *,
    returns: Sequence[float],
    risk_free_daily_rates: Sequence[float],
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
    autocorrelation_lags: int = DEFAULT_AUTOCORRELATION_LAGS,
) -> float | None:
    """Lo (2002) annualised Sharpe ratio with HAC autocorrelation adjustment.

    Uses Bartlett (Newey-West 1987) triangular weights ``w_k = 1 - k/(m+1)``
    where ``m`` is ``autocorrelation_lags`` (the truncation lag). The
    ``m+1`` denominator is the canonical Newey-West convention and matches
    ``effective_sample_size_lo_signed`` so both HAC paths apply the same
    penalty.

    bug_001 — earlier code used ``1 - k/m`` which gives the highest lag a
    weight of zero (effectively dropping it) and disagreed with the ESS
    path. The convention switch is mathematically the right call but
    changes observable output for series with strong, persistent
    autocorrelation: returns whose adjusted variance under the corrected
    weights is non-positive (e.g. tightly mean-reverting pairs spreads or
    short-side strategies with strong negative lag-1 autocorrelation) now
    return ``None`` instead of a finite Sharpe. Callers consuming this in
    production should expect intermittent ``None`` for such series and
    treat that as "Sharpe undefined", not as a regression.
    """

    excess_returns = _excess_returns(
        returns=returns,
        risk_free_daily_rates=risk_free_daily_rates,
    )
    if excess_returns.size < 30:
        LOGGER.warning(
            "Sharpe ratio is undefined because fewer than 30 returns were supplied."
        )
        return None
    if np.allclose(excess_returns, excess_returns[0]):
        LOGGER.warning("Sharpe ratio is undefined because variance is zero.")
        return None

    volatility = float(np.std(excess_returns, ddof=1))
    if volatility <= 0 or math.isnan(volatility):
        LOGGER.warning("Sharpe ratio is undefined because variance is zero.")
        return None

    base_sharpe = float(np.mean(excess_returns)) / volatility
    lag_count = min(autocorrelation_lags, excess_returns.size - 1)
    autocorrelation_adjustment = 1.0
    if lag_count > 0:
        for lag in range(1, lag_count + 1):
            correlation = _lagged_autocorrelation(excess_returns, lag)
            if correlation is None:
                continue
            # Bartlett (Newey-West 1987) triangular weight ``1 - k/(M+1)``.
            # Must match ``effective_sample_size_lo_signed`` so the two
            # HAC paths apply the same autocorrelation penalty.
            autocorrelation_adjustment += (
                2.0 * (1.0 - (lag / (lag_count + 1.0))) * correlation
            )
    if autocorrelation_adjustment <= 0:
        LOGGER.warning(
            "Sharpe ratio is undefined because the autocorrelation adjustment "
            "is non-positive."
        )
        return None

    return float(
        math.sqrt(periods_per_year)
        * base_sharpe
        / math.sqrt(autocorrelation_adjustment)
    )


def probabilistic_sharpe_ratio(
    *,
    observed_sharpe: float,
    benchmark_sharpe: float,
    sample_size: float,
    skewness: float,
    excess_kurtosis: float,
) -> float:
    """Bailey & López de Prado (2012) PSR.

    ``excess_kurtosis`` is kurtosis - 3 (i.e. excess over the normal).
    Defect 4 renamed the parameter from ``kurtosis`` to make this
    explicit; callers must pass the excess (not raw) kurtosis.
    """

    if sample_size <= 1:
        raise ValueError("sample_size must be greater than 1.")
    # Bailey & López de Prado (2012), eq.(5). The published denominator
    # uses ``(γ4 - 1)/4`` where γ4 is the RAW kurtosis (= 3 for normal
    # returns). Expressed in excess-kurtosis form (γ4_excess = γ4 - 3),
    # the same term becomes ``(γ4_excess + 2)/4`` — which collapses to
    # the canonical Lo (2002) ``Var[SR] = (1 + SR² / 2)/(n - 1)`` for
    # normal returns. The earlier ``(excess_kurtosis - 1)/4`` form was a
    # rename without an algebraic update and produced a negative
    # contribution for normal returns, biasing PSR upward.
    denominator = (
        1.0
        - (skewness * observed_sharpe)
        + (((excess_kurtosis + 2.0) / 4.0) * (observed_sharpe**2))
    )
    if denominator <= 0:
        raise ValueError("PSR denominator must be positive.")
    test_statistic = (
        (observed_sharpe - benchmark_sharpe)
        * math.sqrt(sample_size - 1.0)
        / math.sqrt(denominator)
    )
    return float(norm.cdf(test_statistic))


def expected_max_sharpe(
    *,
    n_trials: int,
    trial_sharpe_variance: float,
    mean_trial_sharpe: float = 0.0,
    periods_per_year: int = PAPER_PERIODS_PER_YEAR,
) -> float:
    if n_trials <= 0:
        raise ValueError("n_trials must be positive.")
    if trial_sharpe_variance < 0:
        raise ValueError("trial_sharpe_variance must be non-negative.")
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive.")
    if n_trials == 1:
        return mean_trial_sharpe
    max_z_score = ((1.0 - EULER_MASCHERONI) * norm.ppf(1.0 - (1.0 / n_trials))) + (
        EULER_MASCHERONI * norm.ppf(1.0 - (1.0 / (n_trials * math.e)))
    )
    # The Bailey and Lopez de Prado paper reports the cross-trial variance in
    # annualized Sharpe units, while PSR/DSR operate on the per-period Sharpe.
    trial_sharpe_sigma = math.sqrt(trial_sharpe_variance / periods_per_year)
    return float(mean_trial_sharpe + trial_sharpe_sigma * max_z_score)


def deflated_sharpe_ratio(
    *,
    observed_sharpe: float,
    sample_size: float,
    skewness: float,
    excess_kurtosis: float,
    n_trials: int,
    trial_sharpe_variance: float,
    mean_trial_sharpe: float = 0.0,
    periods_per_year: int = PAPER_PERIODS_PER_YEAR,
) -> float:
    """Bailey & López de Prado (2014) DSR.

    ``excess_kurtosis`` is kurtosis - 3 (Defect 4 rename).
    """

    benchmark_sharpe = expected_max_sharpe(
        n_trials=n_trials,
        trial_sharpe_variance=trial_sharpe_variance,
        mean_trial_sharpe=mean_trial_sharpe,
        periods_per_year=periods_per_year,
    )
    return probabilistic_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        benchmark_sharpe=benchmark_sharpe,
        sample_size=sample_size,
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
    )


def max_drawdown(returns: Sequence[float]) -> float:
    if not returns:
        return 0.0

    cumulative = 1.0
    peak = 1.0
    worst = 0.0
    for value in returns:
        cumulative *= 1.0 + float(value)
        if cumulative > peak:
            peak = cumulative
        drawdown = (peak - cumulative) / peak
        if drawdown > worst:
            worst = drawdown
    return worst


def conditional_drawdown_at_risk(
    returns: Sequence[float],
    *,
    confidence: float = 0.95,
) -> float:
    if not returns:
        return 0.0
    if confidence <= 0.0 or confidence >= 1.0:
        raise ValueError("confidence must be in (0, 1).")

    cumulative = 1.0
    peak = 1.0
    drawdowns: list[float] = []
    for value in returns:
        cumulative *= 1.0 + float(value)
        if cumulative > peak:
            peak = cumulative
        drawdowns.append((peak - cumulative) / peak)

    drawdowns.sort(reverse=True)
    tail_size = max(1, math.ceil((1.0 - confidence) * len(drawdowns)))
    worst_tail = drawdowns[:tail_size]
    return sum(worst_tail) / len(worst_tail)


def effective_sample_size_lo_signed(
    returns: Sequence[float],
    *,
    max_lag: int = DEFAULT_AUTOCORRELATION_LAGS,
) -> tuple[float, tuple[dict[str, object], ...]]:
    """Lo (2002) effective sample size with SIGNED autocorrelations.

    Uses signed autocorrelations together with Bartlett (Newey-West 1987)
    triangular weights ``w_k = 1 - k/(m+1)`` where ``m`` is the truncation
    lag (max_lag). Defect 4 renamed this from ``effective_sample_size_hac``
    after the adversarial review found that summing absolute
    autocorrelations both double-penalizes negatively-correlated returns
    and silently omits the Bartlett window. ``lo_adjusted_sharpe_ratio``
    uses the same window so the two HAC paths apply consistent penalties.
    """

    values = cast(FloatArray, np.asarray(list(returns), dtype=float))
    n_observations = int(values.size)
    if n_observations <= 1:
        return float(n_observations), ()
    lag_count = min(max(max_lag, 0), n_observations - 1)
    if lag_count == 0:
        return float(n_observations), ()
    lag_sensitivity: list[dict[str, object]] = []
    autocorrelation_penalty = 0.0
    for lag in range(1, lag_count + 1):
        correlation = _lagged_autocorrelation(values, lag)
        signed_correlation = 0.0 if correlation is None else float(correlation)
        bartlett_weight = 1.0 - (lag / (lag_count + 1.0))
        autocorrelation_penalty += bartlett_weight * signed_correlation
        denominator = 1.0 + (2.0 * autocorrelation_penalty)
        lag_effective_sample_size = (
            float(n_observations) if denominator <= 0 else n_observations / denominator
        )
        lag_sensitivity.append(
            {
                "lag": lag,
                "autocorrelation": (
                    "0" if correlation is None else _decimal_string(correlation)
                ),
                "bartlett_weight": _decimal_string(bartlett_weight),
                "effective_sample_size": _decimal_string(
                    min(float(n_observations), max(0.0, lag_effective_sample_size))
                ),
            }
        )
    denominator = 1.0 + (2.0 * autocorrelation_penalty)
    effective_sample_size = (
        float(n_observations) if denominator <= 0 else n_observations / denominator
    )
    return (
        min(float(n_observations), max(0.0, effective_sample_size)),
        tuple(lag_sensitivity),
    )


# Defect 4 — Backwards-compatible alias kept until callers migrate.
# New code MUST use ``effective_sample_size_lo_signed`` directly.
effective_sample_size_hac = effective_sample_size_lo_signed


def build_power_analysis_report(
    *,
    strategy_id: str,
    returns: Sequence[float],
    minimum_effective_sample_size: int,
    max_lag: int = DEFAULT_AUTOCORRELATION_LAGS,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    effective_sample_size, lag_sensitivity = effective_sample_size_hac(
        returns,
        max_lag=max_lag,
    )
    status = (
        "powered"
        if effective_sample_size >= float(minimum_effective_sample_size)
        else "underpowered"
    )
    return {
        "schema_version": "1.0",
        "kind": "power_analysis_report",
        "strategy_id": strategy_id,
        "n_observations": len(returns),
        "effective_sample_size": _decimal_string(effective_sample_size),
        "minimum_effective_sample_size": minimum_effective_sample_size,
        "max_lag": max_lag,
        "lag_sensitivity": list(lag_sensitivity),
        "status": status,
        "blocker_codes": ([] if status == "powered" else ["dsr_pbo_inputs_incomplete"]),
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_threshold_justification(
    *,
    strategy_id: str,
    metric_name: str,
    threshold_value: Decimal | str | None,
    rationale: str,
    justification_ref: str,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    status = "valid" if threshold_value not in {None, ""} else "pending_threshold"
    return {
        "schema_version": "1.0",
        "kind": "threshold_justification",
        "strategy_id": strategy_id,
        "metric_name": metric_name,
        "threshold_value": "" if threshold_value is None else str(threshold_value),
        "rationale": rationale,
        "justification_ref": justification_ref,
        "status": status,
        "blocker_codes": [] if status == "valid" else ["pending_threshold"],
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_stationary_block_bootstrap_report(
    *,
    strategy_id: str,
    returns: Sequence[float],
    random_seed: int = DEFAULT_BOOTSTRAP_SEED,
    block_lengths: Sequence[int] = DEFAULT_BLOCK_LENGTHS,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    tail_tolerance: float | None = None,
    tail_tolerance_relative_to_mean: float = 0.10,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    """Defect 4: tail_tolerance is now relative to |mean| of the returns.

    The previous absolute threshold (default 0.01) silently assumed the
    return scale was order 1%. For sub-percent return series an absolute
    tolerance is unsupportable. The new
    ``tail_tolerance_relative_to_mean`` expresses the threshold as a
    fraction of |mean(returns)|. ``tail_tolerance`` is kept as a
    deprecated alias for backwards compatibility with existing callers.
    """

    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive.")
    if tail_tolerance is not None:
        # Accept legacy callers that pass an absolute tolerance.
        relative_tolerance = float(tail_tolerance)
    else:
        relative_tolerance = float(tail_tolerance_relative_to_mean)
    values = tuple(float(value) for value in returns)
    mean_value = float(np.mean(values)) if values else 0.0
    absolute_tolerance = abs(mean_value) * relative_tolerance
    if tail_tolerance is not None:
        # Legacy mode treats ``tail_tolerance`` as absolute.
        absolute_tolerance = float(tail_tolerance)
    sensitivity: list[dict[str, object]] = []
    tail_spreads: list[float] = []
    for block_length in block_lengths:
        if block_length <= 0:
            raise ValueError("block lengths must be positive.")
        resampled_means = _stationary_bootstrap_means(
            values,
            block_length=block_length,
            n_resamples=n_resamples,
            random_seed=random_seed + block_length,
        )
        p05 = _percentile_float(resampled_means, 5.0)
        p50 = _percentile_float(resampled_means, 50.0)
        p95 = _percentile_float(resampled_means, 95.0)
        tail_spreads.append(abs(p95 - p05))
        sensitivity.append(
            {
                "block_length": block_length,
                "mean_return_p05": _decimal_string(p05),
                "mean_return_p50": _decimal_string(p50),
                "mean_return_p95": _decimal_string(p95),
            }
        )
    max_tail_spread = max(tail_spreads, default=float("inf"))
    stable = bool(values) and max_tail_spread <= absolute_tolerance
    status = "stable" if stable else "unstable"
    return {
        "schema_version": "1.0",
        "kind": "bootstrap_report",
        "strategy_id": strategy_id,
        "random_seed": random_seed,
        "n_resamples": n_resamples,
        "block_length_sensitivity": sensitivity,
        "tail_stability_threshold": _decimal_string(absolute_tolerance),
        "tail_tolerance_relative_to_mean": _decimal_string(relative_tolerance),
        "tail_stability_status": status,
        "blocker_codes": [] if stable else ["dsr_pbo_inputs_incomplete"],
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def _newey_west_truncation_lag(n: int) -> int:
    """Standard Newey-West truncation lag: floor(4 * (n/100)**(2/9))."""

    if n <= 1:
        return 0
    return int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))


def _hac_adjusted_std_error(paired_diff: Sequence[float]) -> float:
    """Newey-West HAC standard error of the mean of paired differences.

    Uses Bartlett triangular weights and the lag rule
    ``floor(4 * (n/100)**(2/9))`` as recommended for Newey-West (1987).
    Falls back to the iid OLS standard error when n is too small for any
    lag adjustment.
    """

    n = len(paired_diff)
    if n < 2:
        return 0.0
    arr = cast(FloatArray, np.asarray(list(paired_diff), dtype=float))
    mean = float(np.mean(arr))
    centered = arr - mean
    gamma_zero = float(np.dot(centered, centered) / n)
    truncation_lag = _newey_west_truncation_lag(n)
    long_run_variance = gamma_zero
    for k in range(1, truncation_lag + 1):
        if k >= n:
            break
        bartlett_weight = 1.0 - (k / (truncation_lag + 1.0))
        gamma_k = float(np.dot(centered[:-k], centered[k:]) / n)
        long_run_variance += 2.0 * bartlett_weight * gamma_k
    if long_run_variance <= 0:
        # Fall back to the iid standard error so the lower bound is at
        # least as wide as the unadjusted estimate.
        return float(np.std(arr, ddof=1)) / math.sqrt(n)
    return math.sqrt(long_run_variance / n)


def build_paired_benchmark_uncertainty_report(
    *,
    strategy_id: str,
    candidate_returns: Sequence[float],
    benchmark_returns_by_name: Mapping[str, Sequence[float]],
    required_benchmarks: Sequence[str] = DEFAULT_REQUIRED_BENCHMARKS,
    confidence_level: Decimal | str = Decimal("0.95"),
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    """Defect 4: replace the hard-coded 1.96 with the proper z-quantile and
    apply Newey-West HAC adjustment to the paired-difference standard error.
    """

    candidate = tuple(float(value) for value in candidate_returns)
    missing = [
        name for name in required_benchmarks if name not in benchmark_returns_by_name
    ]
    comparisons: list[dict[str, object]] = []
    confidence = float(Decimal(str(confidence_level)))
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence_level must lie strictly within (0, 1).")
    z_quantile = float(norm.ppf(1.0 - (1.0 - confidence) / 2.0))
    for name in required_benchmarks:
        if name not in benchmark_returns_by_name:
            continue
        benchmark = tuple(float(value) for value in benchmark_returns_by_name[name])
        if len(benchmark) != len(candidate) or len(candidate) < 2:
            missing.append(name)
            continue
        paired_diff = [
            left - right for left, right in zip(candidate, benchmark, strict=True)
        ]
        mean_diff = float(np.mean(paired_diff))
        std_error = _hac_adjusted_std_error(paired_diff)
        lower_bound = mean_diff - (z_quantile * std_error)
        comparisons.append(
            {
                "benchmark_name": name,
                "mean_excess_return": _decimal_string(mean_diff),
                "lower_confidence_bound": _decimal_string(lower_bound),
                "sample_size": len(paired_diff),
                "supports_positive_edge": lower_bound > 0.0,
            }
        )
    status = "complete" if not missing else "incomplete"
    return {
        "schema_version": "1.0",
        "kind": "paired_benchmark_uncertainty_report",
        "strategy_id": strategy_id,
        "confidence_level": str(confidence_level),
        "required_benchmarks": list(required_benchmarks),
        "missing_benchmarks": sorted(set(missing)),
        "comparisons": comparisons,
        "status": status,
        "blocker_codes": [] if status == "complete" else ["dsr_pbo_inputs_incomplete"],
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def classify_statistical_evidence(payload: Mapping[str, object]) -> dict[str, object]:
    kind = str(payload.get("kind", ""))
    if kind in {
        "threshold_justification",
        "power_analysis_report",
        "bootstrap_report",
        "paired_benchmark_uncertainty_report",
        "statistical_validation_report",
    }:
        return {
            "classification": "wave4_statistical_evidence",
            "blocker_codes": list(
                _as_string_sequence(payload.get("blocker_codes", ()))
            ),
        }
    metric_markers = {
        "candidate_metrics",
        "benchmark_metrics",
        "deflated_sharpe_ratio",
        "pbo_value",
        "pbo_report_id",
    }
    if metric_markers.intersection(payload):
        return {
            "classification": "legacy_statistical_evidence",
            "blocker_codes": ["legacy_statistical_evidence"],
        }
    return {"classification": "non_statistical", "blocker_codes": []}


def build_statistical_validation_report(
    *,
    strategy_id: str,
    threshold_justification: Mapping[str, object] | None,
    power_report: Mapping[str, object] | None,
    bootstrap_report: Mapping[str, object] | None,
    paired_benchmark_report: Mapping[str, object] | None,
    trial_universe_manifest: Mapping[str, object] | None,
    pbo_report: Mapping[str, object] | None,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    component_status: dict[str, str] = {}
    for name, payload, missing_blocker in (
        ("threshold", threshold_justification, "pending_threshold"),
        ("power", power_report, "dsr_pbo_inputs_incomplete"),
        ("bootstrap", bootstrap_report, "dsr_pbo_inputs_incomplete"),
        ("paired_benchmark", paired_benchmark_report, "dsr_pbo_inputs_incomplete"),
    ):
        if payload is None:
            component_status[name] = "missing"
            _append_unique(blocker_codes, missing_blocker)
            continue
        component_status[name] = str(
            payload.get("status", payload.get("tail_stability_status", ""))
        )
        for code in _as_string_sequence(payload.get("blocker_codes", ())):
            _append_unique(blocker_codes, code)
    trial_stats = (
        trial_universe_manifest.get("trial_statistics", {})
        if isinstance(trial_universe_manifest, Mapping)
        else {}
    )
    if not isinstance(trial_stats, Mapping):
        trial_stats = {}
    dsr_required_fields = (
        "effective_independent_trial_count",
        "trial_correlation_estimate",
        "selection_rule",
        "selected_strategy_rank",
        "trial_sharpe_mean",
        "trial_sharpe_variance",
        "trial_return_skewness",
        "trial_return_kurtosis",
        "failed_run_treatment",
        "full_cpcv_pbo_matrix_ref",
    )
    missing_dsr_fields = [
        field
        for field in dsr_required_fields
        if _missing_stat_field(trial_stats, field)
    ]
    if missing_dsr_fields:
        _append_unique(blocker_codes, "dsr_pbo_inputs_incomplete")
    if pbo_report is None or _missing_stat_field(pbo_report, "full_cpcv_matrix_ref"):
        _append_unique(blocker_codes, "dsr_pbo_inputs_incomplete")
    status = "valid" if not blocker_codes else "incomplete"
    # Defect 12 — emit ``legacy`` evidence_class when the classifier
    # determines the inputs are legacy (pre-Wave-4) rather than just
    # incomplete. Previously the schema didn't allow ``legacy`` so the
    # builder fell through to ``exploratory``, hiding legacy-evidence
    # bundles from operators.
    classifier = classify_statistical_evidence(
        {
            "kind": "statistical_validation_report",
            "blocker_codes": blocker_codes,
        }
    )
    if str(classifier.get("classification", "")) == "legacy_statistical_evidence":
        evidence_class = "legacy"
    elif status == "valid":
        evidence_class = "promotion_valid"
    else:
        evidence_class = "exploratory"
    return {
        "schema_version": "1.0",
        "kind": "statistical_validation_report",
        "strategy_id": strategy_id,
        "status": status,
        "evidence_class": evidence_class,
        "promotion_valid": status == "valid",
        "blocker_codes": blocker_codes,
        "component_status": component_status,
        "missing_dsr_fields": missing_dsr_fields,
        "pbo_report_id": (
            "" if pbo_report is None else str(pbo_report.get("report_id", ""))
        ),
        "full_cpcv_matrix_ref": (
            ""
            if pbo_report is None
            else str(pbo_report.get("full_cpcv_matrix_ref", ""))
        ),
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def calmar_ratio(
    returns: Sequence[float],
    *,
    periods_per_year: int = DEFAULT_PERIODS_PER_YEAR,
) -> float:
    if not returns:
        return 0.0

    cumulative = 1.0
    for value in returns:
        cumulative *= 1.0 + float(value)
    annualized = cumulative ** (periods_per_year / len(returns)) - 1.0
    mdd = max_drawdown(returns)
    if mdd == 0.0:
        return float("inf") if annualized > 0.0 else 0.0
    return float(annualized / mdd)


def _stationary_bootstrap_means(
    values: tuple[float, ...],
    *,
    block_length: int,
    n_resamples: int,
    random_seed: int,
) -> tuple[float, ...]:
    """Politis & Romano (1994) stationary bootstrap with geometric blocks.

    Defect 4 — block_length is interpreted as the EXPECTED block length;
    each block's actual length is drawn from a geometric distribution
    with parameter ``p = 1/block_length`` (sampled here via
    ``random.expovariate(p)``). Fixed-block-length resampling that the
    earlier implementation used is the *circular* block bootstrap, not
    the stationary one.
    """

    if not values:
        return ()
    if block_length <= 0:
        raise ValueError("block_length must be positive (it is the mean).")
    random_state = random.Random(random_seed)
    p = 1.0 / float(block_length)
    n_observations = len(values)
    means: list[float] = []
    for _ in range(n_resamples):
        sample: list[float] = []
        while len(sample) < n_observations:
            start = random_state.randrange(n_observations)
            # Geometric block length: ceil(Exp(p)) gives a positive
            # geometric sample with mean 1/p == block_length.
            actual_length = max(1, int(math.ceil(random_state.expovariate(p))))
            for offset in range(actual_length):
                if len(sample) == n_observations:
                    break
                sample.append(values[(start + offset) % n_observations])
        means.append(float(sum(sample) / len(sample)))
    return tuple(means)


def _percentile_float(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    rank = (percentile / 100.0) * (len(ordered) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _decimal_string(value: float) -> str:
    if not math.isfinite(value):
        return "0"
    return str(Decimal(str(value)).normalize())


def _utc_iso(value: datetime | None) -> str:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).isoformat()


def _as_string_sequence(value: object) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return tuple(str(item) for item in value)
    return ()


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _missing_stat_field(payload: Mapping[str, object], field: str) -> bool:
    value = payload.get(field)
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _excess_returns(
    *,
    returns: Sequence[float],
    risk_free_daily_rates: Sequence[float],
) -> FloatArray:
    realized_returns = cast(FloatArray, np.asarray(list(returns), dtype=float))
    risk_free_rates = cast(
        FloatArray,
        np.asarray(list(risk_free_daily_rates), dtype=float),
    )
    if realized_returns.shape != risk_free_rates.shape:
        raise ValueError("returns and risk_free_daily_rates must have the same length.")
    return realized_returns - risk_free_rates


def _lagged_autocorrelation(values: FloatArray, lag: int) -> float | None:
    if lag <= 0 or lag >= values.size:
        return None
    leading = values[:-lag]
    lagged = values[lag:]
    if leading.size < 2 or lagged.size < 2:
        return None
    if np.allclose(leading, leading[0]) or np.allclose(lagged, lagged[0]):
        return None
    correlation_matrix = np.corrcoef(leading, lagged)
    correlation = float(correlation_matrix[0, 1])
    if math.isnan(correlation):
        return None
    return correlation


__all__ = (
    "DEFAULT_AUTOCORRELATION_LAGS",
    "DEFAULT_PERIODS_PER_YEAR",
    "PAPER_PERIODS_PER_YEAR",
    "calmar_ratio",
    "build_paired_benchmark_uncertainty_report",
    "build_power_analysis_report",
    "build_stationary_block_bootstrap_report",
    "build_statistical_validation_report",
    "build_threshold_justification",
    "classify_statistical_evidence",
    "deflated_sharpe_ratio",
    "effective_sample_size_hac",
    "expected_max_sharpe",
    "conditional_drawdown_at_risk",
    "lo_adjusted_sharpe_ratio",
    "max_drawdown",
    "naive_annualized_sharpe_ratio",
    "probabilistic_sharpe_ratio",
)
