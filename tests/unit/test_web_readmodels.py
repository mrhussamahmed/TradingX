# ruff: noqa: E501

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from tradingx.config import TradingConfig
from tradingx.journal import SqliteOmsJournal
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    BotRuntimeState,
    ClosedTradeRecord,
    EvaluationEvidencePack,
    Gate3CriterionSnapshot,
    Gate3ReadinessReport,
    GateAssessment,
    HistoricalWarmupRecord,
    MarketAutomationRunRecord,
    OperatorAlert,
    OpportunityScore,
    OpportunitySelectionRecord,
    ServiceCycleSnapshot,
    StrategyActivationRecord,
    ValidationCandidateResult,
    ValidationCriterionResult,
    ValidationReport,
    WebServiceState,
)
from tradingx.web import readmodels as readmodels_module
from tradingx.web.readmodels import LocalWebReadModel


class FakeServiceManager:
    def __init__(self, state: WebServiceState) -> None:
        self._state = state

    def get_state(self) -> WebServiceState:
        return self._state


class FakeRuntimeHostManager:
    def __init__(self, state: BotRuntimeState) -> None:
        self._state = state

    def get_state(self) -> BotRuntimeState:
        return self._state


def _minimal_runtime_state(timestamp: datetime) -> BotRuntimeState:
    return BotRuntimeState(
        status="trading_ready",
        status_reason="Runtime boot complete.",
        active_symbols=("SPY",),
        started_at_utc=timestamp,
        updated_at_utc=timestamp,
        last_error="",
        active_strategy_id="baseline-long-only-v1",
        active_model_snapshot_id="approved-baseline-long-only-v1",
        latest_selection_id="selection-1",
    )


def _minimal_read_model(tmp_path, timestamp: datetime) -> LocalWebReadModel:
    return LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
            }
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
        runtime_host_manager=FakeRuntimeHostManager(_minimal_runtime_state(timestamp)),
    )


def _write_service_cycle(
    paper_store: FilesystemArtifactStore,
    *,
    timestamp: datetime,
    cycle_id: str = "cycle-1",
    payload_overrides: dict[str, object] | None = None,
) -> None:
    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id=cycle_id,
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            cycle_status="executed",
            symbols=("SPY",),
            symbol_results=(),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            open_position_symbols=("SPY",),
            cash=Decimal("99999.57"),
            equity=Decimal("99999.57"),
            buying_power=Decimal("399998.28"),
        )
    )
    if payload_overrides:
        path = paper_store._root_dir / "service_cycles" / f"{cycle_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(payload_overrides)
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_dashboard_service_status_uses_persisted_cycles_when_web_manager_idle(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 28, 19, 44, tzinfo=UTC)
    read_model = _minimal_read_model(tmp_path, timestamp)
    _write_service_cycle(
        read_model._paper_store,
        timestamp=timestamp,
        payload_overrides={"symbols": ("SPY", "QQQ", "IWM")},
    )

    snapshot = read_model.build_command_center_snapshot()

    assert snapshot.service_status.status == "idle"
    assert snapshot.service_status.cycles_completed == 1
    assert snapshot.service_status.active_symbols == ("SPY", "QQQ", "IWM")
    assert snapshot.service_status.last_completed_at_utc == timestamp


def test_count_pending_orders_ignores_stale_day_order_events(tmp_path) -> None:
    now = datetime(2026, 4, 29, 13, 30, tzinfo=UTC)
    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
            }
        ),
        paper_store=FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop"),
        validation_store=FilesystemArtifactStore(tmp_path / "artifacts" / "validation"),
        docs_root=tmp_path / "docs",
        repo_root=tmp_path,
        service_manager=FakeServiceManager(
            WebServiceState(
                status="running",
                active_symbols=("SPY",),
                interval_seconds=300,
                cycles_completed=1,
                started_at_utc=now,
                last_completed_at_utc=now,
                last_error="",
            )
        ),
        runtime_host_manager=FakeRuntimeHostManager(_minimal_runtime_state(now)),
        now_provider=lambda: now,
    )
    journal = SqliteOmsJournal(tmp_path / "data" / "journal.db")
    journal.append_event(
        event_type="ack",
        recorded_at_utc=now - timedelta(hours=13),
        decision_snapshot_id="decision-stale",
        cycle_correlation_id="cycle-stale",
        client_order_id="stale-client",
        broker_order_id="stale-broker-order",
        symbol="XLE",
        side="buy",
        payload={"status": "pending_new"},
    )
    journal.append_event(
        event_type="submit_attempt",
        recorded_at_utc=now - timedelta(minutes=10),
        decision_snapshot_id="decision-fresh",
        cycle_correlation_id="cycle-fresh",
        client_order_id="fresh-client",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={"reason_code": "baseline_long_entry"},
    )

    assert read_model._count_pending_orders() == 1


