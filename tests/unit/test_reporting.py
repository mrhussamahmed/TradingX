from __future__ import annotations

import importlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    EvaluationEvidencePack,
    GateAssessment,
    OperatorAlert,
    ServiceCycleSnapshot,
    ServiceSymbolResult,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
)


def test_reporting_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.reporting")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_build_gate_decision_brief_combines_validation_and_paper_evidence(
    tmp_path: Path,
) -> None:
    reporting = importlib.import_module("tradingx.reporting")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)

    validation_store.write_validation_report(
        ValidationReport(
            report_id="gate-1-20260417T180000Z",
            gate_id="1",
            generated_at_utc=timestamp,
            status="pass",
            benchmark_symbol="SPY",
            window_start_utc=datetime(2023, 1, 1, tzinfo=UTC),
            window_end_utc=timestamp,
            candidate_results=(
                ValidationCandidateResult(
                    candidate_id="trend-following-v1",
                    gate_id="1",
                    status="pass",
                    evidence_pack_id="evaluation-1",
                    criteria=(
                        ValidationCriterionResult(
                            criterion_id="benchmark_edge",
                            passed=True,
                            threshold="Sharpe >= 1.0 and >= 1.3x SPY Sharpe",
                            details="Sharpe edge satisfied.",
                        ),
                    ),
                    summary="All Gate 1 criteria satisfied.",
                ),
                ValidationCandidateResult(
                    candidate_id="mean-reversion-v1",
                    gate_id="1",
                    status="fail",
                    evidence_pack_id="evaluation-2",
                    criteria=(
                        ValidationCriterionResult(
                            criterion_id="max_drawdown",
                            passed=False,
                            threshold="Max drawdown <= 15%",
                            details="Drawdown exceeded threshold.",
                        ),
                    ),
                    summary="Gate 1 criteria failed.",
                ),
            ),
            summary="Gate 1 passed for trend-following-v1.",
            assumptions=("benchmark series declared dividend-adjusted",),
            evidence_refs=("evaluation_evidence/evaluation-1.json",),
        )
    )
    validation_store.write_gate_assessment(
        GateAssessment(
            gate_id="1",
            status="pass",
            evidence_refs=(
                "validation_reports/gate-1-20260417T180000Z.json",
                "evaluation_evidence/evaluation-1.json",
            ),
            decision_summary="Gate 1 passed for one mandatory candidate.",
            recorded_at_utc=timestamp,
        )
    )
    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            cycle_status="executed",
            symbols=("SPY", "QQQ"),
            symbol_results=(
                ServiceSymbolResult(
                    symbol="SPY",
                    terminal_state="reconciled_trade",
                    reason_code="baseline_long_entry",
                    recovered=False,
                ),
            ),
            blocked_trade_count=2,
            reconciliation_failure_count=1,
            open_position_symbols=("SPY",),
            cash=Decimal("10025.00"),
            equity=Decimal("10030.00"),
            buying_power=Decimal("20030.00"),
        )
    )
    paper_store.write_operator_alert(
        OperatorAlert(
            alert_id="alert-1",
            severity="warning",
            category="risk",
            summary="stale_data blocked trade intent intent-1",
            evidence_refs=("risk_events/risk-1.json",),
            delivery_targets=("telegram",),
            sent_at_utc=timestamp,
        )
    )
    paper_store.write_evaluation_evidence(
        EvaluationEvidencePack(
            evidence_pack_id="evaluation-1",
            candidate_id="trend-following-v1",
            window_start_utc=datetime(2023, 1, 1, tzinfo=UTC),
            window_end_utc=timestamp,
            benchmark_metrics={"sharpe_ratio": Decimal("1.0")},
            candidate_metrics={"sharpe_ratio": Decimal("1.4")},
            adversarial_checks=("cost_stress",),
            recommendation="keep",
            assumptions=("same benchmark window",),
        )
    )

    brief = reporting.build_gate_decision_brief(
        validation_store=validation_store,
        paper_store=paper_store,
        gate_id="1",
    )

    assert brief.gate_id == "1"
    assert brief.status == "pass"
    assert "advance" in brief.required_operator_action.lower()
    assert brief.latest_open_positions == ("SPY",)
    assert brief.blocked_trade_count == 2
    assert brief.reconciliation_failure_count == 1
    assert brief.latest_alert_summary == "stale_data blocked trade intent intent-1"
    assert brief.candidate_summaries[0].candidate_id == "trend-following-v1"
    assert brief.candidate_summaries[0].failed_criteria == ()
    assert brief.candidate_summaries[1].failed_criteria == ("max_drawdown",)
    assert brief.evidence_refs == (
        "validation_reports/gate-1-20260417T180000Z.json",
        "evaluation_evidence/evaluation-1.json",
    )


