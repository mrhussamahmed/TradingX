"""Backtest reference return artifacts under the runtime tree."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path


def artifact_path(*, artifact_root: Path, sleeve_id: str) -> Path:
    return artifact_root / "drift" / "backtest_reference_returns" / f"{sleeve_id}.json"


def write_backtest_reference_returns(
    *,
    artifact_root: Path,
    sleeve_id: str,
    returns: tuple[Decimal, ...],
) -> Path:
    path = artifact_path(artifact_root=artifact_root, sleeve_id=sleeve_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sleeve_id": sleeve_id,
        "returns": [str(value) for value in returns],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_backtest_reference_returns(
    *,
    artifact_root: Path,
    sleeve_id: str,
) -> tuple[Decimal, ...]:
    path = artifact_path(artifact_root=artifact_root, sleeve_id=sleeve_id)
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(Decimal(str(value)) for value in payload.get("returns", ()))


__all__ = (
    "artifact_path",
    "load_backtest_reference_returns",
    "write_backtest_reference_returns",
)
