from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.journal import SqliteOmsJournal
from tradingx.operator_control import OperatorControlStore, build_today_summary
from tradingx.persistence import FilesystemArtifactStore
from tradingx.snapshots import (
    CandidateIntentSnapshot,
    ContentAddressedSnapshotStore,
    DecisionSnapshotV1,
)
from tradingx.types import ServiceCycleSnapshot


def test_operator_control_store_manages_week1_marker_files(tmp_path) -> None:
    store = OperatorControlStore(tmp_path / "data" / "control")
    now = datetime(2026, 4, 20, 12, 0, tzinfo=UTC)

    initial = store.read_state()

    assert initial.halt_requested is False
    assert initial.kill_requested is False
    assert initial.clearance_requested is False

    store.request_halt(now=now)
    halted = store.read_state()
    assert halted.halt_requested is True
    assert (tmp_path / "data" / "control" / "halt_request").exists()

    store.request_kill(now=now)
    killed = store.read_state()
    assert killed.kill_requested is True
    assert (tmp_path / "data" / "control" / "kill_flag").exists()

    store.request_resume(now=now)
    resumed = store.read_state()
    assert resumed.halt_requested is False
    assert resumed.kill_requested is False
    assert resumed.clearance_requested is True
    assert (tmp_path / "data" / "control" / "clearance_request").exists()


def test_build_today_summary_counts_cycles_snapshots_and_journal_rows(tmp_path) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    snapshot_store = ContentAddressedSnapshotStore(tmp_path / "data" / "snapshots")
    journal = SqliteOmsJournal(tmp_path / "data" / "journal.db")
    now = datetime(2026, 4, 20, 14, 0, tzinfo=UTC)

    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=now,
            completed_at_utc=now,
            cycle_status="executed",
            symbols=("SPY",),
            symbol_results=(),
            blocked_trade_count=1,
            reconciliation_failure_count=0,
            open_position_symbols=(),
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            buying_power=Decimal("200000"),
        )
    )
    snapshot_store.write_decision_snapshot(
        DecisionSnapshotV1(
            schema_version=1,
            timestamp_utc=now,
            cycle_correlation_id="cycle-1",
            session_snapshot_id="session-1",
            universe_snapshot_id="universe-1",
            policy_snapshot_id="policy-1",
            model_snapshot_id="model-1",
            strategy_version="1.0.0",
            strategy_config_hash="config-hash",
            git_sha="abc1234",
            dry_run=True,
            market_data_window_hash="window-hash",
            feature_snapshot_id="feature-1",
            session_start_equity=Decimal("100000"),
            candidate_intents=(
                CandidateIntentSnapshot(
                    symbol="SPY",
                    selected=True,
                    terminal_reason="selected",
                    base_score=Decimal("1.0"),
                    final_score=Decimal("0.9"),
                    eligibility="eligible",
                    risk_status="approved",
                ),
            ),
            final_action="buy",
            risk_verdict_id="risk-1",
        )
    )
    journal.append_event(
        event_type="simulated",
        recorded_at_utc=now,
        decision_snapshot_id="decision-1",
        cycle_correlation_id="cycle-1",
        client_order_id="cid-1",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={"reason": "dry_run"},
    )

    summary = build_today_summary(
        session_date=now.date(),
        paper_store=paper_store,
        snapshot_store=snapshot_store,
        journal=journal,
    )

    assert summary["session_date"] == "2026-04-20"
    assert summary["cycle_count"] == 1
    assert summary["decision_snapshot_count"] == 1
    assert summary["journal_event_count"] == 1
    assert summary["blocked_reason_counts"] == {}


def test_sleeve_halt_store_records_and_reads_halt(tmp_path) -> None:
    store = OperatorControlStore(tmp_path / "data" / "control")

    store.halt_sleeve(sleeve_id="trend-following-v1", reason="signal drift")
    assert store.is_sleeve_halted(sleeve_id="trend-following-v1") is True
    assert store.is_sleeve_halted(sleeve_id="vol-target-v1") is False

    store.resume_sleeve(sleeve_id="trend-following-v1")
    assert store.is_sleeve_halted(sleeve_id="trend-following-v1") is False


def test_sleeve_halt_store_persists_reason_and_timestamp(tmp_path) -> None:
    store = OperatorControlStore(tmp_path / "data" / "control")

    store.halt_sleeve(sleeve_id="trend-following-v1", reason="drift alarm")
    record = store.get_sleeve_halt_record(sleeve_id="trend-following-v1")

    assert record is not None
    assert record["reason"] == "drift alarm"
    assert record["halted"] is True
    assert str(record["at_utc"]).endswith("Z")


def test_recalibrate_drift_reference_records_audit_entry(tmp_path) -> None:
    store = OperatorControlStore(tmp_path / "data" / "control")

    result = store.recalibrate_drift_reference(
        snapshot_id="ref-2026-04-21",
        now=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
    )

    assert result.last_command == "drift_reference_recalibrated"
