from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tradingx.types import ApprovedWeightSnapshot


class ApprovedWeightSnapshotNotFoundError(FileNotFoundError):
    pass


def default_approved_weight_snapshot_root() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "strategy" / "weights"


class ApprovedWeightSnapshotStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def load_by_strategy_id(self, strategy_id: str) -> ApprovedWeightSnapshot:
        path = self._root_dir / f"{strategy_id}.yaml"
        if not path.exists():
            raise ApprovedWeightSnapshotNotFoundError(
                f"No approved weight snapshot exists for strategy '{strategy_id}'."
            )

        payload = self._parse_yaml(path)
        weights_payload = payload.get("weights", {})
        if not isinstance(weights_payload, dict):
            raise ValueError(f"weights section must be a mapping in {path}")

        generated_at_utc = datetime.fromisoformat(str(payload["generated_at_utc"]))
        if generated_at_utc.tzinfo is None:
            raise ValueError(f"generated_at_utc must be timezone-aware in {path}")

        return approved_weight_snapshot_from_payload(
            {
                "snapshot_id": payload["snapshot_id"],
                "strategy_id": payload["strategy_id"],
                "status": payload["status"],
                "generated_at_utc": generated_at_utc.astimezone(UTC),
                "minimum_supporting_trades": payload["minimum_supporting_trades"],
                "weights": weights_payload,
            }
        )

    def _parse_yaml(self, path: Path) -> dict[str, object]:
        result: dict[str, object] = {}
        current_section: str | None = None
        current_mapping: dict[str, object] | None = None

        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not raw_line.startswith(" "):
                if not line.endswith(":"):
                    key, value = self._split_key_value(line, path)
                    result[key] = value
                    current_section = None
                    current_mapping = None
                    continue
                current_section = stripped[:-1]
                current_mapping = {}
                result[current_section] = current_mapping
                continue
            if current_section is None or current_mapping is None:
                raise ValueError(f"Unexpected indented line in {path}: {raw_line}")
            key, value = self._split_key_value(stripped, path)
            current_mapping[key] = value

        return result

    def _split_key_value(self, line: str, path: Path) -> tuple[str, str]:
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"Malformed YAML line in {path}: {line}")
        return key.strip(), value.strip()


def approved_weight_snapshot_from_payload(
    payload: Mapping[str, Any],
) -> ApprovedWeightSnapshot:
    generated_at_utc = payload["generated_at_utc"]
    if not isinstance(generated_at_utc, datetime):
        generated_at_utc = datetime.fromisoformat(str(generated_at_utc))
    if generated_at_utc.tzinfo is None:
        raise ValueError("generated_at_utc must be timezone-aware.")

    weights_payload = payload["weights"]
    if not isinstance(weights_payload, Mapping):
        raise ValueError("weights section must be a mapping.")

    return ApprovedWeightSnapshot(
        snapshot_id=str(payload["snapshot_id"]),
        strategy_id=str(payload["strategy_id"]),
        status=str(payload["status"]),
        generated_at_utc=generated_at_utc.astimezone(UTC),
        minimum_supporting_trades=int(str(payload["minimum_supporting_trades"])),
        weights={
            str(key): Decimal(str(value)) for key, value in weights_payload.items()
        },
    )


__all__ = (
    "approved_weight_snapshot_from_payload",
    "ApprovedWeightSnapshotNotFoundError",
    "ApprovedWeightSnapshotStore",
    "default_approved_weight_snapshot_root",
)
