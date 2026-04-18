from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.replay_slippage import generate_replay_slippage_evidence
from tradingx.types import ExecutionLifecycleRecord


def test_generate_replay_slippage_evidence_writes_records_and_summary(tmp_path) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    timestamp = datetime(2026, 4, 18, 12, 0, tzinfo=UTC)

    paper_store.write_execution_lifecycle_record(
        ExecutionLifecycleRecord(
            execution_id="execution-1",
            intent_id="intent-1",
            symbol="SPY",
            side="buy",
            reason_code="baseline_long_entry",
            reference_price=Decimal("500.00"),
            fill_price=Decimal("500.25"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("5.0"),
            bid_price=Decimal("499.80"),
            ask_price=Decimal("500.20"),
            average_daily_volume_30d=Decimal("1000000"),
            submitted_at_utc=timestamp,
            filled_at_utc=timestamp,
            recovered=False,
        )
    )

    result = generate_replay_slippage_evidence(
        paper_store=paper_store,
        validation_store=validation_store,
    )

    assert result.summary.matched_execution_count == 1
    assert result.summary.status == "pass"
    assert result.summary.divergence_ratio <= Decimal("2.0")
    assert len(result.record_paths) == 1
    assert result.summary_path.exists()


def test_generate_replay_slippage_evidence_stays_pending_without_context(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    timestamp = datetime(2026, 4, 18, 12, 0, tzinfo=UTC)

    paper_store.write_execution_lifecycle_record(
        ExecutionLifecycleRecord(
            execution_id="execution-1",
            intent_id="intent-1",
            symbol="SPY",
            side="buy",
            reason_code="baseline_long_entry",
            reference_price=Decimal("500.00"),
            fill_price=Decimal("500.25"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("5.0"),
            submitted_at_utc=timestamp,
            filled_at_utc=timestamp,
            recovered=False,
        )
    )

    result = generate_replay_slippage_evidence(
        paper_store=paper_store,
        validation_store=validation_store,
    )

    assert result.summary.status == "pending"
    assert result.summary.matched_execution_count == 0
    assert result.record_paths == ()
