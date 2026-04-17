"""Operator-facing summaries built from persisted evidence artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import cast

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import GateDecisionBrief, GateDecisionCandidateSummary


def _pick_latest_payload(
    payloads: list[dict[str, object]],
    *,
    timestamp_field: str,
) -> dict[str, object] | None:
    if not payloads:
        return None
    return max(payloads, key=lambda payload: str(payload.get(timestamp_field, "")))


def _payload_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item) for item in value)
    return ()


def _required_operator_action(gate_id: str, status: str) -> str:
    if status == "pass":
        return (
            "Review the evidence and decide whether to advance "
            f"beyond Gate {gate_id}."
        )
    if status == "pending":
        return f"Do not advance; collect the missing evidence and rerun Gate {gate_id}."
    return f"Do not advance; address failed criteria and regenerate Gate {gate_id}."


def build_gate_decision_brief(
    *,
    validation_store: FilesystemArtifactStore,
    paper_store: FilesystemArtifactStore,
    gate_id: str | None = None,
) -> GateDecisionBrief:
    validation_reports = validation_store.list_artifact_payloads("validation_reports")
    gate_assessments = validation_store.list_artifact_payloads("gate_assessments")
    if gate_id is not None:
        validation_reports = [
            payload
            for payload in validation_reports
            if str(payload.get("gate_id", "")) == gate_id
        ]
        gate_assessments = [
            payload
            for payload in gate_assessments
            if str(payload.get("gate_id", "")) == gate_id
        ]
    latest_assessment = _pick_latest_payload(
        gate_assessments,
        timestamp_field="recorded_at_utc",
    )
    selected_gate_id = (
        str(latest_assessment["gate_id"])
        if latest_assessment is not None
        else (gate_id or "")
    )
    if not selected_gate_id:
        latest_report = _pick_latest_payload(
            validation_reports,
            timestamp_field="generated_at_utc",
        )
        if latest_report is None:
            raise ValueError(
                "No validation reports are available for a decision brief."
            )
        selected_gate_id = str(latest_report["gate_id"])
    validation_reports = [
        payload
        for payload in validation_reports
        if str(payload.get("gate_id", "")) == selected_gate_id
    ]
    latest_report = _pick_latest_payload(
        validation_reports,
        timestamp_field="generated_at_utc",
    )
    if latest_report is None:
        raise ValueError(
            f"No validation reports are available for gate {selected_gate_id}."
        )
    if latest_assessment is None:
        matching_assessments = [
            payload
            for payload in validation_store.list_artifact_payloads("gate_assessments")
            if str(payload.get("gate_id", "")) == selected_gate_id
        ]
        latest_assessment = _pick_latest_payload(
            matching_assessments,
            timestamp_field="recorded_at_utc",
        )

    paper_report = paper_store.build_operator_evidence_report()
    paper_summary = cast(dict[str, object], paper_report["summary"])
    latest_alerts = paper_store.list_artifact_payloads("operator_alerts")
    latest_alert = _pick_latest_payload(latest_alerts, timestamp_field="sent_at_utc")
    candidate_payloads = cast(
        list[dict[str, object]],
        latest_report.get("candidate_results", []),
    )

    candidate_summaries = tuple(
        GateDecisionCandidateSummary(
            candidate_id=str(candidate["candidate_id"]),
            status=str(candidate["status"]),
            failed_criteria=tuple(
                str(criterion["criterion_id"])
                for criterion in cast(
                    list[dict[str, object]],
                    candidate.get("criteria", []),
                )
                if not bool(criterion.get("passed"))
            ),
            summary=str(candidate["summary"]),
        )
        for candidate in candidate_payloads
    )
    generated_at_utc = datetime.fromisoformat(str(latest_report["generated_at_utc"]))
    status = (
        str(latest_assessment["status"])
        if latest_assessment is not None
        else str(latest_report["status"])
    )
    decision_summary = (
        str(latest_assessment["decision_summary"])
        if latest_assessment is not None
        else str(latest_report["summary"])
    )
    evidence_refs = (
        _payload_strings(latest_assessment.get("evidence_refs", ()))
        if latest_assessment is not None
        else _payload_strings(latest_report.get("evidence_refs", ()))
    )
    latest_cash_raw = str(paper_summary.get("latest_cash", "")).strip()
    latest_equity_raw = str(paper_summary.get("latest_equity", "")).strip()
    return GateDecisionBrief(
        gate_id=selected_gate_id,
        status=status,
        decision_summary=decision_summary,
        required_operator_action=_required_operator_action(selected_gate_id, status),
        generated_at_utc=generated_at_utc,
        evidence_refs=evidence_refs,
        candidate_summaries=candidate_summaries,
        latest_open_positions=_payload_strings(
            paper_summary.get("latest_open_positions", ())
        ),
        latest_cash=Decimal(latest_cash_raw) if latest_cash_raw else None,
        latest_equity=Decimal(latest_equity_raw) if latest_equity_raw else None,
        blocked_trade_count=int(str(paper_summary.get("blocked_trade_count", 0))),
        reconciliation_failure_count=int(
            str(paper_summary.get("reconciliation_failure_count", 0))
        ),
        latest_alert_summary=(
            str(latest_alert["summary"]) if latest_alert is not None else ""
        ),
    )


__all__ = ("build_gate_decision_brief",)