def test_command_center_keeps_last_account_snapshot_after_market_closed_cycle(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 28, 19, 44, tzinfo=UTC)
    closed_timestamp = datetime(2026, 4, 28, 20, 26, tzinfo=UTC)
    read_model = _minimal_read_model(tmp_path, timestamp)
    _write_service_cycle(
        read_model._paper_store,
        timestamp=timestamp,
        cycle_id="cycle-account",
        payload_overrides={
            "symbols": ("SPY", "QQQ", "IWM"),
            "open_position_symbols": ("SPY", "QQQ", "IWM"),
            "cash": "98363.03",
            "equity": "100006.08",
            "buying_power": "397170.85",
        },
    )
    _write_service_cycle(
        read_model._paper_store,
        timestamp=closed_timestamp,
        cycle_id="cycle-market-closed",
        payload_overrides={
            "symbols": ("SPY", "QQQ", "IWM"),
            "cycle_status": "market_closed",
            "open_position_symbols": (),
            "cash": "0",
            "equity": "0",
            "buying_power": "0",
        },
    )

    snapshot = read_model.build_command_center_snapshot()

    assert snapshot.gate_statuses["paper_cycle"] == "pass"
    assert snapshot.service_status.cycles_completed == 2
    assert snapshot.service_status.last_completed_at_utc == closed_timestamp
    assert snapshot.account_summary == {
        "cash": "98363.03",
        "equity": "100006.08",
        "buying_power": "397170.85",
        "daily_pnl": "0",
    }
    watchlist = {row["symbol"]: row["status"] for row in snapshot.watchlist}
    assert watchlist["SPY"] == "active"
    assert watchlist["QQQ"] == "active"
    assert watchlist["IWM"] == "active"


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
        runtime_host_manager=FakeRuntimeHostManager(
            BotRuntimeState(
                status="trading_ready",
                status_reason="Runtime boot complete.",
                active_symbols=("SPY", "QQQ"),
                started_at_utc=timestamp,
                updated_at_utc=timestamp,
                last_error="",
                active_strategy_id="baseline-long-only-v1",
                active_model_snapshot_id="snapshot-1",
                latest_selection_id="selection-1",
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
    assert snapshot.gate_authority_statuses["1"] == "legacy_non_authority"
    assert (
        snapshot.recommendation_authority_statuses["promote_candidate"]
        == "legacy_non_authority"
    )
    assert snapshot.document_summary["v5_authority_status"] == "legacy_non_authority"
    assert (
        snapshot.document_summary["gate_validation_authority_status"]
        == "legacy_non_authority"
    )
    assert (
        snapshot.document_summary["recommendation_authority_status"]
        == "legacy_non_authority"
    )
    assert snapshot.document_summary["session_count"] == 1
    assert documents[0].kind == "handover"
    assert proposals[0].proposal_id == "proposal-1"


def test_command_center_uses_operational_paper_gates_for_trade_permission(
    monkeypatch,
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 28, 19, 6, tzinfo=UTC)
    read_model = _minimal_read_model(tmp_path, timestamp)
    paper_store = read_model._paper_store
    validation_store = read_model._validation_store
    _write_service_cycle(paper_store, timestamp=timestamp)
    validation_store.write_gate_assessment(
        GateAssessment(
            gate_id="1",
            status="fail",
            evidence_refs=("artifacts/validation/gate_assessments/gate-1.json",),
            decision_summary="Old research gate failed.",
            recorded_at_utc=timestamp,
        )
    )

    monkeypatch.setattr(
        readmodels_module,
        "build_artifact_promotion_decision_provider",
        lambda root: lambda strategy_id: SimpleNamespace(
            max_state=readmodels_module.PromotionState.PAPER_TRADING,
            blocker_codes=(),
        ),
    )

    command_center = read_model.build_command_center_snapshot()

    assert command_center.gate_statuses == {
        "paper_runtime": "pass",
        "paper_cycle": "pass",
        "paper_reconciliation": "pass",
        "paper_authority": "pass",
    }


def test_local_web_read_model_redacts_unreleased_promotion_metrics(tmp_path) -> None:
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    validation_store.write_evaluation_evidence(
        EvaluationEvidencePack(
            evidence_pack_id="evidence-unreleased",
            candidate_id="trend-following-v1",
            window_start_utc=datetime(2026, 1, 1, tzinfo=UTC),
            window_end_utc=datetime(2026, 4, 1, tzinfo=UTC),
            benchmark_metrics={"sharpe": "SENTINEL-9.8765"},
            candidate_metrics={"sharpe": "SENTINEL-9.8765"},
            adversarial_checks=("cost_sensitivity_pass",),
            recommendation="promote",
            assumptions=(),
        )
    )
    evidence_path = (
        tmp_path
        / "artifacts"
        / "validation"
        / "evaluation_evidence"
        / "evidence-unreleased.json"
    )
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    payload["metric_visibility_context"] = {
        "promotion_valid": True,
        "metric_vault_release_status": "pending",
        "metric_release_token_ref": "",
        "experiment_id": "exp-001",
        "run_id": "run-001",
        "promotion_decision_scope": "scope-prod-001",
    }
    evidence_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
            }
        ),
        paper_store=FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop"),
        validation_store=validation_store,
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
        runtime_host_manager=FakeRuntimeHostManager(
            _minimal_runtime_state(datetime(2026, 4, 26, tzinfo=UTC))
        ),
    )

    research = read_model.build_research_snapshot()
    evidence = read_model.list_evidence("evaluation_evidence")
    encoded = json.dumps(
        {"research": research, "evidence": evidence},
        default=str,
        sort_keys=True,
    )

    assert "SENTINEL-9.8765" not in encoded
    assert research.candidate_summaries[0].candidate_metrics == {}


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
        runtime_host_manager=FakeRuntimeHostManager(
            BotRuntimeState(
                status="trading_ready",
                status_reason="Runtime boot complete.",
                active_symbols=("SPY", "QQQ"),
                started_at_utc=timestamp,
                updated_at_utc=timestamp,
                last_error="",
                active_strategy_id="baseline-long-only-v1",
                active_model_snapshot_id="snapshot-1",
                latest_selection_id="selection-1",
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


def test_readmodel_surfaces_cost_drag_when_present(tmp_path) -> None:
    timestamp = datetime(2026, 4, 21, 14, 30, tzinfo=UTC)
    read_model = _minimal_read_model(tmp_path, timestamp)

    diagnostics = read_model._build_performance_diagnostics(
        runtime_state=_minimal_runtime_state(timestamp),
        warmup=None,
        validation_report={
            "status": "fail",
            "summary": "Gate 1 failed.",
            "candidate_results": [
                {
                    "candidate_id": "trend-following-v1",
                    "status": "fail",
                    "criteria": [],
                    "annualized_cost_drag_bps": "12.5",
                },
                {
                    "candidate_id": "vol-target-v1",
                    "status": "fail",
                    "criteria": [],
                    "annualized_cost_drag_bps": "8.0",
                },
            ],
        },
        replay_summary=None,
    )

    gate_validation = next(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.diagnostic_id == "gate_validation"
    )
    assert "12.5" in gate_validation.detail
    assert "cost drag" in gate_validation.detail.lower()


def test_readmodel_ignores_missing_cost_drag(tmp_path) -> None:
    timestamp = datetime(2026, 4, 21, 14, 30, tzinfo=UTC)
    read_model = _minimal_read_model(tmp_path, timestamp)

    diagnostics = read_model._build_performance_diagnostics(
        runtime_state=_minimal_runtime_state(timestamp),
        warmup=None,
        validation_report={
            "status": "fail",
            "summary": "Gate 1 failed.",
            "candidate_results": [
                {
                    "candidate_id": "trend-following-v1",
                    "status": "fail",
                    "criteria": [],
                },
            ],
        },
        replay_summary=None,
    )

    gate_validation = next(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.diagnostic_id == "gate_validation"
    )
    assert "cost drag" not in gate_validation.detail.lower()


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
            benchmark_symbol="SPY+AGG",
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
                            criterion_id="hurdle_clearance",
                            passed=True,
                            threshold="Candidate total return must exceed the cash hurdle total return",
                            details="Candidate total return=0.121, cash hurdle total return=0.019.",
                        ),
                        ValidationCriterionResult(
                            criterion_id="opportunity_cost_edge",
                            passed=True,
                            threshold="Candidate CAGR must exceed SPY:0.6+AGG:0.4 CAGR by 0.02 absolute",
                            details="Candidate CAGR=0.143, SPY:0.6+AGG:0.4 CAGR=0.091.",
                        ),
                        ValidationCriterionResult(
                            criterion_id="operating_constraint",
                            passed=True,
                            threshold="max_drawdown <= 0.15 and CDaR@0.95 <= 0.08",
                            details="max_drawdown=0.060, CDaR=0.041, halt=0.250.",
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
        runtime_host_manager=FakeRuntimeHostManager(
            BotRuntimeState(
                status="trading_ready",
                status_reason="Runtime boot complete.",
                active_symbols=("SPY", "QQQ"),
                started_at_utc=timestamp,
                updated_at_utc=timestamp,
                last_error="",
                active_strategy_id="baseline-long-only-v1",
                active_model_snapshot_id="snapshot-1",
                latest_selection_id="selection-1",
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


def test_local_web_read_model_prefers_live_oms_journal_over_ops_rehearsal_journal(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    timestamp = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            cycle_status="executed",
            symbols=("SPY",),
            symbol_results=(),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            open_position_symbols=(),
            cash=Decimal("99999.57"),
            equity=Decimal("99999.57"),
            buying_power=Decimal("399998.28"),
        )
    )

    ops_journal = SqliteOmsJournal(
        tmp_path / "artifacts" / "ops" / "data" / "journal.db"
    )
    ops_journal.append_event(
        event_type="reject",
        recorded_at_utc=timestamp,
        decision_snapshot_id="decision-ops",
        cycle_correlation_id="cycle-ops",
        client_order_id="client-ops",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={
            "reason_code": "insufficient_buying_power",
            "message": '{"message":"insufficient buying power for requested exposure"}',
        },
    )

    live_journal = SqliteOmsJournal(tmp_path / "data" / "journal.db")
    live_journal.append_event(
        event_type="submit_attempt",
        recorded_at_utc=timestamp,
        decision_snapshot_id="decision-live",
        cycle_correlation_id="cycle-live",
        client_order_id="client-live",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={"reason_code": "baseline_long_entry"},
    )

    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
            }
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
        runtime_host_manager=FakeRuntimeHostManager(
            BotRuntimeState(
                status="trading_ready",
                status_reason="Runtime boot complete.",
                active_symbols=("SPY",),
                started_at_utc=timestamp,
                updated_at_utc=timestamp,
                last_error="",
                active_strategy_id="baseline-long-only-v1",
                active_model_snapshot_id="approved-baseline-long-only-v1",
                latest_selection_id="selection-1",
            )
        ),
    )

    snapshot = read_model.build_portfolio_workspace_snapshot()
    execution_quality = next(
        card for card in snapshot.metric_cards if card.metric_id == "execution_quality"
    )
    reject_rate = next(
        card for card in snapshot.metric_cards if card.metric_id == "reject_rate"
    )

    assert execution_quality.value == "No recent rejects"
    assert execution_quality.delta == "No broker rejection recorded"
    assert reject_rate.value == "0.00%"
    assert snapshot.execution_panel.summary_metrics[0].value == "0"


def test_local_web_read_model_labels_live_and_rehearsal_portfolio_sources(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    timestamp = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            cycle_status="executed",
            symbols=("SPY",),
            symbol_results=(),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            open_position_symbols=(),
            cash=Decimal("99999.57"),
            equity=Decimal("99999.57"),
            buying_power=Decimal("399998.28"),
        )
    )
    live_journal = SqliteOmsJournal(tmp_path / "data" / "journal.db")
    live_journal.append_event(
        event_type="submit_attempt",
        recorded_at_utc=timestamp,
        decision_snapshot_id="decision-live",
        cycle_correlation_id="cycle-live",
        client_order_id="client-live",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={"reason_code": "baseline_long_entry"},
    )
    ops_root = tmp_path / "artifacts" / "ops"
    ops_root.mkdir(parents=True, exist_ok=True)
    (ops_root / "paper_account_starting_state.json").write_text(
        (
            "{\n"
            '  "buying_power": "399998.28",\n'
            '  "cash": "99999.57",\n'
            '  "equity": "99999.57",\n'
            '  "recorded_at_utc": "2026-04-19T21:30:18.589286+00:00"\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
            }
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
        runtime_host_manager=FakeRuntimeHostManager(
            BotRuntimeState(
                status="trading_ready",
                status_reason="Runtime boot complete.",
                active_symbols=("SPY",),
                started_at_utc=timestamp,
                updated_at_utc=timestamp,
                last_error="",
                active_strategy_id="baseline-long-only-v1",
                active_model_snapshot_id="approved-baseline-long-only-v1",
                latest_selection_id="selection-1",
            )
        ),
    )

    snapshot = read_model.build_portfolio_workspace_snapshot()
    equity_card = next(
        card for card in snapshot.metric_cards if card.metric_id == "equity"
    )

    assert [note.label for note in snapshot.source_notes] == [
        "Live account",
        "Live OMS journal",
        "Rehearsal baseline",
    ]
    assert equity_card.provenance is not None
    assert equity_card.provenance.label == "Mixed evidence"
    assert snapshot.execution_panel.provenance is not None
    assert snapshot.execution_panel.provenance.label == "Live OMS journal"


