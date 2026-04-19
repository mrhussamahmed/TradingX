"""Gate-focused validation report builders for Stage 1 evidence."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from tradingx.backtest import run_daily_bar_backtest
from tradingx.costs import CostModelConfig
from tradingx.evaluation import (
    TRADING_DAYS_PER_YEAR,
    AdversarialCheckContext,
    evaluate_candidate,
)
from tradingx.signals.mean_revert import generate_mean_revert_signal
from tradingx.signals.trend import generate_trend_signal
from tradingx.signals.vol_target_spy import generate_vol_target_spy_signal
from tradingx.sizing import apply_position_sizing
from tradingx.types import (
    BenchmarkCloseSeries,
    ScalarValue,
    StrategyCandidate,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
)

# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE1_MIN_CAGR_EDGE = Decimal("0.02")
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE1_MIN_SHARPE = Decimal("1.0")
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE1_MIN_BENCHMARK_SHARPE_MULTIPLIER = Decimal("1.3")
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE1_MAX_DRAWDOWN = Decimal("0.15")
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE1_MIN_CALMAR = Decimal("0.5")
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE1_MIN_OUT_OF_SAMPLE_DAYS = 756
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE1_MAX_PROFILE_DRIFT = Decimal("0.30")

# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE2_MIN_WALK_FORWARD_DAYS = 252
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE2_MIN_WALK_FORWARD_SHARPE = Decimal("0.5")


def _to_float_sequence(values: Sequence[Decimal]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def _total_return(returns: Sequence[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1.0 + value
    return equity - 1.0


def _sharpe_ratio(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return 0.0
    return (mean_return / math.sqrt(variance)) * math.sqrt(float(TRADING_DAYS_PER_YEAR))


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


def _cagr(total_return: float, periods: int) -> float:
    if periods <= 0:
        return 0.0
    annualized_return = float(
        pow(1.0 + total_return, float(TRADING_DAYS_PER_YEAR) / periods)
    )
    return annualized_return - 1.0


def _calmar(total_return: float, max_drawdown: float, periods: int) -> float:
    if periods <= 0:
        return 0.0
    if max_drawdown <= 0:
        return float("inf") if total_return > 0 else 0.0
    return _cagr(total_return, periods) / max_drawdown


def _metric_pack(returns: Sequence[Decimal]) -> dict[str, float]:
    float_returns = _to_float_sequence(returns)
    total_return = _total_return(float_returns)
    max_drawdown = _max_drawdown(float_returns)
    return {
        "total_return": total_return,
        "cagr": _cagr(total_return, len(float_returns)),
        "sharpe_ratio": _sharpe_ratio(float_returns),
        "max_drawdown": max_drawdown,
        "calmar_ratio": _calmar(total_return, max_drawdown, len(float_returns)),
    }


def _relative_drift(reference: float, observed: float) -> float:
    denominator = max(abs(reference), 1e-9)
    return abs(observed - reference) / denominator


def _rolling_windows(
    values: Sequence[Decimal],
    *,
    window_size: int,
) -> tuple[tuple[Decimal, ...], ...]:
    if len(values) < window_size:
        return ()
    return tuple(
        tuple(values[index : index + window_size])
        for index in range(0, len(values) - window_size + 1)
    )


def _build_gate1_candidate_result(
    *,
    candidate: StrategyCandidate,
    candidate_returns: tuple[Decimal, ...],
    benchmark_returns: tuple[Decimal, ...],
    window_start_utc: datetime,
    window_end_utc: datetime,
    benchmark_series_is_adjusted: bool,
    adversarial_context: AdversarialCheckContext,
) -> ValidationCandidateResult:
    evidence_pack = evaluate_candidate(
        candidate,
        candidate_returns=candidate_returns,
        benchmark_returns=benchmark_returns,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        adversarial_context=adversarial_context,
    )
    adversarial_statuses = set(evidence_pack.adversarial_checks)
    candidate_metrics = _metric_pack(candidate_returns)
    benchmark_metrics = _metric_pack(benchmark_returns)
    benchmark_edge_passed = candidate_metrics["cagr"] > benchmark_metrics[
        "cagr"
    ] + float(GATE1_MIN_CAGR_EDGE) or (
        candidate_metrics["sharpe_ratio"] >= float(GATE1_MIN_SHARPE)
        and candidate_metrics["sharpe_ratio"]
        >= benchmark_metrics["sharpe_ratio"]
        * float(GATE1_MIN_BENCHMARK_SHARPE_MULTIPLIER)
    )
    max_drawdown_passed = candidate_metrics["max_drawdown"] <= float(GATE1_MAX_DRAWDOWN)
    calmar_passed = candidate_metrics["calmar_ratio"] >= float(GATE1_MIN_CALMAR)

    out_of_sample_passed = False
    history_complete = len(candidate_returns) >= GATE1_MIN_OUT_OF_SAMPLE_DAYS + 252
    if history_complete:
        out_of_sample_passed = "out_of_sample_pass" in adversarial_statuses
        out_of_sample_details = (
            "Passed the settled 30% tolerance check across Sharpe, CAGR, and "
            "MaxDD on the held-out window."
            if out_of_sample_passed
            else "Failed the settled 30% tolerance check across Sharpe, CAGR, and "
            "MaxDD on the held-out window."
        )
    else:
        out_of_sample_details = (
            "Needs at least 1008 trading days to support a 252-day in-sample "
            "window plus 756 out-of-sample trading days."
        )

    adjusted_details = (
        "Benchmark series was explicitly declared dividend-adjusted."
        if benchmark_series_is_adjusted
        else "Benchmark series adjustment was not declared by the operator."
    )

    criteria = (
        ValidationCriterionResult(
            criterion_id="benchmark_edge",
            passed=benchmark_edge_passed,
            threshold=(
                "CAGR > benchmark CAGR + 2% absolute OR Sharpe >= 1.0 "
                "and >= 1.3x benchmark"
            ),
            details=(
                f"Candidate CAGR={candidate_metrics['cagr']:.3f}, benchmark CAGR="
                f"{benchmark_metrics['cagr']:.3f}, candidate Sharpe="
                f"{candidate_metrics['sharpe_ratio']:.3f}, benchmark Sharpe="
                f"{benchmark_metrics['sharpe_ratio']:.3f}."
            ),
        ),
        ValidationCriterionResult(
            criterion_id="max_drawdown",
            passed=max_drawdown_passed,
            threshold="Max drawdown <= 15%",
            details=f"Candidate max drawdown={candidate_metrics['max_drawdown']:.3f}.",
        ),
        ValidationCriterionResult(
            criterion_id="calmar",
            passed=calmar_passed,
            threshold="Calmar >= 0.5",
            details=f"Candidate Calmar={candidate_metrics['calmar_ratio']:.3f}.",
        ),
        ValidationCriterionResult(
            criterion_id="out_of_sample_profile",
            passed=out_of_sample_passed,
            threshold=(
                "756-day out-of-sample metrics remain within 30% of "
                "in-sample profile"
            ),
            details=out_of_sample_details,
        ),
        ValidationCriterionResult(
            criterion_id="benchmark_adjustment",
            passed=benchmark_series_is_adjusted,
            threshold="Benchmark comparison uses a dividend-adjusted SPY series",
            details=adjusted_details,
        ),
    )
    if not history_complete or not benchmark_series_is_adjusted:
        status = "pending"
    elif all(criterion.passed for criterion in criteria):
        status = "pass"
    else:
        status = "fail"
    return ValidationCandidateResult(
        candidate_id=candidate.candidate_id,
        gate_id="1",
        status=status,
        evidence_pack_id=evidence_pack.evidence_pack_id,
        criteria=criteria,
        summary=(
            "Gate 1 evidence is complete and all criteria passed."
            if status == "pass"
            else (
                "Gate 1 evidence is incomplete."
                if status == "pending"
                else "Gate 1 criteria failed."
            )
        ),
    )


def _build_gate2_candidate_result(
    *,
    candidate: StrategyCandidate,
    candidate_returns: tuple[Decimal, ...],
    benchmark_returns: tuple[Decimal, ...],
    window_start_utc: datetime,
    window_end_utc: datetime,
    adversarial_context: AdversarialCheckContext,
) -> ValidationCandidateResult:
    evidence_pack = evaluate_candidate(
        candidate,
        candidate_returns=candidate_returns,
        benchmark_returns=benchmark_returns,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        adversarial_context=adversarial_context,
    )
    adversarial_statuses = set(evidence_pack.adversarial_checks)
    cost_stress_passed = "cost_sensitivity_pass" in adversarial_statuses
    parameter_perturbation_passed = "parameter_sensitivity_pass" in adversarial_statuses
    walk_forward_windows = _rolling_windows(
        candidate_returns,
        window_size=GATE2_MIN_WALK_FORWARD_DAYS,
    )
    if walk_forward_windows:
        window_sharpes = tuple(
            _metric_pack(window)["sharpe_ratio"] for window in walk_forward_windows
        )
        walk_forward_passed = min(window_sharpes) >= float(
            GATE2_MIN_WALK_FORWARD_SHARPE
        )
        walk_forward_details = (
            f"Minimum rolling 252-day Sharpe={min(window_sharpes):.3f} across "
            f"{len(window_sharpes)} windows."
        )
    else:
        walk_forward_passed = False
        walk_forward_details = (
            "Needs at least 252 trading days to compute a rolling walk-forward window."
        )

    criteria = (
        ValidationCriterionResult(
            criterion_id="cost_stress",
            passed=cost_stress_passed,
            threshold=(
                "Net profitable across simultaneous 2x half-spread, impact, "
                "and commission stresses, and across each stressed component "
                "individually"
            ),
            details=(
                "Passed the simultaneous and individual reruns across half-spread, "
                "impact, and commission shocks in the turnover-aware cost model."
                if cost_stress_passed
                else "Failed at least one stressed rerun across half-spread, "
                "impact, or commission shocks in the turnover-aware cost model."
            ),
        ),
        ValidationCriterionResult(
            criterion_id="parameter_perturbation",
            passed=parameter_perturbation_passed,
            threshold=(
                "Perturbing each numeric strategy parameter by +/-20% and +/-40% "
                "does not degrade Sharpe by more than 30%"
            ),
            details=(
                "Passed all full-rerun parameter perturbations."
                if parameter_perturbation_passed
                else "At least one full-rerun parameter perturbation degraded "
                "Sharpe beyond the allowed 30% threshold."
            ),
        ),
        ValidationCriterionResult(
            criterion_id="walk_forward_window",
            passed=walk_forward_passed,
            threshold=(
                "Every rolling walk-forward window of at least 1 year "
                "keeps Sharpe >= 0.5"
            ),
            details=walk_forward_details,
        ),
    )
    if not walk_forward_windows:
        status = "pending"
    elif all(criterion.passed for criterion in criteria):
        status = "pass"
    else:
        status = "fail"
    return ValidationCandidateResult(
        candidate_id=candidate.candidate_id,
        gate_id="2",
        status=status,
        evidence_pack_id=evidence_pack.evidence_pack_id,
        criteria=criteria,
        summary=(
            "Gate 2 evidence is complete and all criteria passed."
            if status == "pass"
            else (
                "Gate 2 evidence is incomplete."
                if status == "pending"
                else "Gate 2 criteria failed."
            )
        ),
    )


def _align_bars_by_symbol(
    bars_by_symbol: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    common_index = None
    for bars in bars_by_symbol.values():
        if common_index is None:
            common_index = bars.index
        else:
            common_index = common_index.intersection(bars.index)
    if common_index is None or common_index.empty:
        raise ValueError(
            "bars_by_symbol must contain at least one aligned bar history."
        )
    return {
        symbol: bars.loc[common_index].astype(float).copy()
        for symbol, bars in bars_by_symbol.items()
    }


def _wide_ohlcv_frame(
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    payload: dict[tuple[str, str], pd.Series] = {}
    reference_index = next(iter(bars_by_symbol.values())).index
    for symbol, bars in bars_by_symbol.items():
        for field in ("open", "high", "low", "close", "volume"):
            payload[(symbol, field)] = (
                bars[field].astype(float).reindex(reference_index)
            )
    return pd.DataFrame(payload, index=reference_index)


def _normalize_target_weights(target_weights: pd.DataFrame) -> pd.DataFrame:
    normalized = target_weights.fillna(0.0).astype(float).copy()
    gross_exposure = normalized.abs().sum(axis=1)
    for timestamp in normalized.index[gross_exposure > 1.0]:
        normalized.loc[timestamp] = normalized.loc[timestamp] / float(
            gross_exposure.loc[timestamp]
        )
    return normalized


def _trend_target_weights(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    symbol_weights = {}
    for symbol in candidate.universe:
        bars = bars_by_symbol[symbol]
        signal = generate_trend_signal(
            bars,
            lookback_days=int(candidate.parameter_set["lookback_days"]),
            sma_window_days=int(candidate.parameter_set["sma_window_days"]),
            skip_recent_days=int(candidate.parameter_set.get("skip_recent_days", 1)),
        )
        symbol_weights[symbol] = apply_position_sizing(
            bars,
            signal=signal,
            pre_sized=False,
        )
    reference_index = next(iter(symbol_weights.values())).index
    return _normalize_target_weights(
        pd.DataFrame(symbol_weights, index=reference_index, dtype=float)
    )


def _vol_target_target_weights(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    benchmark_symbol = candidate.benchmark_symbol
    bars = bars_by_symbol[benchmark_symbol]
    signal = generate_vol_target_spy_signal(
        bars,
        target_volatility=float(candidate.parameter_set["target_volatility"]),
        realized_vol_window_days=int(
            candidate.parameter_set["realized_vol_window_days"]
        ),
        max_gross_leverage=float(candidate.parameter_set["max_gross_leverage"]),
    )
    return pd.DataFrame({benchmark_symbol: signal}, index=bars.index, dtype=float)


def _mean_reversion_target_weights(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    if not candidate.universe:
        raise ValueError(
            "mean_reversion candidate requires at least one tradable symbol."
        )
    relevant_bars = {
        symbol: bars_by_symbol[symbol]
        for symbol in (candidate.benchmark_symbol, *candidate.universe)
    }
    signal_frame = generate_mean_revert_signal(
        _wide_ohlcv_frame(relevant_bars),
        benchmark_symbol=candidate.benchmark_symbol,
        tradable_symbols=candidate.universe,
        beta_window_days=int(candidate.parameter_set["beta_window_days"]),
        residual_sum_days=int(candidate.parameter_set["residual_sum_days"]),
        zscore_window_days=int(candidate.parameter_set["zscore_window_days"]),
        zscore_threshold=float(candidate.parameter_set["zscore_threshold"]),
    )
    sized_weights = {
        symbol: apply_position_sizing(
            bars_by_symbol[symbol],
            signal=signal_frame[symbol],
            pre_sized=False,
        )
        for symbol in candidate.universe
    }
    return _normalize_target_weights(
        pd.DataFrame(sized_weights, index=signal_frame.index, dtype=float)
    )


def _candidate_returns(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    parameter_overrides: dict[str, ScalarValue] | None = None,
    cost_model_config: CostModelConfig | None = None,
) -> tuple[Decimal, ...]:
    configured_candidate = _candidate_with_parameter_overrides(
        candidate,
        parameter_overrides=parameter_overrides,
    )

    if configured_candidate.family == "trend_following":
        traded_symbols = configured_candidate.universe
        target_weights = _trend_target_weights(
            configured_candidate,
            bars_by_symbol=bars_by_symbol,
        )
    elif configured_candidate.family == "vol_target":
        traded_symbols = (configured_candidate.benchmark_symbol,)
        target_weights = _vol_target_target_weights(
            configured_candidate,
            bars_by_symbol=bars_by_symbol,
        )
    elif configured_candidate.family == "mean_reversion":
        traded_symbols = configured_candidate.universe
        target_weights = _mean_reversion_target_weights(
            configured_candidate,
            bars_by_symbol=bars_by_symbol,
        )
    else:
        raise ValueError(f"Unsupported candidate family: {configured_candidate.family}")

    result = run_daily_bar_backtest(
        {symbol: bars_by_symbol[symbol] for symbol in traded_symbols},
        target_weights=target_weights,
        cost_model_config=cost_model_config,
    )
    return tuple(Decimal(str(value)) for value in result.portfolio_returns.tolist())


def _candidate_with_parameter_overrides(
    candidate: StrategyCandidate,
    *,
    parameter_overrides: dict[str, ScalarValue] | None,
) -> StrategyCandidate:
    if not parameter_overrides:
        return candidate
    merged_parameter_set = dict(candidate.parameter_set)
    merged_parameter_set.update(parameter_overrides)
    return replace(candidate, parameter_set=merged_parameter_set)


def _benchmark_returns(
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    benchmark_symbol: str,
) -> tuple[Decimal, ...]:
    bars = bars_by_symbol[benchmark_symbol]
    result = run_daily_bar_backtest(
        {benchmark_symbol: bars},
        target_weights=pd.DataFrame(
            {benchmark_symbol: [1.0] * len(bars)},
            index=bars.index,
            dtype=float,
        ),
        initial_weights={benchmark_symbol: 1.0},
    )
    return tuple(Decimal(str(value)) for value in result.portfolio_returns.tolist())


def build_gate_report(
    *,
    gate_id: str,
    bars_by_symbol: dict[str, pd.DataFrame],
    candidates: Sequence[StrategyCandidate],
    benchmark_symbol: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
    benchmark_series_is_adjusted: bool,
) -> ValidationReport:
    aligned_bars = _align_bars_by_symbol(bars_by_symbol)
    benchmark_returns = _benchmark_returns(
        bars_by_symbol=aligned_bars,
        benchmark_symbol=benchmark_symbol,
    )
    base_cost_model_config = CostModelConfig()

    def backtest_runner(
        rerun_candidate: StrategyCandidate,
        *,
        parameter_overrides: dict[str, ScalarValue] | None = None,
        cost_model_config: CostModelConfig | None = None,
    ) -> tuple[Decimal, ...]:
        return _candidate_returns(
            rerun_candidate,
            bars_by_symbol=aligned_bars,
            parameter_overrides=parameter_overrides,
            cost_model_config=cost_model_config,
        )

    candidate_results = []
    for candidate in candidates:
        candidate_returns = _candidate_returns(candidate, bars_by_symbol=aligned_bars)
        adversarial_context = AdversarialCheckContext(
            benchmark_bars=aligned_bars[benchmark_symbol],
            backtest_runner=backtest_runner,
            base_cost_model_config=base_cost_model_config,
        )
        if gate_id == "1":
            result = _build_gate1_candidate_result(
                candidate=candidate,
                candidate_returns=candidate_returns,
                benchmark_returns=benchmark_returns,
                window_start_utc=window_start_utc,
                window_end_utc=window_end_utc,
                benchmark_series_is_adjusted=benchmark_series_is_adjusted,
                adversarial_context=adversarial_context,
            )
        elif gate_id == "2":
            result = _build_gate2_candidate_result(
                candidate=candidate,
                candidate_returns=candidate_returns,
                benchmark_returns=benchmark_returns,
                window_start_utc=window_start_utc,
                window_end_utc=window_end_utc,
                adversarial_context=adversarial_context,
            )
        else:
            raise ValueError(f"Unsupported gate_id: {gate_id}")
        candidate_results.append(result)

    statuses = {result.status for result in candidate_results}
    if statuses == {"pass"}:
        report_status = "pass"
    elif "fail" in statuses:
        report_status = "fail"
    else:
        report_status = "pending"

    report_timestamp = datetime.now(UTC)
    return ValidationReport(
        report_id=f"gate-{gate_id}-{report_timestamp.strftime('%Y%m%dT%H%M%SZ')}",
        gate_id=gate_id,
        generated_at_utc=report_timestamp,
        status=report_status,
        benchmark_symbol=benchmark_symbol,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        candidate_results=tuple(candidate_results),
        summary=(
            f"Gate {gate_id} {'passed' if report_status == 'pass' else report_status} "
            f"for {len(candidate_results)} mandatory candidates."
        ),
        assumptions=(
            "candidate returns are generated from daily-bar next-open backtests",
            "candidate adversarial checks rerun the same backtest engine with "
            "parameter and cost perturbations",
            "portfolio weights are normalized to max gross exposure 1.0 before replay",
        ),
        evidence_refs=tuple(result.evidence_pack_id for result in candidate_results),
    )


def _parse_optional_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    timestamp = datetime.fromisoformat(str(value))
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def load_benchmark_close_series(path: Path) -> BenchmarkCloseSeries:
    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return BenchmarkCloseSeries(
            symbol="SPY",
            closes=(),
            window_start_utc=None,
            window_end_utc=None,
            generated_at_utc=None,
            feed="",
            adjustment="",
            series_is_adjusted=False,
        )
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        tokens = [token.strip() for token in raw_text.replace("\n", ",").split(",")]
        return BenchmarkCloseSeries(
            symbol="SPY",
            closes=tuple(Decimal(token) for token in tokens if token),
            window_start_utc=None,
            window_end_utc=None,
            generated_at_utc=None,
            feed="",
            adjustment="",
            series_is_adjusted=False,
        )
    if isinstance(payload, list):
        return BenchmarkCloseSeries(
            symbol="SPY",
            closes=tuple(Decimal(str(value)) for value in payload),
            window_start_utc=None,
            window_end_utc=None,
            generated_at_utc=None,
            feed="",
            adjustment="",
            series_is_adjusted=False,
        )
    if not isinstance(payload, dict):
        raise ValueError(
            "Benchmark closes file must contain a JSON list or a "
            "benchmark artifact object."
        )
    closes = payload.get("closes")
    if not isinstance(closes, list):
        raise ValueError(
            "Benchmark artifact object must contain a JSON list of closes."
        )
    adjustment = str(payload.get("adjustment") or "")
    return BenchmarkCloseSeries(
        symbol=str(payload.get("symbol") or "SPY"),
        closes=tuple(Decimal(str(value)) for value in closes),
        window_start_utc=_parse_optional_datetime(payload.get("window_start_utc")),
        window_end_utc=_parse_optional_datetime(payload.get("window_end_utc")),
        generated_at_utc=_parse_optional_datetime(payload.get("generated_at_utc")),
        feed=str(payload.get("feed") or ""),
        adjustment=adjustment,
        series_is_adjusted=bool(
            payload.get("series_is_adjusted", adjustment in {"dividend", "all"})
        ),
    )


def load_close_series(path: Path) -> tuple[Decimal, ...]:
    return load_benchmark_close_series(path).closes


def write_benchmark_close_series(path: Path, series: BenchmarkCloseSeries) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": series.symbol,
        "window_start_utc": (
            series.window_start_utc.astimezone(UTC).isoformat()
            if series.window_start_utc is not None
            else None
        ),
        "window_end_utc": (
            series.window_end_utc.astimezone(UTC).isoformat()
            if series.window_end_utc is not None
            else None
        ),
        "generated_at_utc": (
            series.generated_at_utc.astimezone(UTC).isoformat()
            if series.generated_at_utc is not None
            else None
        ),
        "feed": series.feed,
        "adjustment": series.adjustment,
        "series_is_adjusted": series.series_is_adjusted,
        "closes": [str(value) for value in series.closes],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


__all__ = (
    "build_gate_report",
    "load_benchmark_close_series",
    "load_close_series",
    "write_benchmark_close_series",
)
