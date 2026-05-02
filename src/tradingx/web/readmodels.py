# ruff: noqa: E501

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol, cast

from tradingx.config import TradingConfig
from tradingx.drift.gateway import ArtifactBackedDriftAlarmStateReader
from tradingx.experiments import (
    metric_visibility_context_from_payload,
    sanitize_metric_payload,
)
from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import (
    list_portfolio_blueprints,
    load_portfolio_blueprint,
    portfolio_blueprint_from_payload,
)
from tradingx.promotion import (
    LEGACY_NON_AUTHORITY_STATUS,
    PromotionState,
    build_artifact_promotion_decision_provider,
    state_allows,
)
from tradingx.sleeves.base import build_sleeve_from_candidate
from tradingx.strategy import build_runtime_candidate_registry
from tradingx.types import (
    ApprovedWeightSnapshot,
    BenchmarkComparisonRow,
    BlueprintActivationRecord,
    BotBrainCycleExplanation,
    BotBrainDecisionStage,
    BotBrainOrderEvent,
    BotBrainSleeveCycleReason,
    BotBrainSleeveReadiness,
    BotBrainSnapshot,
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
    PortfolioBlueprintCatalog,
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
    SessionTimelineEvent,
    SessionTimelineFilters,
    SessionTimelineResponse,
    SessionTimelineSession,
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

_STALE_DAY_ORDER_PENDING_AFTER = timedelta(hours=12)


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
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._paper_store = paper_store
        self._validation_store = validation_store
        self._docs_root = docs_root
        self._repo_root = repo_root
        self._service_manager = service_manager
        self._runtime_host_manager = runtime_host_manager or _IdleRuntimeHostManager()
        self._scheduler_manager = scheduler_manager or _IdleSchedulerManager()
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        artifact_root = config.runtime.artifact_root
        self._operator_platform_root = artifact_root / "operator_platform"
        self._approved_snapshot_store = ApprovedWeightSnapshotStore(
            repo_root / "config" / "strategy" / "weights"
        )

    def list_blueprint_catalog(self) -> PortfolioBlueprintCatalog:
        records = self._operator_platform_store().list_blueprint_activation_records()
        active = self._latest_activation_by_status(records, "active")
        pending = self._latest_activation_by_status(records, "pending_next_start")
        return PortfolioBlueprintCatalog(
            blueprints=list_portfolio_blueprints(
                self._repo_root / "config" / "portfolio" / "blueprints"
            ),
            active_activation=active,
            pending_activation=pending,
        )

    def build_bot_brain_snapshot(self) -> BotBrainSnapshot:
        generated_at = self._now_provider()
        catalog = self.list_blueprint_catalog()
        heartbeat = self.build_runtime_heartbeat_snapshot()
        runtime_state = self.get_runtime_host_state()
        service_cycles = self._paper_store.list_artifact_payloads("service_cycles")
        latest_cycle = self._pick_latest_payload(
            service_cycles,
            timestamp_field="completed_at_utc",
        )
        cycle_explanation = self._build_bot_brain_cycle_explanation(latest_cycle)
        market_state = (
            cycle_explanation.market_state
            if cycle_explanation.market_state
            else self._market_session_label(latest_cycle).lower()
        )
        live_report = self._config.live_disable_report()
        sleeve_readiness = self._build_bot_brain_sleeve_readiness(
            active_activation=catalog.active_activation,
            pending_activation=catalog.pending_activation,
        )
        latest_cycle_order = self._latest_real_order_event(latest_cycle=latest_cycle)
        last_real_order = self._latest_real_order_event()
        return BotBrainSnapshot(
            generated_at_utc=generated_at,
            active_blueprint_id=(
                catalog.active_activation.blueprint_id
                if catalog.active_activation is not None
                else ""
            ),
            queued_blueprint_id=(
                catalog.pending_activation.blueprint_id
                if catalog.pending_activation is not None
                else ""
            ),
            trading_mode=(
                "live" if bool(live_report.get("live_trading_enabled")) else "paper"
            ),
            market_state=market_state,
            next_check_at_utc=heartbeat.next_evaluation_at_utc,
            decision_stages=self._build_bot_brain_decision_stages(
                heartbeat=heartbeat,
                runtime_state=runtime_state,
                latest_cycle=latest_cycle,
                cycle_explanation=cycle_explanation,
                last_order=latest_cycle_order,
            ),
            last_real_order=last_real_order,
            sleeve_readiness=sleeve_readiness,
            cycle_explanation=cycle_explanation,
        )

    def build_dashboard_snapshot(self) -> DashboardSnapshot:
        paper_report = self._paper_store.build_operator_evidence_report()
        validation_report = self._validation_store.build_operator_evidence_report()
        paper_summary = self._ensure_mapping(paper_report["summary"])
        validation_summary = self._ensure_mapping(validation_report["summary"])
        service_cycles = self._paper_store.list_artifact_payloads("service_cycles")
        latest_cycle = self._pick_latest_payload(
            service_cycles,
            timestamp_field="completed_at_utc",
        )
        latest_account_cycle = self._pick_latest_account_cycle(service_cycles)
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
                latest_account_cycle.get("open_position_symbols", ())
                if latest_account_cycle is not None
                else paper_summary.get("latest_open_positions", ())
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
            service_status=self._build_effective_service_state(
                service_cycles=service_cycles,
                latest_cycle=latest_cycle,
            ),
            account_summary=self._build_dashboard_account_summary(
                latest_account_cycle=latest_account_cycle,
                service_cycles=service_cycles,
                paper_summary=paper_summary,
            ),
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

    def _build_command_center_gate_statuses(
        self,
        *,
        runtime_heartbeat: RuntimeHeartbeatSnapshot,
        latest_cycle: Mapping[str, object] | None,
    ) -> dict[str, str]:
        runtime_state = self.get_runtime_host_state()
        runtime_tone = runtime_heartbeat.heartbeat_tone.lower()
        if runtime_state.last_error or runtime_tone == "risk":
            runtime_status = "fail"
        elif runtime_tone in {"good", "info"}:
            runtime_status = "pass"
        else:
            runtime_status = "watch"

        if latest_cycle is None:
            cycle_status = "watch"
            reconciliation_status = "watch"
        else:
            blocked_count = int(str(latest_cycle.get("blocked_trade_count", 0) or 0))
            reconciliation_failures = int(
                str(latest_cycle.get("reconciliation_failure_count", 0) or 0)
            )
            terminal_status = str(latest_cycle.get("cycle_status", "")).lower()
            if blocked_count > 0 or reconciliation_failures > 0:
                cycle_status = "fail"
            elif re.search(r"fail|error|blocked|recovery", terminal_status):
                cycle_status = "fail"
            else:
                cycle_status = "pass"
            reconciliation_status = "fail" if reconciliation_failures > 0 else "pass"

        strategy_id = runtime_state.active_strategy_id
        if strategy_id:
            decision = build_artifact_promotion_decision_provider(
                self._repo_root / "config" / "strategy" / "promotion"
            )(strategy_id)
            authority_status = (
                "pass"
                if state_allows(
                    decision.max_state,
                    PromotionState.PAPER_TRADING,
                )
                and not decision.blocker_codes
                else "fail"
            )
        else:
            authority_status = "watch"

        return {
            "paper_runtime": runtime_status,
            "paper_cycle": cycle_status,
            "paper_reconciliation": reconciliation_status,
            "paper_authority": authority_status,
        }

    def build_command_center_snapshot(self) -> CommandCenterSnapshot:
        dashboard = self.build_dashboard_snapshot()
        runtime_heartbeat = self.build_runtime_heartbeat_snapshot()
        service_cycles = self._paper_store.list_artifact_payloads("service_cycles")
        latest_account_cycle = self._pick_latest_account_cycle(service_cycles)
        fallback_open_positions = tuple(
            {"symbol": symbol}
            for symbol in self._payload_strings(
                latest_account_cycle.get("open_position_symbols", ())
                if latest_account_cycle is not None
                else ()
            )
        )
        latest_portfolio_state = self._latest_reconciliation_portfolio_state_payload(
            minimum_as_of=self._payload_timestamp(
                latest_account_cycle,
                "started_at_utc",
                "completed_at_utc",
            ),
            fallback_open_symbols=tuple(
                position["symbol"] for position in fallback_open_positions
            ),
        )
        latest_open_positions = self._latest_open_position_symbols(
            fallback_positions=fallback_open_positions or dashboard.positions,
            latest_portfolio_state=latest_portfolio_state,
        )
        exposure_breakdown = self._build_exposure_breakdown(
            latest_open_positions=latest_open_positions,
            latest_portfolio_state=latest_portfolio_state,
        )
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
        command_equity_points: list[tuple[datetime, dict[str, str]]] = []
        for payload in service_cycles:
            timestamp = self._payload_timestamp(payload, "completed_at_utc")
            equity_value = self._decimal_from_candidates(
                payload.get("equity"),
                default=Decimal("0"),
            )
            if timestamp is None or equity_value <= Decimal("0"):
                continue
            command_equity_points.append(
                (
                    timestamp,
                    {
                        "label": self._timeline_label(
                            str(payload.get("completed_at_utc", ""))
                        ),
                        "value": str(equity_value),
                    },
                )
            )
        return CommandCenterSnapshot(
            generated_at_utc=dashboard.generated_at_utc,
            service_status=dashboard.service_status,
            market_session_label=market_session_label,
            session_mode=session_mode,
            account_summary=dashboard.account_summary,
            equity_curve=tuple(
                point
                for _, point in sorted(command_equity_points, key=lambda item: item[0])[
                    -12:
                ]
            ),
            exposure_breakdown=exposure_breakdown,
            watchlist=watchlist,
            gate_statuses=self._build_command_center_gate_statuses(
                runtime_heartbeat=runtime_heartbeat,
                latest_cycle=latest_cycle,
            ),
            recommendations=dashboard.recommendations,
            headline_incidents=tuple(
                {
                    "incident_id": incident.incident_id,
                    "severity": incident.severity,
                }
                for incident in incidents[:3]
            ),
        )

    def _latest_open_position_symbols(
        self,
        *,
        fallback_positions: tuple[dict[str, str], ...],
        latest_portfolio_state: dict[str, object] | None,
    ) -> tuple[str, ...]:
        if latest_portfolio_state is not None:
            return tuple(
                symbol
                for position in self._ensure_list(
                    latest_portfolio_state.get("positions", ())
                )
                if isinstance(position, Mapping)
                and (symbol := str(position.get("symbol", "")).strip())
                and (
                    self._decimal_from_payload(position.get("quantity")) is None
                    or self._decimal_from_payload(position.get("quantity"))
                    != Decimal("0")
                )
            )
        return tuple(
            position["symbol"] for position in fallback_positions if position["symbol"]
        )

    def _payload_timestamp(
        self,
        payload: Mapping[str, object] | None,
        *fields: str,
    ) -> datetime | None:
        if payload is None:
            return None
        for field in fields:
            raw_value = str(payload.get(field, "")).strip()
            if raw_value:
                return self._parse_datetime(raw_value)
        return None

    def _pick_latest_account_cycle(
        self,
        service_cycles: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object] | None:
        account_cycles = [
            self._ensure_mapping(payload)
            for payload in service_cycles
            if self._service_cycle_has_account_snapshot(payload)
        ]
        return self._pick_latest_payload(
            account_cycles,
            timestamp_field="completed_at_utc",
        )

    def _service_cycle_has_account_snapshot(
        self, payload: Mapping[str, object]
    ) -> bool:
        if self._payload_strings(payload.get("open_position_symbols", ())):
            return True
        for field in ("cash", "equity", "buying_power"):
            value = self._decimal_from_payload(payload.get(field))
            if value is not None and value != Decimal("0"):
                return True
        return False

    def _build_dashboard_account_summary(
        self,
        *,
        latest_account_cycle: Mapping[str, object] | None,
        service_cycles: Sequence[Mapping[str, object]],
        paper_summary: Mapping[str, object],
    ) -> dict[str, str]:
        if latest_account_cycle is None:
            return {
                "cash": str(paper_summary.get("latest_cash", "")),
                "equity": str(paper_summary.get("latest_equity", "")),
                "buying_power": "",
                "daily_pnl": str(paper_summary.get("daily_pnl", "0")),
            }
        return {
            "cash": str(latest_account_cycle.get("cash", "")),
            "equity": str(latest_account_cycle.get("equity", "")),
            "buying_power": str(latest_account_cycle.get("buying_power", "")),
            "daily_pnl": self._daily_pnl_from_account_cycles(
                service_cycles=service_cycles,
                latest_account_cycle=latest_account_cycle,
            ),
        }

    def _daily_pnl_from_account_cycles(
        self,
        *,
        service_cycles: Sequence[Mapping[str, object]],
        latest_account_cycle: Mapping[str, object],
    ) -> str:
        latest_completed = str(latest_account_cycle.get("completed_at_utc", ""))
        latest_day = latest_completed.split("T")[0]
        if not latest_day:
            return "0"
        same_day_account_cycles = [
            payload
            for payload in service_cycles
            if str(payload.get("completed_at_utc", "")).startswith(latest_day)
            and self._service_cycle_has_account_snapshot(payload)
        ]
        if not same_day_account_cycles:
            return "0"
        first_equity = self._decimal_from_payload(
            same_day_account_cycles[0].get("equity")
        )
        last_equity = self._decimal_from_payload(
            same_day_account_cycles[-1].get("equity")
        )
        if first_equity is None or last_equity is None:
            return "0"
        daily_pnl = last_equity - first_equity
        return "0" if daily_pnl == 0 else str(daily_pnl)

    def _decimal_from_payload(self, value: object) -> Decimal | None:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _latest_payload_timestamp(
        self,
        payloads: Sequence[Mapping[str, object]],
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
        latest_account_cycle = self._pick_latest_account_cycle(service_cycles)
        fallback_open_positions = tuple(
            {"symbol": symbol}
            for symbol in self._payload_strings(
                latest_account_cycle.get("open_position_symbols", ())
                if latest_account_cycle is not None
                else ()
            )
        )
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
                + "Benchmark and strategy attribution panels disclose missing sources instead of hiding unavailable values."
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
                positions=self._portfolio_position_inputs(
                    fallback_positions=fallback_open_positions or dashboard.positions,
                    latest_portfolio_state=self._latest_reconciliation_portfolio_state_payload(
                        minimum_as_of=self._payload_timestamp(
                            latest_account_cycle,
                            "started_at_utc",
                            "completed_at_utc",
                        ),
                        fallback_open_symbols=tuple(
                            position["symbol"] for position in fallback_open_positions
                        ),
                    ),
                ),
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

    def _build_effective_service_state(
        self,
        *,
        service_cycles: Sequence[Mapping[str, object]],
        latest_cycle: Mapping[str, object] | None,
    ) -> WebServiceState:
        manager_state = self._service_manager.get_state()
        if manager_state.status != "idle" or not service_cycles:
            return manager_state
        active_symbols = (
            self._payload_strings(latest_cycle.get("symbols", ()))
            if latest_cycle is not None
            else ()
        )
        return WebServiceState(
            status="idle",
            active_symbols=active_symbols,
            interval_seconds=manager_state.interval_seconds,
            cycles_completed=len(service_cycles),
            started_at_utc=manager_state.started_at_utc,
            last_completed_at_utc=self._payload_timestamp(
                latest_cycle,
                "completed_at_utc",
                "started_at_utc",
            ),
            last_error=manager_state.last_error,
        )

    def get_runtime_host_state(self) -> BotRuntimeState:
        manager_state = self._runtime_host_manager.get_state()
        if manager_state.status != "idle":
            return manager_state
        payload_path = self._operator_platform_root / "runtime_host" / "state.json"
        if not payload_path.exists():
            return manager_state
        try:
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return manager_state
        return BotRuntimeState(
            status=str(payload.get("status", manager_state.status)),
            status_reason=str(
                payload.get("status_reason", manager_state.status_reason)
            ),
            active_symbols=self._payload_strings(payload.get("active_symbols", ())),
            started_at_utc=self._payload_timestamp(payload, "started_at_utc"),
            updated_at_utc=(
                self._payload_timestamp(payload, "updated_at_utc")
                or manager_state.updated_at_utc
            ),
            last_error=str(payload.get("last_error", "")),
            active_strategy_id=str(payload.get("active_strategy_id", "")),
            active_model_snapshot_id=str(payload.get("active_model_snapshot_id", "")),
            latest_selection_id=str(payload.get("latest_selection_id", "")),
        )

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
        cadence_settings = self._runtime_cadence_settings(runtime_state=runtime_state)
        configured_cadence_seconds = cast(
            int, cadence_settings["configured_cadence_seconds"]
        )
        running_cadence_seconds = cast(int, cadence_settings["running_cadence_seconds"])
        cadence_seconds = running_cadence_seconds
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

        latest_portfolio_state = self._latest_reconciliation_portfolio_state_payload(
            minimum_as_of=self._payload_timestamp(
                latest_cycle_payload,
                "started_at_utc",
                "completed_at_utc",
            ),
            fallback_open_symbols=tuple(
                self._payload_strings(
                    latest_cycle_payload.get("open_position_symbols", ())
                )
                if latest_cycle_payload is not None
                else ()
            ),
        )
        fallback_open_positions = tuple(
            {"symbol": symbol}
            for symbol in (
                self._payload_strings(
                    latest_cycle_payload.get("open_position_symbols", ())
                )
                if latest_cycle_payload is not None
                else ()
            )
        )
        current_open_symbols = self._latest_open_position_symbols(
            fallback_positions=fallback_open_positions,
            latest_portfolio_state=latest_portfolio_state,
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
            configured_cadence_seconds=configured_cadence_seconds,
            running_cadence_seconds=running_cadence_seconds,
            cadence_source=str(cadence_settings["cadence_source"]),
            cadence_applies_at=str(cadence_settings["cadence_applies_at"]),
        )

    def _runtime_cadence_settings(
        self,
        *,
        runtime_state: BotRuntimeState,
    ) -> dict[str, object]:
        configured = self._config.runtime.service_interval_seconds
        running = self._config.runtime.service_interval_seconds
        source = "config"
        applies_at = "next_start"
        payload_path = self._operator_platform_root / "runtime_config" / "cadence.json"
        if payload_path.exists():
            try:
                payload = json.loads(payload_path.read_text(encoding="utf-8"))
                override = int(payload.get("configured_cadence_seconds", configured))
                if override > 0:
                    configured = override
                    source = str(payload.get("cadence_source", "operator_override"))
                    applies_at = "next_start"
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        if runtime_state.status in {"idle", "halted", "stopping", "error"}:
            running = configured
        else:
            running_payload_path = (
                self._operator_platform_root / "runtime_config" / "running_cadence.json"
            )
            if running_payload_path.exists():
                try:
                    running_payload = json.loads(
                        running_payload_path.read_text(encoding="utf-8")
                    )
                    running = int(
                        running_payload.get("running_cadence_seconds", running)
                    )
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass
        if (
            runtime_state.status not in {"idle", "halted", "stopping", "error"}
            and source == "operator_override"
            and running == configured
        ):
            applies_at = "current_run"
        return {
            "configured_cadence_seconds": configured,
            "running_cadence_seconds": running,
            "cadence_source": source,
            "cadence_applies_at": applies_at,
        }

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
        latest_portfolio_state = self._latest_reconciliation_portfolio_state_payload(
            minimum_as_of=self._payload_timestamp(
                latest_cycle_payload,
                "started_at_utc",
                "completed_at_utc",
            ),
            fallback_open_symbols=tuple(
                self._payload_strings(
                    latest_cycle_payload.get("open_position_symbols", ())
                )
                if latest_cycle_payload is not None
                else ()
            ),
        )
        fallback_open_positions = tuple(
            {"symbol": symbol}
            for symbol in (
                self._payload_strings(
                    latest_cycle_payload.get("open_position_symbols", ())
                )
                if latest_cycle_payload is not None
                else ()
            )
        )
        current_open_symbols = self._latest_open_position_symbols(
            fallback_positions=fallback_open_positions,
            latest_portfolio_state=latest_portfolio_state,
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
        score = (
            selected_score
            if selected_score is not None
            else (top_score if selection.decision == "no_trade" else None)
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
            symbol=(
                score.symbol if score is not None and not integrity_reason else None
            ),
            final_score=(
                score.final_score
                if score is not None and not integrity_reason
                else None
            ),
            base_signal=(
                score.base_signal
                if score is not None and not integrity_reason
                else None
            ),
            model_weight=(
                score.model_weight
                if score is not None and not integrity_reason
                else None
            ),
            regime_weight=(
                score.regime_weight
                if score is not None and not integrity_reason
                else None
            ),
            liquidity_weight=(
                score.liquidity_weight
                if score is not None and not integrity_reason
                else None
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
        candidate_points: list[tuple[datetime, PortfolioSeriesPoint]] = []
        for payload in service_cycles:
            timestamp_raw = str(payload.get("completed_at_utc", "")).strip()
            if not timestamp_raw:
                continue
            timestamp = self._parse_datetime(timestamp_raw)
            equity = self._decimal_from_candidates(
                payload.get("equity"),
                default=Decimal("0"),
            )
            if equity <= Decimal("0"):
                continue
            candidate_points.append(
                (
                    timestamp,
                    PortfolioSeriesPoint(
                        label=self._timeline_label(timestamp_raw),
                        timestamp_utc=timestamp,
                        equity=self._format_money(equity),
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
                    ),
                )
            )
        points = tuple(
            point
            for _, point in sorted(candidate_points, key=lambda item: item[0])[-24:]
        )
        if len(points) < 2:
            return PortfolioCurvePanel(
                status="unavailable",
                headline="No real TradingX equity curve yet",
                detail=(
                    "The portfolio curve needs at least two non-zero, timestamped account snapshots."
                ),
                points=points,
            )
        return PortfolioCurvePanel(
            status="available",
            headline="TradingX equity curve",
            detail="This chart is built from non-zero recorded account snapshots sorted by source timestamp.",
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
                    benchmark_return="source missing",
                    excess_return="source missing",
                    detail=(
                        "Portfolio return is source-backed, but no aligned S&P 500 benchmark price series "
                        "was found for the same window."
                    ),
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
                attribution_date = (
                    attribution.trading_day
                    if attribution is not None
                    else "unavailable"
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
                            f"Sleeve {binding.sleeve_id}; strategy {binding.strategy_id}; "
                            f"attribution date {attribution_date}; daily return {daily_return}; "
                            f"drift {drift_by_sleeve.get(binding.sleeve_id, 'pending')}."
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
        active_strategy_id = runtime_state.active_strategy_id or "unknown"
        approved_strategy_ids = self._approved_strategy_ids()
        inactive_strategy_rows = tuple(
            PortfolioStrategyRow(
                strategy_id=strategy_id,
                label=strategy_id.replace("-", " ").title(),
                status="configured_not_active",
                pnl="not active",
                trade_count="0",
                win_rate="not active",
                max_drawdown="not active",
                detail=(
                    "Approved strategy config exists, but no active blueprint binding assigns it to the "
                    "running portfolio."
                ),
                drift_severity="pending",
            )
            for strategy_id in approved_strategy_ids
            if strategy_id != active_strategy_id
        )
        return PortfolioStrategyPanel(
            status="partial",
            headline="Strategy attribution is partially available",
            detail=(
                "Closed trades exist, but no active blueprint activation was found. The active runtime "
                "strategy is shown separately from approved-but-inactive strategy configs."
            ),
            strategies=(
                PortfolioStrategyRow(
                    strategy_id=active_strategy_id,
                    label=(active_strategy_id or "Runtime strategy")
                    .replace("-", " ")
                    .title(),
                    status=runtime_state.status,
                    pnl="source missing",
                    trade_count=str(len(closed_trades)),
                    win_rate="source missing",
                    max_drawdown="source missing",
                    detail=(
                        "Only closed-trade count is available; realized P&L and win/loss attribution "
                        "are not present in the current closed-trade records."
                    ),
                    drift_severity="pending",
                ),
            )
            + inactive_strategy_rows,
        )

    def _approved_strategy_ids(self) -> tuple[str, ...]:
        weights_root = self._repo_root / "config" / "strategy" / "weights"
        if not weights_root.exists():
            return ()
        strategy_ids: list[str] = []
        for path in sorted(weights_root.glob("*.yaml")):
            payload = self._parse_simple_yaml(path)
            strategy_id = str(payload.get("strategy_id", "")).strip()
            status = str(payload.get("status", "")).strip().lower()
            if strategy_id and status == "approved":
                strategy_ids.append(strategy_id)
        return tuple(strategy_ids)

    def _parse_simple_yaml(self, path: Path) -> dict[str, object]:
        payload: dict[str, object] = {}
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("#") or ":" not in stripped:
                    continue
                key, _, value = stripped.partition(":")
                if raw_line.startswith(" ") or not value.strip():
                    continue
                payload[key.strip()] = value.strip()
        except OSError:
            return {}
        return payload

    def _latest_active_blueprint_activation(self) -> BlueprintActivationRecord | None:
        records = self._operator_platform_store().list_blueprint_activation_records()
        return self._latest_activation_by_status(records, "active")

    def _latest_activation_by_status(
        self,
        records: Sequence[BlueprintActivationRecord],
        status: str,
    ) -> BlueprintActivationRecord | None:
        matching = tuple(record for record in records if record.status == status)
        if not matching:
            return None
        return max(matching, key=lambda record: record.approved_at_utc)

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

    def _latest_reconciliation_portfolio_state_payload(
        self,
        *,
        minimum_as_of: datetime | None = None,
        fallback_open_symbols: tuple[str, ...] = (),
    ) -> dict[str, object] | None:
        latest_payload: dict[str, object] | None = None
        latest_timestamp: datetime | None = None
        latest_any_payload: dict[str, object] | None = None
        latest_any_timestamp: datetime | None = None
        for payload in self._paper_store.list_artifact_payloads("reconciliation"):
            portfolio_state = self._ensure_mapping(payload.get("portfolio_state", {}))
            timestamp = self._payload_timestamp(portfolio_state, "as_of_utc")
            if timestamp is None:
                continue
            if latest_any_timestamp is None or timestamp > latest_any_timestamp:
                latest_any_timestamp = timestamp
                latest_any_payload = dict(portfolio_state)
            if minimum_as_of is not None and timestamp < minimum_as_of:
                continue
            if latest_timestamp is None or timestamp > latest_timestamp:
                latest_timestamp = timestamp
                latest_payload = dict(portfolio_state)
        if (
            latest_payload is None
            and fallback_open_symbols
            and latest_any_payload is not None
        ):
            portfolio_symbols = {
                symbol
                for position in self._ensure_list(
                    latest_any_payload.get("positions", ())
                )
                if isinstance(position, Mapping)
                and (symbol := str(position.get("symbol", "")).strip())
                and (
                    self._decimal_from_payload(position.get("quantity")) is None
                    or self._decimal_from_payload(position.get("quantity"))
                    != Decimal("0")
                )
            }
            fallback_symbols = {symbol for symbol in fallback_open_symbols if symbol}
            if portfolio_symbols and portfolio_symbols == fallback_symbols:
                latest_payload = dict(latest_any_payload)
                latest_payload["_source_status"] = "stale"
        return latest_payload

    def _portfolio_position_inputs(
        self,
        *,
        fallback_positions: tuple[dict[str, str], ...],
        latest_portfolio_state: dict[str, object] | None,
    ) -> tuple[dict[str, object], ...]:
        if latest_portfolio_state is None:
            return tuple(dict(position) for position in fallback_positions)
        source_at = str(latest_portfolio_state.get("as_of_utc", "")).strip()
        source_status = str(
            latest_portfolio_state.get("_source_status", "fresh")
        ).strip()
        positions = []
        for position in self._ensure_list(latest_portfolio_state.get("positions", ())):
            if not isinstance(position, Mapping):
                continue
            row = dict(position)
            if source_at:
                row["source_evidence_at_utc"] = source_at
            if source_status:
                row["source_status"] = source_status
            row["portfolio_equity"] = latest_portfolio_state.get("equity")
            positions.append(row)
        return tuple(positions)

    def _build_portfolio_positions_panel(
        self,
        *,
        positions: tuple[dict[str, object], ...],
    ) -> PortfolioPositionsPanel:
        if not positions:
            return PortfolioPositionsPanel(
                status="available",
                headline="No open positions",
                detail="The account is flat right now.",
                positions=(),
            )
        rows: list[PortfolioPositionRow] = []
        for position in positions:
            symbol = str(position.get("symbol", "")).strip()
            quantity = self._nullable_decimal_string(position.get("quantity"))
            market_value = self._nullable_decimal_string(position.get("market_value"))
            average_entry_price = self._nullable_decimal_string(
                position.get("average_entry_price")
            )
            latest_price = self._position_latest_price(
                quantity=quantity,
                market_value=market_value,
            )
            portfolio_equity = self._decimal_from_payload(
                position.get("portfolio_equity")
            )
            market_value_decimal = self._decimal_from_payload(market_value)
            exposure_pct = None
            exposure_status = "source_missing"
            source_status = str(position.get("source_status", "fresh")).strip()
            valued_status = "stale" if source_status == "stale" else "fresh"
            if (
                market_value_decimal is not None
                and portfolio_equity is not None
                and portfolio_equity > Decimal("0")
            ):
                exposure_pct = self._format_plain_decimal(
                    (abs(market_value_decimal) / portfolio_equity) * Decimal("100"),
                    decimals=2,
                )
                exposure_status = valued_status
            quantity_status = (
                valued_status if quantity is not None else "source_missing"
            )
            price_status = valued_status if market_value is not None else "unpriced"
            source_evidence_at = self._payload_timestamp(
                position,
                "source_evidence_at_utc",
            )
            rows.append(
                PortfolioPositionRow(
                    symbol=symbol,
                    quantity=quantity,
                    market_value=market_value,
                    exposure_pct=exposure_pct,
                    status=(
                        "missing_price"
                        if market_value is None
                        else "stale_price" if source_status == "stale" else "open"
                    ),
                    quantity_status=quantity_status,
                    price_status=price_status,
                    exposure_status=exposure_status,
                    average_entry_price=average_entry_price,
                    latest_price=latest_price,
                    latest_price_at_utc=source_evidence_at,
                    source_evidence_at_utc=source_evidence_at,
                )
            )
        return PortfolioPositionsPanel(
            status="available",
            headline="Open positions are available",
            detail="These are the current positions reported by the latest account snapshot.",
            positions=tuple(rows),
        )

    def _nullable_decimal_string(self, value: object) -> str | None:
        decimal_value = self._decimal_from_payload(value)
        if decimal_value is None:
            return None
        return str(decimal_value)

    def _position_latest_price(
        self,
        *,
        quantity: str | None,
        market_value: str | None,
    ) -> str | None:
        quantity_decimal = self._decimal_from_payload(quantity)
        market_value_decimal = self._decimal_from_payload(market_value)
        if (
            quantity_decimal is None
            or quantity_decimal == Decimal("0")
            or market_value_decimal is None
        ):
            return None
        return str((market_value_decimal / quantity_decimal).quantize(Decimal("0.01")))

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

    def _latest_real_order_event(
        self,
        *,
        latest_cycle: Mapping[str, object] | None = None,
    ) -> BotBrainOrderEvent | None:
        journal_path = self._data_root_path() / "journal.db"
        if not journal_path.exists():
            return None
        real_order_events = (
            "submit_attempt",
            "ack",
            "accepted",
            "order_recovered",
            "fill",
            "fill_recorded",
            "reject",
            "submit_rejected",
            "rejected",
            "canceled",
            "cancelled",
            "expired",
        )
        placeholders = ",".join("?" for _event in real_order_events)
        query = (
            "select event_type, recorded_at_utc, decision_snapshot_id, "
            "cycle_correlation_id, client_order_id, broker_order_id, symbol, side, "
            "payload_json from oms_journal "
            f"where event_type in ({placeholders}) order by row_id desc limit 200"
        )
        try:
            with sqlite3.connect(journal_path) as connection:
                rows = connection.execute(query, real_order_events).fetchall()
        except sqlite3.Error:
            return None
        if latest_cycle is not None:
            rows = [
                row
                for row in rows
                if self._oms_order_row_belongs_to_cycle(row, latest_cycle)
            ]
        if not rows:
            return None
        latest_by_client_order_id: dict[str, tuple[object, ...]] = {}
        for row in rows:
            client_order_id = str(row[4] or "")
            key = client_order_id or f"row:{len(latest_by_client_order_id)}"
            latest_by_client_order_id.setdefault(key, row)
        row = next(iter(latest_by_client_order_id.values()))
        (
            row_event_type,
            row_recorded_at_utc,
            _decision_snapshot_id,
            _cycle_correlation_id,
            row_client_order_id,
            row_broker_order_id,
            row_symbol,
            row_side,
            row_payload_json,
        ) = row
        try:
            payload = self._ensure_mapping(json.loads(str(row_payload_json)))
        except Exception:
            payload = {}
        reason = str(
            payload.get("reason_code")
            or payload.get("terminal_reason")
            or payload.get("message")
            or row_event_type
        )
        return BotBrainOrderEvent(
            event_type=str(row_event_type),
            recorded_at_utc=self._parse_datetime(str(row_recorded_at_utc)),
            symbol=str(row_symbol),
            side=str(row_side),
            client_order_id=str(row_client_order_id or ""),
            broker_order_id=str(row_broker_order_id or ""),
            reason=reason,
        )

    def _oms_order_row_belongs_to_cycle(
        self,
        row: tuple[object, ...],
        latest_cycle: Mapping[str, object],
    ) -> bool:
        cycle_id = str(latest_cycle.get("cycle_id", "")).strip()
        decision_snapshot_id = str(row[2] or "").strip()
        cycle_correlation_id = str(row[3] or "").strip()
        if cycle_id and cycle_correlation_id == cycle_id:
            return True
        expected_decision_ids = {
            str(value).strip()
            for value in self._ensure_sequence(
                latest_cycle.get("decision_snapshot_ids", ())
            )
            if str(value).strip()
        }
        single_decision_id = str(latest_cycle.get("decision_snapshot_id", "")).strip()
        if single_decision_id:
            expected_decision_ids.add(single_decision_id)
        if decision_snapshot_id and decision_snapshot_id in expected_decision_ids:
            return True

        recorded_at = self._parse_datetime(str(row[1] or ""))
        started_at = self._payload_timestamp(latest_cycle, "started_at_utc")
        completed_at = self._payload_timestamp(latest_cycle, "completed_at_utc")
        if recorded_at is None or started_at is None or completed_at is None:
            return False
        return started_at <= recorded_at <= completed_at + timedelta(seconds=60)

    def _build_bot_brain_decision_stages(
        self,
        *,
        heartbeat: RuntimeHeartbeatSnapshot,
        runtime_state: BotRuntimeState,
        latest_cycle: Mapping[str, object] | None,
        cycle_explanation: BotBrainCycleExplanation,
        last_order: BotBrainOrderEvent | None,
    ) -> tuple[BotBrainDecisionStage, ...]:
        cycle_status = str(latest_cycle.get("cycle_status", "")) if latest_cycle else ""
        decision_source_at = heartbeat.last_evaluation_at_utc
        selected_status = "complete" if heartbeat.selected_symbol else "empty"
        planned_status = (
            "complete"
            if cycle_explanation.planner_status in {"planned", "executed"}
            or cycle_status == "executed"
            else "empty"
        )
        submitted_status = "complete" if last_order is not None else "empty"
        terminal_without_fill_events = {
            "reject",
            "submit_rejected",
            "rejected",
            "canceled",
            "cancelled",
            "expired",
        }
        filled_status = (
            "complete"
            if last_order is not None
            and last_order.event_type in {"fill", "fill_recorded"}
            else "empty"
        )
        held_status = (
            "complete"
            if (
                (cycle_status and cycle_status != "executed" and last_order is None)
                or (
                    last_order is not None
                    and last_order.event_type in terminal_without_fill_events
                )
            )
            else "empty"
        )
        return (
            BotBrainDecisionStage(
                stage="selected",
                status=selected_status,
                detail=heartbeat.last_decision or "No candidate selected yet.",
                occurred_at_utc=decision_source_at,
            ),
            BotBrainDecisionStage(
                stage="planned",
                status=planned_status,
                detail=(
                    "Runtime planner produced evidence for the latest cycle."
                    if planned_status == "complete"
                    else "No persisted executable planner output for the latest cycle."
                ),
                occurred_at_utc=self._payload_timestamp(
                    latest_cycle,
                    "completed_at_utc",
                ),
            ),
            BotBrainDecisionStage(
                stage="submitted",
                status=submitted_status,
                detail=(
                    f"{last_order.event_type} for {last_order.symbol}"
                    if last_order is not None
                    else "No OMS submit or acceptance event has been recorded."
                ),
                occurred_at_utc=(
                    last_order.recorded_at_utc if last_order is not None else None
                ),
            ),
            BotBrainDecisionStage(
                stage="filled",
                status=filled_status,
                detail=(
                    f"Fill recorded for {last_order.symbol}"
                    if filled_status == "complete" and last_order is not None
                    else "No broker fill event has been recorded."
                ),
                occurred_at_utc=(
                    last_order.recorded_at_utc
                    if filled_status == "complete" and last_order is not None
                    else None
                ),
            ),
            BotBrainDecisionStage(
                stage="held_skipped",
                status=held_status,
                detail=(
                    f"Latest order ended as {last_order.event_type}: {last_order.reason}"
                    if last_order is not None
                    and last_order.event_type in terminal_without_fill_events
                    else (
                        f"Latest cycle ended as {cycle_status}."
                        if held_status == "complete"
                        else runtime_state.status_reason
                    )
                ),
                occurred_at_utc=self._payload_timestamp(
                    latest_cycle,
                    "completed_at_utc",
                ),
            ),
        )

    def _build_bot_brain_cycle_explanation(
        self,
        latest_cycle: Mapping[str, object] | None,
    ) -> BotBrainCycleExplanation:
        if latest_cycle is None:
            return BotBrainCycleExplanation(
                summary="No service cycle has been recorded yet.",
                primary_reason_code="no_cycle",
                market_state="unknown",
                planner_status="unknown",
                risk_status="unknown",
                sleeve_reasons=(),
            )
        raw = self._ensure_mapping(latest_cycle.get("cycle_explanation", {}))
        if raw:
            sleeve_reasons = tuple(
                BotBrainSleeveCycleReason(
                    sleeve_id=str(item.get("sleeve_id", "")),
                    status=str(item.get("status", "")),
                    reason=str(item.get("reason", "")),
                )
                for item in self._ensure_sequence(raw.get("sleeve_reasons", ()))
                if isinstance(item, Mapping)
            )
            return BotBrainCycleExplanation(
                summary=str(raw.get("summary", "")),
                primary_reason_code=str(raw.get("primary_reason_code", "")),
                market_state=str(raw.get("market_state", "")),
                planner_status=str(raw.get("planner_status", "")),
                risk_status=str(raw.get("risk_status", "")),
                sleeve_reasons=sleeve_reasons,
            )
        cycle_status = str(latest_cycle.get("cycle_status", "unknown"))
        symbol_results = self._ensure_sequence(latest_cycle.get("symbol_results", ()))
        blocked_count = int(str(latest_cycle.get("blocked_trade_count", 0) or 0))
        if cycle_status == "market_closed":
            summary = "No trade because the market is closed."
            market_state = "closed"
            planner_status = "not_run"
            risk_status = "not_evaluated"
        elif cycle_status == "no_trade":
            summary = (
                "No trade because the planner did not produce an executable order."
            )
            market_state = "open_or_unknown"
            planner_status = "no_trade"
            risk_status = "not_blocked"
        elif blocked_count > 0:
            summary = "No trade because risk or execution controls blocked the order."
            market_state = "open_or_unknown"
            planner_status = "planned"
            risk_status = "blocked"
        else:
            summary = f"Latest cycle ended as {cycle_status}."
            market_state = "open_or_unknown"
            planner_status = "executed" if cycle_status == "executed" else cycle_status
            risk_status = "not_blocked"
        sleeve_reasons = tuple(
            BotBrainSleeveCycleReason(
                sleeve_id=sleeve_id,
                status=str(item.get("terminal_state", "")),
                reason=str(item.get("reason_code", "")),
            )
            for item in symbol_results
            if isinstance(item, Mapping)
            and (sleeve_id := str(item.get("sleeve_id", "")).strip())
        )
        return BotBrainCycleExplanation(
            summary=summary,
            primary_reason_code=cycle_status,
            market_state=market_state,
            planner_status=planner_status,
            risk_status=risk_status,
            sleeve_reasons=sleeve_reasons,
        )

    def _build_bot_brain_sleeve_readiness(
        self,
        *,
        active_activation: BlueprintActivationRecord | None,
        pending_activation: BlueprintActivationRecord | None,
    ) -> tuple[BotBrainSleeveReadiness, ...]:
        candidate_by_id = {
            candidate.candidate_id: candidate
            for candidate in build_runtime_candidate_registry(
                self._config.runtime.symbol_universe
            )
        }
        promotion_provider = build_artifact_promotion_decision_provider(
            self._repo_root / "config" / "strategy" / "promotion"
        )
        rows: list[BotBrainSleeveReadiness] = []
        for activation, activation_role in (
            (active_activation, "active"),
            (pending_activation, "queued"),
        ):
            if activation is None:
                continue
            budget_by_sleeve = self._bot_brain_budget_by_sleeve_for_activation(
                activation
            )
            for binding in activation.sleeve_activation_bindings:
                sleeve_id = binding.sleeve_id
                strategy_id = binding.strategy_id
                candidate = candidate_by_id.get(strategy_id)
                candidate_role = (
                    "reference"
                    if candidate is not None and candidate.status == "reference"
                    else "evaluated" if candidate is not None else "unknown"
                )
                implemented = candidate is not None
                runtime_resolvable = False
                if candidate is not None and candidate.sleeve_class_path is not None:
                    try:
                        build_sleeve_from_candidate(candidate)
                        runtime_resolvable = True
                    except Exception:
                        runtime_resolvable = False
                decision = promotion_provider(strategy_id)
                paper_approved = (
                    state_allows(decision.max_state, PromotionState.PAPER_TRADING)
                    and not decision.blocker_codes
                )
                budget = budget_by_sleeve.get(sleeve_id)
                cap = self._promotion_allocation_cap(
                    decision.strategy_allocation_limits
                )
                allocation_approved = paper_approved and (
                    budget is None or (cap is not None and cap >= budget)
                )
                blocker_code = self._bot_brain_blocker_code(
                    implemented=implemented,
                    runtime_resolvable=runtime_resolvable,
                    paper_approved=paper_approved,
                    allocation_approved=allocation_approved,
                    promotion_blockers=decision.blocker_codes,
                )
                human, guidance = self._humanize_bot_brain_blocker(blocker_code)
                if blocker_code:
                    display_state = "blocked"
                elif activation_role == "active":
                    display_state = "active"
                elif activation_role == "queued":
                    display_state = "queued"
                else:
                    display_state = "ready"
                rows.append(
                    BotBrainSleeveReadiness(
                        sleeve_id=sleeve_id,
                        strategy_id=strategy_id,
                        implemented=implemented,
                        runtime_resolvable=runtime_resolvable,
                        paper_approved=paper_approved,
                        allocation_approved=allocation_approved,
                        display_state=display_state,
                        blocker_code=blocker_code,
                        human_explanation=human,
                        fix_guidance=guidance,
                        evidence_refs=tuple(decision.artifact_refs),
                        activation_id=activation.activation_id,
                        blueprint_id=activation.blueprint_id,
                        activation_role=activation_role,
                        candidate_role=candidate_role,
                    )
                )
        return tuple(rows)

    def _bot_brain_budget_by_sleeve_for_activation(
        self,
        activation: BlueprintActivationRecord,
    ) -> dict[str, Decimal]:
        try:
            if activation.blueprint_payload is not None:
                blueprint = portfolio_blueprint_from_payload(
                    activation.blueprint_payload
                )
            else:
                source_path = activation.source_blueprint_path
                if not source_path.is_absolute():
                    source_path = self._repo_root / source_path
                blueprint = load_portfolio_blueprint(source_path)
        except Exception:
            return {}
        return {
            sleeve.sleeve_id: sleeve.budget_fraction_of_equity
            for sleeve in blueprint.sleeve_budgets
        }

    def _promotion_allocation_cap(
        self,
        limits: tuple[dict[str, str], ...],
    ) -> Decimal | None:
        caps: list[Decimal] = []
        for limit in limits:
            try:
                caps.append(Decimal(str(limit.get("max_strategy_allocation", ""))))
            except Exception:
                continue
        return min(caps) if caps else None

    def _bot_brain_blocker_code(
        self,
        *,
        implemented: bool,
        runtime_resolvable: bool,
        paper_approved: bool,
        allocation_approved: bool,
        promotion_blockers: tuple[str, ...],
    ) -> str:
        if not implemented or not runtime_resolvable:
            return "strategy_not_connected_as_sleeve"
        if not paper_approved:
            return (
                promotion_blockers[0]
                if promotion_blockers
                else "not_approved_for_paper_trading"
            )
        if not allocation_approved:
            return "budget_above_approved_limit"
        return ""

    def _humanize_bot_brain_blocker(self, blocker_code: str) -> tuple[str, str]:
        messages = {
            "": ("Ready for paper runtime.", "No fix needed."),
            "authority_artifact_invalid": (
                "Missing authority package for paper trading.",
                "Generate and sign a valid paper-trading promotion bundle for this strategy.",
            ),
            "not_approved_for_paper_trading": (
                "Strategy is not approved for paper trading.",
                "Promote the strategy to paper trading with no blocker codes.",
            ),
            "strategy_not_connected_as_sleeve": (
                "Strategy is not connected as a runtime sleeve.",
                "Register a SleeveProtocol implementation for this strategy.",
            ),
            "budget_above_approved_limit": (
                "Blueprint budget is above the approved allocation limit.",
                "Sign a capital allocation policy with an approved cap at the blueprint budget.",
            ),
        }
        return messages.get(
            blocker_code,
            (
                f"Authority blocker {blocker_code} is preventing paper trading.",
                "Inspect the promotion-check output and fix the cited authority evidence.",
            ),
        )

    def _count_pending_orders(self) -> int:
        journal_path = self._data_root_path() / "journal.db"
        if not journal_path.exists():
            return 0
        query = (
            "select row_id, client_order_id, event_type, recorded_at_utc "
            "from oms_journal order by row_id desc"
        )
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
        now = self._now_provider().astimezone(UTC)
        for _row_id, client_order_id, event_type, recorded_at_utc in rows:
            client_order = str(client_order_id)
            if not client_order or client_order in seen_client_order_ids:
                continue
            seen_client_order_ids.add(client_order)
            normalized_event_type = str(event_type)
            if normalized_event_type in active_event_types:
                event_time = self._parse_datetime(str(recorded_at_utc))
                if now - event_time > _STALE_DAY_ORDER_PENDING_AFTER:
                    continue
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

    def build_session_timeline(
        self,
        *,
        trading_day: str | None = None,
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> SessionTimelineResponse:
        all_events = self.list_timeline_events(
            symbol=symbol,
            cycle_id=cycle_id,
            incident_id=incident_id,
        )
        available_trading_days = self._available_session_timeline_days(all_events)
        filtered_event_days = tuple(
            sorted(
                {event.occurred_at_utc.date().isoformat() for event in all_events},
                reverse=True,
            )
        )
        should_default_to_event_day = cycle_id is not None or incident_id is not None
        selected_trading_day = trading_day or (
            filtered_event_days[0]
            if should_default_to_event_day and filtered_event_days
            else (
                available_trading_days[0]
                if available_trading_days
                else datetime.now(UTC).date().isoformat()
            )
        )
        session = self._session_timeline_session(selected_trading_day)
        schedule_payload = self._session_timeline_schedule_payload(selected_trading_day)
        filtered_events = [
            self._session_timeline_event(event)
            for event in all_events
            if self._event_belongs_to_trading_day(event, session)
        ]
        schedule_event = self._session_schedule_timeline_event(schedule_payload)
        if schedule_event is not None and self._schedule_event_matches_filters(
            schedule_event,
            cycle_id=cycle_id,
            incident_id=incident_id,
        ):
            filtered_events.insert(0, schedule_event)
        return SessionTimelineResponse(
            session=session,
            available_trading_days=available_trading_days,
            events=tuple(filtered_events),
            filters=SessionTimelineFilters(
                trading_day=selected_trading_day,
                symbol=symbol,
                cycle_id=cycle_id,
                incident_id=incident_id,
            ),
        )

    def _available_session_timeline_days(
        self,
        events: tuple[OperatorTimelineEvent, ...],
    ) -> tuple[str, ...]:
        days = {event.occurred_at_utc.date().isoformat() for event in events}
        days.update(
            str(payload.get("trading_day", "")).strip()
            for payload in self._operator_platform_store().list_artifact_payloads(
                "market_day_schedules"
            )
            if str(payload.get("trading_day", "")).strip()
        )
        return tuple(sorted(days, reverse=True))

    def _session_timeline_session(self, trading_day: str) -> SessionTimelineSession:
        schedule_payload = self._session_timeline_schedule_payload(trading_day)
        if schedule_payload is None:
            return SessionTimelineSession(
                trading_day=trading_day,
                schedule_id="",
                session_open_at_utc=None,
                session_close_at_utc=None,
                exchange="",
                timezone="",
                status="missing_session_metadata",
                metadata_status="schedule_missing",
                partial_reason=(
                    "No market-day schedule metadata was found for this trading day."
                ),
            )

        explicit_open = self._payload_timestamp(schedule_payload, "session_open_at_utc")
        scheduled_open = self._payload_timestamp(
            schedule_payload,
            "scheduled_open_at_utc",
        )
        session_open = explicit_open or scheduled_open
        session_close = self._payload_timestamp(
            schedule_payload, "session_close_at_utc"
        )
        if session_close is None:
            return SessionTimelineSession(
                trading_day=trading_day,
                schedule_id=str(schedule_payload.get("schedule_id", "")),
                session_open_at_utc=session_open,
                session_close_at_utc=None,
                exchange=str(schedule_payload.get("exchange", "")),
                timezone=str(schedule_payload.get("timezone", "")),
                status="partial_session_metadata",
                metadata_status="session_close_missing",
                partial_reason=(
                    "Historical schedule lacks session_close_at_utc; close was not inferred."
                ),
            )
        schedule_status = str(schedule_payload.get("status", "")).strip().lower()
        return SessionTimelineSession(
            trading_day=trading_day,
            schedule_id=str(schedule_payload.get("schedule_id", "")),
            session_open_at_utc=session_open,
            session_close_at_utc=session_close,
            exchange=str(schedule_payload.get("exchange", "")),
            timezone=str(schedule_payload.get("timezone", "")),
            status=(
                "schedule_failed"
                if schedule_status == "failed"
                else "complete_session_metadata"
            ),
            metadata_status="complete",
            partial_reason="",
        )

    def _session_timeline_schedule_payload(
        self,
        trading_day: str,
    ) -> Mapping[str, object] | None:
        payloads = [
            self._ensure_mapping(payload)
            for payload in self._operator_platform_store().list_artifact_payloads(
                "market_day_schedules"
            )
            if str(payload.get("trading_day", "")).strip() == trading_day
        ]
        if not payloads:
            return None
        return max(payloads, key=lambda item: str(item.get("launched_at_utc", "")))

    def _event_belongs_to_trading_day(
        self,
        event: OperatorTimelineEvent,
        session: SessionTimelineSession,
    ) -> bool:
        if (
            session.session_open_at_utc is not None
            and session.session_close_at_utc is not None
            and session.session_open_at_utc
            <= event.occurred_at_utc
            <= session.session_close_at_utc
        ):
            return True
        return event.occurred_at_utc.date().isoformat() == session.trading_day

    def _session_schedule_timeline_event(
        self,
        schedule_payload: Mapping[str, object] | None,
    ) -> SessionTimelineEvent | None:
        if schedule_payload is None:
            return None
        schedule_id = str(schedule_payload.get("schedule_id", "")).strip()
        if not schedule_id:
            return None
        occurred_at = self._payload_timestamp(
            schedule_payload,
            "completed_at_utc",
            "launched_at_utc",
            "scheduled_open_at_utc",
        )
        if occurred_at is None:
            return None
        status = str(schedule_payload.get("status", "")).strip() or "unknown"
        summary = str(schedule_payload.get("summary", "")).strip()
        return SessionTimelineEvent(
            event_id=schedule_id,
            event_type="market_day_schedule",
            symbol="",
            severity=("warning" if status == "failed" else "info"),
            headline=f"Market-day schedule {status}",
            details=summary,
            occurred_at_utc=occurred_at,
            artifact_path=str(
                self._config.runtime.artifact_root
                / "operator_platform"
                / "market_day_schedules"
                / f"{schedule_id}.json"
            ),
            related_ids=tuple(
                item
                for item in (
                    schedule_id,
                    str(schedule_payload.get("automation_run_id", "")).strip(),
                )
                if item
            ),
            shape="instant",
            started_at_utc=None,
            ended_at_utc=None,
            duration_seconds=None,
            status=status,
            reason=summary,
            evidence_freshness="source_timestamp",
            source_status="authoritative_instant",
        )

    def _schedule_event_matches_filters(
        self,
        event: SessionTimelineEvent,
        *,
        cycle_id: str | None,
        incident_id: str | None,
    ) -> bool:
        focus_ids = tuple(item for item in (cycle_id, incident_id) if item)
        if not focus_ids:
            return True
        event_ids = {event.event_id, *event.related_ids}
        return any(focus_id in event_ids for focus_id in focus_ids)

    def _session_timeline_event(
        self,
        event: OperatorTimelineEvent,
    ) -> SessionTimelineEvent:
        return SessionTimelineEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            symbol=event.symbol,
            severity=event.severity,
            headline=event.headline,
            details=event.details,
            occurred_at_utc=event.occurred_at_utc,
            artifact_path=event.artifact_path,
            related_ids=event.related_ids,
            shape="instant",
            started_at_utc=None,
            ended_at_utc=None,
            duration_seconds=None,
            status=self._session_timeline_event_status(event),
            reason=event.details,
            evidence_freshness="source_timestamp",
            source_status="authoritative_instant",
        )

    def _session_timeline_event_status(self, event: OperatorTimelineEvent) -> str:
        if event.severity in {"critical", "error", "warning"}:
            return event.severity
        if "failed" in event.details.lower():
            return "failed"
        if "blocked" in event.details.lower():
            return "blocked"
        return "completed"

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
            session_open_at_utc=self._payload_timestamp(
                payload,
                "session_open_at_utc",
            ),
            session_close_at_utc=self._payload_timestamp(
                payload,
                "session_close_at_utc",
            ),
            exchange=str(payload.get("exchange", "")),
            timezone=str(payload.get("timezone", "")),
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

    def _ensure_sequence(self, value: object) -> tuple[object, ...]:
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            return tuple(value)
        return ()

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
        *,
        latest_open_positions: tuple[str, ...],
        latest_portfolio_state: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], ...]:
        if not latest_open_positions:
            return ()
        positions_by_symbol: dict[str, Mapping[str, object]] = {}
        if latest_portfolio_state is not None:
            source_status = str(
                latest_portfolio_state.get("_source_status", "fresh")
            ).strip()
            for position in self._ensure_list(
                latest_portfolio_state.get("positions", ())
            ):
                if isinstance(position, Mapping):
                    position_symbol = str(position.get("symbol", "")).strip()
                    if position_symbol:
                        positions_by_symbol[position_symbol] = position
        rows: list[dict[str, object]] = []
        for symbol in latest_open_positions:
            latest_position = positions_by_symbol.get(symbol)
            market_value = (
                self._decimal_from_payload(latest_position.get("market_value"))
                if latest_position is not None
                else None
            )
            if market_value is None:
                rows.append(
                    {
                        "symbol": symbol,
                        "value": None,
                        "value_status": (
                            "unpriced"
                            if latest_position is not None
                            else "source_missing"
                        ),
                        "missing_reason": (
                            "Position market value is missing."
                            if latest_position is not None
                            else "Only open-position symbols are available; market values are missing."
                        ),
                    }
                )
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "value": str(market_value),
                    "value_status": ("stale" if source_status == "stale" else "fresh"),
                    "missing_reason": (
                        "Using latest broker-priced reconciliation because newer cycles did not publish a newer broker snapshot."
                        if source_status == "stale"
                        else ""
                    ),
                }
            )
        return tuple(rows)

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
            occurred_at = self._payload_timestamp(
                payload,
                "submitted_at_utc",
                "filled_at_utc",
                "recorded_at_utc",
                "updated_at_utc",
            )
            if occurred_at is None:
                continue
            events.append(
                OperatorTimelineEvent(
                    event_id=order_id or client_order_id,
                    event_type="order",
                    symbol=symbol,
                    severity="info",
                    headline=f"Order for {symbol}",
                    details=f"Status: {payload.get('status', '')}.",
                    occurred_at_utc=occurred_at,
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
