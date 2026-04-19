from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _read_optional_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json(path)


def build_gates_0001_status(
    *,
    dry_run_report_path: Path,
    ops_artifact_root: Path,
) -> dict[str, Any]:
    report = _load_json(dry_run_report_path)
    operator_control = _read_optional_artifact(
        ops_artifact_root / "operator_control_verification.json"
    )
    premortem_review = _read_optional_artifact(
        ops_artifact_root / "premortem_review.json"
    )
    sunday_rehearsal = _read_optional_artifact(
        ops_artifact_root / "sunday_rehearsal.json"
    )
    reconciliation_review = _read_optional_artifact(
        ops_artifact_root / "reconciliation_review.json"
    )

    blocked_intents = report.get("blocked_intents", [])
    anomalies = report.get("anomalies", {})
    coverage = report.get("major_path_coverage", {})

    criteria = {
        "zero_unhandled_exceptions": not bool(anomalies.get("unexpected_log_levels")),
        "zero_unresolved_reconciliation_discrepancies": not bool(
            reconciliation_review.get("unresolved_discrepancy_count", 0)
            if reconciliation_review is not None
            else len(anomalies.get("reconciliation_flags", ()))
        ),
        "blocked_intents_have_documented_reasons": all(
            bool(str(item.get("reason", "")).strip())
            for item in blocked_intents
            if isinstance(item, dict)
        ),
        "cycles_within_budget": not bool(anomalies.get("cycle_overruns")),
        "operator_control_path_verified": (
            operator_control is not None
            and str(operator_control.get("status", "")) == "pass"
        ),
        "premortem_review_complete": (
            premortem_review is not None
            and tuple(premortem_review.get("reviewers", ()))
            == ("snooze", "solo", "week1")
        ),
        "major_path_coverage_complete": all(
            bool(coverage.get(path_name))
            for path_name in ("entry", "exit", "halt", "reject", "recovery")
        ),
        "sunday_rehearsal_complete": (
            sunday_rehearsal is not None
            and str(sunday_rehearsal.get("status", "")) == "pass"
        ),
    }
    return {
        "gate_id": "GATES-0001",
        "status": "pass" if all(criteria.values()) else "pending",
        "criteria": criteria,
        "dry_run_report_path": str(dry_run_report_path),
        "ops_artifact_root": str(ops_artifact_root),
    }


__all__ = ("build_gates_0001_status",)
