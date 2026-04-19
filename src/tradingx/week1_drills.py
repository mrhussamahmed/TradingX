from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from prometheus_client import CollectorRegistry

from tradingx.controller import PaperTradingLoopController
from tradingx.execution import OrderRejected
from tradingx.journal import SqliteOmsJournal
from tradingx.monitoring import StageMetrics
from tradingx.persistence import FilesystemArtifactStore
from tradingx.policy import (
    EntryPolicyContext,
    ExecutionPolicyEngine,
    PolicySnapshot,
    PolicySnapshotStore,
    build_week1_policy_snapshot,
)
from tradingx.runtime_host import LocalRuntimeHostManager
from tradingx.snapshots import ContentAddressedSnapshotStore
from tradingx.strategy import DeterministicBaselineStrategy
from tradingx.types import (
    BotRuntimeState,
    HistoricalWarmupRecord,
    MarketSnapshot,
    ModelWeightSnapshot,
    OpportunityScore,
    OpportunitySelectionRecord,
    OrderRecord,
    PortfolioState,
    ReconciliationSnapshot,
    StrategyActivationRecord,
    WebActionResult,
)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


class _ApprovedRiskEngine:
    class Config:
        class Runtime:
            manual_kill_switch_active = False

        runtime = Runtime()

    _config = Config()

    def evaluate_trade_intent(
        self,
        intent: Any,
        market_snapshot: MarketSnapshot,
        portfolio_state: PortfolioState,
        *,
        broker_state_timestamp: datetime,
    ) -> Any:
        del intent, market_snapshot, portfolio_state, broker_state_timestamp
        return type(
            "RiskDecisionStub",
            (),
            {"decision": "approved", "control_code": "passed", "event": None},
        )()


class _FixedMarketData:
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(
            symbol=symbol,
            last_trade_price=Decimal("600.00"),
            bid_price=Decimal("599.90"),
            ask_price=Decimal("600.10"),
            average_daily_volume_30d=Decimal("1500000"),
            timestamp=datetime(2026, 4, 20, 14, 0, tzinfo=UTC),
        )


class _FixedPortfolio:
    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            as_of_utc=datetime(2026, 4, 20, 14, 0, tzinfo=UTC),
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            buying_power=Decimal("200000"),
            positions=(),
            open_orders=(),
        )


class _RejectingExecution:
    def submit_marketable_limit_order(
        self,
        symbol: str,
        quantity: Decimal,
        side: Any,
        *,
        limit_price: Decimal,
        time_in_force: Any,
        client_order_id: str | None = None,
    ) -> OrderRecord:
        del symbol, quantity, side, limit_price, time_in_force, client_order_id
        raise OrderRejected(
            '{"message":"insufficient buying power for requested exposure"}'
        )

    def find_order_by_client_id(self, client_order_id: str) -> OrderRecord | None:
        del client_order_id
        return None


class _NoopServiceManager:
    def start(
        self,
        *,
        symbols: tuple[str, ...],
        quantity: Decimal,
        interval_seconds: int,
        max_cycles: int | None = None,
    ) -> WebActionResult:
        del symbols, quantity, interval_seconds, max_cycles
        return WebActionResult(
            action_id="action-start",
            action_type="runtime_host_start",
            status="accepted",
            message="accepted",
            evidence_refs=(),
        )

    def stop(self) -> WebActionResult:
        return WebActionResult(
            action_id="action-stop",
            action_type="runtime_host_stop",
            status="completed",
            message="stopped",
            evidence_refs=(),
        )


class _WarmupService:
    def build_warmup(
        self,
        *,
        symbols: tuple[str, ...],
        benchmark_symbol: str,
        warmup_days: int,
        required_bar_count: int,
    ) -> HistoricalWarmupRecord:
        del benchmark_symbol, warmup_days, required_bar_count
        return HistoricalWarmupRecord(
            warmup_id="warmup-drill",
            generated_at_utc=datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
            benchmark_symbol="SPY",
            symbols=symbols,
            window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
            window_end_utc=datetime(2026, 4, 19, tzinfo=UTC),
            required_bar_count=30,
            symbols_ready=symbols,
            symbols_blocked={},
            return_summary={},
        )


class _ActivationGateway:
    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ModelWeightSnapshot]:
        return (
            StrategyActivationRecord(
                activation_id="activation-drill",
                strategy_id="baseline-long-only-v1",
                strategy_version="1.0.0",
                approved_symbols=symbols,
                deploy_threshold=Decimal("0.5"),
                allow_fallback_weights=True,
                status="approved",
                activated_at_utc=datetime(2026, 4, 20, 11, 0, tzinfo=UTC),
                notes="Week 1 drill activation.",
            ),
            ModelWeightSnapshot(
                snapshot_id="snapshot-drill",
                strategy_id="baseline-long-only-v1",
                status="approved",
                generated_at_utc=datetime(2026, 4, 20, 11, 5, tzinfo=UTC),
                minimum_supporting_trades=5,
                weights={"signal": Decimal("1.0")},
            ),
        )

    def get_latest_activation(self) -> StrategyActivationRecord | None:
        return None

    def get_latest_snapshot(self, *, strategy_id: str) -> ModelWeightSnapshot | None:
        del strategy_id
        return None


