from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tradingx.journal import SqliteOmsJournal
from tradingx.persistence import FilesystemArtifactStore
from tradingx.snapshots import ContentAddressedSnapshotStore


def _pick_latest_snapshot_day(
    snapshots: Sequence[dict[str, Any]],
) -> str:
    if not snapshots:
        return ""
    latest = max(snapshots, key=lambda payload: str(payload.get("timestamp_utc", "")))
    return str(latest.get("timestamp_utc", "")).split("T")[0]


def build_dry_run_report(
    *,
    paper_store: FilesystemArtifactStore,
    snapshot_store: ContentAddressedSnapshotStore,
    journal: SqliteOmsJournal,
) -> dict[str, Any]:
    service_cycles = paper_store.list_artifact_payloads("service_cycles")
    decision_snapshots = snapshot_store.list_decision_snapshot_payloads()
    journal_events = journal.list_events()
    trading_day = _pick_latest_snapshot_day(decision_snapshots)

    cycle_summaries = [
        {
            "cycle_id": str(payload.get("cycle_id", "")),
            "cycle_status": str(payload.get("cycle_status", "")),
            "completed_at_utc": str(payload.get("completed_at_utc", "")),
            "blocked_trade_count": int(payload.get("blocked_trade_count", 0)),
            "reconciliation_failure_count": int(
                payload.get("reconciliation_failure_count", 0)
            ),
        }
        for payload in service_cycles
    ]
    decision_summaries = [
        {
            "decision_snapshot_id": str(payload.get("decision_snapshot_id", "")),
            "timestamp_utc": str(payload.get("timestamp_utc", "")),
            "final_action": str(payload.get("final_action", "")),
            "candidate_count": len(payload.get("candidate_intents", [])),
        }
        for payload in decision_snapshots
    ]

    blocked_intents = []
    no_trade_reasons = []
    for payload in decision_snapshots:
        decision_snapshot_id = str(payload.get("decision_snapshot_id", ""))
        candidate_intents = payload.get("candidate_intents", [])
        if not isinstance(candidate_intents, list):
            continue
        for candidate in candidate_intents:
            if not isinstance(candidate, dict):
                continue
            reason = str(candidate.get("terminal_reason", ""))
            symbol = str(candidate.get("symbol", ""))
            if str(payload.get("final_action", "")) == "blocked_trade":
                blocked_intents.append(
                    {
                        "decision_snapshot_id": decision_snapshot_id,
                        "symbol": symbol,
                        "reason": reason,
                    }
                )
            if str(payload.get("final_action", "")) == "no_trade":
                no_trade_reasons.append(
                    {
                        "decision_snapshot_id": decision_snapshot_id,
                        "symbol": symbol,
                        "reason": reason,
                    }
                )

    simulated_orders = [
        {
            "decision_snapshot_id": event.decision_snapshot_id,
            "client_order_id": event.client_order_id,
            "symbol": event.symbol,
            "side": event.side,
            "quantity": str(event.payload.get("quantity", "")),
            "reason_code": str(event.payload.get("reason_code", "")),
            "reference_price": str(event.payload.get("reference_price", "")),
            "would_submit_limit_price": str(
                event.payload.get("would_submit_limit_price", "")
            ),
        }
        for event in journal_events
        if event.event_type == "simulated"
    ]

    cycle_overruns = [
        str(payload.get("cycle_id", ""))
        for payload in service_cycles
        if str(payload.get("cycle_status", "")) == "cycle_overrun"
    ]
    reconciliation_flags = [
        str(payload.get("cycle_id", ""))
        for payload in service_cycles
        if int(payload.get("reconciliation_failure_count", 0)) > 0
    ]
    halt_reasons = {"daily_drawdown_halt", "daily_drawdown_halt_sticky"}
    reject_events = [event for event in journal_events if event.event_type == "reject"]
    major_path_coverage = {
        "entry": any(order["side"] == "buy" for order in simulated_orders),
        "exit": any(order["side"] == "sell" for order in simulated_orders),
        "halt": any(
            blocked_intent["reason"] in halt_reasons
            for blocked_intent in blocked_intents
        ),
        "reject": bool(reject_events),
        "recovery": bool(reconciliation_flags),
    }

    return {
        "report_id": (
            f"dry-run-report-{trading_day}"
            if trading_day
            else "dry-run-report-unscheduled"
        ),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "trading_day": trading_day,
        "dry_run": any(bool(payload.get("dry_run")) for payload in decision_snapshots),
        "cycle_count": len(service_cycles),
        "cycles": cycle_summaries,
        "decision_snapshots": decision_summaries,
        "blocked_intents": blocked_intents,
        "no_trade_reasons": no_trade_reasons,
        "simulated_orders": simulated_orders,
        "simulated_pnl_vs_spy_buy_hold": {
            "status": "insufficient_simulated_closes",
            "simulated_pnl": "0",
            "benchmark_return": "",
        },
        "major_path_coverage": major_path_coverage,
        "anomalies": {
            "cycle_overruns": cycle_overruns,
            "reconciliation_flags": reconciliation_flags,
            "unexpected_log_levels": [],
        },
    }


def write_dry_run_report(
    *,
    report: dict[str, Any],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_id = str(report.get("report_id", "dry-run-report-unscheduled"))
    path = output_dir / f"{report_id}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


__all__ = ("build_dry_run_report", "write_dry_run_report")
