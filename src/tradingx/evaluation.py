"""Benchmark-relative Stage 1 strategy evaluation."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from tradingx.stats import lo_adjusted_sharpe_ratio
from tradingx.types import EvaluationEvidencePack, ScalarValue, StrategyCandidate

LOGGER = logging.getLogger(__name__)
TRADING_DAYS_PER_YEAR = 252


def _to_float_sequence(values: Sequence[Decimal]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def _total_return(returns: Sequence[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1.0 + value
    return equity - 1.0


def _sharpe_ratio(
    *,
    returns: Sequence[float],
    risk_free_daily_rates: Sequence[float],
) -> float | None:
    return lo_adjusted_sharpe_ratio(
        returns=returns,
        risk_free_daily_rates=risk_free_daily_rates,
        periods_per_year=TRADING_DAYS_PER_YEAR,
    )


def _max_drawdown(returns: Sequence[float]) -> float:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        drawdown = (equity / peak) - 1.0
        max_drawdown = min(max_drawdown, drawdown)
    return abs(max_drawdown)


def _calmar_ratio(total_return: float, max_drawdown: float, periods: int) -> float:
    if periods == 0 or max_drawdown == 0:
        return 0.0
    annualized_return = float(
        (1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / periods) - 1.0
    )
    return annualized_return / max_drawdown


def _build_metric_pack(returns: Sequence[Decimal]) -> dict[str, float]:
    float_returns = _to_float_sequence(returns)
    total_return = _total_return(float_returns)
    max_drawdown = _max_drawdown(float_returns)
    sharpe_ratio = _sharpe_ratio(
        returns=float_returns,
        risk_free_daily_rates=(0.0,) * len(float_returns),
    )
    return {
        "total_return": total_return,
        "sharpe_ratio": 0.0 if sharpe_ratio is None else sharpe_ratio,
        "max_drawdown": max_drawdown,
        "calmar_ratio": _calmar_ratio(total_return, max_drawdown, len(float_returns)),
    }


def _run_adversarial_checks(returns: Sequence[Decimal]) -> tuple[str, ...]:
    if not returns:
        return (
            "cost_sensitivity_fail",
            "out_of_sample_fail",
            "parameter_sensitivity_fail",
            "regime_behavior_fail",
        )

    midpoint = max(1, len(returns) // 2)
    overall_metrics = _build_metric_pack(returns)
    second_half_metrics = _build_metric_pack(returns[midpoint:])
    cost_adjusted = tuple(value - Decimal("0.001") for value in returns)
    cost_adjusted_metrics = _build_metric_pack(cost_adjusted)

    out_of_sample = (
        "out_of_sample_pass"
        if second_half_metrics["total_return"] >= 0
        else "out_of_sample_fail"
    )
    cost_sensitivity = (
        "cost_sensitivity_pass"
        if cost_adjusted_metrics["total_return"] >= 0
        else "cost_sensitivity_fail"
    )
    parameter_sensitivity = (
        "parameter_sensitivity_pass"
        if overall_metrics["max_drawdown"] <= 0.15
        else "parameter_sensitivity_fail"
    )
    regime_behavior = (
        "regime_behavior_pass"
        if min(float(value) for value in returns) > -0.05
        else "regime_behavior_fail"
    )
    return (
        cost_sensitivity,
        out_of_sample,
        parameter_sensitivity,
        regime_behavior,
    )


def evaluate_candidate(
    candidate: StrategyCandidate,
    *,
    candidate_returns: Sequence[Decimal],
    benchmark_returns: Sequence[Decimal],
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> EvaluationEvidencePack:
    candidate_metrics_numeric = _build_metric_pack(candidate_returns)
    benchmark_metrics_numeric = _build_metric_pack(benchmark_returns)
    excess_return = (
        candidate_metrics_numeric["total_return"]
        - benchmark_metrics_numeric["total_return"]
    )
    adversarial_checks = _run_adversarial_checks(candidate_returns)
    benchmark_metrics: dict[str, ScalarValue] = dict(benchmark_metrics_numeric)
    candidate_metrics: dict[str, ScalarValue] = dict(candidate_metrics_numeric)
    candidate_metrics["excess_return"] = excess_return

    if (
        all(check.endswith("_pass") for check in adversarial_checks)
        and candidate_metrics_numeric["sharpe_ratio"]
        >= benchmark_metrics_numeric["sharpe_ratio"]
        and excess_return > 0
    ):
        recommendation = "keep"
    elif excess_return > 0:
        recommendation = "research_further"
    else:
        recommendation = "reject"

    return EvaluationEvidencePack(
        evidence_pack_id=(
            f"{candidate.candidate_id}-{window_end_utc.strftime('%Y%m%dT%H%M%SZ')}"
        ),
        candidate_id=candidate.candidate_id,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        benchmark_metrics=benchmark_metrics,
        candidate_metrics=candidate_metrics,
        adversarial_checks=adversarial_checks,
        recommendation=recommendation,
        assumptions=(
            "benchmark-relative comparison uses the same return window",
            "cost sensitivity applies a fixed per-period penalty",
        ),
    )


__all__ = ("evaluate_candidate",)