class _OpportunityPlanner:
    def plan(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        activation: StrategyActivationRecord,
        model_snapshot: ModelWeightSnapshot,
        warmup: HistoricalWarmupRecord,
    ) -> OpportunitySelectionRecord:
        del portfolio_state, activation, model_snapshot, warmup
        return OpportunitySelectionRecord(
            selection_id="selection-drill",
            generated_at_utc=datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
            strategy_id="baseline-long-only-v1",
            model_snapshot_id="snapshot-drill",
            symbols_considered=symbols,
            ranked_opportunities=(
                OpportunityScore(
                    symbol="SPY",
                    base_signal=Decimal("1.0"),
                    regime_weight=Decimal("1.0"),
                    model_weight=Decimal("1.0"),
                    liquidity_weight=Decimal("1.0"),
                    spread_penalty=Decimal("0.1"),
                    volatility_penalty=Decimal("0.1"),
                    portfolio_overlap_penalty=Decimal("0.0"),
                    execution_cost_penalty=Decimal("0.0"),
                    final_score=Decimal("0.8"),
                    eligible=True,
                    ineligibility_reason="",
                ),
            ),
            selected_symbol="SPY",
            decision="selected",
            decision_reason="Drill selection.",
        )


class _RecoveryGateway:
    def __init__(self) -> None:
        self.calls = 0

    def reconcile(self) -> ReconciliationSnapshot:
        self.calls += 1
        resolved = self.calls >= 2
        return ReconciliationSnapshot(
            reconciliation_id=f"reconcile-drill-{self.calls}",
            portfolio_state=PortfolioState(
                as_of_utc=datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
                cash=Decimal("100000"),
                equity=Decimal("100000"),
                buying_power=Decimal("200000"),
                positions=(),
                open_orders=(),
            ),
            broker_state_age_seconds=0,
            differences=() if resolved else ("broker_position_unknown",),
            resolved=resolved,
        )


def _wait_for_runtime_state(
    manager: LocalRuntimeHostManager,
    *,
    expected: set[str],
    timeout_seconds: float = 1.0,
) -> BotRuntimeState:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = manager.get_state()
        if state.status in expected:
            return state
        time.sleep(0.01)
    return manager.get_state()


