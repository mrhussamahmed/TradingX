from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

TIER0_ALLOWED_DECISIONS = (
    "go",
    "stop_or_refocus",
    "blocked_remediation_required",
    "blocked_measurement_untrusted",
    "blocked_insufficient_history",
    "blocked_as_is_unreproducible",
    "blocked_stress_coverage_missing",
)
_REQUIRED_MEMO_FIELDS = (
    "selected_capital_tier",
    "operator_model",
    "shorting_policy",
    "hurdle_policy",
)
_MISSING_STATUSES = {"", "missing", "unavailable", "incomplete"}
_AS_IS_REPLAY_PASS_STATUSES = {"addressable"}
_STRESS_COVERAGE_PASS_STATUSES = {"covered"}
_MANIFEST_EVIDENCE_PASS_STATUSES = {"complete"}
_GEOMETRIC_UNCERTAINTY_PASS_STATUSES = {"complete"}


def build_geometric_uncertainty_report(
    *,
    strategy_id: str,
    candidate_returns: Sequence[float],
    benchmark_returns_by_name: Mapping[str, Sequence[float]],
    required_benchmarks: Sequence[str],
    block_length: int | None,
    random_seed: int = 2026,
    n_resamples: int = 2_000,
    confidence_percentile: float = 5.0,
    periods_per_year: int = 252,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    if block_length is None:
        return {
            "schema_version": "1.0",
            "kind": "tier0a_geometric_uncertainty_report",
            "strategy_id": strategy_id,
            "status": "unavailable",
            "blocker_codes": ["geometric_uncertainty_block_length_missing"],
            "generated_at_utc": _utc_iso(generated_at_utc),
        }
    if block_length <= 0:
        raise ValueError("block_length must be positive.")
    if n_resamples < 2_000:
        raise ValueError("n_resamples must be at least 2000 for Tier 0A.")
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive.")
    if not 0.0 < confidence_percentile < 50.0:
        raise ValueError("confidence_percentile must be in (0, 50).")

    candidate = tuple(float(value) for value in candidate_returns)
    if _has_invalid_geometric_return(candidate):
        return _blocked_uncertainty_report(
            strategy_id=strategy_id,
            blocker_code="invalid_geometric_return",
            generated_at_utc=generated_at_utc,
        )

    missing_benchmarks: list[str] = []
    comparisons: list[dict[str, Any]] = []
    for name in required_benchmarks:
        benchmark = benchmark_returns_by_name.get(name)
        if benchmark is None:
            missing_benchmarks.append(name)
            continue
        benchmark_values = tuple(float(value) for value in benchmark)
        if len(benchmark_values) != len(candidate) or len(candidate) < 2:
            missing_benchmarks.append(name)
            continue
        if _has_invalid_geometric_return(benchmark_values):
            return _blocked_uncertainty_report(
                strategy_id=strategy_id,
                blocker_code="invalid_geometric_return",
                generated_at_utc=generated_at_utc,
            )
        paired_log_relative_returns = _paired_log_relative_returns(
            candidate,
            benchmark_values,
        )
        contains_total_loss = any(
            value <= -1.0 for value in (*candidate, *benchmark_values)
        )
        if contains_total_loss:
            terminal_samples = np.full(n_resamples, -math.inf, dtype=float)
        else:
            terminal_samples = _stationary_bootstrap_sums(
                paired_log_relative_returns,
                block_length=block_length,
                n_resamples=n_resamples,
                random_seed=random_seed + len(comparisons),
            )
        lower_terminal = _percentile_or_negative_infinity(
            terminal_samples,
            confidence_percentile,
        )
        annualization_factor = periods_per_year / float(len(candidate))
        lower_annualized_growth = (
            -math.inf
            if lower_terminal == -math.inf
            else lower_terminal * annualization_factor
        )
        comparisons.append(
            {
                "benchmark_name": name,
                "paired_log_relative_returns": list(paired_log_relative_returns),
                "lower_bound_log_relative_terminal_wealth": lower_terminal,
                "lower_bound_annualized_log_relative_growth": lower_annualized_growth,
                "supports_positive_edge": lower_annualized_growth > 0.0,
                "contains_total_loss": contains_total_loss,
                "sample_size": len(candidate),
            }
        )

    status = "complete" if not missing_benchmarks else "incomplete"
    all_required_passed = bool(comparisons) and all(
        bool(comparison["supports_positive_edge"]) for comparison in comparisons
    )
    return {
        "schema_version": "1.0",
        "kind": "tier0a_geometric_uncertainty_report",
        "strategy_id": strategy_id,
        "random_seed": random_seed,
        "n_resamples": n_resamples,
        "block_length": block_length,
        "confidence_percentile": confidence_percentile,
        "paired_row_resampling": "stationary_bootstrap_on_paired_daily_rows",
        "required_benchmarks": list(required_benchmarks),
        "missing_benchmarks": missing_benchmarks,
        "comparisons": comparisons,
        "all_required_passed": all_required_passed,
        "status": status,
        "blocker_codes": [] if status == "complete" else ["missing_required_benchmark"],
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_tier0a_decision_payload(
    *,
    memo_inputs: Mapping[str, Any],
    as_is_replay: Mapping[str, Any],
    hard_hurdles: Mapping[str, Any],
    geometric_uncertainty: Mapping[str, Any],
    stress_coverage: Mapping[str, Any],
    manifest_evidence: Mapping[str, Any],
    pbo_cpcv: Mapping[str, Any],
    marginal_portfolio_contribution: Mapping[str, Any],
    cost_stress: Mapping[str, Any],
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    blocker_codes: list[str] = []
    missing_memo = [
        field for field in _REQUIRED_MEMO_FIELDS if not str(memo_inputs.get(field, ""))
    ]
    if not isinstance(memo_inputs.get("plausible_next_higher_tiers", []), list):
        missing_memo.append("plausible_next_higher_tiers")
    if missing_memo:
        blocker_codes.append("tier0a_memo_inputs_missing")

    as_is_status = _status(as_is_replay)
    stress_status = _status(stress_coverage)
    manifest_status = _status(manifest_evidence)
    geometric_status = _status(geometric_uncertainty)
    pbo_status = _status(pbo_cpcv)
    marginal_status = _status(marginal_portfolio_contribution)
    cost_status = _status(cost_stress)
    hard_hurdle_status = _status(hard_hurdles)

    as_is_passed = as_is_status in _AS_IS_REPLAY_PASS_STATUSES
    stress_passed = stress_status in _STRESS_COVERAGE_PASS_STATUSES
    manifest_passed = manifest_status in _MANIFEST_EVIDENCE_PASS_STATUSES
    geometric_passed = geometric_status in _GEOMETRIC_UNCERTAINTY_PASS_STATUSES

    if not as_is_passed:
        blocker_codes.append("as_is_replay_failed_or_missing")
    if not stress_passed:
        blocker_codes.append("fixed_stress_coverage_failed_or_missing")
    if not manifest_passed:
        blocker_codes.append("manifest_evidence_failed_or_missing")
    if not geometric_passed:
        blocker_codes.append("geometric_uncertainty_failed_or_missing")
    if pbo_status not in {"pass", "pending_allowed"}:
        blocker_codes.append("pbo_cpcv_gate_failed_or_missing")
    if marginal_status != "pass":
        blocker_codes.append("marginal_portfolio_contribution_failed_or_missing")
    if cost_status != "pass":
        blocker_codes.append("cost_stress_failed_or_missing")
    if hard_hurdle_status != "pass":
        blocker_codes.append("hard_hurdles_failed_or_missing")

    if as_is_status in _MISSING_STATUSES:
        decision = "blocked_as_is_unreproducible"
    elif not stress_passed:
        decision = "blocked_stress_coverage_missing"
    elif not (as_is_passed and manifest_passed and geometric_passed):
        decision = "blocked_measurement_untrusted"
    elif missing_memo or pbo_status not in {"pass", "pending_allowed"}:
        decision = "blocked_measurement_untrusted"
    elif marginal_status != "pass":
        decision = "blocked_measurement_untrusted"
    elif cost_status != "pass":
        decision = "stop_or_refocus"
    elif not bool(geometric_uncertainty.get("all_required_passed", False)):
        blocker_codes.append("geometric_uncertainty_hurdle_failed")
        decision = "stop_or_refocus"
    elif hard_hurdle_status != "pass":
        decision = "stop_or_refocus"
    elif blocker_codes:
        decision = "blocked_measurement_untrusted"
    else:
        decision = "go"

    return {
        "schema_version": "1.0",
        "kind": "tier0a_decision_payload",
        "allowed_decisions": list(TIER0_ALLOWED_DECISIONS),
        "decision": decision,
        "blocker_codes": blocker_codes,
        "memo_inputs": dict(memo_inputs),
        "as_is_replay": dict(as_is_replay),
        "hard_hurdles": dict(hard_hurdles),
        "geometric_uncertainty": dict(geometric_uncertainty),
        "stress_coverage": dict(stress_coverage),
        "manifest_evidence": dict(manifest_evidence),
        "pbo_cpcv": dict(pbo_cpcv),
        "marginal_portfolio_contribution": dict(marginal_portfolio_contribution),
        "cost_stress": dict(cost_stress),
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def write_tier0a_decision_artifacts(
    payload: Mapping[str, Any],
    *,
    metrics_path: Path = Path("docs/reports/tradingx_tier0a_benchmark_metrics.json"),
    report_path: Path = Path(
        "docs/reports/tradingx_tier0a_benchmark_decision_report.md"
    ),
) -> tuple[Path, Path]:
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_markdown_report(payload), encoding="utf-8")
    return metrics_path, report_path


def _paired_log_relative_returns(
    candidate: Sequence[float],
    benchmark: Sequence[float],
) -> tuple[float, ...]:
    values: list[float] = []
    for left, right in zip(candidate, benchmark, strict=True):
        if left <= -1.0 or right <= -1.0:
            values.append(-math.inf)
        else:
            values.append(math.log1p(left) - math.log1p(right))
    return tuple(values)


def _stationary_bootstrap_sums(
    values: Sequence[float],
    *,
    block_length: int,
    n_resamples: int,
    random_seed: int,
) -> np.ndarray[Any, np.dtype[np.float64]]:
    rng = random.Random(random_seed)
    n_observations = len(values)
    probability = 1.0 / float(block_length)
    samples = np.empty(n_resamples, dtype=float)
    for sample_index in range(n_resamples):
        cursor = rng.randrange(n_observations)
        total = 0.0
        for _ in range(n_observations):
            total += values[cursor]
            if rng.random() < probability:
                cursor = rng.randrange(n_observations)
            else:
                cursor = (cursor + 1) % n_observations
        samples[sample_index] = total
    return samples


def _has_invalid_geometric_return(values: Sequence[float]) -> bool:
    return any(not math.isfinite(value) or value < -1.0 for value in values)


def _blocked_uncertainty_report(
    *,
    strategy_id: str,
    blocker_code: str,
    generated_at_utc: datetime | None,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "tier0a_geometric_uncertainty_report",
        "strategy_id": strategy_id,
        "status": "blocked_measurement_untrusted",
        "blocker_codes": [blocker_code],
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def _percentile_or_negative_infinity(
    values: np.ndarray[Any, np.dtype[np.float64]],
    percentile: float,
) -> float:
    if np.isneginf(values).any():
        return -math.inf
    return float(np.percentile(values, percentile))


def _status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("status", "missing"))


def _utc_iso(value: datetime | None) -> str:
    resolved = value or datetime.now(UTC)
    return resolved.astimezone(UTC).isoformat()


def _markdown_report(payload: Mapping[str, Any]) -> str:
    blockers = payload.get("blocker_codes", [])
    blocker_text = ", ".join(str(item) for item in blockers) if blockers else "none"
    return "\n".join(
        (
            "# TradingX Tier 0A Benchmark Decision Report",
            "",
            f"Decision: `{payload.get('decision', 'blocked_measurement_untrusted')}`",
            "",
            f"Blocker codes: {blocker_text}",
            "",
            "This artifact is generated by the Tier 0A controlled decision harness. "
            "A `go` decision is impossible unless all source-plan mandatory evidence "
            "is present and every hard hurdle passes.",
            "",
        )
    )


__all__ = (
    "TIER0_ALLOWED_DECISIONS",
    "build_geometric_uncertainty_report",
    "build_tier0a_decision_payload",
    "write_tier0a_decision_artifacts",
)
