from __future__ import annotations

import hashlib
import json
import logging
import math
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce

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
    build_default_market_data_gateway,
    build_market_data_gateway_for_mode,
)
from tradingx.execution import (
    AlpacaPaperExecutionGateway,
    OrderRejected,
    OrderRouteAuthorityGuard,
    classify_order_rejection_reason,
)
from tradingx.promotion import (
    PromotionState,
    build_artifact_promotion_decision_provider,
)
from tradingx.experiments import MetricVisibilityContext
from tradingx.journal import SqliteOmsJournal, build_client_order_id
from tradingx.live_enablement import (
    build_trading_client_for_mode,
    resolve_broker_mode,
)
from tradingx.monitoring import StageMetrics
from tradingx.operator_control import OperatorControlStore
from tradingx.pbo import (
    DEFAULT_MIN_COHORT_SIZE,
    InsufficientCPCVCohortError,
    MixedCohortWindowError,
    cohort_window_id_for,
    compute_pbo,
)
from tradingx.persistence import FilesystemArtifactStore
from tradingx.policy import (
    PolicySnapshot,
    PolicySnapshotStore,
    build_week1_policy_snapshot,
)
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.risk import PaperOnlyRiskEngine, PreTradeRiskContext
from tradingx.runtime_logging import (
    StructuredRuntimeLogger,
    build_default_runtime_logger,
)
from tradingx.snapshots import (
    CandidateIntentSnapshot,
    ContentAddressedSnapshotStore,
    DecisionSnapshotV1,
)
from tradingx.strategy import (
    DeterministicBaselineStrategy,
    build_mandatory_candidate_registry,
)
from tradingx.trials import TrialsLedger
from tradingx.types import (
    BenchmarkStackPayload,
    ClosedTradeRecord,
    CPCVCohortWindowSummary,
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
from tradingx.validation import (
    _CPCV_CONFIG_FINGERPRINT,
    _CPCV_N_GROUPS,
    _CPCV_TEST_GROUP_COUNT,
    _run_cpcv_for_candidate,
    build_gate_report,
)

LOGGER = logging.getLogger(__name__)


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


def _parse_aware_utc_datetime(raw_value: str, *, field_name: str) -> datetime:
    timestamp = datetime.fromisoformat(raw_value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return timestamp.astimezone(UTC)


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
        operator_control_store: OperatorControlStore | None = None,
        runtime_logger: StructuredRuntimeLogger | None = None,
        universe_symbols: tuple[str, ...] | None = None,
        live_order_mode: bool = False,
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
        self._operator_control_store = operator_control_store
        self._runtime_logger = runtime_logger
        self._default_universe_snapshot_id = _universe_snapshot_id(
            universe_symbols or ()
        )
        self._live_order_mode = live_order_mode
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
        return self._execute_trade_intent_impl(
            trade_intent,
            market_snapshot=market_snapshot,
            portfolio_state=portfolio_state,
            default_quantity=quantity,
            strategy_fingerprint=_strategy_config_hash(self._strategy),
        )

    def execute_trade_intent(
        self,
        trade_intent: TradeIntent,
        *,
        market_snapshot: MarketSnapshot | None = None,
        portfolio_state: PortfolioState | None = None,
        default_quantity: Decimal = Decimal("0"),
        strategy_fingerprint: str | None = None,
        universe_snapshot_id: str | None = None,
    ) -> TradingLoopResult:
        resolved_portfolio_state = (
            portfolio_state or self._portfolio.get_portfolio_state()
        )
        if self._session_start_equity is None:
            self._session_start_equity = resolved_portfolio_state.equity
        resolved_market_snapshot = market_snapshot
        if resolved_market_snapshot is None and trade_intent.side in {
            "buy",
            "sell",
            "reduce",
        }:
            resolved_market_snapshot = self._market_data.get_market_snapshot(
                trade_intent.symbol
            )
        return self._execute_trade_intent_impl(
            trade_intent,
            market_snapshot=resolved_market_snapshot,
            portfolio_state=resolved_portfolio_state,
            default_quantity=default_quantity,
            strategy_fingerprint=strategy_fingerprint or trade_intent.candidate_id,
            universe_snapshot_id=universe_snapshot_id,
        )

    def _manual_halt_active(self) -> bool:
        manual_halt = getattr(self._risk, "is_manual_halt_active", None)
        if callable(manual_halt):
            return bool(manual_halt())
        runtime_config = getattr(getattr(self._risk, "_config", None), "runtime", None)
        return bool(getattr(runtime_config, "manual_kill_switch_active", False))

    def _execute_trade_intent_impl(
        self,
        trade_intent: TradeIntent,
        *,
        market_snapshot: MarketSnapshot | None,
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
        strategy_fingerprint: str,
        universe_snapshot_id: str | None = None,
    ) -> TradingLoopResult:
        trade_path = self._artifacts.write_trade_intent(trade_intent)
        self._metrics.record_evidence_artifact("trade_intent")
        self._metrics.record_live_disable_state(True)
        self._metrics.record_manual_halt_state(self._manual_halt_active())

        if trade_intent.side not in {"buy", "sell", "reduce"}:
            decision_path = self._write_decision_snapshot(
                trade_intent=trade_intent,
                session_start_equity=portfolio_state.equity,
                risk_verdict_id="not_applicable",
                final_action="no_action",
                strategy_fingerprint=strategy_fingerprint,
                universe_snapshot_id=universe_snapshot_id,
            )
            self._log_runtime_event(
                event_type="decision_recorded",
                severity="info",
                message="Decision snapshot recorded with no actionable trade.",
                decision_path=decision_path,
                trade_intent=trade_intent,
                fields={"final_action": "no_action"},
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

        operator_state = (
            self._operator_control_store.read_state()
            if self._operator_control_store is not None
            else None
        )
        if (
            operator_state is not None
            and trade_intent.side == "buy"
            and operator_state.halt_requested
        ):
            risk_event = self._build_manual_risk_event(
                trade_intent,
                control_code="operator_halt",
            )
            decision_path = self._write_decision_snapshot(
                trade_intent=trade_intent,
                session_start_equity=portfolio_state.equity,
                risk_verdict_id=risk_event.event_id,
                final_action="blocked",
                strategy_fingerprint=strategy_fingerprint,
                universe_snapshot_id=universe_snapshot_id,
            )
            self._log_runtime_event(
                event_type="decision_recorded",
                severity="warning",
                message="Decision snapshot recorded and blocked by operator halt.",
                decision_path=decision_path,
                trade_intent=trade_intent,
                fields={"final_action": "blocked", "control_type": "operator_halt"},
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
                strategy_fingerprint=strategy_fingerprint,
                universe_snapshot_id=universe_snapshot_id,
            )
            self._log_runtime_event(
                event_type="decision_recorded",
                severity="warning",
                message="Decision snapshot recorded outside regular hours.",
                decision_path=decision_path,
                trade_intent=trade_intent,
                fields={
                    "final_action": "blocked",
                    "control_type": "outside_regular_hours",
                },
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

        if market_snapshot is None:
            raise RuntimeError(
                "Market snapshot is required for actionable trade intent "
                f"{trade_intent.intent_id}."
            )

        risk_decision = self._risk.evaluate_trade_intent(
            trade_intent,
            market_snapshot,
            portfolio_state,
            broker_state_timestamp=portfolio_state.as_of_utc,
            is_live_order=self._live_order_mode,
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
            strategy_fingerprint=strategy_fingerprint,
            universe_snapshot_id=universe_snapshot_id,
        )
        self._log_runtime_event(
            event_type="decision_recorded",
            severity="info",
            message="Decision snapshot persisted before OMS handling.",
            decision_path=decision_path,
            trade_intent=trade_intent,
            fields={
                "final_action": (
                    "blocked"
                    if risk_decision.event is not None
                    else ("dry_run" if self._dry_run else trade_intent.side)
                ),
            },
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
            self._log_runtime_event(
                event_type="blocked_intent",
                severity="warning",
                message="Trade intent blocked by risk controls.",
                decision_path=decision_path,
                trade_intent=trade_intent,
                fields={"control_type": risk_decision.control_code},
            )
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
            would_submit_limit_price = (
                str(
                    self._marketable_limit_price(
                        trade_intent=trade_intent,
                        market_snapshot=market_snapshot,
                    )
                )
                if trade_intent.side in {"buy", "sell"}
                else ""
            )
            reference_price = (
                str(market_snapshot.ask_price)
                if trade_intent.side == "buy"
                else (
                    str(market_snapshot.bid_price)
                    if trade_intent.side == "sell"
                    else ""
                )
            )
            self._append_journal_event(
                event_type="simulated",
                decision_path=decision_path,
                trade_intent=trade_intent,
                client_order_id=client_order_id,
                broker_order_id="",
                payload={
                    "side": trade_intent.side,
                    "quantity": str(trade_intent.quantity or default_quantity),
                    "reason_code": trade_intent.reason_code,
                    "reference_price": reference_price,
                    "would_submit_limit_price": would_submit_limit_price,
                },
            )
            self._log_runtime_event(
                event_type="dry_run_simulated",
                severity="info",
                message=(
                    "Dry-run simulated order path recorded without broker "
                    "submission."
                ),
                decision_path=decision_path,
                trade_intent=trade_intent,
                fields={
                    "reference_price": reference_price,
                    "would_submit_limit_price": would_submit_limit_price,
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
        execution_quantity = trade_intent.quantity or default_quantity
        try:
            if existing_order is None:
                existing_order = self._find_existing_order_by_client_id(client_order_id)
                if existing_order is not None:
                    recovered = True
                    self._log_runtime_event(
                        event_type="order_recovered",
                        severity="warning",
                        message=(
                            "Recovered existing broker order by deterministic "
                            "client_order_id."
                        ),
                        decision_path=decision_path,
                        trade_intent=trade_intent,
                        fields={"client_order_id": existing_order.client_order_id},
                    )
                    self._append_journal_event(
                        event_type="ack",
                        decision_path=decision_path,
                        trade_intent=trade_intent,
                        client_order_id=existing_order.client_order_id,
                        broker_order_id=existing_order.order_id,
                        payload={
                            "status": existing_order.status,
                            "recovered_via_client_order_id": True,
                        },
                    )
                    order_path = self._artifacts.write_order_record(
                        trade_intent.intent_id,
                        existing_order,
                    )
                    self._metrics.record_evidence_artifact("order")
                else:
                    self._log_runtime_event(
                        event_type="submit_attempt",
                        severity="info",
                        message="Submitting order to broker.",
                        decision_path=decision_path,
                        trade_intent=trade_intent,
                        fields={"client_order_id": client_order_id},
                    )
                    self._append_journal_event(
                        event_type="submit_attempt",
                        decision_path=decision_path,
                        trade_intent=trade_intent,
                        client_order_id=client_order_id,
                        broker_order_id="",
                        payload={"reason_code": trade_intent.reason_code},
                    )
                    existing_order = self._submit_entry_or_exit_order(
                        trade_intent=trade_intent,
                        market_snapshot=market_snapshot,
                        symbol=trade_intent.symbol,
                        quantity=execution_quantity,
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
        except OrderRejected as error:
            return self._build_rejected_trade_result(
                trade_intent=trade_intent,
                portfolio_state=portfolio_state,
                decision_path=decision_path,
                trade_path=trade_path,
                error=error,
            )
        order_record = self._merge_order_records(existing_order, order_record)
        self._artifacts.write_order_record(trade_intent.intent_id, order_record)
        self._log_runtime_event(
            event_type="fill_recorded",
            severity="info",
            message="Broker order reached filled state.",
            decision_path=decision_path,
            trade_intent=trade_intent,
            fields={
                "broker_order_id": order_record.order_id,
                "filled_qty": order_record.filled_qty,
                "filled_avg_price": order_record.filled_avg_price,
            },
        )
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
        closed_trade_paths = self._write_closed_trade_records_if_available(
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
                    *closed_trade_paths,
                )
                if path is not None
            ),
            recovered=recovered,
        )

    def _build_rejected_trade_result(
        self,
        *,
        trade_intent: TradeIntent,
        portfolio_state: PortfolioState,
        decision_path: Path,
        trade_path: Path,
        error: OrderRejected,
    ) -> TradingLoopResult:
        rejection_message = str(error)
        reason_code = classify_order_rejection_reason(rejection_message)
        self._log_runtime_event(
            event_type="submit_rejected",
            severity="error",
            message="Broker rejected order submission.",
            decision_path=decision_path,
            trade_intent=trade_intent,
            fields={"reason_code": reason_code},
        )
        self._append_journal_event(
            event_type="reject",
            decision_path=decision_path,
            trade_intent=trade_intent,
            client_order_id=build_client_order_id(
                decision_snapshot_id=decision_path.stem,
                symbol=trade_intent.symbol,
                side=trade_intent.side,
                intent_seq=0,
            ),
            broker_order_id="",
            payload={
                "reason_code": reason_code,
                "message": rejection_message,
            },
        )
        force_reconciliation = reason_code == "insufficient_buying_power"
        reconciliation = self._build_reconciliation(
            trade_intent=trade_intent,
            portfolio_state=portfolio_state,
            differences=(reason_code,),
            resolved=not force_reconciliation,
        )
        reconciliation_path = self._artifacts.write_reconciliation_snapshot(
            reconciliation
        )
        self._metrics.record_evidence_artifact("reconciliation")
        self._metrics.record_trade_terminal_state("rejected")
        self._metrics.record_reconciliation_age_seconds(
            reconciliation.broker_state_age_seconds
        )
        return TradingLoopResult(
            terminal_state="rejected",
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
        strategy_fingerprint: str,
        universe_snapshot_id: str | None = None,
    ) -> Path:
        if self._snapshot_store is None or self._policy_snapshot is None:
            return self._artifacts.write_trade_intent(trade_intent)
        snapshot = DecisionSnapshotV1(
            schema_version=1,
            timestamp_utc=self._now_provider(),
            cycle_correlation_id=f"cycle-{trade_intent.intent_id}",
            session_snapshot_id=self._policy_snapshot.policy_snapshot_id,
            universe_snapshot_id=(
                universe_snapshot_id
                or self._default_universe_snapshot_id
                or _universe_snapshot_id((trade_intent.symbol,))
            ),
            policy_snapshot_id=self._policy_snapshot.policy_snapshot_id,
            model_snapshot_id=trade_intent.candidate_id,
            strategy_version=trade_intent.candidate_id,
            strategy_config_hash=strategy_fingerprint,
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
                        "pending" if risk_verdict_id == "risk-approved" else "blocked"
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

    def _log_runtime_event(
        self,
        *,
        event_type: str,
        severity: str,
        message: str,
        decision_path: Path,
        trade_intent: TradeIntent,
        fields: dict[str, Any] | None = None,
    ) -> None:
        if self._runtime_logger is None:
            return
        payload: dict[str, Any] = {
            "symbol": trade_intent.symbol,
            "side": trade_intent.side,
            "reason_code": trade_intent.reason_code,
        }
        if fields is not None:
            payload.update(fields)
        self._runtime_logger.log(
            event_type=event_type,
            severity=severity,
            message=message,
            decision_snapshot_id=decision_path.stem,
            cycle_correlation_id=f"cycle-{trade_intent.intent_id}",
            fields=payload,
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
        resolved: bool = True,
    ) -> ReconciliationSnapshot:
        return ReconciliationSnapshot(
            reconciliation_id=self._reconciliation_id(trade_intent.intent_id),
            portfolio_state=portfolio_state,
            broker_state_age_seconds=max(
                0,
                int((self._now_provider() - portfolio_state.as_of_utc).total_seconds()),
            ),
            differences=differences,
            resolved=resolved,
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
            sleeve_attributions=trade_intent.sleeve_attributions,
        )

    def _marketable_limit_price(
        self,
        *,
        trade_intent: TradeIntent,
        market_snapshot: MarketSnapshot,
    ) -> Decimal:
        if self._policy_snapshot is None:
            buffer_bps = Decimal("10")
        elif trade_intent.side == "buy":
            buffer_bps = self._policy_snapshot.entry_marketable_limit_bps
        else:
            buffer_bps = self._policy_snapshot.exit_marketable_limit_bps
        if trade_intent.side == "buy":
            reference_price = market_snapshot.ask_price
            multiplier = Decimal("1") + (buffer_bps / Decimal("10000"))
        else:
            reference_price = market_snapshot.bid_price
            multiplier = Decimal("1") - (buffer_bps / Decimal("10000"))
        return (reference_price * multiplier).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    def _find_existing_order_by_client_id(
        self,
        client_order_id: str,
    ) -> Any | None:
        finder = getattr(self._execution, "find_order_by_client_id", None)
        if callable(finder):
            return finder(client_order_id)
        return None

    def _submit_entry_or_exit_order(
        self,
        trade_intent: TradeIntent,
        market_snapshot: MarketSnapshot,
        symbol: str,
        quantity: Decimal,
        client_order_id: str,
    ) -> Any:
        submit_marketable_limit_order = getattr(
            self._execution,
            "submit_marketable_limit_order",
            None,
        )
        side = OrderSide.BUY if trade_intent.side == "buy" else OrderSide.SELL
        if callable(submit_marketable_limit_order):
            return submit_marketable_limit_order(
                symbol,
                quantity,
                side,
                limit_price=self._marketable_limit_price(
                    trade_intent=trade_intent,
                    market_snapshot=market_snapshot,
                ),
                time_in_force=TimeInForce.DAY,
                client_order_id=client_order_id,
            )
        return self._execution.submit_market_order(
            symbol,
            quantity,
            side,
            client_order_id=client_order_id,
        )

    def _write_closed_trade_records_if_available(
        self,
        *,
        trade_intent: TradeIntent,
        order_record: Any,
    ) -> tuple[Path, ...]:
        if trade_intent.side != "sell":
            return ()
        closed_trades = self._artifacts.list_artifact_payloads("closed_trades")
        consumed_quantities: dict[str, Decimal] = {}
        for payload in closed_trades:
            entry_intent_id = str(payload.get("entry_intent_id", "")).strip()
            if not entry_intent_id:
                continue
            consumed_quantities[entry_intent_id] = consumed_quantities.get(
                entry_intent_id,
                Decimal("0"),
            ) + Decimal(str(payload.get("quantity", "0")))
        candidate_entries = sorted(
            [
                payload
                for payload in self._artifacts.list_artifact_payloads(
                    "execution_lifecycles"
                )
                if str(payload.get("symbol", "")) == trade_intent.symbol
                and str(payload.get("side", "")).lower() == "buy"
            ],
            key=lambda payload: (
                str(payload.get("filled_at_utc", "")),
                str(payload.get("intent_id", "")),
            ),
        )
        if not candidate_entries:
            return ()
        remaining_exit_quantity = Decimal(str(order_record.filled_qty))
        paths: list[Path] = []
        for entry_payload in candidate_entries:
            if remaining_exit_quantity <= Decimal("0"):
                break
            entry_intent_id = str(entry_payload.get("intent_id", ""))
            entry_quantity = Decimal(str(entry_payload.get("filled_qty", "0")))
            entry_remaining = entry_quantity - consumed_quantities.get(
                entry_intent_id,
                Decimal("0"),
            )
            if entry_remaining <= Decimal("0"):
                continue
            matched_quantity = min(entry_remaining, remaining_exit_quantity)
            entry_price = Decimal(str(entry_payload.get("fill_price", "0")))
            opened_at_utc = _parse_aware_utc_datetime(
                str(
                    entry_payload.get(
                        "filled_at_utc",
                        trade_intent.generated_at_utc.isoformat(),
                    )
                ),
                field_name="filled_at_utc",
            )
            gross_pnl = (order_record.filled_avg_price - entry_price) * matched_quantity
            closed_trade = ClosedTradeRecord(
                trade_id=f"trade-{trade_intent.intent_id}-{entry_intent_id}",
                symbol=trade_intent.symbol,
                entry_intent_id=entry_intent_id,
                exit_intent_id=trade_intent.intent_id,
                opened_at_utc=opened_at_utc,
                closed_at_utc=self._now_provider(),
                quantity=matched_quantity,
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
                    int((self._now_provider() - opened_at_utc).total_seconds()),
                ),
                entry_sleeve_attributions=tuple(
                    (str(item[0]), Decimal(str(item[1])))
                    for item in entry_payload.get("sleeve_attributions", ())
                ),
                exit_sleeve_attributions=trade_intent.sleeve_attributions,
            )
            paths.append(self._artifacts.write_closed_trade_record(closed_trade))
            remaining_exit_quantity -= matched_quantity
        return tuple(paths)


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
        market_data: Any,
        metrics: StageMetrics | None = None,
        trials_ledger: TrialsLedger | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._market_data = market_data
        self._metrics = metrics or StageMetrics()
        self._trials_ledger = trials_ledger

    def generate_gate_report(
        self,
        *,
        gate_id: str,
        benchmark_stack_payload: BenchmarkStackPayload,
        window_start_utc: datetime,
        window_end_utc: datetime,
        universe: tuple[str, ...],
        metric_visibility_context: MetricVisibilityContext | None = None,
        dataset_manifest_id: str | None = None,
    ) -> GateReportResult:
        candidates = build_mandatory_candidate_registry(universe)
        metrics_blocked = (
            metric_visibility_context is not None
            and metric_visibility_context.promotion_valid
            and not metric_visibility_context.is_released
        )
        if metrics_blocked:
            report = build_gate_report(
                gate_id=gate_id,
                bars_by_symbol={},
                candidates=candidates,
                benchmark_stack_payload=benchmark_stack_payload,
                window_start_utc=window_start_utc,
                window_end_utc=window_end_utc,
                gate1_pbo_payload=None,
                trials_ledger=None,
                metric_visibility_context=metric_visibility_context,
                dataset_manifest_id=dataset_manifest_id,
            )
            return self._persist_gate_report_result(report, gate_id=gate_id)
        required_symbols = {candidate.benchmark_symbol for candidate in candidates} | {
            symbol for candidate in candidates for symbol in candidate.universe
        }
        bars_by_symbol = {
            symbol: self._market_data.get_daily_bar_history(
                symbol,
                start_utc=window_start_utc,
                end_utc=window_end_utc,
            )
            for symbol in sorted(required_symbols)
        }
        if gate_id == "1":
            for candidate in candidates:
                try:
                    _run_cpcv_for_candidate(
                        candidate=candidate,
                        bars_by_symbol=bars_by_symbol,
                        window_start_utc=window_start_utc,
                        window_end_utc=window_end_utc,
                        artifact_store=self._artifacts,
                    )
                except Exception:
                    LOGGER.exception(
                        "criterion: cpcv_run_failed gate_id=%s candidate_id=%s",
                        gate_id,
                        candidate.candidate_id,
                    )
        gate1_pbo_payload = self._gate1_pbo_activation_payload(
            gate_id=gate_id,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
        )
        report = build_gate_report(
            gate_id=gate_id,
            bars_by_symbol=bars_by_symbol,
            candidates=candidates,
            benchmark_stack_payload=benchmark_stack_payload,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            gate1_pbo_payload=gate1_pbo_payload,
            trials_ledger=self._trials_ledger,
            metric_visibility_context=metric_visibility_context,
            dataset_manifest_id=dataset_manifest_id,
        )
        return self._persist_gate_report_result(report, gate_id=gate_id)

    def _persist_gate_report_result(
        self,
        report: Any,
        *,
        gate_id: str,
    ) -> GateReportResult:
        report_path = self._artifacts.write_validation_report(report)
        self._metrics.record_evidence_artifact("validation_report")
        assessment = GateAssessment(
            gate_id=gate_id,
            status=report.status,
            evidence_refs=(str(report_path),),
            decision_summary=report.summary,
            recorded_at_utc=datetime.now(UTC),
            promotion_valid=report.promotion_valid,
            evidence_class=report.evidence_class,
            blocker_codes=report.blocker_codes,
            experiment_id=report.experiment_id,
            run_id=report.run_id,
            dataset_manifest_id=report.dataset_manifest_id,
        )
        assessment_path = self._artifacts.write_gate_assessment(assessment)
        self._metrics.record_evidence_artifact("gate_assessment")
        return GateReportResult(
            report=report,
            gate_assessment=assessment,
            artifact_paths=(report_path, assessment_path),
        )

    def _gate1_pbo_activation_payload(
        self,
        *,
        gate_id: str,
        window_start_utc: datetime,
        window_end_utc: datetime,
    ) -> tuple[Decimal, str] | None:
        if gate_id != "1":
            return None

        summaries = self._artifacts.list_cpcv_cohort_windows()
        current_cohort_window_id = cohort_window_id_for(
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            cpcv_config_fingerprint=_CPCV_CONFIG_FINGERPRINT,
        )
        maturity_cutoff = datetime.now(UTC) - timedelta(days=182)
        if not any(
            summary.earliest_recorded_at_utc <= maturity_cutoff for summary in summaries
        ):
            LOGGER.info(
                "criterion: pbo_cohort_insufficient gate_id=%s "
                "cohort_window_id=%s reason=no_mature_cohort",
                gate_id,
                current_cohort_window_id,
            )
            return None

        current_summary = next(
            (
                summary
                for summary in summaries
                if summary.cohort_window_id == current_cohort_window_id
            ),
            None,
        )
        if not self._current_cohort_is_ready(
            current_summary=current_summary,
            current_cohort_window_id=current_cohort_window_id,
            gate_id=gate_id,
        ):
            return None

        records = self._artifacts.list_cpcv_trial_records(
            cohort_window_id=current_cohort_window_id
        )
        run_timestamp = datetime.now(UTC)
        run_nonce = f"{time.time_ns():x}"[-8:]
        evaluation_id = (
            f"gate1-{run_timestamp.strftime('%Y%m%dT%H%M%S.%fZ')}-"
            f"{run_nonce}-{current_cohort_window_id}"
        )
        try:
            report = compute_pbo(
                cpcv_records=records,
                evaluation_id=evaluation_id,
                generated_at_utc=run_timestamp,
            )
        except InsufficientCPCVCohortError:
            LOGGER.info(
                "criterion: pbo_cohort_insufficient gate_id=%s "
                "cohort_window_id=%s reason=compute_pbo_insufficient",
                gate_id,
                current_cohort_window_id,
            )
            return None
        except MixedCohortWindowError:
            LOGGER.exception(
                "criterion: pbo_cohort_integrity_failed gate_id=%s "
                "cohort_window_id=%s",
                gate_id,
                current_cohort_window_id,
            )
            raise

        self._artifacts.write_pbo_report(report)
        self._metrics.record_evidence_artifact("pbo_report")
        return (report.pbo_value, report.report_id)

    def _current_cohort_is_ready(
        self,
        *,
        current_summary: CPCVCohortWindowSummary | None,
        current_cohort_window_id: str,
        gate_id: str,
    ) -> bool:
        required_path_count = math.comb(_CPCV_N_GROUPS, _CPCV_TEST_GROUP_COUNT)
        if current_summary is None:
            LOGGER.info(
                "criterion: pbo_cohort_insufficient gate_id=%s "
                "cohort_window_id=%s reason=current_cohort_missing",
                gate_id,
                current_cohort_window_id,
            )
            return False
        if current_summary.strategy_config_count < DEFAULT_MIN_COHORT_SIZE:
            LOGGER.info(
                "criterion: pbo_cohort_insufficient gate_id=%s "
                "cohort_window_id=%s reason=current_cohort_too_small "
                "strategy_config_count=%s required=%s",
                gate_id,
                current_cohort_window_id,
                current_summary.strategy_config_count,
                DEFAULT_MIN_COHORT_SIZE,
            )
            return False
        if current_summary.path_count != required_path_count:
            LOGGER.info(
                "criterion: pbo_cohort_insufficient gate_id=%s "
                "cohort_window_id=%s reason=current_cohort_incomplete "
                "path_count=%s required=%s",
                gate_id,
                current_cohort_window_id,
                current_summary.path_count,
                required_path_count,
            )
            return False
        return True


def build_default_controller(config: TradingConfig) -> RoundTripController:
    """Backwards-compatible alias for the legacy paper roundtrip controller.

    The legacy non-V5 paper roundtrip lives in
    :mod:`tradingx.legacy_paper_roundtrip` so the ``legacy_paper_non_authority``
    flag is concentrated in a single, clearly-labeled legacy module
    (Defect 2).
    """

    from tradingx.legacy_paper_roundtrip import (
        build_legacy_paper_roundtrip_controller,
    )

    return build_legacy_paper_roundtrip_controller(config)


def build_default_paper_trading_controller(
    config: TradingConfig,
) -> PaperTradingLoopController:
    return build_default_trading_loop_controller(config, broker_mode="paper")


def _required_state_for_broker_mode(broker_mode: str) -> PromotionState:
    """Map a broker_mode label onto the V5 promotion state it requires.

    Defect 2 requires production runtime routes to enforce the matching
    promotion state — not the historical paper-non-authority bypass.
    """

    normalized = broker_mode.strip().lower()
    if normalized == "live":
        return PromotionState.PRODUCTION
    if normalized == "live_probe":
        return PromotionState.TINY_LIVE_PROBE
    return PromotionState.PAPER_TRADING


def _route_label_for_broker_mode(broker_mode: str) -> str:
    normalized = broker_mode.strip().lower()
    if normalized == "live":
        return "live_order"
    if normalized == "live_probe":
        return "live_probe_order"
    return "paper_order"


def _build_default_authority_guard(
    config: TradingConfig,
    *,
    broker_mode: str,
) -> OrderRouteAuthorityGuard:
    """Wire the V5 authority guard for a runtime route.

    Sources the promotion decision from
    ``config.runtime.artifact_root / "promotion"``. Bundles that are
    missing or fail authority validation will fail-closed at order
    submission via :class:`OrderRouteAuthorityError`.
    """

    promotion_root = config.runtime.artifact_root / "promotion"
    decision_provider = build_artifact_promotion_decision_provider(promotion_root)
    return OrderRouteAuthorityGuard(
        decision_provider=decision_provider,
        required_state=_required_state_for_broker_mode(broker_mode),
        route_label=_route_label_for_broker_mode(broker_mode),
    )


def build_default_trading_loop_controller(
    config: TradingConfig,
    *,
    broker_mode: str | None = None,
    strategy_id: str = "trend-following-v1",
) -> PaperTradingLoopController:
    decision = resolve_broker_mode(config, explicit_mode=broker_mode)
    trading_client = build_trading_client_for_mode(config, decision)
    market_data_gateway = build_market_data_gateway_for_mode(
        config,
        broker_mode=decision.requested_mode,
    )
    policy_snapshot = build_week1_policy_snapshot(
        generated_at_utc=datetime.now(UTC),
        artifact_root=config.runtime.artifact_root,
        git_sha=_resolve_git_sha(),
        dry_run=config.runtime.dry_run,
    )
    authority_guard = _build_default_authority_guard(
        config,
        broker_mode=decision.effective_mode,
    )
    return PaperTradingLoopController(
        market_data=market_data_gateway,
        execution=AlpacaPaperExecutionGateway(
            trading_client=trading_client,
            authority_guard=authority_guard,
            strategy_id=strategy_id,
        ),
        portfolio=AlpacaPortfolioGateway(trading_client=trading_client),
        risk=PaperOnlyRiskEngine(config),
        strategy=DeterministicBaselineStrategy(),
        artifacts=FilesystemArtifactStore(config.runtime.artifact_root / "paper_loop"),
        metrics=StageMetrics(namespace=config.runtime.metrics_namespace),
        alert_dispatcher=build_alert_dispatcher(config),
        regular_hours_checker=AlpacaRegularHoursCalendar().is_open,
        command_timeout_seconds=config.runtime.command_timeout_seconds,
        policy_snapshot=policy_snapshot,
        policy_store=PolicySnapshotStore(config.runtime.data_root / "policy"),
        snapshot_store=ContentAddressedSnapshotStore(
            config.runtime.data_root / "snapshots"
        ),
        journal=SqliteOmsJournal(config.runtime.data_root / "journal.db"),
        git_sha=_resolve_git_sha(),
        dry_run=config.runtime.dry_run,
        operator_control_store=OperatorControlStore(
            config.runtime.data_root / "control"
        ),
        runtime_logger=build_default_runtime_logger(config, component="controller"),
        universe_symbols=config.runtime.symbol_universe,
        live_order_mode=decision.effective_mode == "live",
    )


def build_default_gate_validation_controller(
    config: TradingConfig,
    *,
    artifact_root: Path,
) -> GateValidationController:
    return GateValidationController(
        artifacts=FilesystemArtifactStore(artifact_root),
        market_data=build_default_market_data_gateway(config),
        metrics=StageMetrics(namespace=config.runtime.metrics_namespace),
        trials_ledger=TrialsLedger(
            database_path=config.runtime.data_root / "validation" / "trials.db"
        ),
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


def _universe_snapshot_id(symbols: tuple[str, ...]) -> str:
    normalized = tuple(
        sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    )
    if not normalized:
        return "universe-empty"
    return "universe-" + "-".join(symbol.lower() for symbol in normalized)


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
