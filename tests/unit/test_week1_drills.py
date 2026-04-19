from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tradingx.week1_drills import run_week1_rehearsal


def test_run_week1_rehearsal_writes_required_artifacts(tmp_path: Path) -> None:
    result = run_week1_rehearsal(
        output_dir=tmp_path / "ops",
        account_state_provider=lambda: {
            "cash": "100000",
            "equity": "100000",
            "buying_power": "200000",
            "positions": [],
            "open_orders": [],
        },
        now_provider=lambda: datetime(2026, 4, 19, 15, 0, tzinfo=UTC),
    )

    assert result["status"] == "pass"
    assert [item["name"] for item in result["drills"]] == [
        "HALT",
        "REJECT",
        "RECOVERY",
    ]
    rehearsal_payload = json.loads(
        (tmp_path / "ops" / "sunday_rehearsal.json").read_text(encoding="utf-8")
    )
    assert rehearsal_payload["status"] == "pass"
    reconciliation_payload = json.loads(
        (tmp_path / "ops" / "reconciliation_review.json").read_text(encoding="utf-8")
    )
    assert reconciliation_payload["unresolved_discrepancy_count"] == 0
    paper_account_payload = json.loads(
        (tmp_path / "ops" / "paper_account_starting_state.json").read_text(
            encoding="utf-8"
        )
    )
    assert paper_account_payload["status"] == "recorded"
