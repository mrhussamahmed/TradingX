from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.config import TradingConfig
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    EvaluationEvidencePack,
    GateAssessment,
    MarketAutomationRunRecord,
    OperatorAlert,
    ServiceCycleSnapshot,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
    WebServiceState,
)
from tradingx.web.readmodels import LocalWebReadModel


class FakeServiceManager:
    def __init__(self, state: WebServiceState) -> None:
        self._state = state

    def get_state(self) -> WebServiceState:
        return self._state


def test_local_web_read_model_builds_dashboard_from_artifacts_and_docs(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)

    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            cycle_status="executed",
            symbols=("SPY", "QQQ"),
            symbol_results=(),
            blocked_trade_count=1,
            reconciliation_failure_count=0,
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
            summary="Blocked trade due to stale broker state.",
            evidence_refs=("artifacts/paper_loop/operator_alerts/alert-1.json",),
            delivery_targets=("telegram",),
            sent_at_utc=timestamp,
        )
    )
    validation_store.write_gate_assessment(
        GateAssessment(
            gate_id="1",
            status="pass",
            evidence_refs=("artifacts/validation/gate_assessments/gate-1.json",),
            decision_summary="Gate 1 passed.",
            recorded_at_utc=timestamp,
        )
    )
    validation_store.write_evaluation_evidence(
        EvaluationEvidencePack(
            evidence_pack_id="eval-1",
            candidate_id="baseline-long-only-v1",
            window_start_utc=timestamp,
            window_end_utc=timestamp,
            benchmark_metrics={"sharpe": "1.0"},
            candidate_metrics={"sharpe": "1.4"},
            adversarial_checks=("fee_stress",),
            recommendation="promote_candidate",
            assumptions=("benchmark series declared adjusted",),
        )
    )

    docs_root = tmp_path / "docs"
    (docs_root / "handover" / "SESSIONS").mkdir(parents=True)
    (docs_root / "handover" / "STATE.md").write_text(
        "# State\n\nGate 3 pending after local web app delivery.\n",
        encoding="utf-8",
    )
    (docs_root / "handover" / "SESSIONS" / "SESS-2026-04-17-013.md").write_text(
        (
            "---\nstatus: active\nsession_status: open\n---\n\n"
            "Approved local web app build.\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "config" / "proposals").mkdir(parents=True)
    (tmp_path / "config" / "proposals" / "proposal-1.md").write_text(
        "# Proposal\n\nUpdate symbol universe.\n",
        encoding="utf-8",
    )

    config = TradingConfig.from_mapping(
        {
            "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
        }
    )
    read_model = LocalWebReadModel(
        config=config,
        paper_store=paper_store,
        validation_store=validation_store,
        docs_root=docs_root,
        repo_root=tmp_path,
        service_manager=FakeServiceManager(
            WebServiceState(
                status="running",
                active_symbols=("SPY", "QQQ"),
                interval_seconds=300,
                cycles_completed=2,
                started_at_utc=timestamp,
                last_completed_at_utc=timestamp,
                last_error="",
            )
        ),
    )

    snapshot = read_model.build_dashboard_snapshot()
    documents = read_model.list_documents()
    proposals = read_model.list_config_proposals()

    assert snapshot.service_status.status == "running"
    assert snapshot.account_summary["cash"] == "10025.00"
    assert snapshot.gate_statuses["1"] == "pass"
    assert snapshot.recommendations["promote_candidate"] == 1
    assert snapshot.document_summary["session_count"] == 1
    assert documents[0].kind == "handover"
    assert proposals[0].proposal_id == "proposal-1"


def test_local_web_read_model_lists_artifact_payloads_by_category(tmp_path) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
    paper_store.write_operator_alert(
        OperatorAlert(
            alert_id="alert-1",
            severity="critical",
            category="risk",
            summary="Kill switch active.",
            evidence_refs=("operator_alerts/alert-1.json",),
            delivery_targets=("smtp",),
            sent_at_utc=timestamp,
        )
    )
    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        paper_store=paper_store,
        validation_store=FilesystemArtifactStore(tmp_path / "artifacts" / "validation"),
        docs_root=tmp_path / "docs",
        repo_root=tmp_path,
        service_manager=FakeServiceManager(
            WebServiceState(
                status="idle",
                active_symbols=(),
                interval_seconds=300,
                cycles_completed=0,
                started_at_utc=None,
                last_completed_at_utc=None,
                last_error="",
            )
        ),
    )

    payloads = read_model.list_evidence(category="operator_alerts")

    assert len(payloads) == 1
    assert payloads[0]["summary"] == "Kill switch active."


def test_local_web_read_model_parse_datetime_tolerates_invalid_iso(tmp_path) -> None:
    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        paper_store=FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop"),
        validation_store=FilesystemArtifactStore(tmp_path / "artifacts" / "validation"),
        docs_root=tmp_path / "docs",
        repo_root=tmp_path,
        service_manager=FakeServiceManager(
            WebServiceState(
                status="idle",
                active_symbols=(),
                interval_seconds=300,
                cycles_completed=0,
                started_at_utc=None,
                last_completed_at_utc=None,
                last_error="",
            )
        ),
    )

    parsed = read_model._parse_datetime("not-a-timestamp")

    assert parsed == datetime(1970, 1, 1, tzinfo=UTC)


