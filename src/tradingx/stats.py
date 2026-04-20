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
from collections.abc import Sequence
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
    excess_returns = _excess_returns(
        returns=returns,
        risk_free_daily_rates=risk_free_daily_rates,
    )
    if excess_returns.size < 30:
        LOGGER.warning(
            "Sharpe ratio is undefined because fewer than 30 returns were supplied."
        )
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
            autocorrelation_adjustment += 2.0 * (1.0 - (lag / lag_count)) * correlation
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
    kurtosis: float,
) -> float:
    if sample_size <= 1:
        raise ValueError("sample_size must be greater than 1.")
    denominator = (
        1.0
        - (skewness * observed_sharpe)
        + (((kurtosis - 1.0) / 4.0) * (observed_sharpe**2))
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
    kurtosis: float,
    n_trials: int,
    trial_sharpe_variance: float,
    mean_trial_sharpe: float = 0.0,
    periods_per_year: int = PAPER_PERIODS_PER_YEAR,
) -> float:
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
        kurtosis=kurtosis,
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
    return annualized / mdd


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
    "deflated_sharpe_ratio",
    "expected_max_sharpe",
    "conditional_drawdown_at_risk",
    "lo_adjusted_sharpe_ratio",
    "max_drawdown",
    "naive_annualized_sharpe_ratio",
    "probabilistic_sharpe_ratio",
)
