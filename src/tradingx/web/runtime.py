from __future__ import annotations

import json
import threading
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from alpaca.data.enums import Adjustment, DataFeed

from tradingx.alerts import build_gate_decision_alert
from tradingx.config import TradingConfig
from tradingx.controller import (
    build_default_gate_validation_controller,
    build_default_paper_trading_controller,
)
from tradingx.data import build_default_market_data_gateway
from tradingx.persistence import FilesystemArtifactStore
from tradingx.reporting import build_gate_decision_brief
from tradingx.service import PaperTradingService, build_default_paper_service
from tradingx.types import ConfigProposal, WebActionResult, WebServiceState
from tradingx.validation import (
    load_benchmark_close_series,
    write_benchmark_close_series,
)
from tradingx.web.readmodels import LocalWebReadModel


class ServiceBuilderProtocol(Protocol):
    def __call__(self) -> PaperTradingService: ...


class LocalServiceManager:
    def __init__(
        self,
        *,
        config: TradingConfig,
        service_builder: ServiceBuilderProtocol | None = None,
    ) -> None:
        self._config = config
        self._service_builder = service_builder or (
            lambda: build_default_paper_service(config)
        )
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state = WebServiceState(
            status="idle",
            active_symbols=(),
            interval_seconds=config.runtime.service_interval_seconds,
            cycles_completed=0,
            started_at_utc=None,
            last_completed_at_utc=None,
            last_error="",
        )

    def get_state(self) -> WebServiceState:
        with self._lock:
            return self._state

    def start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return WebActionResult(
                    action_id=f"action-{uuid.uuid4()}",
                    action_type="paper_service_start",
                    status="blocked",
                    message="Paper service is already running.",
                    evidence_refs=(),
                )
            self._stop_event.clear()
            self._state = WebServiceState(
                status="running",
                active_symbols=symbols,
                interval_seconds=interval_seconds,
                cycles_completed=self._state.cycles_completed,
                started_at_utc=datetime.now(UTC),
                last_completed_at_utc=self._state.last_completed_at_utc,
                last_error="",
            )
            self._thread = threading.Thread(
                target=self._run_service_loop,
                kwargs={
                    "symbols": symbols,
                    "quantity": quantity,
                    "interval_seconds": interval_seconds,
                    "max_cycles": max_cycles,
                },
                daemon=True,
            )
            self._thread.start()
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="paper_service_start",
            status="accepted",
            message="Paper service started.",
            evidence_refs=(),
        )

    def stop(self) -> WebActionResult:
        self._stop_event.set()
        with self._lock:
            self._state = replace(self._state, status="stopping")
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="paper_service_stop",
            status="accepted",
            message="Paper service stop requested.",
            evidence_refs=(),
        )

    def _run_service_loop(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None,
    ) -> None:
        service = self._service_builder()
        cycles_completed = 0
        try:
            while not self._stop_event.is_set() and (
                max_cycles is None or cycles_completed < max_cycles
            ):
                result = service.run(
                    symbols=symbols,
                    quantity=quantity,
                    interval_seconds=interval_seconds,
                    max_cycles=1,
                )
                cycles_completed += result.cycles_completed
                with self._lock:
                    self._state = replace(
                        self._state,
                        cycles_completed=self._state.cycles_completed + 1,
                        last_completed_at_utc=result.last_cycle.completed_at_utc,
                    )
                if max_cycles is not None and cycles_completed >= max_cycles:
                    break
                if self._stop_event.wait(interval_seconds):
                    break
        except Exception as exc:
            with self._lock:
                self._state = replace(self._state, status="error", last_error=str(exc))
            return
        with self._lock:
            self._state = replace(
                self._state,
                status="stopped" if self._stop_event.is_set() else "idle",
            )


