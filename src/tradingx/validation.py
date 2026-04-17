"""Gate-focused validation report builders for Stage 1 evidence."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.data import close_to_close_returns
from tradingx.evaluation import TRADING_DAYS_PER_YEAR, evaluate_candidate
from tradingx.strategy import build_candidate_return_series
from tradingx.types import (
    BenchmarkCloseSeries,
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

# source: src/tradingx/evaluation.py fixed per-period cost sensitivity assumption
BASE_COST_PENALTY = Decimal("0.001")
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE2_COST_MULTIPLIER = Decimal("2.0")
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE2_PARAMETER_PERTURBATION = Decimal("0.20")
# source: docs/validation/acceptance_gates.md (GATES-0001 v1.0.0, retrieved 2026-04-17)
GATE2_MAX_SHARPE_DEGRADATION = Decimal("0.30")
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


def _apply_cost_stress(returns: Sequence[Decimal]) -> tuple[Decimal, ...]:
    penalty = BASE_COST_PENALTY * GATE2_COST_MULTIPLIER
    return tuple(value - penalty for value in returns)


def _apply_parameter_stress(
    returns: Sequence[Decimal],
    *,
    direction: str,
) -> tuple[Decimal, ...]:
    stressed: list[Decimal] = []
    for value in returns:
        magnitude = abs(value) * GATE2_PARAMETER_PERTURBATION
        if direction == "minus":
            adjusted = value - (magnitude * Decimal("0.25"))
            if value < 0:
                adjusted = value - (magnitude * Decimal("0.10"))
        else:
            adjusted = value - (magnitude * Decimal("0.15"))
            if value < 0:
                adjusted = value - (magnitude * Decimal("0.05"))
        stressed.append(adjusted)
    return tuple(stressed)


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
) -> ValidationCandidateResult:
    evidence_pack = evaluate_candidate(
        candidate,
        candidate_returns=candidate_returns,
        benchmark_returns=benchmark_returns,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
    )
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
        in_sample_returns = candidate_returns[:-GATE1_MIN_OUT_OF_SAMPLE_DAYS]
        out_of_sample_returns = candidate_returns[-GATE1_MIN_OUT_OF_SAMPLE_DAYS:]
        in_sample_metrics = _metric_pack(in_sample_returns)
        out_of_sample_metrics = _metric_pack(out_of_sample_returns)
        cagr_drift = _relative_drift(
            in_sample_metrics["cagr"],
            out_of_sample_metrics["cagr"],
        )
        sharpe_drift = _relative_drift(
            in_sample_metrics["sharpe_ratio"],
            out_of_sample_metrics["sharpe_ratio"],
        )
        out_of_sample_passed = cagr_drift <= float(
            GATE1_MAX_PROFILE_DRIFT
        ) and sharpe_drift <= float(GATE1_MAX_PROFILE_DRIFT)
        out_of_sample_details = (
            f"OOS CAGR drift={cagr_drift:.3f}, OOS Sharpe drift={sharpe_drift:.3f}."
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
) -> ValidationCandidateResult:
    evidence_pack = evaluate_candidate(
        candidate,
        candidate_returns=candidate_returns,
        benchmark_returns=benchmark_returns,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
    )
    base_metrics = _metric_pack(candidate_returns)
    cost_metrics = _metric_pack(_apply_cost_stress(candidate_returns))
    minus_metrics = _metric_pack(
        _apply_parameter_stress(candidate_returns, direction="minus")
    )
    plus_metrics = _metric_pack(
        _apply_parameter_stress(candidate_returns, direction="plus")
    )
    base_sharpe = max(base_metrics["sharpe_ratio"], 1e-9)
    max_degradation = max(
        _relative_drift(base_sharpe, minus_metrics["sharpe_ratio"]),
        _relative_drift(base_sharpe, plus_metrics["sharpe_ratio"]),
    )
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
            passed=cost_metrics["total_return"] > 0,
            threshold="Net profitable at 2x slippage and 2x fees",
            details=(
                f"2x cost-stress total return={cost_metrics['total_return']:.3f} "
                f"using a {BASE_COST_PENALTY * GATE2_COST_MULTIPLIER:.4f} "
                "per-period cost penalty."
            ),
        ),
        ValidationCriterionResult(
            criterion_id="parameter_perturbation",
            passed=max_degradation <= float(GATE2_MAX_SHARPE_DEGRADATION),
            threshold="+/-20% perturbation does not degrade Sharpe by more than 30%",
            details=(
                f"Max Sharpe degradation={max_degradation:.3f}; base Sharpe="
                f"{base_metrics['sharpe_ratio']:.3f}."
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


def build_gate_report(
    *,
    gate_id: str,
    benchmark_closes: Sequence[Decimal],
    candidates: Sequence[StrategyCandidate],
    window_start_utc: datetime,
    window_end_utc: datetime,
    benchmark_series_is_adjusted: bool,
) -> ValidationReport:
    benchmark_returns = close_to_close_returns(benchmark_closes)
    candidate_results: list[ValidationCandidateResult] = []
    for candidate in candidates:
        candidate_returns = build_candidate_return_series(candidate, benchmark_closes)
        if gate_id == "1":
            candidate_result = _build_gate1_candidate_result(
                candidate=candidate,
                candidate_returns=candidate_returns,
                benchmark_returns=benchmark_returns,
                window_start_utc=window_start_utc,
                window_end_utc=window_end_utc,
                benchmark_series_is_adjusted=benchmark_series_is_adjusted,
            )
        elif gate_id == "2":
            candidate_result = _build_gate2_candidate_result(
                candidate=candidate,
                candidate_returns=candidate_returns,
                benchmark_returns=benchmark_returns,
                window_start_utc=window_start_utc,
                window_end_utc=window_end_utc,
            )
        else:
            raise ValueError(f"Unsupported gate id: {gate_id}")
        candidate_results.append(candidate_result)

    if any(result.status == "pass" for result in candidate_results):
        status = "pass"
    elif any(result.status == "pending" for result in candidate_results):
        status = "pending"
    else:
        status = "fail"

    report_id = f"gate-{gate_id}-{window_end_utc.strftime('%Y%m%dT%H%M%SZ')}"
    passing_candidates = ", ".join(
        result.candidate_id for result in candidate_results if result.status == "pass"
    )
    return ValidationReport(
        report_id=report_id,
        gate_id=gate_id,
        generated_at_utc=window_end_utc,
        status=status,
        benchmark_symbol="SPY",
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        candidate_results=tuple(candidate_results),
        summary=(
            f"Gate {gate_id} passed for {passing_candidates}."
            if status == "pass"
            else (
                f"Gate {gate_id} remains pending due to incomplete evidence."
                if status == "pending"
                else f"Gate {gate_id} failed for every mandatory candidate."
            )
        ),
        assumptions=(
            "Mandatory candidates are evaluated against the same benchmark "
            "return window.",
            "Gate 2 parameter perturbation uses deterministic return-profile "
            "stress until a richer strategy-parameter sweep exists.",
        ),
        evidence_refs=tuple(
            f"evaluation_evidence/{result.evidence_pack_id}.json"
            for result in candidate_results
        ),
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
