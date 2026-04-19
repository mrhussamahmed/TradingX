from __future__ import annotations

import json
from datetime import UTC, datetime

from tradingx.runtime_logging import StructuredRuntimeLogger


def test_structured_runtime_logger_writes_jsonl_record_with_required_fields(
    tmp_path,
) -> None:
    logger = StructuredRuntimeLogger(
        component="controller",
        root_dir=tmp_path / "data" / "logs",
        max_bytes=1024,
        retention_count=2,
        now_provider=lambda: datetime(2026, 4, 20, 13, 30, tzinfo=UTC),
    )

    logger.log(
        event_type="decision_recorded",
        severity="info",
        message="Dry-run decision persisted.",
        decision_snapshot_id="snapshot-1",
        cycle_correlation_id="cycle-1",
        fields={"symbol": "SPY", "final_action": "dry_run"},
    )

    log_path = tmp_path / "data" / "logs" / "controller.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["timestamp_utc"] == "2026-04-20T13:30:00+00:00"
    assert payload["component"] == "controller"
    assert payload["event_type"] == "decision_recorded"
    assert payload["severity"] == "info"
    assert payload["message"] == "Dry-run decision persisted."
    assert payload["decision_snapshot_id"] == "snapshot-1"
    assert payload["cycle_correlation_id"] == "cycle-1"
    assert payload["fields"] == {"symbol": "SPY", "final_action": "dry_run"}


def test_structured_runtime_logger_rotates_and_retains_files(tmp_path) -> None:
    logger = StructuredRuntimeLogger(
        component="service",
        root_dir=tmp_path / "data" / "logs",
        max_bytes=180,
        retention_count=2,
        now_provider=lambda: datetime(2026, 4, 20, 13, 30, tzinfo=UTC),
    )

    for index in range(6):
        logger.log(
            event_type="cycle_completed",
            severity="info",
            message=f"Cycle {index} completed with a deliberately long payload.",
            decision_snapshot_id="",
            cycle_correlation_id=f"service-cycle-{index}",
            fields={"cycle_index": index, "status": "executed"},
        )

    root = tmp_path / "data" / "logs"
    assert (root / "service.jsonl").exists()
    assert (root / "service.jsonl.1").exists()
    assert (root / "service.jsonl.2").exists()
    assert not (root / "service.jsonl.3").exists()
