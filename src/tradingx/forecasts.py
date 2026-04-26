"""Wave 6 forecast governance, expected-return, and sizing-policy artifacts.

These builders gate the path from raw forecasts to executable size:
``forecast_model_manifest`` registers model identity; ``feature_manifest``
and ``label_definition`` audit feature/label timing; ``expected_return_report``
captures calibration and OOS utility; ``sizing_policy`` binds the final
exposure caps. Each builder returns a schema-conforming payload that
the promotion evaluator can re-derive blockers from.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal


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


def build_feature_manifest(
    *,
    manifest_id: str,
    strategy_id: str,
    feature_definitions: Sequence[str],
    availability_timestamp_policy: str,
    timestamp_source: str,
    decision_timestamp_policy: str,
    lookback_windows: Mapping[str, str],
    lag_policy: str,
    missing_value_policy: str,
    leakage_audit_status: str,
    freeze_at_utc: datetime,
    feature_set_hash: str,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if leakage_audit_status in {"feature_after_decision", "label_overlap"}:
        _append_unique(blocker_codes, "feature_timestamp_unauditable")
    if leakage_audit_status == "not_audited":
        _append_unique(blocker_codes, "feature_timestamp_unauditable")
    if timestamp_source == "unspecified":
        _append_unique(blocker_codes, "feature_timestamp_unauditable")
    return {
        "schema_version": "1.0",
        "kind": "feature_manifest",
        "manifest_id": manifest_id,
        "strategy_id": strategy_id,
        "feature_definitions": list(feature_definitions),
        "availability_timestamp_policy": availability_timestamp_policy,
        "timestamp_source": timestamp_source,
        "decision_timestamp_policy": decision_timestamp_policy,
        "lookback_windows": {
            str(key): str(value) for key, value in lookback_windows.items()
        },
        "lag_policy": lag_policy,
        "missing_value_policy": missing_value_policy,
        "leakage_audit_status": leakage_audit_status,
        "freeze_at_utc": _utc_iso(freeze_at_utc),
        "feature_set_hash": feature_set_hash,
        "blocker_codes": blocker_codes,
    }


def build_label_definition(
    *,
    definition_id: str,
    strategy_id: str,
    target: str,
    horizon: str,
    return_basis: str,
    benchmark_ref: str,
    cost_adjustment: str,
    overlap_policy: str,
    purge_window: str,
    embargo_window: str,
    overlap_status: str,
    label_definition_hash: str,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if overlap_status == "overlapping_unhandled":
        _append_unique(blocker_codes, "feature_timestamp_unauditable")
    return {
        "schema_version": "1.0",
        "kind": "label_definition",
        "definition_id": definition_id,
        "strategy_id": strategy_id,
        "target": target,
        "horizon": horizon,
        "return_basis": return_basis,
        "benchmark_ref": benchmark_ref,
        "cost_adjustment": cost_adjustment,
        "overlap_policy": overlap_policy,
        "purge_window": purge_window,
        "embargo_window": embargo_window,
        "overlap_status": overlap_status,
        "label_definition_hash": label_definition_hash,
        "blocker_codes": blocker_codes,
    }


def build_forecast_model_manifest(
    *,
    manifest_id: str,
    strategy_id: str,
    model_identity: str,
    model_version_hash: str,
    feature_manifest_ref: str,
    label_definition_ref: str,
    training_dataset_ref: str,
    model_class: str,
    horizon: str,
    target_variable: str,
    uncertainty_estimator: str,
    uncertainty_calibrated: bool,
    retraining_cadence: str,
    approved_at_utc: datetime,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if not uncertainty_calibrated:
        _append_unique(blocker_codes, "expected_return_uncertainty_uncalibrated")
        promotion_status = "uncertainty_penalized"
    else:
        promotion_status = "promotion_valid"
    if not feature_manifest_ref.strip() or not label_definition_ref.strip():
        _append_unique(blocker_codes, "feature_timestamp_unauditable")
    return {
        "schema_version": "1.0",
        "kind": "forecast_model_manifest",
        "manifest_id": manifest_id,
        "strategy_id": strategy_id,
        "model_identity": model_identity,
        "model_version_hash": model_version_hash,
        "feature_manifest_ref": feature_manifest_ref,
        "label_definition_ref": label_definition_ref,
        "training_dataset_ref": training_dataset_ref,
        "model_class": model_class,
        "horizon": horizon,
        "target_variable": target_variable,
        "uncertainty_estimator": uncertainty_estimator,
        "uncertainty_calibrated": bool(uncertainty_calibrated),
        "retraining_cadence": retraining_cadence,
        "promotion_status": promotion_status,
        "approved_at_utc": _utc_iso(approved_at_utc),
        "blocker_codes": blocker_codes,
    }


def build_expected_return_report(
    *,
    report_id: str,
    strategy_id: str,
    forecast_model_ref: str,
    mu_hat: Decimal,
    sigma_mu: Decimal,
    uncertainty_penalized_mu: Decimal,
    uncertainty_calibrated: bool,
    prediction_interval_coverage: Decimal,
    calibration_window: str,
    calibration_status: str,
    oos_utility_after_costs: Decimal,
    no_forecast_baseline_utility: Decimal,
    heuristic_baseline_utility: Decimal,
    feature_ablation_status: str,
    regime_split_status: str,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if not uncertainty_calibrated or calibration_status == "uncalibrated":
        _append_unique(blocker_codes, "expected_return_uncertainty_uncalibrated")
    if oos_utility_after_costs <= no_forecast_baseline_utility:
        _append_unique(blocker_codes, "expected_return_not_promotion_valid")
    if oos_utility_after_costs <= heuristic_baseline_utility:
        _append_unique(blocker_codes, "expected_return_not_promotion_valid")
    if blocker_codes:
        promotion_valid = False
        evidence_class = (
            "uncertainty_penalized"
            if "expected_return_uncertainty_uncalibrated" in blocker_codes
            and "expected_return_not_promotion_valid" not in blocker_codes
            else "exploratory"
        )
    else:
        promotion_valid = True
        evidence_class = "promotion_valid"
    return {
        "schema_version": "1.0",
        "kind": "expected_return_report",
        "report_id": report_id,
        "strategy_id": strategy_id,
        "forecast_model_ref": forecast_model_ref,
        "mu_hat": _decimal_str(mu_hat),
        "sigma_mu": _decimal_str(sigma_mu),
        "uncertainty_penalized_mu": _decimal_str(uncertainty_penalized_mu),
        "uncertainty_calibrated": bool(uncertainty_calibrated),
        "prediction_interval_coverage": _decimal_str(prediction_interval_coverage),
        "calibration_window": calibration_window,
        "calibration_status": calibration_status,
        "oos_utility_after_costs": _decimal_str(oos_utility_after_costs),
        "no_forecast_baseline_utility": _decimal_str(no_forecast_baseline_utility),
        "heuristic_baseline_utility": _decimal_str(heuristic_baseline_utility),
        "feature_ablation_status": feature_ablation_status,
        "regime_split_status": regime_split_status,
        "evidence_class": evidence_class,
        "promotion_valid": promotion_valid,
        "blocker_codes": blocker_codes,
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_sizing_policy(
    *,
    policy_id: str,
    strategy_id: str,
    sizing_method: str,
    target_volatility: Decimal,
    position_cap: Decimal,
    sleeve_cap: Decimal,
    gross_exposure_cap: Decimal,
    net_exposure_cap: Decimal,
    leverage_cap: Decimal,
    order_cap: Decimal,
    participation_cap: Decimal,
    drawdown_budget: Decimal,
    cost_model_ref: str,
    capacity_curve_ref: str,
    kelly_disabled: bool,
    kelly_gate_complete: bool,
    max_kelly_multiplier: Decimal,
    freeze_at_utc: datetime,
    sizing_policy_hash: str,
    approved_at_utc: datetime,
    approver: str,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if (
        position_cap <= Decimal("0")
        or sleeve_cap <= Decimal("0")
        or gross_exposure_cap <= Decimal("0")
        or net_exposure_cap <= Decimal("0")
        or leverage_cap <= Decimal("0")
        or order_cap <= Decimal("0")
        or participation_cap <= Decimal("0")
        or drawdown_budget <= Decimal("0")
    ):
        _append_unique(blocker_codes, "hard_exposure_caps_missing")
    if not kelly_disabled and not kelly_gate_complete:
        _append_unique(blocker_codes, "kelly_gate_incomplete")
    if max_kelly_multiplier > Decimal("1") and not kelly_gate_complete:
        _append_unique(blocker_codes, "kelly_gate_incomplete")
    if not cost_model_ref.strip() or not capacity_curve_ref.strip():
        _append_unique(blocker_codes, "execution_semantics_incomplete")
    return {
        "schema_version": "1.0",
        "kind": "sizing_policy",
        "policy_id": policy_id,
        "strategy_id": strategy_id,
        "sizing_method": sizing_method,
        "target_volatility": _decimal_str(target_volatility),
        "position_cap": _decimal_str(position_cap),
        "sleeve_cap": _decimal_str(sleeve_cap),
        "gross_exposure_cap": _decimal_str(gross_exposure_cap),
        "net_exposure_cap": _decimal_str(net_exposure_cap),
        "leverage_cap": _decimal_str(leverage_cap),
        "order_cap": _decimal_str(order_cap),
        "participation_cap": _decimal_str(participation_cap),
        "drawdown_budget": _decimal_str(drawdown_budget),
        "cost_model_ref": cost_model_ref,
        "capacity_curve_ref": capacity_curve_ref,
        "kelly_disabled": bool(kelly_disabled),
        "kelly_gate_complete": bool(kelly_gate_complete),
        "max_kelly_multiplier": _decimal_str(max_kelly_multiplier),
        "freeze_at_utc": _utc_iso(freeze_at_utc),
        "sizing_policy_hash": sizing_policy_hash,
        "approved_at_utc": _utc_iso(approved_at_utc),
        "approver": approver,
        "blocker_codes": blocker_codes,
    }


def assert_sizing_monotonicity(
    *,
    base_size: Decimal,
    candidate_size: Decimal,
    higher_cost: bool = False,
    higher_uncertainty: bool = False,
    lower_capacity: bool = False,
    worse_drawdown: bool = False,
    negative_penalized_edge: bool = False,
    explicit_short_allowed: bool = False,
) -> tuple[str, ...]:
    """Return blocker codes for any sizing-monotonicity violations."""
    violations: list[str] = []
    if higher_cost and candidate_size > base_size:
        _append_unique(violations, "sizing_property_violated")
    if higher_uncertainty and candidate_size > base_size:
        _append_unique(violations, "sizing_property_violated")
    if lower_capacity and candidate_size > base_size:
        _append_unique(violations, "sizing_property_violated")
    if worse_drawdown and candidate_size > base_size:
        _append_unique(violations, "sizing_property_violated")
    if (
        negative_penalized_edge
        and candidate_size > Decimal("0")
        and not explicit_short_allowed
    ):
        _append_unique(violations, "sizing_property_violated")
    return tuple(violations)


class SizingPolicyViolation(RuntimeError):
    """Raised when a runtime sizing decision violates monotonicity.

    Defect 7 — the runtime sizing engine MUST refuse to ship a decision
    whose size has increased while the underlying conditions worsened.
    Callers that catch this exception are expected to:
      - emit ``sizing_property_violated`` into the next decision payload
      - hold the trade and surface the violation through promotion-check
    """

    def __init__(self, violations: tuple[str, ...]) -> None:
        super().__init__(
            "sizing-policy violation: " + ", ".join(violations)
        )
        self.violations = violations


def enforce_sizing_monotonicity_runtime(
    *,
    prior_decision: Mapping[str, object] | None,
    candidate_decision: Mapping[str, object],
) -> tuple[Mapping[str, object], tuple[str, ...]]:
    """Runtime gate around :func:`assert_sizing_monotonicity`.

    Compares the prior decision (or a zero-sized baseline if absent) with
    the candidate decision. Raises :class:`SizingPolicyViolation` when
    the candidate increases size while one of the monotonicity inputs
    (cost / uncertainty / capacity / drawdown / negative penalised edge)
    has worsened. Returns the mutated candidate (with
    ``sizing_property_violated`` added to ``blocker_codes``) and the
    tuple of violation codes for downstream propagation.

    Defect 7 wires this into ``sizing.py`` and ``risk.py`` so the
    monotonicity property is enforced AT RUNTIME, not just in offline
    artifact validation.
    """

    base_size = Decimal(
        str((prior_decision or {}).get("size", "0") if prior_decision else "0")
    )
    candidate_size = Decimal(str(candidate_decision.get("size", "0")))
    higher_cost = bool(candidate_decision.get("higher_cost", False))
    higher_uncertainty = bool(candidate_decision.get("higher_uncertainty", False))
    lower_capacity = bool(candidate_decision.get("lower_capacity", False))
    worse_drawdown = bool(candidate_decision.get("worse_drawdown", False))
    negative_penalized_edge = bool(
        candidate_decision.get("negative_penalized_edge", False)
    )
    explicit_short_allowed = bool(
        candidate_decision.get("explicit_short_allowed", False)
    )
    violations = assert_sizing_monotonicity(
        base_size=base_size,
        candidate_size=candidate_size,
        higher_cost=higher_cost,
        higher_uncertainty=higher_uncertainty,
        lower_capacity=lower_capacity,
        worse_drawdown=worse_drawdown,
        negative_penalized_edge=negative_penalized_edge,
        explicit_short_allowed=explicit_short_allowed,
    )
    if not violations:
        return candidate_decision, ()
    next_payload = dict(candidate_decision)
    blocker_codes = list(next_payload.get("blocker_codes", []) or [])
    for code in violations:
        if code not in blocker_codes:
            blocker_codes.append(code)
    next_payload["blocker_codes"] = blocker_codes
    raise SizingPolicyViolation(violations)


__all__ = (
    "assert_sizing_monotonicity",
    "enforce_sizing_monotonicity_runtime",
    "SizingPolicyViolation",
    "build_expected_return_report",
    "build_feature_manifest",
    "build_forecast_model_manifest",
    "build_label_definition",
    "build_sizing_policy",
)