def test_build_gate_decision_brief_derives_null_criterion_status_from_passed(
    tmp_path: Path,
) -> None:
    reporting = importlib.import_module("tradingx.reporting")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    timestamp = datetime(2026, 4, 23, 12, 0, tzinfo=UTC)

    validation_store.write_validation_report(
        ValidationReport(
            report_id="gate-1-20260423T120000Z",
            gate_id="1",
            generated_at_utc=timestamp,
            status="fail",
            benchmark_symbol="SPY",
            window_start_utc=datetime(2023, 1, 1, tzinfo=UTC),
            window_end_utc=timestamp,
            candidate_results=(
                ValidationCandidateResult(
                    candidate_id="trend-following-v1",
                    gate_id="1",
                    status="fail",
                    evidence_pack_id="evaluation-1",
                    criteria=(
                        ValidationCriterionResult(
                            criterion_id="benchmark_edge",
                            passed=True,
                            threshold="Sharpe >= 1.0",
                            details="Passed benchmark edge.",
                        ),
                        ValidationCriterionResult(
                            criterion_id="max_drawdown",
                            passed=False,
                            threshold="Max drawdown <= 15%",
                            details="Drawdown exceeded threshold.",
                        ),
                    ),
                    summary="Gate 1 criteria failed.",
                ),
            ),
            summary="Gate 1 failed for trend-following-v1.",
            assumptions=(),
            evidence_refs=(),
        )
    )

    stored_report_path = (
        tmp_path / "validation" / "validation_reports" / "gate-1-20260423T120000Z.json"
    )
    stored_payload = stored_report_path.read_text(encoding="utf-8")
    assert '"status": null' in stored_payload

    brief = reporting.build_gate_decision_brief(
        validation_store=validation_store,
        paper_store=paper_store,
        gate_id="1",
    )

    assert brief.candidate_summaries[0].failed_criteria == ("max_drawdown",)


def test_build_gate_decision_brief_excludes_pending_criterion_from_failed_criteria(
    tmp_path: Path,
) -> None:
    reporting = importlib.import_module("tradingx.reporting")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    timestamp = datetime(2026, 4, 23, 12, 30, tzinfo=UTC)

    validation_store.write_validation_report(
        ValidationReport(
            report_id="gate-1-20260423T123000Z",
            gate_id="1",
            generated_at_utc=timestamp,
            status="pending",
            benchmark_symbol="SPY",
            window_start_utc=datetime(2023, 1, 1, tzinfo=UTC),
            window_end_utc=timestamp,
            candidate_results=(
                ValidationCandidateResult(
                    candidate_id="trend-following-v1",
                    gate_id="1",
                    status="pending",
                    evidence_pack_id="evaluation-1",
                    criteria=(
                        ValidationCriterionResult(
                            criterion_id="pbo_overfitting",
                            passed=False,
                            threshold="PBO <= 0.30",
                            details="Pending until cohort matures.",
                            status="pending",
                        ),
                    ),
                    summary="Gate 1 evidence is incomplete.",
                ),
            ),
            summary="Gate 1 pending for trend-following-v1.",
            assumptions=(),
            evidence_refs=(),
        )
    )

    brief = reporting.build_gate_decision_brief(
        validation_store=validation_store,
        paper_store=paper_store,
        gate_id="1",
    )

    assert brief.candidate_summaries[0].failed_criteria == ()
