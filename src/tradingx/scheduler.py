from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from tradingx.automation import (
    build_default_market_day_automation_runner,
)
from tradingx.config import TradingConfig
from tradingx.data import AlpacaRegularHoursCalendar, RegularSessionWindow
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    MarketAutomationRunResult,
    MarketDayScheduleRecord,
    MarketDaySchedulerRunResult,
    MarketDaySchedulerState,
)


class AutomationRunnerProtocol(Protocol):
    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_heartbeats: int | None,
        stop_event: threading.Event | None = None,
    ) -> MarketAutomationRunResult: ...


class SessionCalendarProtocol(Protocol):
    def get_current_or_next_session(
        self,
        observed_at_utc: datetime,
    ) -> RegularSessionWindow | None: ...


StateCallback = Callable[[MarketDaySchedulerState], None]


@dataclass(frozen=True)
class _SchedulerProgress:
    last_started_at_utc: datetime | None = None
    last_completed_at_utc: datetime | None = None
    active_trading_day: str = ""
    last_error: str = ""


class MarketDayScheduler:
    def __init__(
        self,
        *,
        operator_store: FilesystemArtifactStore,
        automation_runner: AutomationRunnerProtocol,
        session_calendar: SessionCalendarProtocol,
        now_provider: Callable[[], datetime] | None = None,
        sleep_fn: Callable[[int], None] | None = None,
    ) -> None:
        self._operator_store = operator_store
        self._automation_runner = automation_runner
        self._session_calendar = session_calendar
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._sleep_fn = sleep_fn or (lambda seconds: __import__("time").sleep(seconds))

    def run(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        poll_interval_seconds: int,
        max_scheduled_days: int | None,
        stop_event: threading.Event | None = None,
        state_callback: StateCallback | None = None,
    ) -> MarketDaySchedulerRunResult:
        scheduled_days_completed = 0
        latest_schedule_record_path = None
        progress = _SchedulerProgress()

        while (
            max_scheduled_days is None or scheduled_days_completed < max_scheduled_days
        ):
            if stop_event is not None and stop_event.is_set():
                break
            observed_at = self._now_provider()
            session_window = self._session_calendar.get_current_or_next_session(
                observed_at
            )
            if session_window is None:
                self._emit_state(
                    callback=state_callback,
                    status="waiting",
                    poll_interval_seconds=poll_interval_seconds,
                    active_symbols=symbols,
                    next_run_at_utc=None,
                    progress=progress,
                )
                if self._pause(stop_event, poll_interval_seconds):
                    break
                continue

            existing_record = self._latest_schedule_record_for_day(
                session_window.trading_day
            )
            if existing_record is not None:
                next_session = self._session_calendar.get_current_or_next_session(
                    session_window.close_at_utc + timedelta(seconds=1)
                )
                self._emit_state(
                    callback=state_callback,
                    status="waiting",
                    poll_interval_seconds=poll_interval_seconds,
                    active_symbols=symbols,
                    next_run_at_utc=(
                        next_session.open_at_utc if next_session is not None else None
                    ),
                    progress=_SchedulerProgress(
                        last_started_at_utc=existing_record.launched_at_utc,
                        last_completed_at_utc=existing_record.completed_at_utc,
                        active_trading_day=existing_record.trading_day,
                        last_error=progress.last_error,
                    ),
                )
                if self._pause(stop_event, poll_interval_seconds):
                    break
                continue

            if observed_at < session_window.open_at_utc:
                self._emit_state(
                    callback=state_callback,
                    status="waiting",
                    poll_interval_seconds=poll_interval_seconds,
                    active_symbols=symbols,
                    next_run_at_utc=session_window.open_at_utc,
                    progress=progress,
                )
                if self._pause(stop_event, poll_interval_seconds):
                    break
                continue

            launch_started_at = self._now_provider()
            progress = _SchedulerProgress(
                last_started_at_utc=launch_started_at,
                last_completed_at_utc=progress.last_completed_at_utc,
                active_trading_day=session_window.trading_day,
                last_error="",
            )
            self._emit_state(
                callback=state_callback,
                status="running",
                poll_interval_seconds=poll_interval_seconds,
                active_symbols=symbols,
                next_run_at_utc=None,
                progress=progress,
            )
            try:
                market_day_result = self._automation_runner.run_market_day(
                    symbols=symbols,
                    quantity=quantity,
                    interval_seconds=interval_seconds,
                    max_heartbeats=None,
                    stop_event=stop_event,
                )
            except Exception as exc:
                completed_at = self._now_provider()
                schedule_record = MarketDayScheduleRecord(
                    schedule_id=f"schedule-{uuid.uuid4()}",
                    trading_day=session_window.trading_day,
                    scheduled_open_at_utc=session_window.open_at_utc,
                    launched_at_utc=launch_started_at,
                    completed_at_utc=completed_at,
                    status="failed",
                    automation_run_id="",
                    summary="Scheduled market day failed before completion.",
                    evidence_refs=(),
                )
                latest_schedule_record_path = (
                    self._operator_store.write_market_day_schedule_record(
                        schedule_record
                    )
                )
                progress = _SchedulerProgress(
                    last_started_at_utc=launch_started_at,
                    last_completed_at_utc=completed_at,
                    active_trading_day=session_window.trading_day,
                    last_error=str(exc),
                )
                self._emit_state(
                    callback=state_callback,
                    status="error",
                    poll_interval_seconds=poll_interval_seconds,
                    active_symbols=symbols,
                    next_run_at_utc=None,
                    progress=progress,
                )
                return MarketDaySchedulerRunResult(
                    scheduled_days_completed=scheduled_days_completed,
                    latest_schedule_record_path=latest_schedule_record_path,
                )

            completed_at = self._now_provider()
            schedule_record = MarketDayScheduleRecord(
                schedule_id=f"schedule-{uuid.uuid4()}",
                trading_day=session_window.trading_day,
                scheduled_open_at_utc=session_window.open_at_utc,
                launched_at_utc=launch_started_at,
                completed_at_utc=completed_at,
                status=market_day_result.run_record.status,
                automation_run_id=market_day_result.run_record.run_id,
                summary=market_day_result.run_record.summary,
                evidence_refs=(
                    str(market_day_result.run_record_path),
                    *market_day_result.run_record.evidence_refs,
                ),
            )
            latest_schedule_record_path = (
                self._operator_store.write_market_day_schedule_record(schedule_record)
            )
            scheduled_days_completed += 1
            progress = _SchedulerProgress(
                last_started_at_utc=launch_started_at,
                last_completed_at_utc=completed_at,
                active_trading_day=session_window.trading_day,
                last_error="",
            )

            next_session = self._session_calendar.get_current_or_next_session(
                session_window.close_at_utc + timedelta(seconds=1)
            )
            next_run_at_utc = (
                next_session.open_at_utc if next_session is not None else None
            )
            final_status = (
                "idle"
                if max_scheduled_days is not None
                and scheduled_days_completed >= max_scheduled_days
                else "waiting"
            )
            self._emit_state(
                callback=state_callback,
                status=final_status,
                poll_interval_seconds=poll_interval_seconds,
                active_symbols=symbols,
                next_run_at_utc=next_run_at_utc,
                progress=progress,
            )

            if (
                max_scheduled_days is not None
                and scheduled_days_completed >= max_scheduled_days
            ):
                break

        return MarketDaySchedulerRunResult(
            scheduled_days_completed=scheduled_days_completed,
            latest_schedule_record_path=latest_schedule_record_path,
        )

    def _latest_schedule_record_for_day(
        self,
        trading_day: str,
    ) -> MarketDayScheduleRecord | None:
        payloads = [
            payload
            for payload in self._operator_store.list_artifact_payloads(
                "market_day_schedules"
            )
            if str(payload.get("trading_day", "")) == trading_day
        ]
        if not payloads:
            return None
        payload = max(payloads, key=lambda item: str(item.get("launched_at_utc", "")))
        completed_raw = payload.get("completed_at_utc")
        return MarketDayScheduleRecord(
            schedule_id=str(payload.get("schedule_id", "")),
            trading_day=str(payload.get("trading_day", "")),
            scheduled_open_at_utc=datetime.fromisoformat(
                str(payload.get("scheduled_open_at_utc", "1970-01-01T00:00:00+00:00"))
            ),
            launched_at_utc=datetime.fromisoformat(
                str(payload.get("launched_at_utc", "1970-01-01T00:00:00+00:00"))
            ),
            completed_at_utc=(
                datetime.fromisoformat(str(completed_raw)) if completed_raw else None
            ),
            status=str(payload.get("status", "")),
            automation_run_id=str(payload.get("automation_run_id", "")),
            summary=str(payload.get("summary", "")),
            evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", [])),
        )

    def _emit_state(
        self,
        *,
        callback: StateCallback | None,
        status: str,
        poll_interval_seconds: int,
        active_symbols: tuple[str, ...],
        next_run_at_utc: datetime | None,
        progress: _SchedulerProgress,
    ) -> None:
        if callback is None:
            return
        callback(
            MarketDaySchedulerState(
                status=status,
                poll_interval_seconds=poll_interval_seconds,
                active_symbols=active_symbols,
                next_run_at_utc=next_run_at_utc,
                last_started_at_utc=progress.last_started_at_utc,
                last_completed_at_utc=progress.last_completed_at_utc,
                active_trading_day=progress.active_trading_day,
                last_error=progress.last_error,
            )
        )

    def _pause(
        self,
        stop_event: threading.Event | None,
        poll_interval_seconds: int,
    ) -> bool:
        if stop_event is not None:
            return stop_event.wait(poll_interval_seconds)
        self._sleep_fn(poll_interval_seconds)
        return False


def build_default_market_day_scheduler(config: TradingConfig) -> MarketDayScheduler:
    return MarketDayScheduler(
        operator_store=FilesystemArtifactStore(
            config.runtime.artifact_root / "operator_platform"
        ),
        automation_runner=build_default_market_day_automation_runner(config),
        session_calendar=AlpacaRegularHoursCalendar(),
    )


__all__ = ("MarketDayScheduler", "build_default_market_day_scheduler")
