from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide

from tradingx.alerts import (
    OperatorAlertDispatcher,
    build_alert_dispatcher,
    build_evaluation_summary_alert,
    build_risk_control_alert,
)
from tradingx.config import TradingConfig
from tradingx.data import (
    AlpacaMarketDataGateway,
    AlpacaRegularHoursCalendar,
    close_to_close_returns,
)
from tradingx.evaluation import evaluate_candidate
from tradingx.execution import AlpacaPaperExecutionGateway
from tradingx.journal import SqliteOmsJournal, build_client_order_id
from tradingx.monitoring import StageMetrics
from tradingx.persistence import FilesystemArtifactStore
from tradingx.policy import (
    PolicySnapshot,
    PolicySnapshotStore,
    build_week1_policy_snapshot,
)
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.risk import PaperOnlyRiskEngine, PreTradeRiskContext
from tradingx.snapshots import (
    CandidateIntentSnapshot,
    ContentAddressedSnapshotStore,
    DecisionSnapshotV1,
)
from tradingx.strategy import (
    DeterministicBaselineStrategy,
    build_candidate_return_series,
    build_mandatory_candidate_registry,
)
from tradingx.types import (
    ClosedTradeRecord,
    EvaluationEvidencePack,
    ExecutionLifecycleRecord,
    GateAssessment,
    GateReportResult,
    LatestQuote,
    MarketSnapshot,
    PortfolioState,
    ReconciliationSnapshot,
    RiskControlEvent,
    RoundTripResult,
    TradeIntent,
    TradingLoopResult,
)
from tradingx.validation import build_gate_report


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


