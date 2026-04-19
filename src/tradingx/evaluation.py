"""Benchmark-relative Stage 1 strategy evaluation."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.costs import CostModelConfig
from tradingx.stats import lo_adjusted_sharpe_ratio
from tradingx.types import EvaluationEvidencePack, ScalarValue, StrategyCandidate

LOGGER = logging.getLogger(__name__)
TRADING_DAYS_PER_YEAR = 252
OOS_DAYS = 756
MIN_IN_SAMPLE_DAYS = 252
PROFILE_TOLERANCE = 0.30
PROFILE_TOLERANCE_FLOOR = 0.3
REGIME_VOL_WINDOW_DAYS = 60
REGIME_TREND_WINDOW_DAYS = 200


BacktestRunner = Callable[..., tuple[Decimal, ...]]


@dataclass(frozen=True)
class AdversarialCheckContext:
    benchmark_bars: pd.DataFrame
    backtest_runner: BacktestRunner
    base_cost_model_config: CostModelConfig


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


def _cagr(total_return: float, periods: int) -> float:
    if periods <= 0:
        return 0.0
    return float((1.0 + total_return) ** (TRADING_DAYS_PER_YEAR / periods) - 1.0)


def _metric_triplet(returns: Sequence[Decimal]) -> tuple[float | None, float, float]:
    float_returns = _to_float_sequence(returns)
    sharpe_ratio = _sharpe_ratio(
        returns=float_returns,
        risk_free_daily_rates=(0.0,) * len(float_returns),
    )
    total_return = _total_return(float_returns)
    return (
        sharpe_ratio,
        _cagr(total_return, len(float_returns)),
        _max_drawdown(float_returns),
    )


def _within_tolerance(reference: float, observed: float) -> bool:
    return (
        abs(observed - reference) / max(abs(reference), PROFILE_TOLERANCE_FLOOR)
        <= PROFILE_TOLERANCE
    )


def _oos_check(returns: Sequence[Decimal]) -> str:
    if len(returns) < MIN_IN_SAMPLE_DAYS + OOS_DAYS:
        return "out_of_sample_fail"

    in_sample_returns = tuple(returns[:-OOS_DAYS])
    out_of_sample_returns = tuple(returns[-OOS_DAYS:])
    sharpe_is, cagr_is, maxdd_is = _metric_triplet(in_sample_returns)
    sharpe_oos, cagr_oos, maxdd_oos = _metric_triplet(out_of_sample_returns)
    if sharpe_is is None or sharpe_oos is None:
        return "out_of_sample_fail"
    if not _within_tolerance(sharpe_is, sharpe_oos):
        return "out_of_sample_fail"
    if not _within_tolerance(cagr_is, cagr_oos):
        return "out_of_sample_fail"
    if not _within_tolerance(maxdd_is, maxdd_oos):
        return "out_of_sample_fail"
    return "out_of_sample_pass"


def _perturb_value(value: ScalarValue, factor: float) -> ScalarValue | None:
    if isinstance(value, Decimal):
        return Decimal(str(max(float(value) * factor, 0.0)))
    if isinstance(value, int):
        return max(int(round(value * factor)), 1)
    if isinstance(value, float):
        return max(value * factor, 0.0)
    return None


def _parameter_sensitivity_check(
    candidate: StrategyCandidate,
    *,
    backtest_runner: BacktestRunner,
    base_returns: Sequence[Decimal],
) -> str:
    base_sharpe = _sharpe_ratio(
        returns=_to_float_sequence(base_returns),
        risk_free_daily_rates=(0.0,) * len(base_returns),
    )
    if base_sharpe is None or base_sharpe <= 0.0:
        return "parameter_sensitivity_fail"

    worst_degradation = 0.0
    numeric_parameters = {
        key: value
        for key, value in candidate.parameter_set.items()
        if isinstance(value, (Decimal, float, int))
    }
    if not numeric_parameters:
        return "parameter_sensitivity_fail"

    for key, value in numeric_parameters.items():
        for factor in (0.6, 0.8, 1.2, 1.4):
            perturbed_value = _perturb_value(value, factor)
            if perturbed_value is None:
                continue
            perturbed_returns = backtest_runner(
                candidate,
                parameter_overrides={key: perturbed_value},
            )
            perturbed_sharpe = _sharpe_ratio(
                returns=_to_float_sequence(perturbed_returns),
                risk_free_daily_rates=(0.0,) * len(perturbed_returns),
            )
            if perturbed_sharpe is None:
                return "parameter_sensitivity_fail"
            degradation = max(0.0, (base_sharpe - perturbed_sharpe) / abs(base_sharpe))
            worst_degradation = max(worst_degradation, degradation)
    return (
        "parameter_sensitivity_pass"
        if worst_degradation <= 0.30
        else "parameter_sensitivity_fail"
    )


def _regime_behavior_check(
    candidate_returns: Sequence[Decimal],
    *,
    benchmark_bars: pd.DataFrame,
) -> str:
    candidate_return_series = pd.Series(
        _to_float_sequence(candidate_returns),
        index=benchmark_bars.index,
        dtype=float,
    )
    overall_sharpe = _sharpe_ratio(
        returns=candidate_return_series.tolist(),
        risk_free_daily_rates=[0.0] * len(candidate_return_series),
    )
    if overall_sharpe is None or overall_sharpe <= 0.0:
        return "regime_behavior_fail"

    benchmark_closes = benchmark_bars["close"].astype(float)
    trailing_vol = (
        benchmark_closes.pct_change()
        .shift(1)
        .rolling(REGIME_VOL_WINDOW_DAYS)
        .std(ddof=1)
    )
    valid_vol = trailing_vol.dropna()
    if valid_vol.empty:
        return "regime_behavior_fail"

    vol_bucket = pd.qcut(
        valid_vol.rank(method="first"),
        3,
        labels=("low", "mid", "high"),
    )
    trend_up = benchmark_closes.shift(1) > benchmark_closes.shift(
        REGIME_TREND_WINDOW_DAYS
    )
    valid_index = vol_bucket.index.intersection(trend_up.dropna().index)
    if valid_index.empty:
        return "regime_behavior_fail"

    regime_frame = pd.DataFrame(index=valid_index)
    regime_frame["returns"] = candidate_return_series.reindex(valid_index)
    regime_frame["vol_bucket"] = vol_bucket.reindex(valid_index)
    regime_frame["trend_bucket"] = trend_up.reindex(valid_index).map(
        lambda value: "up" if bool(value) else "down"
    )
    regime_frame["regime"] = (
        regime_frame["vol_bucket"].astype(str)
        + "_"
        + regime_frame["trend_bucket"].astype(str)
    )

    for _, regime_returns in regime_frame.groupby("regime")["returns"]:
        if len(regime_returns) < 30:
            continue
        regime_sharpe = _sharpe_ratio(
            returns=regime_returns.tolist(),
            risk_free_daily_rates=[0.0] * len(regime_returns),
        )
        if regime_sharpe is None or regime_sharpe < 0.0:
            return "regime_behavior_fail"
        if regime_sharpe < (overall_sharpe * 0.7):
            return "regime_behavior_fail"
    return "regime_behavior_pass"


def _cost_sensitivity_check(
    candidate: StrategyCandidate,
    *,
    backtest_runner: BacktestRunner,
    base_cost_model_config: CostModelConfig,
) -> str:
    stress_configs = (
        CostModelConfig(
            half_spread_multiplier=base_cost_model_config.half_spread_multiplier * 2.0,
            impact_coefficient=base_cost_model_config.impact_coefficient * 2.0,
            commission_per_share=base_cost_model_config.commission_per_share * 2.0,
            sec_fee_per_dollar=base_cost_model_config.sec_fee_per_dollar,
            finra_taf_per_share=base_cost_model_config.finra_taf_per_share,
            finra_taf_max_per_trade=base_cost_model_config.finra_taf_max_per_trade,
        ),
        CostModelConfig(
            half_spread_multiplier=base_cost_model_config.half_spread_multiplier * 2.0,
            impact_coefficient=base_cost_model_config.impact_coefficient,
            commission_per_share=base_cost_model_config.commission_per_share,
            sec_fee_per_dollar=base_cost_model_config.sec_fee_per_dollar,
            finra_taf_per_share=base_cost_model_config.finra_taf_per_share,
            finra_taf_max_per_trade=base_cost_model_config.finra_taf_max_per_trade,
        ),
        CostModelConfig(
            half_spread_multiplier=base_cost_model_config.half_spread_multiplier,
            impact_coefficient=base_cost_model_config.impact_coefficient * 2.0,
            commission_per_share=base_cost_model_config.commission_per_share,
            sec_fee_per_dollar=base_cost_model_config.sec_fee_per_dollar,
            finra_taf_per_share=base_cost_model_config.finra_taf_per_share,
            finra_taf_max_per_trade=base_cost_model_config.finra_taf_max_per_trade,
        ),
        CostModelConfig(
            half_spread_multiplier=base_cost_model_config.half_spread_multiplier,
            impact_coefficient=base_cost_model_config.impact_coefficient,
            commission_per_share=max(
                base_cost_model_config.commission_per_share * 2.0,
                0.0001,
            ),
            sec_fee_per_dollar=base_cost_model_config.sec_fee_per_dollar,
            finra_taf_per_share=base_cost_model_config.finra_taf_per_share,
            finra_taf_max_per_trade=base_cost_model_config.finra_taf_max_per_trade,
        ),
    )
    for stressed_config in stress_configs:
        try:
            stressed_returns = backtest_runner(
                candidate,
                cost_model_config=stressed_config,
            )
        except Exception:
            return "cost_sensitivity_fail"
        if _total_return(_to_float_sequence(stressed_returns)) <= 0.0:
            return "cost_sensitivity_fail"
    return "cost_sensitivity_pass"


def _run_adversarial_checks(
    candidate: StrategyCandidate,
    *,
    returns: Sequence[Decimal],
    adversarial_context: AdversarialCheckContext | None,
) -> tuple[str, ...]:
    if not returns:
        return (
            "cost_sensitivity_fail",
            "out_of_sample_fail",
            "parameter_sensitivity_fail",
            "regime_behavior_fail",
        )

    out_of_sample = _oos_check(returns)
    if adversarial_context is None:
        return (
            "cost_sensitivity_fail",
            out_of_sample,
            "parameter_sensitivity_fail",
            "regime_behavior_fail",
        )

    parameter_sensitivity = _parameter_sensitivity_check(
        candidate,
        backtest_runner=adversarial_context.backtest_runner,
        base_returns=returns,
    )
    regime_behavior = _regime_behavior_check(
        returns,
        benchmark_bars=adversarial_context.benchmark_bars,
    )
    cost_sensitivity = _cost_sensitivity_check(
        candidate,
        backtest_runner=adversarial_context.backtest_runner,
        base_cost_model_config=adversarial_context.base_cost_model_config,
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
    adversarial_context: AdversarialCheckContext | None = None,
) -> EvaluationEvidencePack:
    candidate_metrics_numeric = _build_metric_pack(candidate_returns)
    benchmark_metrics_numeric = _build_metric_pack(benchmark_returns)
    excess_return = (
        candidate_metrics_numeric["total_return"]
        - benchmark_metrics_numeric["total_return"]
    )
    adversarial_checks = _run_adversarial_checks(
        candidate,
        returns=candidate_returns,
        adversarial_context=adversarial_context,
    )
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
            "adversarial checks rerun the strategy through the supplied "
            "backtest context",
        ),
    )


__all__ = (
    "AdversarialCheckContext",
    "_cost_sensitivity_check",
    "_oos_check",
    "_parameter_sensitivity_check",
    "_regime_behavior_check",
    "evaluate_candidate",
)
