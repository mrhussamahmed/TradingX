from __future__ import annotations

from tradingx.config import TradingConfig
from tradingx.types import (
    BotRuntimeState,
    CommandCenterSnapshot,
    ConfigProposal,
    DailySessionDigest,
    DashboardSnapshot,
    DocumentRecord,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    HistoricalWarmupRecord,
    IncidentRecord,
    MarketAutomationRunRecord,
    MarketDayScheduleRecord,
    MarketDaySchedulerState,
    OpportunitySelectionRecord,
    ReplaySession,
    ReplaySlippageSummary,
    ResearchStudioSnapshot,
    StrategyActivationRecord,
    WebActionResult,
    WebServiceState,
)
from tradingx.web.app import create_app


class _Day0ReadModel:
    def build_dashboard_snapshot(self) -> DashboardSnapshot:
        raise NotImplementedError

    def build_command_center_snapshot(self) -> CommandCenterSnapshot:
        raise NotImplementedError

    def build_bot_brain_snapshot(self):
        return {"status": "ok"}

    def list_documents(self) -> tuple[DocumentRecord, ...]:
        return ()

    def list_evidence(self, category: str) -> list[dict[str, object]]:
        return []

    def list_config_proposals(self) -> tuple[ConfigProposal, ...]:
        return ()

    def get_service_state(self) -> object:
        return WebServiceState(
            status="idle",
            active_symbols=(),
            interval_seconds=300,
            cycles_completed=0,
            started_at_utc=None,
            last_completed_at_utc=None,
            last_error="",
        )

    def get_runtime_host_state(self) -> BotRuntimeState:
        raise NotImplementedError

    def get_latest_historical_warmup(self) -> HistoricalWarmupRecord | None:
        return None

    def get_latest_strategy_activation(self) -> StrategyActivationRecord | None:
        return None

    def get_latest_model_weight_snapshot(self):
        return None

    def get_latest_opportunity_selection(self) -> OpportunitySelectionRecord | None:
        return None

    def list_timeline_events(
        self,
        *,
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> tuple[object, ...]:
        return ()

    def list_incidents(self) -> tuple[IncidentRecord, ...]:
        return ()

    def build_research_snapshot(self) -> ResearchStudioSnapshot:
        raise NotImplementedError

    def build_gate3_readiness(self) -> Gate3ReadinessReport:
        raise NotImplementedError

    def get_latest_gate3_promotion_package(self) -> Gate3PromotionPackage | None:
        return None

    def get_latest_replay_slippage_summary(self) -> ReplaySlippageSummary | None:
        return None

    def build_replay_session(
        self,
        *,
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> ReplaySession:
        raise NotImplementedError

    def search_records(
        self,
        *,
        query: str = "",
        category: str | None = None,
    ) -> tuple[object, ...] | list[dict[str, object]]:
        return ()

    def get_latest_daily_digest(self) -> DailySessionDigest | None:
        return None

    def get_latest_market_automation_run(self) -> MarketAutomationRunRecord | None:
        return None

    def get_scheduler_state(self) -> MarketDaySchedulerState:
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

    def get_latest_market_day_schedule(self) -> MarketDayScheduleRecord | None:
        return None


class _Day0ActionRunner:
    def start_service(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult:
        raise NotImplementedError

    def stop_service(self) -> WebActionResult:
        raise NotImplementedError

    def start_runtime_host(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult:
        raise NotImplementedError

    def stop_runtime_host(self) -> WebActionResult:
        raise NotImplementedError

    def start_market_scheduler(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        poll_interval_seconds: int,
        max_scheduled_days: int | None = None,
    ) -> WebActionResult:
        raise NotImplementedError

    def stop_market_scheduler(self) -> WebActionResult:
        raise NotImplementedError

    def run_paper_loop(self, *, symbol: str, quantity: str) -> WebActionResult:
        raise NotImplementedError

    def run_paper_recover(self, *, symbol: str) -> WebActionResult:
        raise NotImplementedError

    def prepare_benchmark(
        self,
        *,
        window_start: str,
        window_end: str,
    ) -> WebActionResult:
        raise NotImplementedError

    def generate_gate_report(
        self,
        *,
        gate: str,
        benchmark_stack_file: str,
        window_start: str,
        window_end: str,
        universe: tuple[str, ...] = (),
    ) -> WebActionResult:
        raise NotImplementedError

    def generate_decision_report(self, *, gate: str | None) -> WebActionResult:
        raise NotImplementedError

    def run_session_preopen(self) -> WebActionResult:
        raise NotImplementedError

    def run_session_heartbeat(self) -> WebActionResult:
        raise NotImplementedError

    def run_session_close(self) -> WebActionResult:
        raise NotImplementedError

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_heartbeats: int | None,
    ) -> WebActionResult:
        raise NotImplementedError

    def run_recovery_drill(self, *, symbol: str) -> WebActionResult:
        raise NotImplementedError

    def run_alert_drill(self, *, channel: str) -> WebActionResult:
        raise NotImplementedError

    def generate_gate3_report(self) -> WebActionResult:
        raise NotImplementedError

    def generate_gate3_package(self) -> WebActionResult:
        raise NotImplementedError

    def generate_replay_slippage_report(self) -> WebActionResult:
        raise NotImplementedError

    def acknowledge_incident(self, *, incident_id: str) -> WebActionResult:
        raise NotImplementedError

    def create_config_proposal(
        self,
        *,
        target_area: str,
        proposed_values: dict[str, object],
        rationale: str,
    ) -> ConfigProposal:
        raise NotImplementedError


def test_learning_proposal_endpoints_are_removed() -> None:
    app = create_app(
        config=TradingConfig.from_mapping({}),
        read_model=_Day0ReadModel(),
        action_runner=_Day0ActionRunner(),
    )
    routes = {route.path for route in app.routes}

    assert "/api/runtime-host/proposal/latest" not in routes
    assert "/api/actions/runtime-host/learn" not in routes
