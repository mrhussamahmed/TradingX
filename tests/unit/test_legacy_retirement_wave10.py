"""Wave 10 tests for legacy path retirement and hardening."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tradingx.authority import validate_quant_artifact
from tradingx.legacy_retirement import (
    build_legacy_artifact_migration_report,
    classify_legacy_artifact,
)

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "quant"
NOW = datetime(2026, 4, 26, 12, 0, tzinfo=UTC)


def _schema(name: str) -> dict[str, object]:
    payload = json.loads((SCHEMA_ROOT / f"{name}.schema.json").read_text())
    assert isinstance(payload, dict)
    return payload


def test_classify_promotion_valid_artifact() -> None:
    result = classify_legacy_artifact(
        {"kind": "promotion_evidence", "evidence_class": "promotion_valid"}
    )
    assert result["classification"] == "valid"


def test_classify_legacy_kind() -> None:
    result = classify_legacy_artifact({"kind": "gate_assessment"})
    assert result["classification"] == "legacy"


def test_classify_legacy_replay_slippage_without_quote_quality() -> None:
    result = classify_legacy_artifact(
        {"kind": "replay_slippage_summary", "quote_quality_state": ""}
    )
    assert result["classification"] == "legacy"


def test_classify_artifact_with_blockers_is_invalid() -> None:
    result = classify_legacy_artifact(
        {
            "kind": "cost_model_report",
            "blocker_codes": ["unsupported_cost_bucket"],
        }
    )
    assert result["classification"] == "invalid"


def test_classify_unknown_kind_requires_manual_review() -> None:
    result = classify_legacy_artifact({"kind": "ancient_v3_artifact"})
    assert result["classification"] == "manual_review_required"


def test_classify_evidence_class_legacy_is_legacy() -> None:
    result = classify_legacy_artifact(
        {"kind": "cost_model_report", "evidence_class": "legacy"}
    )
    assert result["classification"] == "legacy"


def test_migration_report_schema_validates() -> None:
    report = build_legacy_artifact_migration_report(
        report_id="legacy-001",
        artifacts=[
            {"kind": "promotion_evidence", "artifact_ref": "cas://pe-001"},
            {"kind": "gate_assessment", "artifact_ref": "cas://ga-001"},
            {
                "kind": "replay_slippage_summary",
                "artifact_ref": "cas://replay-001",
                "quote_quality_state": "",
            },
        ],
        generated_at_utc=NOW,
    )
    validate_quant_artifact(report, schema=_schema("legacy_artifact_migration_report"))
    assert report["summary_counts"]["legacy"] == 2
    assert report["summary_counts"]["valid"] == 1
    assert "legacy_artifacts_detected" in report["blocker_codes"]


def test_migration_report_with_only_valid_emits_no_blocker() -> None:
    report = build_legacy_artifact_migration_report(
        report_id="legacy-002",
        artifacts=[
            {"kind": "promotion_evidence", "artifact_ref": "cas://pe-001"},
            {"kind": "experiment_registration", "artifact_ref": "cas://er-001"},
        ],
        generated_at_utc=NOW,
    )
    validate_quant_artifact(report, schema=_schema("legacy_artifact_migration_report"))
    assert report["blocker_codes"] == []


def test_deprecation_legacy_activation_record_cannot_bypass_promotion() -> None:
    """Old `strategy_activation_record` artifacts are classified as legacy
    and cannot be promotion-valid."""

    result = classify_legacy_artifact(
        {"kind": "strategy_activation_record", "artifact_ref": "cas://sa-001"}
    )
    assert result["classification"] == "legacy"


def test_evaluate_legacy_retirement_blockers_surfaces_legacy_artifacts_detected() -> (
    None
):
    """Review finding bug_014 — ``legacy_artifacts_detected`` must be a
    real, reachable blocker. The Wave 10 builder emits it on a contaminated
    bundle and the registry caps it at PAPER_SHADOW, but no evaluator
    consumed ``legacy_artifact_migration_report`` payloads in
    promotion. Promote-the-stub to a real evaluator that re-derives
    the blocker from the report's fields.
    """

    from tradingx.promotion import (
        PromotionState,
        evaluate_legacy_retirement_blockers,
        strictest_state_cap,
    )

    contaminated = build_legacy_artifact_migration_report(
        report_id="legacy-001",
        artifacts=[
            {"kind": "promotion_evidence", "artifact_ref": "cas://pe-001"},
            {"kind": "gate_assessment", "artifact_ref": "cas://ga-001"},
        ],
        generated_at_utc=NOW,
    )
    blockers = evaluate_legacy_retirement_blockers(artifact_payloads=(contaminated,))
    codes = [blocker.code for blocker in blockers]
    assert "legacy_artifacts_detected" in codes
    cap = strictest_state_cap(blockers)
    assert cap == PromotionState.PAPER_SHADOW


def test_evaluate_legacy_retirement_blockers_passes_clean_bundle() -> None:
    """A migration report covering only valid V5 artifacts must NOT emit
    ``legacy_artifacts_detected``."""

    from tradingx.promotion import evaluate_legacy_retirement_blockers

    clean = build_legacy_artifact_migration_report(
        report_id="legacy-002",
        artifacts=[
            {"kind": "promotion_evidence", "artifact_ref": "cas://pe-001"},
            {"kind": "experiment_registration", "artifact_ref": "cas://er-001"},
        ],
        generated_at_utc=NOW,
    )
    blockers = evaluate_legacy_retirement_blockers(artifact_payloads=(clean,))
    assert blockers == ()
