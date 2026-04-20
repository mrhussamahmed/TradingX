from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from tradingx.config import TradingConfig
from tradingx.types import (
    ApprovedWeightSnapshot,
    BotRuntimeState,
    CommandCenterSnapshot,
    ConfigProposal,
    DailySessionDigest,
    DashboardSnapshot,
    DocumentRecord,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    IncidentRecord,
    MarketAutomationRunRecord,
    MarketDayScheduleRecord,
    MarketDaySchedulerState,
    OpportunityScore,
    OpportunitySelectionRecord,
    ReplaySession,
    ReplaySlippageSummary,
    ResearchCandidateSummary,
    ResearchStudioSnapshot,
    RuntimeHeartbeatSnapshot,
    RuntimeDecisionLadderRow,
    StrategyActivationRecord,
    RuntimeOperatorGuidance,
    RuntimeSymbolHeartbeatRow,
    RuntimeTruthItem,
    WebActionResult,
    WebServiceState,
)
from tradingx.web.app import create_app


class FakeReadModel:
    def build_dashboard_snapshot(self) -> DashboardSnapshot:
        timestamp = datetime(2026, 4, 17, 18, 0, tzinfo=UTC)
        return DashboardSnapshot(
            generated_at_utc=timestamp,
            service_status=WebServiceState(
                status="running",
                active_symbols=("SPY", "QQQ"),
                interval_seconds=300,
                cycles_completed=3,
                started_at_utc=timestamp,
                last_completed_at_utc=timestamp,
                last_error="",
            ),
            account_summary={
                "cash": "10025.00",
                "equity": "10030.00",
                "buying_power": "20030.00",
                "daily_pnl": "5.00",
            },
            positions=({"symbol": "SPY", "quantity": "1", "market_value": "101.00"},),
            alerts=("Blocked trade due to stale broker state.",),
            gate_statuses={"1": "pass", "2": "pending"},
            recommendations={"promote_candidate": 1},
            document_summary={"session_count": 2, "latest_state": "Gate 3 pending."},
        )

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        return (
            DocumentRecord(
                doc_id="STATE",
                title="Project state",
                path=Path("docs/handover/STATE.md"),
                preview="Gate 3 pending.",
                kind="state",
            ),
        )

    def list_evidence(self, category: str) -> list[dict[str, object]]:
        return [{"category": category, "summary": "ok"}]

    def list_config_proposals(self) -> tuple[ConfigProposal, ...]:
        return (
            ConfigProposal(
                proposal_id="proposal-1",
                target_area="runtime",
                proposed_values={"TRADINGX_SYMBOL_UNIVERSE": ["SPY"]},
                diff_preview="+ TRADINGX_SYMBOL_UNIVERSE=SPY",
                output_path=Path("config/proposals/proposal-1.md"),
            ),
        )

    def get_service_state(self) -> WebServiceState:
        return self.build_dashboard_snapshot().service_status

    def build_command_center_snapshot(self) -> CommandCenterSnapshot:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return CommandCenterSnapshot(
            generated_at_utc=timestamp,
            service_status=self.build_dashboard_snapshot().service_status,
            market_session_label="Regular session monitor",
            session_mode="intraday",
            account_summary=self.build_dashboard_snapshot().account_summary,
            equity_curve=(
                {"label": "09:30", "value": "10000.00"},
                {"label": "10:00", "value": "10030.00"},
            ),
            exposure_breakdown=({"symbol": "SPY", "value": "100"},),
            watchlist=({"symbol": "SPY", "status": "active"},),
            gate_statuses={"1": "pass"},
            recommendations={"promote_candidate": 1},
            headline_incidents=(
                {"incident_id": "incident-alert-1", "severity": "warning"},
            ),
        )

    def list_incidents(self) -> tuple[IncidentRecord, ...]:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return (
            IncidentRecord(
                incident_id="incident-alert-1",
                title="Blocked trade",
                severity="warning",
                status="open",
                category="risk",
                summary="Stale broker state blocked a trade.",
                first_seen_at_utc=timestamp,
                latest_seen_at_utc=timestamp,
                acknowledged_at_utc=None,
                acknowledged_by="",
                related_event_ids=("event-1",),
                evidence_refs=("artifacts/paper_loop/operator_alerts/alert-1.json",),
                suggested_action="Review broker state freshness.",
            ),
        )

    def build_gate3_readiness(self) -> Gate3ReadinessReport:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return Gate3ReadinessReport(
            report_id="gate3-1",
            generated_at_utc=timestamp,
            status="pending",
            closed_trade_count=4,
            calendar_days_observed=7,
            criteria=(),
            summary="Gate 3 is still collecting evidence.",
            required_operator_action="Continue paper trading and drills.",
            evidence_refs=("artifacts/validation/gate3_reports/gate3-1.json",),
        )

    def get_latest_gate3_promotion_package(self) -> Gate3PromotionPackage | None:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return Gate3PromotionPackage(
            package_id="gate3-package-1",
            generated_at_utc=timestamp,
            status="pending",
            headline="Gate 3 is not ready for promotion.",
            decision_summary="More paper evidence is required.",
            criteria_statuses={"duration_or_trade_count": "pending"},
            evidence_refs=("artifacts/validation/gate3_packages/gate3-package-1.json",),
        )

    def get_latest_replay_slippage_summary(self) -> ReplaySlippageSummary | None:
        timestamp = datetime(2026, 4, 18, 18, 5, tzinfo=UTC)
        return ReplaySlippageSummary(
            summary_id="replay-summary-1",
            matched_execution_count=12,
            paper_mean_absolute_slippage_bps="5.0",
            replay_mean_absolute_slippage_bps="7.5",
            divergence_ratio="1.5",
            status="pass",
            details="Replay divergence is within the allowed bound.",
            generated_at_utc=timestamp,
        )

    def get_latest_market_automation_run(self) -> MarketAutomationRunRecord | None:
        timestamp = datetime(2026, 4, 18, 18, 6, tzinfo=UTC)
        return MarketAutomationRunRecord(
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

    def get_scheduler_state(self) -> MarketDaySchedulerState:
        timestamp = datetime(2026, 4, 18, 18, 7, tzinfo=UTC)
        return MarketDaySchedulerState(
            status="waiting",
            poll_interval_seconds=60,
            active_symbols=("SPY", "QQQ"),
            next_run_at_utc=timestamp,
            last_started_at_utc=None,
            last_completed_at_utc=None,
            active_trading_day="2026-04-21",
            last_error="",
        )

    def get_latest_market_day_schedule(self) -> MarketDayScheduleRecord | None:
        timestamp = datetime(2026, 4, 18, 18, 7, tzinfo=UTC)
        return MarketDayScheduleRecord(
            schedule_id="schedule-1",
            trading_day="2026-04-18",
            scheduled_open_at_utc=timestamp,
            launched_at_utc=timestamp,
            completed_at_utc=timestamp,
            status="completed",
            automation_run_id="automation-1",
            summary="Scheduled market day completed.",
            evidence_refs=(
                "artifacts/operator_platform/market_day_schedules/schedule-1.json",
            ),
        )

    def build_portfolio_workspace_snapshot(self) -> dict[str, object]:
        return {
            "generated_at_utc": datetime(2026, 4, 19, 12, 30, tzinfo=UTC),
            "trading_mode": "paper",
            "data_state": "partial",
            "source_summary": "Account balances and execution evidence are real; benchmark comparison is waiting for persisted TradingX history.",
            "metric_cards": [
                {
                    "metric_id": "equity",
                    "label": "Total Equity",
                    "value": "$100,030.00",
                    "delta": "Flat vs seeded account",
                    "health": "neutral",
                    "summary": "Neutral because capital is preserved, but there is no completed live evidence yet.",
                    "detail": "Equity is intact. This protects capital, but it does not yet demonstrate trading edge.",
                    "sparkline": (),
                },
                {
                    "metric_id": "execution_quality",
                    "label": "Execution Quality",
                    "value": "2 rejects",
                    "delta": "Latest reason: insufficient buying power",
                    "health": "bad",
                    "summary": "Bad because the bot is attempting orders the account cannot currently support.",
                    "detail": "Repeated rejected submissions indicate a sizing or risk-control mismatch that should be fixed before more automation.",
                    "sparkline": ("2", "2"),
                },
            ],
            "equity_curve": {
                "status": "unavailable",
                "headline": "No real TradingX equity curve yet",
                "detail": "The portfolio curve will appear after at least one timestamped service cycle is recorded.",
                "points": [],
            },
            "benchmark_panel": {
                "status": "unavailable",
                "headline": "Benchmark comparison waiting for evidence",
                "detail": "TradingX needs a persisted equity history window before benchmark-relative analytics can be trusted.",
                "benchmark_rows": [],
            },
            "strategy_panel": {
                "status": "unavailable",
                "headline": "Strategy attribution waiting for closed-trade evidence",
                "detail": "Strategy contribution will unlock after TradingX records closed trades and realized P&L.",
                "strategies": [],
            },
            "execution_panel": {
                "status": "available",
                "headline": "Execution journal is available",
                "detail": "Recent order attempts are available from the OMS journal and are safe to inspect now.",
                "summary_metrics": [
                    {"label": "Reject Count", "value": "2"},
                    {"label": "Latest Reason", "value": "insufficient buying power"},
                ],
                "recent_events": [
                    {
                        "label": "Reject",
                        "value": "SPY buy rejected",
                        "context": "insufficient buying power",
                    }
                ],
            },
            "positions_panel": {
                "status": "available",
                "headline": "No open positions",
                "detail": "The account is flat right now.",
                "positions": [],
            },
            "diagnostics": [
                {
                    "diagnostic_id": "runtime",
                    "title": "Runtime is halted before warmup completed",
                    "detail": "QQQ remains blocked by insufficient bars.",
                    "severity": "warning",
                    "owner": "Runtime Host",
                    "action": "Refresh warmup inputs before broadening deployment.",
                }
            ],
        }

    def build_performance_analytics_snapshot(self) -> dict[str, object]:
        return self.build_portfolio_workspace_snapshot()

    def get_runtime_host_state(self) -> BotRuntimeState:
        timestamp = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        return BotRuntimeState(
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

    def build_runtime_heartbeat_snapshot(self) -> RuntimeHeartbeatSnapshot:
        timestamp = datetime(2026, 4, 19, 12, 5, tzinfo=UTC)
        return RuntimeHeartbeatSnapshot(
            heartbeat_state="Waiting for next evaluation",
            heartbeat_summary=(
                "TradingX evaluated the configured universe, found no deployable trade, "
                "and is waiting for the next cadence tick."
            ),
            heartbeat_tone="info",
            cadence_seconds=300,
            cadence_label="Every 5m",
            last_evaluation_at_utc=timestamp,
            next_evaluation_at_utc=timestamp,
            last_decision="No trade",
            decision_reason="No eligible opportunity cleared the deploy threshold.",
            score_explanation="SPY scored 0.4177 which is below the deploy threshold of 0.50.",
            current_exposure="Flat",
            current_exposure_detail="No open position is currently held in the paper account.",
            active_symbol="SPY",
            selected_symbol="",
            decision="no_trade",
            runtime_truth=(
                RuntimeTruthItem(
                    label="Session posture",
                    value="Intraday monitor",
                    detail="Mission Control is in its market-session monitoring posture.",
                    tone="info",
                ),
                RuntimeTruthItem(
                    label="Trading mode",
                    value="Paper",
                    detail="Orders remain in paper mode only.",
                    tone="good",
                ),
            ),
            symbol_rows=(
                RuntimeSymbolHeartbeatRow(
                    symbol="SPY",
                    status="Below threshold",
                    score="0.4177",
                    threshold_gap="-0.0823",
                    reason="Score remained below the deploy threshold.",
                    warmup_state="Ready",
                    exposure_state="Flat",
                    tone="info",
                ),
                RuntimeSymbolHeartbeatRow(
                    symbol="QQQ",
                    status="Blocked",
                    score="n/a",
                    threshold_gap="n/a",
                    reason="Insufficient daily bars for warmup coverage.",
                    warmup_state="Blocked",
                    exposure_state="Flat",
                    tone="watch",
                ),
            ),
            decision_ladder=(
                RuntimeDecisionLadderRow(
                    rank=1,
                    symbol="SPY",
                    final_score="0.4177",
                    threshold="0.50",
                    threshold_gap="-0.0823",
                    primary_driver="Volatility penalty",
                    disposition="Monitor",
                ),
                RuntimeDecisionLadderRow(
                    rank=2,
                    symbol="QQQ",
                    final_score="n/a",
                    threshold="0.50",
                    threshold_gap="n/a",
                    primary_driver="Warmup blocked",
                    disposition="Blocked",
                ),
            ),
            operator_guidance=RuntimeOperatorGuidance(
                recommendation="Investigate warmup failure",
                detail="QQQ is still blocked by warmup, so TradingX is evaluating an incomplete universe.",
                tone="watch",
            ),
        )

    def get_latest_historical_warmup(self):
        timestamp = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        return {
            "warmup_id": "warmup-1",
            "generated_at_utc": timestamp,
            "benchmark_symbol": "SPY",
            "symbols": ("SPY", "QQQ"),
            "window_start_utc": timestamp,
            "window_end_utc": timestamp,
            "required_bar_count": 30,
            "symbols_ready": ("SPY", "QQQ"),
            "symbols_blocked": {},
            "return_summary": {"SPY": {"cumulative_return": "0.02"}},
        }

    def get_latest_strategy_activation(self) -> StrategyActivationRecord | None:
        timestamp = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        return StrategyActivationRecord(
            activation_id="activation-1",
            strategy_id="baseline-long-only-v1",
            strategy_version="1.0.0",
            approved_symbols=("SPY", "QQQ"),
            deploy_threshold="0.5",
            allow_fallback_weights=True,
            status="approved",
            activated_at_utc=timestamp,
            notes="Baseline activation.",
        )

    def get_latest_model_weight_snapshot(self) -> ApprovedWeightSnapshot | None:
        timestamp = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        return ApprovedWeightSnapshot(
            snapshot_id="snapshot-1",
            strategy_id="baseline-long-only-v1",
            status="approved",
            generated_at_utc=timestamp,
            minimum_supporting_trades=5,
            weights={"signal": "1.0"},
        )

    def get_latest_opportunity_selection(self) -> OpportunitySelectionRecord | None:
        timestamp = datetime(2026, 4, 19, 12, 0, tzinfo=UTC)
        return OpportunitySelectionRecord(
            selection_id="selection-1",
            generated_at_utc=timestamp,
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="snapshot-1",
            symbols_considered=("SPY", "QQQ"),
            ranked_opportunities=(
                OpportunityScore(
                    symbol="SPY",
                    base_signal="1.0",
                    regime_weight="1.0",
                    model_weight="1.0",
                    liquidity_weight="1.0",
                    spread_penalty="0.1",
                    volatility_penalty="0.1",
                    portfolio_overlap_penalty="0.0",
                    execution_cost_penalty="0.0",
                    final_score="0.8",
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="SPY",
            decision="selected",
            decision_reason="Top ranked.",
        )

    def build_research_snapshot(self) -> ResearchStudioSnapshot:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return ResearchStudioSnapshot(
            generated_at_utc=timestamp,
            gate_summaries=({"gate_id": "1", "status": "pass"},),
            candidate_summaries=(
                ResearchCandidateSummary(
                    candidate_id="trend-following-v1",
                    family="trend_following",
                    recommendation="promote_candidate",
                    benchmark_metrics={"sharpe": "1.0"},
                    candidate_metrics={"sharpe": "1.4"},
                    adversarial_checks=("fee_stress",),
                    gate_statuses={"1": "pass"},
                    summary="Candidate cleared Gate 1.",
                ),
            ),
            decision_summary="Gate 1 passed.",
        )

    def build_replay_session(
        self,
        *,
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> ReplaySession:
        return ReplaySession(
            replay_id="replay-1",
            focus_type="symbol",
            focus_value=symbol or cycle_id or incident_id or "SPY",
            headline="Replay",
            events=(),
            summary="Replay ready.",
        )

    def search_records(
        self,
        *,
        query: str = "",
        category: str | None = None,
    ) -> list[dict[str, object]]:
        return [
            {
                "record_id": "record-1",
                "category": category or "validation_report",
                "title": "Gate 1 report",
                "preview": f"query={query}",
                "path": "artifacts/validation/validation_reports/gate-1.json",
                "symbol": "SPY",
                "recorded_at_utc": "2026-04-18T18:00:00+00:00",
            }
        ]

    def get_latest_daily_digest(self) -> DailySessionDigest | None:
        timestamp = datetime(2026, 4, 18, 18, 0, tzinfo=UTC)
        return DailySessionDigest(
            digest_id="digest-1",
            generated_at_utc=timestamp,
            session_label="session_close",
            service_status="stopped",
            blocked_trade_count=1,
            reconciliation_failure_count=0,
            latest_positions=("SPY",),
            top_incidents=("incident-alert-1",),
            recommended_actions=("Review broker freshness.",),
            evidence_refs=("artifacts/operator_platform/daily_digests/digest-1.json",),
        )


class FakeActionRunner:
    def start_service(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult:
        return WebActionResult(
            action_id="action-start",
            action_type="paper_service_start",
            status="accepted",
            message=f"Started service for {','.join(symbols)}.",
            evidence_refs=(),
        )

    def stop_service(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-stop",
            action_type="paper_service_stop",
            status="accepted",
            message="Stop requested.",
            evidence_refs=(),
        )

    def start_market_scheduler(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        poll_interval_seconds: int,
        max_scheduled_days: int | None = None,
    ) -> WebActionResult:
        return WebActionResult(
            action_id="action-scheduler-start",
            action_type="market_scheduler_start",
            status="accepted",
            message=f"Started scheduler for {','.join(symbols)}.",
            evidence_refs=(),
        )

    def stop_market_scheduler(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-scheduler-stop",
            action_type="market_scheduler_stop",
            status="accepted",
            message="Scheduler stop requested.",
            evidence_refs=(),
        )

    def start_runtime_host(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult:
        return WebActionResult(
            action_id="action-runtime-start",
            action_type="runtime_host_start",
            status="accepted",
            message=f"Runtime host started for {','.join(symbols)}.",
            evidence_refs=(),
        )

    def stop_runtime_host(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-runtime-stop",
            action_type="runtime_host_stop",
            status="accepted",
            message="Runtime host stop requested.",
            evidence_refs=(),
        )

    def run_paper_loop(self, *, symbol: str, quantity: str) -> WebActionResult:
        return WebActionResult(
            action_id="action-1",
            action_type="paper_loop",
            status="completed",
            message=f"Ran paper loop for {symbol}.",
            evidence_refs=("artifacts/paper_loop/service_cycles/cycle-1.json",),
        )

    def run_paper_recover(self, *, symbol: str) -> WebActionResult:
        return WebActionResult(
            action_id="action-recover",
            action_type="paper_recover",
            status="completed",
            message=f"Recovered {symbol}.",
            evidence_refs=("artifacts/paper_loop/reconciliation/recover.json",),
        )

    def prepare_benchmark(
        self,
        *,
        symbol: str,
        window_start: str,
        window_end: str,
        feed: str = "iex",
        adjustment: str = "dividend",
    ) -> WebActionResult:
        return WebActionResult(
            action_id="action-benchmark",
            action_type="prepare_benchmark",
            status="completed",
            message=f"Prepared benchmark for {symbol}.",
            evidence_refs=("artifacts/validation/benchmarks/spy.json",),
        )

    def generate_gate_report(
        self,
        *,
        gate: str,
        benchmark_closes_file: str,
        window_start: str,
        window_end: str,
        universe: tuple[str, ...] = (),
    ) -> WebActionResult:
        return WebActionResult(
            action_id="action-gate",
            action_type="gate_report",
            status="completed",
            message=f"Generated Gate {gate} report.",
            evidence_refs=("artifacts/validation/validation_reports/gate-1.json",),
        )

    def generate_decision_report(self, *, gate: str | None) -> WebActionResult:
        return WebActionResult(
            action_id="action-decision",
            action_type="decision_report",
            status="completed",
            message=f"Generated decision report for gate {gate or 'latest'}.",
            evidence_refs=("artifacts/validation/gate_assessments/gate-1.json",),
        )

    def create_config_proposal(
        self,
        *,
        target_area: str,
        proposed_values: dict[str, object],
        rationale: str,
    ) -> ConfigProposal:
        return ConfigProposal(
            proposal_id="proposal-2",
            target_area=target_area,
            proposed_values=proposed_values,
            diff_preview=f"# {rationale}",
            output_path=Path("config/proposals/proposal-2.md"),
        )

    def run_session_preopen(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-preopen",
            action_type="session_preopen",
            status="completed",
            message="Pre-open checklist captured.",
            evidence_refs=("artifacts/operator_platform/daily_digests/preopen.json",),
        )

    def run_session_heartbeat(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-heartbeat",
            action_type="session_heartbeat",
            status="completed",
            message="Heartbeat captured.",
            evidence_refs=("artifacts/operator_platform/daily_digests/heartbeat.json",),
        )

    def run_session_close(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-close",
            action_type="session_close",
            status="completed",
            message="Session close digest generated.",
            evidence_refs=("artifacts/operator_platform/daily_digests/close.json",),
        )

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_heartbeats: int | None,
    ) -> WebActionResult:
        return WebActionResult(
            action_id="action-market-day",
            action_type="market_day_run",
            status="completed",
            message=f"Market-day automation completed for {','.join(symbols)}.",
            evidence_refs=(
                "artifacts/operator_platform/market_automation_runs/automation-1.json",
            ),
        )

    def run_recovery_drill(self, *, symbol: str) -> WebActionResult:
        return WebActionResult(
            action_id="action-recovery-drill",
            action_type="recovery_drill",
            status="completed",
            message=f"Recovery drill completed for {symbol}.",
            evidence_refs=("artifacts/paper_loop/recovery_drills/recovery-1.json",),
        )

    def run_alert_drill(self, *, channel: str) -> WebActionResult:
        return WebActionResult(
            action_id="action-alert-drill",
            action_type="alert_drill",
            status="completed",
            message=f"Alert drill completed for {channel}.",
            evidence_refs=("artifacts/paper_loop/alert_drills/alert-1.json",),
        )

    def generate_gate3_report(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-gate3-report",
            action_type="gate3_report",
            status="completed",
            message="Gate 3 readiness report generated.",
            evidence_refs=("artifacts/validation/gate3_reports/gate3-1.json",),
        )

    def generate_gate3_package(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-gate3-package",
            action_type="gate3_package",
            status="completed",
            message="Gate 3 promotion package generated.",
            evidence_refs=("artifacts/validation/gate3_packages/gate3-package-1.json",),
        )

    def generate_replay_slippage_report(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-replay",
            action_type="replay_slippage_report",
            status="completed",
            message="Replay slippage report generated.",
            evidence_refs=(
                "artifacts/validation/replay_slippage_summaries/replay-summary-1.json",
            ),
        )

    def acknowledge_incident(self, *, incident_id: str) -> WebActionResult:
        return WebActionResult(
            action_id="action-ack",
            action_type="incident_acknowledge",
            status="completed",
            message=f"Acknowledged {incident_id}.",
            evidence_refs=(
                f"artifacts/operator_platform/incident_acknowledgements/{incident_id}.json",
            ),
        )


def test_local_web_app_exposes_dashboard_and_document_endpoints() -> None:
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=FakeReadModel(),
        action_runner=FakeActionRunner(),
    )
    client = TestClient(app)

    overview = client.get("/api/overview")
    documents = client.get("/api/documents")
    service_state = client.get("/api/service/state")
    config_summary = client.get("/api/config/summary")
    evidence = client.get("/api/evidence/operator_alerts")
    command_center = client.get("/api/platform/command-center")
    incidents = client.get("/api/platform/incidents")
    gate3 = client.get("/api/platform/gate3/readiness")
    gate3_package = client.get("/api/platform/gate3/promotions/latest")
    research = client.get("/api/platform/research")
    replay = client.get("/api/platform/replay?symbol=SPY")
    explorer = client.get("/api/platform/explorer?query=Gate")
    digest = client.get("/api/platform/digests/latest")
    automation = client.get("/api/platform/gate3/automation/latest")
    scheduler_state = client.get("/api/platform/gate3/scheduler/state")
    scheduler_latest = client.get("/api/platform/gate3/scheduler/latest")
    portfolio = client.get("/api/platform/portfolio")
    performance = client.get("/api/platform/performance")
    runtime_state = client.get("/api/runtime-host/state")
    runtime_heartbeat = client.get("/api/runtime-host/heartbeat")
    runtime_warmup = client.get("/api/runtime-host/warmup/latest")
    runtime_activation = client.get("/api/runtime-host/activation/latest")
    runtime_model = client.get("/api/runtime-host/model/latest")
    runtime_selection = client.get("/api/runtime-host/selection/latest")

    assert overview.status_code == 200
    assert overview.json()["service_status"]["status"] == "running"
    assert documents.status_code == 200
    assert documents.json()[0]["kind"] == "state"
    assert service_state.status_code == 200
    assert service_state.json()["status"] == "running"
    assert config_summary.status_code == 200
    assert config_summary.json()["config"]["web_write_mode_enabled"] is False
    assert evidence.status_code == 200
    assert evidence.json()[0]["category"] == "operator_alerts"
    assert command_center.status_code == 200
    assert command_center.json()["market_session_label"] == "Regular session monitor"
    assert incidents.status_code == 200
    assert incidents.json()[0]["status"] == "open"
    assert gate3.status_code == 200
    assert gate3.json()["status"] == "pending"
    assert gate3_package.status_code == 200
    assert gate3_package.json()["package_id"] == "gate3-package-1"
    assert research.status_code == 200
    assert (
        research.json()["candidate_summaries"][0]["candidate_id"]
        == "trend-following-v1"
    )
    assert replay.status_code == 200
    assert replay.json()["focus_value"] == "SPY"
    assert explorer.status_code == 200
    assert explorer.json()[0]["title"] == "Gate 1 report"
    assert digest.status_code == 200
    assert digest.json()["digest_id"] == "digest-1"
    assert automation.status_code == 200
    assert automation.json()["run_id"] == "automation-1"
    assert scheduler_state.status_code == 200
    assert scheduler_state.json()["status"] == "waiting"
    assert scheduler_latest.status_code == 200
    assert scheduler_latest.json()["schedule_id"] == "schedule-1"
    assert portfolio.status_code == 200
    assert portfolio.json()["data_state"] == "partial"
    assert portfolio.json()["metric_cards"][0]["metric_id"] == "equity"
    assert portfolio.json()["benchmark_panel"]["status"] == "unavailable"
    assert performance.status_code == 200
    assert performance.json()["data_state"] == "partial"
    assert performance.json()["execution_panel"]["headline"] == "Execution journal is available"
    assert runtime_state.status_code == 200
    assert runtime_state.json()["status"] == "trading_ready"
    assert runtime_heartbeat.status_code == 200
    assert runtime_heartbeat.json()["heartbeat_state"] == "Waiting for next evaluation"
    assert runtime_heartbeat.json()["last_decision"] == "No trade"
    assert runtime_heartbeat.json()["runtime_truth"][0]["label"] == "Session posture"
    assert runtime_heartbeat.json()["symbol_rows"][0]["symbol"] == "SPY"
    assert (
        runtime_heartbeat.json()["operator_guidance"]["recommendation"]
        == "Investigate warmup failure"
    )
    assert runtime_warmup.status_code == 200
    assert runtime_warmup.json()["warmup_id"] == "warmup-1"
    assert runtime_activation.status_code == 200
    assert runtime_activation.json()["activation_id"] == "activation-1"
    assert runtime_model.status_code == 200
    assert runtime_model.json()["snapshot_id"] == "snapshot-1"
    assert runtime_selection.status_code == 200
    assert runtime_selection.json()["selected_symbol"] == "SPY"


def test_replay_slippage_endpoints_return_summary_and_accept_generation() -> None:
    app = create_app(
        config=TradingConfig.from_mapping(
            {
                "TRADINGX_WEB_WRITE_MODE_ENABLED": "true",
            }
        ),
        read_model=FakeReadModel(),
        action_runner=FakeActionRunner(),
    )
    client = TestClient(app)

    summary = client.get("/api/platform/gate3/replay-slippage/latest")
    action = client.post("/api/actions/replay-slippage/generate")

    assert summary.status_code == 200
    assert summary.json()["summary_id"] == "replay-summary-1"
    assert action.status_code == 200
    assert action.json()["action_type"] == "replay_slippage_report"


def test_local_web_app_blocks_mutations_when_write_mode_is_disabled() -> None:
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=FakeReadModel(),
        action_runner=FakeActionRunner(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/actions/paper-loop",
        json={"symbol": "SPY", "quantity": "1"},
    )
    digest = client.post("/api/actions/session/close")

    assert response.status_code == 403
    assert response.json()["detail"] == "Web write mode is disabled."
    assert digest.status_code == 403


def test_local_web_app_allows_safe_mutations_when_write_mode_is_enabled() -> None:
    app = create_app(
        config=TradingConfig.from_mapping({"TRADINGX_WEB_WRITE_MODE_ENABLED": "true"}),
        read_model=FakeReadModel(),
        action_runner=FakeActionRunner(),
    )
    client = TestClient(app)

    action = client.post(
        "/api/actions/paper-loop",
        json={"symbol": "SPY", "quantity": "1"},
    )
    service_start = client.post(
        "/api/actions/service/start",
        json={
            "symbols": ["SPY", "QQQ"],
            "quantity": "1",
            "interval_seconds": 300,
            "max_cycles": 1,
        },
    )
    service_stop = client.post("/api/actions/service/stop")
    runtime_start = client.post(
        "/api/actions/runtime-host/start",
        json={
            "symbols": ["SPY", "QQQ"],
            "quantity": "1",
            "interval_seconds": 300,
            "max_cycles": 1,
        },
    )
    runtime_stop = client.post("/api/actions/runtime-host/stop")
    recover = client.post(
        "/api/actions/recover",
        json={"symbol": "SPY"},
    )
    benchmark = client.post(
        "/api/actions/prepare-benchmark",
        json={
            "symbol": "SPY",
            "window_start": "2023-01-01",
            "window_end": "2026-04-17",
        },
    )
    gate = client.post(
        "/api/actions/gate-report",
        json={
            "gate": "1",
            "benchmark_closes_file": "artifacts/validation/benchmarks/spy.json",
            "window_start": "2023-01-01",
            "window_end": "2026-04-17",
            "universe": ["SPY", "QQQ"],
        },
    )
    decision = client.post(
        "/api/actions/decision-report",
        json={"gate": "1"},
    )
    proposal = client.post(
        "/api/config/proposals",
        json={
            "target_area": "runtime",
            "proposed_values": {"TRADINGX_SYMBOL_UNIVERSE": ["SPY", "QQQ"]},
            "rationale": "Expand the universe for the next paper session.",
        },
    )
    preopen = client.post("/api/actions/session/preopen")
    heartbeat = client.post("/api/actions/session/heartbeat")
    close_result = client.post("/api/actions/session/close")
    market_day = client.post(
        "/api/actions/session/market-day",
        json={
            "symbols": ["SPY", "QQQ"],
            "quantity": "1",
            "interval_seconds": 300,
            "max_heartbeats": 2,
        },
    )
    gate3_report = client.post("/api/actions/gate3/report")
    gate3_package = client.post("/api/actions/gate3/package")
    recovery_drill = client.post(
        "/api/actions/recovery-drill",
        json={"symbol": "SPY"},
    )
    alert_drill = client.post(
        "/api/actions/alert-drill",
        json={"channel": "smtp"},
    )
    acknowledge = client.post("/api/actions/incidents/incident-alert-1/acknowledge")

    assert action.status_code == 200
    assert action.json()["status"] == "completed"
    assert service_start.status_code == 200
    assert service_start.json()["status"] == "accepted"
    assert service_stop.status_code == 200
    assert runtime_start.status_code == 200
    assert runtime_start.json()["action_type"] == "runtime_host_start"
    assert runtime_stop.status_code == 200
    assert recover.status_code == 200
    assert benchmark.status_code == 200
    assert gate.status_code == 200
    assert decision.status_code == 200
    assert proposal.status_code == 200
    assert proposal.json()["proposal_id"] == "proposal-2"
    assert preopen.status_code == 200
    assert heartbeat.status_code == 200
    assert close_result.status_code == 200
    assert market_day.status_code == 200
    assert market_day.json()["action_type"] == "market_day_run"
    assert gate3_report.status_code == 200
    assert gate3_package.status_code == 200
    assert recovery_drill.status_code == 200
    assert alert_drill.status_code == 200
    assert acknowledge.status_code == 200
