# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.config import TradingConfig
from tradingx.journal import SqliteOmsJournal
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    BotRuntimeState,
    EvaluationEvidencePack,
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

    ops_journal = SqliteOmsJournal(tmp_path / "artifacts" / "ops" / "data" / "journal.db")
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
    equity_card = next(card for card in snapshot.metric_cards if card.metric_id == "equity")

    assert [note.label for note in snapshot.source_notes] == [
        "Live account",
        "Live OMS journal",
        "Rehearsal baseline",
    ]
    assert equity_card.provenance is not None
    assert equity_card.provenance.label == "Mixed evidence"
    assert snapshot.execution_panel.provenance is not None
    assert snapshot.execution_panel.provenance.label == "Live OMS journal"


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
    assert (
        symbol_rows["IWM"].reason == "Insufficient daily bars for warmup coverage."
    )

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
