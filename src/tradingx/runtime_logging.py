from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tradingx.config import TradingConfig

if TYPE_CHECKING:
    from tradingx.experiments import MetricVisibilityContext


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


class StructuredRuntimeLogger:
    def __init__(
        self,
        *,
        component: str,
        root_dir: Path,
        max_bytes: int = 100 * 1024 * 1024,
        retention_count: int = 30,
        now_provider: Any | None = None,
    ) -> None:
        self._component = component
        self._root_dir = root_dir
        self._max_bytes = max_bytes
        self._retention_count = retention_count
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        return self._root_dir / f"{self._component}.jsonl"

    def log(
        self,
        *,
        event_type: str,
        severity: str,
        message: str,
        decision_snapshot_id: str,
        cycle_correlation_id: str,
        fields: dict[str, Any] | None = None,
        metric_visibility_context: MetricVisibilityContext | None = None,
    ) -> Path:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        visible_payload: dict[str, object] = {
            "message": message,
            "fields": fields or {},
        }
        if metric_visibility_context is not None:
            from tradingx.experiments import sanitize_metric_payload

            visible_payload = sanitize_metric_payload(
                visible_payload,
                context=metric_visibility_context,
                surface="structured_runtime_log",
            )
        payload = {
            "timestamp_utc": self._now_provider(),
            "component": self._component,
            "event_type": event_type,
            "severity": severity,
            "message": visible_payload.get("message", message),
            "decision_snapshot_id": decision_snapshot_id,
            "cycle_correlation_id": cycle_correlation_id,
            "fields": visible_payload.get("fields", fields or {}),
        }
        for key in (
            "promotion_valid",
            "evidence_class",
            "blocker_codes",
            "metric_visibility_status",
            "metric_visibility_surface",
            "experiment_id",
            "run_id",
            "promotion_decision_scope",
        ):
            if key in visible_payload:
                payload[key] = visible_payload[key]
        encoded = json.dumps(_serialize(payload), sort_keys=True) + "\n"
        self._rotate_if_needed(incoming_bytes=len(encoded.encode("utf-8")))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)
        return self.path

    def _rotate_if_needed(self, *, incoming_bytes: int) -> None:
        if self._retention_count <= 0:
            return
        if (
            self.path.exists()
            and self.path.stat().st_size + incoming_bytes <= self._max_bytes
        ):
            return
        oldest_path = self._rotated_path(self._retention_count)
        if oldest_path.exists():
            oldest_path.unlink()
        for index in range(self._retention_count - 1, 0, -1):
            candidate = self._rotated_path(index)
            if candidate.exists():
                candidate.rename(self._rotated_path(index + 1))
        if self.path.exists():
            self.path.rename(self._rotated_path(1))

    def _rotated_path(self, index: int) -> Path:
        return self._root_dir / f"{self._component}.jsonl.{index}"


def build_default_runtime_logger(
    config: TradingConfig,
    *,
    component: str,
) -> StructuredRuntimeLogger:
    return StructuredRuntimeLogger(
        component=component,
        root_dir=config.runtime.data_root / "logs",
        max_bytes=config.runtime.log_max_bytes,
        retention_count=config.runtime.log_retention_files,
    )


__all__ = (
    "StructuredRuntimeLogger",
    "build_default_runtime_logger",
)
