"""Stage 1 filesystem persistence helpers."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tradingx.experiments import MetricVisibilityContext, MetricVisibilityError
from tradingx.types import (
    AlertDrillRecord,
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    BootstrapPositionAllocation,
    BotRuntimeState,
    ClosedTradeRecord,
    CPCVCohortWindowSummary,
    CPCVTrialRecord,
    DailySessionDigest,
    DriftMonitorVerdictRecord,
    EvaluationEvidencePack,
    ExecutionLifecycleRecord,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    GateAssessment,
    HistoricalWarmupRecord,
    MarketAutomationRunRecord,
    MarketDayScheduleRecord,
    MarketSessionRecord,
    OperatorAlert,
    OpportunitySelectionRecord,
    OrderRecord,
    PBOReport,
    PortfolioState,
    PositionSnapshot,
    ReconciliationSnapshot,
    RecoveryDrillRecord,
    ReplaySlippageRecord,
    ReplaySlippageSummary,
    ResidualPositionAllocation,
    ResidualReserveSnapshot,
    RiskControlEvent,
    ServiceCycleSnapshot,
    SessionOpenPortfolioStateRecord,
    SleeveAttributionGapRecord,
    SleeveBootstrapAllocationRecord,
    SleeveDailyAttributionRecord,
    SleeveDecompositionRecord,
    SleeveLedgerPosition,
    SleevePositionLedgerSnapshot,
    SleeveTargetWeights,
    StrategyActivationRecord,
    TradeIntent,
    ValidationReport,
)
from tradingx.weights import approved_weight_snapshot_from_payload


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


class FilesystemArtifactStore:
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def write_trade_intent(self, intent: TradeIntent) -> Path:
        return self._write_json("trade_intents", f"{intent.intent_id}.json", intent)

    def write_order_record(self, intent_id: str, order: OrderRecord) -> Path:
        return self._write_json("orders", f"{intent_id}.json", order)

    def write_risk_control_event(self, event: RiskControlEvent) -> Path:
        return self._write_json("risk_events", f"{event.event_id}.json", event)

    def write_reconciliation_snapshot(self, snapshot: ReconciliationSnapshot) -> Path:
        return self._write_json(
            "reconciliation", f"{snapshot.reconciliation_id}.json", snapshot
        )

    def write_evaluation_evidence(
        self,
        evidence_pack: EvaluationEvidencePack,
        *,
        metric_visibility_context: MetricVisibilityContext | None = None,
    ) -> Path:
        if (
            metric_visibility_context is None
            and evidence_pack.metric_visibility_context
        ):
            metric_visibility_context = MetricVisibilityContext.from_mapping(
                evidence_pack.metric_visibility_context
            )
        if evidence_pack.promotion_valid and metric_visibility_context is None:
            raise MetricVisibilityError(
                "promotion-valid evaluation metrics require visibility context"
            )
        payload: Any = evidence_pack
        if metric_visibility_context is not None:
            if (
                metric_visibility_context.promotion_valid
                and not metric_visibility_context.is_released
            ):
                raise MetricVisibilityError(
                    "promotion-valid evaluation metrics require metric-vault release"
                )
            serialized = _serialize(evidence_pack)
            if isinstance(serialized, dict):
                serialized["metric_visibility_context"] = (
                    metric_visibility_context.to_json()
                )
                serialized["promotion_valid"] = metric_visibility_context.is_released
                serialized["evidence_class"] = (
                    "valid" if metric_visibility_context.is_released else "exploratory"
                )
                serialized["blocker_codes"] = list(
                    metric_visibility_context.blocker_codes
                )
                payload = serialized
        return self._write_json(
            "evaluation_evidence",
            f"{evidence_pack.evidence_pack_id}.json",
            payload,
        )

    def write_operator_alert(self, alert: OperatorAlert) -> Path:
        return self._write_json("operator_alerts", f"{alert.alert_id}.json", alert)

    def write_gate_assessment(self, assessment: GateAssessment) -> Path:
        return self._write_json(
            "gate_assessments",
            f"gate-{assessment.gate_id}.json",
            assessment,
        )

    def write_service_cycle_snapshot(self, snapshot: ServiceCycleSnapshot) -> Path:
        return self._write_json(
            "service_cycles",
            f"{snapshot.cycle_id}.json",
            snapshot,
        )

    def write_runtime_portfolio_plan(self, plan: Any) -> Path:
        plan_id = str(getattr(plan, "plan_id", "runtime-plan"))
        return self._write_json(
            "runtime_portfolio_plans",
            f"{plan_id}.json",
            plan,
        )

    def read_runtime_portfolio_plan(self, plan_id: str) -> Any | None:
        path = self._path_for("runtime_portfolio_plans", f"{plan_id}.json")
        if not path.exists():
            return None
        from tradingx.runtime_portfolio import (
            RuntimePortfolioPlan,
            RuntimePortfolioTrade,
        )
        from tradingx.types import MarketSnapshot

        payload = json.loads(path.read_text(encoding="utf-8"))
        return RuntimePortfolioPlan(
            plan_id=str(payload["plan_id"]),
            generated_at_utc=datetime.fromisoformat(str(payload["generated_at_utc"])),
            strategy_id=str(payload["strategy_id"]),
            universe_snapshot_id=str(payload["universe_snapshot_id"]),
            benchmark_symbol=str(payload["benchmark_symbol"]),
            crash_overlay_active=bool(payload["crash_overlay_active"]),
            symbols_considered=tuple(
                str(value) for value in payload["symbols_considered"]
            ),
            current_weights={
                str(symbol): Decimal(str(weight))
                for symbol, weight in dict(payload["current_weights"]).items()
            },
            target_weights={
                str(symbol): Decimal(str(weight))
                for symbol, weight in dict(payload["target_weights"]).items()
            },
            trade_intents=tuple(
                TradeIntent(
                    intent_id=str(item["intent_id"]),
                    candidate_id=str(item["candidate_id"]),
                    symbol=str(item["symbol"]),
                    side=str(item["side"]),
                    quantity=(
                        None
                        if item["quantity"] is None
                        else Decimal(str(item["quantity"]))
                    ),
                    reason_code=str(item["reason_code"]),
                    generated_at_utc=datetime.fromisoformat(
                        str(item["generated_at_utc"])
                    ),
                    sleeve_attributions=tuple(
                        (str(entry[0]), Decimal(str(entry[1])))
                        for entry in item.get("sleeve_attributions", ())
                    ),
                )
                for item in payload["trade_intents"]
            ),
            planned_trades=tuple(
                RuntimePortfolioTrade(
                    symbol=str(item["symbol"]),
                    side=str(item["side"]),
                    reason_code=str(item["reason_code"]),
                    last_trade_price=Decimal(str(item["last_trade_price"])),
                    current_weight=Decimal(str(item["current_weight"])),
                    target_weight=Decimal(str(item["target_weight"])),
                    current_quantity=Decimal(str(item["current_quantity"])),
                    target_quantity=Decimal(str(item["target_quantity"])),
                    delta_quantity=Decimal(str(item["delta_quantity"])),
                    no_trade_band_applied=bool(item["no_trade_band_applied"]),
                )
                for item in payload["planned_trades"]
            ),
            market_snapshots={
                str(symbol): MarketSnapshot(
                    symbol=str(snapshot["symbol"]),
                    last_trade_price=Decimal(str(snapshot["last_trade_price"])),
                    bid_price=Decimal(str(snapshot["bid_price"])),
                    ask_price=Decimal(str(snapshot["ask_price"])),
                    average_daily_volume_30d=Decimal(
                        str(snapshot["average_daily_volume_30d"])
                    ),
                    timestamp=datetime.fromisoformat(str(snapshot["timestamp"])),
                )
                for symbol, snapshot in dict(payload["market_snapshots"]).items()
            },
            per_sleeve_target_weights=tuple(
                SleeveTargetWeights(
                    sleeve_id=str(entry["sleeve_id"]),
                    target_weights_by_symbol=tuple(
                        (str(pair[0]), Decimal(str(pair[1])))
                        for pair in entry["target_weights_by_symbol"]
                    ),
                )
                for entry in payload.get("per_sleeve_target_weights", ())
            ),
            sleeve_failure_reasons=tuple(
                (str(entry[0]), str(entry[1]))
                for entry in payload.get("sleeve_failure_reasons", ())
            ),
        )

    def write_runtime_host_state(self, state: BotRuntimeState) -> Path:
        return self._write_json("runtime_host", "state.json", state)

    def write_historical_warmup_record(
        self,
        record: HistoricalWarmupRecord,
    ) -> Path:
        return self._write_json(
            "historical_warmups", f"{record.warmup_id}.json", record
        )

    def write_strategy_activation_record(
        self,
        record: StrategyActivationRecord,
    ) -> Path:
        return self._write_json(
            "strategy_activations",
            f"{record.activation_id}.json",
            record,
        )

    def write_blueprint_activation_record(
        self,
        record: BlueprintActivationRecord,
    ) -> Path:
        return self._write_json(
            "blueprint_activation",
            f"{record.activation_id}.json",
            record,
        )

    def load_blueprint_activation_record(
        self,
        *,
        activation_id: str,
    ) -> BlueprintActivationRecord | None:
        path = self._root_dir / "blueprint_activation" / f"{activation_id}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return self._deserialize_blueprint_activation_record(payload)

    def list_blueprint_activation_records(
        self,
    ) -> tuple[BlueprintActivationRecord, ...]:
        directory = self._root_dir / "blueprint_activation"
        if not directory.exists():
            return ()
        records: list[BlueprintActivationRecord] = []
        for path in sorted(directory.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(self._deserialize_blueprint_activation_record(payload))
        return tuple(records)

    def write_model_weight_snapshot(self, snapshot: ApprovedWeightSnapshot) -> Path:
        return self._write_json(
            "model_weight_snapshots",
            f"{snapshot.snapshot_id}.json",
            snapshot,
        )

    def load_approved_weight_snapshot_by_snapshot_id(
        self,
        *,
        snapshot_id: str,
    ) -> ApprovedWeightSnapshot:
        path = self._path_for("model_weight_snapshots", f"{snapshot_id}.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return self._deserialize_approved_weight_snapshot(payload)

    def write_opportunity_selection_record(
        self,
        record: OpportunitySelectionRecord,
    ) -> Path:
        return self._write_json(
            "opportunity_selections",
            f"{record.selection_id}.json",
            record,
        )

    def write_validation_report(self, report: ValidationReport) -> Path:
        if report.promotion_valid and (
            report.metric_vault_release_status != "released"
            or not report.metric_release_token_ref
        ):
            raise MetricVisibilityError(
                "promotion-valid validation reports require metric-vault release"
            )
        return self._write_json(
            "validation_reports",
            f"{report.report_id}.json",
            report,
        )

    def write_cpcv_trial_record(
        self,
        record: CPCVTrialRecord,
    ) -> Path:
        filename = (
            f"{record.cohort_window_id}__{record.strategy_config_id}"
            f"__{record.cpcv_path_id}.json"
        )
        return self._write_json("cpcv_trials", filename, record)

    def write_pbo_report(self, report: PBOReport) -> Path:
        return self._write_json("pbo_reports", f"{report.report_id}.json", report)

    def load_pbo_report_by_evaluation_id(
        self,
        *,
        evaluation_id: str,
    ) -> PBOReport | None:
        category_dir = self._root_dir / "pbo_reports"
        if not category_dir.exists():
            return None
        for path in sorted(category_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if str(payload.get("evaluation_id")) != evaluation_id:
                continue
            return self._deserialize_pbo_report(payload)
        return None

    def write_execution_lifecycle_record(
        self,
        execution: ExecutionLifecycleRecord,
    ) -> Path:
        return self._write_json(
            "execution_lifecycles",
            f"{execution.execution_id}.json",
            execution,
        )

    def list_execution_lifecycle_records(
        self,
        *,
        trading_day: str | None = None,
    ) -> tuple[ExecutionLifecycleRecord, ...]:
        category_dir = self._root_dir / "execution_lifecycles"
        if not category_dir.exists():
            return ()
        records: list[ExecutionLifecycleRecord] = []
        for path in sorted(category_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = self._deserialize_execution_lifecycle_record(payload)
            if (
                trading_day is not None
                and record.filled_at_utc.date().isoformat() != trading_day
            ):
                continue
            records.append(record)
        return tuple(
            sorted(
                records, key=lambda record: (record.filled_at_utc, record.execution_id)
            )
        )

    def write_closed_trade_record(self, closed_trade: ClosedTradeRecord) -> Path:
        return self._write_json(
            "closed_trades",
            f"{closed_trade.trade_id}.json",
            closed_trade,
        )

    def write_recovery_drill_record(
        self,
        recovery_drill: RecoveryDrillRecord,
    ) -> Path:
        return self._write_json(
            "recovery_drills",
            f"{recovery_drill.drill_id}.json",
            recovery_drill,
        )

    def write_alert_drill_record(self, alert_drill: AlertDrillRecord) -> Path:
        return self._write_json(
            "alert_drills",
            f"{alert_drill.drill_id}.json",
            alert_drill,
        )

    def write_market_session_record(
        self,
        market_session: MarketSessionRecord,
    ) -> Path:
        return self._write_json(
            "market_sessions",
            f"{market_session.session_id}.json",
            market_session,
        )

    def write_daily_session_digest(self, digest: DailySessionDigest) -> Path:
        return self._write_json(
            "daily_digests",
            f"{digest.digest_id}.json",
            digest,
        )

    def write_market_automation_run_record(
        self,
        run_record: MarketAutomationRunRecord,
    ) -> Path:
        return self._write_json(
            "market_automation_runs",
            f"{run_record.run_id}.json",
            run_record,
        )

    def write_market_day_schedule_record(
        self,
        schedule_record: MarketDayScheduleRecord,
    ) -> Path:
        return self._write_json(
            "market_day_schedules",
            f"{schedule_record.schedule_id}.json",
            schedule_record,
        )

    def write_gate3_readiness_report(self, report: Gate3ReadinessReport) -> Path:
        return self._write_json(
            "gate3_reports",
            f"{report.report_id}.json",
            report,
        )

    def write_gate3_promotion_package(
        self,
        package: Gate3PromotionPackage,
    ) -> Path:
        return self._write_json(
            "gate3_packages",
            f"{package.package_id}.json",
            package,
        )

    def write_replay_slippage_record(
        self,
        record: ReplaySlippageRecord,
    ) -> Path:
        return self._write_json(
            "replay_slippage_records",
            f"{record.replay_id}.json",
            record,
        )

    def write_replay_slippage_summary(
        self,
        summary: ReplaySlippageSummary,
    ) -> Path:
        return self._write_json(
            "replay_slippage_summaries",
            f"{summary.summary_id}.json",
            summary,
        )

    def write_backtest_reference_returns(
        self,
        *,
        sleeve_id: str,
        returns: tuple[Decimal, ...],
    ) -> Path:
        from tradingx.drift.backtest_reference import write_backtest_reference_returns

        return write_backtest_reference_returns(
            artifact_root=self._root_dir,
            sleeve_id=sleeve_id,
            returns=returns,
        )

    def load_backtest_reference_returns(
        self,
        *,
        sleeve_id: str,
    ) -> tuple[Decimal, ...]:
        from tradingx.drift.backtest_reference import load_backtest_reference_returns

        return load_backtest_reference_returns(
            artifact_root=self._root_dir,
            sleeve_id=sleeve_id,
        )

    def write_sleeve_daily_attribution_record(
        self,
        record: SleeveDailyAttributionRecord,
    ) -> Path:
        return self._write_json(
            "sleeve_daily_attribution",
            f"{record.sleeve_id}__{record.trading_day}.json",
            record,
        )

    def write_sleeve_bootstrap_allocation_record(
        self,
        record: SleeveBootstrapAllocationRecord,
    ) -> Path:
        return self._write_json(
            "sleeve_bootstrap",
            f"{record.ledger_genesis_id}.json",
            record,
        )

    def write_sleeve_position_ledger_snapshot(
        self,
        record: SleevePositionLedgerSnapshot,
    ) -> Path:
        return self._write_json(
            "sleeve_position_ledger",
            f"{record.trading_day}__{record.snapshot_id}__{record.sleeve_id}.json",
            record,
        )

    def write_residual_reserve_snapshot(
        self,
        record: ResidualReserveSnapshot,
    ) -> Path:
        return self._write_json(
            "residual_reserve",
            f"{record.trading_day}__{record.snapshot_id}.json",
            record,
        )

    def write_session_open_portfolio_state_record(
        self,
        record: SessionOpenPortfolioStateRecord,
    ) -> Path:
        return self._write_json(
            "session_open_portfolio_state",
            f"{record.trading_day}.json",
            record,
        )

    def write_sleeve_attribution_gap_record(
        self,
        record: SleeveAttributionGapRecord,
    ) -> Path:
        return self._write_json(
            "sleeve_attribution_gaps",
            f"{record.sleeve_id}__{record.trading_day}.json",
            record,
        )

    def write_sleeve_decomposition_record(
        self,
        record: SleeveDecompositionRecord,
    ) -> Path:
        return self._write_json(
            "sleeve_decomposition",
            f"{record.trading_day}__{record.decomposition_id}.json",
            record,
        )

    def write_drift_monitor_verdict_record(
        self,
        record: DriftMonitorVerdictRecord,
    ) -> Path:
        return self._write_json(
            "drift_monitor_verdicts",
            f"{record.recorded_at_utc.isoformat()}__{record.verdict_id}.json",
            record,
        )

    def trade_intent_path(self, intent_id: str) -> Path:
        return self._path_for("trade_intents", f"{intent_id}.json")

    def order_record_path(self, intent_id: str) -> Path:
        return self._path_for("orders", f"{intent_id}.json")

    def reconciliation_path(self, reconciliation_id: str) -> Path:
        return self._path_for("reconciliation", f"{reconciliation_id}.json")

    def read_trade_intent(self, intent_id: str) -> TradeIntent | None:
        path = self.trade_intent_path(intent_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TradeIntent(
            intent_id=str(payload["intent_id"]),
            candidate_id=str(payload["candidate_id"]),
            symbol=str(payload["symbol"]),
            side=str(payload["side"]),
            quantity=(
                None
                if payload["quantity"] is None
                else Decimal(str(payload["quantity"]))
            ),
            reason_code=str(payload["reason_code"]),
            generated_at_utc=datetime.fromisoformat(payload["generated_at_utc"]),
            sleeve_attributions=tuple(
                (str(entry[0]), Decimal(str(entry[1])))
                for entry in payload.get("sleeve_attributions", ())
            ),
        )

    def find_latest_trade_intent(self, symbol: str) -> TradeIntent | None:
        trade_intent_dir = self._root_dir / "trade_intents"
        if not trade_intent_dir.exists():
            return None
        latest: TradeIntent | None = None
        for path in sorted(trade_intent_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("symbol") != symbol:
                continue
            candidate = TradeIntent(
                intent_id=str(payload["intent_id"]),
                candidate_id=str(payload["candidate_id"]),
                symbol=str(payload["symbol"]),
                side=str(payload["side"]),
                quantity=(
                    None
                    if payload["quantity"] is None
                    else Decimal(str(payload["quantity"]))
                ),
                reason_code=str(payload["reason_code"]),
                generated_at_utc=datetime.fromisoformat(payload["generated_at_utc"]),
                sleeve_attributions=tuple(
                    (str(entry[0]), Decimal(str(entry[1])))
                    for entry in payload.get("sleeve_attributions", ())
                ),
            )
            if latest is None or candidate.generated_at_utc > latest.generated_at_utc:
                latest = candidate
        return latest

    def read_order_record(self, intent_id: str) -> OrderRecord | None:
        path = self.order_record_path(intent_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return OrderRecord(
            order_id=str(payload["order_id"]),
            client_order_id=str(payload["client_order_id"]),
            symbol=str(payload["symbol"]),
            side=str(payload["side"]),
            status=str(payload["status"]),
            filled_qty=Decimal(str(payload["filled_qty"])),
            filled_avg_price=Decimal(str(payload["filled_avg_price"])),
        )

    def read_reconciliation_snapshot(
        self,
        reconciliation_id: str,
    ) -> ReconciliationSnapshot | None:
        path = self.reconciliation_path(reconciliation_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ReconciliationSnapshot(
            reconciliation_id=str(payload["reconciliation_id"]),
            portfolio_state=self._deserialize_portfolio_state(
                payload["portfolio_state"]
            ),
            broker_state_age_seconds=int(payload["broker_state_age_seconds"]),
            differences=tuple(str(value) for value in payload["differences"]),
            resolved=bool(payload["resolved"]),
        )

    def list_sleeve_daily_attribution_records(
        self,
        *,
        sleeve_id: str | None = None,
        trading_day: str | None = None,
    ) -> tuple[SleeveDailyAttributionRecord, ...]:
        category_dir = self._root_dir / "sleeve_daily_attribution"
        if not category_dir.exists():
            return ()
        records: list[SleeveDailyAttributionRecord] = []
        pattern = (
            f"{sleeve_id}__{trading_day}.json"
            if sleeve_id is not None and trading_day is not None
            else (
                f"{sleeve_id}__*.json"
                if sleeve_id is not None
                else f"*__{trading_day}.json" if trading_day is not None else "*.json"
            )
        )
        for path in sorted(category_dir.glob(pattern)):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(self._deserialize_sleeve_daily_attribution_record(payload))
        return tuple(records)

    def latest_sleeve_bootstrap_allocation(
        self,
    ) -> SleeveBootstrapAllocationRecord | None:
        category_dir = self._root_dir / "sleeve_bootstrap"
        if not category_dir.exists():
            return None
        latest: SleeveBootstrapAllocationRecord | None = None
        for path in sorted(category_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = self._deserialize_sleeve_bootstrap_allocation_record(payload)
            if latest is None or record.recorded_at_utc > latest.recorded_at_utc:
                latest = record
        return latest

    def latest_sleeve_position_ledger_snapshot(
        self,
        *,
        sleeve_id: str,
        before_trading_day: str | None = None,
        include_same_day_bootstrap: bool = False,
    ) -> SleevePositionLedgerSnapshot | None:
        category_dir = self._root_dir / "sleeve_position_ledger"
        if not category_dir.exists():
            return None
        latest: SleevePositionLedgerSnapshot | None = None
        for path in sorted(category_dir.glob(f"*__{sleeve_id}.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = self._deserialize_sleeve_position_ledger_snapshot(payload)
            if before_trading_day is not None:
                if record.trading_day < before_trading_day:
                    pass
                elif (
                    include_same_day_bootstrap
                    and record.trading_day == before_trading_day
                    and record.snapshot_id.startswith("bootstrap-")
                ):
                    pass
                else:
                    continue
            if latest is None or record.recorded_at_utc > latest.recorded_at_utc:
                latest = record
        return latest

    def latest_residual_reserve_snapshot(
        self,
        *,
        before_trading_day: str | None = None,
        include_same_day_bootstrap: bool = False,
    ) -> ResidualReserveSnapshot | None:
        category_dir = self._root_dir / "residual_reserve"
        if not category_dir.exists():
            return None
        latest: ResidualReserveSnapshot | None = None
        for path in sorted(category_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = self._deserialize_residual_reserve_snapshot(payload)
            if before_trading_day is not None:
                if record.trading_day < before_trading_day:
                    pass
                elif (
                    include_same_day_bootstrap
                    and record.trading_day == before_trading_day
                    and record.snapshot_id.startswith("bootstrap-")
                ):
                    pass
                else:
                    continue
            if latest is None or record.recorded_at_utc > latest.recorded_at_utc:
                latest = record
        return latest

    def list_residual_reserve_snapshots(
        self,
        *,
        trading_day: str | None = None,
    ) -> tuple[ResidualReserveSnapshot, ...]:
        category_dir = self._root_dir / "residual_reserve"
        if not category_dir.exists():
            return ()
        records: list[ResidualReserveSnapshot] = []
        pattern = f"{trading_day}__*.json" if trading_day is not None else "*.json"
        for path in sorted(category_dir.glob(pattern)):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(self._deserialize_residual_reserve_snapshot(payload))
        return tuple(records)

    def read_session_open_portfolio_state_record(
        self,
        *,
        trading_day: str,
    ) -> SessionOpenPortfolioStateRecord | None:
        path = self._path_for("session_open_portfolio_state", f"{trading_day}.json")
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return self._deserialize_session_open_portfolio_state_record(payload)

    def list_sleeve_attribution_gap_records(
        self,
        *,
        sleeve_id: str | None = None,
        trading_day: str | None = None,
    ) -> tuple[SleeveAttributionGapRecord, ...]:
        category_dir = self._root_dir / "sleeve_attribution_gaps"
        if not category_dir.exists():
            return ()
        records: list[SleeveAttributionGapRecord] = []
        pattern = (
            f"{sleeve_id}__{trading_day}.json"
            if sleeve_id is not None and trading_day is not None
            else (
                f"{sleeve_id}__*.json"
                if sleeve_id is not None
                else f"*__{trading_day}.json" if trading_day is not None else "*.json"
            )
        )
        for path in sorted(category_dir.glob(pattern)):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(self._deserialize_sleeve_attribution_gap_record(payload))
        return tuple(records)

    def list_sleeve_decomposition_records(
        self,
        *,
        trading_day: str,
    ) -> tuple[SleeveDecompositionRecord, ...]:
        category_dir = self._root_dir / "sleeve_decomposition"
        if not category_dir.exists():
            return ()
        records: list[SleeveDecompositionRecord] = []
        for path in sorted(category_dir.glob(f"{trading_day}__*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(self._deserialize_sleeve_decomposition_record(payload))
        return tuple(records)

    def latest_sleeve_decomposition_record(self) -> SleeveDecompositionRecord | None:
        category_dir = self._root_dir / "sleeve_decomposition"
        if not category_dir.exists():
            return None
        latest_record: SleeveDecompositionRecord | None = None
        for path in sorted(category_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = self._deserialize_sleeve_decomposition_record(payload)
            if (
                latest_record is None
                or record.recorded_at_utc > latest_record.recorded_at_utc
            ):
                latest_record = record
        return latest_record

    def list_drift_monitor_verdict_records(
        self,
        *,
        sleeve_id: str | None = None,
    ) -> tuple[DriftMonitorVerdictRecord, ...]:
        category_dir = self._root_dir / "drift_monitor_verdicts"
        if not category_dir.exists():
            return ()
        records: list[DriftMonitorVerdictRecord] = []
        for path in sorted(category_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = self._deserialize_drift_monitor_verdict_record(payload)
            if sleeve_id is not None and record.sleeve_id != sleeve_id:
                continue
            records.append(record)
        return tuple(records)

    def list_runtime_portfolio_plans(self) -> tuple[Any, ...]:
        category_dir = self._root_dir / "runtime_portfolio_plans"
        if not category_dir.exists():
            return ()
        records: list[Any] = []
        for path in sorted(category_dir.glob("*.json")):
            loaded = self.read_runtime_portfolio_plan(path.stem)
            if loaded is not None:
                records.append(loaded)
        return tuple(records)

    def list_cpcv_trial_records(
        self,
        *,
        cohort_window_id: str,
    ) -> tuple[CPCVTrialRecord, ...]:
        category_dir = self._root_dir / "cpcv_trials"
        if not category_dir.exists():
            return ()
        records: list[CPCVTrialRecord] = []
        for path in sorted(category_dir.glob(f"{cohort_window_id}__*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(self._deserialize_cpcv_trial_record(payload))
        return tuple(records)

    def list_cpcv_cohort_windows(
        self,
    ) -> tuple[CPCVCohortWindowSummary, ...]:
        category_dir = self._root_dir / "cpcv_trials"
        if not category_dir.exists():
            return ()
        grouped: dict[str, list[CPCVTrialRecord]] = {}
        for path in sorted(category_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            record = self._deserialize_cpcv_trial_record(payload)
            grouped.setdefault(record.cohort_window_id, []).append(record)
        summaries = [
            CPCVCohortWindowSummary(
                cohort_window_id=cohort_window_id,
                cpcv_config_fingerprint=(
                    f"N={records[0].n_groups},"
                    f"k={records[0].test_group_count},"
                    f"h={records[0].embargo_days},"
                    f"L={records[0].label_horizon}"
                ),
                window_start_utc=records[0].window_start_utc,
                window_end_utc=records[0].window_end_utc,
                earliest_recorded_at_utc=min(
                    record.recorded_at_utc for record in records
                ),
                latest_recorded_at_utc=max(
                    record.recorded_at_utc for record in records
                ),
                record_count=len(records),
                strategy_config_count=len(
                    {record.strategy_config_id for record in records}
                ),
                path_count=len({record.cpcv_path_id for record in records}),
                git_shas=frozenset(record.git_sha for record in records),
            )
            for cohort_window_id, records in grouped.items()
        ]
        return tuple(
            sorted(summaries, key=lambda summary: summary.earliest_recorded_at_utc)
        )

    def _write_json(self, category: str, filename: str, payload: Any) -> Path:
        path = self._path_for(category, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_text_atomically(
            path,
            json.dumps(_serialize(payload), indent=2, sort_keys=True),
        )
        return path

    def _path_for(self, category: str, filename: str) -> Path:
        return self._root_dir / category / filename

    def _deserialize_portfolio_state(self, payload: dict[str, Any]) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime.fromisoformat(payload["as_of_utc"]),
            cash=Decimal(str(payload["cash"])),
            equity=Decimal(str(payload["equity"])),
            buying_power=Decimal(str(payload["buying_power"])),
            positions=tuple(
                PositionSnapshot(
                    symbol=str(position["symbol"]),
                    quantity=Decimal(str(position["quantity"])),
                    average_entry_price=Decimal(str(position["average_entry_price"])),
                    market_value=Decimal(str(position["market_value"])),
                )
                for position in payload["positions"]
            ),
            open_orders=tuple(str(value) for value in payload["open_orders"]),
        )

    def _deserialize_approved_weight_snapshot(
        self,
        payload: dict[str, Any],
    ) -> ApprovedWeightSnapshot:
        return approved_weight_snapshot_from_payload(payload)

    def _deserialize_execution_lifecycle_record(
        self,
        payload: dict[str, Any],
    ) -> ExecutionLifecycleRecord:
        return ExecutionLifecycleRecord(
            execution_id=str(payload["execution_id"]),
            intent_id=str(payload["intent_id"]),
            symbol=str(payload["symbol"]),
            side=str(payload["side"]),
            reason_code=str(payload["reason_code"]),
            reference_price=Decimal(str(payload["reference_price"])),
            fill_price=Decimal(str(payload["fill_price"])),
            filled_qty=Decimal(str(payload["filled_qty"])),
            slippage_bps=Decimal(str(payload["slippage_bps"])),
            submitted_at_utc=datetime.fromisoformat(str(payload["submitted_at_utc"])),
            filled_at_utc=datetime.fromisoformat(str(payload["filled_at_utc"])),
            recovered=bool(payload["recovered"]),
            bid_price=(
                Decimal(str(payload["bid_price"]))
                if payload.get("bid_price") is not None
                else None
            ),
            ask_price=(
                Decimal(str(payload["ask_price"]))
                if payload.get("ask_price") is not None
                else None
            ),
            average_daily_volume_30d=(
                Decimal(str(payload["average_daily_volume_30d"]))
                if payload.get("average_daily_volume_30d") is not None
                else None
            ),
            sleeve_attributions=tuple(
                (str(entry[0]), Decimal(str(entry[1])))
                for entry in payload.get("sleeve_attributions", ())
            ),
        )

    def _deserialize_bootstrap_position_allocation(
        self,
        payload: dict[str, Any],
    ) -> BootstrapPositionAllocation:
        return BootstrapPositionAllocation(
            sleeve_id=str(payload["sleeve_id"]),
            symbol=str(payload["symbol"]),
            quantity=Decimal(str(payload["quantity"])),
            average_cost=Decimal(str(payload["average_cost"])),
            market_value=Decimal(str(payload["market_value"])),
            allocation_source=str(payload["allocation_source"]),
            confidence=str(payload["confidence"]),
            evidence_refs=tuple(str(value) for value in payload["evidence_refs"]),
        )

    def _deserialize_residual_position_allocation(
        self,
        payload: dict[str, Any],
    ) -> ResidualPositionAllocation:
        return ResidualPositionAllocation(
            symbol=str(payload["symbol"]),
            quantity=Decimal(str(payload["quantity"])),
            average_cost=Decimal(str(payload["average_cost"])),
            market_value=Decimal(str(payload["market_value"])),
            reason=str(payload["reason"]),
            evidence_refs=tuple(str(value) for value in payload["evidence_refs"]),
        )

    def _deserialize_sleeve_bootstrap_allocation_record(
        self,
        payload: dict[str, Any],
    ) -> SleeveBootstrapAllocationRecord:
        return SleeveBootstrapAllocationRecord(
            bootstrap_id=str(payload["bootstrap_id"]),
            ledger_genesis_id=str(payload["ledger_genesis_id"]),
            bootstrapped_from_activation_id=str(
                payload["bootstrapped_from_activation_id"]
            ),
            trading_day=str(payload["trading_day"]),
            recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
            position_allocations=tuple(
                self._deserialize_bootstrap_position_allocation(entry)
                for entry in payload["position_allocations"]
            ),
            residual_cash_balance=Decimal(str(payload["residual_cash_balance"])),
            residual_positions=tuple(
                self._deserialize_residual_position_allocation(entry)
                for entry in payload["residual_positions"]
            ),
            notes=tuple(str(value) for value in payload["notes"]),
        )

    def _deserialize_sleeve_ledger_position(
        self,
        payload: dict[str, Any],
    ) -> SleeveLedgerPosition:
        return SleeveLedgerPosition(
            sleeve_id=str(payload["sleeve_id"]),
            symbol=str(payload["symbol"]),
            quantity=Decimal(str(payload["quantity"])),
            average_cost=Decimal(str(payload["average_cost"])),
            realized_pnl_cumulative=Decimal(str(payload["realized_pnl_cumulative"])),
        )

    def _deserialize_sleeve_position_ledger_snapshot(
        self,
        payload: dict[str, Any],
    ) -> SleevePositionLedgerSnapshot:
        return SleevePositionLedgerSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            ledger_genesis_id=str(payload["ledger_genesis_id"]),
            active_blueprint_activation_id=str(
                payload["active_blueprint_activation_id"]
            ),
            trading_day=str(payload["trading_day"]),
            recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
            sleeve_id=str(payload["sleeve_id"]),
            cash_balance=Decimal(str(payload["cash_balance"])),
            positions=tuple(
                self._deserialize_sleeve_ledger_position(entry)
                for entry in payload["positions"]
            ),
            bootstrap_id=str(payload["bootstrap_id"]),
        )

    def _deserialize_residual_reserve_snapshot(
        self,
        payload: dict[str, Any],
    ) -> ResidualReserveSnapshot:
        return ResidualReserveSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            ledger_genesis_id=str(payload["ledger_genesis_id"]),
            active_blueprint_activation_id=str(
                payload["active_blueprint_activation_id"]
            ),
            trading_day=str(payload["trading_day"]),
            recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
            cash_balance=Decimal(str(payload["cash_balance"])),
            positions=tuple(
                self._deserialize_residual_position_allocation(entry)
                for entry in payload["positions"]
            ),
            bootstrap_id=str(payload["bootstrap_id"]),
        )

    def _deserialize_session_open_portfolio_state_record(
        self,
        payload: dict[str, Any],
    ) -> SessionOpenPortfolioStateRecord:
        return SessionOpenPortfolioStateRecord(
            record_id=str(payload["record_id"]),
            trading_day=str(payload["trading_day"]),
            recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
            portfolio_state=self._deserialize_portfolio_state(
                payload["portfolio_state"]
            ),
        )

    def _deserialize_sleeve_attribution_gap_record(
        self,
        payload: dict[str, Any],
    ) -> SleeveAttributionGapRecord:
        return SleeveAttributionGapRecord(
            gap_id=str(payload["gap_id"]),
            sleeve_id=str(payload["sleeve_id"]),
            trading_day=str(payload["trading_day"]),
            recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
            severity=str(payload["severity"]),
            reason=str(payload["reason"]),
            evidence_refs=tuple(str(value) for value in payload["evidence_refs"]),
        )

    def _deserialize_sleeve_daily_attribution_record(
        self,
        payload: dict[str, Any],
    ) -> SleeveDailyAttributionRecord:
        return SleeveDailyAttributionRecord(
            attribution_id=str(payload["attribution_id"]),
            sleeve_id=str(payload["sleeve_id"]),
            trading_day=str(payload["trading_day"]),
            recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
            starting_equity=Decimal(str(payload["starting_equity"])),
            ending_equity=Decimal(str(payload["ending_equity"])),
            daily_return=Decimal(str(payload["daily_return"])),
            per_symbol_open_weight=tuple(
                (str(item[0]), Decimal(str(item[1])))
                for item in payload["per_symbol_open_weight"]
            ),
            per_symbol_close_weight=tuple(
                (str(item[0]), Decimal(str(item[1])))
                for item in payload["per_symbol_close_weight"]
            ),
            realized_pnl=(
                Decimal(str(payload["realized_pnl"]))
                if payload.get("realized_pnl") is not None
                else None
            ),
            unrealized_pnl=(
                Decimal(str(payload["unrealized_pnl"]))
                if payload.get("unrealized_pnl") is not None
                else None
            ),
            cash_balance=(
                Decimal(str(payload["cash_balance"]))
                if payload.get("cash_balance") is not None
                else None
            ),
            calculation_mode=(
                str(payload["calculation_mode"])
                if payload.get("calculation_mode") is not None
                else None
            ),
            bootstrap_confidence=(
                str(payload["bootstrap_confidence"])
                if payload.get("bootstrap_confidence") is not None
                else None
            ),
            ledger_genesis_id=(
                str(payload["ledger_genesis_id"])
                if payload.get("ledger_genesis_id") is not None
                else None
            ),
        )

    def _deserialize_cpcv_trial_record(
        self,
        payload: dict[str, Any],
    ) -> CPCVTrialRecord:
        return CPCVTrialRecord(
            trial_id=str(payload["trial_id"]),
            cohort_window_id=str(payload["cohort_window_id"]),
            candidate_id=str(payload["candidate_id"]),
            config_fingerprint=str(payload["config_fingerprint"]),
            strategy_config_id=str(payload["strategy_config_id"]),
            cpcv_path_id=str(payload["cpcv_path_id"]),
            n_groups=int(payload["n_groups"]),
            test_group_count=int(payload["test_group_count"]),
            embargo_days=int(payload["embargo_days"]),
            label_horizon=int(payload["label_horizon"]),
            window_start_utc=datetime.fromisoformat(str(payload["window_start_utc"])),
            window_end_utc=datetime.fromisoformat(str(payload["window_end_utc"])),
            train_indices=tuple(int(index) for index in payload["train_indices"]),
            test_indices=tuple(int(index) for index in payload["test_indices"]),
            in_sample_sharpe=Decimal(str(payload["in_sample_sharpe"])),
            out_of_sample_sharpe=Decimal(str(payload["out_of_sample_sharpe"])),
            in_sample_n_trades=int(payload["in_sample_n_trades"]),
            out_of_sample_n_trades=int(payload["out_of_sample_n_trades"]),
            git_sha=str(payload["git_sha"]),
            recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
        )

    def _deserialize_blueprint_activation_record(
        self,
        payload: dict[str, Any],
    ) -> BlueprintActivationRecord:
        return BlueprintActivationRecord(
            activation_id=str(payload["activation_id"]),
            blueprint_id=str(payload["blueprint_id"]),
            sleeve_activation_bindings=tuple(
                BlueprintSleeveBinding(
                    sleeve_id=str(entry["sleeve_id"]),
                    strategy_id=str(entry["strategy_id"]),
                    captured_snapshot_id=str(entry["captured_snapshot_id"]),
                )
                for entry in payload["sleeve_activation_bindings"]
            ),
            status=str(payload["status"]),
            approved_at_utc=datetime.fromisoformat(str(payload["approved_at_utc"])),
            approved_by=str(payload["approved_by"]),
            source_blueprint_path=Path(str(payload["source_blueprint_path"])),
            blueprint_content_hash=(
                str(payload["blueprint_content_hash"])
                if payload.get("blueprint_content_hash") is not None
                else None
            ),
            blueprint_payload=(
                dict(payload["blueprint_payload"])
                if isinstance(payload.get("blueprint_payload"), dict)
                else None
            ),
            superseded_at_utc=(
                datetime.fromisoformat(str(payload["superseded_at_utc"]))
                if payload.get("superseded_at_utc") is not None
                else None
            ),
            supersedes_activation_id=(
                str(payload["supersedes_activation_id"])
                if payload.get("supersedes_activation_id") is not None
                else None
            ),
        )

    def _deserialize_sleeve_decomposition_record(
        self,
        payload: dict[str, Any],
    ) -> SleeveDecompositionRecord:
        return SleeveDecompositionRecord(
            decomposition_id=str(payload["decomposition_id"]),
            cycle_id=str(payload["cycle_id"]),
            trading_day=str(payload["trading_day"]),
            recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
            blueprint_activation_id=str(payload["blueprint_activation_id"]),
            per_sleeve_target_weights=tuple(
                SleeveTargetWeights(
                    sleeve_id=str(entry["sleeve_id"]),
                    target_weights_by_symbol=tuple(
                        (str(pair[0]), Decimal(str(pair[1])))
                        for pair in entry["target_weights_by_symbol"]
                    ),
                )
                for entry in payload["per_sleeve_target_weights"]
            ),
        )

    def _deserialize_drift_monitor_verdict_record(
        self,
        payload: dict[str, Any],
    ) -> DriftMonitorVerdictRecord:
        return DriftMonitorVerdictRecord(
            verdict_id=str(payload["verdict_id"]),
            monitor_id=str(payload["monitor_id"]),
            sleeve_id=(
                str(payload["sleeve_id"])
                if payload.get("sleeve_id") is not None
                else None
            ),
            severity=str(payload["severity"]),
            metric_value=(
                Decimal(str(payload["metric_value"]))
                if payload.get("metric_value") is not None
                else None
            ),
            threshold_value=(
                Decimal(str(payload["threshold_value"]))
                if payload.get("threshold_value") is not None
                else None
            ),
            details=str(payload["details"]),
            recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
        )

    def _deserialize_pbo_report(
        self,
        payload: dict[str, Any],
    ) -> PBOReport:
        return PBOReport(
            report_id=str(payload["report_id"]),
            evaluation_id=str(payload["evaluation_id"]),
            cohort_window_id=str(payload["cohort_window_id"]),
            cohort_size=int(payload["cohort_size"]),
            n_paths=int(payload["n_paths"]),
            n_splits_sampled=int(payload["n_splits_sampled"]),
            pbo_value=Decimal(str(payload["pbo_value"])),
            logit_distribution_percentiles=tuple(
                (Decimal(str(pair[0])), Decimal(str(pair[1])))
                for pair in payload["logit_distribution_percentiles"]
            ),
            cpcv_config_fingerprint=str(payload["cpcv_config_fingerprint"]),
            metric_name=str(payload["metric_name"]),
            random_seed=int(payload["random_seed"]),
            generated_at_utc=datetime.fromisoformat(str(payload["generated_at_utc"])),
            full_cpcv_matrix_ref=str(payload.get("full_cpcv_matrix_ref", "")),
        )

    def build_operator_evidence_report(self) -> dict[str, object]:
        categories = (
            "trade_intents",
            "orders",
            "risk_events",
            "reconciliation",
            "evaluation_evidence",
            "operator_alerts",
            "gate_assessments",
            "service_cycles",
            "runtime_portfolio_plans",
            "validation_reports",
            "cpcv_trials",
            "pbo_reports",
            "execution_lifecycles",
            "closed_trades",
            "drift_monitor_verdicts",
            "recovery_drills",
            "alert_drills",
            "runtime_host",
            "historical_warmups",
            "strategy_activations",
            "blueprint_activation",
            "model_weight_snapshots",
            "opportunity_selections",
            "market_sessions",
            "daily_digests",
            "market_automation_runs",
            "gate3_reports",
            "gate3_packages",
            "replay_slippage_records",
            "replay_slippage_summaries",
            "sleeve_bootstrap",
            "sleeve_position_ledger",
            "residual_reserve",
            "session_open_portfolio_state",
            "sleeve_attribution_gaps",
            "sleeve_daily_attribution",
            "sleeve_decomposition",
        )
        counts: dict[str, int] = {}
        latest_artifacts: dict[str, str] = {}
        for category in categories:
            category_dir = self._root_dir / category
            artifacts = (
                sorted(category_dir.glob("*.json")) if category_dir.exists() else []
            )
            counts[category] = len(artifacts)
            latest_artifacts[category] = self._latest_artifact_name(artifacts)
        service_cycle_payloads = self._read_category_payloads_by_recency(
            "service_cycles"
        )
        reconciliation_payloads = self._read_category_payloads("reconciliation")
        evaluation_payloads = self._read_category_payloads("evaluation_evidence")
        gate_payloads = self._read_category_payloads("gate_assessments")
        latest_service_cycle = (
            service_cycle_payloads[-1] if service_cycle_payloads else None
        )
        latest_portfolio_summary = self._latest_portfolio_summary(
            latest_service_cycle=latest_service_cycle,
            reconciliation_payloads=reconciliation_payloads,
        )
        daily_pnl = Decimal("0")
        if latest_service_cycle is not None:
            latest_cycle_day = str(latest_service_cycle["completed_at_utc"]).split("T")[
                0
            ]
            same_day_cycles = [
                payload
                for payload in service_cycle_payloads
                if str(payload["completed_at_utc"]).startswith(latest_cycle_day)
            ]
            if same_day_cycles:
                daily_pnl = Decimal(str(same_day_cycles[-1]["equity"])) - Decimal(
                    str(same_day_cycles[0]["equity"])
                )
        recommendation_counts: dict[str, int] = {}
        for payload in evaluation_payloads:
            recommendation = str(payload.get("recommendation", "")).strip()
            if not recommendation:
                continue
            recommendation_counts[recommendation] = (
                recommendation_counts.get(recommendation, 0) + 1
            )
        return {
            "counts": counts,
            "latest_artifacts": latest_artifacts,
            "summary": {
                "blocked_trade_count": sum(
                    int(payload.get("blocked_trade_count", 0))
                    for payload in service_cycle_payloads
                ),
                "reconciliation_failure_count": sum(
                    int(payload.get("reconciliation_failure_count", 0))
                    for payload in service_cycle_payloads
                ),
                "latest_open_positions": latest_portfolio_summary[
                    "latest_open_positions"
                ],
                "latest_cash": latest_portfolio_summary["latest_cash"],
                "latest_equity": latest_portfolio_summary["latest_equity"],
                "daily_pnl": str(daily_pnl),
                "evaluation_recommendations": recommendation_counts,
                "latest_gate_statuses": {
                    str(payload["gate_id"]): str(payload["status"])
                    for payload in gate_payloads
                },
            },
        }

    def _latest_portfolio_summary(
        self,
        *,
        latest_service_cycle: dict[str, Any] | None,
        reconciliation_payloads: list[dict[str, Any]],
    ) -> dict[str, object]:
        service_as_of = self._parse_artifact_timestamp(
            None
            if latest_service_cycle is None
            else latest_service_cycle.get("completed_at_utc")
        )
        latest_reconciliation = self._latest_reconciliation_portfolio_payload(
            reconciliation_payloads
        )
        reconciliation_as_of = self._parse_artifact_timestamp(
            None
            if latest_reconciliation is None
            else self._portfolio_state_payload(latest_reconciliation).get("as_of_utc")
        )
        if latest_reconciliation is not None and (
            service_as_of is None
            or (
                reconciliation_as_of is not None
                and reconciliation_as_of >= service_as_of
            )
        ):
            portfolio_state = self._portfolio_state_payload(latest_reconciliation)
            return {
                "latest_open_positions": self._open_position_symbols_from_payload(
                    portfolio_state
                ),
                "latest_cash": str(portfolio_state.get("cash", "")),
                "latest_equity": str(portfolio_state.get("equity", "")),
            }
        if latest_service_cycle is None:
            return {
                "latest_open_positions": [],
                "latest_cash": "",
                "latest_equity": "",
            }
        return {
            "latest_open_positions": list(
                latest_service_cycle.get("open_position_symbols", ())
            ),
            "latest_cash": str(latest_service_cycle.get("cash", "")),
            "latest_equity": str(latest_service_cycle.get("equity", "")),
        }

    def _latest_artifact_name(self, artifacts: list[Path]) -> str:
        if not artifacts:
            return ""
        return max(artifacts, key=self._artifact_recency_key).name

    def _artifact_recency_key(self, path: Path) -> tuple[datetime, float, str]:
        fallback_mtime = path.stat().st_mtime
        timestamp = self._artifact_payload_timestamp(path)
        if timestamp is None:
            timestamp = datetime.fromtimestamp(fallback_mtime, UTC)
        return (timestamp, fallback_mtime, path.name)

    def _artifact_payload_timestamp(self, path: Path) -> datetime | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return self._payload_timestamp(payload)

    def _payload_timestamp(self, payload: dict[str, Any]) -> datetime | None:
        for field in (
            "generated_at_utc",
            "completed_at_utc",
            "recorded_at_utc",
            "sent_at_utc",
            "filled_at_utc",
            "submitted_at_utc",
            "activated_at_utc",
            "timestamp_utc",
            "as_of_utc",
        ):
            timestamp = self._parse_artifact_timestamp(payload.get(field))
            if timestamp is not None:
                return timestamp
        portfolio_state = self._portfolio_state_payload(payload)
        return self._parse_artifact_timestamp(portfolio_state.get("as_of_utc"))

    def _latest_reconciliation_portfolio_payload(
        self,
        reconciliation_payloads: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        candidates = [
            payload
            for payload in reconciliation_payloads
            if self._portfolio_state_payload(payload)
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda payload: self._parse_artifact_timestamp(
                self._portfolio_state_payload(payload).get("as_of_utc")
            )
            or datetime.min.replace(tzinfo=UTC),
        )

    def _portfolio_state_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_portfolio_state = payload.get("portfolio_state")
        return (
            dict(raw_portfolio_state) if isinstance(raw_portfolio_state, dict) else {}
        )

    def _open_position_symbols_from_payload(
        self,
        portfolio_state: dict[str, Any],
    ) -> list[str]:
        symbols: list[str] = []
        for raw_position in portfolio_state.get("positions", ()):
            if not isinstance(raw_position, dict):
                continue
            quantity = Decimal(str(raw_position.get("quantity", "0")))
            if quantity != Decimal("0"):
                symbols.append(str(raw_position.get("symbol", "")))
        return [symbol for symbol in symbols if symbol]

    def _parse_artifact_timestamp(self, value: object) -> datetime | None:
        raw_value = str(value or "").strip()
        if not raw_value:
            return None
        try:
            timestamp = datetime.fromisoformat(raw_value)
        except ValueError:
            return None
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC)

    def list_artifact_payloads(self, category: str) -> list[dict[str, Any]]:
        return self._read_category_payloads(category)

    def _read_category_payloads(self, category: str) -> list[dict[str, Any]]:
        category_dir = self._root_dir / category
        if not category_dir.exists():
            return []
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(category_dir.glob("*.json"))
        ]

    def _read_category_payloads_by_recency(
        self,
        category: str,
    ) -> list[dict[str, Any]]:
        return sorted(
            self._read_category_payloads(category),
            key=lambda payload: self._payload_timestamp(payload)
            or datetime.min.replace(tzinfo=UTC),
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


__all__ = ("FilesystemArtifactStore",)
