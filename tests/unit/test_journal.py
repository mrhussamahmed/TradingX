from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tradingx.journal import SqliteOmsJournal, build_client_order_id


def test_sqlite_oms_journal_uses_wal_mode_and_appends_rows(tmp_path: Path) -> None:
    journal = SqliteOmsJournal(tmp_path / "journal.db")
    journal.append_event(
        event_type="intent",
        recorded_at_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        decision_snapshot_id="decision-1",
        cycle_correlation_id="cycle-1",
        client_order_id="cid-1",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={"intent_seq": 0},
    )
    journal.append_event(
        event_type="submit_attempt",
        recorded_at_utc=datetime(2026, 4, 19, 12, 0, 1, tzinfo=UTC),
        decision_snapshot_id="decision-1",
        cycle_correlation_id="cycle-1",
        client_order_id="cid-1",
        broker_order_id="broker-1",
        symbol="SPY",
        side="buy",
        payload={"intent_seq": 0},
    )

    assert journal.journal_mode() == "wal"
    rows = journal.list_events()
    assert [row.event_type for row in rows] == ["intent", "submit_attempt"]
    assert rows[1].broker_order_id == "broker-1"


def test_sqlite_oms_journal_can_find_latest_event_by_client_order_id(
    tmp_path: Path,
) -> None:
    journal = SqliteOmsJournal(tmp_path / "journal.db")
    journal.append_event(
        event_type="intent",
        recorded_at_utc=datetime(2026, 4, 19, 12, 0, tzinfo=UTC),
        decision_snapshot_id="decision-1",
        cycle_correlation_id="cycle-1",
        client_order_id="cid-1",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={"intent_seq": 0},
    )
    journal.append_event(
        event_type="rejected",
        recorded_at_utc=datetime(2026, 4, 19, 12, 0, 2, tzinfo=UTC),
        decision_snapshot_id="decision-1",
        cycle_correlation_id="cycle-1",
        client_order_id="cid-1",
        broker_order_id="broker-1",
        symbol="SPY",
        side="buy",
        payload={"reason": "insufficient_buying_power"},
    )

    latest = journal.find_latest_by_client_order_id("cid-1")

    assert latest is not None
    assert latest.event_type == "rejected"
    assert latest.payload["reason"] == "insufficient_buying_power"


def test_build_client_order_id_is_stable_and_retry_sensitive() -> None:
    first = build_client_order_id(
        decision_snapshot_id="decision-1",
        symbol="SPY",
        side="buy",
        intent_seq=0,
    )
    same = build_client_order_id(
        decision_snapshot_id="decision-1",
        symbol="SPY",
        side="buy",
        intent_seq=0,
    )
    retry = build_client_order_id(
        decision_snapshot_id="decision-1",
        symbol="SPY",
        side="buy",
        intent_seq=1,
    )

    assert first == same
    assert retry != first
