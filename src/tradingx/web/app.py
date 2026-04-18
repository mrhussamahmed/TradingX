from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tradingx.config import TradingConfig
from tradingx.types import (
    CommandCenterSnapshot,
    ConfigProposal,
    DailySessionDigest,
    DashboardSnapshot,
    DocumentRecord,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    IncidentRecord,
    MarketAutomationRunRecord,
    ReplaySession,
    ReplaySlippageSummary,
    ResearchStudioSnapshot,
    WebActionResult,
)


class ReadModelProtocol(Protocol):
    def build_dashboard_snapshot(self) -> DashboardSnapshot: ...

    def build_command_center_snapshot(self) -> CommandCenterSnapshot: ...

    def list_documents(self) -> tuple[DocumentRecord, ...]: ...

    def list_evidence(self, category: str) -> list[dict[str, object]]: ...

    def list_config_proposals(self) -> tuple[ConfigProposal, ...]: ...

    def get_service_state(self) -> object: ...

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


class ActionRunnerProtocol(Protocol):
    def start_service(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult: ...

    def stop_service(self) -> WebActionResult: ...

    def run_paper_loop(self, *, symbol: str, quantity: str) -> WebActionResult: ...

    def run_paper_recover(self, *, symbol: str) -> WebActionResult: ...

    def prepare_benchmark(
        self,
        *,
        symbol: str,
        window_start: str,
        window_end: str,
        feed: str = "iex",
        adjustment: str = "dividend",
    ) -> WebActionResult: ...

    def generate_gate_report(
        self,
        *,
        gate: str,
        benchmark_closes_file: str,
        window_start: str,
        window_end: str,
        universe: tuple[str, ...] = (),
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


class ConfigProposalRequest(BaseModel):
    target_area: str
    proposed_values: dict[str, object]
    rationale: str


class ServiceStartRequest(BaseModel):
    symbols: list[str]
    quantity: str
    interval_seconds: int
    max_cycles: int | None = None


class RecoverRequest(BaseModel):
    symbol: str


class PrepareBenchmarkRequest(BaseModel):
    symbol: str
    window_start: str
    window_end: str
    feed: str = "iex"
    adjustment: str = "dividend"


class GateReportRequest(BaseModel):
    gate: str
    benchmark_closes_file: str
    window_start: str
    window_end: str
    universe: list[str] = []


class DecisionReportRequest(BaseModel):
    gate: str | None = None


class AlertDrillRequest(BaseModel):
    channel: str = "smtp"


class MarketDayRequest(BaseModel):
    symbols: list[str]
    quantity: str
    interval_seconds: int
    max_heartbeats: int | None = None


def create_app(
    *,
    config: TradingConfig,
    read_model: ReadModelProtocol,
    action_runner: ActionRunnerProtocol,
) -> FastAPI:
    app = FastAPI(title="TradingX Local Control Web App")
    static_dir = _repo_root() / "webapp" / "dist"
    if static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

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

    @app.get("/api/documents")
    def get_documents() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.list_documents()))

    @app.get("/api/evidence/{category}")
    def get_evidence(category: str) -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.list_evidence(category)))

    @app.get("/api/service/state")
    def get_service_state() -> JSONResponse:
        return JSONResponse(content=_serialize(read_model.get_service_state()))

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
    def post_service_start(payload: ServiceStartRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(
                action_runner.start_service(
                    symbols=tuple(symbol.upper() for symbol in payload.symbols),
                    quantity=payload.quantity,
                    interval_seconds=payload.interval_seconds,
                    max_cycles=payload.max_cycles,
                )
            )
        )

    @app.post("/api/actions/service/stop")
    def post_service_stop() -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(content=_serialize(action_runner.stop_service()))

    @app.post("/api/actions/paper-loop")
    def post_paper_loop(payload: PaperLoopRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(
                action_runner.run_paper_loop(
                    symbol=payload.symbol,
                    quantity=payload.quantity,
                )
            )
        )

    @app.post("/api/actions/recover")
    def post_recover(payload: RecoverRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(action_runner.run_paper_recover(symbol=payload.symbol))
        )

    @app.post("/api/actions/prepare-benchmark")
    def post_prepare_benchmark(payload: PrepareBenchmarkRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(
                action_runner.prepare_benchmark(
                    symbol=payload.symbol,
                    window_start=payload.window_start,
                    window_end=payload.window_end,
                    feed=payload.feed,
                    adjustment=payload.adjustment,
                )
            )
        )

    @app.post("/api/actions/gate-report")
    def post_gate_report(payload: GateReportRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(
                action_runner.generate_gate_report(
                    gate=payload.gate,
                    benchmark_closes_file=payload.benchmark_closes_file,
                    window_start=payload.window_start,
                    window_end=payload.window_end,
                    universe=tuple(symbol.upper() for symbol in payload.universe),
                )
            )
        )

    @app.post("/api/actions/decision-report")
    def post_decision_report(payload: DecisionReportRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(
                action_runner.generate_decision_report(gate=payload.gate)
            )
        )

    @app.post("/api/actions/session/preopen")
    def post_session_preopen() -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(content=_serialize(action_runner.run_session_preopen()))

    @app.post("/api/actions/session/heartbeat")
    def post_session_heartbeat() -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(content=_serialize(action_runner.run_session_heartbeat()))

    @app.post("/api/actions/session/close")
    def post_session_close() -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(content=_serialize(action_runner.run_session_close()))

    @app.post("/api/actions/session/market-day")
    def post_market_day(payload: MarketDayRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(
                action_runner.run_market_day(
                    symbols=tuple(symbol.upper() for symbol in payload.symbols),
                    quantity=payload.quantity,
                    interval_seconds=payload.interval_seconds,
                    max_heartbeats=payload.max_heartbeats,
                )
            )
        )

    @app.post("/api/actions/recovery-drill")
    def post_recovery_drill(payload: RecoverRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(action_runner.run_recovery_drill(symbol=payload.symbol))
        )

    @app.post("/api/actions/alert-drill")
    def post_alert_drill(payload: AlertDrillRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(action_runner.run_alert_drill(channel=payload.channel))
        )

    @app.post("/api/actions/gate3/report")
    def post_gate3_report() -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(content=_serialize(action_runner.generate_gate3_report()))

    @app.post("/api/actions/gate3/package")
    def post_gate3_package() -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(content=_serialize(action_runner.generate_gate3_package()))

    @app.post("/api/actions/replay-slippage/generate")
    def post_replay_slippage_report() -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(action_runner.generate_replay_slippage_report())
        )

    @app.post("/api/actions/incidents/{incident_id}/acknowledge")
    def post_incident_acknowledge(incident_id: str) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(
                action_runner.acknowledge_incident(incident_id=incident_id)
            )
        )

    @app.post("/api/config/proposals")
    def post_config_proposal(payload: ConfigProposalRequest) -> JSONResponse:
        _ensure_write_mode(config)
        return JSONResponse(
            content=_serialize(
                action_runner.create_config_proposal(
                    target_area=payload.target_area,
                    proposed_values=payload.proposed_values,
                    rationale=payload.rationale,
                )
            )
        )

    @app.get("/{full_path:path}", response_model=None)
    def get_spa_shell(full_path: str) -> FileResponse | JSONResponse:
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse(
            content={
                "message": "Web app frontend has not been built yet.",
                "requested_path": full_path,
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


def _ensure_write_mode(config: TradingConfig) -> None:
    if not config.web.write_mode_enabled:
        raise HTTPException(status_code=403, detail="Web write mode is disabled.")


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


__all__ = ("create_app", "run_web_app")
