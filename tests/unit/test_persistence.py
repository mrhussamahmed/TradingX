from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    EvaluationEvidencePack,
    GateAssessment,
    OperatorAlert,
    ServiceCycleSnapshot,
    ServiceSymbolResult,
    TradeIntent,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
)


def test_persistence_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.persistence")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_filesystem_artifact_store_writes_trade_intent_json(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    intent = TradeIntent(
        intent_id="intent-1",
        candidate_id="trend-following-v1",
        symbol="SPY",
        side="buy",
        quantity=Decimal("1"),
        reason_code="trend_breakout",
        generated_at_utc=datetime(2026, 4, 17, 18, 0, tzinfo=UTC),
    )

    path = store.write_trade_intent(intent)

    assert path == tmp_path / "trade_intents" / "intent-1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["symbol"] == "SPY"
    assert payload["generated_at_utc"] == "2026-04-17T18:00:00+00:00"


def test_filesystem_artifact_store_separates_alert_and_gate_artifacts(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)

    alert_path = store.write_operator_alert(
        OperatorAlert(
            alert_id="alert-1",
            severity="critical",
            category="risk",
            summary="Blocked trade",
            evidence_refs=("artifacts/trade_intents/intent-1.json",),
            delivery_targets=("telegram",),
            sent_at_utc=timestamp,
        )
    )
    gate_path = store.write_gate_assessment(
        GateAssessment(
            gate_id="0.5",
            status="pass",
            evidence_refs=("artifacts/smoke/spy.json",),
            decision_summary="Walking skeleton passed.",
            recorded_at_utc=timestamp,
        )
    )

    assert alert_path == tmp_path / "operator_alerts" / "alert-1.json"
    assert gate_path == tmp_path / "gate_assessments" / "gate-0.5.json"


def test_filesystem_artifact_store_builds_operator_evidence_report(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    store.write_trade_intent(
        TradeIntent(
            intent_id="intent-1",
            candidate_id="trend-following-v1",
            symbol="SPY",
            side="buy",
            quantity=Decimal("1"),
            reason_code="trend_breakout",
            generated_at_utc=timestamp,
        )
    )
    store.write_operator_alert(
        OperatorAlert(
            alert_id="alert-1",
            severity="warning",
            category="risk",
            summary="Blocked trade",
            evidence_refs=("artifacts/trade_intents/intent-1.json",),
            delivery_targets=("telegram",),
            sent_at_utc=timestamp,
        )
    )

    report = store.build_operator_evidence_report()

    assert report["counts"]["trade_intents"] == 1
    assert report["counts"]["operator_alerts"] == 1
    assert "alert-1.json" in report["latest_artifacts"]["operator_alerts"]


def test_filesystem_artifact_store_writes_service_cycle_and_builds_richer_summary(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    store.write_service_cycle_snapshot(
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
                ServiceSymbolResult(
                    symbol="QQQ",
                    terminal_state="blocked_trade",
                    reason_code="liquidity_filter",
                    recovered=False,
                ),
            ),
            blocked_trade_count=1,
            reconciliation_failure_count=0,
            open_position_symbols=("SPY",),
            cash=Decimal("10025.00"),
            equity=Decimal("10030.00"),
            buying_power=Decimal("20030.00"),
        )
    )
    store.write_evaluation_evidence(
        EvaluationEvidencePack(
            evidence_pack_id="evaluation-1",
            candidate_id="trend-following-v1",
            window_start_utc=timestamp,
            window_end_utc=timestamp,
            benchmark_metrics={"sharpe": Decimal("1.0")},
            candidate_metrics={"sharpe": Decimal("1.2")},
            adversarial_checks=("adv_check",),
            recommendation="keep",
            assumptions=(),
        )
    )

    report = store.build_operator_evidence_report()

    assert report["counts"]["service_cycles"] == 1
    assert report["summary"]["blocked_trade_count"] == 1
    assert report["summary"]["latest_open_positions"] == ["SPY"]
    assert report["summary"]["latest_cash"] == "10025.00"
    assert report["summary"]["latest_equity"] == "10030.00"
    assert report["summary"]["evaluation_recommendations"] == {"keep": 1}


def test_filesystem_artifact_store_writes_validation_report_and_summarizes_gate_status(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)

    report_path = store.write_validation_report(
        ValidationReport(
            report_id="gate-1-20260417",
            gate_id="1",
            generated_at_utc=timestamp,
            status="pass",
            benchmark_symbol="SPY",
            window_start_utc=timestamp,
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
            ),
            summary="Gate 1 passed for trend-following-v1.",
            assumptions=("benchmark series declared dividend-adjusted",),
            evidence_refs=("evaluation_evidence/evaluation-1.json",),
        )
    )
    store.write_gate_assessment(
        GateAssessment(
            gate_id="1",
            status="pass",
            evidence_refs=(str(report_path),),
            decision_summary="Gate 1 passed for one mandatory candidate.",
            recorded_at_utc=timestamp,
        )
    )

    report = store.build_operator_evidence_report()

    assert report_path == tmp_path / "validation_reports" / "gate-1-20260417.json"
    assert report["counts"]["validation_reports"] == 1
    assert report["summary"]["latest_gate_statuses"] == {"1": "pass"}