def test_portfolio_source_evidence_uses_service_cycle_account_position_source(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    _write_service_cycle(
        paper_store,
        timestamp=timestamp,
        payload_overrides={
            "account_source_at_utc": timestamp.isoformat(),
            "position_source_at_utc": timestamp.isoformat(),
        },
    )
    read_model = _minimal_read_model(tmp_path, timestamp)

    snapshot = read_model.build_portfolio_workspace_snapshot()

    assert snapshot.source_evidence_at_utc == timestamp
    assert snapshot.account_position_source_at_utc == timestamp
    assert snapshot.execution_journal_source_at_utc is None
    assert snapshot.closed_trade_source_at_utc is None


def test_portfolio_source_evidence_stays_missing_without_explicit_account_position_source(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    _write_service_cycle(paper_store, timestamp=timestamp)

    snapshot = _minimal_read_model(
        tmp_path, timestamp
    ).build_portfolio_workspace_snapshot()

    assert snapshot.source_evidence_at_utc is None
    assert snapshot.account_position_source_at_utc is None


def test_portfolio_source_evidence_keeps_one_sided_account_position_missing(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    account_time = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    position_time = datetime(2026, 4, 20, 14, 10, tzinfo=UTC)
    _write_service_cycle(
        paper_store,
        timestamp=timestamp,
        cycle_id="account-only",
        payload_overrides={
            "account_source_at_utc": account_time.isoformat(),
            "position_source_at_utc": "",
        },
    )
    account_only = _minimal_read_model(
        tmp_path, timestamp
    ).build_portfolio_workspace_snapshot()

    assert account_only.source_evidence_at_utc is None
    assert account_only.account_position_source_at_utc is None

    _write_service_cycle(
        paper_store,
        timestamp=timestamp,
        cycle_id="position-only",
        payload_overrides={
            "account_source_at_utc": "",
            "position_source_at_utc": position_time.isoformat(),
        },
    )
    position_only = _minimal_read_model(
        tmp_path, timestamp
    ).build_portfolio_workspace_snapshot()

    assert position_only.source_evidence_at_utc is None
    assert position_only.account_position_source_at_utc is None


def test_portfolio_source_evidence_uses_older_split_account_position_source(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    account_time = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    position_time = datetime(2026, 4, 20, 14, 10, tzinfo=UTC)
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    _write_service_cycle(
        paper_store,
        timestamp=timestamp,
        payload_overrides={
            "account_source_at_utc": account_time.isoformat(),
            "position_source_at_utc": position_time.isoformat(),
        },
    )

    snapshot = _minimal_read_model(
        tmp_path, timestamp
    ).build_portfolio_workspace_snapshot()

    assert snapshot.source_evidence_at_utc == position_time
    assert snapshot.account_position_source_at_utc == position_time


def test_portfolio_required_source_ignores_fresh_oms_and_closed_trade_without_account_position(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    paper_store.write_closed_trade_record(
        ClosedTradeRecord(
            trade_id="trade-1",
            symbol="SPY",
            entry_intent_id="intent-entry",
            exit_intent_id="intent-exit",
            opened_at_utc=timestamp,
            closed_at_utc=timestamp,
            quantity=Decimal("1"),
            entry_price=Decimal("500"),
            exit_price=Decimal("505"),
            gross_pnl=Decimal("5"),
            return_pct=Decimal("0.01"),
            outcome="win",
            holding_period_seconds=300,
        )
    )
    journal = SqliteOmsJournal(tmp_path / "data" / "journal.db")
    journal.append_event(
        event_type="submit_attempt",
        recorded_at_utc=timestamp,
        decision_snapshot_id="decision-live",
        cycle_correlation_id="cycle-live",
        client_order_id="client-live",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={"reason_code": "baseline_long_entry"},
    )

    snapshot = _minimal_read_model(
        tmp_path, timestamp
    ).build_portfolio_workspace_snapshot()

    assert snapshot.source_evidence_at_utc is None
    assert snapshot.account_position_source_at_utc is None
    assert snapshot.execution_journal_source_at_utc == timestamp
    assert snapshot.closed_trade_source_at_utc == timestamp


def test_local_web_read_model_builds_runtime_heartbeat_from_latest_cycle_and_selection(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    timestamp = datetime(2026, 4, 20, 14, 58, 30, tzinfo=UTC)
    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            cycle_status="executed",
            symbols=("SPY",),
            symbol_results=(),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            open_position_symbols=(),
            cash=Decimal("99999.57"),
            equity=Decimal("99999.57"),
            buying_power=Decimal("399998.28"),
        )
    )
    operator_store.write_historical_warmup_record(
        HistoricalWarmupRecord(
            warmup_id="warmup-1",
            generated_at_utc=timestamp,
            benchmark_symbol="SPY",
            symbols=("SPY", "QQQ", "IWM"),
            window_start_utc=timestamp,
            window_end_utc=timestamp,
            required_bar_count=30,
            symbols_ready=("SPY", "QQQ"),
            symbols_blocked={"IWM": "Insufficient daily bars for warmup coverage."},
            return_summary={
                "SPY": {
                    "cumulative_return": "0.03633208383570791129794373504",
                    "mean_return": "0.0",
                    "volatility": "0.01047064497825575500",
                },
                "QQQ": {
                    "cumulative_return": "0.0284019921010000000000000000",
                    "mean_return": "0.0",
                    "volatility": "0.01200000000000000000",
                },
            },
        )
    )
    operator_store.write_strategy_activation_record(
        StrategyActivationRecord(
            activation_id="activation-1",
            strategy_id="baseline-long-only-v1",
            strategy_version="1.0.0",
            approved_symbols=("SPY", "QQQ", "IWM"),
            deploy_threshold="0.50",
            allow_fallback_weights=True,
            status="approved",
            activated_at_utc=timestamp,
            notes="Three-symbol supervised dry-run activation.",
        )
    )
    operator_store.write_opportunity_selection_record(
        OpportunitySelectionRecord(
            selection_id="selection-1",
            generated_at_utc=timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="approved-baseline-long-only-v1",
            symbols_considered=("SPY", "QQQ", "IWM"),
            ranked_opportunities=(
                OpportunityScore(
                    symbol="SPY",
                    base_signal=Decimal("0.3633208383570791129794373504"),
                    regime_weight=Decimal("1.028718329115396922360880821"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.50"),
                    spread_penalty=Decimal("0.02545536825432741260323566014"),
                    volatility_penalty=Decimal("0.1047064497825575500"),
                    portfolio_overlap_penalty=Decimal("0.0"),
                    execution_cost_penalty=Decimal("0.01272768412716370630161783007"),
                    final_score=Decimal("0.4177427064872007865966329969"),
                    eligible=True,
                    ineligibility_reason="",
                ),
                OpportunityScore(
                    symbol="QQQ",
                    base_signal=Decimal("0.2900"),
                    regime_weight=Decimal("1.0200"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.35"),
                    spread_penalty=Decimal("0.0180"),
                    volatility_penalty=Decimal("0.0420"),
                    portfolio_overlap_penalty=Decimal("0.0"),
                    execution_cost_penalty=Decimal("0.0080"),
                    final_score=Decimal("0.3310"),
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="",
            decision="no_trade",
            decision_reason="No eligible opportunity cleared the deploy threshold.",
        )
    )

    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
                "TRADINGX_SERVICE_INTERVAL_SECONDS": "300",
                "TRADINGX_SYMBOL_UNIVERSE": "SPY,QQQ,IWM",
            }
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
        runtime_host_manager=FakeRuntimeHostManager(
            BotRuntimeState(
                status="trading_ready",
                status_reason="Runtime boot complete.",
                active_symbols=("SPY", "QQQ", "IWM"),
                started_at_utc=timestamp,
                updated_at_utc=timestamp,
                last_error="",
                active_strategy_id="baseline-long-only-v1",
                active_model_snapshot_id="approved-baseline-long-only-v1",
                latest_selection_id="selection-1",
            )
        ),
    )

    heartbeat = read_model.build_runtime_heartbeat_snapshot()

    assert heartbeat.heartbeat_state == "Waiting for next evaluation"
    assert heartbeat.last_decision == "No trade"
    assert heartbeat.current_exposure == "Flat"
    assert heartbeat.cadence_label == "Every 5m"
    assert heartbeat.last_evaluation_at_utc == timestamp
    assert heartbeat.next_evaluation_at_utc == datetime(
        2026, 4, 20, 15, 3, 30, tzinfo=UTC
    )
    assert (
        heartbeat.score_explanation
        == "SPY scored 0.4177 which is below the deploy threshold of 0.50."
    )
    truth_items = {item.label: item.value for item in heartbeat.runtime_truth}
    assert truth_items["Session posture"] == "Intraday monitor"
    assert truth_items["Trading mode"] == "Paper"
    assert truth_items["Runtime engine"] == "Active"
    assert truth_items["Open positions"] == "0"
    assert truth_items["Pending orders"] == "0"

    symbol_rows = {row.symbol: row for row in heartbeat.symbol_rows}
    assert symbol_rows["SPY"].status == "Below threshold"
    assert symbol_rows["SPY"].threshold_gap == "-0.0823"
    assert symbol_rows["QQQ"].status == "Below threshold"
    assert symbol_rows["QQQ"].reason == "Score remained below the deploy threshold."
    assert symbol_rows["IWM"].status == "Blocked"
    assert symbol_rows["IWM"].warmup_state == "Blocked"
    assert symbol_rows["IWM"].reason == "Insufficient daily bars for warmup coverage."

    assert [row.symbol for row in heartbeat.decision_ladder] == ["SPY", "QQQ", "IWM"]
    assert heartbeat.decision_ladder[0].primary_driver == "Volatility penalty"
    assert heartbeat.decision_ladder[1].primary_driver == "Volatility penalty"
    assert heartbeat.decision_ladder[2].disposition == "Blocked"

    assert heartbeat.operator_guidance is not None
    assert heartbeat.operator_guidance.recommendation == "Investigate warmup failure"
    assert (
        heartbeat.operator_guidance.detail
        == "IWM is still blocked by warmup, so TradingX is evaluating an incomplete universe. Resolve the warmup gap before broadening unattended operation."
    )


def test_runtime_heartbeat_prefers_latest_operator_artifacts_by_timestamp(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    older_timestamp = datetime(2026, 4, 20, 17, 4, tzinfo=UTC)
    newer_timestamp = datetime(2026, 4, 22, 14, 2, 13, tzinfo=UTC)

    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-latest",
            started_at_utc=newer_timestamp,
            completed_at_utc=newer_timestamp,
            cycle_status="executed",
            symbols=("SPY", "QQQ", "IWM"),
            symbol_results=(),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            open_position_symbols=("SPY", "QQQ", "IWM"),
            cash=Decimal("98316.59"),
            equity=Decimal("100004.46"),
            buying_power=Decimal("398122.25"),
        )
    )
    operator_store.write_historical_warmup_record(
        HistoricalWarmupRecord(
            warmup_id="warmup-z-old",
            generated_at_utc=older_timestamp,
            benchmark_symbol="SPY",
            symbols=("SPY",),
            window_start_utc=older_timestamp,
            window_end_utc=older_timestamp,
            required_bar_count=30,
            symbols_ready=("SPY",),
            symbols_blocked={},
            return_summary={
                "SPY": {
                    "cumulative_return": "0.03673855618034435164581019192",
                    "mean_return": "0.0",
                    "volatility": "0.01046714083591610900",
                }
            },
        )
    )
    operator_store.write_historical_warmup_record(
        HistoricalWarmupRecord(
            warmup_id="warmup-a-new",
            generated_at_utc=newer_timestamp,
            benchmark_symbol="SPY",
            symbols=("SPY", "QQQ", "IWM"),
            window_start_utc=newer_timestamp,
            window_end_utc=newer_timestamp,
            required_bar_count=30,
            symbols_ready=("SPY", "QQQ", "IWM"),
            symbols_blocked={},
            return_summary={
                "SPY": {
                    "cumulative_return": "0.05396956955943802895846951408",
                    "mean_return": "0.0",
                    "volatility": "0.01031118289880468900",
                },
                "QQQ": {
                    "cumulative_return": "0.1033020836578743735363571369",
                    "mean_return": "0.0",
                    "volatility": "0.01273729624580978000",
                },
                "IWM": {
                    "cumulative_return": "0.08350809089345879210123877161",
                    "mean_return": "0.0",
                    "volatility": "0.01414188890150961400",
                },
            },
        )
    )
    operator_store.write_strategy_activation_record(
        StrategyActivationRecord(
            activation_id="activation-z-old",
            strategy_id="baseline-long-only-v1",
            strategy_version="1.0.0",
            approved_symbols=("SPY",),
            deploy_threshold="0.50",
            allow_fallback_weights=True,
            status="approved",
            activated_at_utc=older_timestamp,
            notes="Old activation.",
        )
    )
    operator_store.write_strategy_activation_record(
        StrategyActivationRecord(
            activation_id="activation-a-new",
            strategy_id="baseline-long-only-v1",
            strategy_version="1.0.0",
            approved_symbols=("SPY", "QQQ", "IWM"),
            deploy_threshold="0.50",
            allow_fallback_weights=True,
            status="approved",
            activated_at_utc=newer_timestamp,
            notes="Latest activation.",
        )
    )
    operator_store.write_opportunity_selection_record(
        OpportunitySelectionRecord(
            selection_id="selection-z-old",
            generated_at_utc=older_timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="approved-baseline-long-only-v1",
            symbols_considered=("SPY",),
            ranked_opportunities=(
                OpportunityScore(
                    symbol="SPY",
                    base_signal=Decimal("0.3673855618034435164581019192"),
                    regime_weight=Decimal("1.029045582802455129883352241"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.50"),
                    spread_penalty=Decimal("0.008480445506070585574762194174"),
                    volatility_penalty=Decimal("0.1046714083591610900"),
                    portfolio_overlap_penalty=Decimal("0.0"),
                    execution_cost_penalty=Decimal("0.004240222753035292787381097087"),
                    final_score=Decimal("0.4496926577205809292058637092"),
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="",
            decision="no_trade",
            decision_reason="No eligible opportunity cleared the deploy threshold.",
        )
    )
    operator_store.write_opportunity_selection_record(
        OpportunitySelectionRecord(
            selection_id="selection-a-new",
            generated_at_utc=newer_timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="approved-baseline-long-only-v1",
            symbols_considered=("SPY", "QQQ", "IWM"),
            ranked_opportunities=(
                OpportunityScore(
                    symbol="SPY",
                    base_signal=Decimal("0.5396956955943802895846951408"),
                    regime_weight=Decimal("1.043144746509919177075679647"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.50"),
                    spread_penalty=Decimal("0.01127252744155899054516760839"),
                    volatility_penalty=Decimal("0.1031118289880468900"),
                    portfolio_overlap_penalty=Decimal("0.00"),
                    execution_cost_penalty=Decimal("0.005636263720779495272583804195"),
                    final_score=Decimal("0.7244504742095561209447578289"),
                    eligible=True,
                    ineligibility_reason="",
                ),
                OpportunityScore(
                    symbol="QQQ",
                    base_signal=Decimal("1.033020836578743735363571369"),
                    regime_weight=Decimal("1.043144746509919177075679647"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.174694866666666666666666667"),
                    spread_penalty=Decimal("0.01537657225451302395669957253"),
                    volatility_penalty=Decimal("0.127372962458097800"),
                    portfolio_overlap_penalty=Decimal("1.00"),
                    execution_cost_penalty=Decimal("0.007688286127256511978349786265"),
                    final_score=Decimal("0.115401924439592197252488572"),
                    eligible=True,
                    ineligibility_reason="",
                ),
                OpportunityScore(
                    symbol="IWM",
                    base_signal=Decimal("0.8350809089345879210123877161"),
                    regime_weight=Decimal("1.043144746509919177075679647"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.48162350"),
                    spread_penalty=Decimal("0.3464265738050989661331938004"),
                    volatility_penalty=Decimal("0.1414188890150961400"),
                    portfolio_overlap_penalty=Decimal("1.00"),
                    execution_cost_penalty=Decimal("0.1732132869025494830665969002"),
                    final_score=Decimal("-0.370401312873208638402102467"),
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="SPY",
            decision="selected",
            decision_reason="Top-ranked eligible opportunity.",
        )
    )

    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
                "TRADINGX_SERVICE_INTERVAL_SECONDS": "180",
                "TRADINGX_SYMBOL_UNIVERSE": "SPY,QQQ,IWM",
            }
        ),
        paper_store=paper_store,
        validation_store=FilesystemArtifactStore(tmp_path / "artifacts" / "validation"),
        docs_root=tmp_path / "docs",
        repo_root=tmp_path,
        service_manager=FakeServiceManager(
            WebServiceState(
                status="running",
                active_symbols=("SPY", "QQQ", "IWM"),
                interval_seconds=180,
                cycles_completed=1,
                started_at_utc=newer_timestamp,
                last_completed_at_utc=newer_timestamp,
                last_error="",
            )
        ),
        runtime_host_manager=FakeRuntimeHostManager(
            BotRuntimeState(
                status="trading_ready",
                status_reason="Runtime boot complete.",
                active_symbols=("SPY", "QQQ", "IWM"),
                started_at_utc=newer_timestamp,
                updated_at_utc=newer_timestamp,
                last_error="",
                active_strategy_id="baseline-long-only-v1",
                active_model_snapshot_id="approved-baseline-long-only-v1",
                latest_selection_id="selection-a-new",
            )
        ),
    )

    heartbeat = read_model.build_runtime_heartbeat_snapshot()
    symbol_rows = {row.symbol: row for row in heartbeat.symbol_rows}

    assert heartbeat.last_evaluation_at_utc == newer_timestamp
    assert heartbeat.score_explanation.startswith("SPY scored 0.7245")
    assert symbol_rows["SPY"].score == "0.7245"
    assert symbol_rows["QQQ"].score == "0.1154"
    assert symbol_rows["QQQ"].threshold_gap == "-0.3846"
    assert symbol_rows["IWM"].score == "-0.3704"
    assert symbol_rows["IWM"].threshold_gap == "-0.8704"
    assert symbol_rows["QQQ"].warmup_state == "Ready"
    assert symbol_rows["IWM"].warmup_state == "Ready"


def test_runtime_decision_detail_uses_selection_timestamp_and_selected_score(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 20, 14, 58, 30, tzinfo=UTC)
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    operator_store.write_strategy_activation_record(
        StrategyActivationRecord(
            activation_id="activation-1",
            strategy_id="baseline-long-only-v1",
            strategy_version="1.0.0",
            approved_symbols=("SPY",),
            deploy_threshold=Decimal("0.50"),
            allow_fallback_weights=True,
            status="approved",
            activated_at_utc=timestamp,
            notes="Approved.",
        )
    )
    operator_store.write_opportunity_selection_record(
        OpportunitySelectionRecord(
            selection_id="selection-1",
            generated_at_utc=timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="approved-baseline-long-only-v1",
            symbols_considered=("SPY",),
            ranked_opportunities=(
                OpportunityScore(
                    symbol="SPY",
                    base_signal=Decimal("0.40"),
                    regime_weight=Decimal("1.10"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.20"),
                    spread_penalty=Decimal("0.01"),
                    volatility_penalty=Decimal("0.02"),
                    portfolio_overlap_penalty=Decimal("0.03"),
                    execution_cost_penalty=Decimal("0.01"),
                    final_score=Decimal("0.75"),
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="SPY",
            decision="selected",
            decision_reason="SPY cleared the threshold.",
        )
    )

    detail = _minimal_read_model(tmp_path, timestamp).build_runtime_decision_detail()

    assert detail is not None
    assert detail.selection_id == "selection-1"
    assert detail.decision_source_at_utc == timestamp
    assert detail.signal.available is True
    assert detail.signal.symbol == "SPY"
    assert detail.signal.final_score == Decimal("0.75")
    assert detail.risk.threshold == Decimal("0.50")
    assert detail.risk.threshold_gap == Decimal("0.25")
    assert detail.freshness.decision_source_at_utc == timestamp


def test_runtime_decision_detail_missing_activation_keeps_threshold_unknown(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 20, 14, 58, 30, tzinfo=UTC)
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    operator_store.write_opportunity_selection_record(
        OpportunitySelectionRecord(
            selection_id="selection-1",
            generated_at_utc=timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="approved-baseline-long-only-v1",
            symbols_considered=("SPY",),
            ranked_opportunities=(
                OpportunityScore(
                    symbol="SPY",
                    base_signal=Decimal("0.40"),
                    regime_weight=Decimal("1.10"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.20"),
                    spread_penalty=Decimal("0.01"),
                    volatility_penalty=Decimal("0.02"),
                    portfolio_overlap_penalty=Decimal("0.03"),
                    execution_cost_penalty=Decimal("0.01"),
                    final_score=Decimal("0.75"),
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="SPY",
            decision="selected",
            decision_reason="SPY cleared the threshold.",
        )
    )

    detail = _minimal_read_model(tmp_path, timestamp).build_runtime_decision_detail()

    assert detail is not None
    assert detail.risk.threshold is None
    assert detail.risk.threshold_gap is None


def test_runtime_decision_detail_selected_symbol_mismatch_fails_closed(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 20, 14, 58, 30, tzinfo=UTC)
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    operator_store.write_opportunity_selection_record(
        OpportunitySelectionRecord(
            selection_id="selection-1",
            generated_at_utc=timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="approved-baseline-long-only-v1",
            symbols_considered=("SPY", "QQQ"),
            ranked_opportunities=(
                OpportunityScore(
                    symbol="QQQ",
                    base_signal=Decimal("0.40"),
                    regime_weight=Decimal("1.10"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.20"),
                    spread_penalty=Decimal("0.01"),
                    volatility_penalty=Decimal("0.02"),
                    portfolio_overlap_penalty=Decimal("0.03"),
                    execution_cost_penalty=Decimal("0.01"),
                    final_score=Decimal("0.75"),
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="SPY",
            decision="selected",
            decision_reason="SPY was selected.",
        )
    )

    detail = _minimal_read_model(tmp_path, timestamp).build_runtime_decision_detail()

    assert detail is not None
    assert detail.decision_source_at_utc == timestamp
    assert detail.selected_symbol == "SPY"
    assert detail.signal.available is False
    assert detail.signal.symbol is None
    assert detail.signal.final_score is None
    assert detail.risk.eligible is False
    assert (
        detail.risk.ineligibility_reason
        == "selected_symbol missing from ranked_opportunities"
    )


def test_runtime_decision_detail_no_trade_without_scores_keeps_null_signal_fields(
    tmp_path,
) -> None:
    timestamp = datetime(2026, 4, 20, 14, 58, 30, tzinfo=UTC)
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    operator_store.write_opportunity_selection_record(
        OpportunitySelectionRecord(
            selection_id="selection-1",
            generated_at_utc=timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="approved-baseline-long-only-v1",
            symbols_considered=("SPY", "QQQ"),
            ranked_opportunities=(),
            selected_symbol="",
            decision="no_trade",
            decision_reason="No candidate score is currently available.",
        )
    )

    detail = _minimal_read_model(tmp_path, timestamp).build_runtime_decision_detail()

    assert detail is not None
    assert detail.decision_source_at_utc == timestamp
    assert detail.signal.available is False
    assert detail.signal.final_score is None
    assert detail.risk.eligible is None
    assert detail.risk.threshold_gap is None


def test_runtime_heartbeat_uses_active_approved_symbols_over_config_universe(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    timestamp = datetime(2026, 4, 22, 14, 59, 2, tzinfo=UTC)
    approved_symbols = ("SPY", "QQQ", "IWM", "XLE", "XLF", "XLK", "EEM", "TLT")
    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-8-symbols",
            started_at_utc=timestamp,
            completed_at_utc=timestamp,
            cycle_status="executed",
            symbols=approved_symbols,
            symbol_results=(),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            open_position_symbols=("SPY", "QQQ", "IWM", "XLF"),
            cash=Decimal("98316.59"),
            equity=Decimal("100004.46"),
            buying_power=Decimal("398122.25"),
        )
    )
    operator_store.write_historical_warmup_record(
        HistoricalWarmupRecord(
            warmup_id="warmup-8-symbols",
            generated_at_utc=timestamp,
            benchmark_symbol="SPY",
            symbols=approved_symbols,
            window_start_utc=timestamp,
            window_end_utc=timestamp,
            required_bar_count=30,
            symbols_ready=approved_symbols,
            symbols_blocked={},
            return_summary={
                symbol: {
                    "cumulative_return": "0.02",
                    "mean_return": "0.0",
                    "volatility": "0.01",
                }
                for symbol in approved_symbols
            },
        )
    )
    operator_store.write_strategy_activation_record(
        StrategyActivationRecord(
            activation_id="activation-8-symbols",
            strategy_id="baseline-long-only-v1",
            strategy_version="1.0.0",
            approved_symbols=approved_symbols,
            deploy_threshold="0.50",
            allow_fallback_weights=True,
            status="approved",
            activated_at_utc=timestamp,
            notes="Expanded activation.",
        )
    )
    operator_store.write_opportunity_selection_record(
        OpportunitySelectionRecord(
            selection_id="selection-8-symbols",
            generated_at_utc=timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="approved-baseline-long-only-v1",
            symbols_considered=approved_symbols,
            ranked_opportunities=tuple(
                OpportunityScore(
                    symbol=symbol,
                    base_signal=Decimal("0.5"),
                    regime_weight=Decimal("1.0"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.0"),
                    spread_penalty=Decimal("0.01"),
                    volatility_penalty=Decimal("0.02"),
                    portfolio_overlap_penalty=(
                        Decimal("1.0")
                        if symbol in {"SPY", "QQQ", "IWM", "XLF"}
                        else Decimal("0.0")
                    ),
                    execution_cost_penalty=Decimal("0.01"),
                    final_score=Decimal("0.46"),
                    eligible=True,
                    ineligibility_reason="",
                )
                for symbol in approved_symbols
            ),
            selected_symbol="",
            decision="no_trade",
            decision_reason="No eligible opportunity cleared the deploy threshold.",
        )
    )

    read_model = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
                "TRADINGX_SERVICE_INTERVAL_SECONDS": "180",
                "TRADINGX_SYMBOL_UNIVERSE": "SPY,QQQ,IWM",
            }
        ),
        paper_store=paper_store,
        validation_store=FilesystemArtifactStore(tmp_path / "artifacts" / "validation"),
        docs_root=tmp_path / "docs",
        repo_root=tmp_path,
        service_manager=FakeServiceManager(
            WebServiceState(
                status="idle",
                active_symbols=(),
                interval_seconds=180,
                cycles_completed=1,
                started_at_utc=timestamp,
                last_completed_at_utc=timestamp,
                last_error="",
            )
        ),
        runtime_host_manager=FakeRuntimeHostManager(
            BotRuntimeState(
                status="trading_ready",
                status_reason="Runtime boot complete.",
                active_symbols=approved_symbols,
                started_at_utc=timestamp,
                updated_at_utc=timestamp,
                last_error="",
                active_strategy_id="baseline-long-only-v1",
                active_model_snapshot_id="approved-baseline-long-only-v1",
                latest_selection_id="selection-8-symbols",
            )
        ),
    )

    heartbeat = read_model.build_runtime_heartbeat_snapshot()

    assert [row.symbol for row in heartbeat.symbol_rows] == list(approved_symbols)
    assert [row.symbol for row in heartbeat.decision_ladder] == list(approved_symbols)


def test_gate3_readiness_preserves_persisted_source_lineage(tmp_path) -> None:
    timestamp = datetime(2026, 4, 20, 14, 30, tzinfo=UTC)
    oldest_source = datetime(2026, 4, 20, 14, 10, tzinfo=UTC)
    latest_source = datetime(2026, 4, 20, 14, 25, tzinfo=UTC)
    validation_store = FilesystemArtifactStore(tmp_path / "artifacts" / "validation")
    validation_store.write_gate3_readiness_report(
        Gate3ReadinessReport(
            report_id="gate3-1",
            generated_at_utc=timestamp,
            status="pending",
            closed_trade_count=4,
            calendar_days_observed=7,
            criteria=(
                Gate3CriterionSnapshot(
                    criterion_id="duration_or_trade_count",
                    status="pending",
                    threshold="At least 180 calendar days or 100 closed trades",
                    observed_value="4 trades / 7 days",
                    details="Gate 3 paper-history progress.",
                    evidence_refs=("artifacts/paper_loop/service_cycles/cycle-1.json",),
                    source_evidence_at_utc=oldest_source,
                    required=True,
                ),
                Gate3CriterionSnapshot(
                    criterion_id="replay_slippage_divergence",
                    status="pending",
                    threshold="Replay divergence <= limit",
                    observed_value="not available",
                    details="Diagnostic criterion.",
                    evidence_refs=(),
                    source_evidence_at_utc=latest_source,
                    required=False,
                ),
            ),
            summary="Gate 3 evidence is still incomplete.",
            required_operator_action="Continue paper trading and drills.",
            evidence_refs=("artifacts/validation/gate3_reports/gate3-1.json",),
            source_evidence_at_utc=oldest_source,
            oldest_required_source_evidence_at_utc=oldest_source,
            latest_source_evidence_at_utc=latest_source,
            required_criterion_ids=("duration_or_trade_count",),
            missing_source_criterion_ids=(),
        )
    )

    report = LocalWebReadModel(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
                "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
            }
        ),
        paper_store=FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop"),
        validation_store=validation_store,
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
        runtime_host_manager=FakeRuntimeHostManager(_minimal_runtime_state(timestamp)),
    ).build_gate3_readiness()

    assert report.source_evidence_at_utc == oldest_source
    assert report.oldest_required_source_evidence_at_utc == oldest_source
    assert report.latest_source_evidence_at_utc == latest_source
    assert report.required_criterion_ids == ("duration_or_trade_count",)
    assert report.missing_source_criterion_ids == ()
    assert report.criteria[0].source_evidence_at_utc == oldest_source
    assert report.criteria[0].required is True
    assert report.criteria[1].source_evidence_at_utc == latest_source
    assert report.criteria[1].required is False
