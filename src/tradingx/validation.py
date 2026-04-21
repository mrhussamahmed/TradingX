"""Gate-focused validation report builders for Stage 1 evidence."""

from __future__ import annotations

import json
import logging
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
from tradingx.portfolio_construction import build_candidate_target_weight_history
from tradingx.stats import (
    conditional_drawdown_at_risk,
    lo_adjusted_sharpe_ratio,
    max_drawdown,
)
from tradingx.types import (
    BenchmarkCloseSeries,
    BenchmarkStackPayload,
    OperatingConstraintBudget,
    ScalarValue,
    StrategyCandidate,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
)

LOGGER = logging.getLogger(__name__)

# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE1_MIN_CAGR_EDGE = Decimal("0.02")
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
    sharpe_ratio = lo_adjusted_sharpe_ratio(
        returns=returns,
        risk_free_daily_rates=(0.0,) * len(returns),
        periods_per_year=TRADING_DAYS_PER_YEAR,
    )
    if sharpe_ratio is None:
        return 0.0
    return sharpe_ratio


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


def evaluate_hurdle_clearance(
    *,
    candidate_returns: tuple[Decimal, ...],
    hurdle_returns: tuple[Decimal, ...],
) -> ValidationCriterionResult:
    if len(candidate_returns) != len(hurdle_returns):
        raise ValueError("candidate_returns and hurdle_returns must align in length.")
    candidate_metrics = _metric_pack(candidate_returns)
    hurdle_metrics = _metric_pack(hurdle_returns)
    passed = candidate_metrics["total_return"] > hurdle_metrics["total_return"]
    return ValidationCriterionResult(
        criterion_id="hurdle_clearance",
        passed=passed,
        threshold="Candidate total return must exceed the cash hurdle total return",
        details=(
            f"Candidate total return={candidate_metrics['total_return']:.3f}, "
            f"cash hurdle total return={hurdle_metrics['total_return']:.3f}."
        ),
    )


def evaluate_opportunity_cost_edge(
    *,
    candidate_returns: tuple[Decimal, ...],
    opportunity_cost_returns: tuple[Decimal, ...],
    opportunity_cost_weights: tuple[tuple[str, Decimal], ...],
) -> ValidationCriterionResult:
    if len(candidate_returns) != len(opportunity_cost_returns):
        raise ValueError(
            "candidate_returns and opportunity_cost_returns must align in length."
        )
    candidate_metrics = _metric_pack(candidate_returns)
    opportunity_cost_metrics = _metric_pack(opportunity_cost_returns)
    passed = candidate_metrics["cagr"] > opportunity_cost_metrics["cagr"] + float(
        GATE1_MIN_CAGR_EDGE
    )
    composition = "+".join(
        f"{symbol}:{weight.normalize()}" for symbol, weight in opportunity_cost_weights
    )
    return ValidationCriterionResult(
        criterion_id="opportunity_cost_edge",
        passed=passed,
        threshold=(
            f"Candidate CAGR must exceed {composition} CAGR by "
            f"{GATE1_MIN_CAGR_EDGE:.2f} absolute"
        ),
        details=(
            f"Candidate CAGR={candidate_metrics['cagr']:.3f}, "
            f"{composition} CAGR={opportunity_cost_metrics['cagr']:.3f}."
        ),
    )


def evaluate_operating_constraint(
    *,
    candidate_returns: tuple[Decimal, ...],
    constraint: OperatingConstraintBudget,
) -> ValidationCriterionResult:
    float_returns = _to_float_sequence(candidate_returns)
    observed_max_drawdown = Decimal(str(max_drawdown(float_returns)))
    observed_cdar = Decimal(
        str(
            conditional_drawdown_at_risk(
                float_returns,
                confidence=float(constraint.cdar_confidence),
            )
        )
    )
    passed = (
        observed_max_drawdown <= constraint.max_drawdown_design
        and observed_cdar <= constraint.cdar_threshold
    )
    return ValidationCriterionResult(
        criterion_id="operating_constraint",
        passed=passed,
        threshold=(
            f"max_drawdown <= {constraint.max_drawdown_design} and "
            f"CDaR@{constraint.cdar_confidence} <= {constraint.cdar_threshold}"
        ),
        details=(
            f"max_drawdown={observed_max_drawdown:.3f}, "
            f"CDaR={observed_cdar:.3f}, "
            f"halt={constraint.max_drawdown_halt:.3f}."
        ),
    )


