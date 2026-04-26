"""Wave 9 red tests for recertification and change-control governance."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from tradingx.authority import validate_quant_artifact
from tradingx.change_control import (
    build_change_control_record,
    build_drift_monitor_report,
    build_drift_monitor_spec,
    build_production_decay_event,
    build_recertification_report,
    build_replay_equivalence_report,
    detect_unrecorded_change,
)
from tradingx.promotion import (
    PromotionState,
    evaluate_change_control_blockers,
    strictest_state_cap,
)

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "quant"
NOW = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=30)
EARLIER = NOW - timedelta(days=30)


def _schema(name: str) -> dict[str, object]:
    payload = json.loads((SCHEMA_ROOT / f"{name}.schema.json").read_text())
    assert isinstance(payload, dict)
    return payload


def _change(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "change_id": "chg-001",
        "change_type": "code",
        "change_scope": "feature_set",
        "unknown_scope": False,
        "affected_strategies": ["trend-following-v1"],
        "affected_evidence_refs": ["cas://evidence-001"],
        "dependency_index_refs": ["cas://dep-index-001"],
        "automatic_classification": "material",
        "manual_classification": "material",
        "classifier_confidence": Decimal("0.95"),
        "classifier_version": "v1",
        "change_hash": "sha256:" + "a" * 64,
        "git_shas": ["abc123"],
        "creator": "ops-lead",
        "schema_compatibility_status": "compatible",
        "approval_ref": "cas://approval-001",
        "created_at_utc": NOW,
    }
    defaults.update(overrides)
    return build_change_control_record(**defaults)  # type: ignore[arg-type]


def _recert(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "report_id": "recert-001",
        "strategy_id": "trend-following-v1",
        "production_state_before": "production",
        "production_state_after": "production",
        "reason": "monthly review",
        "authority_boundary_ref": "cas://ab-001",
        "risk_accepted": True,
        "evidence_refs": ["cas://evidence-001"],
        "freshness_status": "fresh",
        "statistical_status": "valid",
        "cost_capacity_status": "valid",
        "optimizer_status": "valid",
        "live_probe_status": "valid",
        "drift_status": "nominal",
        "incident_status": "resolved",
        "approval_status": "approved",
        "approver": "ops-lead",
        "production_expires_at_utc": LATER,
        "next_operational_review_due_utc": LATER,
        "next_statistical_review_due_utc": LATER,
        "generated_at_utc": NOW,
    }
    defaults.update(overrides)
    return build_recertification_report(**defaults)  # type: ignore[arg-type]


def _drift_spec(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "spec_id": "drift-001",
        "strategy_id": "trend-following-v1",
        "monitored_variables": ["sharpe_drift", "feature_psi"],
        "reference_window": "trailing_252",
        "live_window": "trailing_30",
        "thresholds": {"sharpe_drift": Decimal("0.30"), "feature_psi": Decimal("0.20")},
        "regime_labels": ["calm", "volatile"],
        "multiple_testing_policy": "bonferroni",
        "alert_latency_seconds": 60,
        "missing_data_policy": "halt_on_gap",
        "minimum_sample_requirement": 20,
        "demotion_rules": ["psi>0.2 -> demote", "sharpe drift>0.3 -> halt"],
        "operator_notification_path": "telegram:ops",
        "expires_at_utc": LATER,
    }
    defaults.update(overrides)
    return build_drift_monitor_spec(**defaults)  # type: ignore[arg-type]


# -------------------------------------------------------------
# Schema sanity
# -------------------------------------------------------------


def test_change_control_record_schema_validates() -> None:
    payload = _change()
    validate_quant_artifact(payload, schema=_schema("change_control_record"))
    assert payload["materiality_class"] == "material"


def test_recertification_report_schema_validates() -> None:
    payload = _recert()
    validate_quant_artifact(payload, schema=_schema("recertification_report"))
    assert payload["promotion_valid"] is True


def test_drift_monitor_spec_schema_validates() -> None:
    payload = _drift_spec()
    validate_quant_artifact(payload, schema=_schema("drift_monitor_spec"))


def test_replay_equivalence_report_schema_validates() -> None:
    payload = build_replay_equivalence_report(
        report_id="re-001",
        strategy_id="trend-following-v1",
        old_artifact_ref="cas://old",
        new_artifact_ref="cas://new",
        metric_deltas={"sharpe": Decimal("0.001")},
        decision_deltas=[],
        trade_deltas=[],
        safety_rule_deltas=[],
        materiality_threshold=Decimal("0.10"),
        generated_at_utc=NOW,
    )
    validate_quant_artifact(payload, schema=_schema("replay_equivalence_report"))
    assert payload["equivalence_status"] == "equivalent"


def test_drift_monitor_report_schema_validates() -> None:
    payload = build_drift_monitor_report(
        report_id="drift-rep-001",
        strategy_id="trend-following-v1",
        spec_ref="cas://drift-spec-001",
        monitored_values={
            "sharpe_drift": Decimal("0.1"),
            "feature_psi": Decimal("0.05"),
        },
        threshold_results={"sharpe_drift": "within", "feature_psi": "within"},
        regime_classification="calm",
        missing_data_status="complete",
        multiple_testing_adjustment="bonferroni_applied",
        alerted_at_utc=None,
        demotion_recommendation="no_action",
        evidence_refs=["cas://drift-evidence"],
        generated_at_utc=NOW,
    )
    validate_quant_artifact(payload, schema=_schema("drift_monitor_report"))


def test_production_decay_event_schema_validates() -> None:
    payload = build_production_decay_event(
        event_id="decay-001",
        strategy_id="trend-following-v1",
        decay_reason="production_expired",
        previous_state="production",
        new_state="paper_trading",
        triggering_artifact_ref="cas://recert-001",
        occurred_at_utc=NOW,
        operator_notification_status="sent",
    )
    validate_quant_artifact(payload, schema=_schema("production_decay_event"))


# -------------------------------------------------------------
# Required Wave 9 red tests
# -------------------------------------------------------------


def test_current_hash_differs_without_change_record_yields_unrecorded() -> None:
    blockers = detect_unrecorded_change(
        current_hash="sha256:current",
        approved_hash="sha256:approved",
        change_record_present=False,
    )
    assert "unrecorded_material_change" in blockers


def test_unknown_change_scope_defaults_critical() -> None:
    payload = _change(
        unknown_scope=True,
        manual_classification="",
        automatic_classification="minor",
    )
    assert payload["materiality_class"] == "critical"
    assert "unrecorded_material_change" in payload["blocker_codes"]


def test_dependency_scope_unresolved_blocks_production() -> None:
    payload = _change(dependency_index_refs=[])
    assert "dependency_scope_unresolved" in payload["blocker_codes"]


def test_production_approval_expires_and_decays() -> None:
    payload = _recert(production_expires_at_utc=EARLIER)
    blockers = evaluate_change_control_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "production_approval_expired" in codes


def test_drift_monitor_spec_missing_yields_drift_monitor_spec_missing() -> None:
    payload = _drift_spec(monitored_variables=[])
    blockers = evaluate_change_control_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "drift_monitor_spec_missing" in codes


def test_replay_equivalence_fails_when_material_default_fires() -> None:
    payload = build_replay_equivalence_report(
        report_id="re-002",
        strategy_id="trend-following-v1",
        old_artifact_ref="cas://old",
        new_artifact_ref="cas://new",
        metric_deltas={"sharpe": Decimal("0.30")},
        decision_deltas=[],
        trade_deltas=[],
        safety_rule_deltas=[],
        materiality_threshold=Decimal("0.10"),
        generated_at_utc=NOW,
    )
    assert payload["equivalence_status"] == "non_equivalent"
    assert "unrecorded_material_change" in payload["blocker_codes"]


def test_manual_exception_cannot_extend_production_indefinitely() -> None:
    """A recertification report with an expired production_expires_at_utc
    fires `production_approval_expired` regardless of the approver's
    self-asserted `approval_status`. Manual operator override of the
    expiry timestamp is therefore impossible."""

    payload = _recert(
        production_expires_at_utc=EARLIER,
        approval_status="approved",
        risk_accepted=True,
    )
    blockers = evaluate_change_control_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "production_approval_expired" in codes


# -------------------------------------------------------------
# Adversarial re-derivation
# -------------------------------------------------------------


def test_evaluator_re_derives_unrecorded_material_change_from_critical() -> None:
    payload = dict(_change())
    payload["materiality_class"] = "critical"
    payload["blocker_codes"] = []
    blockers = evaluate_change_control_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "unrecorded_material_change" in codes


def test_evaluator_re_derives_drift_alarm_live_from_demotion_recommendation() -> None:
    payload = build_drift_monitor_report(
        report_id="drift-rep-002",
        strategy_id="trend-following-v1",
        spec_ref="cas://drift-spec",
        monitored_values={"sharpe_drift": Decimal("0.5")},
        threshold_results={"sharpe_drift": "exceeds"},
        regime_classification="volatile",
        missing_data_status="complete",
        multiple_testing_adjustment="bonferroni_applied",
        alerted_at_utc=NOW,
        demotion_recommendation="halt",
        evidence_refs=["cas://drift-evidence"],
        generated_at_utc=NOW,
    )
    payload["blocker_codes"] = []
    blockers = evaluate_change_control_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "drift_alarm_live" in codes


def test_evaluator_re_derives_breaking_schema_no_migration() -> None:
    payload = dict(_change())
    payload["schema_compatibility_status"] = "breaking_no_migration"
    payload["blocker_codes"] = []
    blockers = evaluate_change_control_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "unrecorded_material_change" in codes


def test_recertification_with_expired_review_caps_at_paper_trading() -> None:
    payload = _recert(next_operational_review_due_utc=EARLIER)
    blockers = evaluate_change_control_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "next_review_due_passed" in codes
    cap = strictest_state_cap(blockers)
    assert cap == PromotionState.PAPER_TRADING


def test_recertification_without_authority_boundary_blocks() -> None:
    payload = _recert(authority_boundary_ref="")
    blockers = evaluate_change_control_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "authority_boundary_missing" in codes


def test_recertification_report_with_mismatched_change_id_blocks_production() -> None:
    """Defect 3 — recertification_report.change_id must match an open change.

    A bundle whose change_control_record requires recertification on
    ``chg-real`` but whose recertification_report references ``chg-stale``
    must NOT be promotable: the report does not certify any actual change.
    """

    open_change = _change(change_id="chg-real")  # material -> recert required
    stale_recert = _recert(change_id="chg-stale")
    blockers = evaluate_change_control_blockers(
        artifact_payloads=(open_change, stale_recert)
    )
    codes = [blocker.code for blocker in blockers]
    assert "recertification_report_missing" in codes
    cap = strictest_state_cap(blockers)
    assert cap != PromotionState.PRODUCTION


def test_recertification_report_with_aligned_change_id_passes() -> None:
    """Sanity: matching change_id does NOT fire the cross-bundle blocker."""

    open_change = _change(change_id="chg-real")
    aligned_recert = _recert(change_id="chg-real")
    blockers = evaluate_change_control_blockers(
        artifact_payloads=(open_change, aligned_recert)
    )
    codes = [blocker.code for blocker in blockers]
    assert "recertification_report_missing" not in codes