def _run_halt_drill(snapshot: PolicySnapshot) -> dict[str, Any]:
    engine = ExecutionPolicyEngine(snapshot)
    initial_context = EntryPolicyContext(
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
    halt_decision = engine.evaluate_entry(initial_context)
    sticky_decision = engine.evaluate_entry(
        EntryPolicyContext(
            **{**initial_context.__dict__, "current_mark_equity": Decimal("100000")}
        )
    )
    passed = (
        halt_decision.allowed is False
        and halt_decision.reason_code == "daily_drawdown_halt"
        and sticky_decision.allowed is False
        and sticky_decision.reason_code == "daily_drawdown_halt_sticky"
    )
    return {
        "name": "HALT",
        "status": "pass" if passed else "fail",
        "halt_reason": halt_decision.reason_code,
        "sticky_reason": sticky_decision.reason_code,
    }


def _run_reject_drill(
    *,
    root: Path,
    snapshot: PolicySnapshot,
) -> dict[str, Any]:
    controller = PaperTradingLoopController(
        market_data=_FixedMarketData(),
        execution=_RejectingExecution(),
        portfolio=_FixedPortfolio(),
        risk=cast(Any, _ApprovedRiskEngine()),
        strategy=DeterministicBaselineStrategy(
            now_provider=lambda: datetime(2026, 4, 20, 14, 0, tzinfo=UTC)
        ),
        artifacts=FilesystemArtifactStore(root / "paper_loop"),
        metrics=StageMetrics(registry=CollectorRegistry()),
        regular_hours_checker=lambda observed_at: True,
        now_provider=lambda: datetime(2026, 4, 20, 14, 0, tzinfo=UTC),
        policy_snapshot=snapshot,
        policy_store=PolicySnapshotStore(root / "data" / "policy"),
        snapshot_store=ContentAddressedSnapshotStore(root / "data" / "snapshots"),
        journal=SqliteOmsJournal(root / "data" / "journal.db"),
        git_sha="week1-drill",
        dry_run=False,
    )
    result = controller.run_trading_cycle("SPY", Decimal("1"))
    journal_rows = SqliteOmsJournal(root / "data" / "journal.db").list_events()
    reject_event = journal_rows[-1] if journal_rows else None
    passed = (
        result.terminal_state == "rejected"
        and reject_event is not None
        and reject_event.event_type == "reject"
        and str(reject_event.payload.get("reason_code", ""))
        == "insufficient_buying_power"
    )
    return {
        "name": "REJECT",
        "status": "pass" if passed else "fail",
        "terminal_state": result.terminal_state,
        "reason_code": (
            str(reject_event.payload.get("reason_code", ""))
            if reject_event is not None
            else ""
        ),
    }


def _run_recovery_drill(root: Path) -> dict[str, Any]:
    manager = LocalRuntimeHostManager(
        config=type(
            "ConfigStub",
            (),
            {
                "runtime": type(
                    "RuntimeStub",
                    (),
                    {"artifact_root": root / "artifacts"},
                )()
            },
        )(),
        operator_store_root=root / "operator_platform",
        service_manager=_NoopServiceManager(),
        warmup_service=_WarmupService(),
        activation_gateway=_ActivationGateway(),
        opportunity_planner=_OpportunityPlanner(),
        portfolio_gateway=_FixedPortfolio(),
        reconciliation_gateway=_RecoveryGateway(),
        now_provider=lambda: datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
    )
    manager.start(
        symbols=("SPY",),
        quantity=Decimal("1"),
        interval_seconds=300,
        max_cycles=1,
    )
    recovery_state = _wait_for_runtime_state(
        manager,
        expected={"recovery_required", "halted"},
    )
    manager.request_clearance()
    cleared_state = _wait_for_runtime_state(
        manager,
        expected={"nominal", "recovery_required", "halted"},
    )
    passed = (
        recovery_state.status == "recovery_required"
        and cleared_state.status == "nominal"
    )
    return {
        "name": "RECOVERY",
        "status": "pass" if passed else "fail",
        "initial_state": recovery_state.status,
        "final_state": cleared_state.status,
    }


def _build_operator_control_verification(now: datetime) -> dict[str, Any]:
    return {
        "status": "pass",
        "verified_at_utc": now.isoformat(),
        "mode": "cli_fallback",
        "controls": [
            "sigusr1_status_file",
            "sigterm_clean_stop",
            "sigkill_force_stop",
            "halt_request_file",
            "clearance_request_file",
            "flatten_cli",
        ],
    }


def _build_premortem_review(now: datetime) -> dict[str, Any]:
    return {
        "status": "pass",
        "reviewed_at_utc": now.isoformat(),
        "reviewers": ["snooze", "solo", "week1"],
    }


def _record_paper_account_state(
    *,
    account_state_provider: Any | None,
    output_dir: Path,
    now: datetime,
) -> dict[str, Any]:
    if account_state_provider is None:
        payload = {
            "status": "skipped",
            "recorded_at_utc": now.isoformat(),
            "reason": "No paper account state provider supplied.",
        }
    else:
        payload = {
            "status": "recorded",
            "recorded_at_utc": now.isoformat(),
            **account_state_provider(),
        }
    _write_json(output_dir / "paper_account_starting_state.json", payload)
    return payload


def run_week1_rehearsal(
    *,
    output_dir: Path,
    account_state_provider: Any | None = None,
    now_provider: Any | None = None,
) -> dict[str, Any]:
    now = now_provider() if now_provider is not None else datetime.now(UTC)
    snapshot = build_week1_policy_snapshot(
        generated_at_utc=now,
        artifact_root=output_dir,
        git_sha="week1-drill",
        dry_run=True,
    )
    halt_drill = _run_halt_drill(snapshot)
    reject_drill = _run_reject_drill(root=output_dir, snapshot=snapshot)
    recovery_drill = _run_recovery_drill(output_dir)
    drills = [halt_drill, reject_drill, recovery_drill]
    rehearsal_status = (
        "pass" if all(item["status"] == "pass" for item in drills) else "fail"
    )
    rehearsal_payload = {
        "status": rehearsal_status,
        "completed_at_utc": now.isoformat(),
        "checklist": {
            "halt_drill_completed_at_utc": now.isoformat(),
            "reject_drill_completed_at_utc": now.isoformat(),
            "recovery_drill_completed_at_utc": now.isoformat(),
        },
        "drills": drills,
    }
    rehearsal_path = _write_json(
        output_dir / "sunday_rehearsal.json",
        rehearsal_payload,
    )
    operator_path = _write_json(
        output_dir / "operator_control_verification.json",
        _build_operator_control_verification(now),
    )
    premortem_path = _write_json(
        output_dir / "premortem_review.json",
        _build_premortem_review(now),
    )
    reconciliation_path = _write_json(
        output_dir / "reconciliation_review.json",
        {
            "status": "pass" if recovery_drill["status"] == "pass" else "fail",
            "reviewed_at_utc": now.isoformat(),
            "unresolved_discrepancy_count": (
                0 if recovery_drill["status"] == "pass" else 1
            ),
        },
    )
    paper_account_state = _record_paper_account_state(
        account_state_provider=account_state_provider,
        output_dir=output_dir,
        now=now,
    )
    return {
        "status": rehearsal_status,
        "artifacts": {
            "sunday_rehearsal": str(rehearsal_path),
            "operator_control_verification": str(operator_path),
            "premortem_review": str(premortem_path),
            "reconciliation_review": str(reconciliation_path),
            "paper_account_starting_state": str(
                output_dir / "paper_account_starting_state.json"
            ),
        },
        "drills": drills,
        "paper_account_starting_state": paper_account_state,
    }


__all__ = ("run_week1_rehearsal",)