def evaluate_gate1_benchmark_criteria(
    *,
    candidate_returns: tuple[Decimal, ...],
    benchmark_stack_payload: BenchmarkStackPayload,
) -> tuple[ValidationCriterionResult, ...]:
    return (
        evaluate_hurdle_clearance(
            candidate_returns=candidate_returns,
            hurdle_returns=benchmark_stack_payload.hurdle_returns,
        ),
        evaluate_opportunity_cost_edge(
            candidate_returns=candidate_returns,
            opportunity_cost_returns=benchmark_stack_payload.opportunity_cost_returns,
            opportunity_cost_weights=benchmark_stack_payload.opportunity_cost_weights,
        ),
        evaluate_operating_constraint(
            candidate_returns=candidate_returns,
            constraint=benchmark_stack_payload.operating_constraint,
        ),
    )


def _build_gate1_candidate_result(
    *,
    candidate: StrategyCandidate,
    candidate_returns: tuple[Decimal, ...],
    benchmark_stack_payload: BenchmarkStackPayload,
    window_start_utc: datetime,
    window_end_utc: datetime,
    adversarial_context: AdversarialCheckContext,
) -> ValidationCandidateResult:
    evidence_pack = evaluate_candidate(
        candidate,
        candidate_returns=candidate_returns,
        benchmark_returns=benchmark_stack_payload.opportunity_cost_returns,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        adversarial_context=adversarial_context,
    )
    adversarial_statuses = set(evidence_pack.adversarial_checks)

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

    criteria = evaluate_gate1_benchmark_criteria(
        candidate_returns=candidate_returns,
        benchmark_stack_payload=benchmark_stack_payload,
    ) + (
        ValidationCriterionResult(
            criterion_id="out_of_sample_profile",
            passed=out_of_sample_passed,
            threshold=(
                "756-day out-of-sample metrics remain within 30% of "
                "in-sample profile"
            ),
            details=out_of_sample_details,
        ),
    )
    if not history_complete:
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
                "Net profitable across the 1x, 2x, and 4x cost grid, including "
                "simultaneous half-spread, impact, and commission stresses and "
                "each stressed component individually"
            ),
            details=(
                "Passed the baseline, simultaneous, and individual reruns across "
                "the 1x, 2x, and 4x half-spread, impact, and commission shocks "
                "in the turnover-aware cost model."
                if cost_stress_passed
                else "Failed at least one baseline, simultaneous, or individual "
                "rerun across the 1x, 2x, and 4x half-spread, impact, or "
                "commission shocks in the turnover-aware cost model."
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


def _candidate_returns(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    parameter_overrides: dict[str, ScalarValue] | None = None,
    cost_model_config: CostModelConfig | None = None,
) -> tuple[tuple[Decimal, ...], Decimal]:
    configured_candidate = _candidate_with_parameter_overrides(
        candidate,
        parameter_overrides=parameter_overrides,
    )
    target_weights = build_candidate_target_weight_history(
        configured_candidate,
        bars_by_symbol=bars_by_symbol,
    )
    traded_symbols = tuple(str(symbol) for symbol in target_weights.columns)

    result = run_daily_bar_backtest(
        {symbol: bars_by_symbol[symbol] for symbol in traded_symbols},
        target_weights=target_weights,
        cost_model_config=cost_model_config or CostModelConfig(),
    )
    returns = tuple(Decimal(str(value)) for value in result.portfolio_returns.tolist())
    return returns, result.annualized_cost_drag_bps


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


def build_gate_report(
    *,
    gate_id: str,
    bars_by_symbol: dict[str, pd.DataFrame],
    candidates: Sequence[StrategyCandidate],
    benchmark_stack_payload: BenchmarkStackPayload,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> ValidationReport:
    aligned_bars = _align_bars_by_symbol(bars_by_symbol)
    benchmark_returns = benchmark_stack_payload.opportunity_cost_returns
    base_cost_model_config = CostModelConfig()

    def backtest_runner(
        rerun_candidate: StrategyCandidate,
        *,
        parameter_overrides: dict[str, ScalarValue] | None = None,
        cost_model_config: CostModelConfig | None = None,
    ) -> tuple[Decimal, ...]:
        returns, _ = _candidate_returns(
            rerun_candidate,
            bars_by_symbol=aligned_bars,
            parameter_overrides=parameter_overrides,
            cost_model_config=cost_model_config,
        )
        return returns

    candidate_results = []
    for candidate in candidates:
        candidate_returns, _ = _candidate_returns(candidate, bars_by_symbol=aligned_bars)
        if len(candidate_returns) != len(benchmark_stack_payload.hurdle_returns):
            raise ValueError(
                "benchmark_stack_payload.hurdle_returns must align with "
                "candidate returns."
            )
        if len(candidate_returns) != len(
            benchmark_stack_payload.opportunity_cost_returns
        ):
            raise ValueError(
                "benchmark_stack_payload.opportunity_cost_returns must align "
                "with candidate returns."
            )
        adversarial_context = AdversarialCheckContext(
            benchmark_bars=aligned_bars[candidate.benchmark_symbol],
            backtest_runner=backtest_runner,
            base_cost_model_config=base_cost_model_config,
        )
        if gate_id == "1":
            result = _build_gate1_candidate_result(
                candidate=candidate,
                candidate_returns=candidate_returns,
                benchmark_stack_payload=benchmark_stack_payload,
                window_start_utc=window_start_utc,
                window_end_utc=window_end_utc,
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
        benchmark_symbol="+".join(
            symbol for symbol, _ in benchmark_stack_payload.opportunity_cost_weights
        ),
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
        LOGGER.warning(
            "Benchmark close series at %s uses legacy bare-number format "
            "without metadata.",
            path,
        )
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
        LOGGER.warning(
            "Benchmark close series at %s uses legacy JSON-list format "
            "without metadata.",
            path,
        )
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


def load_benchmark_stack_payload(path: Path) -> BenchmarkStackPayload:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Benchmark stack payload must be a JSON object.")

    hurdle_returns = payload.get("hurdle_returns")
    opportunity_cost_returns = payload.get("opportunity_cost_returns")
    opportunity_cost_weights = payload.get("opportunity_cost_weights")
    operating_constraint = payload.get("operating_constraint")
    if not isinstance(hurdle_returns, list) or not isinstance(
        opportunity_cost_returns,
        list,
    ):
        raise ValueError(
            "Benchmark stack payload must contain hurdle_returns and "
            "opportunity_cost_returns lists."
        )
    if not isinstance(opportunity_cost_weights, list) or not isinstance(
        operating_constraint,
        dict,
    ):
        raise ValueError(
            "Benchmark stack payload must contain opportunity_cost_weights "
            "and operating_constraint."
        )
    return BenchmarkStackPayload(
        hurdle_returns=tuple(Decimal(str(value)) for value in hurdle_returns),
        opportunity_cost_returns=tuple(
            Decimal(str(value)) for value in opportunity_cost_returns
        ),
        opportunity_cost_weights=tuple(
            (str(item["symbol"]), Decimal(str(item["weight"])))
            for item in opportunity_cost_weights
        ),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal(
                str(operating_constraint["max_drawdown_design"])
            ),
            max_drawdown_halt=Decimal(str(operating_constraint["max_drawdown_halt"])),
            cdar_threshold=Decimal(str(operating_constraint["cdar_threshold"])),
            cdar_confidence=Decimal(str(operating_constraint["cdar_confidence"])),
        ),
    )


def write_benchmark_stack_payload(
    path: Path,
    payload: BenchmarkStackPayload,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = {
        "hurdle_returns": [str(value) for value in payload.hurdle_returns],
        "opportunity_cost_returns": [
            str(value) for value in payload.opportunity_cost_returns
        ],
        "opportunity_cost_weights": [
            {"symbol": symbol, "weight": str(weight)}
            for symbol, weight in payload.opportunity_cost_weights
        ],
        "operating_constraint": {
            "max_drawdown_design": str(
                payload.operating_constraint.max_drawdown_design
            ),
            "max_drawdown_halt": str(payload.operating_constraint.max_drawdown_halt),
            "cdar_threshold": str(payload.operating_constraint.cdar_threshold),
            "cdar_confidence": str(payload.operating_constraint.cdar_confidence),
        },
    }
    path.write_text(json.dumps(serialized, indent=2, sort_keys=True), encoding="utf-8")
    return path


__all__ = (
    "build_gate_report",
    "load_benchmark_close_series",
    "load_benchmark_stack_payload",
    "load_close_series",
    "write_benchmark_close_series",
    "write_benchmark_stack_payload",
)
