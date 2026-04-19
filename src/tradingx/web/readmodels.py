from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from tradingx.config import TradingConfig
from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    ApprovedWeightSnapshot,
    BotRuntimeState,
    CommandCenterSnapshot,
    ConfigProposal,
    DailySessionDigest,
    DashboardSnapshot,
    DocumentRecord,
    ExplorerRecord,
    Gate3CriterionSnapshot,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    HistoricalWarmupRecord,
    IncidentRecord,
    MarketAutomationRunRecord,
    MarketDayScheduleRecord,
    MarketDaySchedulerState,
    OperatorTimelineEvent,
    OpportunityScore,
    OpportunitySelectionRecord,
    ReplaySession,
    ReplaySlippageSummary,
    ResearchCandidateSummary,
    ResearchStudioSnapshot,
    ScalarValue,
    StrategyActivationRecord,
    WebServiceState,
)
from tradingx.weights import (
    ApprovedWeightSnapshotNotFoundError,
    ApprovedWeightSnapshotStore,
)


class ServiceManagerProtocol(Protocol):
    def get_state(self) -> WebServiceState: ...


class SchedulerManagerProtocol(Protocol):
    def get_state(self) -> MarketDaySchedulerState: ...


class RuntimeHostManagerProtocol(Protocol):
    def get_state(self) -> BotRuntimeState: ...


class _IdleSchedulerManager:
    def get_state(self) -> MarketDaySchedulerState:
        return MarketDaySchedulerState(
            status="idle",
            poll_interval_seconds=60,
            active_symbols=(),
            next_run_at_utc=None,
            last_started_at_utc=None,
            last_completed_at_utc=None,
            active_trading_day="",
            last_error="",
        )


class _IdleRuntimeHostManager:
    def get_state(self) -> BotRuntimeState:
        return BotRuntimeState(
            status="idle",
            status_reason="Runtime host is idle.",
            active_symbols=(),
            started_at_utc=None,
            updated_at_utc=datetime.now(UTC),
            last_error="",
            active_strategy_id="",
            active_model_snapshot_id="",
            latest_selection_id="",
        )


