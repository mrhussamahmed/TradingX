"""Wave 6 red tests for portfolio utility, optimizer, forecasts, and sizing."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.authority import validate_quant_artifact
from tradingx.forecasts import (
    assert_sizing_monotonicity,
    build_expected_return_report,
    build_feature_manifest,
    build_forecast_model_manifest,
    build_label_definition,
    build_sizing_policy,
)
from tradingx.portfolio.optimizer import (
    REQUIRED_BASELINES,
    build_optimizer_validation_report,
    build_portfolio_utility_definition,
)
from tradingx.promotion import (
    PromotionState,
    evaluate_forecast_sizing_blockers,
    evaluate_portfolio_optimizer_blockers,
    strictest_state_cap,
)

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "quant"
GENERATED_AT = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def _schema(name: str) -> dict[str, object]:
    payload = json.loads((SCHEMA_ROOT / f"{name}.schema.json").read_text())
    assert isinstance(payload, dict)
    return payload


def _utility(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "utility_id": "util-001",
        "strategy_id": "trend-following-v1",
        "lambda_values": {"return": Decimal("1.0"), "risk": Decimal("0.5")},
        "lambda_justification_refs": {"return": "cas://r-just", "risk": "cas://k-just"},
        "pre_experiment_approval_ref": "cas://pre-experiment-approval",
        "freeze_at_utc": GENERATED_AT,
        "change_policy": "frozen_for_oos",
        "objective_hierarchy": ["return", "risk", "drawdown", "tail"],
        "tail_risk_components": ["cvar"],
        "return_components": ["expected_return"],
        "risk_components": ["covariance"],
        "drawdown_components": ["max_drawdown"],
        "cost_components": ["all_events_stress"],
        "capacity_components": ["lower_bound_capacity"],
        "liquidity_components": ["adv_floor"],
        "constraint_components": ["gross_exposure_cap"],
        "threshold_justification_ref": "cas://threshold",
        "approver": "ops-lead",
        "approved_at_utc": GENERATED_AT,
    }
    defaults.update(overrides)
    return build_portfolio_utility_definition(**defaults)  # type: ignore[arg-type]


def _validation(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "report_id": "opt-val-001",
        "strategy_id": "trend-following-v1",
        "utility_definition_ref": "cas://utility",
        "candidate_baselines": list(REQUIRED_BASELINES),
        "tested_baselines": list(REQUIRED_BASELINES),
        "excluded_baselines": [],
        "excluded_baseline_approval_refs": {},
        "lockbox_status": "frozen",
        "paired_oos_utility_lower_ci": Decimal("0.05"),
        "paired_oos_utility_threshold": Decimal("0.01"),
        "no_alpha_pipeline_status": "null_passed",
        "perturbation_status": "stable",
        "covariance_drift_status": "nominal",
        "turnover_status": "within_cap",
        "max_adjacent_decision_turnover": Decimal("0.20"),
        "observed_adjacent_turnover": Decimal("0.10"),
        "cost_capacity_report_refs": ["cas://cost-001", "cas://capacity-001"],
        "expected_return_status": "promotion_valid",
        "generated_at_utc": GENERATED_AT,
    }
    defaults.update(overrides)
    return build_optimizer_validation_report(**defaults)  # type: ignore[arg-type]


def _expected_return(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "report_id": "er-001",
        "strategy_id": "trend-following-v1",
        "forecast_model_ref": "cas://forecast",
        "mu_hat": Decimal("0.05"),
        "sigma_mu": Decimal("0.01"),
        "uncertainty_penalized_mu": Decimal("0.04"),
        "uncertainty_calibrated": True,
        "prediction_interval_coverage": Decimal("0.95"),
        "calibration_window": "rolling_252",
        "calibration_status": "calibrated",
        "oos_utility_after_costs": Decimal("0.10"),
        "no_forecast_baseline_utility": Decimal("0.05"),
        "heuristic_baseline_utility": Decimal("0.06"),
        "feature_ablation_status": "feature_set_validated",
        "regime_split_status": "consistent",
        "generated_at_utc": GENERATED_AT,
    }
    defaults.update(overrides)
    return build_expected_return_report(**defaults)  # type: ignore[arg-type]


def _sizing_policy(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "policy_id": "sizing-001",
        "strategy_id": "trend-following-v1",
        "sizing_method": "vol_target",
        "target_volatility": Decimal("0.12"),
        "position_cap": Decimal("0.05"),
        "sleeve_cap": Decimal("0.20"),
        "gross_exposure_cap": Decimal("1.0"),
        "net_exposure_cap": Decimal("1.0"),
        "leverage_cap": Decimal("1.0"),
        "order_cap": Decimal("0.02"),
        "participation_cap": Decimal("0.05"),
        "drawdown_budget": Decimal("0.05"),
        "cost_model_ref": "cas://cost",
        "capacity_curve_ref": "cas://capacity",
        "kelly_disabled": True,
        "kelly_gate_complete": False,
        "max_kelly_multiplier": Decimal("0"),
        "freeze_at_utc": GENERATED_AT,
        "sizing_policy_hash": "sha256:abc",
        "approved_at_utc": GENERATED_AT,
        "approver": "ops-lead",
    }
    defaults.update(overrides)
    return build_sizing_policy(**defaults)  # type: ignore[arg-type]


# -------------------------------------------------------------
# Schema sanity
# -------------------------------------------------------------


def test_portfolio_utility_definition_validates() -> None:
    payload = _utility()
    validate_quant_artifact(payload, schema=_schema("portfolio_utility_definition"))
    assert payload["blocker_codes"] == []


def test_optimizer_validation_report_validates() -> None:
    payload = _validation()
    validate_quant_artifact(payload, schema=_schema("optimizer_validation_report"))
    assert payload["promotion_valid"] is True


def test_expected_return_report_validates() -> None:
    payload = _expected_return()
    validate_quant_artifact(payload, schema=_schema("expected_return_report"))
    assert payload["promotion_valid"] is True


def test_sizing_policy_validates() -> None:
    payload = _sizing_policy()
    validate_quant_artifact(payload, schema=_schema("sizing_policy"))


# -------------------------------------------------------------
# Required Wave 6 red tests
# -------------------------------------------------------------


def test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing() -> None:
    payload = _utility(
        pre_experiment_approval_ref="",
        threshold_justification_ref="",
    )

    blockers = evaluate_portfolio_optimizer_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "optimizer_or_sizing_lockbox_missing" in codes


def test_excluding_equal_weight_without_signed_approval_blocks() -> None:
    payload = _validation(
        excluded_baselines=["equal_weight"],
        excluded_baseline_approval_refs={},
    )
    assert "applicable_baseline_excluded" in payload["blocker_codes"]


def test_no_alpha_full_pipeline_showing_edge_blocks_optimizer_promotion() -> None:
    payload = _validation(no_alpha_pipeline_status="null_edge_detected")
    assert "no_alpha_pipeline_edge" in payload["blocker_codes"]


def test_forecast_feature_timestamp_after_decision_time_blocks() -> None:
    feature_manifest = build_feature_manifest(
        manifest_id="fm-001",
        strategy_id="trend-following-v1",
        feature_definitions=["sma_20"],
        availability_timestamp_policy="prior_close",
        timestamp_source="computation",
        decision_timestamp_policy="next_open",
        lookback_windows={"sma": "20"},
        lag_policy="t-1",
        missing_value_policy="forward_fill",
        leakage_audit_status="feature_after_decision",
        freeze_at_utc=GENERATED_AT,
        feature_set_hash="sha256:fm",
    )
    blockers = evaluate_forecast_sizing_blockers(artifact_payloads=(feature_manifest,))
    codes = {blocker.code for blocker in blockers}
    assert "feature_timestamp_unauditable" in codes


def test_uncalibrated_uncertainty_caps_at_paper_shadow() -> None:
    payload = _expected_return(
        uncertainty_calibrated=False,
        calibration_status="uncalibrated",
    )
    blockers = evaluate_forecast_sizing_blockers(artifact_payloads=(payload,))
    cap = strictest_state_cap(blockers)
    assert cap == PromotionState.PAPER_SHADOW
    assert "expected_return_uncertainty_uncalibrated" in payload["blocker_codes"]


def test_higher_cost_increasing_size_fails_property_test() -> None:
    violations = assert_sizing_monotonicity(
        base_size=Decimal("100"),
        candidate_size=Decimal("150"),
        higher_cost=True,
    )
    assert "sizing_property_violated" in violations


def test_negative_penalized_edge_creating_long_exposure_fails_unless_allowed() -> None:
    violations_blocked = assert_sizing_monotonicity(
        base_size=Decimal("0"),
        candidate_size=Decimal("100"),
        negative_penalized_edge=True,
        explicit_short_allowed=False,
    )
    assert "sizing_property_violated" in violations_blocked

    violations_allowed = assert_sizing_monotonicity(
        base_size=Decimal("0"),
        candidate_size=Decimal("100"),
        negative_penalized_edge=True,
        explicit_short_allowed=True,
    )
    assert violations_allowed == ()


def test_paired_oos_utility_failure_blocks() -> None:
    payload = _validation(
        paired_oos_utility_lower_ci=Decimal("0"),
        paired_oos_utility_threshold=Decimal("0.05"),
    )
    assert "paired_oos_utility_failed" in payload["blocker_codes"]


def test_perturbation_unstable_blocks_promotion() -> None:
    payload = _validation(perturbation_status="unstable")
    assert "optimizer_perturbation_unstable" in payload["blocker_codes"]


def test_evaluator_re_derives_lockbox_missing_from_raw_fields() -> None:
    payload = dict(_utility())
    payload["pre_experiment_approval_ref"] = ""
    payload["blocker_codes"] = []
    blockers = evaluate_portfolio_optimizer_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "optimizer_or_sizing_lockbox_missing" in codes


def test_sizing_policy_missing_hard_caps_blocks_promotion() -> None:
    payload = _sizing_policy(position_cap=Decimal("0"))
    blockers = evaluate_forecast_sizing_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "hard_exposure_caps_missing" in codes


def test_kelly_enabled_without_complete_gate_blocks() -> None:
    payload = _sizing_policy(
        kelly_disabled=False,
        kelly_gate_complete=False,
        max_kelly_multiplier=Decimal("0.5"),
    )
    blockers = evaluate_forecast_sizing_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "kelly_gate_incomplete" in codes


def test_label_overlap_unhandled_blocks() -> None:
    label = build_label_definition(
        definition_id="lbl-001",
        strategy_id="trend-following-v1",
        target="next_day_return",
        horizon="1d",
        return_basis="adjusted_close",
        benchmark_ref="cas://bench",
        cost_adjustment="all_events_stress",
        overlap_policy="none",
        purge_window="1d",
        embargo_window="1d",
        overlap_status="overlapping_unhandled",
        label_definition_hash="sha256:lbl",
    )
    blockers = evaluate_forecast_sizing_blockers(artifact_payloads=(label,))
    codes = {blocker.code for blocker in blockers}
    assert "feature_timestamp_unauditable" in codes


def test_forecast_model_with_uncalibrated_uncertainty_blocks() -> None:
    manifest = build_forecast_model_manifest(
        manifest_id="fm-001",
        strategy_id="trend-following-v1",
        model_identity="ridge_v1",
        model_version_hash="sha256:mv",
        feature_manifest_ref="cas://fm",
        label_definition_ref="cas://lbl",
        training_dataset_ref="cas://train",
        model_class="ridge",
        horizon="1d",
        target_variable="next_day_return",
        uncertainty_estimator="bootstrap",
        uncertainty_calibrated=False,
        retraining_cadence="weekly",
        approved_at_utc=GENERATED_AT,
    )
    blockers = evaluate_forecast_sizing_blockers(artifact_payloads=(manifest,))
    codes = {blocker.code for blocker in blockers}
    assert "expected_return_uncertainty_uncalibrated" in codes


@pytest.mark.parametrize("status", ["null_edge_detected", "not_run"])
def test_no_alpha_pipeline_non_passed_states_block(status: str) -> None:
    """Anything other than `null_passed` is treated as a Wave 6 blocker —
    absence of evidence cannot be evidence of absence (loop-1 finding M4).
    """

    payload = _validation(no_alpha_pipeline_status=status)
    assert "no_alpha_pipeline_edge" in payload["blocker_codes"]


def test_evaluator_re_derives_no_alpha_block_for_not_run() -> None:
    payload = dict(_validation())
    payload["no_alpha_pipeline_status"] = "not_run"
    payload["blocker_codes"] = []
    blockers = evaluate_portfolio_optimizer_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "no_alpha_pipeline_edge" in codes


@pytest.mark.parametrize("omitted_baseline", REQUIRED_BASELINES)
def test_silent_baseline_omission_blocks_promotion(omitted_baseline: str) -> None:
    """A required baseline silently omitted from `tested_baselines` (without
    an approved exclusion) must be flagged — not just explicit exclusion.
    Each of the seven required baselines is exercised independently.
    """

    candidates = [b for b in REQUIRED_BASELINES if b != omitted_baseline]
    payload = _validation(
        candidate_baselines=candidates,
        tested_baselines=candidates,
        excluded_baselines=[],
        excluded_baseline_approval_refs={},
    )
    assert "applicable_baseline_excluded" in payload["blocker_codes"]


def test_evaluator_re_derives_silent_baseline_omission() -> None:
    candidates = [b for b in REQUIRED_BASELINES if b != "equal_weight"]
    payload = dict(_validation())
    payload["tested_baselines"] = candidates
    payload["excluded_baselines"] = []
    payload["blocker_codes"] = []
    blockers = evaluate_portfolio_optimizer_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "applicable_baseline_excluded" in codes


def test_evaluator_re_derives_tail_risk_whitelist() -> None:
    """Tail-risk components must include at least one whitelisted term."""

    payload = dict(_utility())
    payload["tail_risk_components"] = ["volatility"]
    payload["blocker_codes"] = []
    blockers = evaluate_portfolio_optimizer_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "tail_risk_missing" in codes


def test_evaluator_re_derives_turnover_cap_from_decimals() -> None:
    payload = dict(_validation())
    payload["max_adjacent_decision_turnover"] = "0.10"
    payload["observed_adjacent_turnover"] = "0.30"
    payload["turnover_status"] = "within_cap"
    payload["blocker_codes"] = []
    blockers = evaluate_portfolio_optimizer_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "turnover_cap_exceeded" in codes


def test_evaluator_re_derives_cost_capacity_refs_missing() -> None:
    payload = dict(_validation())
    payload["cost_capacity_report_refs"] = []
    payload["blocker_codes"] = []
    blockers = evaluate_portfolio_optimizer_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "execution_semantics_incomplete" in codes


def test_kelly_enabled_evaluator_fails_closed_on_missing_field() -> None:
    payload = dict(_sizing_policy())
    # Simulate a tampered payload that drops `kelly_disabled` entirely.
    payload.pop("kelly_disabled", None)
    payload["blocker_codes"] = []
    blockers = evaluate_forecast_sizing_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "kelly_gate_incomplete" in codes


def test_evaluator_re_derives_drawdown_budget_missing() -> None:
    payload = dict(_sizing_policy())
    payload["drawdown_budget"] = "0"
    payload["blocker_codes"] = []
    blockers = evaluate_forecast_sizing_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "hard_exposure_caps_missing" in codes
