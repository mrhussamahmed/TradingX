from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    AlertDrillRecord,
    ClosedTradeRecord,
    EvaluationEvidencePack,
    ExecutionLifecycleRecord,
    RecoveryDrillRecord,
    ReplaySlippageSummary,
)


def _write_execution_pair(
    store: FilesystemArtifactStore,
    *,
    index: int,
    opened_at: datetime,
    closed_at: datetime,
    pnl: Decimal,
) -> None:
    entry_fill = Decimal("500.00") + Decimal(index)
    exit_fill = entry_fill + pnl
    store.write_execution_lifecycle_record(
        execution=ExecutionLifecycleRecord(
            execution_id=f"execution-entry-{index}",
            intent_id=f"intent-entry-{index}",
            symbol="SPY",
            side="buy",
            reason_code="baseline_long_entry",
            reference_price=entry_fill - Decimal("0.25"),
            fill_price=entry_fill,
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("5"),
            submitted_at_utc=opened_at,
            filled_at_utc=opened_at,
            recovered=False,
        )
    )
    store.write_execution_lifecycle_record(
        execution=ExecutionLifecycleRecord(
            execution_id=f"execution-exit-{index}",
            intent_id=f"intent-exit-{index}",
            symbol="SPY",
            side="sell",
            reason_code="take_profit_exit" if pnl > 0 else "stop_loss_exit",
            reference_price=exit_fill + Decimal("0.25"),
            fill_price=exit_fill,
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("5"),
            submitted_at_utc=closed_at,
            filled_at_utc=closed_at,
            recovered=False,
        )
    )
    store.write_closed_trade_record(
        closed_trade=ClosedTradeRecord(
            trade_id=f"trade-{index}",
            symbol="SPY",
            entry_intent_id=f"intent-entry-{index}",
            exit_intent_id=f"intent-exit-{index}",
            opened_at_utc=opened_at,
            closed_at_utc=closed_at,
            quantity=Decimal("1"),
            entry_price=entry_fill,
            exit_price=exit_fill,
            gross_pnl=pnl,
            return_pct=(pnl / entry_fill),
            outcome="win" if pnl > 0 else "loss",
            holding_period_seconds=int((closed_at - opened_at).total_seconds()),
        )
    )


def test_gate3_readiness_report_rolls_up_trade_and_drill_evidence(tmp_path) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    start = datetime(2025, 10, 1, 14, 30, tzinfo=UTC)

    for index in range(100):
        opened_at = start + timedelta(days=index)
        closed_at = opened_at + timedelta(minutes=30)
        pnl = Decimal("5.00") if index < 60 else Decimal("-2.00")
        _write_execution_pair(
            paper_store,
            index=index,
            opened_at=opened_at,
            closed_at=closed_at,
            pnl=pnl,
        )

    paper_store.write_recovery_drill_record(
        recovery_drill=RecoveryDrillRecord(
            drill_id="recovery-1",
            symbol="SPY",
            started_at_utc=start,
            completed_at_utc=start + timedelta(minutes=5),
            status="completed",
            summary="Recovery succeeded.",
            evidence_refs=("artifacts/paper_loop/recovery_drills/recovery-1.json",),
        )
    )
    paper_store.write_alert_drill_record(
        alert_drill=AlertDrillRecord(
            drill_id="alert-1",
            channel="smtp",
            recorded_at_utc=start,
            status="completed",
            summary="SMTP delivered.",
            evidence_refs=("artifacts/paper_loop/alert_drills/alert-1.json",),
        )
    )
    validation_store.write_evaluation_evidence(
        EvaluationEvidencePack(
            evidence_pack_id="baseline-reference",
            candidate_id="baseline-long-only-v1",
            window_start_utc=start,
            window_end_utc=start + timedelta(days=100),
            benchmark_metrics={"sharpe_ratio": Decimal("1.0")},
            candidate_metrics={
                "sharpe_ratio": Decimal("1.4"),
                "hit_rate": Decimal("0.60"),
            },
            adversarial_checks=("none",),
            recommendation="keep",
            assumptions=("reference expectation for Gate 3",),
        )
    )

    report = build_gate3_readiness_report(
        paper_store=paper_store,
        validation_store=validation_store,
    )
    package = build_gate3_promotion_package(report)

    criterion_statuses = {
        criterion.criterion_id: criterion.status for criterion in report.criteria
    }

    assert report.status == "pending"
    assert report.closed_trade_count == 100
    assert report.calendar_days_observed >= 100
    assert criterion_statuses["duration_or_trade_count"] == "pass"
    assert criterion_statuses["p1_bug_incidents"] == "pass"
    assert criterion_statuses["realized_slippage"] == "pass"
    assert criterion_statuses["hit_rate_alignment"] == "pass"
    assert criterion_statuses["realized_sharpe"] == "pass"
    assert criterion_statuses["recovery_drill"] == "pass"
    assert criterion_statuses["smtp_alert_drill"] == "pass"
    assert criterion_statuses["replay_slippage_divergence"] == "pending"
    assert package.status == "pending"
    assert "replay_slippage_divergence" in package.criteria_statuses


def test_gate3_readiness_report_uses_latest_replay_slippage_summary(tmp_path) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    start = datetime(2026, 4, 18, 8, 0, tzinfo=UTC)

    validation_store.write_replay_slippage_summary(
        ReplaySlippageSummary(
            summary_id="replay-summary-1",
            matched_execution_count=12,
            paper_mean_absolute_slippage_bps=Decimal("5.0"),
            replay_mean_absolute_slippage_bps=Decimal("7.5"),
            divergence_ratio=Decimal("1.5"),
            status="pass",
            details="Replay divergence is within the allowed bound.",
            generated_at_utc=start,
        )
    )

    report = build_gate3_readiness_report(
        paper_store=paper_store,
        validation_store=validation_store,
    )

    criterion_statuses = {
        criterion.criterion_id: criterion.status for criterion in report.criteria
    }
    observed_values = {
        criterion.criterion_id: criterion.observed_value
        for criterion in report.criteria
    }

    assert criterion_statuses["replay_slippage_divergence"] == "pass"
    assert observed_values["replay_slippage_divergence"] == "1.5x"
