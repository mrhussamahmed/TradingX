from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, is_dataclass
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
    if isinstance(value, Path):
        return str(value)
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
class CloseLadderStep:
    stage: str
    minutes_to_close: int


@dataclass(frozen=True)
class PolicySnapshot:
    policy_snapshot_id: str
    generated_at_utc: datetime
    schema_version: int
    git_sha: str
    dry_run: bool
    universe: tuple[str, ...]
    max_new_entries_per_day: int
    max_concurrent_positions: int
    max_entries_per_symbol_per_day: int
    reentry_cooldown_scope: str
    per_position_dollar_cap: Decimal
    total_deployed_cap_fraction: Decimal
    daily_drawdown_halt_fraction: Decimal
    quote_absolute_spread_cap: Decimal
    quote_relative_spread_bps_cap: Decimal
    quote_staleness_seconds: int
    data_stall_seconds: int
    broker_failure_threshold: int
    broker_staleness_seconds: int
    entry_marketable_limit_bps: Decimal
    exit_marketable_limit_bps: Decimal
    decision_budget_seconds: int
    cycle_budget_seconds: int
    close_ladder: tuple[CloseLadderStep, ...]
    snapshot_hash: str


@dataclass(frozen=True)
class EntryPolicyContext:
    symbol: str
    entries_today: int
    entries_for_symbol: int
    concurrent_positions: int
    exited_symbols: tuple[str, ...]
    deployed_capital: Decimal
    session_start_equity: Decimal
    current_mark_equity: Decimal
    minutes_to_close: int
    quote_spread: Decimal
    quote_spread_bps: Decimal
    quote_age_seconds: int
    regular_hours: bool
    kill_switch_active: bool


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str


def build_week1_policy_snapshot(
    *,
    generated_at_utc: datetime,
    artifact_root: Path,
    git_sha: str,
    dry_run: bool,
) -> PolicySnapshot:
    del artifact_root
    close_ladder: tuple[CloseLadderStep, ...] = (
        CloseLadderStep(stage="halt_entries", minutes_to_close=15),
        CloseLadderStep(stage="flatten_marketable_limit", minutes_to_close=10),
        CloseLadderStep(stage="flatten_ioc", minutes_to_close=5),
        CloseLadderStep(stage="flatten_market", minutes_to_close=2),
        CloseLadderStep(stage="critical_incident", minutes_to_close=0),
    )
    payload = {
        "generated_at_utc": generated_at_utc,
        "schema_version": 1,
        "git_sha": git_sha,
        "dry_run": dry_run,
        "universe": ("SPY",),
        "max_new_entries_per_day": 3,
        "max_concurrent_positions": 2,
        "max_entries_per_symbol_per_day": 1,
        "reentry_cooldown_scope": "rest_of_session",
        "per_position_dollar_cap": Decimal("500"),
        "total_deployed_cap_fraction": Decimal("0.30"),
        "daily_drawdown_halt_fraction": Decimal("0.005"),
        "quote_absolute_spread_cap": Decimal("0.05"),
        "quote_relative_spread_bps_cap": Decimal("5"),
        "quote_staleness_seconds": 3,
        "data_stall_seconds": 30,
        "broker_failure_threshold": 2,
        "broker_staleness_seconds": 60,
        "entry_marketable_limit_bps": Decimal("10"),
        "exit_marketable_limit_bps": Decimal("10"),
        "decision_budget_seconds": 5,
        "cycle_budget_seconds": 30,
        "close_ladder": close_ladder,
    }
    snapshot_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return PolicySnapshot(
        policy_snapshot_id=f"policy-{snapshot_hash}",
        generated_at_utc=generated_at_utc,
        schema_version=1,
        git_sha=git_sha,
        dry_run=dry_run,
        universe=("SPY",),
        max_new_entries_per_day=3,
        max_concurrent_positions=2,
        max_entries_per_symbol_per_day=1,
        reentry_cooldown_scope="rest_of_session",
        per_position_dollar_cap=Decimal("500"),
        total_deployed_cap_fraction=Decimal("0.30"),
        daily_drawdown_halt_fraction=Decimal("0.005"),
        quote_absolute_spread_cap=Decimal("0.05"),
        quote_relative_spread_bps_cap=Decimal("5"),
        quote_staleness_seconds=3,
        data_stall_seconds=30,
        broker_failure_threshold=2,
        broker_staleness_seconds=60,
        entry_marketable_limit_bps=Decimal("10"),
        exit_marketable_limit_bps=Decimal("10"),
        decision_budget_seconds=5,
        cycle_budget_seconds=30,
        close_ladder=close_ladder,
        snapshot_hash=snapshot_hash,
    )


class PolicySnapshotStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def write(self, snapshot: PolicySnapshot) -> Path:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        path = self._root_dir / f"policy_snapshot_{snapshot.snapshot_hash}.yaml"
        if not path.exists():
            path.write_text(self._to_yaml(snapshot), encoding="utf-8")
        return path

    def _to_yaml(self, snapshot: PolicySnapshot) -> str:
        lines = [
            f"policy_snapshot_id: {snapshot.policy_snapshot_id}",
            (
                "generated_at_utc: "
                f"{snapshot.generated_at_utc.astimezone(UTC).isoformat()}"
            ),
            f"schema_version: {snapshot.schema_version}",
            f"git_sha: {snapshot.git_sha}",
            f"dry_run: {'true' if snapshot.dry_run else 'false'}",
            "universe:",
        ]
        lines.extend(f"  - {symbol}" for symbol in snapshot.universe)
        scalar_fields = [
            ("max_new_entries_per_day", snapshot.max_new_entries_per_day),
            ("max_concurrent_positions", snapshot.max_concurrent_positions),
            ("max_entries_per_symbol_per_day", snapshot.max_entries_per_symbol_per_day),
            ("reentry_cooldown_scope", snapshot.reentry_cooldown_scope),
            ("per_position_dollar_cap", snapshot.per_position_dollar_cap),
            ("total_deployed_cap_fraction", snapshot.total_deployed_cap_fraction),
            ("daily_drawdown_halt_fraction", snapshot.daily_drawdown_halt_fraction),
            ("quote_absolute_spread_cap", snapshot.quote_absolute_spread_cap),
            ("quote_relative_spread_bps_cap", snapshot.quote_relative_spread_bps_cap),
            ("quote_staleness_seconds", snapshot.quote_staleness_seconds),
            ("data_stall_seconds", snapshot.data_stall_seconds),
            ("broker_failure_threshold", snapshot.broker_failure_threshold),
            ("broker_staleness_seconds", snapshot.broker_staleness_seconds),
            ("entry_marketable_limit_bps", snapshot.entry_marketable_limit_bps),
            ("exit_marketable_limit_bps", snapshot.exit_marketable_limit_bps),
            ("decision_budget_seconds", snapshot.decision_budget_seconds),
            ("cycle_budget_seconds", snapshot.cycle_budget_seconds),
            ("snapshot_hash", snapshot.snapshot_hash),
        ]
        lines.extend(f"{name}: {value}" for name, value in scalar_fields)
        lines.append("close_ladder:")
        for step in snapshot.close_ladder:
            lines.append(f"  - stage: {step.stage}")
            lines.append(f"    minutes_to_close: {step.minutes_to_close}")
        return "\n".join(lines) + "\n"


