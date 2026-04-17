from __future__ import annotations

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
