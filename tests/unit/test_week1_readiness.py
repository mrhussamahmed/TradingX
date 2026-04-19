from __future__ import annotations

import json

from tradingx.week1_readiness import build_gates_0001_status


def test_build_gates_0001_status_reads_dry_run_and_ops_artifacts(tmp_path) -> None:
    dry_run_report_path = tmp_path / "dry-run-report-2026-04-20.json"
    dry_run_report_path.write_text(
        json.dumps(
            {
                "blocked_intents": [{"reason": "daily_entry_cap_reached"}],
                "major_path_coverage": {
                    "entry": True,
                    "exit": True,
                    "halt": True,
                    "reject": True,
                    "recovery": True,
                },
                "anomalies": {
                    "unexpected_log_levels": [],
                    "reconciliation_flags": [],
                    "cycle_overruns": [],
                },
            }
        ),
        encoding="utf-8",
    )
    ops_root = tmp_path / "ops"
    ops_root.mkdir(parents=True, exist_ok=True)
    (ops_root / "operator_control_verification.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )
    (ops_root / "premortem_review.json").write_text(
        json.dumps({"reviewers": ["snooze", "solo", "week1"]}),
        encoding="utf-8",
    )
    (ops_root / "sunday_rehearsal.json").write_text(
        json.dumps({"status": "pass"}),
        encoding="utf-8",
    )

    status = build_gates_0001_status(
        dry_run_report_path=dry_run_report_path,
        ops_artifact_root=ops_root,
    )

    assert status["gate_id"] == "GATES-0001"
    assert status["status"] == "pass"
    assert all(status["criteria"].values())