class RoundTripController:
    def __init__(
        self,
        *,
        market_data: AlpacaMarketDataGateway,
        execution: AlpacaPaperExecutionGateway,
        portfolio: AlpacaPortfolioGateway,
        risk: PaperOnlyRiskEngine,
    ) -> None:
        self._market_data = market_data
        self._execution = execution
        self._portfolio = portfolio
        self._risk = risk

    def run_paper_roundtrip(
        self,
        symbol: str,
        quantity: Decimal,
        *,
        log_dir: Path,
    ) -> RoundTripResult:
        initial_account = self._portfolio.get_account_snapshot()
        initial_position_quantity = self._portfolio.get_position_quantity(symbol)
        entry_market_snapshot = self._market_data.get_market_snapshot(symbol)
        quote = LatestQuote(
            symbol=symbol,
            bid_price=entry_market_snapshot.bid_price,
            ask_price=entry_market_snapshot.ask_price,
            timestamp=entry_market_snapshot.timestamp,
        )

        self._risk.assert_order_allowed(
            PreTradeRiskContext(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                last_trade_price=entry_market_snapshot.last_trade_price,
                average_daily_volume_30d=entry_market_snapshot.average_daily_volume_30d,
                market_data_timestamp=entry_market_snapshot.timestamp,
                account_equity=initial_account.equity,
                buying_power=initial_account.buying_power,
                current_position_quantity=initial_position_quantity,
                broker_state_timestamp=datetime.now(UTC),
            ),
            is_live_order=False,
        )
        buy_submitted = self._execution.submit_market_order(
            symbol, quantity, OrderSide.BUY
        )
        buy_order = self._execution.wait_for_fill(buy_submitted.order_id)

        opened_position_quantity = self._wait_for_position_quantity(
            symbol,
            minimum_quantity=quantity,
        )
        exit_market_snapshot = self._market_data.get_market_snapshot(symbol)
        self._risk.assert_order_allowed(
            PreTradeRiskContext(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                last_trade_price=exit_market_snapshot.last_trade_price,
                average_daily_volume_30d=exit_market_snapshot.average_daily_volume_30d,
                market_data_timestamp=exit_market_snapshot.timestamp,
                account_equity=initial_account.equity,
                buying_power=initial_account.buying_power,
                current_position_quantity=opened_position_quantity,
                broker_state_timestamp=datetime.now(UTC),
            ),
            is_live_order=False,
        )
        sell_submitted = self._execution.close_position(symbol)
        sell_order = self._execution.wait_for_fill(sell_submitted.order_id)

        final_account = self._portfolio.get_account_snapshot()
        final_position_quantity = self._portfolio.get_position_quantity(symbol)
        if final_position_quantity != Decimal("0"):
            raise RuntimeError(
                "Expected flat position after round trip, "
                f"found {final_position_quantity}."
            )

        result = RoundTripResult(
            symbol=symbol,
            quantity=quantity,
            quote=quote,
            initial_account=initial_account,
            final_account=final_account,
            buy_order=buy_order,
            sell_order=sell_order,
            final_position_quantity=final_position_quantity,
            cash_delta=final_account.cash - initial_account.cash,
            log_path=Path(),
        )
        log_path = self._write_structured_log(result, log_dir=log_dir)
        return RoundTripResult(
            symbol=result.symbol,
            quantity=result.quantity,
            quote=result.quote,
            initial_account=result.initial_account,
            final_account=result.final_account,
            buy_order=result.buy_order,
            sell_order=result.sell_order,
            final_position_quantity=result.final_position_quantity,
            cash_delta=result.cash_delta,
            log_path=log_path,
        )

    def _write_structured_log(self, result: RoundTripResult, *, log_dir: Path) -> Path:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        log_path = log_dir / f"{result.symbol.lower()}-paper-roundtrip-{timestamp}.json"
        payload = {
            "symbol": result.symbol,
            "quantity": result.quantity,
            "quote": asdict(result.quote),
            "initial_account": asdict(result.initial_account),
            "buy_order": asdict(result.buy_order),
            "sell_order": asdict(result.sell_order),
            "final_account": asdict(result.final_account),
            "final_position_quantity": result.final_position_quantity,
            "cash_delta": result.cash_delta,
        }
        log_path.write_text(
            json.dumps(_serialize(payload), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return log_path

    def _wait_for_position_quantity(
        self,
        symbol: str,
        *,
        minimum_quantity: Decimal,
        timeout_seconds: float = 30,
        poll_interval_seconds: float = 1,
    ) -> Decimal:
        deadline = time.monotonic() + timeout_seconds
        while True:
            position_quantity = self._portfolio.get_position_quantity(symbol)
            if position_quantity >= minimum_quantity:
                return position_quantity
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Timed out waiting for broker position in "
                    f"{symbol} to reach {minimum_quantity}."
                )
            time.sleep(poll_interval_seconds)


class PaperTradingLoopController:
    def __init__(
        self,
        *,
        market_data: Any,
        execution: Any,
        portfolio: Any,
        risk: PaperOnlyRiskEngine,
        strategy: DeterministicBaselineStrategy,
        artifacts: FilesystemArtifactStore,
        metrics: StageMetrics,
        alert_dispatcher: OperatorAlertDispatcher | None = None,
        regular_hours_checker: Any,
        now_provider: Any | None = None,
        command_timeout_seconds: float = 30,
        policy_snapshot: PolicySnapshot | None = None,
        policy_store: PolicySnapshotStore | None = None,
        snapshot_store: ContentAddressedSnapshotStore | None = None,
        journal: SqliteOmsJournal | None = None,
        git_sha: str = "unknown",
        dry_run: bool = False,
    ) -> None:
        self._market_data = market_data
        self._execution = execution
        self._portfolio = portfolio
        self._risk = risk
        self._strategy = strategy
        self._artifacts = artifacts
        self._metrics = metrics
        self._alert_dispatcher = alert_dispatcher
        self._regular_hours_checker = regular_hours_checker
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._command_timeout_seconds = command_timeout_seconds
        self._policy_snapshot = policy_snapshot
        self._policy_store = policy_store
        self._snapshot_store = snapshot_store
        self._journal = journal
        self._git_sha = git_sha
        self._dry_run = dry_run
        self._session_start_equity: Decimal | None = None
        self._policy_path: Path | None = None
        if self._policy_store is not None and self._policy_snapshot is not None:
            self._policy_path = self._policy_store.write(self._policy_snapshot)

    def run_trading_cycle(
        self,
        symbol: str,
        quantity: Decimal,
    ) -> TradingLoopResult:
        portfolio_state = self._portfolio.get_portfolio_state()
        if self._session_start_equity is None:
            self._session_start_equity = portfolio_state.equity
        market_snapshot = self._market_data.get_market_snapshot(symbol)
        trade_intent = self._strategy.generate_trade_intent(
            market_snapshot=market_snapshot,
            portfolio_state=portfolio_state,
            quantity=quantity,
        )
        trade_path = self._artifacts.write_trade_intent(trade_intent)
        self._metrics.record_evidence_artifact("trade_intent")
        self._metrics.record_live_disable_state(True)
        self._metrics.record_manual_halt_state(
            self._risk._config.runtime.manual_kill_switch_active
        )

        if trade_intent.side not in {"buy", "sell", "reduce"}:
            decision_path = self._write_decision_snapshot(
                trade_intent=trade_intent,
                session_start_equity=portfolio_state.equity,
                risk_verdict_id="not_applicable",
                final_action="no_action",
            )
            self._append_journal_event(
                event_type="intent",
                decision_path=decision_path,
                trade_intent=trade_intent,
                client_order_id="",
                broker_order_id="",
                payload={"terminal_reason": trade_intent.reason_code},
            )
            reconciliation = self._build_reconciliation(
                trade_intent=trade_intent,
                portfolio_state=portfolio_state,
                differences=(trade_intent.reason_code,),
            )
            reconciliation_path = self._artifacts.write_reconciliation_snapshot(
                reconciliation
            )
            self._metrics.record_evidence_artifact("reconciliation")
            self._metrics.record_trade_terminal_state("no_action")
            return TradingLoopResult(
                terminal_state="no_action",
                trade_intent=trade_intent,
                order_record=None,
                risk_event=None,
                reconciliation=reconciliation,
                artifact_paths=tuple(
                    path
                    for path in (
                        trade_path,
                        self._policy_path,
                        decision_path,
                        reconciliation_path,
                    )
                    if path is not None
                ),
            )

        if not self._regular_hours_checker(self._now_provider()):
            risk_event = self._build_manual_risk_event(
                trade_intent,
                control_code="outside_regular_hours",
            )
            decision_path = self._write_decision_snapshot(
                trade_intent=trade_intent,
                session_start_equity=portfolio_state.equity,
                risk_verdict_id=risk_event.event_id,
                final_action="blocked",
            )
            self._append_journal_event(
                event_type="intent",
                decision_path=decision_path,
                trade_intent=trade_intent,
                client_order_id="",
                broker_order_id="",
                payload={"terminal_reason": risk_event.control_type},
            )
            risk_path = self._artifacts.write_risk_control_event(risk_event)
            self._metrics.record_evidence_artifact("risk_event")
            reconciliation = self._build_reconciliation(
                trade_intent=trade_intent,
                portfolio_state=portfolio_state,
                differences=(risk_event.control_type,),
            )
            reconciliation_path = self._artifacts.write_reconciliation_snapshot(
                reconciliation
            )
            self._metrics.record_evidence_artifact("reconciliation")
            self._metrics.record_trade_terminal_state("blocked_trade")
            self._metrics.record_reconciliation_age_seconds(
                reconciliation.broker_state_age_seconds
            )
            alert_path = self._dispatch_risk_alert(
                risk_event,
                evidence_refs=(str(risk_path), str(reconciliation_path)),
            )
            return TradingLoopResult(
                terminal_state="blocked_trade",
                trade_intent=trade_intent,
                order_record=None,
                risk_event=risk_event,
                reconciliation=reconciliation,
                artifact_paths=tuple(
                    path
                    for path in (
                        trade_path,
                        self._policy_path,
                        decision_path,
                        risk_path,
                        reconciliation_path,
                        alert_path,
                    )
                    if path is not None
                ),
            )

        risk_decision = self._risk.evaluate_trade_intent(
            trade_intent,
            market_snapshot,
            portfolio_state,
            broker_state_timestamp=portfolio_state.as_of_utc,
        )
        decision_path = self._write_decision_snapshot(
            trade_intent=trade_intent,
            session_start_equity=portfolio_state.equity,
            risk_verdict_id=(
                risk_decision.event.event_id
                if risk_decision.event is not None
                else "risk-approved"
            ),
            final_action=(
                "blocked"
                if risk_decision.event is not None
                else ("dry_run" if self._dry_run else trade_intent.side)
            ),
        )
        client_order_id = ""
        if trade_intent.side in {"buy", "sell", "reduce"}:
            client_order_id = build_client_order_id(
                decision_snapshot_id=decision_path.stem,
                symbol=trade_intent.symbol,
                side=trade_intent.side,
                intent_seq=0,
            )
        self._append_journal_event(
            event_type="intent",
            decision_path=decision_path,
            trade_intent=trade_intent,
            client_order_id=client_order_id,
            broker_order_id="",
            payload={"terminal_reason": trade_intent.reason_code},
        )
        if risk_decision.event is not None:
            risk_path = self._artifacts.write_risk_control_event(risk_decision.event)
            self._metrics.record_evidence_artifact("risk_event")
            self._metrics.record_blocked_trade(risk_decision.control_code)
            reconciliation = self._build_reconciliation(
                trade_intent=trade_intent,
                portfolio_state=portfolio_state,
                differences=(risk_decision.control_code,),
            )
            reconciliation_path = self._artifacts.write_reconciliation_snapshot(
                reconciliation
            )
            self._metrics.record_evidence_artifact("reconciliation")
            self._metrics.record_trade_terminal_state("blocked_trade")
            self._metrics.record_reconciliation_age_seconds(
                reconciliation.broker_state_age_seconds
            )
            alert_path = self._dispatch_risk_alert(
                risk_decision.event,
                evidence_refs=(str(risk_path), str(reconciliation_path)),
            )
            return TradingLoopResult(
                terminal_state="blocked_trade",
                trade_intent=trade_intent,
                order_record=None,
                risk_event=risk_decision.event,
                reconciliation=reconciliation,
                artifact_paths=tuple(
                    path
                    for path in (
                        trade_path,
                        self._policy_path,
                        decision_path,
                        risk_path,
                        reconciliation_path,
                        alert_path,
                    )
                    if path is not None
                ),
            )

        if self._dry_run:
            self._append_journal_event(
                event_type="simulated",
                decision_path=decision_path,
                trade_intent=trade_intent,
                client_order_id=client_order_id,
                broker_order_id="",
                payload={
                    "side": trade_intent.side,
                    "quantity": str(trade_intent.quantity or quantity),
                    "reason_code": trade_intent.reason_code,
                },
            )
            reconciliation = self._build_reconciliation(
                trade_intent=trade_intent,
                portfolio_state=portfolio_state,
                differences=(),
            )
            reconciliation_path = self._artifacts.write_reconciliation_snapshot(
                reconciliation
            )
            self._metrics.record_evidence_artifact("reconciliation")
            self._metrics.record_trade_terminal_state("dry_run")
            return TradingLoopResult(
                terminal_state="dry_run",
                trade_intent=trade_intent,
                order_record=None,
                risk_event=None,
                reconciliation=reconciliation,
                artifact_paths=tuple(
                    path
                    for path in (
                        trade_path,
                        self._policy_path,
                        decision_path,
                        reconciliation_path,
                    )
                    if path is not None
                ),
            )

        existing_order = self._artifacts.read_order_record(trade_intent.intent_id)
        recovered = existing_order is not None
        execution_quantity = trade_intent.quantity or quantity
        if existing_order is None:
            self._append_journal_event(
                event_type="submit_attempt",
                decision_path=decision_path,
                trade_intent=trade_intent,
                client_order_id=client_order_id,
                broker_order_id="",
                payload={"reason_code": trade_intent.reason_code},
            )
            existing_order = self._execution.submit_market_order(
                trade_intent.symbol,
                execution_quantity,
                OrderSide.BUY if trade_intent.side == "buy" else OrderSide.SELL,
                client_order_id=client_order_id,
            )
            self._append_journal_event(
                event_type="ack",
                decision_path=decision_path,
                trade_intent=trade_intent,
                client_order_id=existing_order.client_order_id,
                broker_order_id=existing_order.order_id,
                payload={"status": existing_order.status},
            )
            order_path = self._artifacts.write_order_record(
                trade_intent.intent_id,
                existing_order,
            )
            self._metrics.record_evidence_artifact("order")
        else:
            order_path = self._artifacts.order_record_path(trade_intent.intent_id)

        order_record = self._execution.wait_for_fill(
            existing_order.order_id,
            timeout_seconds=self._command_timeout_seconds,
            poll_interval_seconds=0,
        )
        order_record = self._merge_order_records(existing_order, order_record)
        self._artifacts.write_order_record(trade_intent.intent_id, order_record)
        self._append_journal_event(
            event_type="fill",
            decision_path=decision_path,
            trade_intent=trade_intent,
            client_order_id=order_record.client_order_id,
            broker_order_id=order_record.order_id,
            payload={
                "status": order_record.status,
                "filled_qty": str(order_record.filled_qty),
                "filled_avg_price": str(order_record.filled_avg_price),
            },
        )
        execution_record = self._build_execution_lifecycle_record(
            trade_intent=trade_intent,
            market_snapshot=market_snapshot,
            order_record=order_record,
            recovered=recovered,
        )
        execution_path = self._artifacts.write_execution_lifecycle_record(
            execution_record
        )
        final_portfolio_state = self._portfolio.get_portfolio_state()
        reconciliation = self._build_reconciliation(
            trade_intent=trade_intent,
            portfolio_state=final_portfolio_state,
            differences=(),
        )
        reconciliation_path = self._artifacts.write_reconciliation_snapshot(
            reconciliation
        )
        closed_trade_path = self._write_closed_trade_record_if_available(
            trade_intent=trade_intent,
            order_record=order_record,
        )
        self._metrics.record_evidence_artifact("reconciliation")
        self._metrics.record_trade_terminal_state("reconciled_trade")
        self._metrics.record_reconciliation_age_seconds(
            reconciliation.broker_state_age_seconds
        )
        return TradingLoopResult(
            terminal_state="reconciled_trade",
            trade_intent=trade_intent,
            order_record=order_record,
            risk_event=None,
            reconciliation=reconciliation,
            artifact_paths=tuple(
                path
                for path in (
                    trade_path,
                    self._policy_path,
                    decision_path,
                    order_path,
                    execution_path,
                    reconciliation_path,
                    closed_trade_path,
                )
                if path is not None
            ),
            recovered=recovered,
        )

    def recover_trading_cycle(self, symbol: str) -> TradingLoopResult | None:
        trade_intent = self._artifacts.find_latest_trade_intent(symbol)
        if trade_intent is None:
            return None
        order_record = self._artifacts.read_order_record(trade_intent.intent_id)
        reconciliation_id = self._reconciliation_id(trade_intent.intent_id)
        existing_reconciliation = self._artifacts.read_reconciliation_snapshot(
            reconciliation_id
        )
        trade_path = self._artifacts.trade_intent_path(trade_intent.intent_id)
        artifact_paths = [trade_path]
        if order_record is not None:
            artifact_paths.append(
                self._artifacts.order_record_path(trade_intent.intent_id)
            )
        if existing_reconciliation is not None and existing_reconciliation.resolved:
            artifact_paths.append(
                self._artifacts.reconciliation_path(reconciliation_id)
            )
            return TradingLoopResult(
                terminal_state=(
                    "reconciled_trade" if order_record is not None else "blocked_trade"
                ),
                trade_intent=trade_intent,
                order_record=order_record,
                risk_event=None,
                reconciliation=existing_reconciliation,
                artifact_paths=tuple(artifact_paths),
                recovered=True,
            )
        if order_record is None:
            return None

        filled_order = self._execution.wait_for_fill(
            order_record.order_id,
            timeout_seconds=self._command_timeout_seconds,
            poll_interval_seconds=0,
        )
        filled_order = self._merge_order_records(order_record, filled_order)
        self._artifacts.write_order_record(trade_intent.intent_id, filled_order)
        final_portfolio_state = self._portfolio.get_portfolio_state()
        reconciliation = self._build_reconciliation(
            trade_intent=trade_intent,
            portfolio_state=final_portfolio_state,
            differences=(),
        )
        reconciliation_path = self._artifacts.write_reconciliation_snapshot(
            reconciliation
        )
        self._metrics.record_evidence_artifact("reconciliation")
        self._metrics.record_trade_terminal_state("reconciled_trade")
        self._metrics.record_reconciliation_age_seconds(
            reconciliation.broker_state_age_seconds
        )
        return TradingLoopResult(
            terminal_state="reconciled_trade",
            trade_intent=trade_intent,
            order_record=filled_order,
            risk_event=None,
            reconciliation=reconciliation,
            artifact_paths=tuple(artifact_paths + [reconciliation_path]),
            recovered=True,
        )

    def _write_decision_snapshot(
        self,
        *,
        trade_intent: TradeIntent,
        session_start_equity: Decimal,
        risk_verdict_id: str,
        final_action: str,
    ) -> Path:
        if self._snapshot_store is None or self._policy_snapshot is None:
            return self._artifacts.write_trade_intent(trade_intent)
        snapshot = DecisionSnapshotV1(
            schema_version=1,
            timestamp_utc=self._now_provider(),
            cycle_correlation_id=f"cycle-{trade_intent.intent_id}",
            session_snapshot_id=self._policy_snapshot.policy_snapshot_id,
            universe_snapshot_id="week1-spy",
            policy_snapshot_id=self._policy_snapshot.policy_snapshot_id,
            model_snapshot_id="baseline-deterministic",
            strategy_version=self._strategy.candidate_id,
            strategy_config_hash=_strategy_config_hash(self._strategy),
            git_sha=self._git_sha,
            dry_run=self._dry_run,
            market_data_window_hash=f"market-{trade_intent.symbol.lower()}",
            feature_snapshot_id=f"feature-{trade_intent.symbol.lower()}",
            session_start_equity=session_start_equity,
            candidate_intents=(
                CandidateIntentSnapshot(
                    symbol=trade_intent.symbol,
                    selected=trade_intent.side in {"buy", "sell", "reduce"},
                    terminal_reason=trade_intent.reason_code,
                    base_score=Decimal("0"),
                    final_score=Decimal("0"),
                    eligibility="eligible",
                    risk_status=(
                        "pending"
                        if risk_verdict_id == "risk-approved"
                        else "blocked"
                    ),
                ),
            ),
            final_action=final_action,
            risk_verdict_id=risk_verdict_id,
        )
        return self._snapshot_store.write_decision_snapshot(snapshot)

    def _append_journal_event(
        self,
        *,
        event_type: str,
        decision_path: Path,
        trade_intent: TradeIntent,
        client_order_id: str,
        broker_order_id: str,
        payload: dict[str, Any],
    ) -> None:
        if self._journal is None:
            return
        self._journal.append_event(
            event_type=event_type,
            recorded_at_utc=self._now_provider(),
            decision_snapshot_id=decision_path.stem,
            cycle_correlation_id=f"cycle-{trade_intent.intent_id}",
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            symbol=trade_intent.symbol,
            side=trade_intent.side,
            payload=payload,
        )

    def _build_manual_risk_event(
        self,
        trade_intent: TradeIntent,
        *,
        control_code: str,
    ) -> RiskControlEvent:
        return RiskControlEvent(
            event_id=f"risk-{trade_intent.intent_id}",
            intent_id=trade_intent.intent_id,
            severity="warning",
            control_type=control_code,
            blocked=True,
            recorded_at_utc=self._now_provider(),
            operator_visible=True,
        )

    def _build_reconciliation(
        self,
        *,
        trade_intent: TradeIntent,
        portfolio_state: PortfolioState,
        differences: tuple[str, ...],
    ) -> ReconciliationSnapshot:
        return ReconciliationSnapshot(
            reconciliation_id=self._reconciliation_id(trade_intent.intent_id),
            portfolio_state=portfolio_state,
            broker_state_age_seconds=max(
                0,
                int((self._now_provider() - portfolio_state.as_of_utc).total_seconds()),
            ),
            differences=differences,
            resolved=True,
        )

    def _reconciliation_id(self, intent_id: str) -> str:
        return f"reconcile-{intent_id}"

    def _merge_order_records(self, accepted_order: Any, filled_order: Any) -> Any:
        return type(filled_order)(
            order_id=filled_order.order_id,
            client_order_id=accepted_order.client_order_id,
            symbol=filled_order.symbol,
            side=filled_order.side,
            status=filled_order.status,
            filled_qty=filled_order.filled_qty,
            filled_avg_price=filled_order.filled_avg_price,
        )

    def _dispatch_risk_alert(
        self,
        risk_event: RiskControlEvent,
        *,
        evidence_refs: tuple[str, ...],
    ) -> Path | None:
        alert = build_risk_control_alert(
            risk_event,
            evidence_refs=evidence_refs,
        )
        if self._alert_dispatcher is not None:
            alert = self._alert_dispatcher.dispatch(alert)
        self._metrics.record_operator_alert(alert.severity)
        self._metrics.record_evidence_artifact("operator_alert")
        return self._artifacts.write_operator_alert(alert)

    def _build_execution_lifecycle_record(
        self,
        *,
        trade_intent: TradeIntent,
        market_snapshot: MarketSnapshot,
        order_record: Any,
        recovered: bool,
    ) -> ExecutionLifecycleRecord:
        slippage = Decimal("0")
        market_reference_price = market_snapshot.last_trade_price
        if market_reference_price > Decimal("0"):
            slippage = (
                (order_record.filled_avg_price - market_reference_price)
                / market_reference_price
            ) * Decimal("10000")
        return ExecutionLifecycleRecord(
            execution_id=f"execution-{trade_intent.intent_id}",
            intent_id=trade_intent.intent_id,
            symbol=trade_intent.symbol,
            side=str(order_record.side),
            reason_code=trade_intent.reason_code,
            reference_price=market_reference_price,
            fill_price=order_record.filled_avg_price,
            filled_qty=order_record.filled_qty,
            slippage_bps=slippage,
            submitted_at_utc=trade_intent.generated_at_utc,
            filled_at_utc=self._now_provider(),
            recovered=recovered,
            bid_price=market_snapshot.bid_price,
            ask_price=market_snapshot.ask_price,
            average_daily_volume_30d=market_snapshot.average_daily_volume_30d,
        )

    def _write_closed_trade_record_if_available(
        self,
        *,
        trade_intent: TradeIntent,
        order_record: Any,
    ) -> Path | None:
        if trade_intent.side != "sell":
            return None
        closed_trades = self._artifacts.list_artifact_payloads("closed_trades")
        used_entry_ids = {
            str(payload.get("entry_intent_id", ""))
            for payload in closed_trades
            if str(payload.get("entry_intent_id", "")).strip()
        }
        candidate_entries = [
            payload
            for payload in self._artifacts.list_artifact_payloads(
                "execution_lifecycles"
            )
            if str(payload.get("symbol", "")) == trade_intent.symbol
            and str(payload.get("side", "")).lower() == "buy"
            and str(payload.get("intent_id", "")) not in used_entry_ids
        ]
        if not candidate_entries:
            return None
        entry_payload = max(
            candidate_entries,
            key=lambda payload: str(payload.get("filled_at_utc", "")),
        )
        entry_price = Decimal(str(entry_payload.get("fill_price", "0")))
        quantity = Decimal(str(order_record.filled_qty))
        gross_pnl = (order_record.filled_avg_price - entry_price) * quantity
        closed_trade = ClosedTradeRecord(
            trade_id=f"trade-{trade_intent.intent_id}",
            symbol=trade_intent.symbol,
            entry_intent_id=str(entry_payload.get("intent_id", "")),
            exit_intent_id=trade_intent.intent_id,
            opened_at_utc=datetime.fromisoformat(
                str(
                    entry_payload.get(
                        "filled_at_utc",
                        trade_intent.generated_at_utc.isoformat(),
                    )
                )
            ),
            closed_at_utc=self._now_provider(),
            quantity=quantity,
            entry_price=entry_price,
            exit_price=order_record.filled_avg_price,
            gross_pnl=gross_pnl,
            return_pct=(
                Decimal("0")
                if entry_price == Decimal("0")
                else (order_record.filled_avg_price - entry_price) / entry_price
            ),
            outcome="win" if gross_pnl > Decimal("0") else "loss",
            holding_period_seconds=max(
                0,
                int(
                    (
                        self._now_provider()
                        - datetime.fromisoformat(
                            str(
                                entry_payload.get(
                                    "filled_at_utc",
                                    trade_intent.generated_at_utc.isoformat(),
                                )
                            )
                        )
                    ).total_seconds()
                ),
            ),
        )
        return self._artifacts.write_closed_trade_record(closed_trade)


class StrategyEvaluationController:
    def __init__(
        self,
        *,
        adapter: Any,
        artifacts: FilesystemArtifactStore,
        alert_dispatcher: OperatorAlertDispatcher | None = None,
        metrics: StageMetrics | None = None,
    ) -> None:
        self._adapter = adapter
        self._artifacts = artifacts
        self._alert_dispatcher = alert_dispatcher
        self._metrics = metrics or StageMetrics()

    def evaluate_mandatory_candidates(
        self,
        *,
        benchmark_closes: tuple[Decimal, ...],
        window_start_utc: datetime,
        window_end_utc: datetime,
        universe: tuple[str, ...],
    ) -> tuple[EvaluationEvidencePack, ...]:
        evidence_packs: list[EvaluationEvidencePack] = []
        for candidate in build_mandatory_candidate_registry(universe):
            evidence_pack = self._adapter.evaluate_price_history(
                candidate,
                benchmark_closes=benchmark_closes,
                window_start_utc=window_start_utc,
                window_end_utc=window_end_utc,
            )
            evidence_path = self._artifacts.write_evaluation_evidence(evidence_pack)
            self._metrics.record_evidence_artifact("evaluation_evidence")
            if self._alert_dispatcher is not None:
                alert = self._alert_dispatcher.dispatch(
                    build_evaluation_summary_alert(
                        evidence_pack,
                        evidence_refs=(str(evidence_path),),
                    )
                )
                self._artifacts.write_operator_alert(alert)
                self._metrics.record_operator_alert(alert.severity)
                self._metrics.record_evidence_artifact("operator_alert")
            self._metrics.record_candidate_recommendation(evidence_pack.recommendation)
            evidence_packs.append(evidence_pack)
        return tuple(evidence_packs)


class GateValidationController:
    def __init__(
        self,
        *,
        artifacts: FilesystemArtifactStore,
        metrics: StageMetrics | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._metrics = metrics or StageMetrics()

    def generate_gate_report(
        self,
        *,
        gate_id: str,
        benchmark_closes: tuple[Decimal, ...],
        window_start_utc: datetime,
        window_end_utc: datetime,
        universe: tuple[str, ...],
        benchmark_series_is_adjusted: bool,
    ) -> GateReportResult:
        candidates = build_mandatory_candidate_registry(universe)
        benchmark_returns = close_to_close_returns(benchmark_closes)
        evidence_paths: list[Path] = []
        for candidate in candidates:
            evidence_pack = evaluate_candidate(
                candidate,
                candidate_returns=build_candidate_return_series(
                    candidate,
                    benchmark_closes,
                ),
                benchmark_returns=benchmark_returns,
                window_start_utc=window_start_utc,
                window_end_utc=window_end_utc,
            )
            evidence_path = self._artifacts.write_evaluation_evidence(evidence_pack)
            self._metrics.record_evidence_artifact("evaluation_evidence")
            self._metrics.record_candidate_recommendation(evidence_pack.recommendation)
            evidence_paths.append(evidence_path)

        report = build_gate_report(
            gate_id=gate_id,
            benchmark_closes=benchmark_closes,
            candidates=candidates,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            benchmark_series_is_adjusted=benchmark_series_is_adjusted,
        )
        report_path = self._artifacts.write_validation_report(report)
        self._metrics.record_evidence_artifact("validation_report")
        gate_assessment = GateAssessment(
            gate_id=gate_id,
            status=report.status,
            evidence_refs=tuple(str(path) for path in evidence_paths + [report_path]),
            decision_summary=report.summary,
            recorded_at_utc=window_end_utc,
        )
        gate_path = self._artifacts.write_gate_assessment(gate_assessment)
        self._metrics.record_evidence_artifact("gate_assessment")
        return GateReportResult(
            report=report,
            gate_assessment=gate_assessment,
            artifact_paths=tuple(evidence_paths + [report_path, gate_path]),
        )


def build_default_controller(config: TradingConfig) -> RoundTripController:
    trading_client = TradingClient(
        config.paper_credentials.api_key,
        config.paper_credentials.api_secret,
        paper=True,
    )
    return RoundTripController(
        market_data=AlpacaMarketDataGateway.from_credentials(
            api_key=config.paper_credentials.api_key,
            api_secret=config.paper_credentials.api_secret,
        ),
        execution=AlpacaPaperExecutionGateway(trading_client=trading_client),
        portfolio=AlpacaPortfolioGateway(trading_client=trading_client),
        risk=PaperOnlyRiskEngine(config),
    )


def build_default_paper_trading_controller(
    config: TradingConfig,
) -> PaperTradingLoopController:
    trading_client = TradingClient(
        config.paper_credentials.api_key,
        config.paper_credentials.api_secret,
        paper=True,
    )
    policy_snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime.now(UTC),
        artifact_root=config.runtime.artifact_root,
        git_sha=_resolve_git_sha(),
        dry_run=config.runtime.dry_run,
    )
    return PaperTradingLoopController(
        market_data=AlpacaMarketDataGateway.from_credentials(
            api_key=config.paper_credentials.api_key,
            api_secret=config.paper_credentials.api_secret,
        ),
        execution=AlpacaPaperExecutionGateway(trading_client=trading_client),
        portfolio=AlpacaPortfolioGateway(trading_client=trading_client),
        risk=PaperOnlyRiskEngine(config),
        strategy=DeterministicBaselineStrategy(),
        artifacts=FilesystemArtifactStore(config.runtime.artifact_root / "paper_loop"),
        metrics=StageMetrics(namespace=config.runtime.metrics_namespace),
        alert_dispatcher=build_alert_dispatcher(config),
        regular_hours_checker=AlpacaRegularHoursCalendar(trading_client).is_open,
        command_timeout_seconds=config.runtime.command_timeout_seconds,
        policy_snapshot=policy_snapshot,
        policy_store=PolicySnapshotStore(config.runtime.data_root / "policy"),
        snapshot_store=ContentAddressedSnapshotStore(
            config.runtime.data_root / "snapshots"
        ),
        journal=SqliteOmsJournal(config.runtime.data_root / "journal.db"),
        git_sha=_resolve_git_sha(),
        dry_run=config.runtime.dry_run,
    )


def build_default_gate_validation_controller(
    config: TradingConfig,
    *,
    artifact_root: Path,
) -> GateValidationController:
    return GateValidationController(
        artifacts=FilesystemArtifactStore(artifact_root),
        metrics=StageMetrics(namespace=config.runtime.metrics_namespace),
    )


def main() -> None:
    print(
        "TradingX Phase 0 scaffold is installed. "
        "Run `./scripts/validate` or the smoke test to exercise the paper round trip."
    )


def _resolve_git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _strategy_config_hash(strategy: DeterministicBaselineStrategy) -> str:
    payload = json.dumps(
        {
            "candidate_id": strategy.candidate_id,
            "max_spread_bps": str(strategy.max_spread_bps),
            "take_profit_bps": str(strategy.take_profit_bps),
            "stop_loss_bps": str(strategy.stop_loss_bps),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
