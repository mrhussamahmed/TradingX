from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.policy import (
    EntryPolicyContext,
    ExecutionPolicyEngine,
    PolicySnapshotStore,
    build_week1_policy_snapshot,
)


def test_week1_policy_snapshot_has_locked_defaults(tmp_path: Path) -> None:
    snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=tmp_path,
        git_sha="abc1234",
        dry_run=True,
    )

    assert snapshot.schema_version == 1
    assert snapshot.dry_run is True
    assert snapshot.universe == ("SPY",)
    assert snapshot.max_new_entries_per_day == 3
    assert snapshot.max_concurrent_positions == 2
    assert snapshot.max_entries_per_symbol_per_day == 1
    assert snapshot.per_position_dollar_cap == Decimal("500")
    assert snapshot.total_deployed_cap_fraction == Decimal("0.30")
    assert snapshot.daily_drawdown_halt_fraction == Decimal("0.005")
    assert snapshot.quote_absolute_spread_cap == Decimal("0.05")
    assert snapshot.quote_relative_spread_bps_cap == Decimal("5")
    assert snapshot.quote_staleness_seconds == 3
    assert snapshot.data_stall_seconds == 30
    assert snapshot.broker_failure_threshold == 2
    assert snapshot.broker_staleness_seconds == 60
    assert snapshot.entry_marketable_limit_bps == Decimal("10")
    assert snapshot.exit_marketable_limit_bps == Decimal("10")
    assert tuple(step.stage for step in snapshot.close_ladder) == (
        "halt_entries",
        "flatten_marketable_limit",
        "flatten_ioc",
        "flatten_market",
        "critical_incident",
    )


def test_policy_snapshot_store_writes_yaml_with_stable_filename(tmp_path: Path) -> None:
    snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=tmp_path,
        git_sha="abc1234",
        dry_run=True,
    )
    store = PolicySnapshotStore(tmp_path / "policy")

    path = store.write(snapshot)

    assert path == (
        tmp_path / "policy" / f"policy_snapshot_{snapshot.snapshot_hash}.yaml"
    )
    payload = path.read_text(encoding="utf-8")
    assert "schema_version: 1" in payload
    assert "max_new_entries_per_day: 3" in payload
    assert "entry_marketable_limit_bps: 10" in payload
    assert "stage: flatten_market" in payload


def test_execution_policy_engine_blocks_entry_after_daily_cap() -> None:
    snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=Path("artifacts"),
        git_sha="abc1234",
        dry_run=True,
    )
    engine = ExecutionPolicyEngine(snapshot)

    decision = engine.evaluate_entry(
        EntryPolicyContext(
            symbol="SPY",
            entries_today=3,
            entries_for_symbol=0,
            concurrent_positions=0,
            exited_symbols=(),
            deployed_capital=Decimal("0"),
            session_start_equity=Decimal("100000"),
            current_mark_equity=Decimal("100000"),
            minutes_to_close=120,
            quote_spread=Decimal("0.01"),
            quote_spread_bps=Decimal("1"),
            quote_age_seconds=1,
            regular_hours=True,
            kill_switch_active=False,
        )
    )

    assert decision.allowed is False
    assert decision.reason_code == "daily_entry_cap_reached"


def test_execution_policy_engine_enforces_sticky_drawdown_halt() -> None:
    snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=Path("artifacts"),
        git_sha="abc1234",
        dry_run=True,
    )
    engine = ExecutionPolicyEngine(snapshot)

    first = engine.evaluate_entry(
        EntryPolicyContext(
            symbol="SPY",
            entries_today=0,
            entries_for_symbol=0,
            concurrent_positions=0,
            exited_symbols=(),
            deployed_capital=Decimal("0"),
            session_start_equity=Decimal("100000"),
            current_mark_equity=Decimal("99499"),
            minutes_to_close=120,
            quote_spread=Decimal("0.01"),
            quote_spread_bps=Decimal("1"),
            quote_age_seconds=1,
            regular_hours=True,
            kill_switch_active=False,
        )
    )
    second = engine.evaluate_entry(
        EntryPolicyContext(
            symbol="SPY",
            entries_today=0,
            entries_for_symbol=0,
            concurrent_positions=0,
            exited_symbols=(),
            deployed_capital=Decimal("0"),
            session_start_equity=Decimal("100000"),
            current_mark_equity=Decimal("100000"),
            minutes_to_close=120,
            quote_spread=Decimal("0.01"),
            quote_spread_bps=Decimal("1"),
            quote_age_seconds=1,
            regular_hours=True,
            kill_switch_active=False,
        )
    )

    assert first.reason_code == "daily_drawdown_halt"
    assert second.allowed is False
    assert second.reason_code == "daily_drawdown_halt_sticky"


def test_execution_policy_engine_persists_sticky_drawdown_halt_across_instances(
    tmp_path: Path,
) -> None:
    snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=Path("artifacts"),
        git_sha="abc1234",
        dry_run=True,
    )
    state_path = tmp_path / "data" / "control" / "policy_state.json"
    first_engine = ExecutionPolicyEngine(snapshot, state_path=state_path)
    second_engine = ExecutionPolicyEngine(snapshot, state_path=state_path)

    first = first_engine.evaluate_entry(
        EntryPolicyContext(
            symbol="SPY",
            entries_today=0,
            entries_for_symbol=0,
            concurrent_positions=0,
            exited_symbols=(),
            deployed_capital=Decimal("0"),
            session_start_equity=Decimal("100000"),
            current_mark_equity=Decimal("99499"),
            minutes_to_close=120,
            quote_spread=Decimal("0.01"),
            quote_spread_bps=Decimal("1"),
            quote_age_seconds=1,
            regular_hours=True,
            kill_switch_active=False,
        )
    )
    second = second_engine.evaluate_entry(
        EntryPolicyContext(
            symbol="SPY",
            entries_today=0,
            entries_for_symbol=0,
            concurrent_positions=0,
            exited_symbols=(),
            deployed_capital=Decimal("0"),
            session_start_equity=Decimal("100000"),
            current_mark_equity=Decimal("100000"),
            minutes_to_close=120,
            quote_spread=Decimal("0.01"),
            quote_spread_bps=Decimal("1"),
            quote_age_seconds=1,
            regular_hours=True,
            kill_switch_active=False,
        )
    )

    assert first.reason_code == "daily_drawdown_halt"
    assert second.reason_code == "daily_drawdown_halt_sticky"


@pytest.mark.parametrize(
    ("minutes_to_close", "expected_stage"),
    [
        (16, "normal"),
        (15, "halt_entries"),
        (10, "flatten_marketable_limit"),
        (5, "flatten_ioc"),
        (2, "flatten_market"),
        (0, "critical_incident"),
    ],
)
def test_execution_policy_engine_selects_close_ladder_stage(
    minutes_to_close: int,
    expected_stage: str,
) -> None:
    snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
        artifact_root=Path("artifacts"),
        git_sha="abc1234",
        dry_run=True,
    )
    engine = ExecutionPolicyEngine(snapshot)

    assert (
        engine.close_ladder_stage(minutes_to_close=minutes_to_close) == expected_stage
    )
