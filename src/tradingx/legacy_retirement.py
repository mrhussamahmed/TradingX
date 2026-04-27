"""Wave 10 legacy path retirement helpers.

Builds ``legacy_artifact_migration_report`` payloads classifying
existing artifacts as valid/legacy/stale/invalid/manual_review_required.
The classifier is rule-based and can be invoked from a CLI or test
fixture to produce the canonical "what cannot support promotion"
report.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

_PROMOTION_VALID_KINDS: frozenset[str] = frozenset(
    {
        "promotion_evidence",
        "strategy_capability_manifest",
        "promotion_decision",
        "promotion_decision_ledger_record",
        "investment_mandate",
        "benchmark_policy",
        "wealth_thesis",
        "capital_allocation_policy",
        "lower_bound_net_edge_spec",
        "strategy_materiality_policy",
        "instrument_support_package",
        "jurisdiction_account_use_manifest",
        "experiment_registration",
        "experiment_run_record",
        "trial_universe_manifest",
        "dataset_manifest",
        "evidence_dependency_index",
        "data_restatement_report",
        "evidence_invalidation_report",
        "threshold_justification",
        "power_analysis_report",
        "bootstrap_report",
        "paired_benchmark_uncertainty_report",
        "statistical_validation_report",
        "quote_quality_record",
        "execution_cost_observation",
        "cost_model_report",
        "capacity_curve_report",
        "portfolio_utility_definition",
        "optimizer_validation_report",
        "optimizer_fallback_record",
        "forecast_model_manifest",
        "feature_manifest",
        "label_definition",
        "expected_return_report",
        "sizing_policy",
        "short_capability_manifest",
        "borrow_availability_snapshot",
        "short_financing_model",
        "short_risk_report",
        "short_runtime_event",
        "authority_boundary",
        "pre_trade_control_manifest",
        "operational_safety_drill",
        "live_probe_plan",
        "live_probe_run_record",
        "live_probe_recertification_report",
        "broker_timeout_state_transition",
        "runtime_override_event",
        "reconciliation_incident",
        "change_control_record",
        "replay_equivalence_report",
        "recertification_report",
        "drift_monitor_spec",
        "drift_monitor_report",
        "production_decay_event",
    }
)

_LEGACY_KINDS: frozenset[str] = frozenset(
    {
        "gate_assessment",
        "evaluation_evidence",
        "validation_report",
        "gate_decision_brief",
        "replay_slippage_summary",
        "strategy_activation_record",
    }
)


def classify_legacy_artifact(
    payload: Mapping[str, object],
) -> dict[str, str]:
    kind = str(payload.get("kind", "")).strip()
    blocker_codes = payload.get("blocker_codes", ())
    has_blockers = (
        isinstance(blocker_codes, Sequence)
        and not isinstance(blocker_codes, str | bytes)
        and bool(list(blocker_codes))
    )
    if not kind:
        return {
            "artifact_ref": str(payload.get("artifact_ref", "unknown")),
            "classification": "manual_review_required",
            "reason": "kind missing — manual review required",
        }
    if kind in _LEGACY_KINDS:
        return {
            "artifact_ref": str(payload.get("artifact_ref", kind)),
            "classification": "legacy",
            "reason": f"{kind} is a pre-V5 artifact and cannot support promotion",
        }
    if kind == "replay_slippage_summary" and not payload.get("quote_quality_state"):
        return {
            "artifact_ref": str(payload.get("artifact_ref", kind)),
            "classification": "legacy",
            "reason": "replay summary missing wave-5 quote_quality_state",
        }
    if kind not in _PROMOTION_VALID_KINDS:
        return {
            "artifact_ref": str(payload.get("artifact_ref", kind)),
            "classification": "manual_review_required",
            "reason": f"{kind} is not in the promotion-valid kind set",
        }
    if str(payload.get("evidence_class", "")).strip() == "legacy":
        return {
            "artifact_ref": str(payload.get("artifact_ref", kind)),
            "classification": "legacy",
            "reason": "evidence_class explicitly tagged legacy",
        }
    if has_blockers:
        return {
            "artifact_ref": str(payload.get("artifact_ref", kind)),
            "classification": "invalid",
            "reason": "carries unresolved blocker_codes",
        }
    return {
        "artifact_ref": str(payload.get("artifact_ref", kind)),
        "classification": "valid",
        "reason": "promotion-valid V5 artifact",
    }


def build_legacy_artifact_migration_report(
    *,
    report_id: str,
    artifacts: Sequence[Mapping[str, object]],
    generated_at_utc: datetime | None = None,
) -> dict[str, object]:
    classified = [classify_legacy_artifact(artifact) for artifact in artifacts]
    counts: dict[str, int] = {}
    for entry in classified:
        counts[entry["classification"]] = counts.get(entry["classification"], 0) + 1
    blocker_codes: list[str] = []
    if counts.get("legacy", 0) > 0 or counts.get("invalid", 0) > 0:
        blocker_codes.append("legacy_artifacts_detected")
    timestamp = generated_at_utc or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return {
        "schema_version": "1.0",
        "kind": "legacy_artifact_migration_report",
        "report_id": report_id,
        "generated_at_utc": timestamp.astimezone(UTC).isoformat(),
        "classified_artifacts": classified,
        "summary_counts": counts,
        "blocker_codes": blocker_codes,
    }


__all__ = (
    "build_legacy_artifact_migration_report",
    "classify_legacy_artifact",
)