def test_local_web_read_model_builds_operator_platform_views(tmp_path) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    operator_platform_root = tmp_path / "artifacts" / "operator_platform"
    timestamp = datetime(2026, 4, 18, 14, 30, tzinfo=UTC)

    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            cycle_status="executed",
            symbols=("SPY", "QQQ"),
            symbol_results=(),
            blocked_trade_count=1,
            reconciliation_failure_count=0,
            open_position_symbols=("SPY", "QQQ"),
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
            summary="Stale broker state blocked a trade.",
            evidence_refs=("artifacts/paper_loop/operator_alerts/alert-1.json",),
            delivery_targets=("telegram",),
            sent_at_utc=timestamp,
        )
    )
    validation_store.write_evaluation_evidence(
        EvaluationEvidencePack(
            evidence_pack_id="eval-1",
            candidate_id="trend-following-v1",
            window_start_utc=timestamp,
            window_end_utc=timestamp,
            benchmark_metrics={"sharpe": "1.0"},
            candidate_metrics={"sharpe": "1.4"},
            adversarial_checks=("fee_stress",),
            recommendation="promote_candidate",
            assumptions=("benchmark series declared adjusted",),
        )
    )
    validation_store.write_gate_assessment(
        GateAssessment(
            gate_id="1",
            status="pass",
            evidence_refs=("artifacts/validation/gate_assessments/gate-1.json",),
            decision_summary="Gate 1 passed.",
            recorded_at_utc=timestamp,
        )
    )
    validation_store.write_validation_report(
        ValidationReport(
            report_id="gate-1-20260418",
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
                    evidence_pack_id="eval-1",
                    criteria=(
                        ValidationCriterionResult(
                            criterion_id="benchmark_edge",
                            passed=True,
                            threshold="Sharpe >= 1.0",
                            details="Satisfied.",
                        ),
                    ),
                    summary="Candidate cleared the benchmark gate.",
                ),
            ),
            summary="Gate 1 passed.",
            assumptions=("benchmark series declared adjusted",),
            evidence_refs=("artifacts/validation/validation_reports/gate-1.json",),
        )
    )
    operator_platform_root.mkdir(parents=True)
    (operator_platform_root / "incident_acknowledgements").mkdir(parents=True)
    (
        operator_platform_root / "incident_acknowledgements" / "incident-alert-1.json"
    ).write_text(
        (
            "{\n"
            '  "incident_id": "incident-alert-1",\n'
            '  "acknowledged_at_utc": "2026-04-18T14:35:00+00:00",\n'
            '  "acknowledged_by": "local-operator"\n'
            "}\n"
        ),
        encoding="utf-8",
    )
    (operator_platform_root / "daily_digests").mkdir(parents=True)
    (operator_platform_root / "daily_digests" / "digest-1.json").write_text(
        (
            "{\n"
            '  "digest_id": "digest-1",\n'
            '  "generated_at_utc": "2026-04-18T16:00:00+00:00",\n'
            '  "session_label": "session_close",\n'
            '  "service_status": "stopped",\n'
            '  "blocked_trade_count": 1,\n'
            '  "reconciliation_failure_count": 0,\n'
            '  "latest_positions": ["SPY"],\n'
            '  "top_incidents": ["incident-alert-1"],\n'
            '  "recommended_actions": ["Review stale broker state."],\n'
            '  "evidence_refs": ['
            '"artifacts/operator_platform/daily_digests/digest-1.json"'
            "]\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    docs_root = tmp_path / "docs"
    (docs_root / "handover" / "SESSIONS").mkdir(parents=True)
    (docs_root / "handover" / "STATE.md").write_text(
        "# State\n\nOperator platform in progress.\n",
        encoding="utf-8",
    )
    (docs_root / "handover" / "SESSIONS" / "SESS-2026-04-18-014.md").write_text(
        (
            "---\nstatus: active\nsession_status: open\n---\n\n"
            "Operator platform feature branch.\n"
        ),
        encoding="utf-8",
    )

    config = TradingConfig.from_mapping(
        {
            "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
        }
    )
    read_model = LocalWebReadModel(
        config=config,
        paper_store=paper_store,
        validation_store=validation_store,
        docs_root=docs_root,
        repo_root=tmp_path,
        service_manager=FakeServiceManager(
            WebServiceState(
                status="running",
                active_symbols=("SPY", "QQQ"),
                interval_seconds=300,
                cycles_completed=2,
                started_at_utc=timestamp,
                last_completed_at_utc=timestamp,
                last_error="",
            )
        ),
    )

    command_center = read_model.build_command_center_snapshot()
    incidents = read_model.list_incidents()
    research = read_model.build_research_snapshot()
    replay = read_model.build_replay_session(symbol="SPY")
    explorer = read_model.search_records(query="Gate")
    digest = read_model.get_latest_daily_digest()
    automation_run = read_model.get_latest_market_automation_run()

    assert command_center.session_mode == "intraday"
    assert len(command_center.equity_curve) == 1
    assert incidents[0].status == "acknowledged"
    assert research.candidate_summaries[0].candidate_id == "trend-following-v1"
    assert replay.focus_value == "SPY"
    assert any(item.category == "validation_report" for item in explorer)
    assert digest is not None
    assert digest.session_label == "session_close"
    assert automation_run is None


def test_local_web_read_model_reads_latest_market_automation_run(tmp_path) -> None:
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    timestamp = datetime(2026, 4, 18, 17, 0, tzinfo=UTC)
    operator_store.write_market_automation_run_record(
        MarketAutomationRunRecord(
            run_id="automation-1",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            trading_day="2026-04-18",
            status="completed",
            heartbeat_count=2,
            preopen_session_id="session-preopen-1",
            heartbeat_session_ids=("session-heartbeat-1", "session-heartbeat-2"),
            close_session_id="session-close-1",
            latest_replay_summary_id="replay-summary-1",
            latest_gate3_report_id="gate3-1",
            latest_gate3_package_id="gate3-package-1",
            summary="Automation completed.",
            evidence_refs=(
                "artifacts/operator_platform/market_automation_runs/automation-1.json",
            ),
        )
    )

    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {"TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        paper_store=FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop"),
        validation_store=FilesystemArtifactStore(tmp_path / "artifacts" / "validation"),
        docs_root=tmp_path / "docs",
        repo_root=tmp_path,
        service_manager=FakeServiceManager(
            WebServiceState(
                status="idle",
                active_symbols=(),
                interval_seconds=300,
                cycles_completed=0,
                started_at_utc=None,
                last_completed_at_utc=None,
                last_error="",
            )
        ),
    )

    record = read_model.get_latest_market_automation_run()

    assert record is not None
    assert record.run_id == "automation-1"
    assert record.heartbeat_count == 2
