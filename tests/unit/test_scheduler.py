from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.data import RegularSessionWindow
from tradingx.persistence import FilesystemArtifactStore
from tradingx.scheduler import MarketDayScheduler
from tradingx.types import (
    MarketAutomationRunRecord,
    MarketAutomationRunResult,
    MarketDayScheduleRecord,
    MarketDaySchedulerState,
)


class FakeAutomationRunner:
    def __init__(self) -> None:
        self.called_with = None

    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_heartbeats: int | None,
        stop_event=None,
    ) -> MarketAutomationRunResult:
        self.called_with = {
            "symbols": symbols,
            "quantity": quantity,
            "interval_seconds": interval_seconds,
            "max_heartbeats": max_heartbeats,
            "stop_event": stop_event,
        }
        return MarketAutomationRunResult(
            run_record=MarketAutomationRunRecord(
                run_id="automation-1",
                started_at_utc=datetime(2026, 4, 18, 13, 0, tzinfo=UTC),
                completed_at_utc=datetime(2026, 4, 18, 13, 20, tzinfo=UTC),
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
            ),
            run_record_path=Path(
                "artifacts/operator_platform/market_automation_runs/automation-1.json"
            ),
            session_paths=(),
            daily_digest_paths=(),
            replay_summary_path=Path(
                "artifacts/validation/replay_slippage_summaries/replay-summary-1.json"
            ),
            gate3_report_path=Path("artifacts/validation/gate3_reports/gate3-1.json"),
            gate3_package_path=Path(
                "artifacts/validation/gate3_packages/gate3-package-1.json"
            ),
        )


class FailingAutomationRunner:
    def run_market_day(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_heartbeats: int | None,
        stop_event=None,
    ) -> MarketAutomationRunResult:
        raise RuntimeError("scheduler-run failed")


class FakeSessionCalendar:
    def __init__(self, windows: tuple[RegularSessionWindow, ...]) -> None:
        self._windows = windows

    def get_current_or_next_session(
        self,
        observed_at_utc: datetime,
    ) -> RegularSessionWindow | None:
        for window in self._windows:
            if observed_at_utc <= window.close_at_utc:
                return window
        return None


class FakeStopEvent:
    def __init__(self, *, wait_result: bool) -> None:
        self._is_set = False
        self._wait_result = wait_result

    def is_set(self) -> bool:
        return self._is_set

    def wait(self, timeout: int | float | None = None) -> bool:
        self._is_set = self._wait_result
        return self._wait_result


def _make_now_provider(*values: datetime):
    queue = list(values)
    last = values[-1]

    def now_provider() -> datetime:
        nonlocal last
        if queue:
            last = queue.pop(0)
        return last

    return now_provider


def test_scheduler_launches_market_day_during_active_session(tmp_path) -> None:
    operator_store = FilesystemArtifactStore(tmp_path / "operator_platform")
    session_window = RegularSessionWindow(
        trading_day="2026-04-18",
        open_at_utc=datetime(2026, 4, 18, 13, 30, tzinfo=UTC),
        close_at_utc=datetime(2026, 4, 18, 20, 0, tzinfo=UTC),
    )
    automation_runner = FakeAutomationRunner()
    states: list[MarketDaySchedulerState] = []
    scheduler = MarketDayScheduler(
        operator_store=operator_store,
        automation_runner=automation_runner,
        session_calendar=FakeSessionCalendar((session_window,)),
        now_provider=_make_now_provider(
            datetime(2026, 4, 18, 14, 0, tzinfo=UTC),
            datetime(2026, 4, 18, 14, 0, 5, tzinfo=UTC),
            datetime(2026, 4, 18, 14, 30, tzinfo=UTC),
        ),
    )

    result = scheduler.run(
        symbols=("SPY", "QQQ"),
        quantity=Decimal("1"),
        interval_seconds=300,
        poll_interval_seconds=60,
        max_scheduled_days=1,
        state_callback=states.append,
    )

    assert result.scheduled_days_completed == 1
    assert result.latest_schedule_record_path is not None
    assert automation_runner.called_with == {
        "symbols": ("SPY", "QQQ"),
        "quantity": Decimal("1"),
        "interval_seconds": 300,
        "max_heartbeats": None,
        "stop_event": None,
    }
    assert [state.status for state in states] == ["running", "idle"]

    payloads = operator_store.list_artifact_payloads("market_day_schedules")
    assert len(payloads) == 1
    assert payloads[0]["trading_day"] == "2026-04-18"
    assert payloads[0]["status"] == "completed"
    assert payloads[0]["automation_run_id"] == "automation-1"


