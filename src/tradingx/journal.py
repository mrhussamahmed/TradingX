from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def build_client_order_id(
    *,
    decision_snapshot_id: str,
    symbol: str,
    side: str,
    intent_seq: int,
) -> str:
    digest = hashlib.sha256(
        f"{decision_snapshot_id}|{symbol}|{side}|{intent_seq}".encode()
    ).hexdigest()
    return digest[:48]


@dataclass(frozen=True)
class OmsJournalEvent:
    event_id: str
    event_type: str
    recorded_at_utc: datetime
    decision_snapshot_id: str
    cycle_correlation_id: str
    client_order_id: str
    broker_order_id: str
    symbol: str
    side: str
    payload: dict[str, Any]


class SqliteOmsJournal:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS oms_journal (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL,
                    decision_snapshot_id TEXT NOT NULL,
                    cycle_correlation_id TEXT NOT NULL,
                    client_order_id TEXT NOT NULL,
                    broker_order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """)

    def append_event(
        self,
        *,
        event_type: str,
        recorded_at_utc: datetime,
        decision_snapshot_id: str,
        cycle_correlation_id: str,
        client_order_id: str,
        broker_order_id: str,
        symbol: str,
        side: str,
        payload: dict[str, Any],
    ) -> OmsJournalEvent:
        recorded = recorded_at_utc.astimezone(UTC).isoformat()
        serialized_payload = _serialize_payload(payload)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO oms_journal (
                    event_type,
                    recorded_at_utc,
                    decision_snapshot_id,
                    cycle_correlation_id,
                    client_order_id,
                    broker_order_id,
                    symbol,
                    side,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    recorded,
                    decision_snapshot_id,
                    cycle_correlation_id,
                    client_order_id,
                    broker_order_id,
                    symbol,
                    side,
                    json.dumps(serialized_payload, sort_keys=True),
                ),
            )
            raw_row_id = cursor.lastrowid
            if raw_row_id is None:
                raise RuntimeError(
                    "SQLite did not return a row id for the journal event."
                )
            row_id = int(raw_row_id)
        return OmsJournalEvent(
            event_id=f"journal-{row_id}",
            event_type=event_type,
            recorded_at_utc=datetime.fromisoformat(recorded),
            decision_snapshot_id=decision_snapshot_id,
            cycle_correlation_id=cycle_correlation_id,
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            symbol=symbol,
            side=side,
            payload=serialized_payload,
        )

    def list_events(self) -> list[OmsJournalEvent]:
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT
                    row_id,
                    event_type,
                    recorded_at_utc,
                    decision_snapshot_id,
                    cycle_correlation_id,
                    client_order_id,
                    broker_order_id,
                    symbol,
                    side,
                    payload_json
                FROM oms_journal
                ORDER BY row_id ASC
                """).fetchall()
        return [self._row_to_event(row) for row in rows]

    def find_latest_by_client_order_id(
        self, client_order_id: str
    ) -> OmsJournalEvent | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    row_id,
                    event_type,
                    recorded_at_utc,
                    decision_snapshot_id,
                    cycle_correlation_id,
                    client_order_id,
                    broker_order_id,
                    symbol,
                    side,
                    payload_json
                FROM oms_journal
                WHERE client_order_id = ?
                ORDER BY row_id DESC
                LIMIT 1
                """,
                (client_order_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_event(row)

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode;").fetchone()
        if row is None:
            raise RuntimeError("Could not read SQLite journal mode.")
        return str(row[0]).lower()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _row_to_event(self, row: sqlite3.Row) -> OmsJournalEvent:
        return OmsJournalEvent(
            event_id=f"journal-{int(row['row_id'])}",
            event_type=str(row["event_type"]),
            recorded_at_utc=datetime.fromisoformat(str(row["recorded_at_utc"])),
            decision_snapshot_id=str(row["decision_snapshot_id"]),
            cycle_correlation_id=str(row["cycle_correlation_id"]),
            client_order_id=str(row["client_order_id"]),
            broker_order_id=str(row["broker_order_id"]),
            symbol=str(row["symbol"]),
            side=str(row["side"]),
            payload=json.loads(str(row["payload_json"])),
        )


def _serialize_payload(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, tuple):
        return [_serialize_payload(item) for item in value]
    if isinstance(value, list):
        return [_serialize_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_payload(item) for key, item in value.items()}
    return value


__all__ = ("OmsJournalEvent", "SqliteOmsJournal", "build_client_order_id")
