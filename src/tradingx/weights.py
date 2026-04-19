from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.types import ApprovedWeightSnapshot


class ApprovedWeightSnapshotNotFoundError(FileNotFoundError):
    pass


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


__all__ = (
    "ApprovedWeightSnapshotNotFoundError",
    "ApprovedWeightSnapshotStore",
)