def test_scheduler_skips_duplicate_launch_for_same_trading_day(tmp_path) -> None:
    operator_store = FilesystemArtifactStore(tmp_path / "operator_platform")
    current_session = RegularSessionWindow(
        trading_day="2026-04-18",
        open_at_utc=datetime(2026, 4, 18, 13, 30, tzinfo=UTC),
        close_at_utc=datetime(2026, 4, 18, 20, 0, tzinfo=UTC),
    )
    next_session = RegularSessionWindow(
        trading_day="2026-04-20",
        open_at_utc=datetime(2026, 4, 20, 13, 30, tzinfo=UTC),
        close_at_utc=datetime(2026, 4, 20, 20, 0, tzinfo=UTC),
    )
    operator_store.write_market_day_schedule_record(
        MarketDayScheduleRecord(
            schedule_id="schedule-existing",
            trading_day="2026-04-18",
            scheduled_open_at_utc=current_session.open_at_utc,
            launched_at_utc=datetime(2026, 4, 18, 13, 31, tzinfo=UTC),
            completed_at_utc=datetime(2026, 4, 18, 13, 50, tzinfo=UTC),
            status="completed",
            automation_run_id="automation-existing",
            summary="Existing scheduled automation.",
            evidence_refs=(
                "artifacts/operator_platform/market_day_schedules/existing.json",
            ),
        )
    )
    automation_runner = FakeAutomationRunner()
    states: list[MarketDaySchedulerState] = []
    scheduler = MarketDayScheduler(
        operator_store=operator_store,
        automation_runner=automation_runner,
        session_calendar=FakeSessionCalendar((current_session, next_session)),
        now_provider=_make_now_provider(datetime(2026, 4, 18, 15, 0, tzinfo=UTC)),
    )

    result = scheduler.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        poll_interval_seconds=60,
        max_scheduled_days=None,
        stop_event=FakeStopEvent(wait_result=True),
        state_callback=states.append,
    )

    assert result.scheduled_days_completed == 0
    assert automation_runner.called_with is None
    assert len(states) == 1
    assert states[0].status == "waiting"
    assert states[0].next_run_at_utc == next_session.open_at_utc
    assert states[0].active_trading_day == "2026-04-18"


def test_scheduler_persists_failed_schedule_and_returns_error_state(tmp_path) -> None:
    operator_store = FilesystemArtifactStore(tmp_path / "operator_platform")
    session_window = RegularSessionWindow(
        trading_day="2026-04-18",
        open_at_utc=datetime(2026, 4, 18, 13, 30, tzinfo=UTC),
        close_at_utc=datetime(2026, 4, 18, 20, 0, tzinfo=UTC),
    )
    states: list[MarketDaySchedulerState] = []
    scheduler = MarketDayScheduler(
        operator_store=operator_store,
        automation_runner=FailingAutomationRunner(),
        session_calendar=FakeSessionCalendar((session_window,)),
        now_provider=_make_now_provider(
            datetime(2026, 4, 18, 14, 0, tzinfo=UTC),
            datetime(2026, 4, 18, 14, 0, 2, tzinfo=UTC),
            datetime(2026, 4, 18, 14, 0, 4, tzinfo=UTC),
        ),
    )

    result = scheduler.run(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        poll_interval_seconds=60,
        max_scheduled_days=1,
        state_callback=states.append,
    )

    assert result.scheduled_days_completed == 0
    assert result.latest_schedule_record_path is not None
    assert [state.status for state in states] == ["running", "error"]
    assert states[-1].last_error == "scheduler-run failed"

    payloads = operator_store.list_artifact_payloads("market_day_schedules")
    assert len(payloads) == 1
    assert payloads[0]["status"] == "failed"
    assert payloads[0]["automation_run_id"] == ""
    assert payloads[0]["summary"] == "Scheduled market day failed before completion."
