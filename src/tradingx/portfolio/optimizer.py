"""Wave 6 portfolio optimizer governance artifacts.

This module produces optimizer-side promotion artifacts:
``portfolio_utility_definition``, ``optimizer_validation_report``, and
``optimizer_fallback_record``. The builders are deterministic given
inputs; runtime uses these reports to enforce the Wave 6 promotion
gates without re-running the full optimizer/baselines pipeline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

REQUIRED_BASELINES: tuple[str, ...] = (
    "no_trade",
    "current_holdings",
    "static_sleeve_budget",
    "equal_weight",
    "inverse_volatility",
    "equal_risk_contribution",
    "current_non_optimized_allocation",
)

_TAIL_RISK_TERMS: frozenset[str] = frozenset(
    {
        "cvar",
        "expected_shortfall",
        "downside_semivariance",
        "left_tail_penalty",
        "tail_event_stress",
    }
)


def _utc_iso(value: datetime | None) -> str:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).isoformat()


def _decimal_str(value: Decimal | float | int | str) -> str:
    if isinstance(value, Decimal):
        return str(value)
    return str(Decimal(str(value)))


def _append_unique(values: list[str], code: str) -> None:
    if code and code not in values:
        values.append(code)


def build_portfolio_utility_definition(
    *,
    utility_id: str,
    strategy_id: str,
    lambda_values: Mapping[str, Decimal],
    lambda_justification_refs: Mapping[str, str],
    pre_experiment_approval_ref: str,
    freeze_at_utc: datetime,
    change_policy: str,
    objective_hierarchy: Sequence[str],
    tail_risk_components: Sequence[str],
    return_components: Sequence[str],
    risk_components: Sequence[str],
    drawdown_components: Sequence[str],
    cost_components: Sequence[str],
    capacity_components: Sequence[str],
    liquidity_components: Sequence[str],
    constraint_components: Sequence[str],
    threshold_justification_ref: str,
    approver: str,
    approved_at_utc: datetime,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if not pre_experiment_approval_ref.strip():
        _append_unique(blocker_codes, "optimizer_or_sizing_lockbox_missing")
    if not threshold_justification_ref.strip():
        _append_unique(blocker_codes, "optimizer_or_sizing_lockbox_missing")
    if not lambda_justification_refs:
        _append_unique(blocker_codes, "optimizer_or_sizing_lockbox_missing")
    tail_lower = {item.lower() for item in tail_risk_components}
    if not tail_lower & _TAIL_RISK_TERMS:
        _append_unique(blocker_codes, "tail_risk_missing")
    return {
        "schema_version": "1.0",
        "kind": "portfolio_utility_definition",
        "utility_id": utility_id,
        "strategy_id": strategy_id,
        "lambda_values": {
            str(key): _decimal_str(value) for key, value in lambda_values.items()
        },
        "lambda_justification_refs": {
            str(key): str(value) for key, value in lambda_justification_refs.items()
        },
        "pre_experiment_approval_ref": pre_experiment_approval_ref,
        "freeze_at_utc": _utc_iso(freeze_at_utc),
        "change_policy": change_policy,
        "objective_hierarchy": list(objective_hierarchy),
        "tail_risk_components": list(tail_risk_components),
        "return_components": list(return_components),
        "risk_components": list(risk_components),
        "drawdown_components": list(drawdown_components),
        "cost_components": list(cost_components),
        "capacity_components": list(capacity_components),
        "liquidity_components": list(liquidity_components),
        "constraint_components": list(constraint_components),
        "threshold_justification_ref": threshold_justification_ref,
        "approver": approver,
        "approved_at_utc": _utc_iso(approved_at_utc),
        "blocker_codes": blocker_codes,
    }


def build_optimizer_validation_report(
    *,
    report_id: str,
    strategy_id: str,
    utility_definition_ref: str,
    candidate_baselines: Sequence[str],
    tested_baselines: Sequence[str],
    excluded_baselines: Sequence[str],
    excluded_baseline_approval_refs: Mapping[str, str],
    lockbox_status: str,
    paired_oos_utility_lower_ci: Decimal,
    paired_oos_utility_threshold: Decimal,
    no_alpha_pipeline_status: str,
    perturbation_status: str,
    covariance_drift_status: str,
    turnover_status: str,
    max_adjacent_decision_turnover: Decimal,
    observed_adjacent_turnover: Decimal,
    cost_capacity_report_refs: Sequence[str],
    expected_return_status: str,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if lockbox_status == "missing":
        _append_unique(blocker_codes, "optimizer_or_sizing_lockbox_missing")
    excluded = set(excluded_baselines)
    tested_set = set(tested_baselines)
    for baseline in REQUIRED_BASELINES:
        approved = bool(excluded_baseline_approval_refs.get(baseline, "").strip())
        if baseline in excluded and not approved:
            _append_unique(blocker_codes, "applicable_baseline_excluded")
            break
        if baseline not in tested_set and not (baseline in excluded and approved):
            _append_unique(blocker_codes, "applicable_baseline_excluded")
            break
    if paired_oos_utility_lower_ci <= paired_oos_utility_threshold:
        _append_unique(blocker_codes, "paired_oos_utility_failed")
    if no_alpha_pipeline_status != "null_passed":
        _append_unique(blocker_codes, "no_alpha_pipeline_edge")
    if perturbation_status == "unstable":
        _append_unique(blocker_codes, "optimizer_perturbation_unstable")
    if covariance_drift_status == "drift_unresolved":
        _append_unique(blocker_codes, "covariance_drift_unresolved")
    if turnover_status == "exceeds_cap":
        _append_unique(blocker_codes, "turnover_cap_exceeded")
    if (
        max_adjacent_decision_turnover > Decimal("0")
        and observed_adjacent_turnover > max_adjacent_decision_turnover
    ):
        _append_unique(blocker_codes, "turnover_cap_exceeded")
    if expected_return_status not in {"promotion_valid", "uncertainty_penalized"}:
        _append_unique(blocker_codes, "expected_return_not_promotion_valid")
    if not cost_capacity_report_refs:
        _append_unique(blocker_codes, "execution_semantics_incomplete")
    promotion_valid = not blocker_codes
    evidence_class = "promotion_valid" if promotion_valid else "exploratory"
    return {
        "schema_version": "1.0",
        "kind": "optimizer_validation_report",
        "report_id": report_id,
        "strategy_id": strategy_id,
        "utility_definition_ref": utility_definition_ref,
        "candidate_baselines": list(candidate_baselines),
        "tested_baselines": list(tested_baselines),
        "excluded_baselines": list(excluded_baselines),
        "excluded_baseline_approval_refs": {
            str(key): str(value)
            for key, value in excluded_baseline_approval_refs.items()
        },
        "lockbox_status": lockbox_status,
        "paired_oos_utility_lower_ci": _decimal_str(paired_oos_utility_lower_ci),
        "paired_oos_utility_threshold": _decimal_str(paired_oos_utility_threshold),
        "no_alpha_pipeline_status": no_alpha_pipeline_status,
        "perturbation_status": perturbation_status,
        "covariance_drift_status": covariance_drift_status,
        "turnover_status": turnover_status,
        "max_adjacent_decision_turnover": _decimal_str(max_adjacent_decision_turnover),
        "observed_adjacent_turnover": _decimal_str(observed_adjacent_turnover),
        "cost_capacity_report_refs": list(cost_capacity_report_refs),
        "expected_return_status": expected_return_status,
        "evidence_class": evidence_class,
        "promotion_valid": promotion_valid,
        "blocker_codes": blocker_codes,
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_optimizer_fallback_record(
    *,
    record_id: str,
    strategy_id: str,
    fallback_reason: str,
    fallback_at_utc: datetime,
    static_blueprint_ref: str,
    operator_alert_ref: str,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if not static_blueprint_ref.strip():
        _append_unique(blocker_codes, "optimizer_or_sizing_lockbox_missing")
    if not operator_alert_ref.strip():
        _append_unique(blocker_codes, "optimizer_or_sizing_lockbox_missing")
    return {
        "schema_version": "1.0",
        "kind": "optimizer_fallback_record",
        "record_id": record_id,
        "strategy_id": strategy_id,
        "fallback_reason": fallback_reason,
        "fallback_at_utc": _utc_iso(fallback_at_utc),
        "static_blueprint_ref": static_blueprint_ref,
        "operator_alert_ref": operator_alert_ref,
        "blocker_codes": blocker_codes,
    }


__all__ = (
    "REQUIRED_BASELINES",
    "build_optimizer_fallback_record",
    "build_optimizer_validation_report",
    "build_portfolio_utility_definition",
)
