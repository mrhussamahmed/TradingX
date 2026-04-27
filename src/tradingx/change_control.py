"""Wave 9 recertification and change-control artifacts.

Provides builders for ``change_control_record``,
``replay_equivalence_report``, ``recertification_report``,
``drift_monitor_spec``, ``drift_monitor_report``, and
``production_decay_event``. Builders are deterministic given inputs;
the promotion evaluator re-derives blockers from raw fields so a
tampered payload claiming ``blocker_codes=[]`` cannot bypass enforcement.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal

_UNKNOWN_CHANGE_DEFAULT = "critical"


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


def build_change_control_record(
    *,
    change_id: str,
    change_type: str,
    change_scope: str,
    unknown_scope: bool,
    affected_strategies: Sequence[str],
    affected_evidence_refs: Sequence[str],
    dependency_index_refs: Sequence[str],
    automatic_classification: str,
    manual_classification: str,
    classifier_confidence: Decimal,
    classifier_version: str,
    change_hash: str,
    git_shas: Sequence[str],
    creator: str,
    schema_compatibility_status: str,
    approval_ref: str,
    created_at_utc: datetime,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if unknown_scope:
        materiality_class = _UNKNOWN_CHANGE_DEFAULT
    elif manual_classification.strip():
        materiality_class = manual_classification.strip()
    else:
        materiality_class = automatic_classification.strip() or "material"
    if materiality_class not in {"minor", "material", "critical"}:
        materiality_class = "critical"
    if not dependency_index_refs:
        _append_unique(blocker_codes, "dependency_scope_unresolved")
    if materiality_class == "critical":
        _append_unique(blocker_codes, "unrecorded_material_change")
    if schema_compatibility_status == "breaking_no_migration":
        _append_unique(blocker_codes, "unrecorded_material_change")
    replay_required = materiality_class in {"material", "critical"}
    recertification_required = materiality_class in {"material", "critical"}
    return {
        "schema_version": "1.0",
        "kind": "change_control_record",
        "change_id": change_id,
        "change_type": change_type,
        "change_scope": change_scope,
        "unknown_scope": bool(unknown_scope),
        "affected_strategies": list(affected_strategies),
        "affected_evidence_refs": list(affected_evidence_refs),
        "dependency_index_refs": list(dependency_index_refs),
        "materiality_class": materiality_class,
        "automatic_classification": automatic_classification,
        "manual_classification": manual_classification,
        "classifier_confidence": _decimal_str(classifier_confidence),
        "classifier_version": classifier_version,
        "change_hash": change_hash,
        "git_shas": list(git_shas),
        "creator": creator,
        "replay_required": bool(replay_required),
        "recertification_required": bool(recertification_required),
        "schema_compatibility_status": schema_compatibility_status,
        "approval_ref": approval_ref,
        "created_at_utc": _utc_iso(created_at_utc),
        "blocker_codes": blocker_codes,
    }


def build_replay_equivalence_report(
    *,
    report_id: str,
    strategy_id: str,
    old_artifact_ref: str,
    new_artifact_ref: str,
    metric_deltas: Mapping[str, Decimal],
    decision_deltas: Sequence[str],
    trade_deltas: Sequence[str],
    safety_rule_deltas: Sequence[str],
    materiality_threshold: Decimal,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    material_metric_breach = any(
        abs(value) > materiality_threshold for value in metric_deltas.values()
    )
    if material_metric_breach or decision_deltas or trade_deltas or safety_rule_deltas:
        equivalence_status = "non_equivalent"
        _append_unique(blocker_codes, "unrecorded_material_change")
    elif metric_deltas:
        equivalence_status = "equivalent"
    else:
        equivalence_status = "indeterminate"
        _append_unique(blocker_codes, "unrecorded_material_change")
    return {
        "schema_version": "1.0",
        "kind": "replay_equivalence_report",
        "report_id": report_id,
        "strategy_id": strategy_id,
        "old_artifact_ref": old_artifact_ref,
        "new_artifact_ref": new_artifact_ref,
        "metric_deltas": {
            str(key): _decimal_str(value) for key, value in metric_deltas.items()
        },
        "decision_deltas": list(decision_deltas),
        "trade_deltas": list(trade_deltas),
        "safety_rule_deltas": list(safety_rule_deltas),
        "equivalence_status": equivalence_status,
        "blocker_codes": blocker_codes,
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_recertification_report(
    *,
    report_id: str,
    strategy_id: str,
    production_state_before: str,
    production_state_after: str,
    reason: str,
    authority_boundary_ref: str,
    risk_accepted: bool,
    evidence_refs: Sequence[str],
    freshness_status: str,
    statistical_status: str,
    cost_capacity_status: str,
    optimizer_status: str,
    live_probe_status: str,
    drift_status: str,
    incident_status: str,
    approval_status: str,
    approver: str,
    production_expires_at_utc: datetime,
    next_operational_review_due_utc: datetime,
    next_statistical_review_due_utc: datetime,
    change_id: str = "",
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    now = datetime.now(UTC)
    if production_expires_at_utc.astimezone(UTC) <= now:
        _append_unique(blocker_codes, "production_approval_expired")
    if next_operational_review_due_utc.astimezone(UTC) <= now:
        _append_unique(blocker_codes, "next_review_due_passed")
    if next_statistical_review_due_utc.astimezone(UTC) <= now:
        _append_unique(blocker_codes, "next_review_due_passed")
    if not authority_boundary_ref.strip():
        _append_unique(blocker_codes, "authority_boundary_missing")
    if approval_status != "approved":
        _append_unique(blocker_codes, "recertification_report_missing")
    for status, blocker in (
        (freshness_status, "stale_sources"),
        (drift_status, "drift_alarm_live"),
        (incident_status, "reconciliation_incident_unresolved"),
    ):
        if status in {"stale", "active", "open"}:
            _append_unique(blocker_codes, blocker)
    promotion_valid = not blocker_codes
    evidence_class = "promotion_valid" if promotion_valid else "exploratory"
    return {
        "schema_version": "1.0",
        "kind": "recertification_report",
        "report_id": report_id,
        "strategy_id": strategy_id,
        "production_state_before": production_state_before,
        "production_state_after": production_state_after,
        "reason": reason,
        "authority_boundary_ref": authority_boundary_ref,
        "risk_accepted": bool(risk_accepted),
        "evidence_refs": list(evidence_refs),
        "freshness_status": freshness_status,
        "statistical_status": statistical_status,
        "cost_capacity_status": cost_capacity_status,
        "optimizer_status": optimizer_status,
        "live_probe_status": live_probe_status,
        "drift_status": drift_status,
        "incident_status": incident_status,
        "approval_status": approval_status,
        "approver": approver,
        "production_expires_at_utc": _utc_iso(production_expires_at_utc),
        "next_operational_review_due_utc": _utc_iso(next_operational_review_due_utc),
        "next_statistical_review_due_utc": _utc_iso(next_statistical_review_due_utc),
        "change_id": change_id,
        "evidence_class": evidence_class,
        "promotion_valid": promotion_valid,
        "blocker_codes": blocker_codes,
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_drift_monitor_spec(
    *,
    spec_id: str,
    strategy_id: str,
    monitored_variables: Sequence[str],
    reference_window: str,
    live_window: str,
    thresholds: Mapping[str, Decimal],
    regime_labels: Sequence[str],
    multiple_testing_policy: str,
    alert_latency_seconds: int,
    missing_data_policy: str,
    minimum_sample_requirement: int,
    demotion_rules: Sequence[str],
    operator_notification_path: str,
    expires_at_utc: datetime,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if not monitored_variables:
        _append_unique(blocker_codes, "drift_monitor_spec_missing")
    if not thresholds:
        _append_unique(blocker_codes, "drift_monitor_spec_missing")
    if expires_at_utc.astimezone(UTC) <= datetime.now(UTC):
        _append_unique(blocker_codes, "drift_monitor_spec_missing")
    return {
        "schema_version": "1.0",
        "kind": "drift_monitor_spec",
        "spec_id": spec_id,
        "strategy_id": strategy_id,
        "monitored_variables": list(monitored_variables),
        "reference_window": reference_window,
        "live_window": live_window,
        "thresholds": {
            str(key): _decimal_str(value) for key, value in thresholds.items()
        },
        "regime_labels": list(regime_labels),
        "multiple_testing_policy": multiple_testing_policy,
        "alert_latency_seconds": int(alert_latency_seconds),
        "missing_data_policy": missing_data_policy,
        "minimum_sample_requirement": int(minimum_sample_requirement),
        "demotion_rules": list(demotion_rules),
        "operator_notification_path": operator_notification_path,
        "expires_at_utc": _utc_iso(expires_at_utc),
        "blocker_codes": blocker_codes,
    }


def build_drift_monitor_report(
    *,
    report_id: str,
    strategy_id: str,
    spec_ref: str,
    monitored_values: Mapping[str, Decimal],
    threshold_results: Mapping[str, str],
    regime_classification: str,
    missing_data_status: str,
    multiple_testing_adjustment: str,
    alerted_at_utc: datetime | None,
    demotion_recommendation: str,
    evidence_refs: Sequence[str],
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if demotion_recommendation in {"demote_to_paper_shadow", "halt"}:
        _append_unique(blocker_codes, "drift_alarm_live")
    return {
        "schema_version": "1.0",
        "kind": "drift_monitor_report",
        "report_id": report_id,
        "strategy_id": strategy_id,
        "spec_ref": spec_ref,
        "monitored_values": {
            str(key): _decimal_str(value) for key, value in monitored_values.items()
        },
        "threshold_results": {
            str(key): str(value) for key, value in threshold_results.items()
        },
        "regime_classification": regime_classification,
        "missing_data_status": missing_data_status,
        "multiple_testing_adjustment": multiple_testing_adjustment,
        "alerted_at_utc": (
            _utc_iso(alerted_at_utc) if alerted_at_utc is not None else ""
        ),
        "demotion_recommendation": demotion_recommendation,
        "evidence_refs": list(evidence_refs),
        "blocker_codes": blocker_codes,
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_production_decay_event(
    *,
    event_id: str,
    strategy_id: str,
    decay_reason: str,
    previous_state: str,
    new_state: str,
    triggering_artifact_ref: str,
    occurred_at_utc: datetime,
    operator_notification_status: str,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if previous_state != new_state:
        _append_unique(blocker_codes, "production_approval_expired")
    return {
        "schema_version": "1.0",
        "kind": "production_decay_event",
        "event_id": event_id,
        "strategy_id": strategy_id,
        "decay_reason": decay_reason,
        "previous_state": previous_state,
        "new_state": new_state,
        "triggering_artifact_ref": triggering_artifact_ref,
        "occurred_at_utc": _utc_iso(occurred_at_utc),
        "operator_notification_status": operator_notification_status,
        "blocker_codes": blocker_codes,
    }


def detect_unrecorded_change(
    *,
    current_hash: str,
    approved_hash: str,
    change_record_present: bool,
) -> tuple[str, ...]:
    """Helper for runtime/promotion code: compute blockers when current hash
    differs from approved hash without a corresponding change-control record.
    """

    if current_hash != approved_hash and not change_record_present:
        return ("unrecorded_material_change",)
    return ()


__all__ = (
    "build_change_control_record",
    "build_drift_monitor_report",
    "build_drift_monitor_spec",
    "build_production_decay_event",
    "build_recertification_report",
    "build_replay_equivalence_report",
    "detect_unrecorded_change",
)
