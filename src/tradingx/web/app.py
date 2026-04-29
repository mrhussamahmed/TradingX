from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tradingx.config import TradingConfig
from tradingx.live_enablement import resolve_broker_mode
from tradingx.sizing import RuntimeSizingPolicy
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
    HistoricalWarmupRecord,
    IncidentRecord,
    MarketAutomationRunRecord,
    MarketDayScheduleRecord,
    MarketDaySchedulerState,
    OpportunitySelectionRecord,
    PerformanceAnalyticsSnapshot,
    PortfolioWorkspaceSnapshot,
    ReplaySession,
    ReplaySlippageSummary,
    ResearchStudioSnapshot,
    RuntimeDecisionDetail,
    RuntimeHeartbeatSnapshot,
    StrategyActivationRecord,
    WebActionResult,
)
from tradingx.web.document_routes import (
    DocumentsPostgresUnavailable,
    DocumentsRouteProvider,
    build_documents_route_provider,
)
from tradingx.web.security import WebWriteAuthorizer, WebWriteIdempotencyStore


class ReadModelProtocol(Protocol):
    def build_dashboard_snapshot(self) -> DashboardSnapshot: ...

    def build_command_center_snapshot(self) -> CommandCenterSnapshot: ...

    def build_portfolio_workspace_snapshot(self) -> PortfolioWorkspaceSnapshot: ...

    def build_performance_analytics_snapshot(
        self,
    ) -> PerformanceAnalyticsSnapshot | PortfolioWorkspaceSnapshot: ...

    def list_documents(self) -> tuple[DocumentRecord, ...]: ...

    def list_evidence(self, category: str) -> list[dict[str, object]]: ...

    def list_config_proposals(self) -> tuple[ConfigProposal, ...]: ...

    def get_service_state(self) -> object: ...

    def get_runtime_host_state(self) -> BotRuntimeState: ...

    def get_latest_historical_warmup(self) -> HistoricalWarmupRecord | None: ...

    def get_latest_strategy_activation(self) -> StrategyActivationRecord | None: ...

    def get_latest_model_weight_snapshot(self) -> ApprovedWeightSnapshot | None: ...

    def get_latest_opportunity_selection(self) -> OpportunitySelectionRecord | None: ...

    def build_runtime_heartbeat_snapshot(self) -> RuntimeHeartbeatSnapshot: ...

    def build_runtime_decision_detail(self) -> RuntimeDecisionDetail | None: ...

    def list_timeline_events(
        self,
        *,
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> tuple[object, ...]: ...

    def list_incidents(self) -> tuple[IncidentRecord, ...]: ...

    def build_research_snapshot(self) -> ResearchStudioSnapshot: ...

    def build_gate3_readiness(self) -> Gate3ReadinessReport: ...

    def get_latest_gate3_promotion_package(self) -> Gate3PromotionPackage | None: ...

    def get_latest_replay_slippage_summary(self) -> ReplaySlippageSummary | None: ...

    def build_replay_session(
        self,
        *,
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> ReplaySession: ...

    def search_records(
        self,
        *,
        query: str = "",
        category: str | None = None,
    ) -> tuple[object, ...] | list[dict[str, object]]: ...

    def get_latest_daily_digest(self) -> DailySessionDigest | None: ...

    def get_latest_market_automation_run(self) -> MarketAutomationRunRecord | None: ...

    def get_scheduler_state(self) -> MarketDaySchedulerState: ...

    def get_latest_market_day_schedule(self) -> MarketDayScheduleRecord | None: ...


class ActionRunnerProtocol(Protocol):
    def start_service(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> WebActionResult: ...

    def stop_service(self) -> WebActionResult: ...

    def start_runtime_host(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
        sizing_policy: RuntimeSizingPolicy | None = None,
    ) -> WebActionResult: ...

    def stop_runtime_host(self) -> WebActionResult: ...

    def start_market_scheduler(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        poll_interval_seconds: int,
        max_scheduled_days: int | None = None,
    ) -> WebActionResult: ...

    def stop_market_scheduler(self) -> WebActionResult: ...

    def run_paper_loop(self, *, symbol: str, quantity: str) -> WebActionResult: ...

    def run_paper_recover(self, *, symbol: str) -> WebActionResult: ...

    def prepare_benchmark(
        self,
        *,
        window_start: str,
        window_end: str,
    ) -> WebActionResult: ...

    def generate_gate_report(
        self,
        *,
        gate: str,
        benchmark_stack_file: str,
        window_start: str,
        window_end: str,
        universe: tuple[str, ...] = (),
        experiment_id: str | None = None,
        run_id: str | None = None,
        promotion_decision_scope: str | None = None,
        metric_release_token: str | None = None,
        dataset_manifest_id: str | None = None,
        dataset_manifest_file: str | None = None,
    ) -> WebActionResult: ...

    def generate_decision_report(self, *, gate: str | None) -> WebActionResult: ...

    def run_session_preopen(self) -> WebActionResult: ...

    def run_session_heartbeat(self) -> WebActionResult: ...

    def run_session_close(self) -> WebActionResult: ...

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_heartbeats: int | None,
    ) -> WebActionResult: ...

    def run_recovery_drill(self, *, symbol: str) -> WebActionResult: ...

    def run_alert_drill(self, *, channel: str) -> WebActionResult: ...

    def generate_gate3_report(self) -> WebActionResult: ...

    def generate_gate3_package(self) -> WebActionResult: ...

    def generate_replay_slippage_report(self) -> WebActionResult: ...

    def acknowledge_incident(self, *, incident_id: str) -> WebActionResult: ...

    def create_config_proposal(
        self,
        *,
        target_area: str,
        proposed_values: dict[str, object],
        rationale: str,
    ) -> ConfigProposal: ...


class PaperLoopRequest(BaseModel):
    symbol: str
    quantity: str


class RuntimeSizingPolicyRequest(BaseModel):
    mode: Literal["fixed_shares", "percent_equity"] = "fixed_shares"
    fixed_quantity: str = "1"
    equity_percent: str = "5"
    max_order_notional: str | None = None
    cash_reserve_percent: str = "20"

    def to_domain(self) -> RuntimeSizingPolicy:
        max_order_notional = (
            None
            if self.max_order_notional is None or not self.max_order_notional.strip()
            else Decimal(self.max_order_notional)
        )
        return RuntimeSizingPolicy(
            mode=self.mode,
            fixed_quantity=Decimal(self.fixed_quantity),
            equity_percent=Decimal(self.equity_percent),
            max_order_notional=max_order_notional,
            cash_reserve_percent=Decimal(self.cash_reserve_percent),
        )


class ConfigProposalRequest(BaseModel):
    target_area: str
    proposed_values: dict[str, object]
    rationale: str


class ServiceStartRequest(BaseModel):
    symbols: list[str]
    quantity: str
    interval_seconds: int
    max_cycles: int | None = None
    sizing_policy: RuntimeSizingPolicyRequest | None = None


class RuntimeHostStartRequest(BaseModel):
    symbols: list[str]
    quantity: str
    interval_seconds: int
    max_cycles: int | None = None
    sizing_policy: RuntimeSizingPolicyRequest | None = None


class RecoverRequest(BaseModel):
    symbol: str


class PrepareBenchmarkRequest(BaseModel):
    window_start: str
    window_end: str


class GateReportRequest(BaseModel):
    gate: str
    benchmark_stack_file: str
    window_start: str
    window_end: str
    universe: list[str] = []
    experiment_id: str | None = None
    run_id: str | None = None
    promotion_decision_scope: str | None = None
    metric_release_token: str | None = None
    dataset_manifest_id: str | None = None
    dataset_manifest_file: str | None = None


class DecisionReportRequest(BaseModel):
    gate: str | None = None


class AlertDrillRequest(BaseModel):
    channel: str = "smtp"


class MarketDayRequest(BaseModel):
    symbols: list[str]
    quantity: str
    interval_seconds: int
    max_heartbeats: int | None = None


class SchedulerStartRequest(BaseModel):
    symbols: list[str]
    quantity: str
    interval_seconds: int
    poll_interval_seconds: int
    max_scheduled_days: int | None = None


def create_app(
    *,
    config: TradingConfig,
    read_model: ReadModelProtocol,
    action_runner: ActionRunnerProtocol,
    documents_route_provider: DocumentsRouteProvider | None = None,
) -> FastAPI:
    app = FastAPI(title="TradingX Local Control Web App")
    document_provider = documents_route_provider or build_documents_route_provider(
        config=config,
        read_model=read_model,
    )
    static_dir = _repo_root() / "webapp" / "dist"
    write_authorizer = WebWriteAuthorizer(
        config=config,
        idempotency_store=WebWriteIdempotencyStore(
            config.runtime.data_root / "control" / "web_write_idempotency"
        ),
        now_provider=lambda: datetime.now(UTC),
    )
    if static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    async def _run_authorized_write(
        request: Request,
        action: Callable[[], object],
    ) -> JSONResponse:
        authorization, replay_response = await write_authorizer.authorize(request)
        if replay_response is not None:
            return replay_response
        payload = _serialize(action())
        response = JSONResponse(content=payload)
        if authorization is not None:
            write_authorizer.store_response(
                authorization,
                response_payload=payload,
                status_code=response.status_code,
            )
        return response

    def _envelope(
        data: object,
        *,
        generated_at: datetime | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "request_id": request_id or _new_request_id(),
            "generated_at": _serialize(generated_at or datetime.now(UTC)),
            "data": _serialize(data),
        }

    def _object_response(
        data: object,
        *,
        generated_at: datetime | None = None,
        status_code: int = 200,
    ) -> JSONResponse:
        return JSONResponse(
            content=_envelope(data, generated_at=generated_at),
            status_code=status_code,
        )

    def _list_response(
        items: object,
        *,
        generated_at: datetime | None = None,
        next_cursor: str | None = None,
        status_code: int = 200,
    ) -> JSONResponse:
        return _object_response(
            {
                "items": items,
                "next_cursor": next_cursor,
            },
            generated_at=generated_at,
            status_code=status_code,
        )

    def _error_response(
        *,
        status_code: int,
        code: str,
        message: str,
    ) -> JSONResponse:
        return _object_response(
            {
                "error": {
                    "code": code,
                    "message": message,
                }
            },
            status_code=status_code,
        )

    def _provisional_response(route_name: str) -> JSONResponse:
        response = _object_response(
            {
                "stability": "provisional",
                "frontend_integration_allowed": False,
                "route": route_name,
                "message": (
                    "This governed write surface is intentionally provisional in "
                    "Wave 1 and must not be used for frontend integration until "
                    "Wave 3 hardens command sessions, signatures, and mutation "
                    "preconditions."
                ),
            },
            status_code=503,
        )
        response.headers["X-TradingX-Stability"] = "provisional"
        return response

    def _documents_postgres_unavailable_response() -> JSONResponse:
        return _error_response(
            status_code=503,
            code="documents_postgres_unavailable",
            message="Documents are temporarily unavailable from Postgres.",
        )

    def _generated_at_hint(value: object) -> datetime | None:
        if isinstance(value, dict):
            generated_at = value.get("generated_at_utc")
            if isinstance(generated_at, datetime):
                return generated_at
        try:
            generated_at = value.generated_at_utc  # type: ignore[attr-defined]
        except AttributeError:
            return None
        if isinstance(generated_at, datetime):
            return generated_at
        return None

    def _snapshot_field(snapshot: object, field_name: str) -> object:
        if isinstance(snapshot, dict):
            return snapshot[field_name]
        return getattr(snapshot, field_name)

    def _control_posture_data() -> dict[str, object]:
        current_decision = resolve_broker_mode(config)
        live_capability = resolve_broker_mode(config, explicit_mode="live")
        governance_posture = {
            "operator_signoff_required": True,
            "operator_signoff_status": "missing",
            "gate4_checklist_status": "missing",
            "approved_by": None,
            "approved_at": None,
        }
        governance_blockers = (
            "operator_signoff_missing",
            "gate4_checklist_missing",
        )
        blockers = tuple(
            dict.fromkeys((*live_capability.disable_reasons, *governance_blockers))
        )
        live_allowed = len(blockers) == 0
        effective_mode = (
            "live"
            if current_decision.requested_mode == "live" and live_allowed
            else "paper"
        )
        return {
            "requested_mode": current_decision.requested_mode,
            "effective_mode": effective_mode,
            "live_allowed": live_allowed,
            "explicit_blockers": [
                {
                    "code": reason,
                    "severity": "hard_block",
                    "message": _LIVE_BLOCKER_MESSAGES.get(
                        reason,
                        reason.replace("_", " ").capitalize() + ".",
                    ),
                }
                for reason in blockers
            ],
            "live_control_layer_states": {
                "broker_credentials_present": config.has_real_live_credentials(),
                "config_live_enabled": config.live_controls.config_enabled,
                "env_live_opt_in_enabled": config.live_controls.env_enabled,
                "code_live_enabled": config.live_controls.code_enabled,
                "broker_mode_live_requested": config.broker_mode == "live",
                "write_signing_configured": config.web.write_signing_configured(),
                "manual_kill_switch_active": config.runtime.manual_kill_switch_active,
                "dry_run_active": config.runtime.dry_run,
            },
            "governance_posture": governance_posture,
            "market_data_posture": {
                "mode": effective_mode,
                "aligned_with_effective_mode": True,
                "status": "nominal" if not blockers else "fail_closed",
            },
            "fail_closed_reasons": list(blockers),
        }

    def _runtime_freshness(
        *,
        runtime_state: BotRuntimeState,
        heartbeat: RuntimeHeartbeatSnapshot,
    ) -> dict[str, object]:
        if runtime_state.status in {"halted", "error", "stopping"}:
            status = "blocked"
        elif heartbeat.last_evaluation_at_utc is None:
            status = "pending"
        elif heartbeat.next_evaluation_at_utc is None:
            status = "idle"
        else:
            elapsed = (
                datetime.now(UTC) - heartbeat.last_evaluation_at_utc
            ).total_seconds()
            status = (
                "fresh" if elapsed <= max(heartbeat.cadence_seconds * 2, 1) else "stale"
            )
        return {
            "status": status,
            "last_evaluation_at": heartbeat.last_evaluation_at_utc,
            "next_evaluation_at": heartbeat.next_evaluation_at_utc,
            "cadence_seconds": heartbeat.cadence_seconds,
        }

    def _runtime_data() -> tuple[dict[str, object], datetime]:
        runtime_state = read_model.get_runtime_host_state()
        heartbeat = read_model.build_runtime_heartbeat_snapshot()
        activation = read_model.get_latest_strategy_activation()
        model_snapshot = read_model.get_latest_model_weight_snapshot()
        selection = read_model.get_latest_opportunity_selection()
        generated_at = heartbeat.last_evaluation_at_utc
        if generated_at is None and selection is not None:
            generated_at = selection.generated_at_utc
        if generated_at is None:
            generated_at = runtime_state.updated_at_utc
        return (
            {
                "lifecycle_state": runtime_state.status,
                "current_activity": {
                    "state": heartbeat.heartbeat_state,
                    "summary": heartbeat.heartbeat_summary,
                    "tone": heartbeat.heartbeat_tone,
                },
                "current_evaluation_state": {
                    "decision": heartbeat.last_decision,
                    "reason": heartbeat.decision_reason,
                    "score_explanation": heartbeat.score_explanation,
                },
                "next_planned_action": {
                    "action": (
                        "evaluate_universe"
                        if heartbeat.next_evaluation_at_utc is not None
                        else "operator_intervention"
                    ),
                    "scheduled_for": heartbeat.next_evaluation_at_utc,
                    "detail": heartbeat.heartbeat_summary,
                },
                "current_universe": list(runtime_state.active_symbols),
                "active_strategy": {
                    "strategy_id": runtime_state.active_strategy_id,
                    "activation": activation,
                },
                "active_model_snapshot": model_snapshot,
                "latest_selection": selection,
                "heartbeat_freshness": _runtime_freshness(
                    runtime_state=runtime_state,
                    heartbeat=heartbeat,
                ),
                "runtime_state": runtime_state,
                "heartbeat": heartbeat,
            },
            generated_at,
        )

    def _runtime_heartbeat_history() -> tuple[dict[str, object], ...]:
        heartbeat = read_model.build_runtime_heartbeat_snapshot()
        return (
            {
                "heartbeat_state": heartbeat.heartbeat_state,
                "heartbeat_summary": heartbeat.heartbeat_summary,
                "heartbeat_tone": heartbeat.heartbeat_tone,
                "recorded_at_utc": heartbeat.last_evaluation_at_utc,
                "next_evaluation_at_utc": heartbeat.next_evaluation_at_utc,
                "decision": heartbeat.last_decision,
            },
        )

    def _candidate_criteria_payload(candidate_id: str) -> dict[str, object]:
        validation_reports = read_model.list_evidence("validation_reports")
        criteria_rows: list[dict[str, object]] = []
        evidence_refs: list[str] = []
        for report in validation_reports:
            for candidate in _payload_dicts(report.get("candidate_results", ())):
                if str(candidate.get("candidate_id", "")).strip() != candidate_id:
                    continue
                evidence_pack_id = str(candidate.get("evidence_pack_id", "")).strip()
                if evidence_pack_id:
                    evidence_refs.append(evidence_pack_id)
                for criterion in _payload_dicts(candidate.get("criteria", ())):
                    raw_status = criterion.get("status")
                    effective_status = (
                        str(raw_status)
                        if raw_status in {"pass", "fail", "pending"}
                        else ("pass" if bool(criterion.get("passed")) else "fail")
                    )
                    criteria_rows.append(
                        {
                            "criterion_id": str(criterion.get("criterion_id", "")),
                            "status": raw_status,
                            "effective_status": effective_status,
                            "passed": bool(criterion.get("passed", False)),
                            "threshold": str(criterion.get("threshold", "")),
                            "details": str(criterion.get("details", "")),
                            "evidence_refs": _payload_strings(
                                report.get("evidence_refs", ())
                            )
                            or ([evidence_pack_id] if evidence_pack_id else []),
                        }
                    )
        research_snapshot = read_model.build_research_snapshot()
        candidate_summary = next(
            (
                summary
                for summary in research_snapshot.candidate_summaries
                if summary.candidate_id == candidate_id
            ),
            None,
        )
        readiness_blockers = [
            {
                "criterion_id": row["criterion_id"],
                "details": row["details"],
            }
            for row in criteria_rows
            if row["effective_status"] == "pending"
        ]
        return {
            "candidate_id": candidate_id,
            "candidate_summary": candidate_summary,
            "criteria": criteria_rows,
            "readiness_blockers": readiness_blockers,
            "evidence_refs": evidence_refs,
        }

    def _parse_replay_focus(replay_id: str) -> dict[str, str | None]:
        for prefix, field_name in (
            ("replay-symbol-", "symbol"),
            ("replay-service_cycle-", "cycle_id"),
            ("replay-incident-", "incident_id"),
        ):
            if replay_id.startswith(prefix):
                return {
                    "symbol": (
                        replay_id[len(prefix) :] if field_name == "symbol" else None
                    ),
                    "cycle_id": (
                        replay_id[len(prefix) :] if field_name == "cycle_id" else None
                    ),
                    "incident_id": (
                        replay_id[len(prefix) :]
                        if field_name == "incident_id"
                        else None
                    ),
                }
        return {"symbol": None, "cycle_id": None, "incident_id": None}

    def _stream_payload_for_topic(topic: str) -> tuple[object, datetime]:
        if topic == "control_posture":
            generated_at = datetime.now(UTC)
            return _control_posture_data(), generated_at
        if topic == "runtime":
            return _runtime_data()
        if topic == "incidents":
            generated_at = datetime.now(UTC)
            return {"items": read_model.list_incidents()}, generated_at
        if topic == "events":
            generated_at = datetime.now(UTC)
            return {"items": read_model.list_timeline_events()}, generated_at
        raise ValueError(topic)

    @app.get("/api/v1/control-posture")
    def get_v1_control_posture() -> JSONResponse:
        return _object_response(_control_posture_data())

    @app.get("/api/v1/runtime")
    def get_v1_runtime() -> JSONResponse:
        payload, generated_at = _runtime_data()
        return _object_response(payload, generated_at=generated_at)

    @app.get("/api/v1/runtime/heartbeats")
    def get_v1_runtime_heartbeats(
        cursor: str | None = None,
    ) -> JSONResponse:
        del cursor
        return _list_response(_runtime_heartbeat_history())

    @app.get("/api/v1/stream")
    def get_v1_stream(topics: str = "control_posture,runtime") -> StreamingResponse:
        requested_topics = tuple(
            dict.fromkeys(topic.strip() for topic in topics.split(",") if topic.strip())
        )
        allowed_topics = {
            "control_posture",
            "runtime",
            "incidents",
            "events",
        }
        unknown_topics = sorted(set(requested_topics) - allowed_topics)
        if unknown_topics:
            error_payload = _envelope(
                {
                    "error": {
                        "code": "unknown_topics",
                        "message": "Unknown realtime topics requested.",
                        "topics": unknown_topics,
                    }
                }
            )
            return StreamingResponse(
                iter(
                    [
                        "event: error\n"
                        f"data: {json.dumps(_serialize(error_payload))}\n\n"
                    ]
                ),
                status_code=400,
                media_type="text/event-stream",
            )

        def _event_stream() -> Any:
            for topic in requested_topics or ("control_posture", "runtime"):
                payload, generated_at = _stream_payload_for_topic(topic)
                event_payload = _envelope(
                    {
                        "topic": topic,
                        "data": payload,
                    },
                    generated_at=generated_at,
                )
                yield (
                    f"event: {topic}\n"
                    f"data: {json.dumps(_serialize(event_payload))}\n\n"
                )

        return StreamingResponse(
            _event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-TradingX-Stream-Mode": "snapshot-sse",
            },
        )

    @app.get("/api/v1/incidents")
    def get_v1_incidents(cursor: str | None = None) -> JSONResponse:
        del cursor
        return _list_response(read_model.list_incidents())

    @app.get("/api/v1/events")
    def get_v1_events(
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
        cursor: str | None = None,
    ) -> JSONResponse:
        del cursor
        return _list_response(
            read_model.list_timeline_events(
                symbol=symbol,
                cycle_id=cycle_id,
                incident_id=incident_id,
            )
        )

    @app.get("/api/v1/portfolio")
    def get_v1_portfolio() -> JSONResponse:
        snapshot = read_model.build_portfolio_workspace_snapshot()
        return _object_response(snapshot, generated_at=_generated_at_hint(snapshot))

    @app.get("/api/v1/portfolio/positions")
    def get_v1_portfolio_positions() -> JSONResponse:
        snapshot = read_model.build_portfolio_workspace_snapshot()
        return _object_response(
            _snapshot_field(snapshot, "positions_panel"),
            generated_at=_generated_at_hint(snapshot),
        )

    @app.get("/api/v1/portfolio/performance")
    def get_v1_portfolio_performance(
        symbol: str | None = None,
        group: str | None = None,
        time_range: str | None = None,
        benchmark: str | None = None,
        portfolio_slice: str | None = None,
    ) -> JSONResponse:
        snapshot = read_model.build_performance_analytics_snapshot()
        return _object_response(
            {
                "filters": {
                    "symbol": symbol,
                    "group": group,
                    "time_range": time_range,
                    "benchmark": benchmark,
                    "portfolio_slice": portfolio_slice,
                },
                "snapshot": snapshot,
            }
        )

    @app.get("/api/v1/portfolio/execution-quality")
    def get_v1_portfolio_execution_quality() -> JSONResponse:
        snapshot = read_model.build_portfolio_workspace_snapshot()
        return _object_response(
            _snapshot_field(snapshot, "execution_panel"),
            generated_at=_generated_at_hint(snapshot),
        )

    @app.get("/api/v1/validation/readiness")
    def get_v1_validation_readiness() -> JSONResponse:
        readiness = read_model.build_gate3_readiness()
        promotion_package = read_model.get_latest_gate3_promotion_package()
        replay_slippage = read_model.get_latest_replay_slippage_summary()
        return _object_response(
            {
                "readiness": readiness,
                "latest_promotion_package": promotion_package,
                "latest_replay_slippage": replay_slippage,
            },
            generated_at=readiness.generated_at_utc,
        )

    @app.get("/api/v1/validation/candidates/{candidate_id}/criteria")
    def get_v1_validation_candidate_criteria(candidate_id: str) -> JSONResponse:
        payload = _candidate_criteria_payload(candidate_id)
        return _object_response(payload)

    @app.get("/api/v1/validation/reports")
    def get_v1_validation_reports(cursor: str | None = None) -> JSONResponse:
        del cursor
        return _object_response(
            {
                "reports": read_model.list_evidence("validation_reports"),
                "decision_briefs": read_model.list_evidence("gate_assessments"),
                "next_cursor": None,
            }
        )

    @app.get("/api/v1/validation/pbo-reports")
    def get_v1_validation_pbo_reports(cursor: str | None = None) -> JSONResponse:
        del cursor
        return _list_response(read_model.list_evidence("pbo_reports"))

    @app.get("/api/v1/investigations")
    def get_v1_investigations(cursor: str | None = None) -> JSONResponse:
        del cursor
        latest_replay = read_model.build_replay_session()
        return _list_response(
            (
                {
                    "investigation_id": latest_replay.replay_id,
                    "headline": latest_replay.headline,
                    "focus_type": latest_replay.focus_type,
                    "focus_value": latest_replay.focus_value,
                    "summary": latest_replay.summary,
                    "event_count": len(latest_replay.events),
                },
            )
        )

    @app.get("/api/v1/replays/{replay_id}")
    def get_v1_replay(replay_id: str) -> JSONResponse:
        if replay_id == "replay-symbol-latest":
            replay = read_model.build_replay_session()
            if replay.replay_id == replay_id and replay.events:
                return _object_response(replay)
            return _error_response(
                status_code=404,
                code="replay_not_found",
                message=f"Replay '{replay_id}' was not found.",
            )
        replay_focus = _parse_replay_focus(replay_id)
        if replay_focus == {"symbol": None, "cycle_id": None, "incident_id": None}:
            return _error_response(
                status_code=404,
                code="replay_not_found",
                message=f"Replay '{replay_id}' was not found.",
            )
        replay = read_model.build_replay_session(**replay_focus)
        if replay.replay_id != replay_id or not replay.events:
            return _error_response(
                status_code=404,
                code="replay_not_found",
                message=f"Replay '{replay_id}' was not found.",
            )
        return _object_response(replay)

    @app.get("/api/v1/documents")
    def get_v1_documents(cursor: str | None = None) -> JSONResponse:
        del cursor
        try:
            documents = document_provider.list_documents()
        except DocumentsPostgresUnavailable:
            return _documents_postgres_unavailable_response()
        return _list_response(documents)

    @app.get("/api/v1/documents/{document_id}")
    def get_v1_document(document_id: str) -> JSONResponse:
        try:
            document = document_provider.get_document(document_id)
        except DocumentsPostgresUnavailable:
            return _documents_postgres_unavailable_response()
        if document is None:
            return _error_response(
                status_code=404,
                code="document_not_found",
                message=f"Document '{document_id}' was not found.",
            )
        return _object_response(
            {
                "document_id": document.doc_id,
                "title": document.title,
                "kind": document.kind,
                "preview": document.preview,
                "retrieval_ref": str(document.path),
            }
        )

    @app.get("/api/v1/commands", include_in_schema=False)
    def get_v1_commands_provisional() -> JSONResponse:
        return _provisional_response("/api/v1/commands")

    @app.post("/api/v1/commands", include_in_schema=False)
    def post_v1_commands_provisional() -> JSONResponse:
        return _provisional_response("/api/v1/commands")

    @app.post("/api/v1/command-sessions", include_in_schema=False)
    def post_v1_command_sessions_provisional() -> JSONResponse:
        return _provisional_response("/api/v1/command-sessions")

    @app.get("/api/overview")
    def get_overview() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.build_dashboard_snapshot()))

    @app.get("/api/platform/command-center")
    def get_command_center() -> JSONResponse:
        return JSONResponse(
            content=_serialize(read_model.build_command_center_snapshot())
        )

    @app.get("/api/platform/timeline")
    def get_timeline(
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> JSONResponse:
        return JSONResponse(
            content=_serialize(
                read_model.list_timeline_events(
                    symbol=symbol,
                    cycle_id=cycle_id,
                    incident_id=incident_id,
                )
            )
        )

    @app.get("/api/platform/incidents")
    def get_incidents() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.list_incidents()))

    @app.get("/api/platform/research")
    def get_research() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.build_research_snapshot()))

    @app.get("/api/platform/portfolio")
    def get_portfolio_workspace() -> JSONResponse:
        return JSONResponse(
            content=_serialize(read_model.build_portfolio_workspace_snapshot())
        )

    @app.get("/api/platform/performance")
    def get_performance_analytics() -> JSONResponse:
        return JSONResponse(
            content=_serialize(read_model.build_portfolio_workspace_snapshot())
        )

    @app.get("/api/platform/gate3/readiness")
    def get_gate3_readiness() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.build_gate3_readiness()))

    @app.get("/api/platform/gate3/promotions/latest")
    def get_gate3_promotion_package() -> JSONResponse:
        package = read_model.get_latest_gate3_promotion_package()
        if package is None:
            return JSONResponse(content=None)
        return JSONResponse(content=_serialize(package))

    @app.get("/api/platform/gate3/replay-slippage/latest")
    def get_latest_replay_slippage_summary() -> JSONResponse:
        summary = read_model.get_latest_replay_slippage_summary()
        if summary is None:
            return JSONResponse(content=None)
        return JSONResponse(content=_serialize(summary))

    @app.get("/api/platform/replay")
    def get_replay(
        symbol: str | None = None,
        cycle_id: str | None = None,
        incident_id: str | None = None,
    ) -> JSONResponse:
        return JSONResponse(
            content=_serialize(
                read_model.build_replay_session(
                    symbol=symbol,
                    cycle_id=cycle_id,
                    incident_id=incident_id,
                )
            )
        )

    @app.get("/api/platform/explorer")
    def get_explorer(
        query: str = "",
        category: str | None = None,
    ) -> JSONResponse:
        return JSONResponse(
            content=_serialize(
                read_model.search_records(
                    query=query,
                    category=category,
                )
            )
        )

    @app.get("/api/platform/digests/latest")
    def get_latest_digest() -> JSONResponse:
        digest = read_model.get_latest_daily_digest()
        if digest is None:
            return JSONResponse(content=None)
        return JSONResponse(content=_serialize(digest))

    @app.get("/api/platform/gate3/automation/latest")
    def get_latest_market_automation_run() -> JSONResponse:
        run_record = read_model.get_latest_market_automation_run()
        if run_record is None:
            return JSONResponse(content=None)
        return JSONResponse(content=_serialize(run_record))

    @app.get("/api/platform/gate3/scheduler/state")
    def get_scheduler_state() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.get_scheduler_state()))

    @app.get("/api/platform/gate3/scheduler/latest")
    def get_latest_market_day_schedule() -> JSONResponse:
        schedule_record = read_model.get_latest_market_day_schedule()
        if schedule_record is None:
            return JSONResponse(content=None)
        return JSONResponse(content=_serialize(schedule_record))

    @app.get("/api/documents")
    def get_documents() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.list_documents()))

    @app.get("/api/evidence/{category}")
    def get_evidence(category: str) -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.list_evidence(category)))

    @app.get("/api/service/state")
    def get_service_state() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.get_service_state()))

    @app.get("/api/runtime-host/state")
    def get_runtime_host_state() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.get_runtime_host_state()))

    @app.get("/api/runtime-host/heartbeat")
    def get_runtime_host_heartbeat() -> JSONResponse:
        return JSONResponse(
            content=_serialize(read_model.build_runtime_heartbeat_snapshot())
        )

    @app.get("/api/runtime-host/warmup/latest")
    def get_runtime_host_warmup() -> JSONResponse:
        warmup = read_model.get_latest_historical_warmup()
        return JSONResponse(content=_serialize(warmup) if warmup is not None else None)

    @app.get("/api/runtime-host/activation/latest")
    def get_runtime_host_activation() -> JSONResponse:
        activation = read_model.get_latest_strategy_activation()
        return JSONResponse(
            content=_serialize(activation) if activation is not None else None
        )

    @app.get("/api/runtime-host/model/latest")
    def get_runtime_host_model() -> JSONResponse:
        snapshot = read_model.get_latest_model_weight_snapshot()
        return JSONResponse(
            content=_serialize(snapshot) if snapshot is not None else None
        )

    @app.get("/api/runtime-host/selection/latest")
    def get_runtime_host_selection() -> JSONResponse:
        selection = read_model.get_latest_opportunity_selection()
        return JSONResponse(
            content=_serialize(selection) if selection is not None else None
        )

    @app.get("/api/runtime-host/decision/latest")
    def get_runtime_host_decision() -> JSONResponse:
        detail = read_model.build_runtime_decision_detail()
        return JSONResponse(content=_serialize(detail) if detail is not None else None)

    @app.get("/api/config/summary")
    def get_config_summary() -> JSONResponse:
        return JSONResponse(
            content={
                "config": config.to_safe_summary(),
                "live_disable_report": config.live_disable_report(),
            }
        )

    @app.get("/api/config/proposals")
    def get_config_proposals() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.list_config_proposals()))

    @app.post("/api/actions/service/start")
    async def post_service_start(
        request: Request,
        payload: ServiceStartRequest,
    ) -> JSONResponse:
        def start_service_action() -> WebActionResult:
            symbols = tuple(symbol.upper() for symbol in payload.symbols)
            if payload.sizing_policy is None:
                return action_runner.start_service(
                    symbols=symbols,
                    quantity=payload.quantity,
                    interval_seconds=payload.interval_seconds,
                    max_cycles=payload.max_cycles,
                )
            return action_runner.start_service(
                symbols=symbols,
                quantity=payload.quantity,
                interval_seconds=payload.interval_seconds,
                max_cycles=payload.max_cycles,
                sizing_policy=payload.sizing_policy.to_domain(),
            )

        return await _run_authorized_write(
            request,
            start_service_action,
        )

    @app.post("/api/actions/service/stop")
    async def post_service_stop(request: Request) -> JSONResponse:
        return await _run_authorized_write(request, action_runner.stop_service)

    @app.post("/api/actions/runtime-host/start")
    async def post_runtime_host_start(
        request: Request,
        payload: RuntimeHostStartRequest,
    ) -> JSONResponse:
        def start_runtime_host_action() -> WebActionResult:
            symbols = tuple(symbol.upper() for symbol in payload.symbols)
            if payload.sizing_policy is None:
                return action_runner.start_runtime_host(
                    symbols=symbols,
                    quantity=payload.quantity,
                    interval_seconds=payload.interval_seconds,
                    max_cycles=payload.max_cycles,
                )
            return action_runner.start_runtime_host(
                symbols=symbols,
                quantity=payload.quantity,
                interval_seconds=payload.interval_seconds,
                max_cycles=payload.max_cycles,
                sizing_policy=payload.sizing_policy.to_domain(),
            )

        return await _run_authorized_write(
            request,
            start_runtime_host_action,
        )

    @app.post("/api/actions/runtime-host/stop")
    async def post_runtime_host_stop(request: Request) -> JSONResponse:
        return await _run_authorized_write(request, action_runner.stop_runtime_host)

    @app.post("/api/actions/scheduler/start")
    async def post_scheduler_start(
        request: Request,
        payload: SchedulerStartRequest,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.start_market_scheduler(
                symbols=tuple(symbol.upper() for symbol in payload.symbols),
                quantity=payload.quantity,
                interval_seconds=payload.interval_seconds,
                poll_interval_seconds=payload.poll_interval_seconds,
                max_scheduled_days=payload.max_scheduled_days,
            ),
        )

    @app.post("/api/actions/scheduler/stop")
    async def post_scheduler_stop(request: Request) -> JSONResponse:
        return await _run_authorized_write(request, action_runner.stop_market_scheduler)

    @app.post("/api/actions/paper-loop")
    async def post_paper_loop(
        request: Request,
        payload: PaperLoopRequest,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.run_paper_loop(
                symbol=payload.symbol,
                quantity=payload.quantity,
            ),
        )

    @app.post("/api/actions/recover")
    async def post_recover(request: Request, payload: RecoverRequest) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.run_paper_recover(symbol=payload.symbol),
        )

    @app.post("/api/actions/prepare-benchmark")
    async def post_prepare_benchmark(
        request: Request,
        payload: PrepareBenchmarkRequest,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.prepare_benchmark(
                window_start=payload.window_start,
                window_end=payload.window_end,
            ),
        )

    @app.post("/api/actions/gate-report")
    async def post_gate_report(
        request: Request,
        payload: GateReportRequest,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.generate_gate_report(
                gate=payload.gate,
                benchmark_stack_file=payload.benchmark_stack_file,
                window_start=payload.window_start,
                window_end=payload.window_end,
                universe=tuple(symbol.upper() for symbol in payload.universe),
                experiment_id=payload.experiment_id,
                run_id=payload.run_id,
                promotion_decision_scope=payload.promotion_decision_scope,
                metric_release_token=payload.metric_release_token,
                dataset_manifest_id=payload.dataset_manifest_id,
                dataset_manifest_file=payload.dataset_manifest_file,
            ),
        )

    @app.post("/api/actions/decision-report")
    async def post_decision_report(
        request: Request,
        payload: DecisionReportRequest,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.generate_decision_report(gate=payload.gate),
        )

    @app.post("/api/actions/session/preopen")
    async def post_session_preopen(request: Request) -> JSONResponse:
        return await _run_authorized_write(request, action_runner.run_session_preopen)

    @app.post("/api/actions/session/heartbeat")
    async def post_session_heartbeat(request: Request) -> JSONResponse:
        return await _run_authorized_write(request, action_runner.run_session_heartbeat)

    @app.post("/api/actions/session/close")
    async def post_session_close(request: Request) -> JSONResponse:
        return await _run_authorized_write(request, action_runner.run_session_close)

    @app.post("/api/actions/session/market-day")
    async def post_market_day(
        request: Request,
        payload: MarketDayRequest,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.run_market_day(
                symbols=tuple(symbol.upper() for symbol in payload.symbols),
                quantity=payload.quantity,
                interval_seconds=payload.interval_seconds,
                max_heartbeats=payload.max_heartbeats,
            ),
        )

    @app.post("/api/actions/recovery-drill")
    async def post_recovery_drill(
        request: Request,
        payload: RecoverRequest,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.run_recovery_drill(symbol=payload.symbol),
        )

    @app.post("/api/actions/alert-drill")
    async def post_alert_drill(
        request: Request,
        payload: AlertDrillRequest,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.run_alert_drill(channel=payload.channel),
        )

    @app.post("/api/actions/gate3/report")
    async def post_gate3_report(request: Request) -> JSONResponse:
        return await _run_authorized_write(request, action_runner.generate_gate3_report)

    @app.post("/api/actions/gate3/package")
    async def post_gate3_package(request: Request) -> JSONResponse:
        return await _run_authorized_write(
            request,
            action_runner.generate_gate3_package,
        )

    @app.post("/api/actions/replay-slippage/generate")
    async def post_replay_slippage_report(request: Request) -> JSONResponse:
        return await _run_authorized_write(
            request,
            action_runner.generate_replay_slippage_report,
        )

    @app.post("/api/actions/incidents/{incident_id}/acknowledge")
    async def post_incident_acknowledge(
        incident_id: str,
        request: Request,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.acknowledge_incident(incident_id=incident_id),
        )

    @app.post("/api/config/proposals")
    async def post_config_proposal(
        request: Request,
        payload: ConfigProposalRequest,
    ) -> JSONResponse:
        return await _run_authorized_write(
            request,
            lambda: action_runner.create_config_proposal(
                target_area=payload.target_area,
                proposed_values=payload.proposed_values,
                rationale=payload.rationale,
            ),
        )

    @app.get("/{full_path:path}", response_model=None)
    def get_spa_shell(full_path: str) -> FileResponse | JSONResponse:
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse(
            content={
                "message": "Web app frontend has not been built yet.",
            },
            status_code=503,
        )

    return app


