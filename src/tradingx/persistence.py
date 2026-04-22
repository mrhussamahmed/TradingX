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

from tradingx.types import (
    AlertDrillRecord,
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    BotRuntimeState,
    ClosedTradeRecord,
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
    PortfolioState,
    PositionSnapshot,
    ReconciliationSnapshot,
    RecoveryDrillRecord,
    ReplaySlippageRecord,
    ReplaySlippageSummary,
    RiskControlEvent,
    ServiceCycleSnapshot,
    SleeveDailyAttributionRecord,
    SleeveDecompositionRecord,
    SleeveTargetWeights,
    StrategyActivationRecord,
    TradeIntent,
    ValidationReport,
)


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

    def write_evaluation_evidence(self, evidence_pack: EvaluationEvidencePack) -> Path:
        return self._write_json(
            "evaluation_evidence",
            f"{evidence_pack.evidence_pack_id}.json",
            evidence_pack,
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
        return self._write_json(
            "validation_reports",
            f"{report.report_id}.json",
            report,
        )

    def write_execution_lifecycle_record(
        self,
        execution: ExecutionLifecycleRecord,
    ) -> Path:
        return self._write_json(
            "execution_lifecycles",
            f"{execution.execution_id}.json",
            execution,
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
        sleeve_id: str,
    ) -> tuple[SleeveDailyAttributionRecord, ...]:
        category_dir = self._root_dir / "sleeve_daily_attribution"
        if not category_dir.exists():
            return ()
        records: list[SleeveDailyAttributionRecord] = []
        for path in sorted(category_dir.glob(f"{sleeve_id}__*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            records.append(self._deserialize_sleeve_daily_attribution_record(payload))
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
            latest_artifacts[category] = artifacts[-1].name if artifacts else ""
        service_cycle_payloads = self._read_category_payloads("service_cycles")
        evaluation_payloads = self._read_category_payloads("evaluation_evidence")
        gate_payloads = self._read_category_payloads("gate_assessments")
        latest_service_cycle = (
            service_cycle_payloads[-1] if service_cycle_payloads else None
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
                "latest_open_positions": list(
                    latest_service_cycle.get("open_position_symbols", ())
                    if latest_service_cycle is not None
                    else ()
                ),
                "latest_cash": (
                    str(latest_service_cycle.get("cash", ""))
                    if latest_service_cycle is not None
                    else ""
                ),
                "latest_equity": (
                    str(latest_service_cycle.get("equity", ""))
                    if latest_service_cycle is not None
                    else ""
                ),
                "daily_pnl": str(daily_pnl),
                "evaluation_recommendations": recommendation_counts,
                "latest_gate_statuses": {
                    str(payload["gate_id"]): str(payload["status"])
                    for payload in gate_payloads
                },
            },
        }

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