class LocalWebActionRunner:
    def __init__(
        self,
        *,
        config: TradingConfig,
        repo_root: Path,
        service_manager: LocalServiceManager,
    ) -> None:
        self._config = config
        self._repo_root = repo_root
        self._service_manager = service_manager
        self._paper_store = FilesystemArtifactStore(
            self._config.runtime.artifact_root / "paper_loop"
        )
        self._validation_store = FilesystemArtifactStore(
            self._config.runtime.artifact_root / "validation"
        )
        self._operator_platform_root = (
            self._config.runtime.artifact_root / "operator_platform"
        )

    def run_paper_loop(self, *, symbol: str, quantity: str) -> WebActionResult:
        controller = build_default_paper_trading_controller(self._config)
        result = controller.run_trading_cycle(symbol, Decimal(quantity))
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="paper_loop",
            status="completed",
            message=f"Ran a paper trading cycle for {symbol}.",
            evidence_refs=tuple(str(path) for path in result.artifact_paths),
        )

    def run_paper_recover(self, *, symbol: str) -> WebActionResult:
        controller = build_default_paper_trading_controller(self._config)
        result = controller.recover_trading_cycle(symbol)
        evidence_refs: tuple[str, ...] = ()
        if result is not None:
            evidence_refs = tuple(str(path) for path in result.artifact_paths)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="paper_recover",
            status="completed",
            message=f"Recovery check completed for {symbol}.",
            evidence_refs=evidence_refs,
        )

    def start_service(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: str,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult:
        return self._service_manager.start(
            symbols=symbols,
            quantity=Decimal(quantity),
            interval_seconds=interval_seconds,
            max_cycles=max_cycles,
        )

    def stop_service(self) -> WebActionResult:
        return self._service_manager.stop()

    def prepare_benchmark(
        self,
        *,
        symbol: str,
        window_start: str,
        window_end: str,
        feed: str = "iex",
        adjustment: str = "dividend",
    ) -> WebActionResult:
        market_data_gateway = build_default_market_data_gateway(self._config)
        window_start_utc = datetime.fromisoformat(window_start).replace(tzinfo=UTC)
        window_end_utc = datetime.fromisoformat(window_end).replace(tzinfo=UTC)
        series = market_data_gateway.get_daily_close_series(
            symbol,
            start_utc=window_start_utc,
            end_utc=window_end_utc,
            feed=DataFeed(feed.lower()),
            adjustment=Adjustment(adjustment.lower()),
        )
        output_file = (
            self._config.runtime.artifact_root
            / "validation"
            / "benchmarks"
            / (
                f"{symbol.lower()}-"
                f"{window_start_utc.date().isoformat()}-"
                f"{window_end_utc.date().isoformat()}-"
                f"{adjustment}.json"
            )
        )
        write_benchmark_close_series(output_file, series)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="prepare_benchmark",
            status="completed",
            message=f"Prepared benchmark closes for {symbol}.",
            evidence_refs=(str(output_file),),
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
        controller = build_default_gate_validation_controller(
            self._config,
            artifact_root=self._config.runtime.artifact_root / "validation",
        )
        window_start_utc = datetime.fromisoformat(window_start).replace(tzinfo=UTC)
        window_end_utc = datetime.fromisoformat(window_end).replace(tzinfo=UTC)
        benchmark_series = load_benchmark_close_series(Path(benchmark_closes_file))
        result = controller.generate_gate_report(
            gate_id=gate,
            benchmark_closes=benchmark_series.closes,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            universe=universe or self._config.runtime.symbol_universe,
            benchmark_series_is_adjusted=benchmark_series.series_is_adjusted,
        )
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="gate_report",
            status="completed",
            message=f"Generated Gate {gate} report.",
            evidence_refs=tuple(str(path) for path in result.artifact_paths),
        )

    def generate_decision_report(self, *, gate: str | None) -> WebActionResult:
        brief = build_gate_decision_brief(
            validation_store=FilesystemArtifactStore(
                self._config.runtime.artifact_root / "validation"
            ),
            paper_store=FilesystemArtifactStore(
                self._config.runtime.artifact_root / "paper_loop"
            ),
            gate_id=gate,
        )
        alert = build_gate_decision_alert(brief)
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="decision_report",
            status="completed",
            message=alert.summary,
            evidence_refs=brief.evidence_refs,
        )

    def create_config_proposal(
        self,
        *,
        target_area: str,
        proposed_values: dict[str, object],
        rationale: str,
    ) -> ConfigProposal:
        proposal_id = f"proposal-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        proposal_dir = self._repo_root / "config" / "proposals"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        output_path = proposal_dir / f"{proposal_id}.md"
        diff_preview = "\n".join(
            f"+ {key}={value}" for key, value in proposed_values.items()
        )
        output_path.write_text(
            "\n".join(
                [
                    f"# {proposal_id}",
                    "",
                    f"Target area: {target_area}",
                    "",
                    "## Rationale",
                    rationale,
                    "",
                    "## Proposed values",
                    diff_preview,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return ConfigProposal(
            proposal_id=proposal_id,
            target_area=target_area,
            proposed_values=proposed_values,
            diff_preview=diff_preview,
            output_path=output_path,
        )

    def run_session_preopen(self) -> WebActionResult:
        return self._write_daily_digest(session_label="session_preopen")

    def run_session_heartbeat(self) -> WebActionResult:
        return self._write_daily_digest(session_label="session_heartbeat")

    def run_session_close(self) -> WebActionResult:
        return self._write_daily_digest(session_label="session_close")

    def acknowledge_incident(self, *, incident_id: str) -> WebActionResult:
        acknowledgement_dir = self._operator_platform_root / "incident_acknowledgements"
        acknowledgement_dir.mkdir(parents=True, exist_ok=True)
        output_path = acknowledgement_dir / f"{incident_id}.json"
        payload = {
            "incident_id": incident_id,
            "acknowledged_at_utc": datetime.now(UTC).isoformat(),
            "acknowledged_by": "local-operator",
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type="incident_acknowledge",
            status="completed",
            message=f"Acknowledged {incident_id}.",
            evidence_refs=(str(output_path),),
        )

    def _write_daily_digest(self, *, session_label: str) -> WebActionResult:
        daily_digest_dir = self._operator_platform_root / "daily_digests"
        daily_digest_dir.mkdir(parents=True, exist_ok=True)
        generated_at = datetime.now(UTC)
        digest_id = f"digest-{generated_at.strftime('%Y%m%d%H%M%S')}-{session_label}"
        paper_report = self._paper_store.build_operator_evidence_report()
        summary_payload = paper_report.get("summary", {})
        paper_summary = summary_payload if isinstance(summary_payload, dict) else {}
        latest_alerts = self._paper_store.list_artifact_payloads("operator_alerts")[-3:]
        payload = {
            "digest_id": digest_id,
            "generated_at_utc": generated_at.isoformat(),
            "session_label": session_label,
            "service_status": self._service_manager.get_state().status,
            "blocked_trade_count": int(paper_summary.get("blocked_trade_count", 0)),
            "reconciliation_failure_count": int(
                paper_summary.get("reconciliation_failure_count", 0)
            ),
            "latest_positions": list(paper_summary.get("latest_open_positions", ())),
            "top_incidents": [
                f"incident-{payload.get('alert_id', '')}"
                for payload in latest_alerts
                if str(payload.get("alert_id", "")).strip()
            ],
            "recommended_actions": self._recommended_actions(),
            "evidence_refs": self._digest_evidence_refs(),
        }
        output_path = daily_digest_dir / f"{digest_id}.json"
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return WebActionResult(
            action_id=f"action-{uuid.uuid4()}",
            action_type=session_label,
            status="completed",
            message=self._digest_message(session_label),
            evidence_refs=(str(output_path),),
        )

    def _recommended_actions(self) -> list[str]:
        recommendations: list[str] = []
        gate_assessments = self._validation_store.list_artifact_payloads(
            "gate_assessments"
        )
        latest_gate = gate_assessments[-1] if gate_assessments else None
        if latest_gate is not None:
            recommendations.append(str(latest_gate.get("decision_summary", "")))
        service_state = self._service_manager.get_state()
        if service_state.last_error:
            recommendations.append(
                "Review the latest service error before the next cycle."
            )
        if not recommendations:
            recommendations.append(
                "Continue collecting paper evidence and review incidents."
            )
        return recommendations

    def _digest_evidence_refs(self) -> list[str]:
        refs: list[str] = []
        paper_cycles = self._paper_store.list_artifact_payloads("service_cycles")
        if paper_cycles:
            latest_cycle = paper_cycles[-1]
            cycle_id = str(latest_cycle.get("cycle_id", "")).strip()
            if cycle_id:
                refs.append(
                    str(
                        self._config.runtime.artifact_root
                        / "paper_loop"
                        / "service_cycles"
                        / f"{cycle_id}.json"
                    )
                )
        gate_assessments = self._validation_store.list_artifact_payloads(
            "gate_assessments"
        )
        if gate_assessments:
            gate_id = str(gate_assessments[-1].get("gate_id", "")).strip()
            if gate_id:
                refs.append(
                    str(
                        self._config.runtime.artifact_root
                        / "validation"
                        / "gate_assessments"
                        / f"gate-{gate_id}.json"
                    )
                )
        return refs

    def _digest_message(self, session_label: str) -> str:
        messages = {
            "session_preopen": "Pre-open checklist captured.",
            "session_heartbeat": "Heartbeat captured.",
            "session_close": "Session close digest generated.",
        }
        return messages.get(session_label, "Session digest generated.")


def build_default_local_web_components(
    config: TradingConfig,
) -> tuple[LocalWebReadModel, LocalWebActionRunner]:
    repo_root = Path(__file__).resolve().parents[3]
    service_manager = LocalServiceManager(config=config)
    return (
        LocalWebReadModel(
            config=config,
            paper_store=FilesystemArtifactStore(
                config.runtime.artifact_root / "paper_loop"
            ),
            validation_store=FilesystemArtifactStore(
                config.runtime.artifact_root / "validation"
            ),
            docs_root=repo_root / "docs",
            repo_root=repo_root,
            service_manager=service_manager,
        ),
        LocalWebActionRunner(
            config=config,
            repo_root=repo_root,
            service_manager=service_manager,
        ),
    )


__all__ = (
    "LocalServiceManager",
    "LocalWebActionRunner",
    "build_default_local_web_components",
)
