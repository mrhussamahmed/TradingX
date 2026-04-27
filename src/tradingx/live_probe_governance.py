"""Wave 8 live-probe and operational-safety artifacts.

Provides builders for ``authority_boundary``, ``pre_trade_control_manifest``,
``operational_safety_drill``, ``live_probe_plan``, ``live_probe_run_record``,
``live_probe_recertification_report``, ``broker_timeout_state_transition``,
``runtime_override_event``, and ``reconciliation_incident``.

Builders are deterministic given inputs; the promotion evaluator
re-derives blockers from raw fields so a tampered payload claiming
``blocker_codes=[]`` cannot bypass enforcement.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
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


def build_authority_boundary(
    *,
    boundary_id: str,
    approval_type: str,
    identity_provider: str,
    operator_identity_ids: Sequence[str],
    role_registry_version: str,
    role: str,
    scope: str,
    write_authorization_status: str,
    max_exception_duration_seconds: int,
    second_approver_required: bool,
    approvers: Sequence[str],
    canonical_approval_payload_hash: str,
    signatures: Sequence[str],
    approved_at_utc: datetime,
    expires_at_utc: datetime,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    blocker_codes: list[str] = []
    if write_authorization_status != "authorized":
        _append_unique(blocker_codes, "authority_boundary_invalid")
    if expires_at_utc.astimezone(UTC) <= now:
        _append_unique(blocker_codes, "authority_boundary_expired")
    if second_approver_required and (len(approvers) < 2 or len(signatures) < 2):
        _append_unique(blocker_codes, "authority_boundary_invalid")
    return {
        "schema_version": "1.0",
        "kind": "authority_boundary",
        "boundary_id": boundary_id,
        "approval_type": approval_type,
        "identity_provider": identity_provider,
        "operator_identity_ids": list(operator_identity_ids),
        "role_registry_version": role_registry_version,
        "role": role,
        "scope": scope,
        "write_authorization_status": write_authorization_status,
        "max_exception_duration_seconds": int(max_exception_duration_seconds),
        "second_approver_required": bool(second_approver_required),
        "approvers": list(approvers),
        "canonical_approval_payload_hash": canonical_approval_payload_hash,
        "signatures": list(signatures),
        "approved_at_utc": _utc_iso(approved_at_utc),
        "expires_at_utc": _utc_iso(expires_at_utc),
        "blocker_codes": blocker_codes,
    }


def build_pre_trade_control_manifest(
    *,
    manifest_id: str,
    strategy_id: str,
    broker_id: str,
    broker_mode: str,
    price_collar_bps: Decimal,
    fat_finger_notional_limit: Decimal,
    fat_finger_share_limit: Decimal,
    max_open_orders: int,
    max_order_rate_per_minute: int,
    duplicate_prevention_enabled: bool,
    idempotency_key_policy: str,
    cancel_on_disconnect: bool,
    self_trade_prevention: str,
    buying_power_precheck: bool,
    margin_precheck: bool,
    locate_precheck_for_shorts: bool,
    reject_on_missing_control: bool,
    control_owner: str,
    drill_refs: Sequence[str],
    approved_at_utc: datetime,
    expires_at_utc: datetime,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    blocker_codes: list[str] = []
    if price_collar_bps <= Decimal("0"):
        _append_unique(blocker_codes, "pre_trade_control_missing")
    if fat_finger_notional_limit <= Decimal("0"):
        _append_unique(blocker_codes, "pre_trade_control_missing")
    if fat_finger_share_limit <= Decimal("0"):
        _append_unique(blocker_codes, "pre_trade_control_missing")
    if max_open_orders <= 0 or max_order_rate_per_minute <= 0:
        _append_unique(blocker_codes, "pre_trade_control_missing")
    if not duplicate_prevention_enabled:
        _append_unique(blocker_codes, "pre_trade_control_missing")
    if not cancel_on_disconnect:
        _append_unique(blocker_codes, "pre_trade_control_missing")
    if not reject_on_missing_control:
        _append_unique(blocker_codes, "pre_trade_control_missing")
    if expires_at_utc.astimezone(UTC) <= now:
        _append_unique(blocker_codes, "pre_trade_control_missing")
    return {
        "schema_version": "1.0",
        "kind": "pre_trade_control_manifest",
        "manifest_id": manifest_id,
        "strategy_id": strategy_id,
        "broker_id": broker_id,
        "broker_mode": broker_mode,
        "price_collar_bps": _decimal_str(price_collar_bps),
        "fat_finger_notional_limit": _decimal_str(fat_finger_notional_limit),
        "fat_finger_share_limit": _decimal_str(fat_finger_share_limit),
        "max_open_orders": int(max_open_orders),
        "max_order_rate_per_minute": int(max_order_rate_per_minute),
        "duplicate_prevention_enabled": bool(duplicate_prevention_enabled),
        "idempotency_key_policy": idempotency_key_policy,
        "cancel_on_disconnect": bool(cancel_on_disconnect),
        "self_trade_prevention": self_trade_prevention,
        "buying_power_precheck": bool(buying_power_precheck),
        "margin_precheck": bool(margin_precheck),
        "locate_precheck_for_shorts": bool(locate_precheck_for_shorts),
        "reject_on_missing_control": bool(reject_on_missing_control),
        "control_owner": control_owner,
        "drill_refs": list(drill_refs),
        "approved_at_utc": _utc_iso(approved_at_utc),
        "expires_at_utc": _utc_iso(expires_at_utc),
        "blocker_codes": blocker_codes,
    }


def build_operational_safety_drill(
    *,
    drill_id: str,
    drill_type: str,
    expected_behavior: str,
    observed_behavior: str,
    passed: bool,
    executed_at_utc: datetime,
    freshness_window_seconds: int,
    evidence_refs: Sequence[str],
    now_utc: datetime | None = None,
) -> dict[str, object]:
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    valid_until = executed_at_utc + timedelta(seconds=int(freshness_window_seconds))
    is_stale = now > valid_until.astimezone(UTC)
    blocker_codes: list[str] = []
    if not passed:
        _append_unique(blocker_codes, "safety_drill_failed")
    if is_stale:
        _append_unique(blocker_codes, "safety_drill_stale")
    return {
        "schema_version": "1.0",
        "kind": "operational_safety_drill",
        "drill_id": drill_id,
        "drill_type": drill_type,
        "expected_behavior": expected_behavior,
        "observed_behavior": observed_behavior,
        "passed": bool(passed),
        "executed_at_utc": _utc_iso(executed_at_utc),
        "freshness_window_seconds": int(freshness_window_seconds),
        "valid_until_utc": _utc_iso(valid_until),
        "is_stale": bool(is_stale),
        "evidence_refs": list(evidence_refs),
        "blocker_codes": blocker_codes,
    }


def build_live_probe_plan(
    *,
    plan_id: str,
    strategy_id: str,
    broker_id: str,
    broker_mode: str,
    symbols: Sequence[str],
    capital_limit: Decimal,
    loss_limit: Decimal,
    order_count_limit: int,
    participation_limit: Decimal,
    spread_limit_bps: Decimal,
    duration_seconds: int,
    minimum_order_count: int,
    minimum_filled_notional: Decimal,
    minimum_reconciliation_cycles: int,
    minimum_sessions: int,
    no_signal_outcome_policy: str,
    start_criteria: Sequence[str],
    success_criteria: Sequence[str],
    rollback_criteria: Sequence[str],
    flatten_policy: str,
    kill_switch_required: bool,
    pre_trade_control_manifest_ref: str,
    authority_boundary_ref: str,
    approved_at_utc: datetime,
    expires_at_utc: datetime,
    now_utc: datetime | None = None,
) -> dict[str, object]:
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    blocker_codes: list[str] = []
    if not pre_trade_control_manifest_ref.strip():
        _append_unique(blocker_codes, "pre_trade_control_missing")
    if not authority_boundary_ref.strip():
        _append_unique(blocker_codes, "authority_boundary_missing")
    if not kill_switch_required:
        _append_unique(blocker_codes, "pre_trade_control_missing")
    if expires_at_utc.astimezone(UTC) <= now:
        _append_unique(blocker_codes, "live_probe_plan_expired")
    return {
        "schema_version": "1.0",
        "kind": "live_probe_plan",
        "plan_id": plan_id,
        "strategy_id": strategy_id,
        "broker_id": broker_id,
        "broker_mode": broker_mode,
        "symbols": list(symbols),
        "capital_limit": _decimal_str(capital_limit),
        "loss_limit": _decimal_str(loss_limit),
        "order_count_limit": int(order_count_limit),
        "participation_limit": _decimal_str(participation_limit),
        "spread_limit_bps": _decimal_str(spread_limit_bps),
        "duration_seconds": int(duration_seconds),
        "minimum_order_count": int(minimum_order_count),
        "minimum_filled_notional": _decimal_str(minimum_filled_notional),
        "minimum_reconciliation_cycles": int(minimum_reconciliation_cycles),
        "minimum_sessions": int(minimum_sessions),
        "no_signal_outcome_policy": no_signal_outcome_policy,
        "start_criteria": list(start_criteria),
        "success_criteria": list(success_criteria),
        "rollback_criteria": list(rollback_criteria),
        "flatten_policy": flatten_policy,
        "kill_switch_required": bool(kill_switch_required),
        "pre_trade_control_manifest_ref": pre_trade_control_manifest_ref,
        "authority_boundary_ref": authority_boundary_ref,
        "approved_at_utc": _utc_iso(approved_at_utc),
        "expires_at_utc": _utc_iso(expires_at_utc),
        "blocker_codes": blocker_codes,
    }


def build_live_probe_run_record(
    *,
    run_id: str,
    plan_id: str,
    strategy_id: str,
    status: str,
    order_count: int,
    fill_count: int,
    filled_notional: Decimal,
    session_count: int,
    reconciliation_cycle_count: int,
    slippage_summary_ref: str,
    quote_quality_summary_ref: str,
    limit_breach_count: int,
    rollback_triggered: bool,
    success_criteria_met: bool,
    minimum_activity_met: bool,
    evidence_refs: Sequence[str],
    started_at_utc: datetime,
    completed_at_utc: datetime | None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if not minimum_activity_met:
        _append_unique(blocker_codes, "live_probe_minimum_activity_unmet")
        _append_unique(blocker_codes, "live_probe_inconclusive")
    if status in {"inconclusive", "fail", "rolled_back"}:
        _append_unique(blocker_codes, "live_probe_inconclusive")
    return {
        "schema_version": "1.0",
        "kind": "live_probe_run_record",
        "run_id": run_id,
        "plan_id": plan_id,
        "strategy_id": strategy_id,
        "status": status,
        "order_count": int(order_count),
        "fill_count": int(fill_count),
        "filled_notional": _decimal_str(filled_notional),
        "session_count": int(session_count),
        "reconciliation_cycle_count": int(reconciliation_cycle_count),
        "slippage_summary_ref": slippage_summary_ref,
        "quote_quality_summary_ref": quote_quality_summary_ref,
        "limit_breach_count": int(limit_breach_count),
        "rollback_triggered": bool(rollback_triggered),
        "success_criteria_met": bool(success_criteria_met),
        "minimum_activity_met": bool(minimum_activity_met),
        "evidence_refs": list(evidence_refs),
        "started_at_utc": _utc_iso(started_at_utc),
        "completed_at_utc": (
            _utc_iso(completed_at_utc) if completed_at_utc is not None else ""
        ),
        "blocker_codes": blocker_codes,
    }


def build_live_probe_recertification_report(
    *,
    report_id: str,
    strategy_id: str,
    run_refs: Sequence[str],
    incident_refs: Sequence[str],
    unresolved_incident_refs: Sequence[str],
    minimum_activity_status: str,
    drill_status: str,
    broker_timeout_status: str,
    idempotency_status: str,
    reconciliation_status: str,
    cost_observation_refs: Sequence[str],
    approved_at_utc: datetime,
    approver: str,
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if unresolved_incident_refs:
        _append_unique(blocker_codes, "reconciliation_incident_unresolved")
    if minimum_activity_status != "met":
        _append_unique(blocker_codes, "live_probe_minimum_activity_unmet")
    if drill_status != "fresh":
        _append_unique(blocker_codes, "safety_drill_stale")
    if broker_timeout_status != "defined":
        _append_unique(blocker_codes, "broker_timeout_state_machine_missing")
    if idempotency_status != "complete":
        _append_unique(blocker_codes, "idempotency_evidence_missing")
    if reconciliation_status != "complete":
        _append_unique(blocker_codes, "reconciliation_evidence_missing")
    production_eligible = not blocker_codes
    evidence_class = "promotion_valid" if production_eligible else "exploratory"
    return {
        "schema_version": "1.0",
        "kind": "live_probe_recertification_report",
        "report_id": report_id,
        "strategy_id": strategy_id,
        "run_refs": list(run_refs),
        "incident_refs": list(incident_refs),
        "unresolved_incident_refs": list(unresolved_incident_refs),
        "minimum_activity_status": minimum_activity_status,
        "drill_status": drill_status,
        "broker_timeout_status": broker_timeout_status,
        "idempotency_status": idempotency_status,
        "reconciliation_status": reconciliation_status,
        "cost_observation_refs": list(cost_observation_refs),
        "production_eligible": bool(production_eligible),
        "approved_at_utc": _utc_iso(approved_at_utc),
        "approver": approver,
        "evidence_class": evidence_class,
        "promotion_valid": production_eligible,
        "blocker_codes": blocker_codes,
        "generated_at_utc": _utc_iso(generated_at_utc),
    }


def build_broker_timeout_state_transition(
    *,
    transition_id: str,
    order_id: str,
    intent_id: str,
    idempotency_key: str,
    retry_sequence: int,
    dedupe_window_seconds: int,
    from_state: str,
    to_state: str,
    trigger: str,
    reconciliation_required: bool,
    retry_permitted: bool,
    transition_at_utc: datetime,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    # Retry on a non-recovered, reconcile-required state without
    # reconciliation evidence is unsafe.
    if retry_permitted and reconciliation_required and to_state != "recovered":
        _append_unique(blocker_codes, "broker_timeout_retry_unsafe")
    return {
        "schema_version": "1.0",
        "kind": "broker_timeout_state_transition",
        "transition_id": transition_id,
        "order_id": order_id,
        "intent_id": intent_id,
        "idempotency_key": idempotency_key,
        "retry_sequence": int(retry_sequence),
        "dedupe_window_seconds": int(dedupe_window_seconds),
        "from_state": from_state,
        "to_state": to_state,
        "trigger": trigger,
        "reconciliation_required": bool(reconciliation_required),
        "retry_permitted": bool(retry_permitted),
        "transition_at_utc": _utc_iso(transition_at_utc),
        "blocker_codes": blocker_codes,
    }


_CORE_CONTROL_DISABLE_VERBS: frozenset[str] = frozenset(
    {
        "disable_kill_switch",
        "bypass_kill_switch",
        "bypass_pre_trade_control",
        "disable_pre_trade_control",
        "disable_reconciliation",
        "bypass_reconciliation",
        "disable_drawdown_limit",
        "bypass_drawdown_limit",
        "disable_idempotency",
        "bypass_idempotency",
        "disable_cancel_on_disconnect",
    }
)


def build_runtime_override_event(
    *,
    event_id: str,
    event_type: str,
    priority: int,
    action: str,
    scope: str,
    reason: str,
    operator: str,
    authority_boundary_ref: str,
    disabled_controls_requested: Sequence[str],
    expires_at_utc: datetime,
    occurred_at_utc: datetime,
) -> dict[str, object]:
    blocker_codes: list[str] = []
    # No exception may disable core controls — guard against both the
    # explicit "disabled_controls_requested" list and an attempt to encode
    # the disable as a free-form action verb.
    if disabled_controls_requested:
        _append_unique(blocker_codes, "manual_exception_disabled_core_control")
    if action.lower().strip() in _CORE_CONTROL_DISABLE_VERBS:
        _append_unique(blocker_codes, "manual_exception_disabled_core_control")
    if not authority_boundary_ref.strip():
        _append_unique(blocker_codes, "authority_boundary_missing")
    return {
        "schema_version": "1.0",
        "kind": "runtime_override_event",
        "event_id": event_id,
        "event_type": event_type,
        "priority": int(priority),
        "action": action,
        "scope": scope,
        "reason": reason,
        "operator": operator,
        "authority_boundary_ref": authority_boundary_ref,
        "disabled_controls_requested": list(disabled_controls_requested),
        "expires_at_utc": _utc_iso(expires_at_utc),
        "occurred_at_utc": _utc_iso(occurred_at_utc),
        "blocker_codes": blocker_codes,
    }


def build_reconciliation_incident(
    *,
    incident_id: str,
    strategy_id: str,
    severity: str,
    status: str,
    summary: str,
    first_observed_at_utc: datetime,
    resolved_at_utc: datetime | None,
    resolution_action: str,
    evidence_refs: Sequence[str],
) -> dict[str, object]:
    blocker_codes: list[str] = []
    if status != "resolved":
        _append_unique(blocker_codes, "reconciliation_incident_unresolved")
    return {
        "schema_version": "1.0",
        "kind": "reconciliation_incident",
        "incident_id": incident_id,
        "strategy_id": strategy_id,
        "severity": severity,
        "status": status,
        "summary": summary,
        "first_observed_at_utc": _utc_iso(first_observed_at_utc),
        "resolved_at_utc": (
            _utc_iso(resolved_at_utc) if resolved_at_utc is not None else ""
        ),
        "resolution_action": resolution_action,
        "evidence_refs": list(evidence_refs),
        "blocker_codes": blocker_codes,
    }


__all__ = (
    "build_authority_boundary",
    "build_broker_timeout_state_transition",
    "build_live_probe_plan",
    "build_live_probe_recertification_report",
    "build_live_probe_run_record",
    "build_operational_safety_drill",
    "build_pre_trade_control_manifest",
    "build_reconciliation_incident",
    "build_runtime_override_event",
)