class LocalWebReadModel:
    def __init__(
        self,
        *,
        config: TradingConfig,
        paper_store: FilesystemArtifactStore,
        validation_store: FilesystemArtifactStore,
        docs_root: Path,
        repo_root: Path,
        service_manager: ServiceManagerProtocol,
        runtime_host_manager: RuntimeHostManagerProtocol | None = None,
        scheduler_manager: SchedulerManagerProtocol | None = None,
    ) -> None:
        self._config = config
        self._paper_store = paper_store
        self._validation_store = validation_store
        self._docs_root = docs_root
        self._repo_root = repo_root
        self._service_manager = service_manager
        self._runtime_host_manager = runtime_host_manager or _IdleRuntimeHostManager()
        self._scheduler_manager = scheduler_manager or _IdleSchedulerManager()
        artifact_root = config.runtime.artifact_root
        self._operator_platform_root = artifact_root / "operator_platform"
        self._approved_snapshot_store = ApprovedWeightSnapshotStore(
            repo_root / "config" / "strategy" / "weights"
        )

    def build_dashboard_snapshot(self) -> DashboardSnapshot:
        paper_report = self._paper_store.build_operator_evidence_report()
        validation_report = self._validation_store.build_operator_evidence_report()
        paper_summary = self._ensure_mapping(paper_report["summary"])
        validation_summary = self._ensure_mapping(validation_report["summary"])
        latest_cycle = self._pick_latest_payload(
            self._paper_store.list_artifact_payloads("service_cycles"),
            timestamp_field="completed_at_utc",
        )
        document_records = self.list_documents()
        latest_state_preview = next(
            (record.preview for record in document_records if record.kind == "state"),
            "",
        )
        positions = tuple(
            {
                "symbol": symbol,
                "quantity": "",
                "market_value": "",
            }
            for symbol in self._payload_strings(
                paper_summary.get("latest_open_positions", ())
            )
        )
        alerts = tuple(incident.summary for incident in self.list_incidents()[:5])
        return DashboardSnapshot(
            generated_at_utc=datetime.now(UTC),
            service_status=self._service_manager.get_state(),
            account_summary={
                "cash": (
                    str(latest_cycle.get("cash", ""))
                    if latest_cycle is not None
                    else ""
                ),
                "equity": (
                    str(latest_cycle.get("equity", ""))
                    if latest_cycle is not None
                    else ""
                ),
                "buying_power": (
                    str(latest_cycle.get("buying_power", ""))
                    if latest_cycle is not None
                    else ""
                ),
                "daily_pnl": str(paper_summary.get("daily_pnl", "")),
            },
            positions=positions,
            alerts=alerts,
            gate_statuses={
                str(key): str(value)
                for key, value in self._ensure_mapping(
                    validation_summary.get("latest_gate_statuses", {})
                ).items()
            },
            recommendations={
                str(key): int(str(value))
                for key, value in self._ensure_mapping(
                    validation_summary.get("evaluation_recommendations", {})
                ).items()
            },
            document_summary={
                "session_count": len(
                    [record for record in document_records if record.kind == "handover"]
                ),
                "latest_state": latest_state_preview,
            },
        )

    def build_command_center_snapshot(self) -> CommandCenterSnapshot:
        dashboard = self.build_dashboard_snapshot()
        service_cycles = self._paper_store.list_artifact_payloads("service_cycles")
        latest_open_positions = tuple(
            position["symbol"] for position in dashboard.positions if position["symbol"]
        )
        exposure_breakdown = self._build_exposure_breakdown(latest_open_positions)
        watchlist = tuple(
            {
                "symbol": symbol,
                "status": ("active" if symbol in latest_open_positions else "monitor"),
            }
            for symbol in self._config.runtime.symbol_universe
        )
        incidents = self.list_incidents()
        latest_cycle = self._pick_latest_payload(
            service_cycles,
            timestamp_field="completed_at_utc",
        )
        market_session_label = self._market_session_label(latest_cycle)
        session_mode = (
            "intraday" if dashboard.service_status.status == "running" else "standby"
        )
        return CommandCenterSnapshot(
            generated_at_utc=dashboard.generated_at_utc,
            service_status=dashboard.service_status,
            market_session_label=market_session_label,
            session_mode=session_mode,
            account_summary=dashboard.account_summary,
            equity_curve=tuple(
                {
                    "label": self._timeline_label(
                        str(payload.get("completed_at_utc", ""))
                    ),
                    "value": str(payload.get("equity", "")),
                }
                for payload in service_cycles[-12:]
            ),
            exposure_breakdown=exposure_breakdown,
            watchlist=watchlist,
            gate_statuses=dashboard.gate_statuses,
            recommendations=dashboard.recommendations,
            headline_incidents=tuple(
                {
                    "incident_id": incident.incident_id,
                    "severity": incident.severity,
                }
                for incident in incidents[:3]
            ),
        )

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        records: list[DocumentRecord] = []
        sessions_dir = self._docs_root / "handover" / "SESSIONS"
        for path in sorted(sessions_dir.glob("*.md"), reverse=True):
            records.append(
                DocumentRecord(
                    doc_id=path.stem,
                    title=path.stem.replace("-", " "),
                    path=path,
                    preview=self._preview_text(path),
                    kind="handover",
                )
            )
        for relative_path, kind, title in (
            (Path("handover/STATE.md"), "state", "Project state"),
            (Path("INDEX.md"), "index", "Artifact index"),
        ):
            path = self._docs_root / relative_path
            if path.exists():
                records.append(
                    DocumentRecord(
                        doc_id=path.stem,
                        title=title,
                        path=path,
                        preview=self._preview_text(path),
                        kind=kind,
                    )
                )
        return tuple(records)

    def list_evidence(self, category: str) -> list[dict[str, object]]:
        paper_payloads = self._paper_store.list_artifact_payloads(category)
        if paper_payloads:
            return paper_payloads
        return self._validation_store.list_artifact_payloads(category)

    def list_config_proposals(self) -> tuple[ConfigProposal, ...]:
        proposal_dir = self._repo_root / "config" / "proposals"
        if not proposal_dir.exists():
            return ()
        proposals: list[ConfigProposal] = []
        for path in sorted(proposal_dir.glob("*.md"), reverse=True):
            proposals.append(
                ConfigProposal(
                    proposal_id=path.stem,
                    target_area="proposal",
                    proposed_values={},
                    diff_preview=self._preview_text(path),
                    output_path=path,
                )
            )
        return tuple(proposals)

    def get_service_state(self) -> WebServiceState:
        return self._service_manager.get_state()

    def get_runtime_host_state(self) -> BotRuntimeState:
        return self._runtime_host_manager.get_state()

    def get_latest_historical_warmup(self) -> HistoricalWarmupRecord | None:
        payloads = self._operator_platform_store().list_artifact_payloads(
            "historical_warmups"
        )
        if not payloads:
            return None
        return self._historical_warmup_from_payload(payloads[-1])

    def get_latest_strategy_activation(self) -> StrategyActivationRecord | None:
        payloads = self._operator_platform_store().list_artifact_payloads(
            "strategy_activations"
        )
        if not payloads:
            return None
        return self._activation_from_payload(payloads[-1])

    def get_latest_model_weight_snapshot(self) -> ApprovedWeightSnapshot | None:
        activation = self.get_latest_strategy_activation()
        if activation is None:
            return None
        try:
            return self._approved_snapshot_store.load_by_strategy_id(
                activation.strategy_id
            )
        except ApprovedWeightSnapshotNotFoundError:
            return None

    def get_latest_opportunity_selection(self) -> OpportunitySelectionRecord | None:
        payloads = self._operator_platform_store().list_artifact_payloads(
            "opportunity_selections"
        )
        if not payloads:
            return None
        return self._opportunity_selection_from_payload(payloads[-1])

    def list_timeline_events(
        self,
        *,
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> tuple[OperatorTimelineEvent, ...]:
        events: list[OperatorTimelineEvent] = []
        events.extend(self._service_cycle_events())
        events.extend(self._trade_intent_events())
        events.extend(self._order_events())
        events.extend(self._risk_events())
        events.extend(self._reconciliation_events())
        events.extend(self._alert_events())
        events.extend(self._validation_events())
        events.extend(self._digest_events())
        events.extend(self._acknowledgement_events())
        if symbol is not None:
            events = [event for event in events if event.symbol in {"", symbol}]
        if cycle_id is not None:
            events = [
                event
                for event in events
                if cycle_id in event.related_ids or event.event_id == cycle_id
            ]
        if incident_id is not None:
            events = [
                event
                for event in events
                if incident_id in event.related_ids or event.event_id == incident_id
            ]
        return tuple(sorted(events, key=lambda item: item.occurred_at_utc))

    def list_incidents(self) -> tuple[IncidentRecord, ...]:
        acknowledgements = self._incident_ack_map()
        incidents: list[IncidentRecord] = []
        for payload in reversed(
            self._paper_store.list_artifact_payloads("operator_alerts")
        ):
            alert_id = str(payload.get("alert_id", ""))
            if not alert_id:
                continue
            incident_id = f"incident-{alert_id}"
            acknowledgement = acknowledgements.get(incident_id, {})
            acknowledged_at_raw = str(
                acknowledgement.get("acknowledged_at_utc", "")
            ).strip()
            incidents.append(
                IncidentRecord(
                    incident_id=incident_id,
                    title=str(payload.get("summary", "Operator incident")),
                    severity=str(payload.get("severity", "info")),
                    status="acknowledged" if acknowledged_at_raw else "open",
                    category=str(payload.get("category", "operator_alert")),
                    summary=str(payload.get("summary", "")),
                    first_seen_at_utc=self._parse_datetime(
                        str(payload.get("sent_at_utc", ""))
                    ),
                    latest_seen_at_utc=self._parse_datetime(
                        str(payload.get("sent_at_utc", ""))
                    ),
                    acknowledged_at_utc=(
                        self._parse_datetime(acknowledged_at_raw)
                        if acknowledged_at_raw
                        else None
                    ),
                    acknowledged_by=str(acknowledgement.get("acknowledged_by", "")),
                    related_event_ids=(alert_id,),
                    evidence_refs=self._payload_strings(
                        payload.get("evidence_refs", ())
                    ),
                    suggested_action=self._suggested_action_for_category(
                        str(payload.get("category", "operator_alert"))
                    ),
                )
            )
        return tuple(incidents)

    def build_research_snapshot(self) -> ResearchStudioSnapshot:
        generated_at = datetime.now(UTC)
        evaluation_payloads = self._validation_store.list_artifact_payloads(
            "evaluation_evidence"
        )
        validation_reports = self._validation_store.list_artifact_payloads(
            "validation_reports"
        )
        gate_assessments = self._validation_store.list_artifact_payloads(
            "gate_assessments"
        )
        candidate_statuses: dict[str, dict[str, str]] = {}
        for report in validation_reports:
            for candidate in self._ensure_list(report.get("candidate_results", [])):
                candidate_id = str(candidate.get("candidate_id", ""))
                if not candidate_id:
                    continue
                candidate_statuses.setdefault(candidate_id, {})[
                    str(report.get("gate_id", ""))
                ] = str(candidate.get("status", ""))
        candidate_summaries = tuple(
            ResearchCandidateSummary(
                candidate_id=str(payload.get("candidate_id", "")),
                family=self._candidate_family(str(payload.get("candidate_id", ""))),
                recommendation=str(payload.get("recommendation", "")),
                benchmark_metrics=self._ensure_scalar_mapping(
                    payload.get("benchmark_metrics", {})
                ),
                candidate_metrics=self._ensure_scalar_mapping(
                    payload.get("candidate_metrics", {})
                ),
                adversarial_checks=self._payload_strings(
                    payload.get("adversarial_checks", ())
                ),
                gate_statuses=candidate_statuses.get(
                    str(payload.get("candidate_id", "")),
                    {},
                ),
                summary=(
                    f"Recommendation: {payload.get('recommendation', '') or 'review'}."
                ),
            )
            for payload in reversed(evaluation_payloads)
        )
        gate_summaries = tuple(
            {
                "gate_id": str(payload.get("gate_id", "")),
                "status": str(payload.get("status", "")),
                "decision_summary": str(payload.get("decision_summary", "")),
            }
            for payload in gate_assessments
        )
        latest_gate = self._pick_latest_payload(
            gate_assessments,
            timestamp_field="recorded_at_utc",
        )
        if latest_gate is not None:
            generated_at = self._parse_datetime(
                str(latest_gate.get("recorded_at_utc", ""))
            )
        return ResearchStudioSnapshot(
            generated_at_utc=generated_at,
            gate_summaries=gate_summaries,
            candidate_summaries=candidate_summaries,
            decision_summary=(
                str(latest_gate.get("decision_summary", ""))
                if latest_gate is not None
                else "No gate assessments are available yet."
            ),
        )

    def build_replay_session(
        self,
        *,
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> ReplaySession:
        focus_type = "symbol"
        focus_value = symbol or cycle_id or incident_id or "latest"
        if cycle_id is not None:
            focus_type = "service_cycle"
        elif incident_id is not None:
            focus_type = "incident"
        events = self.list_timeline_events(
            symbol=symbol,
            cycle_id=cycle_id,
            incident_id=incident_id,
        )
        headline = f"{focus_value} replay"
        summary = (
            f"Replay contains {len(events)} events."
            if events
            else "No replayable events are available for this focus."
        )
        return ReplaySession(
            replay_id=f"replay-{focus_type}-{focus_value}",
            focus_type=focus_type,
            focus_value=focus_value,
            headline=headline,
            events=events,
            summary=summary,
        )

    def search_records(
        self,
        *,
        query: str = "",
        category: str | None = None,
    ) -> tuple[ExplorerRecord, ...]:
        query_lower = query.lower().strip()
        records: list[ExplorerRecord] = []
        records.extend(self._document_records_for_explorer())
        records.extend(self._artifact_records_for_explorer())
        if category is not None:
            records = [record for record in records if record.category == category]
        if query_lower:
            records = [
                record
                for record in records
                if query_lower in record.title.lower()
                or query_lower in record.preview.lower()
                or query_lower in record.category.lower()
                or query_lower in record.symbol.lower()
            ]
        return tuple(
            sorted(records, key=lambda record: record.recorded_at_utc, reverse=True)
        )

    def get_latest_daily_digest(self) -> DailySessionDigest | None:
        digest_dir = self._operator_platform_root / "daily_digests"
        if not digest_dir.exists():
            return None
        payloads = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(digest_dir.glob("*.json"))
        ]
        if not payloads:
            return None
        payload = max(payloads, key=lambda item: str(item.get("generated_at_utc", "")))
        return DailySessionDigest(
            digest_id=str(payload.get("digest_id", "")),
            generated_at_utc=self._parse_datetime(
                str(payload.get("generated_at_utc", ""))
            ),
            session_label=str(payload.get("session_label", "")),
            service_status=str(payload.get("service_status", "")),
            blocked_trade_count=int(str(payload.get("blocked_trade_count", 0))),
            reconciliation_failure_count=int(
                str(payload.get("reconciliation_failure_count", 0))
            ),
            latest_positions=self._payload_strings(payload.get("latest_positions", ())),
            top_incidents=self._payload_strings(payload.get("top_incidents", ())),
            recommended_actions=self._payload_strings(
                payload.get("recommended_actions", ())
            ),
            evidence_refs=self._payload_strings(payload.get("evidence_refs", ())),
        )

    def get_latest_market_automation_run(self) -> MarketAutomationRunRecord | None:
        run_dir = self._operator_platform_root / "market_automation_runs"
        if not run_dir.exists():
            return None
        payloads = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(run_dir.glob("*.json"))
        ]
        if not payloads:
            return None
        payload = max(payloads, key=lambda item: str(item.get("completed_at_utc", "")))
        return MarketAutomationRunRecord(
            run_id=str(payload.get("run_id", "")),
            started_at_utc=self._parse_datetime(str(payload.get("started_at_utc", ""))),
            completed_at_utc=self._parse_datetime(
                str(payload.get("completed_at_utc", ""))
            ),
            trading_day=str(payload.get("trading_day", "")),
            status=str(payload.get("status", "pending")),
            heartbeat_count=int(str(payload.get("heartbeat_count", 0))),
            preopen_session_id=str(payload.get("preopen_session_id", "")),
            heartbeat_session_ids=self._payload_strings(
                payload.get("heartbeat_session_ids", ())
            ),
            close_session_id=str(payload.get("close_session_id", "")),
            latest_replay_summary_id=str(payload.get("latest_replay_summary_id", "")),
            latest_gate3_report_id=str(payload.get("latest_gate3_report_id", "")),
            latest_gate3_package_id=str(payload.get("latest_gate3_package_id", "")),
            summary=str(payload.get("summary", "")),
            evidence_refs=self._payload_strings(payload.get("evidence_refs", ())),
        )

    def get_scheduler_state(self) -> MarketDaySchedulerState:
        return self._scheduler_manager.get_state()

    def get_latest_market_day_schedule(self) -> MarketDayScheduleRecord | None:
        payloads = self._operator_platform_store().list_artifact_payloads(
            "market_day_schedules"
        )
        if not payloads:
            return None
        payload = max(payloads, key=lambda item: str(item.get("launched_at_utc", "")))
        completed_raw = payload.get("completed_at_utc")
        return MarketDayScheduleRecord(
            schedule_id=str(payload.get("schedule_id", "")),
            trading_day=str(payload.get("trading_day", "")),
            scheduled_open_at_utc=self._parse_datetime(
                str(payload.get("scheduled_open_at_utc", ""))
            ),
            launched_at_utc=self._parse_datetime(
                str(payload.get("launched_at_utc", ""))
            ),
            completed_at_utc=(
                self._parse_datetime(str(completed_raw)) if completed_raw else None
            ),
            status=str(payload.get("status", "")),
            automation_run_id=str(payload.get("automation_run_id", "")),
            summary=str(payload.get("summary", "")),
            evidence_refs=self._payload_strings(payload.get("evidence_refs", ())),
        )

    def build_gate3_readiness(self) -> Gate3ReadinessReport:
        payloads = self._validation_store.list_artifact_payloads("gate3_reports")
        if not payloads:
            return build_gate3_readiness_report(
                paper_store=self._paper_store,
                validation_store=self._validation_store,
            )
        payload = max(payloads, key=lambda item: str(item.get("generated_at_utc", "")))
        return Gate3ReadinessReport(
            report_id=str(payload.get("report_id", "")),
            generated_at_utc=self._parse_datetime(
                str(payload.get("generated_at_utc", ""))
            ),
            status=str(payload.get("status", "pending")),
            closed_trade_count=int(str(payload.get("closed_trade_count", 0))),
            calendar_days_observed=int(str(payload.get("calendar_days_observed", 0))),
            criteria=tuple(
                Gate3CriterionSnapshot(
                    criterion_id=str(item.get("criterion_id", "")),
                    status=str(item.get("status", "pending")),
                    threshold=str(item.get("threshold", "")),
                    observed_value=str(item.get("observed_value", "")),
                    details=str(item.get("details", "")),
                    evidence_refs=self._payload_strings(item.get("evidence_refs", ())),
                )
                for item in self._ensure_list(payload.get("criteria", ()))
            ),
            summary=str(payload.get("summary", "")),
            required_operator_action=str(payload.get("required_operator_action", "")),
            evidence_refs=self._payload_strings(payload.get("evidence_refs", ())),
        )

    def get_latest_gate3_promotion_package(self) -> Gate3PromotionPackage | None:
        payloads = self._validation_store.list_artifact_payloads("gate3_packages")
        if payloads:
            payload = max(
                payloads,
                key=lambda item: str(item.get("generated_at_utc", "")),
            )
            return Gate3PromotionPackage(
                package_id=str(payload.get("package_id", "")),
                generated_at_utc=self._parse_datetime(
                    str(payload.get("generated_at_utc", ""))
                ),
                status=str(payload.get("status", "pending")),
                headline=str(payload.get("headline", "")),
                decision_summary=str(payload.get("decision_summary", "")),
                criteria_statuses={
                    str(key): str(value)
                    for key, value in self._ensure_mapping(
                        payload.get("criteria_statuses", {})
                    ).items()
                },
                evidence_refs=self._payload_strings(payload.get("evidence_refs", ())),
            )
        report = self.build_gate3_readiness()
        return build_gate3_promotion_package(report)

    def get_latest_replay_slippage_summary(self) -> ReplaySlippageSummary | None:
        payloads = self._validation_store.list_artifact_payloads(
            "replay_slippage_summaries"
        )
        if not payloads:
            return None
        payload = max(payloads, key=lambda item: str(item.get("generated_at_utc", "")))
        return ReplaySlippageSummary(
            summary_id=str(payload.get("summary_id", "")),
            matched_execution_count=int(str(payload.get("matched_execution_count", 0))),
            paper_mean_absolute_slippage_bps=Decimal(
                str(payload.get("paper_mean_absolute_slippage_bps", "0"))
            ),
            replay_mean_absolute_slippage_bps=Decimal(
                str(payload.get("replay_mean_absolute_slippage_bps", "0"))
            ),
            divergence_ratio=Decimal(str(payload.get("divergence_ratio", "0"))),
            status=str(payload.get("status", "pending")),
            details=str(payload.get("details", "")),
            generated_at_utc=self._parse_datetime(
                str(payload.get("generated_at_utc", ""))
            ),
        )

    def _historical_warmup_from_payload(
        self,
        payload: dict[str, object],
    ) -> HistoricalWarmupRecord:
        return HistoricalWarmupRecord(
            warmup_id=str(payload.get("warmup_id", "")),
            generated_at_utc=self._parse_datetime(
                str(payload.get("generated_at_utc", ""))
            ),
            benchmark_symbol=str(payload.get("benchmark_symbol", "")),
            symbols=self._payload_strings(payload.get("symbols", ())),
            window_start_utc=self._parse_datetime(
                str(payload.get("window_start_utc", ""))
            ),
            window_end_utc=self._parse_datetime(str(payload.get("window_end_utc", ""))),
            required_bar_count=int(str(payload.get("required_bar_count", 0))),
            symbols_ready=self._payload_strings(payload.get("symbols_ready", ())),
            symbols_blocked={
                str(key): str(value)
                for key, value in self._ensure_mapping(
                    payload.get("symbols_blocked", {})
                ).items()
            },
            return_summary={
                str(symbol): {
                    str(metric): Decimal(str(metric_value))
                    for metric, metric_value in self._ensure_mapping(summary).items()
                }
                for symbol, summary in self._ensure_mapping(
                    payload.get("return_summary", {})
                ).items()
            },
        )

    def _activation_from_payload(
        self,
        payload: dict[str, object],
    ) -> StrategyActivationRecord:
        return StrategyActivationRecord(
            activation_id=str(payload.get("activation_id", "")),
            strategy_id=str(payload.get("strategy_id", "")),
            strategy_version=str(payload.get("strategy_version", "")),
            approved_symbols=self._payload_strings(payload.get("approved_symbols", ())),
            deploy_threshold=Decimal(str(payload.get("deploy_threshold", "0"))),
            allow_fallback_weights=bool(payload.get("allow_fallback_weights", False)),
            status=str(payload.get("status", "")),
            activated_at_utc=self._parse_datetime(
                str(payload.get("activated_at_utc", ""))
            ),
            notes=str(payload.get("notes", "")),
        )

    def _opportunity_selection_from_payload(
        self,
        payload: dict[str, object],
    ) -> OpportunitySelectionRecord:
        ranked_payloads = payload.get("ranked_opportunities", [])
        ranked_opportunities: tuple[OpportunityScore, ...] = ()
        if isinstance(ranked_payloads, list):
            ranked_opportunities = tuple(
                OpportunityScore(
                    symbol=str(item.get("symbol", "")),
                    base_signal=Decimal(str(item.get("base_signal", "0"))),
                    regime_weight=Decimal(str(item.get("regime_weight", "0"))),
                    model_weight=Decimal(str(item.get("model_weight", "0"))),
                    liquidity_weight=Decimal(str(item.get("liquidity_weight", "0"))),
                    spread_penalty=Decimal(str(item.get("spread_penalty", "0"))),
                    volatility_penalty=Decimal(
                        str(item.get("volatility_penalty", "0"))
                    ),
                    portfolio_overlap_penalty=Decimal(
                        str(item.get("portfolio_overlap_penalty", "0"))
                    ),
                    execution_cost_penalty=Decimal(
                        str(item.get("execution_cost_penalty", "0"))
                    ),
                    final_score=Decimal(str(item.get("final_score", "0"))),
                    eligible=bool(item.get("eligible", False)),
                    ineligibility_reason=str(item.get("ineligibility_reason", "")),
                )
                for item in ranked_payloads
                if isinstance(item, dict)
            )
        return OpportunitySelectionRecord(
            selection_id=str(payload.get("selection_id", "")),
            generated_at_utc=self._parse_datetime(
                str(payload.get("generated_at_utc", ""))
            ),
            strategy_id=str(payload.get("strategy_id", "")),
            model_snapshot_id=str(payload.get("model_snapshot_id", "")),
            symbols_considered=self._payload_strings(
                payload.get("symbols_considered", ())
            ),
            ranked_opportunities=ranked_opportunities,
            selected_symbol=str(payload.get("selected_symbol", "")),
            decision=str(payload.get("decision", "")),
            decision_reason=str(payload.get("decision_reason", "")),
        )

    def _preview_text(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("---")
        ]
        return lines[1] if len(lines) > 1 else (lines[0] if lines else "")

    def _pick_latest_payload(
        self,
        payloads: list[dict[str, object]],
        *,
        timestamp_field: str,
    ) -> dict[str, object] | None:
        if not payloads:
            return None
        return max(payloads, key=lambda payload: str(payload.get(timestamp_field, "")))

    def _ensure_mapping(self, value: object) -> dict[str, object]:
        if isinstance(value, dict):
            return {str(key): item for key, item in value.items()}
        return {}

    def _ensure_scalar_mapping(self, value: object) -> dict[str, ScalarValue]:
        if not isinstance(value, dict):
            return {}
        scalar_mapping: dict[str, ScalarValue] = {}
        for key, item in value.items():
            if isinstance(item, bool | int | float | str):
                scalar_mapping[str(key)] = item
            elif isinstance(item, Decimal):
                scalar_mapping[str(key)] = item
        return scalar_mapping

    def _ensure_list(self, value: object) -> list[dict[str, object]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    def _payload_strings(self, value: object) -> tuple[str, ...]:
        if isinstance(value, list):
            return tuple(str(item) for item in value)
        if isinstance(value, tuple):
            return tuple(str(item) for item in value)
        return ()

    def _timeline_label(self, raw_timestamp: str) -> str:
        if not raw_timestamp:
            return ""
        timestamp = self._parse_datetime(raw_timestamp)
        return timestamp.strftime("%H:%M")

    def _market_session_label(self, latest_cycle: dict[str, object] | None) -> str:
        if latest_cycle is None:
            return "Local operator monitor"
        cycle_status = str(latest_cycle.get("cycle_status", "")).strip()
        if cycle_status == "market_closed":
            return "Market closed posture"
        if self._service_manager.get_state().status == "running":
            return "Regular session monitor"
        return "Post-session review"

    def _build_exposure_breakdown(
        self,
        latest_open_positions: tuple[str, ...],
    ) -> tuple[dict[str, str], ...]:
        if not latest_open_positions:
            return ()
        share = max(1, round(100 / len(latest_open_positions)))
        return tuple(
            {"symbol": symbol, "value": str(share)} for symbol in latest_open_positions
        )

    def _parse_datetime(self, raw_value: str) -> datetime:
        if not raw_value:
            return datetime(1970, 1, 1, tzinfo=UTC)
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            return datetime(1970, 1, 1, tzinfo=UTC)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _candidate_family(self, candidate_id: str) -> str:
        if "-v" in candidate_id:
            return candidate_id.split("-v", maxsplit=1)[0].replace("-", "_")
        return candidate_id or "candidate"

    def _suggested_action_for_category(self, category: str) -> str:
        suggestions = {
            "risk": "Review the blocked condition before the next session.",
            "validation": (
                "Inspect the related gate evidence and rerun validation if needed."
            ),
            "service": "Review the affected cycle and confirm recovery state.",
        }
        fallback = "Review the related evidence before proceeding."
        return suggestions.get(category, fallback)

    def _incident_ack_map(self) -> dict[str, dict[str, object]]:
        ack_dir = self._operator_platform_root / "incident_acknowledgements"
        if not ack_dir.exists():
            return {}
        payloads = {}
        for path in ack_dir.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payloads[str(payload.get("incident_id", path.stem))] = payload
        return payloads

    def _operator_platform_store(self) -> FilesystemArtifactStore:
        return FilesystemArtifactStore(self._operator_platform_root)

    def _service_cycle_events(self) -> list[OperatorTimelineEvent]:
        events: list[OperatorTimelineEvent] = []
        for payload in self._paper_store.list_artifact_payloads("service_cycles"):
            cycle_id = str(payload.get("cycle_id", ""))
            events.append(
                OperatorTimelineEvent(
                    event_id=cycle_id,
                    event_type="service_cycle",
                    symbol="",
                    severity="info",
                    headline=f"Service cycle {cycle_id}",
                    details=f"Cycle status: {payload.get('cycle_status', '')}.",
                    occurred_at_utc=self._parse_datetime(
                        str(payload.get("completed_at_utc", ""))
                    ),
                    artifact_path=str(
                        self._config.runtime.artifact_root
                        / "paper_loop"
                        / "service_cycles"
                        / f"{cycle_id}.json"
                    ),
                    related_ids=(cycle_id,),
                )
            )
        return events

    def _trade_intent_events(self) -> list[OperatorTimelineEvent]:
        events: list[OperatorTimelineEvent] = []
        for payload in self._paper_store.list_artifact_payloads("trade_intents"):
            intent_id = str(payload.get("intent_id", ""))
            symbol = str(payload.get("symbol", ""))
            events.append(
                OperatorTimelineEvent(
                    event_id=intent_id,
                    event_type="trade_intent",
                    symbol=symbol,
                    severity="info",
                    headline=f"Trade intent for {symbol}",
                    details=f"Reason code: {payload.get('reason_code', '')}.",
                    occurred_at_utc=self._parse_datetime(
                        str(payload.get("generated_at_utc", ""))
                    ),
                    artifact_path=str(
                        self._config.runtime.artifact_root
                        / "paper_loop"
                        / "trade_intents"
                        / f"{intent_id}.json"
                    ),
                    related_ids=(intent_id,),
                )
            )
        return events

    def _order_events(self) -> list[OperatorTimelineEvent]:
        events: list[OperatorTimelineEvent] = []
        for payload in self._paper_store.list_artifact_payloads("orders"):
            order_id = str(payload.get("order_id", ""))
            symbol = str(payload.get("symbol", ""))
            client_order_id = str(payload.get("client_order_id", ""))
            events.append(
                OperatorTimelineEvent(
                    event_id=order_id or client_order_id,
                    event_type="order",
                    symbol=symbol,
                    severity="info",
                    headline=f"Order for {symbol}",
                    details=f"Status: {payload.get('status', '')}.",
                    occurred_at_utc=datetime.now(UTC),
                    artifact_path=str(
                        self._config.runtime.artifact_root / "paper_loop" / "orders"
                    ),
                    related_ids=tuple(
                        item for item in (order_id, client_order_id) if item
                    ),
                )
            )
        return events

    def _risk_events(self) -> list[OperatorTimelineEvent]:
        events: list[OperatorTimelineEvent] = []
        for payload in self._paper_store.list_artifact_payloads("risk_events"):
            event_id = str(payload.get("event_id", ""))
            severity = str(payload.get("severity", "warning"))
            events.append(
                OperatorTimelineEvent(
                    event_id=event_id,
                    event_type="risk_event",
                    symbol="",
                    severity=severity,
                    headline=f"Risk event {payload.get('control_type', '')}",
                    details=f"Blocked: {payload.get('blocked', False)}.",
                    occurred_at_utc=self._parse_datetime(
                        str(payload.get("recorded_at_utc", ""))
                    ),
                    artifact_path=str(
                        self._config.runtime.artifact_root
                        / "paper_loop"
                        / "risk_events"
                        / f"{event_id}.json"
                    ),
                    related_ids=(
                        (str(payload.get("intent_id", "")),)
                        if payload.get("intent_id")
                        else ()
                    ),
                )
            )
        return events

    def _reconciliation_events(self) -> list[OperatorTimelineEvent]:
        events: list[OperatorTimelineEvent] = []
        for payload in self._paper_store.list_artifact_payloads("reconciliation"):
            reconciliation_id = str(payload.get("reconciliation_id", ""))
            events.append(
                OperatorTimelineEvent(
                    event_id=reconciliation_id,
                    event_type="reconciliation",
                    symbol="",
                    severity=(
                        "warning"
                        if not bool(payload.get("resolved", False))
                        else "info"
                    ),
                    headline=f"Reconciliation {reconciliation_id}",
                    details=(
                        "Resolved."
                        if bool(payload.get("resolved", False))
                        else "Differences remain unresolved."
                    ),
                    occurred_at_utc=self._parse_datetime(
                        str(
                            self._ensure_mapping(
                                payload.get("portfolio_state", {})
                            ).get("as_of_utc", "")
                        )
                    ),
                    artifact_path=str(
                        self._config.runtime.artifact_root
                        / "paper_loop"
                        / "reconciliation"
                        / f"{reconciliation_id}.json"
                    ),
                    related_ids=(reconciliation_id,),
                )
            )
        return events

    def _alert_events(self) -> list[OperatorTimelineEvent]:
        events: list[OperatorTimelineEvent] = []
        for payload in self._paper_store.list_artifact_payloads("operator_alerts"):
            alert_id = str(payload.get("alert_id", ""))
            events.append(
                OperatorTimelineEvent(
                    event_id=f"incident-{alert_id}",
                    event_type="operator_alert",
                    symbol="",
                    severity=str(payload.get("severity", "warning")),
                    headline=str(payload.get("summary", "Operator alert")),
                    details=str(payload.get("summary", "")),
                    occurred_at_utc=self._parse_datetime(
                        str(payload.get("sent_at_utc", ""))
                    ),
                    artifact_path=str(
                        self._config.runtime.artifact_root
                        / "paper_loop"
                        / "operator_alerts"
                        / f"{alert_id}.json"
                    ),
                    related_ids=(alert_id, f"incident-{alert_id}"),
                )
            )
        return events

    def _validation_events(self) -> list[OperatorTimelineEvent]:
        events: list[OperatorTimelineEvent] = []
        for payload in self._validation_store.list_artifact_payloads(
            "validation_reports"
        ):
            report_id = str(payload.get("report_id", ""))
            events.append(
                OperatorTimelineEvent(
                    event_id=report_id,
                    event_type="validation_report",
                    symbol=str(payload.get("benchmark_symbol", "")),
                    severity="info",
                    headline=f"Gate {payload.get('gate_id', '')} report",
                    details=str(payload.get("summary", "")),
                    occurred_at_utc=self._parse_datetime(
                        str(payload.get("generated_at_utc", ""))
                    ),
                    artifact_path=str(
                        self._config.runtime.artifact_root
                        / "validation"
                        / "validation_reports"
                        / f"{report_id}.json"
                    ),
                    related_ids=(str(payload.get("gate_id", "")),),
                )
            )
        return events

    def _digest_events(self) -> list[OperatorTimelineEvent]:
        events: list[OperatorTimelineEvent] = []
        digest_dir = self._operator_platform_root / "daily_digests"
        if not digest_dir.exists():
            return events
        for path in sorted(digest_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            digest_id = str(payload.get("digest_id", path.stem))
            events.append(
                OperatorTimelineEvent(
                    event_id=digest_id,
                    event_type="daily_digest",
                    symbol="",
                    severity="info",
                    headline=f"Digest {payload.get('session_label', '')}",
                    details=f"Service status: {payload.get('service_status', '')}.",
                    occurred_at_utc=self._parse_datetime(
                        str(payload.get("generated_at_utc", ""))
                    ),
                    artifact_path=str(path),
                    related_ids=(digest_id,),
                )
            )
        return events

    def _acknowledgement_events(self) -> list[OperatorTimelineEvent]:
        events: list[OperatorTimelineEvent] = []
        ack_dir = self._operator_platform_root / "incident_acknowledgements"
        if not ack_dir.exists():
            return events
        for path in sorted(ack_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            incident_id = str(payload.get("incident_id", path.stem))
            events.append(
                OperatorTimelineEvent(
                    event_id=incident_id,
                    event_type="incident_acknowledgement",
                    symbol="",
                    severity="info",
                    headline=f"Acknowledged {incident_id}",
                    details=str(payload.get("acknowledged_by", "local-operator")),
                    occurred_at_utc=self._parse_datetime(
                        str(payload.get("acknowledged_at_utc", ""))
                    ),
                    artifact_path=str(path),
                    related_ids=(incident_id,),
                )
            )
        return events

    def _document_records_for_explorer(self) -> list[ExplorerRecord]:
        records: list[ExplorerRecord] = []
        now = datetime.now(UTC)
        for document in self.list_documents():
            records.append(
                ExplorerRecord(
                    record_id=document.doc_id,
                    category=document.kind,
                    title=document.title,
                    preview=document.preview,
                    path=str(document.path),
                    symbol="",
                    recorded_at_utc=now,
                )
            )
        for proposal in self.list_config_proposals():
            records.append(
                ExplorerRecord(
                    record_id=proposal.proposal_id,
                    category="config_proposal",
                    title=proposal.proposal_id,
                    preview=proposal.diff_preview,
                    path=str(proposal.output_path),
                    symbol="",
                    recorded_at_utc=now,
                )
            )
        return records

    def _artifact_records_for_explorer(self) -> list[ExplorerRecord]:
        records: list[ExplorerRecord] = []
        for category, store in (
            ("operator_alert", self._paper_store),
            ("service_cycle", self._paper_store),
            ("validation_report", self._validation_store),
        ):
            artifact_category = (
                "operator_alerts"
                if category == "operator_alert"
                else (
                    "service_cycles"
                    if category == "service_cycle"
                    else "validation_reports"
                )
            )
            for payload in store.list_artifact_payloads(artifact_category):
                records.append(
                    ExplorerRecord(
                        record_id=str(
                            payload.get("alert_id")
                            or payload.get("cycle_id")
                            or payload.get("report_id")
                            or payload.get("gate_id")
                        ),
                        category=category,
                        title=str(
                            payload.get("summary")
                            or payload.get("cycle_status")
                            or f"Gate {payload.get('gate_id', '')} report"
                        ),
                        preview=str(
                            payload.get("summary")
                            or payload.get("decision_summary")
                            or payload.get("cycle_status")
                            or ""
                        ),
                        path=str(
                            self._config.runtime.artifact_root / artifact_category
                        ),
                        symbol=str(
                            payload.get("symbol")
                            or payload.get("benchmark_symbol")
                            or ""
                        ),
                        recorded_at_utc=self._parse_datetime(
                            str(
                                payload.get("sent_at_utc")
                                or payload.get("completed_at_utc")
                                or payload.get("generated_at_utc")
                                or payload.get("recorded_at_utc")
                                or ""
                            )
                        ),
                    )
                )
        latest_digest = self.get_latest_daily_digest()
        if latest_digest is not None:
            records.append(
                ExplorerRecord(
                    record_id=latest_digest.digest_id,
                    category="daily_digest",
                    title=latest_digest.session_label,
                    preview=", ".join(latest_digest.recommended_actions),
                    path=str(
                        self._operator_platform_root
                        / "daily_digests"
                        / f"{latest_digest.digest_id}.json"
                    ),
                    symbol="",
                    recorded_at_utc=latest_digest.generated_at_utc,
                )
            )
        return records


__all__ = ("LocalWebReadModel",)
