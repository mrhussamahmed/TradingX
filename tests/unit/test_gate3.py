from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.persistence import FilesystemArtifactStore
from tradingx.replay_slippage import generate_replay_slippage_evidence
from tradingx.types import (
    AlertDrillRecord,
    ClosedTradeRecord,
    EvaluationEvidencePack,
    ExecutionLifecycleRecord,
    OperatorAlert,
    RecoveryDrillRecord,
    ReplaySlippageSummary,
    ServiceCycleSnapshot,
    ServiceSymbolResult,
)


def _write_execution_pair(
    store: FilesystemArtifactStore,
    *,
    index: int,
    opened_at: datetime,
    closed_at: datetime,
    pnl: Decimal,
    sleeve_attributions: tuple[tuple[str, Decimal], ...] = (),
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
            sleeve_attributions=sleeve_attributions,
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
            sleeve_attributions=sleeve_attributions,
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
            entry_sleeve_attributions=sleeve_attributions,
            exit_sleeve_attributions=sleeve_attributions,
        )
    )


def test_gate3_readiness_report_uses_governed_two_sleeve_evidence(tmp_path) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    start = datetime(2025, 10, 1, 14, 30, tzinfo=UTC)
    sleeve_attributions = (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )

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
            sleeve_attributions=sleeve_attributions,
        )
    paper_store.write_execution_lifecycle_record(
        execution=ExecutionLifecycleRecord(
            execution_id="reserve-liquidation-1",
            intent_id="reserve-liquidation-1",
            symbol="SPY",
            side="sell",
            reason_code="residual_reserve_liquidation",
            reference_price=Decimal("600.00"),
            fill_price=Decimal("600.00"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("4"),
            submitted_at_utc=start + timedelta(days=101),
            filled_at_utc=start + timedelta(days=101),
            recovered=False,
            sleeve_attributions=(("__residual_reserve__", Decimal("1")),),
        )
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
            evidence_pack_id="trend-reference",
            candidate_id="trend-following-v1",
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
    validation_store.write_evaluation_evidence(
        EvaluationEvidencePack(
            evidence_pack_id="vol-reference",
            candidate_id="vol-target-v1",
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
    slippage_criterion = next(
        criterion
        for criterion in report.criteria
        if criterion.criterion_id == "realized_slippage"
    )
    hit_rate_criterion = next(
        criterion
        for criterion in report.criteria
        if criterion.criterion_id == "hit_rate_alignment"
    )
    sharpe_criterion = next(
        criterion
        for criterion in report.criteria
        if criterion.criterion_id == "realized_sharpe"
    )
    assert "trend-following-v1" in slippage_criterion.observed_value
    assert "vol-target-v1" in slippage_criterion.observed_value
    assert "__residual_reserve__" not in slippage_criterion.observed_value
    assert "notional" in slippage_criterion.details
    assert "trend-following-v1" in hit_rate_criterion.details
    assert "vol-target-v1" in sharpe_criterion.details
    assert "__residual_reserve__" not in hit_rate_criterion.details
    assert "__residual_reserve__" not in sharpe_criterion.details
    assert package.status == "pending"
    assert "replay_slippage_divergence" in package.criteria_statuses


def test_gate3_readiness_report_falls_back_to_legacy_single_strategy_mode(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    start = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)

    for index in range(20):
        opened_at = start + timedelta(days=index)
        closed_at = opened_at + timedelta(minutes=30)
        pnl = Decimal("5.00") if index % 2 == 0 else Decimal("-2.00")
        _write_execution_pair(
            paper_store,
            index=index,
            opened_at=opened_at,
            closed_at=closed_at,
            pnl=pnl,
        )

    validation_store.write_evaluation_evidence(
        EvaluationEvidencePack(
            evidence_pack_id="baseline-reference",
            candidate_id="baseline-long-only-v1",
            window_start_utc=start,
            window_end_utc=start + timedelta(days=20),
            benchmark_metrics={"sharpe_ratio": Decimal("1.0")},
            candidate_metrics={
                "sharpe_ratio": Decimal("0.1"),
                "hit_rate": Decimal("0.50"),
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

    realized_slippage = next(
        criterion
        for criterion in report.criteria
        if criterion.criterion_id == "realized_slippage"
    )
    hit_rate = next(
        criterion
        for criterion in report.criteria
        if criterion.criterion_id == "hit_rate_alignment"
    )

    assert realized_slippage.status == "pass"
    assert realized_slippage.observed_value == "5 bps"
    assert "validation base cost assumption" in realized_slippage.details
    assert hit_rate.status == "pass"
    assert hit_rate.observed_value == "0.5000"
    assert "active strategy" in hit_rate.details


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


def test_gate3_governed_duration_ignores_legacy_pre_sleeve_history(tmp_path) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    start = datetime(2026, 1, 1, 14, 30, tzinfo=UTC)
    sleeve_attributions = (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )

    for index in range(98):
        opened_at = start + timedelta(days=index)
        closed_at = opened_at + timedelta(minutes=30)
        pnl = Decimal("5.00") if index % 2 == 0 else Decimal("-2.00")
        _write_execution_pair(
            paper_store,
            index=index,
            opened_at=opened_at,
            closed_at=closed_at,
            pnl=pnl,
        )

    for index in range(98, 100):
        opened_at = start + timedelta(days=index)
        closed_at = opened_at + timedelta(minutes=30)
        pnl = Decimal("5.00") if index == 98 else Decimal("-2.00")
        _write_execution_pair(
            paper_store,
            index=index,
            opened_at=opened_at,
            closed_at=closed_at,
            pnl=pnl,
            sleeve_attributions=sleeve_attributions,
        )

    for candidate_id in ("trend-following-v1", "vol-target-v1"):
        validation_store.write_evaluation_evidence(
            EvaluationEvidencePack(
                evidence_pack_id=f"{candidate_id}-reference",
                candidate_id=candidate_id,
                window_start_utc=start,
                window_end_utc=start + timedelta(days=100),
                benchmark_metrics={"sharpe_ratio": Decimal("1.0")},
                candidate_metrics={
                    "sharpe_ratio": Decimal("0.10"),
                    "hit_rate": Decimal("0.50"),
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

    duration_criterion = next(
        criterion
        for criterion in report.criteria
        if criterion.criterion_id == "duration_or_trade_count"
    )

    assert report.closed_trade_count == 2
    assert report.calendar_days_observed == 2
    assert duration_criterion.status == "pending"
    assert duration_criterion.observed_value == "2 trades / 2 days"


def test_gate3_governed_duration_uses_first_governed_artifact_timestamp(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    legacy_opened_at = datetime(2026, 1, 1, 14, 30, tzinfo=UTC)
    governed_closed_at = legacy_opened_at + timedelta(days=179, minutes=30)
    sleeve_attributions = (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )

    paper_store.write_closed_trade_record(
        closed_trade=ClosedTradeRecord(
            trade_id="mixed-transition-trade",
            symbol="SPY",
            entry_intent_id="legacy-entry",
            exit_intent_id="governed-exit",
            opened_at_utc=legacy_opened_at,
            closed_at_utc=governed_closed_at,
            quantity=Decimal("1"),
            entry_price=Decimal("500.00"),
            exit_price=Decimal("505.00"),
            gross_pnl=Decimal("5.00"),
            return_pct=Decimal("0.01"),
            outcome="win",
            holding_period_seconds=int(
                (governed_closed_at - legacy_opened_at).total_seconds()
            ),
            exit_sleeve_attributions=sleeve_attributions,
        )
    )
    paper_store.write_execution_lifecycle_record(
        execution=ExecutionLifecycleRecord(
            execution_id="governed-exit-fill",
            intent_id="governed-exit",
            symbol="SPY",
            side="sell",
            reason_code="target_weight_exit",
            reference_price=Decimal("505.25"),
            fill_price=Decimal("505.00"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("5"),
            submitted_at_utc=governed_closed_at,
            filled_at_utc=governed_closed_at,
            recovered=False,
            sleeve_attributions=sleeve_attributions,
        )
    )

    for day_index in range(180):
        cycle_time = legacy_opened_at + timedelta(days=day_index)
        paper_store.write_service_cycle_snapshot(
            ServiceCycleSnapshot(
                cycle_id=f"cycle-{day_index}",
                started_at_utc=cycle_time,
                completed_at_utc=cycle_time,
                cycle_status="completed",
                symbols=("SPY",),
                symbol_results=(
                    ServiceSymbolResult(
                        symbol="SPY",
                        terminal_state="completed",
                        reason_code="cycle_complete",
                        recovered=False,
                    ),
                ),
                blocked_trade_count=0,
                reconciliation_failure_count=0,
                open_position_symbols=(),
                cash=Decimal("10000"),
                equity=Decimal("10000"),
                buying_power=Decimal("20000"),
            )
        )

    for candidate_id in ("trend-following-v1", "vol-target-v1"):
        validation_store.write_evaluation_evidence(
            EvaluationEvidencePack(
                evidence_pack_id=f"{candidate_id}-mixed-transition-reference",
                candidate_id=candidate_id,
                window_start_utc=legacy_opened_at,
                window_end_utc=governed_closed_at,
                benchmark_metrics={"sharpe_ratio": Decimal("1.0")},
                candidate_metrics={
                    "sharpe_ratio": Decimal("0.10"),
                    "hit_rate": Decimal("0.50"),
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

    duration_criterion = next(
        criterion
        for criterion in report.criteria
        if criterion.criterion_id == "duration_or_trade_count"
    )

    assert report.closed_trade_count == 0
    assert report.calendar_days_observed == 0
    assert duration_criterion.status == "pending"
    assert duration_criterion.observed_value == "0 trades / 0 days"


def test_gate3_governed_metrics_reject_exit_only_transition_trades(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    start = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    sleeve_attributions = (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )

    for index in range(100):
        opened_at = start + timedelta(days=index)
        closed_at = opened_at + timedelta(minutes=30)
        paper_store.write_closed_trade_record(
            closed_trade=ClosedTradeRecord(
                trade_id=f"legacy-entry-governed-exit-{index}",
                symbol="SPY",
                entry_intent_id=f"legacy-entry-{index}",
                exit_intent_id=f"governed-exit-{index}",
                opened_at_utc=opened_at,
                closed_at_utc=closed_at,
                quantity=Decimal("1"),
                entry_price=Decimal("500.00"),
                exit_price=Decimal("505.00"),
                gross_pnl=Decimal("5.00"),
                return_pct=Decimal("0.01"),
                outcome="win",
                holding_period_seconds=int((closed_at - opened_at).total_seconds()),
                exit_sleeve_attributions=sleeve_attributions,
            )
        )
        paper_store.write_execution_lifecycle_record(
            execution=ExecutionLifecycleRecord(
                execution_id=f"governed-exit-{index}",
                intent_id=f"governed-exit-{index}",
                symbol="SPY",
                side="sell",
                reason_code="target_weight_exit",
                reference_price=Decimal("505.25"),
                fill_price=Decimal("505.00"),
                filled_qty=Decimal("1"),
                slippage_bps=Decimal("5"),
                submitted_at_utc=closed_at,
                filled_at_utc=closed_at,
                recovered=False,
                sleeve_attributions=sleeve_attributions,
            )
        )

    for candidate_id in ("trend-following-v1", "vol-target-v1"):
        validation_store.write_evaluation_evidence(
            EvaluationEvidencePack(
                evidence_pack_id=f"{candidate_id}-reference",
                candidate_id=candidate_id,
                window_start_utc=start,
                window_end_utc=start + timedelta(days=100),
                benchmark_metrics={"sharpe_ratio": Decimal("1.0")},
                candidate_metrics={
                    "sharpe_ratio": Decimal("0.10"),
                    "hit_rate": Decimal("1.00"),
                },
                adversarial_checks=("none",),
                recommendation="keep",
                assumptions=("reference expectation for Gate 3",),
            )
        )
    paper_store.write_recovery_drill_record(
        recovery_drill=RecoveryDrillRecord(
            drill_id="governed-recovery",
            symbol="SPY",
            started_at_utc=start,
            completed_at_utc=start + timedelta(minutes=5),
            status="completed",
            summary="Recovery succeeded.",
            evidence_refs=("artifacts/paper_loop/recovery_drills/recovery.json",),
        )
    )
    paper_store.write_alert_drill_record(
        alert_drill=AlertDrillRecord(
            drill_id="governed-smtp",
            channel="smtp",
            recorded_at_utc=start,
            status="completed",
            summary="SMTP delivered.",
            evidence_refs=("artifacts/paper_loop/alert_drills/smtp.json",),
        )
    )
    validation_store.write_replay_slippage_summary(
        ReplaySlippageSummary(
            summary_id="governed-replay",
            matched_execution_count=100,
            paper_mean_absolute_slippage_bps=Decimal("5"),
            replay_mean_absolute_slippage_bps=Decimal("5"),
            divergence_ratio=Decimal("1.0"),
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

    assert report.closed_trade_count == 0
    assert criterion_statuses["duration_or_trade_count"] == "pending"
    assert criterion_statuses["hit_rate_alignment"] == "pending"
    assert criterion_statuses["realized_sharpe"] == "pending"
    assert report.status == "pending"


def test_gate3_governed_mode_ignores_stale_operational_evidence(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    stale_at = datetime(2025, 12, 1, 14, 30, tzinfo=UTC)
    governed_start = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    sleeve_attributions = (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )

    for index in range(100):
        opened_at = governed_start + timedelta(days=index)
        closed_at = opened_at + timedelta(minutes=30)
        pnl = Decimal("5.00") if index < 60 else Decimal("-2.00")
        _write_execution_pair(
            paper_store,
            index=index,
            opened_at=opened_at,
            closed_at=closed_at,
            pnl=pnl,
            sleeve_attributions=sleeve_attributions,
        )

    for candidate_id in ("trend-following-v1", "vol-target-v1"):
        validation_store.write_evaluation_evidence(
            EvaluationEvidencePack(
                evidence_pack_id=f"{candidate_id}-reference",
                candidate_id=candidate_id,
                window_start_utc=governed_start,
                window_end_utc=governed_start + timedelta(days=100),
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

    paper_store.write_operator_alert(
        OperatorAlert(
            alert_id="stale-p1-bug",
            severity="critical",
            category="bug",
            summary="Pre-governed P1 bug.",
            evidence_refs=("artifacts/paper_loop/operator_alerts/stale.json",),
            delivery_targets=("local",),
            sent_at_utc=stale_at,
        )
    )
    paper_store.write_recovery_drill_record(
        recovery_drill=RecoveryDrillRecord(
            drill_id="stale-recovery",
            symbol="SPY",
            started_at_utc=stale_at,
            completed_at_utc=stale_at + timedelta(minutes=5),
            status="completed",
            summary="Stale recovery succeeded.",
            evidence_refs=("artifacts/paper_loop/recovery_drills/stale.json",),
        )
    )
    paper_store.write_alert_drill_record(
        alert_drill=AlertDrillRecord(
            drill_id="stale-smtp",
            channel="smtp",
            recorded_at_utc=stale_at,
            status="completed",
            summary="Stale SMTP delivered.",
            evidence_refs=("artifacts/paper_loop/alert_drills/stale.json",),
        )
    )
    validation_store.write_replay_slippage_summary(
        ReplaySlippageSummary(
            summary_id="stale-replay",
            matched_execution_count=100,
            paper_mean_absolute_slippage_bps=Decimal("5"),
            replay_mean_absolute_slippage_bps=Decimal("5"),
            divergence_ratio=Decimal("1.0"),
            status="pass",
            details="Stale replay divergence is within the allowed bound.",
            generated_at_utc=stale_at,
        )
    )

    report = build_gate3_readiness_report(
        paper_store=paper_store,
        validation_store=validation_store,
    )
    criterion_statuses = {
        criterion.criterion_id: criterion.status for criterion in report.criteria
    }

    assert criterion_statuses["p1_bug_incidents"] == "pass"
    assert criterion_statuses["recovery_drill"] == "pending"
    assert criterion_statuses["smtp_alert_drill"] == "pending"
    assert criterion_statuses["replay_slippage_divergence"] == "pending"
    assert report.status == "pending"


def test_gate3_governed_replay_requires_matched_governed_executions(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    legacy_at = datetime(2025, 12, 1, 14, 30, tzinfo=UTC)
    governed_start = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    sleeve_attributions = (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )

    paper_store.write_execution_lifecycle_record(
        execution=ExecutionLifecycleRecord(
            execution_id="legacy-quote-rich-fill",
            intent_id="legacy-intent",
            symbol="SPY",
            side="buy",
            reason_code="legacy_entry",
            reference_price=Decimal("500.00"),
            fill_price=Decimal("500.05"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("1"),
            submitted_at_utc=legacy_at,
            filled_at_utc=legacy_at,
            recovered=False,
            bid_price=Decimal("499.95"),
            ask_price=Decimal("500.05"),
            average_daily_volume_30d=Decimal("100000000"),
        )
    )

    for index in range(100):
        opened_at = governed_start + timedelta(days=index)
        closed_at = opened_at + timedelta(minutes=30)
        pnl = Decimal("5.00") if index < 60 else Decimal("-2.00")
        _write_execution_pair(
            paper_store,
            index=index,
            opened_at=opened_at,
            closed_at=closed_at,
            pnl=pnl,
            sleeve_attributions=sleeve_attributions,
        )

    for candidate_id in ("trend-following-v1", "vol-target-v1"):
        validation_store.write_evaluation_evidence(
            EvaluationEvidencePack(
                evidence_pack_id=f"{candidate_id}-reference",
                candidate_id=candidate_id,
                window_start_utc=governed_start,
                window_end_utc=governed_start + timedelta(days=100),
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
    paper_store.write_recovery_drill_record(
        recovery_drill=RecoveryDrillRecord(
            drill_id="governed-recovery",
            symbol="SPY",
            started_at_utc=governed_start,
            completed_at_utc=governed_start + timedelta(minutes=5),
            status="completed",
            summary="Recovery succeeded.",
            evidence_refs=("artifacts/paper_loop/recovery_drills/recovery.json",),
        )
    )
    paper_store.write_alert_drill_record(
        alert_drill=AlertDrillRecord(
            drill_id="governed-smtp",
            channel="smtp",
            recorded_at_utc=governed_start,
            status="completed",
            summary="SMTP delivered.",
            evidence_refs=("artifacts/paper_loop/alert_drills/smtp.json",),
        )
    )

    replay_result = generate_replay_slippage_evidence(
        paper_store=paper_store,
        validation_store=validation_store,
    )
    assert replay_result.summary.status == "pass"
    assert replay_result.summary.matched_execution_count == 1

    report = build_gate3_readiness_report(
        paper_store=paper_store,
        validation_store=validation_store,
    )
    criterion_statuses = {
        criterion.criterion_id: criterion.status for criterion in report.criteria
    }

    assert criterion_statuses["duration_or_trade_count"] == "pass"
    assert criterion_statuses["realized_slippage"] == "pass"
    assert criterion_statuses["hit_rate_alignment"] == "pass"
    assert criterion_statuses["realized_sharpe"] == "pass"
    assert criterion_statuses["recovery_drill"] == "pass"
    assert criterion_statuses["smtp_alert_drill"] == "pass"
    assert criterion_statuses["replay_slippage_divergence"] == "pending"
    assert report.status == "pending"


def test_gate3_governed_replay_passes_with_matched_governed_execution(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "paper_loop")
    validation_store = FilesystemArtifactStore(tmp_path / "validation")
    governed_start = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    sleeve_attributions = (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )

    for index in range(100):
        opened_at = governed_start + timedelta(days=index)
        closed_at = opened_at + timedelta(minutes=30)
        pnl = Decimal("5.00") if index < 60 else Decimal("-2.00")
        _write_execution_pair(
            paper_store,
            index=index,
            opened_at=opened_at,
            closed_at=closed_at,
            pnl=pnl,
            sleeve_attributions=sleeve_attributions,
        )

    paper_store.write_execution_lifecycle_record(
        execution=ExecutionLifecycleRecord(
            execution_id="governed-quote-rich-fill",
            intent_id="governed-quote-rich-intent",
            symbol="SPY",
            side="buy",
            reason_code="governed_entry",
            reference_price=Decimal("500.00"),
            fill_price=Decimal("500.05"),
            filled_qty=Decimal("1"),
            slippage_bps=Decimal("1"),
            submitted_at_utc=governed_start + timedelta(days=100),
            filled_at_utc=governed_start + timedelta(days=100),
            recovered=False,
            bid_price=Decimal("499.95"),
            ask_price=Decimal("500.05"),
            average_daily_volume_30d=Decimal("100000000"),
            sleeve_attributions=sleeve_attributions,
        )
    )

    for candidate_id in ("trend-following-v1", "vol-target-v1"):
        validation_store.write_evaluation_evidence(
            EvaluationEvidencePack(
                evidence_pack_id=f"{candidate_id}-reference",
                candidate_id=candidate_id,
                window_start_utc=governed_start,
                window_end_utc=governed_start + timedelta(days=100),
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
    paper_store.write_recovery_drill_record(
        recovery_drill=RecoveryDrillRecord(
            drill_id="governed-recovery",
            symbol="SPY",
            started_at_utc=governed_start,
            completed_at_utc=governed_start + timedelta(minutes=5),
            status="completed",
            summary="Recovery succeeded.",
            evidence_refs=("artifacts/paper_loop/recovery_drills/recovery.json",),
        )
    )
    paper_store.write_alert_drill_record(
        alert_drill=AlertDrillRecord(
            drill_id="governed-smtp",
            channel="smtp",
            recorded_at_utc=governed_start,
            status="completed",
            summary="SMTP delivered.",
            evidence_refs=("artifacts/paper_loop/alert_drills/smtp.json",),
        )
    )

    replay_result = generate_replay_slippage_evidence(
        paper_store=paper_store,
        validation_store=validation_store,
    )
    assert replay_result.summary.status == "pass"
    assert replay_result.summary.matched_execution_count == 1

    report = build_gate3_readiness_report(
        paper_store=paper_store,
        validation_store=validation_store,
    )
    criterion_statuses = {
        criterion.criterion_id: criterion.status for criterion in report.criteria
    }

    assert criterion_statuses["replay_slippage_divergence"] == "pass"
    assert report.status == "pass"
