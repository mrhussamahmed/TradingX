from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(_serialize(payload), separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class CandidateIntentSnapshot:
    symbol: str
    selected: bool
    terminal_reason: str
    base_score: Decimal
    final_score: Decimal
    eligibility: str
    risk_status: str


@dataclass(frozen=True)
class DecisionSnapshotV1:
    schema_version: int
    timestamp_utc: datetime
    cycle_correlation_id: str
    session_snapshot_id: str
    universe_snapshot_id: str
    policy_snapshot_id: str
    model_snapshot_id: str
    strategy_version: str
    strategy_config_hash: str
    git_sha: str
    dry_run: bool
    market_data_window_hash: str
    feature_snapshot_id: str
    session_start_equity: Decimal
    candidate_intents: tuple[CandidateIntentSnapshot, ...]
    final_action: str
    risk_verdict_id: str
    decision_snapshot_id: str = field(init=False)

    def __post_init__(self) -> None:
        payload = {
            "schema_version": self.schema_version,
            "timestamp_utc": self.timestamp_utc,
            "cycle_correlation_id": self.cycle_correlation_id,
            "session_snapshot_id": self.session_snapshot_id,
            "universe_snapshot_id": self.universe_snapshot_id,
            "policy_snapshot_id": self.policy_snapshot_id,
            "model_snapshot_id": self.model_snapshot_id,
            "strategy_version": self.strategy_version,
            "strategy_config_hash": self.strategy_config_hash,
            "git_sha": self.git_sha,
            "dry_run": self.dry_run,
            "market_data_window_hash": self.market_data_window_hash,
            "feature_snapshot_id": self.feature_snapshot_id,
            "session_start_equity": self.session_start_equity,
            "candidate_intents": self.candidate_intents,
            "final_action": self.final_action,
            "risk_verdict_id": self.risk_verdict_id,
        }
        digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        object.__setattr__(self, "decision_snapshot_id", digest)

    def to_payload(self) -> dict[str, Any]:
        return {
            "decision_snapshot_id": self.decision_snapshot_id,
            "schema_version": self.schema_version,
            "timestamp_utc": self.timestamp_utc,
            "cycle_correlation_id": self.cycle_correlation_id,
            "session_snapshot_id": self.session_snapshot_id,
            "universe_snapshot_id": self.universe_snapshot_id,
            "policy_snapshot_id": self.policy_snapshot_id,
            "model_snapshot_id": self.model_snapshot_id,
            "strategy_version": self.strategy_version,
            "strategy_config_hash": self.strategy_config_hash,
            "git_sha": self.git_sha,
            "dry_run": self.dry_run,
            "market_data_window_hash": self.market_data_window_hash,
            "feature_snapshot_id": self.feature_snapshot_id,
            "session_start_equity": self.session_start_equity,
            "candidate_intents": self.candidate_intents,
            "final_action": self.final_action,
            "risk_verdict_id": self.risk_verdict_id,
        }


class ContentAddressedSnapshotStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def write_decision_snapshot(self, snapshot: DecisionSnapshotV1) -> Path:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        path = self._root_dir / f"{snapshot.decision_snapshot_id}.json"
        if not path.exists():
            _write_text_atomically(
                path,
                json.dumps(
                    _serialize(snapshot.to_payload()),
                    indent=2,
                    sort_keys=True,
                ),
            )
        return path

    def list_decision_snapshot_payloads(self) -> list[dict[str, Any]]:
        if not self._root_dir.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self._root_dir.glob("*.json"))
        ]


def _write_text_atomically(path: Path, payload: str) -> None:
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


__all__ = (
    "CandidateIntentSnapshot",
    "ContentAddressedSnapshotStore",
    "DecisionSnapshotV1",
)