def run_web_app(config: TradingConfig, *, host: str, port: int) -> None:
    from tradingx.web.runtime import build_default_local_web_components

    read_model, action_runner = build_default_local_web_components(config)
    uvicorn.run(
        create_app(config=config, read_model=read_model, action_runner=action_runner),
        host=host,
        port=port,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def _payload_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list | tuple):
        return []
    return [
        {str(key): item for key, item in entry.items()}
        for entry in value
        if isinstance(entry, dict)
    ]


def _payload_strings(value: object) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [str(item) for item in value]


_LIVE_BLOCKER_MESSAGES = {
    "broker_mode_not_live": "Broker mode is not currently set to live.",
    "missing_live_credentials": "Live broker credentials are not configured.",
    "config_layer_disabled": "The live-trading config layer remains disabled.",
    "env_layer_disabled": "The live-trading environment opt-in remains disabled.",
    "code_layer_disabled": "The live-trading code guard remains disabled.",
    "web_write_signing_unconfigured": "Signed web writes are not configured.",
    "manual_kill_switch_active": "The manual kill switch is active.",
    "dry_run_enabled": "Dry-run mode is still active.",
    "operator_signoff_missing": "Operator sign-off has not been recorded.",
    "gate4_checklist_missing": "The Gate 4 approval checklist is not complete.",
}


def _new_request_id() -> str:
    return f"req_{uuid4().hex}"


__all__ = ("create_app", "run_web_app")