class ExecutionPolicyEngine:
    def __init__(
        self,
        snapshot: PolicySnapshot,
        *,
        state_path: Path | None = None,
    ) -> None:
        self._snapshot = snapshot
        self._state_path = state_path
        self._sticky_drawdown_halt = self._load_sticky_drawdown_state()

    def evaluate_entry(self, context: EntryPolicyContext) -> PolicyDecision:
        if self._state_path is not None:
            self._sticky_drawdown_halt = (
                self._sticky_drawdown_halt or self._load_sticky_drawdown_state()
            )
        if context.kill_switch_active:
            return PolicyDecision(allowed=False, reason_code="kill_switch_active")
        if not context.regular_hours:
            return PolicyDecision(allowed=False, reason_code="outside_regular_hours")
        if self._sticky_drawdown_halt:
            return PolicyDecision(
                allowed=False,
                reason_code="daily_drawdown_halt_sticky",
            )
        if self._drawdown_triggered(context):
            self._sticky_drawdown_halt = True
            self._persist_sticky_drawdown_state()
            return PolicyDecision(allowed=False, reason_code="daily_drawdown_halt")
        if (
            self.close_ladder_stage(minutes_to_close=context.minutes_to_close)
            != "normal"
        ):
            return PolicyDecision(
                allowed=False,
                reason_code="close_window_entry_blocked",
            )
        if context.quote_age_seconds > self._snapshot.quote_staleness_seconds:
            return PolicyDecision(allowed=False, reason_code="stale_quote")
        if context.quote_spread > self._snapshot.quote_absolute_spread_cap:
            return PolicyDecision(allowed=False, reason_code="spread_absolute_cap")
        if context.quote_spread_bps > self._snapshot.quote_relative_spread_bps_cap:
            return PolicyDecision(allowed=False, reason_code="spread_relative_cap")
        if context.entries_today >= self._snapshot.max_new_entries_per_day:
            return PolicyDecision(allowed=False, reason_code="daily_entry_cap_reached")
        if context.entries_for_symbol >= self._snapshot.max_entries_per_symbol_per_day:
            return PolicyDecision(
                allowed=False,
                reason_code="per_symbol_entry_cap_reached",
            )
        if context.concurrent_positions >= self._snapshot.max_concurrent_positions:
            return PolicyDecision(
                allowed=False,
                reason_code="max_concurrent_positions_reached",
            )
        if context.symbol in context.exited_symbols:
            return PolicyDecision(
                allowed=False,
                reason_code="same_session_reentry_cooldown",
            )
        deployed_limit = (
            context.session_start_equity * self._snapshot.total_deployed_cap_fraction
        )
        if (
            context.deployed_capital + self._snapshot.per_position_dollar_cap
            > deployed_limit
        ):
            return PolicyDecision(
                allowed=False,
                reason_code="total_deployed_cap_reached",
            )
        return PolicyDecision(allowed=True, reason_code="allowed")

    def close_ladder_stage(self, *, minutes_to_close: int) -> str:
        for step in sorted(
            self._snapshot.close_ladder,
            key=lambda item: item.minutes_to_close,
        ):
            if minutes_to_close <= step.minutes_to_close:
                return step.stage
        return "normal"

    def _drawdown_triggered(self, context: EntryPolicyContext) -> bool:
        drawdown = context.session_start_equity - context.current_mark_equity
        threshold = (
            context.session_start_equity * self._snapshot.daily_drawdown_halt_fraction
        )
        return drawdown >= threshold

    def _load_sticky_drawdown_state(self) -> bool:
        if self._state_path is None or not self._state_path.exists():
            return False
        payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        if (
            str(payload.get("policy_snapshot_id", ""))
            != self._snapshot.policy_snapshot_id
        ):
            return False
        return bool(payload.get("sticky_drawdown_halt", False))

    def _persist_sticky_drawdown_state(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_atomically(
            self._state_path,
            json.dumps(
                {
                    "policy_snapshot_id": self._snapshot.policy_snapshot_id,
                    "sticky_drawdown_halt": self._sticky_drawdown_halt,
                    "updated_at_utc": datetime.now(UTC).isoformat(),
                },
                indent=2,
                sort_keys=True,
            ),
        )


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
    "CloseLadderStep",
    "EntryPolicyContext",
    "ExecutionPolicyEngine",
    "PolicyDecision",
    "PolicySnapshot",
    "PolicySnapshotStore",
    "build_week1_policy_snapshot",
)
