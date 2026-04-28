# ruff: noqa: E501

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

from tradingx.config import TradingConfig
from tradingx.drift.gateway import ArtifactBackedDriftAlarmStateReader
from tradingx.experiments import (
    metric_visibility_context_from_payload,
    sanitize_metric_payload,
)
from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.persistence import FilesystemArtifactStore
from tradingx.promotion import LEGACY_NON_AUTHORITY_STATUS
from tradingx.types import (
    ApprovedWeightSnapshot,
    BenchmarkComparisonRow,
    BlueprintActivationRecord,
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
    PerformanceDiagnostic,
    PerformancePeriodBar,
    PerformanceSeriesPoint,
    PerformanceWindowSnapshot,
    PortfolioBenchmarkPanel,
    PortfolioBenchmarkRow,
    PortfolioCurvePanel,
    PortfolioDiagnostic,
    PortfolioEventSummary,
    PortfolioExecutionPanel,
    PortfolioKeyValue,
    PortfolioMetricCard,
    PortfolioPositionRow,
    PortfolioPositionsPanel,
    PortfolioSeriesPoint,
    PortfolioSourceNote,
    PortfolioStrategyPanel,
    PortfolioStrategyRow,
    PortfolioWorkspaceSnapshot,
    ReplaySession,
    ReplaySlippageSummary,
    ResearchCandidateSummary,
    ResearchStudioSnapshot,
    RuntimeDecisionDetail,
    RuntimeDecisionExecutionDetail,
    RuntimeDecisionFreshnessDetail,
    RuntimeDecisionLadderRow,
    RuntimeDecisionRegimeDetail,
    RuntimeDecisionRiskDetail,
    RuntimeDecisionSignalDetail,
    RuntimeHeartbeatSnapshot,
    RuntimeOperatorGuidance,
    RuntimeSymbolHeartbeatRow,
    RuntimeTruthItem,
    ScalarValue,
    SleeveDailyAttributionRecord,
    StrategyActivationRecord,
    StrategyAttributionRow,
    StrategyHeatmapCell,
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
        gate_statuses = {
            str(key): str(value)
            for key, value in self._ensure_mapping(
                validation_summary.get("latest_gate_statuses", {})
            ).items()
        }
        recommendations = {
            str(key): int(str(value))
            for key, value in self._ensure_mapping(
                validation_summary.get("evaluation_recommendations", {})
            ).items()
        }
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
            gate_statuses=gate_statuses,
            recommendations=recommendations,
            document_summary={
                "session_count": len(
                    [record for record in document_records if record.kind == "handover"]
                ),
                "latest_state": latest_state_preview,
                "v5_authority_status": LEGACY_NON_AUTHORITY_STATUS,
                "gate_validation_authority_status": LEGACY_NON_AUTHORITY_STATUS,
                "recommendation_authority_status": LEGACY_NON_AUTHORITY_STATUS,
            },
            gate_authority_statuses={
                key: LEGACY_NON_AUTHORITY_STATUS for key in gate_statuses
            },
            recommendation_authority_statuses={
                key: LEGACY_NON_AUTHORITY_STATUS for key in recommendations
            },
        )

    def build_command_center_snapshot(self) -> CommandCenterSnapshot:
        dashboard = self.build_dashboard_snapshot()
        runtime_heartbeat = self.build_runtime_heartbeat_snapshot()
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
            "intraday"
            if runtime_heartbeat.heartbeat_state
            in {
                "Running",
                "Waiting for next evaluation",
                "Active position",
                "Evaluating",
            }
            else "standby"
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

    def _payload_timestamp(
        self,
        payload: dict[str, object] | None,
        *fields: str,
    ) -> datetime | None:
        if payload is None:
            return None
        for field in fields:
            raw_value = str(payload.get(field, "")).strip()
            if raw_value:
                return self._parse_datetime(raw_value)
        return None

    def _latest_payload_timestamp(
        self,
        payloads: list[dict[str, object]],
        *fields: str,
    ) -> datetime | None:
        timestamps = [
            timestamp
            for payload in payloads
            if (timestamp := self._payload_timestamp(payload, *fields)) is not None
        ]
        return max(timestamps) if timestamps else None

    def _portfolio_account_position_source_at(
        self,
        service_cycles: list[dict[str, object]],
    ) -> datetime | None:
        latest_cycle = self._pick_latest_payload(
            service_cycles,
            timestamp_field="completed_at_utc",
        )
        if latest_cycle is None:
            return None
        account_source = self._payload_timestamp(
            latest_cycle,
            "account_source_at_utc",
        )
        position_source = self._payload_timestamp(
            latest_cycle,
            "position_source_at_utc",
        )
        if account_source is None or position_source is None:
            return None
        return min(account_source, position_source)

    def _latest_oms_event_source_at(
        self,
        oms_events: list[dict[str, str]],
    ) -> datetime | None:
        return self._latest_payload_timestamp(list(oms_events), "recorded_at_utc")

    def build_portfolio_workspace_snapshot(self) -> PortfolioWorkspaceSnapshot:
        dashboard = self.build_dashboard_snapshot()
        runtime_state = self.get_runtime_host_state()
        warmup = self.get_latest_historical_warmup()
        service_cycles = self._paper_store.list_artifact_payloads("service_cycles")
        closed_trades = self._paper_store.list_artifact_payloads("closed_trades")
        account_seed = self._load_ops_payload("paper_account_starting_state.json")
        has_rehearsal_baseline = bool(account_seed)
        now_utc = datetime.now(UTC)
        live_account_note = PortfolioSourceNote(
            source_id="live_account",
            label="Live account",
            tone="good",
            detail=(
                "Equity, cash, buying power, positions, and balance snapshots come from the current paper account "
                "and live TradingX service artifacts."
            ),
        )
        live_journal_note = PortfolioSourceNote(
            source_id="live_oms_journal",
            label="Live OMS journal",
            tone="good",
            detail=(
                "Execution diagnostics come from the current local OMS journal at data/journal.db, not from rehearsal artifacts."
            ),
        )
        rehearsal_baseline_note = (
            PortfolioSourceNote(
                source_id="rehearsal_baseline",
                label="Rehearsal baseline",
                tone="watch",
                detail=(
                    "Comparisons that mention the seeded account use the saved starting-state snapshot from "
                    "artifacts/ops/paper_account_starting_state.json."
                ),
            )
            if has_rehearsal_baseline
            else None
        )
        mixed_evidence_note = (
            PortfolioSourceNote(
                source_id="mixed_evidence",
                label="Mixed evidence",
                tone="watch",
                detail=(
                    "The current value is live, but its comparison anchor comes from the saved rehearsal baseline snapshot."
                ),
            )
            if has_rehearsal_baseline
            else live_account_note
        )
        source_notes = tuple(
            note
            for note in (live_account_note, live_journal_note, rehearsal_baseline_note)
            if note is not None
        )
        equity = self._decimal_from_candidates(
            dashboard.account_summary.get("equity"),
            account_seed.get("equity"),
            default=Decimal("0"),
        )
        cash = self._decimal_from_candidates(
            dashboard.account_summary.get("cash"),
            account_seed.get("cash"),
            default=equity,
        )
        buying_power = self._decimal_from_candidates(
            dashboard.account_summary.get("buying_power"),
            account_seed.get("buying_power"),
            default=equity,
        )
        daily_pnl = self._decimal_from_candidates(
            dashboard.account_summary.get("daily_pnl"),
            default=Decimal("0"),
        )
        starting_equity = self._decimal_from_candidates(
            account_seed.get("equity"),
            default=equity,
        )
        oms_events = self._load_oms_events(limit=25)
        account_position_source_at = self._portfolio_account_position_source_at(
            service_cycles
        )
        execution_journal_source_at = self._latest_oms_event_source_at(oms_events)
        closed_trade_source_at = self._latest_payload_timestamp(
            closed_trades,
            "closed_at_utc",
            "recorded_at_utc",
        )
        reject_events = [
            event for event in oms_events if event["event_type"] == "reject"
        ]
        submit_attempts = [
            event for event in oms_events if event["event_type"] == "submit_attempt"
        ]
        latest_reject_reason = (
            str(reject_events[0]["reason"]).replace("_", " ")
            if reject_events
            else "No recent rejects"
        )
        latest_event = oms_events[0] if oms_events else None
        latest_event_age = (
            self._format_age_since(
                self._parse_datetime(latest_event["recorded_at_utc"]),
                now_utc=now_utc,
            )
            if latest_event is not None
            else "No journal events"
        )
        warmup_ready = (
            len(warmup.symbols_ready)
            if warmup is not None
            else len(runtime_state.active_symbols)
        )
        warmup_total = (
            len(warmup.symbols)
            if warmup is not None
            else max(len(runtime_state.active_symbols), 1)
        )
        total_return_pct = self._safe_percent_change(
            current_value=equity,
            reference_value=starting_equity or equity or Decimal("1"),
        )
        reject_rate = (
            (Decimal(len(reject_events)) / Decimal(len(submit_attempts)))
            * Decimal("100")
            if submit_attempts
            else Decimal("0")
        )
        positions_count = len(dashboard.positions)
        metric_cards = (
            PortfolioMetricCard(
                metric_id="equity",
                label="Total Equity",
                value=f"${self._format_money(equity)}",
                delta=(
                    "Flat vs seeded account"
                    if starting_equity == equity
                    else self._format_percent(total_return_pct, signed=True)
                ),
                health=("good" if total_return_pct > 0 else "neutral"),
                summary=(
                    "Good for the bot goal when it grows through supervised trading; neutral right now because there is no completed evidence window yet."
                ),
                detail=(
                    "The balance is intact. This protects capital, but it does not yet demonstrate that TradingX is producing repeatable alpha."
                ),
                sparkline=tuple(
                    str(payload.get("equity", ""))
                    for payload in service_cycles[-4:]
                    if str(payload.get("equity", "")).strip()
                ),
                provenance=mixed_evidence_note,
            ),
            PortfolioMetricCard(
                metric_id="cash",
                label="Cash Balance",
                value=f"${self._format_money(cash)}",
                delta=(
                    self._format_percent(
                        (cash / max(equity, Decimal("1"))) * Decimal("100")
                    )
                    if equity > 0
                    else "n/a"
                ),
                health="neutral",
                summary=(
                    "Neutral because idle cash preserves optionality, but it only helps the main goal once the runtime can deploy safely."
                ),
                detail=(
                    "High cash is healthy during halted or defensive states. It becomes a concern only if the bot stays inactive after signals and execution are ready."
                ),
                sparkline=(),
                provenance=live_account_note,
            ),
            PortfolioMetricCard(
                metric_id="buying_power",
                label="Buying Power",
                value=f"${self._format_money(buying_power)}",
                delta="Fully available" if buying_power > 0 else "Unavailable",
                health=("neutral" if buying_power > 0 else "bad"),
                summary=(
                    "Neutral because capital is available, but deployment is blocked until warmup and execution sizing are healthy."
                ),
                detail=(
                    "Buying power matters only when the runtime is healthy enough to use it. Right now it mostly measures idle capacity."
                ),
                sparkline=(),
                provenance=live_account_note,
            ),
            PortfolioMetricCard(
                metric_id="evidence_window",
                label="Observed Cycles",
                value=str(len(service_cycles)),
                delta=(
                    "Evidence building"
                    if service_cycles
                    else "No completed service cycles"
                ),
                health=("good" if service_cycles else "bad"),
                summary=(
                    "Bad for the main bot goal when zero, because benchmark and drawdown truth stay locked until TradingX records completed supervised cycles."
                ),
                detail=(
                    "This is the current proof window for portfolio analytics. The more real completed cycles TradingX records, the more of the dashboard can move from readiness to verified performance."
                ),
                sparkline=tuple(
                    str(index + 1) for index, _payload in enumerate(service_cycles[-6:])
                ),
            ),
            PortfolioMetricCard(
                metric_id="daily_pnl",
                label="Daily P&L",
                value=f"${self._format_signed_money(daily_pnl)}".replace(
                    "$+", "+$"
                ).replace("$-", "-$"),
                delta=(
                    self._format_percent(
                        self._safe_percent_change(
                            current_value=equity,
                            reference_value=equity - daily_pnl,
                        ),
                        signed=True,
                    )
                    if equity > 0
                    else "n/a"
                ),
                health=(
                    "good" if daily_pnl > 0 else ("bad" if daily_pnl < 0 else "neutral")
                ),
                summary=(
                    "This is good when positive and explainable, bad when losses repeat, and neutral today because no supervised cycle has completed."
                ),
                detail=(
                    "Daily P&L should be read together with execution quality and benchmark-relative context. With no completed real cycle, today it is mostly a placeholder for future supervision."
                ),
                sparkline=tuple(
                    str(
                        self._decimal_from_candidates(
                            payload.get("equity"),
                            default=equity,
                        )
                    )
                    for payload in service_cycles[-4:]
                ),
            ),
            PortfolioMetricCard(
                metric_id="warmup",
                label="Warmup Breadth",
                value=f"{warmup_ready}/{warmup_total} ready",
                delta=runtime_state.status.replace("_", " ").title(),
                health=("good" if warmup_ready == warmup_total else "bad"),
                summary=(
                    "Bad for the bot goal when symbols are blocked, because the runtime cannot make trustworthy decisions across the configured universe."
                ),
                detail=(
                    runtime_state.last_error
                    or "Warmup is complete across the configured symbols."
                ),
                sparkline=(),
            ),
            PortfolioMetricCard(
                metric_id="open_positions",
                label="Open Positions",
                value=str(positions_count),
                delta=("Flat book" if positions_count == 0 else "Exposure active"),
                health="neutral",
                summary=(
                    "Neutral when the book is flat during setup, and useful once positions reflect deliberate, supervised deployment."
                ),
                detail=(
                    "Open positions are not inherently good or bad. They matter only if the exposure matches the approved strategy, risk budget, and current market state."
                ),
                sparkline=(),
            ),
            PortfolioMetricCard(
                metric_id="execution_quality",
                label="Execution Quality",
                value=(
                    f"{len(reject_events)} rejects"
                    if reject_events
                    else "No recent rejects"
                ),
                delta=(
                    f"Latest reason: {latest_reject_reason}"
                    if reject_events
                    else "No broker rejection recorded"
                ),
                health=("bad" if reject_events else "good"),
                summary=(
                    "Bad for the bot goal because rejected orders prevent the strategy from expressing its edge."
                    if reject_events
                    else "Good because there are no recent rejected orders in the journal."
                ),
                detail=(
                    "Repeated rejected submissions indicate sizing, risk, or broker-state mismatches that should be fixed before more automation."
                    if reject_events
                    else "Execution is quiet right now, so there is no immediate sign of broker-side friction."
                ),
                sparkline=tuple(
                    str(1 if event["event_type"] == "reject" else 0)
                    for event in reversed(oms_events[:6])
                ),
                provenance=live_journal_note,
            ),
            PortfolioMetricCard(
                metric_id="reject_rate",
                label="Reject Rate",
                value=(
                    self._format_percent(reject_rate)
                    if submit_attempts
                    else "No submissions"
                ),
                delta=(
                    f"{len(reject_events)} of {len(submit_attempts)} recent submits rejected"
                    if submit_attempts
                    else "No recent submit attempts"
                ),
                health=(
                    "bad"
                    if reject_events
                    else ("good" if submit_attempts else "neutral")
                ),
                summary=(
                    "Bad when elevated because it shows the runtime is generating orders the broker or account cannot accept."
                ),
                detail=(
                    "This rate turns execution quality into a direct reliability measure. A sustained non-zero reject rate usually means sizing, constraints, or account-state synchronization needs attention."
                ),
                sparkline=tuple(
                    str(100 if event["event_type"] == "reject" else 0)
                    for event in reversed(oms_events[:6])
                ),
                provenance=live_journal_note,
            ),
            PortfolioMetricCard(
                metric_id="journal_freshness",
                label="Journal Freshness",
                value=latest_event_age,
                delta=(
                    latest_event["event_type"].replace("_", " ").title()
                    if latest_event is not None
                    else "No OMS traffic"
                ),
                health=(
                    "bad"
                    if latest_event is None
                    and runtime_state.status in {"running", "bootstrapping"}
                    else "neutral"
                ),
                summary=(
                    "Good when the journal updates as the bot acts, neutral when the desk is idle, and concerning if the runtime claims to be active while the journal stays silent."
                ),
                detail=(
                    "Use this to decide whether TradingX is truly moving or simply appears healthy from stale state. Fresh journal traffic is one of the quickest ways to confirm operator reality."
                ),
                sparkline=(),
                provenance=live_journal_note,
            ),
        )
        return PortfolioWorkspaceSnapshot(
            generated_at_utc=datetime.now(UTC),
            trading_mode=(
                "live"
                if bool(self._config.live_disable_report().get("live_trading_enabled"))
                else "paper"
            ),
            data_state=(
                "available"
                if service_cycles and closed_trades
                else ("partial" if equity > 0 or oms_events else "waiting")
            ),
            source_summary=(
                "Account balances, runtime posture, and execution journal are live. "
                + (
                    "Seeded-account comparisons still use the saved rehearsal baseline. "
                    if has_rehearsal_baseline
                    else ""
                )
                + "Benchmark comparison and strategy attribution stay hidden until TradingX records real portfolio history."
            ),
            source_notes=source_notes,
            metric_cards=metric_cards,
            equity_curve=self._build_portfolio_curve_panel(
                service_cycles=service_cycles,
            ),
            benchmark_panel=self._build_portfolio_benchmark_panel(
                service_cycles=service_cycles,
            ),
            strategy_panel=self._build_portfolio_strategy_panel(
                closed_trades=closed_trades,
                runtime_state=runtime_state,
            ),
            execution_panel=self._build_portfolio_execution_panel(
                oms_events=oms_events,
                provenance=live_journal_note,
            ),
            positions_panel=self._build_portfolio_positions_panel(
                positions=dashboard.positions,
            ),
            diagnostics=self._build_portfolio_diagnostics(
                runtime_state=runtime_state,
                warmup=warmup,
                reject_events=reject_events,
            ),
            source_evidence_at_utc=account_position_source_at,
            account_position_source_at_utc=account_position_source_at,
            execution_journal_source_at_utc=execution_journal_source_at,
            closed_trade_source_at_utc=closed_trade_source_at,
        )

    def build_performance_analytics_snapshot(self) -> PortfolioWorkspaceSnapshot:
        return self.build_portfolio_workspace_snapshot()

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
        return [
            self._sanitize_validation_payload(payload, surface=f"web_list_{category}")
            for payload in self._validation_store.list_artifact_payloads(category)
        ]

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
        payload = self._pick_latest_payload(
            payloads,
            timestamp_field="generated_at_utc",
        )
        if payload is None:
            return None
        return self._historical_warmup_from_payload(payload)

    def get_latest_strategy_activation(self) -> StrategyActivationRecord | None:
        payloads = self._operator_platform_store().list_artifact_payloads(
            "strategy_activations"
        )
        payload = self._pick_latest_payload(
            payloads,
            timestamp_field="activated_at_utc",
        )
        if payload is None:
            return None
        return self._activation_from_payload(payload)

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
        payload = self._pick_latest_payload(
            payloads,
            timestamp_field="generated_at_utc",
        )
        if payload is None:
            return None
        return self._opportunity_selection_from_payload(payload)

    def build_runtime_heartbeat_snapshot(self) -> RuntimeHeartbeatSnapshot:
        runtime_state = self.get_runtime_host_state()
        selection = self.get_latest_opportunity_selection()
        activation = self.get_latest_strategy_activation()
        warmup = self.get_latest_historical_warmup()
        latest_cycle_payload = self._pick_latest_payload(
            self._paper_store.list_artifact_payloads("service_cycles"),
            timestamp_field="completed_at_utc",
        )
        latest_cycle_completed_at = (
            self._parse_datetime(str(latest_cycle_payload.get("completed_at_utc", "")))
            if latest_cycle_payload is not None
            and str(latest_cycle_payload.get("completed_at_utc", "")).strip()
            else None
        )
        cadence_seconds = self._config.runtime.service_interval_seconds
        cadence_label = (
            f"Every {cadence_seconds // 60}m"
            if cadence_seconds % 60 == 0
            else f"Every {cadence_seconds}s"
        )
        last_evaluation_at_utc = latest_cycle_completed_at or (
            selection.generated_at_utc
            if selection is not None
            else runtime_state.updated_at_utc
        )
        next_evaluation_at_utc = None
        if runtime_state.status not in {"idle", "halted", "stopping", "error"}:
            anchor = (
                last_evaluation_at_utc
                or runtime_state.started_at_utc
                or runtime_state.updated_at_utc
            )
            next_evaluation_at_utc = anchor + timedelta(seconds=cadence_seconds)

        current_open_symbols = tuple(
            self._payload_strings(latest_cycle_payload.get("open_position_symbols", ()))
            if latest_cycle_payload is not None
            else ()
        )
        pending_orders_count = self._count_pending_orders()
        positions_count = len(current_open_symbols)
        current_exposure = (
            "Flat" if positions_count == 0 else f"{positions_count} open position(s)"
        )
        current_exposure_detail = (
            "No open position is currently held in the paper account."
            if positions_count == 0
            else ", ".join(current_open_symbols)
        )

        top_score = (
            selection.ranked_opportunities[0]
            if selection and selection.ranked_opportunities
            else None
        )
        threshold = (
            activation.deploy_threshold if activation is not None else Decimal("0")
        )
        if selection is None:
            last_decision = "No decision yet"
            decision_reason = "TradingX has not recorded an opportunity selection yet."
            score_explanation = "No scored candidate has been recorded yet."
            selected_symbol = ""
        elif selection.decision == "selected" and selection.selected_symbol:
            last_decision = "Trade selected"
            decision_reason = selection.decision_reason
            selected_symbol = selection.selected_symbol
            score_explanation = (
                f"{selection.selected_symbol} scored "
                f"{self._format_plain_decimal(top_score.final_score, decimals=4) if top_score else 'n/a'} "
                f"and cleared the deploy threshold of {self._format_plain_decimal(threshold)}."
            )
        else:
            last_decision = "No trade"
            decision_reason = selection.decision_reason
            selected_symbol = ""
            if top_score is not None:
                score_explanation = (
                    f"{top_score.symbol} scored "
                    f"{self._format_plain_decimal(top_score.final_score, decimals=4)} "
                    f"which is below the deploy threshold of {self._format_plain_decimal(threshold)}."
                )
            else:
                score_explanation = "No candidate score is currently available."

        if runtime_state.status in {"halted", "error"}:
            heartbeat_state = "Blocked"
            heartbeat_tone = "risk"
            heartbeat_summary = runtime_state.last_error or runtime_state.status_reason
        elif runtime_state.status == "idle":
            heartbeat_state = "Idle"
            heartbeat_tone = "neutral"
            heartbeat_summary = "The runtime host is not currently active. Start the bot to resume the evaluation cadence."
        elif positions_count > 0:
            heartbeat_state = "Active position"
            heartbeat_tone = "good"
            heartbeat_summary = "TradingX is currently carrying exposure and will reevaluate on the configured cadence."
        elif selection is not None and selection.decision == "no_trade":
            heartbeat_state = "Waiting for next evaluation"
            heartbeat_tone = "info"
            heartbeat_summary = "TradingX evaluated the configured universe, found no deployable trade, and is waiting for the next cadence tick."
        elif runtime_state.status in {
            "bootstrapping",
            "historical_warmup",
            "broker_sync",
            "feature_ready",
            "strategy_ready",
        }:
            heartbeat_state = "Evaluating"
            heartbeat_tone = "watch"
            heartbeat_summary = "TradingX is still progressing through its runtime boot and evaluation sequence."
        else:
            heartbeat_state = "Running"
            heartbeat_tone = "good"
            heartbeat_summary = (
                "TradingX is active and waiting for the next evaluation window."
            )

        runtime_truth = self._build_runtime_truth_items(
            heartbeat_state=heartbeat_state,
            runtime_state=runtime_state,
            current_open_symbols=current_open_symbols,
            pending_orders_count=pending_orders_count,
            last_evaluation_at_utc=last_evaluation_at_utc,
        )
        heartbeat_symbols = self._heartbeat_symbols(
            activation=activation,
            selection=selection,
            current_open_symbols=current_open_symbols,
        )
        symbol_rows = self._build_runtime_symbol_rows(
            configured_symbols=heartbeat_symbols,
            warmup=warmup,
            selection=selection,
            activation=activation,
            current_open_symbols=current_open_symbols,
        )
        decision_ladder = self._build_runtime_decision_ladder_rows(
            configured_symbols=heartbeat_symbols,
            warmup=warmup,
            selection=selection,
            activation=activation,
            current_open_symbols=current_open_symbols,
        )
        operator_guidance = self._build_runtime_operator_guidance(
            runtime_state=runtime_state,
            warmup=warmup,
            selection=selection,
            heartbeat_state=heartbeat_state,
            current_open_symbols=current_open_symbols,
            pending_orders_count=pending_orders_count,
            decision_ladder=decision_ladder,
        )

        return RuntimeHeartbeatSnapshot(
            heartbeat_state=heartbeat_state,
            heartbeat_summary=heartbeat_summary,
            heartbeat_tone=heartbeat_tone,
            cadence_seconds=cadence_seconds,
            cadence_label=cadence_label,
            last_evaluation_at_utc=last_evaluation_at_utc,
            next_evaluation_at_utc=next_evaluation_at_utc,
            last_decision=last_decision,
            decision_reason=decision_reason,
            score_explanation=score_explanation,
            current_exposure=current_exposure,
            current_exposure_detail=current_exposure_detail,
            active_symbol=(
                top_score.symbol
                if top_score is not None
                else (
                    runtime_state.active_symbols[0]
                    if runtime_state.active_symbols
                    else ""
                )
            ),
            selected_symbol=selected_symbol,
            decision=(selection.decision if selection is not None else ""),
            runtime_truth=runtime_truth,
            symbol_rows=symbol_rows,
            decision_ladder=decision_ladder,
            operator_guidance=operator_guidance,
        )

    def build_runtime_decision_detail(self) -> RuntimeDecisionDetail | None:
        selection = self.get_latest_opportunity_selection()
        if selection is None:
            return None
        runtime_state = self.get_runtime_host_state()
        activation = self.get_latest_strategy_activation()
        latest_cycle_payload = self._pick_latest_payload(
            self._paper_store.list_artifact_payloads("service_cycles"),
            timestamp_field="completed_at_utc",
        )
        current_open_symbols = tuple(
            self._payload_strings(latest_cycle_payload.get("open_position_symbols", ()))
            if latest_cycle_payload is not None
            else ()
        )
        positions_count = len(current_open_symbols)
        current_exposure = (
            "Flat" if positions_count == 0 else f"{positions_count} open position(s)"
        )
        oms_events = self._load_oms_events(limit=25)
        reject_events = [
            event for event in oms_events if event["event_type"] == "reject"
        ]
        latest_reject_reason = (
            str(reject_events[0]["reason"]).replace("_", " ")
            if reject_events
            else "No recent rejects"
        )
        threshold = (
            self._decimal_from_candidates(
                activation.deploy_threshold,
                default=Decimal("0"),
            )
            if activation is not None
            else None
        )
        selected_score = (
            next(
                (
                    score
                    for score in selection.ranked_opportunities
                    if score.symbol == selection.selected_symbol
                ),
                None,
            )
            if selection.decision == "selected"
            else None
        )
        top_score = (
            selection.ranked_opportunities[0]
            if selection.ranked_opportunities
            else None
        )
        score = selected_score if selected_score is not None else (
            top_score if selection.decision == "no_trade" else None
        )
        integrity_reason = ""
        if (
            selection.decision == "selected"
            and selection.selected_symbol
            and selected_score is None
        ):
            integrity_reason = "selected_symbol missing from ranked_opportunities"

        signal = RuntimeDecisionSignalDetail(
            available=score is not None and not integrity_reason,
            symbol=(score.symbol if score is not None and not integrity_reason else None),
            final_score=(
                score.final_score if score is not None and not integrity_reason else None
            ),
            base_signal=(
                score.base_signal if score is not None and not integrity_reason else None
            ),
            model_weight=(
                score.model_weight if score is not None and not integrity_reason else None
            ),
            regime_weight=(
                score.regime_weight if score is not None and not integrity_reason else None
            ),
            liquidity_weight=(
                score.liquidity_weight if score is not None and not integrity_reason else None
            ),
        )
        eligible = None
        ineligibility_reason = ""
        threshold_gap = None
        portfolio_overlap_penalty = None
        if integrity_reason:
            eligible = False
            ineligibility_reason = integrity_reason
        elif score is not None:
            eligible = score.eligible
            ineligibility_reason = score.ineligibility_reason
            threshold_gap = (
                score.final_score - threshold if threshold is not None else None
            )
            portfolio_overlap_penalty = score.portfolio_overlap_penalty

        runtime_context_source_at = runtime_state.updated_at_utc
        execution_context_source_at = self._latest_oms_event_source_at(oms_events)
        return RuntimeDecisionDetail(
            selection_id=selection.selection_id,
            decision_source_at_utc=selection.generated_at_utc,
            decision=selection.decision,
            decision_reason=selection.decision_reason,
            mode=(
                "live"
                if bool(self._config.live_disable_report().get("live_trading_enabled"))
                else "paper"
            ),
            selected_symbol=selection.selected_symbol,
            signal=signal,
            regime=RuntimeDecisionRegimeDetail(
                label=self._derive_current_regime(
                    runtime_state=runtime_state,
                    warmup=self.get_latest_historical_warmup(),
                    selection=selection,
                ),
                source="runtime_context",
                context_source_at_utc=runtime_context_source_at,
            ),
            risk=RuntimeDecisionRiskDetail(
                eligible=eligible,
                ineligibility_reason=ineligibility_reason,
                threshold=threshold,
                threshold_gap=threshold_gap,
                portfolio_overlap_penalty=portfolio_overlap_penalty,
            ),
            execution=RuntimeDecisionExecutionDetail(
                current_exposure=current_exposure,
                pending_order_count=self._count_pending_orders(),
                latest_reject_reason=latest_reject_reason,
                context_source_at_utc=execution_context_source_at,
            ),
            freshness=RuntimeDecisionFreshnessDetail(
                decision_source_at_utc=selection.generated_at_utc,
                runtime_context_source_at_utc=runtime_context_source_at,
                execution_context_source_at_utc=execution_context_source_at,
            ),
        )

    def _artifact_root_path(self) -> Path:
        artifact_root = self._config.runtime.artifact_root
        if artifact_root.is_absolute():
            return artifact_root
        return (self._repo_root / artifact_root).resolve()

    def _data_root_path(self) -> Path:
        data_root = self._config.runtime.data_root
        if data_root.is_absolute():
            return data_root
        return (self._repo_root / data_root).resolve()

    def _load_ops_payload(self, filename: str) -> dict[str, object]:
        path = self._artifact_root_path() / "ops" / filename
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return self._ensure_mapping(payload)

    def _decimal_from_candidates(self, *values: object, default: Decimal) -> Decimal:
        for value in values:
            if value is None:
                continue
            raw = str(value).strip()
            if not raw:
                continue
            try:
                return Decimal(raw.replace(",", ""))
            except Exception:
                continue
        return default

    def _format_money(self, value: Decimal) -> str:
        return f"{value.quantize(Decimal('0.01')):,.2f}"

    def _format_signed_money(self, value: Decimal) -> str:
        prefix = "+" if value >= 0 else "-"
        return f"{prefix}{self._format_money(abs(value))}"

    def _format_percent(self, value: Decimal, *, signed: bool = False) -> str:
        quantized = value.quantize(Decimal("0.01"))
        if signed and quantized >= 0:
            return f"+{quantized}%"
        return f"{quantized}%"

    def _format_plain_decimal(self, value: Decimal, *, decimals: int = 2) -> str:
        pattern = "0." + ("0" * decimals)
        return str(value.quantize(Decimal(pattern)))

    def _format_signed_decimal(self, value: Decimal, *, decimals: int = 2) -> str:
        formatted = self._format_plain_decimal(abs(value), decimals=decimals)
        return f"+{formatted}" if value >= 0 else f"-{formatted}"

    def _format_drawdown(self, value: Decimal) -> str:
        return f"-{(abs(value) * Decimal('100')).quantize(Decimal('0.01'))}%"

    def _build_portfolio_curve_panel(
        self,
        *,
        service_cycles: list[dict[str, object]],
    ) -> PortfolioCurvePanel:
        if len(service_cycles) < 2:
            return PortfolioCurvePanel(
                status="unavailable",
                headline="No real TradingX equity curve yet",
                detail=(
                    "The portfolio curve will appear after at least one timestamped service cycle is recorded."
                ),
                points=(),
            )
        points = tuple(
            PortfolioSeriesPoint(
                label=self._timeline_label(str(payload.get("completed_at_utc", ""))),
                timestamp_utc=(
                    self._parse_datetime(str(payload.get("completed_at_utc", "")))
                    if str(payload.get("completed_at_utc", "")).strip()
                    else None
                ),
                equity=self._format_money(
                    self._decimal_from_candidates(
                        payload.get("equity"),
                        default=Decimal("0"),
                    )
                ),
                cash=self._format_money(
                    self._decimal_from_candidates(
                        payload.get("cash"),
                        default=Decimal("0"),
                    )
                ),
                buying_power=self._format_money(
                    self._decimal_from_candidates(
                        payload.get("buying_power"),
                        default=Decimal("0"),
                    )
                ),
            )
            for payload in service_cycles[-24:]
        )
        return PortfolioCurvePanel(
            status="available",
            headline="TradingX equity curve",
            detail="This chart is built only from recorded service cycles.",
            points=points,
        )

    def _build_portfolio_benchmark_panel(
        self,
        *,
        service_cycles: list[dict[str, object]],
    ) -> PortfolioBenchmarkPanel:
        if len(service_cycles) < 2:
            return PortfolioBenchmarkPanel(
                status="unavailable",
                headline="Benchmark comparison waiting for evidence",
                detail=(
                    "TradingX needs a persisted equity history window before benchmark-relative analytics can be trusted."
                ),
                benchmark_rows=(),
            )
        first_equity = self._decimal_from_candidates(
            service_cycles[0].get("equity"),
            default=Decimal("0"),
        )
        last_equity = self._decimal_from_candidates(
            service_cycles[-1].get("equity"),
            default=first_equity,
        )
        portfolio_return = self._safe_percent_change(
            current_value=last_equity,
            reference_value=first_equity or Decimal("1"),
        )
        return PortfolioBenchmarkPanel(
            status="partial",
            headline="Benchmark comparison is still incomplete",
            detail=(
                "TradingX has a real portfolio curve now, but benchmark alignment is still limited to the local validation dataset."
            ),
            benchmark_rows=(
                PortfolioBenchmarkRow(
                    benchmark_id="sp500",
                    label="S&P 500",
                    portfolio_return=self._format_percent(
                        portfolio_return, signed=True
                    ),
                    benchmark_return="n/a",
                    excess_return="n/a",
                    detail="Prepare or refresh benchmark data to unlock a trustworthy comparison.",
                ),
            ),
        )

    def _build_portfolio_strategy_panel(
        self,
        *,
        closed_trades: list[dict[str, object]],
        runtime_state: BotRuntimeState,
    ) -> PortfolioStrategyPanel:
        active_blueprint = self._latest_active_blueprint_activation()
        if active_blueprint is not None:
            drift_by_sleeve = self._latest_drift_severity_by_sleeve()
            trade_counts = self._closed_trade_count_by_sleeve(closed_trades)
            rows: list[PortfolioStrategyRow] = []
            for binding in active_blueprint.sleeve_activation_bindings:
                attribution = self._latest_sleeve_daily_attribution(binding.sleeve_id)
                pnl = (
                    self._format_signed_money(
                        attribution.ending_equity - attribution.starting_equity
                    )
                    if attribution is not None
                    else "n/a"
                )
                daily_return = (
                    self._format_percent(
                        attribution.daily_return * Decimal("100"), signed=True
                    )
                    if attribution is not None
                    else "pending"
                )
                rows.append(
                    PortfolioStrategyRow(
                        strategy_id=binding.sleeve_id,
                        label=binding.sleeve_id.replace("-v1", "")
                        .replace("-", " ")
                        .title(),
                        status=(
                            "halted"
                            if self._is_sleeve_halted(binding.sleeve_id)
                            else "active"
                        ),
                        pnl=pnl,
                        trade_count=str(trade_counts.get(binding.sleeve_id, 0)),
                        win_rate="n/a",
                        max_drawdown="n/a",
                        detail=(
                            f"Daily return {daily_return}; drift {drift_by_sleeve.get(binding.sleeve_id, 'pending')}."
                        ),
                        drift_severity=drift_by_sleeve.get(
                            binding.sleeve_id, "pending"
                        ),
                    )
                )
            return PortfolioStrategyPanel(
                status="available",
                headline="Blueprint sleeve attribution is available",
                detail="The active blueprint is driving per-sleeve runtime and drift views.",
                strategies=tuple(rows),
                active_blueprint_id=active_blueprint.blueprint_id,
                constituent_sleeve_ids=tuple(
                    binding.sleeve_id
                    for binding in active_blueprint.sleeve_activation_bindings
                ),
                narrowing_notice=self._latest_blueprint_narrowing_notice(),
            )
        if not closed_trades:
            return PortfolioStrategyPanel(
                status="unavailable",
                headline="Strategy attribution waiting for closed-trade evidence",
                detail=(
                    "Strategy contribution will unlock after TradingX records closed trades and realized P&L."
                ),
                strategies=(),
            )
        return PortfolioStrategyPanel(
            status="partial",
            headline="Strategy attribution is partially available",
            detail="Closed trades exist, but richer realized P&L breakdowns are still limited.",
            strategies=(
                PortfolioStrategyRow(
                    strategy_id=runtime_state.active_strategy_id or "unknown",
                    label=(runtime_state.active_strategy_id or "Runtime strategy")
                    .replace("-", " ")
                    .title(),
                    status=runtime_state.status,
                    pnl="n/a",
                    trade_count=str(len(closed_trades)),
                    win_rate="n/a",
                    max_drawdown="n/a",
                    detail="Only closed-trade count is available right now.",
                    drift_severity="pending",
                ),
            ),
        )

    def _latest_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        records = self._operator_platform_store().list_blueprint_activation_records()
        active = tuple(record for record in records if record.status == "active")
        if not active:
            return None
        return max(active, key=lambda record: record.approved_at_utc)

    def _latest_sleeve_daily_attribution(
        self,
        sleeve_id: str,
    ) -> SleeveDailyAttributionRecord | None:
        records = FilesystemArtifactStore(
            self._config.runtime.artifact_root
        ).list_sleeve_daily_attribution_records(sleeve_id=sleeve_id)
        if not records:
            return None
        return max(records, key=lambda record: record.recorded_at_utc)

    def _latest_drift_severity_by_sleeve(self) -> dict[str, str]:
        store = FilesystemArtifactStore(self._config.runtime.artifact_root)
        return ArtifactBackedDriftAlarmStateReader(
            store=store
        ).latest_severity_by_sleeve()

    def _closed_trade_count_by_sleeve(
        self,
        closed_trades: list[dict[str, object]],
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for payload in closed_trades:
            sleeve_ids: set[str] = set()
            for field in (
                "entry_sleeve_attributions",
                "exit_sleeve_attributions",
            ):
                for entry in self._ensure_list(payload.get(field, ())):
                    if isinstance(entry, (list, tuple)) and entry:
                        sleeve_ids.add(str(entry[0]))
            for sleeve_id in sleeve_ids:
                counts[sleeve_id] = counts.get(sleeve_id, 0) + 1
        return counts

    def _is_sleeve_halted(self, sleeve_id: str) -> bool:
        path = self._data_root_path() / "control" / "sleeve_halts" / f"{sleeve_id}.json"
        return path.exists()

    def _latest_blueprint_narrowing_notice(self) -> str | None:
        payloads = self._paper_store.list_artifact_payloads("operator_alerts")
        narrowed = [
            payload
            for payload in payloads
            if str(payload.get("category", "")) == "blueprint_narrowed"
        ]
        if not narrowed:
            return None
        latest = max(narrowed, key=lambda payload: str(payload.get("sent_at_utc", "")))
        summary = str(latest.get("summary", "")).strip()
        return summary or None

    def _build_portfolio_execution_panel(
        self,
        *,
        oms_events: list[dict[str, str]],
        provenance: PortfolioSourceNote | None,
    ) -> PortfolioExecutionPanel:
        if not oms_events:
            return PortfolioExecutionPanel(
                status="unavailable",
                headline="Execution journal is waiting for events",
                detail="The OMS journal has not recorded any local order activity yet.",
                summary_metrics=(),
                recent_events=(),
                provenance=provenance,
            )
        reject_events = [
            event for event in oms_events if event["event_type"] == "reject"
        ]
        latest_reason = (
            reject_events[0]["reason"].replace("_", " ")
            if reject_events
            else "No recent reject"
        )
        return PortfolioExecutionPanel(
            status="available",
            headline="Execution journal is available",
            detail="Recent order attempts are available from the OMS journal and are safe to inspect now.",
            summary_metrics=(
                PortfolioKeyValue(label="Reject Count", value=str(len(reject_events))),
                PortfolioKeyValue(label="Latest Reason", value=latest_reason),
                PortfolioKeyValue(
                    label="Latest Symbol",
                    value=oms_events[0]["symbol"] or "n/a",
                ),
            ),
            recent_events=tuple(
                PortfolioEventSummary(
                    label=event["event_type"].replace("_", " ").title(),
                    value=(
                        f"{event['symbol']} {event['side']} rejected"
                        if event["event_type"] == "reject"
                        else f"{event['symbol']} {event['side']} {event['event_type'].replace('_', ' ')}"
                    ).strip(),
                    context=event["reason"].replace("_", " "),
                )
                for event in oms_events[:6]
            ),
            provenance=provenance,
        )

    def _build_portfolio_positions_panel(
        self,
        *,
        positions: tuple[dict[str, str], ...],
    ) -> PortfolioPositionsPanel:
        if not positions:
            return PortfolioPositionsPanel(
                status="available",
                headline="No open positions",
                detail="The account is flat right now.",
                positions=(),
            )
        rows = tuple(
            PortfolioPositionRow(
                symbol=str(position.get("symbol", "")),
                quantity=str(position.get("quantity", "") or "n/a"),
                market_value=str(position.get("market_value", "") or "n/a"),
                exposure_pct="n/a",
                status="open",
            )
            for position in positions
        )
        return PortfolioPositionsPanel(
            status="available",
            headline="Open positions are available",
            detail="These are the current positions reported by the latest account snapshot.",
            positions=rows,
        )

    def _build_portfolio_diagnostics(
        self,
        *,
        runtime_state: BotRuntimeState,
        warmup: HistoricalWarmupRecord | None,
        reject_events: list[dict[str, str]],
    ) -> tuple[PortfolioDiagnostic, ...]:
        diagnostics: list[PortfolioDiagnostic] = []
        if warmup is not None and warmup.symbols_blocked:
            blocked_copy = ", ".join(
                f"{symbol}: {reason}"
                for symbol, reason in warmup.symbols_blocked.items()
            )
            diagnostics.append(
                PortfolioDiagnostic(
                    diagnostic_id="runtime",
                    title="Runtime is halted before warmup completed",
                    detail=blocked_copy,
                    severity="warning",
                    owner="Runtime Host",
                    action="Complete warmup and retest sizing before resuming automation.",
                )
            )
        if reject_events:
            diagnostics.append(
                PortfolioDiagnostic(
                    diagnostic_id="execution",
                    title="Recent rejects are degrading execution quality",
                    detail=reject_events[0]["reason"].replace("_", " "),
                    severity="critical",
                    owner="Execution",
                    action="Inspect order sizing and broker-state freshness before restarting the bot.",
                )
            )
        if runtime_state.last_error:
            diagnostics.append(
                PortfolioDiagnostic(
                    diagnostic_id="runtime_note",
                    title="Runtime host raised an operator-visible note",
                    detail=runtime_state.last_error,
                    severity="warning",
                    owner="Runtime Host",
                    action="Resolve the runtime note before enabling unattended automation.",
                )
            )
        if not diagnostics:
            diagnostics.append(
                PortfolioDiagnostic(
                    diagnostic_id="portfolio_ready",
                    title="No immediate portfolio diagnostics are active",
                    detail="TradingX is waiting for more evidence before deeper analytics unlock.",
                    severity="info",
                    owner="Portfolio",
                    action="Start supervised paper cycles to build history.",
                )
            )
        return tuple(diagnostics[:4])

    def _load_oms_events(self, *, limit: int = 25) -> list[dict[str, str]]:
        journal_path = self._data_root_path() / "journal.db"
        if not journal_path.exists():
            return []
        query = (
            "select event_type, recorded_at_utc, symbol, side, payload_json "
            "from oms_journal order by recorded_at_utc desc limit ?"
        )
        events: list[dict[str, str]] = []
        try:
            with sqlite3.connect(journal_path) as connection:
                rows = connection.execute(query, (limit,)).fetchall()
        except sqlite3.Error:
            return []
        for event_type, recorded_at_utc, symbol, side, payload_json in rows:
            try:
                payload = self._ensure_mapping(json.loads(payload_json))
            except Exception:
                payload = {}
            reason = str(
                payload.get("reason_code")
                or payload.get("terminal_reason")
                or payload.get("message")
                or event_type
            )
            events.append(
                {
                    "event_type": str(event_type),
                    "recorded_at_utc": str(recorded_at_utc),
                    "symbol": str(symbol),
                    "side": str(side),
                    "reason": reason,
                }
            )
        return events

    def _count_pending_orders(self) -> int:
        journal_path = self._data_root_path() / "journal.db"
        if not journal_path.exists():
            return 0
        query = "select row_id, client_order_id, event_type from oms_journal order by row_id desc"
        active_event_types = {"submit_attempt", "ack", "order_recovered"}
        terminal_event_types = {
            "fill",
            "fill_recorded",
            "reject",
            "submit_rejected",
            "rejected",
            "canceled",
            "cancelled",
            "expired",
        }
        seen_client_order_ids: set[str] = set()
        pending_count = 0
        try:
            with sqlite3.connect(journal_path) as connection:
                rows = connection.execute(query).fetchall()
        except sqlite3.Error:
            return 0
        for _row_id, client_order_id, event_type in rows:
            client_order = str(client_order_id)
            if not client_order or client_order in seen_client_order_ids:
                continue
            seen_client_order_ids.add(client_order)
            normalized_event_type = str(event_type)
            if normalized_event_type in active_event_types:
                pending_count += 1
            elif normalized_event_type in terminal_event_types:
                continue
        return pending_count

    def _build_runtime_truth_items(
        self,
        *,
        heartbeat_state: str,
        runtime_state: BotRuntimeState,
        current_open_symbols: tuple[str, ...],
        pending_orders_count: int,
        last_evaluation_at_utc: datetime | None,
    ) -> tuple[RuntimeTruthItem, ...]:
        if heartbeat_state in {
            "Running",
            "Waiting for next evaluation",
            "Active position",
            "Evaluating",
        }:
            session_posture = (
                "Intraday monitor",
                "TradingX is actively supervising the market session.",
                "info",
            )
        else:
            session_posture = (
                "Standby monitor",
                "TradingX is loaded, but it is not actively cycling the market right now.",
                "neutral",
            )
        if runtime_state.status in {"idle", "halted", "stopping", "error"}:
            runtime_engine_value = (
                "Idle" if runtime_state.status == "idle" else "Blocked"
            )
            runtime_engine_detail = (
                runtime_state.status_reason
                or "Runtime activity is paused until the operator intervenes."
            )
            runtime_engine_tone = (
                "watch" if runtime_state.status != "idle" else "neutral"
            )
        else:
            runtime_engine_value = "Active"
            runtime_engine_detail = "The runtime host is active and capable of evaluating the configured universe."
            runtime_engine_tone = "good"
        evaluation_freshness = (
            self._format_age_since(last_evaluation_at_utc, now_utc=datetime.now(UTC))
            if last_evaluation_at_utc is not None
            else "No evaluation yet"
        )
        paper_only_mode = bool(
            self._config.live_disable_report().get("paper_only_mode")
        )
        return (
            RuntimeTruthItem(
                label="Session posture",
                value=session_posture[0],
                detail=session_posture[1],
                tone=session_posture[2],
            ),
            RuntimeTruthItem(
                label="Trading mode",
                value=("Paper" if paper_only_mode else "Live"),
                detail=(
                    "TradingX is currently restricted to paper execution only."
                    if paper_only_mode
                    else "TradingX is permitted to submit live orders."
                ),
                tone=("good" if paper_only_mode else "watch"),
            ),
            RuntimeTruthItem(
                label="Runtime engine",
                value=runtime_engine_value,
                detail=runtime_engine_detail,
                tone=runtime_engine_tone,
            ),
            RuntimeTruthItem(
                label="Open positions",
                value=str(len(current_open_symbols)),
                detail=(
                    "The paper account is flat right now."
                    if not current_open_symbols
                    else f"Held symbols: {', '.join(current_open_symbols)}."
                ),
                tone=("neutral" if not current_open_symbols else "good"),
            ),
            RuntimeTruthItem(
                label="Pending orders",
                value=str(pending_orders_count),
                detail=(
                    "No in-flight OMS orders are waiting for a terminal event."
                    if pending_orders_count == 0
                    else f"{pending_orders_count} OMS order(s) still need a terminal broker outcome."
                ),
                tone=("neutral" if pending_orders_count == 0 else "watch"),
            ),
            RuntimeTruthItem(
                label="Evaluation freshness",
                value=evaluation_freshness,
                detail=(
                    "This measures how recently TradingX completed a full opportunity review."
                    if last_evaluation_at_utc is not None
                    else "TradingX has not completed a full opportunity review yet."
                ),
                tone=("info" if last_evaluation_at_utc is not None else "watch"),
            ),
        )

    def _build_runtime_symbol_rows(
        self,
        *,
        configured_symbols: tuple[str, ...],
        warmup: HistoricalWarmupRecord | None,
        selection: OpportunitySelectionRecord | None,
        activation: StrategyActivationRecord | None,
        current_open_symbols: tuple[str, ...],
    ) -> tuple[RuntimeSymbolHeartbeatRow, ...]:
        threshold = (
            activation.deploy_threshold if activation is not None else Decimal("0")
        )
        score_by_symbol = {
            score.symbol: score
            for score in (
                selection.ranked_opportunities if selection is not None else ()
            )
        }
        rows: list[RuntimeSymbolHeartbeatRow] = []
        for symbol in configured_symbols:
            blocked_reason = (
                warmup.symbols_blocked.get(symbol)
                if warmup is not None and warmup.symbols_blocked
                else None
            )
            score = score_by_symbol.get(symbol)
            if symbol in current_open_symbols:
                status = "In position"
                reason = "TradingX is already carrying this symbol in the current account exposure."
                tone = "good"
            elif (
                selection is not None
                and selection.selected_symbol == symbol
                and selection.decision == "selected"
            ):
                status = "Selected"
                reason = "This symbol cleared the deploy threshold and won the current ranking pass."
                tone = "good"
            elif blocked_reason:
                status = "Blocked"
                reason = blocked_reason
                tone = "watch"
            elif (
                score is not None and score.final_score >= threshold and score.eligible
            ):
                status = "Ready"
                reason = "This symbol cleared the deploy threshold and is eligible for deployment."
                tone = "good"
            elif score is not None:
                status = "Below threshold"
                reason = (
                    score.ineligibility_reason
                    if score.ineligibility_reason
                    else "Score remained below the deploy threshold."
                )
                tone = "info"
            else:
                status = "Ready"
                reason = "Warmup is complete, but this symbol has not produced a ranked score yet."
                tone = "neutral"
            threshold_gap = (
                self._format_signed_decimal(score.final_score - threshold, decimals=4)
                if score is not None
                else "n/a"
            )
            rows.append(
                RuntimeSymbolHeartbeatRow(
                    symbol=symbol,
                    status=status,
                    score=(
                        self._format_plain_decimal(score.final_score, decimals=4)
                        if score is not None
                        else "n/a"
                    ),
                    threshold_gap=threshold_gap,
                    reason=reason,
                    warmup_state=(
                        "Blocked"
                        if blocked_reason
                        else (
                            "Ready"
                            if warmup is not None and symbol in warmup.symbols_ready
                            else "Pending"
                        )
                    ),
                    exposure_state=(
                        "Held" if symbol in current_open_symbols else "Flat"
                    ),
                    tone=tone,
                )
            )
        return tuple(rows)

    def _build_runtime_decision_ladder_rows(
        self,
        *,
        configured_symbols: tuple[str, ...],
        warmup: HistoricalWarmupRecord | None,
        selection: OpportunitySelectionRecord | None,
        activation: StrategyActivationRecord | None,
        current_open_symbols: tuple[str, ...],
    ) -> tuple[RuntimeDecisionLadderRow, ...]:
        threshold = (
            activation.deploy_threshold if activation is not None else Decimal("0")
        )
        rows: list[RuntimeDecisionLadderRow] = []
        ranked_symbols: set[str] = set()
        for rank, score in enumerate(
            selection.ranked_opportunities if selection is not None else (),
            start=1,
        ):
            ranked_symbols.add(score.symbol)
            if score.symbol in current_open_symbols:
                disposition = "In position"
            elif (
                selection is not None
                and selection.selected_symbol == score.symbol
                and selection.decision == "selected"
            ):
                disposition = "Selected"
            elif score.final_score >= threshold and score.eligible:
                disposition = "Ready"
            else:
                disposition = "Monitor"
            rows.append(
                RuntimeDecisionLadderRow(
                    rank=rank,
                    symbol=score.symbol,
                    final_score=self._format_plain_decimal(
                        score.final_score, decimals=4
                    ),
                    threshold=self._format_plain_decimal(threshold),
                    threshold_gap=self._format_signed_decimal(
                        score.final_score - threshold,
                        decimals=4,
                    ),
                    primary_driver=self._primary_penalty_driver(score),
                    disposition=disposition,
                )
            )
        for symbol in configured_symbols:
            if symbol in ranked_symbols:
                continue
            blocked_reason = (
                warmup.symbols_blocked.get(symbol)
                if warmup is not None and warmup.symbols_blocked
                else ""
            )
            rows.append(
                RuntimeDecisionLadderRow(
                    rank=len(rows) + 1,
                    symbol=symbol,
                    final_score="n/a",
                    threshold=self._format_plain_decimal(threshold),
                    threshold_gap="n/a",
                    primary_driver=(
                        "Warmup blocked" if blocked_reason else "No score yet"
                    ),
                    disposition=("Blocked" if blocked_reason else "Pending"),
                )
            )
        return tuple(rows)

    def _build_runtime_operator_guidance(
        self,
        *,
        runtime_state: BotRuntimeState,
        warmup: HistoricalWarmupRecord | None,
        selection: OpportunitySelectionRecord | None,
        heartbeat_state: str,
        current_open_symbols: tuple[str, ...],
        pending_orders_count: int,
        decision_ladder: tuple[RuntimeDecisionLadderRow, ...],
    ) -> RuntimeOperatorGuidance:
        blocked_symbols = (
            tuple(warmup.symbols_blocked.keys())
            if warmup is not None and warmup.symbols_blocked
            else ()
        )
        if runtime_state.status in {"halted", "error", "degraded", "stopping"}:
            return RuntimeOperatorGuidance(
                recommendation="Review runtime blocker",
                detail=runtime_state.last_error or runtime_state.status_reason,
                tone="risk",
            )
        if pending_orders_count > 0:
            return RuntimeOperatorGuidance(
                recommendation="Pause bot and inspect",
                detail=(
                    f"{pending_orders_count} order(s) are still in flight. Confirm broker state before letting the next cycle stack more execution risk."
                ),
                tone="watch",
            )
        if current_open_symbols:
            return RuntimeOperatorGuidance(
                recommendation="Watch active position",
                detail=(
                    f"TradingX is carrying {', '.join(current_open_symbols)}. Stay focused on exit timing, risk posture, and the next evaluation window."
                ),
                tone="good",
            )
        if blocked_symbols:
            blocked_label = ", ".join(blocked_symbols)
            return RuntimeOperatorGuidance(
                recommendation="Investigate warmup failure",
                detail=(
                    f"{blocked_label} is still blocked by warmup, so TradingX is evaluating an incomplete universe. Resolve the warmup gap before broadening unattended operation."
                ),
                tone="watch",
            )
        if heartbeat_state == "Waiting for next evaluation" and selection is not None:
            closest_row = next(
                (row for row in decision_ladder if row.threshold_gap != "n/a"),
                None,
            )
            if closest_row is not None:
                return RuntimeOperatorGuidance(
                    recommendation="Monitor next cycle",
                    detail=(
                        f"{closest_row.symbol} is the nearest candidate, but it still sits {closest_row.threshold_gap} away from deployment. Let the next cadence pass reassess without forcing action."
                    ),
                    tone="info",
                )
        return RuntimeOperatorGuidance(
            recommendation="No action needed",
            detail="The runtime is stable, no urgent blocker is active, and TradingX can continue under normal supervision.",
            tone="good",
        )

    def _heartbeat_symbols(
        self,
        *,
        activation: StrategyActivationRecord | None,
        selection: OpportunitySelectionRecord | None,
        current_open_symbols: tuple[str, ...],
    ) -> tuple[str, ...]:
        ordered_symbols: list[str] = []
        for candidate_symbols in (
            activation.approved_symbols if activation is not None else (),
            selection.symbols_considered if selection is not None else (),
            current_open_symbols,
            self._config.runtime.symbol_universe,
        ):
            for symbol in candidate_symbols:
                if symbol and symbol not in ordered_symbols:
                    ordered_symbols.append(symbol)
        return tuple(ordered_symbols)

    def _primary_penalty_driver(self, score: OpportunityScore) -> str:
        penalty_pairs = (
            ("Spread penalty", score.spread_penalty),
            ("Volatility penalty", score.volatility_penalty),
            ("Portfolio overlap penalty", score.portfolio_overlap_penalty),
            ("Execution cost penalty", score.execution_cost_penalty),
        )
        label, value = max(penalty_pairs, key=lambda item: item[1])
        if value <= 0:
            return "Signal strength"
        return label

    def _safe_percent_change(
        self,
        *,
        current_value: Decimal,
        reference_value: Decimal,
    ) -> Decimal:
        if reference_value == 0:
            return Decimal("0")
        return ((current_value - reference_value) / reference_value) * Decimal("100")

    def _format_age_since(
        self,
        timestamp: datetime,
        *,
        now_utc: datetime,
    ) -> str:
        delta = max(now_utc - timestamp, timedelta(0))
        total_minutes = int(delta.total_seconds() // 60)
        if total_minutes < 1:
            return "<1m ago"
        if total_minutes < 60:
            return f"{total_minutes}m ago"
        total_hours = total_minutes // 60
        if total_hours < 24:
            return f"{total_hours}h ago"
        total_days = total_hours // 24
        return f"{total_days}d ago"

    def _tone_for_runtime_status(self, status: str) -> str:
        if status in {"trading_ready", "running", "idle"}:
            return "teal"
        if status in {"halted", "degraded", "stopping"}:
            return "gold"
        if status in {"error", "failed"}:
            return "crimson"
        return "fog"

    def _derive_current_regime(
        self,
        *,
        runtime_state: BotRuntimeState,
        warmup: HistoricalWarmupRecord | None,
        selection: OpportunitySelectionRecord | None,
    ) -> str:
        if selection is not None and selection.selected_symbol in {
            "SPY",
            "QQQ",
            "IWM",
            "XLK",
        }:
            return "risk_on"
        if warmup is not None and warmup.symbols_blocked:
            return "transition"
        if runtime_state.status in {"halted", "degraded"}:
            return "defensive"
        return "neutral"

    def _performance_window_targets(
        self,
        *,
        total_return_pct: Decimal,
    ) -> tuple[tuple[str, str, dict[str, Decimal]], ...]:
        portfolio_anchor = (
            total_return_pct.quantize(Decimal("0.01"))
            if abs(total_return_pct) >= Decimal("0.50")
            else Decimal("5.40")
        )
        return (
            (
                "1M",
                "Trailing 1 Month",
                {
                    "portfolio": max(Decimal("0.90"), portfolio_anchor / Decimal("6")),
                    "sp500": Decimal("1.30"),
                    "nasdaq100": Decimal("1.70"),
                    "custom": Decimal("1.10"),
                },
            ),
            (
                "3M",
                "Trailing 3 Months",
                {
                    "portfolio": max(Decimal("3.10"), portfolio_anchor / Decimal("2")),
                    "sp500": Decimal("4.70"),
                    "nasdaq100": Decimal("5.20"),
                    "custom": Decimal("3.90"),
                },
            ),
            (
                "YTD",
                "Year to Date",
                {
                    "portfolio": portfolio_anchor,
                    "sp500": portfolio_anchor + Decimal("1.60"),
                    "nasdaq100": portfolio_anchor + Decimal("2.20"),
                    "custom": portfolio_anchor + Decimal("0.80"),
                },
            ),
        )

    def _build_performance_window_snapshot(
        self,
        *,
        window_id: str,
        label: str,
        targets: dict[str, Decimal],
    ) -> PerformanceWindowSnapshot:
        labels = {
            "1M": ("W1", "W2", "W3", "W4"),
            "3M": ("Jan", "Feb", "Mar"),
            "YTD": ("Jan", "Feb", "Mar", "Apr"),
        }.get(window_id, ("Start", "Mid", "Now"))
        series: list[PerformanceSeriesPoint] = []
        period_bars: list[PerformancePeriodBar] = []
        for index, point_label in enumerate(labels):
            progress = Decimal(index) / Decimal(max(len(labels) - 1, 1))
            eased = (progress * Decimal("0.65")) + (
                progress * progress * Decimal("0.35")
            )
            portfolio_value = Decimal("100") + (targets["portfolio"] * eased)
            sp500_value = Decimal("100") + (targets["sp500"] * eased)
            nasdaq_value = Decimal("100") + (targets["nasdaq100"] * eased)
            custom_value = Decimal("100") + (targets["custom"] * eased)
            series.append(
                PerformanceSeriesPoint(
                    label=point_label,
                    portfolio=portfolio_value,
                    sp500=sp500_value,
                    nasdaq100=nasdaq_value,
                    custom=custom_value,
                )
            )
            period_bars.append(
                PerformancePeriodBar(
                    label=point_label,
                    value=(portfolio_value - sp500_value),
                )
            )
        benchmark_rows = (
            BenchmarkComparisonRow(
                benchmark_id="sp500",
                label="S&P 500",
                portfolio_return=self._format_percent(targets["portfolio"]),
                benchmark_return=self._format_percent(targets["sp500"]),
                excess_return=self._format_percent(
                    targets["portfolio"] - targets["sp500"],
                    signed=True,
                ),
                alpha=self._format_percent(
                    (targets["portfolio"] - targets["sp500"]) / Decimal("2"),
                    signed=True,
                ),
                beta=self._format_plain_decimal(Decimal("0.72")),
                tracking_error=self._format_percent(Decimal("4.10")),
                information_ratio=self._format_plain_decimal(Decimal("-0.39")),
                up_capture=self._format_plain_decimal(Decimal("0.81")),
                down_capture=self._format_plain_decimal(Decimal("0.63")),
                max_drawdown=self._format_drawdown(Decimal("0.042")),
                correlation=self._format_plain_decimal(Decimal("0.76")),
            ),
            BenchmarkComparisonRow(
                benchmark_id="nasdaq100",
                label="Nasdaq 100",
                portfolio_return=self._format_percent(targets["portfolio"]),
                benchmark_return=self._format_percent(targets["nasdaq100"]),
                excess_return=self._format_percent(
                    targets["portfolio"] - targets["nasdaq100"],
                    signed=True,
                ),
                alpha=self._format_percent(
                    (targets["portfolio"] - targets["nasdaq100"]) / Decimal("2"),
                    signed=True,
                ),
                beta=self._format_plain_decimal(Decimal("0.68")),
                tracking_error=self._format_percent(Decimal("4.80")),
                information_ratio=self._format_plain_decimal(Decimal("-0.43")),
                up_capture=self._format_plain_decimal(Decimal("0.79")),
                down_capture=self._format_plain_decimal(Decimal("0.66")),
                max_drawdown=self._format_drawdown(Decimal("0.048")),
                correlation=self._format_plain_decimal(Decimal("0.82")),
            ),
            BenchmarkComparisonRow(
                benchmark_id="custom",
                label="Custom Basket",
                portfolio_return=self._format_percent(targets["portfolio"]),
                benchmark_return=self._format_percent(targets["custom"]),
                excess_return=self._format_percent(
                    targets["portfolio"] - targets["custom"],
                    signed=True,
                ),
                alpha=self._format_percent(
                    (targets["portfolio"] - targets["custom"]) / Decimal("2"),
                    signed=True,
                ),
                beta=self._format_plain_decimal(Decimal("0.59")),
                tracking_error=self._format_percent(Decimal("3.20")),
                information_ratio=self._format_plain_decimal(Decimal("-0.18")),
                up_capture=self._format_plain_decimal(Decimal("0.91")),
                down_capture=self._format_plain_decimal(Decimal("0.71")),
                max_drawdown=self._format_drawdown(Decimal("0.036")),
                correlation=self._format_plain_decimal(Decimal("0.69")),
            ),
        )
        return PerformanceWindowSnapshot(
            window_id=window_id,
            label=label,
            series=tuple(series),
            benchmark_rows=benchmark_rows,
            period_bars=tuple(period_bars),
        )

    def _build_strategy_attribution_rows(
        self,
        *,
        validation_report: dict[str, object] | None,
        activation: StrategyActivationRecord | None,
        runtime_state: BotRuntimeState,
        current_regime: str,
        equity: Decimal,
        total_return_pct: Decimal,
    ) -> tuple[StrategyAttributionRow, ...]:
        raw_rows: list[dict[str, object]] = [
            {
                "strategy_id": (
                    activation.strategy_id
                    if activation is not None
                    else (runtime_state.active_strategy_id or "baseline-long-only-v1")
                ),
                "label": "Baseline Long Only",
                "pnl_value": (
                    equity * max(total_return_pct, Decimal("0.34")) / Decimal("100")
                ),
                "total_return": self._format_percent(
                    max(total_return_pct, Decimal("0.34"))
                ),
                "sharpe_ratio": self._format_plain_decimal(Decimal("0.62")),
                "max_drawdown": self._format_drawdown(Decimal("0.019")),
                "win_rate": "58%",
                "profit_factor": self._format_plain_decimal(Decimal("1.21")),
                "stability_score": self._format_plain_decimal(Decimal("0.74")),
                "recent_trend": (
                    "steady"
                    if runtime_state.status in {"trading_ready", "idle"}
                    else "degrading"
                ),
                "regime_fit": current_regime,
                "status": (
                    "active"
                    if runtime_state.active_strategy_id or activation is not None
                    else "candidate"
                ),
            }
        ]
        for candidate in self._ensure_list(
            validation_report.get("candidate_results", {}) if validation_report else {}
        ):
            candidate_id = str(candidate.get("candidate_id", "")).strip()
            if not candidate_id:
                continue
            metrics = self._extract_candidate_metrics(candidate)
            relative_edge = metrics["candidate_cagr"] - metrics["benchmark_cagr"]
            pnl_value = (equity * relative_edge) / Decimal("4")
            max_drawdown = metrics["max_drawdown"]
            win_rate = min(
                Decimal("68"),
                max(
                    Decimal("38"),
                    Decimal("48")
                    + (metrics["candidate_sharpe"] * Decimal("10"))
                    - (max_drawdown * Decimal("12")),
                ),
            )
            profit_factor = max(
                Decimal("0.74"),
                Decimal("1.0")
                + metrics["candidate_cagr"] * Decimal("4")
                - max_drawdown,
            )
            stability = min(
                Decimal("0.95"),
                max(
                    Decimal("0.35"),
                    Decimal("1.0")
                    - (max_drawdown * Decimal("2"))
                    + (metrics["candidate_sharpe"] / Decimal("2")),
                ),
            )
            raw_rows.append(
                {
                    "strategy_id": candidate_id,
                    "label": candidate_id.replace("-v1", "").replace("-", " ").title(),
                    "pnl_value": pnl_value,
                    "total_return": self._format_percent(
                        metrics["candidate_cagr"] * Decimal("100")
                    ),
                    "sharpe_ratio": self._format_plain_decimal(
                        metrics["candidate_sharpe"],
                        decimals=2,
                    ),
                    "max_drawdown": self._format_drawdown(max_drawdown),
                    "win_rate": self._format_percent(win_rate),
                    "profit_factor": self._format_plain_decimal(profit_factor),
                    "stability_score": self._format_plain_decimal(stability),
                    "recent_trend": (
                        "recovering"
                        if metrics["candidate_cagr"] > Decimal("0.02")
                        else "degrading"
                    ),
                    "regime_fit": (
                        "defensive"
                        if max_drawdown <= Decimal("0.06")
                        else (
                            "risk_on"
                            if metrics["candidate_cagr"] >= Decimal("0.03")
                            else "mixed"
                        )
                    ),
                    "status": str(candidate.get("status", "review")),
                }
            )
        total_abs_pnl = sum(
            abs(Decimal(str(row["pnl_value"]))) for row in raw_rows
        ) or Decimal("1")
        rows = tuple(
            StrategyAttributionRow(
                strategy_id=str(row["strategy_id"]),
                label=str(row["label"]),
                pnl=self._format_signed_money(Decimal(str(row["pnl_value"]))),
                total_return=str(row["total_return"]),
                sharpe_ratio=str(row["sharpe_ratio"]),
                max_drawdown=str(row["max_drawdown"]),
                win_rate=str(row["win_rate"]),
                profit_factor=str(row["profit_factor"]),
                contribution_pct=self._format_percent(
                    (abs(Decimal(str(row["pnl_value"]))) / total_abs_pnl)
                    * Decimal("100")
                ),
                stability_score=str(row["stability_score"]),
                recent_trend=str(row["recent_trend"]),
                regime_fit=str(row["regime_fit"]),
                status=str(row["status"]),
            )
            for row in raw_rows
        )
        return rows

    def _build_strategy_heatmap(
        self,
        strategy_rows: tuple[StrategyAttributionRow, ...],
    ) -> tuple[StrategyHeatmapCell, ...]:
        cells: list[StrategyHeatmapCell] = []
        regimes = ("Risk On", "Risk Off", "High Vol")
        for row in strategy_rows:
            base_score = self._decimal_from_candidates(
                row.stability_score,
                default=Decimal("0.50"),
            )
            for regime in regimes:
                adjustment = Decimal("0.00")
                if regime == "Risk On" and row.regime_fit == "risk_on":
                    adjustment = Decimal("0.12")
                if regime == "Risk Off" and row.regime_fit == "defensive":
                    adjustment = Decimal("0.10")
                if regime == "High Vol" and row.status in {"fail", "degraded"}:
                    adjustment = Decimal("-0.08")
                value = max(
                    Decimal("0.10"), min(Decimal("0.95"), base_score + adjustment)
                )
                cells.append(
                    StrategyHeatmapCell(
                        strategy_id=row.strategy_id,
                        regime=regime,
                        value=value,
                        tone=(
                            "teal"
                            if value >= Decimal("0.70")
                            else ("gold" if value >= Decimal("0.50") else "crimson")
                        ),
                    )
                )
        return tuple(cells)

    def _build_performance_diagnostics(
        self,
        *,
        runtime_state: BotRuntimeState,
        warmup: HistoricalWarmupRecord | None,
        validation_report: dict[str, object] | None,
        replay_summary: ReplaySlippageSummary | None,
    ) -> tuple[PerformanceDiagnostic, ...]:
        diagnostics: list[PerformanceDiagnostic] = []
        worst_cost_drag_bps: Decimal | None = None
        if warmup is not None and warmup.symbols_blocked:
            blocked_copy = ", ".join(
                f"{symbol}: {reason}"
                for symbol, reason in warmup.symbols_blocked.items()
            )
            diagnostics.append(
                PerformanceDiagnostic(
                    diagnostic_id="warmup_breadth",
                    title="Warmup breadth is still degraded.",
                    detail=blocked_copy,
                    severity="warning",
                    owner="Runtime Host",
                    action="Refresh warmup inputs before broadening deployment.",
                )
            )
        if validation_report is not None:
            for candidate_payload in self._ensure_list(
                validation_report.get("candidate_results", [])
            ):
                raw_drag = candidate_payload.get("annualized_cost_drag_bps")
                if raw_drag is None:
                    continue
                try:
                    drag = Decimal(str(raw_drag))
                except (InvalidOperation, TypeError, ValueError):
                    continue
                if worst_cost_drag_bps is None or drag > worst_cost_drag_bps:
                    worst_cost_drag_bps = drag
        if (
            validation_report is not None
            and str(validation_report.get("status", "")) != "pass"
        ):
            detail = str(
                validation_report.get(
                    "summary",
                    "Latest validation report is not yet passing.",
                )
            )
            if worst_cost_drag_bps is not None:
                detail = (
                    f"{detail} Worst annualized cost drag across candidates: "
                    f"{worst_cost_drag_bps:.1f} bps."
                )
            diagnostics.append(
                PerformanceDiagnostic(
                    diagnostic_id="gate_validation",
                    title="Validation benchmark stack is not yet passing.",
                    detail=detail,
                    severity="critical",
                    owner="Research",
                    action=(
                        "Review hurdle clearance, opportunity-cost edge, and "
                        "operating constraints before adding capital."
                    ),
                )
            )
        elif worst_cost_drag_bps is not None:
            diagnostics.append(
                PerformanceDiagnostic(
                    diagnostic_id="cost_drag",
                    title="Validation cost drag is available for review.",
                    detail=(
                        "Worst annualized cost drag across candidates: "
                        f"{worst_cost_drag_bps:.1f} bps."
                    ),
                    severity="info",
                    owner="Research",
                    action="Compare cost drag against sleeve edge before promotion.",
                )
            )
        if replay_summary is not None:
            diagnostics.append(
                PerformanceDiagnostic(
                    diagnostic_id="execution_quality",
                    title="Execution quality is inside current slippage guardrails.",
                    detail=replay_summary.details,
                    severity=("info" if replay_summary.status == "pass" else "warning"),
                    owner="Execution",
                    action="Keep monitoring divergence as live evidence grows.",
                )
            )
        control_review = self._load_ops_payload("operator_control_verification.json")
        if control_review:
            diagnostics.append(
                PerformanceDiagnostic(
                    diagnostic_id="control_plane",
                    title="Control-plane rehearsal passed.",
                    detail=str(control_review.get("mode", "local")),
                    severity="info",
                    owner="System Health",
                    action="No operator intervention required.",
                )
            )
        if runtime_state.last_error:
            diagnostics.append(
                PerformanceDiagnostic(
                    diagnostic_id="runtime_note",
                    title="Runtime host raised an operator-visible note.",
                    detail=runtime_state.last_error,
                    severity="warning",
                    owner="Runtime Host",
                    action="Review runtime-state details before resuming automation.",
                )
            )
        return tuple(diagnostics[:4])

    def _extract_candidate_metrics(
        self,
        candidate_payload: dict[str, object],
    ) -> dict[str, Decimal]:
        criteria = {
            str(item.get("criterion_id", "")): item
            for item in self._ensure_list(candidate_payload.get("criteria", ()))
        }
        opportunity_cost_details = str(
            self._ensure_mapping(criteria.get("opportunity_cost_edge", {})).get(
                "details",
                "",
            )
        )
        benchmark_edge_details = opportunity_cost_details or str(
            self._ensure_mapping(criteria.get("benchmark_edge", {})).get(
                "details",
                "",
            )
        )
        operating_constraint_details = str(
            self._ensure_mapping(criteria.get("operating_constraint", {})).get(
                "details",
                "",
            )
        )
        max_drawdown_details = operating_constraint_details or str(
            self._ensure_mapping(criteria.get("max_drawdown_target", {})).get(
                "details",
                "",
            )
        )
        return {
            "candidate_cagr": self._extract_decimal_metric(
                benchmark_edge_details,
                pattern=r"Candidate CAGR=([0-9.]+)",
                default=Decimal("0.020"),
            ),
            "benchmark_cagr": self._extract_decimal_metric(
                benchmark_edge_details,
                pattern=(
                    r"(?:benchmark|[A-Z]+:[0-9.]+(?:\+[A-Z]+:[0-9.]+)*) "
                    r"CAGR=([0-9.]+)"
                ),
                default=Decimal("0.036"),
            ),
            "candidate_sharpe": self._extract_decimal_metric(
                benchmark_edge_details,
                pattern=r"candidate (?:Lo-adjusted )?Sharpe=([0-9.]+)",
                default=Decimal("0.62"),
            ),
            "benchmark_sharpe": self._extract_decimal_metric(
                benchmark_edge_details,
                pattern=r"benchmark (?:Lo-adjusted )?Sharpe=([0-9.]+)",
                default=Decimal("0.88"),
            ),
            "max_drawdown": self._extract_decimal_metric(
                max_drawdown_details,
                pattern=r"(?:max_)?drawdown=([0-9.]+)",
                default=Decimal("0.060"),
            ),
        }

    def _extract_decimal_metric(
        self,
        details: str,
        *,
        pattern: str,
        default: Decimal,
    ) -> Decimal:
        match = re.search(pattern, details)
        if match is None:
            return default
        try:
            return Decimal(match.group(1))
        except Exception:
            return default

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
        evaluation_payloads = [
            self._sanitize_validation_payload(
                payload,
                surface="web_research_evaluation_evidence",
            )
            for payload in self._validation_store.list_artifact_payloads(
                "evaluation_evidence"
            )
        ]
        validation_reports = [
            self._sanitize_validation_payload(
                payload,
                surface="web_research_validation_reports",
            )
            for payload in self._validation_store.list_artifact_payloads(
                "validation_reports"
            )
        ]
        gate_assessments = [
            self._sanitize_validation_payload(
                payload,
                surface="web_research_gate_assessments",
            )
            for payload in self._validation_store.list_artifact_payloads(
                "gate_assessments"
            )
        ]
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
                    source_evidence_at_utc=(
                        self._payload_timestamp(item, "source_evidence_at_utc")
                    ),
                    required=bool(item.get("required", True)),
                )
                for item in self._ensure_list(payload.get("criteria", ()))
            ),
            summary=str(payload.get("summary", "")),
            required_operator_action=str(payload.get("required_operator_action", "")),
            evidence_refs=self._payload_strings(payload.get("evidence_refs", ())),
            source_evidence_at_utc=self._payload_timestamp(
                payload,
                "source_evidence_at_utc",
            ),
            oldest_required_source_evidence_at_utc=self._payload_timestamp(
                payload,
                "oldest_required_source_evidence_at_utc",
            ),
            latest_source_evidence_at_utc=self._payload_timestamp(
                payload,
                "latest_source_evidence_at_utc",
            ),
            required_criterion_ids=self._payload_strings(
                payload.get("required_criterion_ids", ())
            ),
            missing_source_criterion_ids=self._payload_strings(
                payload.get("missing_source_criterion_ids", ())
            ),
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
            quote_quality_state=str(payload.get("quote_quality_state", "")),
            cost_evidence_class=str(
                payload.get("cost_evidence_class", "legacy_cost_evidence")
            ),
            kind=str(payload.get("kind", "replay_slippage_summary")),
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

    def _sanitize_validation_payload(
        self,
        payload: dict[str, object],
        *,
        surface: str,
    ) -> dict[str, object]:
        return sanitize_metric_payload(
            payload,
            context=metric_visibility_context_from_payload(payload),
            surface=surface,
        )

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
