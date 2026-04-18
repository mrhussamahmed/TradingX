"""Stage 1 filesystem persistence helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tradingx.types import (
    AlertDrillRecord,
    ClosedTradeRecord,
    EvaluationEvidencePack,
    ExecutionLifecycleRecord,
    Gate3PromotionPackage,
    Gate3ReadinessReport,
    GateAssessment,
    MarketSessionRecord,
    OperatorAlert,
    OrderRecord,
    PortfolioState,
    PositionSnapshot,
    ReconciliationSnapshot,
    RecoveryDrillRecord,
    ReplaySlippageRecord,
    ReplaySlippageSummary,
    RiskControlEvent,
    ServiceCycleSnapshot,
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

    def _write_json(self, category: str, filename: str, payload: Any) -> Path:
        path = self._path_for(category, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_serialize(payload), indent=2, sort_keys=True),
            encoding="utf-8",
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
            "validation_reports",
            "execution_lifecycles",
            "closed_trades",
            "recovery_drills",
            "alert_drills",
            "market_sessions",
            "gate3_reports",
            "gate3_packages",
            "replay_slippage_records",
            "replay_slippage_summaries",
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


__all__ = ("FilesystemArtifactStore",)
