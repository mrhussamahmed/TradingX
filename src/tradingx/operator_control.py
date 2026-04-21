from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from tradingx.journal import SqliteOmsJournal
from tradingx.persistence import FilesystemArtifactStore
from tradingx.snapshots import ContentAddressedSnapshotStore


@dataclass(frozen=True)
class OperatorControlState:
    halt_requested: bool
    kill_requested: bool
    clearance_requested: bool
    updated_at_utc: datetime
    last_command: str


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


class OperatorControlStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._state_path = self._root_dir / "state.json"
        self._offset_path = self._root_dir / "telegram_offset.json"

    def read_state(self) -> OperatorControlState:
        payload = self._read_state_payload()
        updated_raw = str(payload.get("updated_at_utc", "1970-01-01T00:00:00+00:00"))
        return OperatorControlState(
            halt_requested=self._marker_path("halt_request").exists(),
            kill_requested=self._marker_path("kill_flag").exists(),
            clearance_requested=self._marker_path("clearance_request").exists(),
            updated_at_utc=datetime.fromisoformat(updated_raw),
            last_command=str(payload.get("last_command", "")),
        )

    def request_halt(self, *, now: datetime) -> OperatorControlState:
        self._touch_marker("halt_request", now=now)
        return self._write_state(now=now, last_command="halt")

    def request_kill(self, *, now: datetime) -> OperatorControlState:
        self._touch_marker("kill_flag", now=now)
        return self._write_state(now=now, last_command="kill")

    def request_clearance(self, *, now: datetime) -> OperatorControlState:
        self._touch_marker("clearance_request", now=now)
        return self._write_state(now=now, last_command="clearance")

    def request_resume(self, *, now: datetime) -> OperatorControlState:
        self._remove_marker("halt_request")
        self._remove_marker("kill_flag")
        self._touch_marker("clearance_request", now=now)
        return self._write_state(now=now, last_command="resume")

    def clear_clearance_request(self, *, now: datetime) -> OperatorControlState:
        self._remove_marker("clearance_request")
        return self._write_state(now=now, last_command="clearance_cleared")

    def recalibrate_drift_reference(
        self,
        *,
        snapshot_id: str,
        now: datetime,
    ) -> OperatorControlState:
        state = self._write_state(
            now=now,
            last_command="drift_reference_recalibrated",
        )
        marker = self._root_dir / "drift_reference_recalibration.json"
        marker.write_text(
            json.dumps(
                {
                    "snapshot_id": snapshot_id,
                    "at_utc": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return state

    def halt_sleeve(self, *, sleeve_id: str, reason: str) -> None:
        path = self._sleeve_halt_path(sleeve_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sleeve_id": sleeve_id,
            "halted": True,
            "reason": reason,
            "at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def resume_sleeve(self, *, sleeve_id: str) -> None:
        path = self._sleeve_halt_path(sleeve_id)
        if path.exists():
            path.unlink()

    def is_sleeve_halted(self, *, sleeve_id: str) -> bool:
        record = self.get_sleeve_halt_record(sleeve_id=sleeve_id)
        if record is None:
            return False
        return bool(record.get("halted", False))

    def is_halted(self, *, sleeve_id: str) -> bool:
        return self.is_sleeve_halted(sleeve_id=sleeve_id)

    def get_sleeve_halt_record(self, *, sleeve_id: str) -> dict[str, Any] | None:
        path = self._sleeve_halt_path(sleeve_id)
        if not path.exists():
            return None
        try:
            return cast(
                dict[str, Any],
                json.loads(path.read_text(encoding="utf-8")),
            )
        except (OSError, json.JSONDecodeError):
            return None

    def read_telegram_offset(self) -> int | None:
        if not self._offset_path.exists():
            return None
        payload = json.loads(self._offset_path.read_text(encoding="utf-8"))
        offset = payload.get("offset")
        return None if offset is None else int(offset)

    def write_telegram_offset(self, offset: int) -> None:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._offset_path.write_text(
            json.dumps({"offset": offset}, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _touch_marker(self, name: str, *, now: datetime) -> None:
        path = self._marker_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(now.astimezone(UTC).isoformat() + "\n", encoding="utf-8")

    def _remove_marker(self, name: str) -> None:
        path = self._marker_path(name)
        if path.exists():
            path.unlink()

    def _marker_path(self, name: str) -> Path:
        return self._root_dir / name

    def _sleeve_halt_path(self, sleeve_id: str) -> Path:
        return self._root_dir / "sleeve_halts" / f"{sleeve_id}.json"

    def _read_state_payload(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {
                "updated_at_utc": datetime(1970, 1, 1, tzinfo=UTC).isoformat(),
                "last_command": "",
            }
        return cast(
            dict[str, Any],
            json.loads(self._state_path.read_text(encoding="utf-8")),
        )

    def _write_state(
        self,
        *,
        now: datetime,
        last_command: str,
    ) -> OperatorControlState:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        state = OperatorControlState(
            halt_requested=self._marker_path("halt_request").exists(),
            kill_requested=self._marker_path("kill_flag").exists(),
            clearance_requested=self._marker_path("clearance_request").exists(),
            updated_at_utc=now.astimezone(UTC),
            last_command=last_command,
        )
        self._state_path.write_text(
            json.dumps(_serialize(asdict(state)), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return state


def build_today_summary(
    *,
    session_date: date,
    paper_store: FilesystemArtifactStore,
    snapshot_store: ContentAddressedSnapshotStore,
    journal: SqliteOmsJournal,
) -> dict[str, Any]:
    session_key = session_date.isoformat()
    cycle_payloads = [
        payload
        for payload in paper_store.list_artifact_payloads("service_cycles")
        if str(payload.get("started_at_utc", "")).startswith(session_key)
    ]
    snapshot_payloads = [
        payload
        for payload in snapshot_store.list_decision_snapshot_payloads()
        if str(payload.get("timestamp_utc", "")).startswith(session_key)
    ]
    journal_rows = [
        row
        for row in journal.list_events()
        if row.recorded_at_utc.astimezone(UTC).date() == session_date
    ]
    blocked_reason_counts: dict[str, int] = {}
    for payload in snapshot_payloads:
        for candidate in payload.get("candidate_intents", []):
            reason = str(candidate.get("terminal_reason", ""))
            if reason in {"selected", "", "baseline_long_entry"}:
                continue
            blocked_reason_counts[reason] = blocked_reason_counts.get(reason, 0) + 1
    summary = {
        "session_date": session_key,
        "cycle_count": len(cycle_payloads),
        "decision_snapshot_count": len(snapshot_payloads),
        "journal_event_count": len(journal_rows),
        "blocked_reason_counts": blocked_reason_counts,
        "anomalies": {
            "cycle_statuses": [
                str(payload.get("cycle_status", "")) for payload in cycle_payloads
            ],
        },
    }
    return cast(dict[str, Any], summary)


__all__ = (
    "OperatorControlState",
    "OperatorControlStore",
    "build_today_summary",
)
