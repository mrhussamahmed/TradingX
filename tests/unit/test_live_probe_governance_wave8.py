"""Wave 8 red tests for live-probe and operational-safety governance."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from tradingx.authority import validate_quant_artifact
from tradingx.live_probe_governance import (
    build_authority_boundary,
    build_broker_timeout_state_transition,
    build_live_probe_plan,
    build_live_probe_recertification_report,
    build_live_probe_run_record,
    build_operational_safety_drill,
    build_pre_trade_control_manifest,
    build_reconciliation_incident,
    build_runtime_override_event,
)
from tradingx.promotion import (
    PromotionState,
    evaluate_live_probe_blockers,
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


def _authority(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "boundary_id": "ab-001",
        "approval_type": "live_probe",
        "identity_provider": "internal",
        "operator_identity_ids": ["op-001", "op-002"],
        "role_registry_version": "v1",
        "role": "ops-lead",
        "scope": "live_probe",
        "write_authorization_status": "authorized",
        "max_exception_duration_seconds": 3600,
        "second_approver_required": True,
        "approvers": ["op-001", "op-002"],
        "canonical_approval_payload_hash": "sha256:" + "a" * 64,
        "signatures": ["sig-001", "sig-002"],
        "approved_at_utc": NOW,
        "expires_at_utc": LATER,
    }
    defaults.update(overrides)
    return build_authority_boundary(**defaults)  # type: ignore[arg-type]


def _pre_trade(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "manifest_id": "ptc-001",
        "strategy_id": "trend-following-v1",
        "broker_id": "alpaca",
        "broker_mode": "live_probe",
        "price_collar_bps": Decimal("150"),
        "fat_finger_notional_limit": Decimal("10000"),
        "fat_finger_share_limit": Decimal("1000"),
        "max_open_orders": 5,
        "max_order_rate_per_minute": 10,
        "duplicate_prevention_enabled": True,
        "idempotency_key_policy": "intent_hash_plus_client_order_id",
        "cancel_on_disconnect": True,
        "self_trade_prevention": "enabled",
        "buying_power_precheck": True,
        "margin_precheck": True,
        "locate_precheck_for_shorts": True,
        "reject_on_missing_control": True,
        "control_owner": "ops-lead",
        "drill_refs": ["cas://drill-001"],
        "approved_at_utc": NOW,
        "expires_at_utc": LATER,
    }
    defaults.update(overrides)
    return build_pre_trade_control_manifest(**defaults)  # type: ignore[arg-type]


def _drill(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "drill_id": "drl-001",
        "drill_type": "kill_switch",
        "expected_behavior": "halt all orders",
        "observed_behavior": "halted all orders",
        "passed": True,
        "executed_at_utc": NOW,
        "freshness_window_seconds": 86400,
        "evidence_refs": ["cas://drill-evidence-001"],
    }
    defaults.update(overrides)
    return build_operational_safety_drill(**defaults)  # type: ignore[arg-type]


def _plan(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "plan_id": "lp-001",
        "strategy_id": "trend-following-v1",
        "broker_id": "alpaca",
        "broker_mode": "live_probe",
        "symbols": ["SPY"],
        "capital_limit": Decimal("1000"),
        "loss_limit": Decimal("100"),
        "order_count_limit": 50,
        "participation_limit": Decimal("0.01"),
        "spread_limit_bps": Decimal("50"),
        "duration_seconds": 86400,
        "minimum_order_count": 10,
        "minimum_filled_notional": Decimal("500"),
        "minimum_reconciliation_cycles": 3,
        "minimum_sessions": 1,
        "no_signal_outcome_policy": "inconclusive",
        "start_criteria": ["market_open", "kill_switch_armed"],
        "success_criteria": ["all_fills_reconciled", "no_breach"],
        "rollback_criteria": ["loss_breach", "operator_kill"],
        "flatten_policy": "market_orders_to_zero",
        "kill_switch_required": True,
        "pre_trade_control_manifest_ref": "cas://ptc-001",
        "authority_boundary_ref": "cas://ab-001",
        "approved_at_utc": NOW,
        "expires_at_utc": LATER,
    }
    defaults.update(overrides)
    return build_live_probe_plan(**defaults)  # type: ignore[arg-type]


# -------------------------------------------------------------
# Schema sanity
# -------------------------------------------------------------


def test_authority_boundary_schema_validates() -> None:
    payload = _authority()
    validate_quant_artifact(payload, schema=_schema("authority_boundary"))
    assert payload["blocker_codes"] == []


def test_pre_trade_control_manifest_schema_validates() -> None:
    payload = _pre_trade()
    validate_quant_artifact(payload, schema=_schema("pre_trade_control_manifest"))
    assert payload["blocker_codes"] == []


def test_operational_safety_drill_schema_validates() -> None:
    payload = _drill()
    validate_quant_artifact(payload, schema=_schema("operational_safety_drill"))


def test_live_probe_plan_schema_validates() -> None:
    payload = _plan()
    validate_quant_artifact(payload, schema=_schema("live_probe_plan"))
    assert payload["blocker_codes"] == []


def test_live_probe_run_record_schema_validates() -> None:
    payload = build_live_probe_run_record(
        run_id="lpr-001",
        plan_id="lp-001",
        strategy_id="trend-following-v1",
        status="pass",
        order_count=20,
        fill_count=20,
        filled_notional=Decimal("800"),
        session_count=2,
        reconciliation_cycle_count=4,
        slippage_summary_ref="cas://slip-001",
        quote_quality_summary_ref="cas://qq-001",
        limit_breach_count=0,
        rollback_triggered=False,
        success_criteria_met=True,
        minimum_activity_met=True,
        evidence_refs=["cas://run-evidence-001"],
        started_at_utc=NOW,
        completed_at_utc=NOW + timedelta(hours=1),
    )
    validate_quant_artifact(payload, schema=_schema("live_probe_run_record"))


def test_recertification_report_schema_validates() -> None:
    payload = build_live_probe_recertification_report(
        report_id="rec-001",
        strategy_id="trend-following-v1",
        run_refs=["cas://run-001"],
        incident_refs=[],
        unresolved_incident_refs=[],
        minimum_activity_status="met",
        drill_status="fresh",
        broker_timeout_status="defined",
        idempotency_status="complete",
        reconciliation_status="complete",
        cost_observation_refs=["cas://cost-001"],
        approved_at_utc=NOW,
        approver="ops-lead",
        generated_at_utc=NOW,
    )
    validate_quant_artifact(
        payload, schema=_schema("live_probe_recertification_report")
    )
    assert payload["promotion_valid"] is True


# -------------------------------------------------------------
# Required Wave 8 red tests
# -------------------------------------------------------------


def test_missing_price_collar_yields_pre_trade_control_missing() -> None:
    payload = _pre_trade(price_collar_bps=Decimal("0"))
    assert "pre_trade_control_missing" in payload["blocker_codes"]


def test_expired_live_probe_approval_blocks_live_route() -> None:
    payload = _plan(expires_at_utc=EARLIER)
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "live_probe_plan_expired" in codes


def test_timeout_state_cannot_retry_until_reconciliation() -> None:
    """Retry on a reconcile_required state without recovery is unsafe."""

    payload = build_broker_timeout_state_transition(
        transition_id="bt-001",
        order_id="ord-001",
        intent_id="int-001",
        idempotency_key="key-001",
        retry_sequence=1,
        dedupe_window_seconds=60,
        from_state="ack_unknown",
        to_state="reconcile_required",
        trigger="ack_timeout",
        reconciliation_required=True,
        retry_permitted=True,
        transition_at_utc=NOW,
    )
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "broker_timeout_retry_unsafe" in codes


def test_no_signal_probe_is_inconclusive_unless_extension_predeclared() -> None:
    payload = build_live_probe_run_record(
        run_id="lpr-002",
        plan_id="lp-001",
        strategy_id="trend-following-v1",
        status="inconclusive",
        order_count=0,
        fill_count=0,
        filled_notional=Decimal("0"),
        session_count=1,
        reconciliation_cycle_count=2,
        slippage_summary_ref="",
        quote_quality_summary_ref="",
        limit_breach_count=0,
        rollback_triggered=False,
        success_criteria_met=False,
        minimum_activity_met=False,
        evidence_refs=[],
        started_at_utc=NOW,
        completed_at_utc=NOW + timedelta(hours=1),
    )
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "live_probe_inconclusive" in codes
    assert "live_probe_minimum_activity_unmet" in codes


def test_manual_exception_disabling_kill_switch_is_rejected() -> None:
    """Roadmap §1620-1630: no exception may disable core controls."""

    payload = build_runtime_override_event(
        event_id="ovr-001",
        event_type="operator_exception",
        priority=10,
        action="disable_kill_switch",
        scope="strategy",
        reason="ad hoc test",
        operator="ops-lead",
        authority_boundary_ref="cas://ab-001",
        disabled_controls_requested=["kill_switch"],
        expires_at_utc=LATER,
        occurred_at_utc=NOW,
    )
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "manual_exception_disabled_core_control" in codes


def test_unresolved_reconciliation_incident_blocks_production_eligibility() -> None:
    payload = build_reconciliation_incident(
        incident_id="inc-001",
        strategy_id="trend-following-v1",
        severity="high",
        status="open",
        summary="position mismatch on QQQ",
        first_observed_at_utc=NOW,
        resolved_at_utc=None,
        resolution_action="",
        evidence_refs=["cas://inc-evidence-001"],
    )
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "reconciliation_incident_unresolved" in codes


# -------------------------------------------------------------
# Adversarial re-derivation
# -------------------------------------------------------------


def test_evaluator_re_derives_authority_boundary_invalid() -> None:
    payload = dict(_authority())
    payload["write_authorization_status"] = "not_authorized"
    payload["blocker_codes"] = []
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "authority_boundary_invalid" in codes


def test_evaluator_re_derives_authority_boundary_expired() -> None:
    payload = dict(_authority(expires_at_utc=EARLIER))
    payload["blocker_codes"] = []
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "authority_boundary_expired" in codes


def test_evaluator_re_derives_pre_trade_control_missing() -> None:
    payload = dict(_pre_trade())
    payload["price_collar_bps"] = "0"
    payload["blocker_codes"] = []
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "pre_trade_control_missing" in codes


def test_evaluator_re_derives_safety_drill_stale() -> None:
    payload = dict(_drill())
    payload["is_stale"] = True
    payload["blocker_codes"] = []
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "safety_drill_stale" in codes


def test_run_record_with_status_pass_but_min_activity_unmet_blocks() -> None:
    """A forged status="pass" with `minimum_activity_met=False` must still
    surface `live_probe_inconclusive` (loop-1 finding #3)."""

    payload = build_live_probe_run_record(
        run_id="lpr-bypass",
        plan_id="lp-001",
        strategy_id="trend-following-v1",
        status="pass",
        order_count=2,
        fill_count=2,
        filled_notional=Decimal("50"),
        session_count=1,
        reconciliation_cycle_count=1,
        slippage_summary_ref="cas://slip",
        quote_quality_summary_ref="cas://qq",
        limit_breach_count=0,
        rollback_triggered=False,
        success_criteria_met=True,
        minimum_activity_met=False,
        evidence_refs=["cas://evidence"],
        started_at_utc=NOW,
        completed_at_utc=NOW + timedelta(hours=1),
    )
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "live_probe_inconclusive" in codes
    assert "live_probe_minimum_activity_unmet" in codes


def test_run_record_with_status_fail_blocks() -> None:
    payload = build_live_probe_run_record(
        run_id="lpr-fail",
        plan_id="lp-001",
        strategy_id="trend-following-v1",
        status="fail",
        order_count=20,
        fill_count=20,
        filled_notional=Decimal("800"),
        session_count=2,
        reconciliation_cycle_count=4,
        slippage_summary_ref="cas://slip",
        quote_quality_summary_ref="cas://qq",
        limit_breach_count=3,
        rollback_triggered=True,
        success_criteria_met=False,
        minimum_activity_met=True,
        evidence_refs=["cas://evidence"],
        started_at_utc=NOW,
        completed_at_utc=NOW + timedelta(hours=1),
    )
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "live_probe_inconclusive" in codes


def test_runtime_override_with_disable_action_blocks() -> None:
    """An override with `action="disable_kill_switch"` must trigger the
    core-control disable blocker even when the explicit
    `disabled_controls_requested` list is empty."""

    payload = build_runtime_override_event(
        event_id="ovr-action",
        event_type="operator_exception",
        priority=10,
        action="disable_kill_switch",
        scope="strategy",
        reason="test",
        operator="ops-lead",
        authority_boundary_ref="cas://ab-001",
        disabled_controls_requested=[],
        expires_at_utc=LATER,
        occurred_at_utc=NOW,
    )
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "manual_exception_disabled_core_control" in codes


def test_run_record_without_recertification_blocks_production() -> None:
    """A bundle that includes a run record but no recertification report
    must surface `post_probe_recertification_missing` (loop-1 finding #1)."""

    payload = build_live_probe_run_record(
        run_id="lpr-001",
        plan_id="lp-001",
        strategy_id="trend-following-v1",
        status="pass",
        order_count=20,
        fill_count=20,
        filled_notional=Decimal("800"),
        session_count=2,
        reconciliation_cycle_count=4,
        slippage_summary_ref="cas://slip",
        quote_quality_summary_ref="cas://qq",
        limit_breach_count=0,
        rollback_triggered=False,
        success_criteria_met=True,
        minimum_activity_met=True,
        evidence_refs=["cas://evidence"],
        started_at_utc=NOW,
        completed_at_utc=NOW + timedelta(hours=1),
    )
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "post_probe_recertification_missing" in codes


def test_recertification_with_unresolved_incidents_caps_at_paper_trading() -> None:
    payload = build_live_probe_recertification_report(
        report_id="rec-002",
        strategy_id="trend-following-v1",
        run_refs=["cas://run-001"],
        incident_refs=["cas://inc-001"],
        unresolved_incident_refs=["cas://inc-001"],
        minimum_activity_status="met",
        drill_status="fresh",
        broker_timeout_status="defined",
        idempotency_status="complete",
        reconciliation_status="complete",
        cost_observation_refs=["cas://cost-001"],
        approved_at_utc=NOW,
        approver="ops-lead",
        generated_at_utc=NOW,
    )
    blockers = evaluate_live_probe_blockers(artifact_payloads=(payload,))
    codes = {blocker.code for blocker in blockers}
    assert "reconciliation_incident_unresolved" in codes
    cap = strictest_state_cap(blockers)
    assert cap == PromotionState.PAPER_TRADING


def test_recertification_report_with_stale_run_refs_blocks_live_probe_promotion() -> (
    None
):
    """Defect 3 — recertification.run_refs must cover every live_probe_run_record.

    A bundle whose live_probe_run_record reports run-id ``run-real`` but
    whose recertification report only references ``run-stale`` does not
    certify the actual probe run, so post-probe recertification cannot
    be considered satisfied.
    """

    run = build_live_probe_run_record(
        run_id="run-real",
        plan_id="lp-001",
        strategy_id="trend-following-v1",
        status="pass",
        order_count=20,
        fill_count=20,
        filled_notional=Decimal("800"),
        session_count=2,
        reconciliation_cycle_count=4,
        slippage_summary_ref="cas://slip-001",
        quote_quality_summary_ref="cas://qq-001",
        limit_breach_count=0,
        rollback_triggered=False,
        success_criteria_met=True,
        minimum_activity_met=True,
        evidence_refs=["cas://run-evidence-001"],
        started_at_utc=NOW,
        completed_at_utc=NOW + timedelta(hours=1),
    )
    stale_recert = build_live_probe_recertification_report(
        report_id="rec-003",
        strategy_id="trend-following-v1",
        run_refs=["run-stale"],
        incident_refs=[],
        unresolved_incident_refs=[],
        minimum_activity_status="met",
        drill_status="fresh",
        broker_timeout_status="defined",
        idempotency_status="complete",
        reconciliation_status="complete",
        cost_observation_refs=["cas://cost-001"],
        approved_at_utc=NOW,
        approver="ops-lead",
        generated_at_utc=NOW,
    )
    blockers = evaluate_live_probe_blockers(
        artifact_payloads=(run, stale_recert)
    )
    codes = [blocker.code for blocker in blockers]
    assert "post_probe_recertification_missing" in codes


def test_recertification_run_refs_match_across_canonical_namespaces() -> None:
    """Defect 3 hardening — namespace alone must not break linkage.

    A live_probe_run_record carries a bare ``run_id`` while a
    recertification_report typically references runs via ``cas://``
    indirection. The cross-bundle check normalises both sides so the
    bundle is linked when the underlying identifier matches.
    """

    run = build_live_probe_run_record(
        run_id="run-real",
        plan_id="lp-001",
        strategy_id="trend-following-v1",
        status="pass",
        order_count=20,
        fill_count=20,
        filled_notional=Decimal("800"),
        session_count=2,
        reconciliation_cycle_count=4,
        slippage_summary_ref="cas://slip-001",
        quote_quality_summary_ref="cas://qq-001",
        limit_breach_count=0,
        rollback_triggered=False,
        success_criteria_met=True,
        minimum_activity_met=True,
        evidence_refs=["cas://run-evidence-001"],
        started_at_utc=NOW,
        completed_at_utc=NOW + timedelta(hours=1),
    )
    cas_recert = build_live_probe_recertification_report(
        report_id="rec-004",
        strategy_id="trend-following-v1",
        run_refs=["cas://run-real"],
        incident_refs=[],
        unresolved_incident_refs=[],
        minimum_activity_status="met",
        drill_status="fresh",
        broker_timeout_status="defined",
        idempotency_status="complete",
        reconciliation_status="complete",
        cost_observation_refs=["cas://cost-001"],
        approved_at_utc=NOW,
        approver="ops-lead",
        generated_at_utc=NOW,
    )
    blockers = evaluate_live_probe_blockers(
        artifact_payloads=(run, cas_recert)
    )
    codes = [blocker.code for blocker in blockers]
    assert "post_probe_recertification_missing" not in codes

