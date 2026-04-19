from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.dry_run_report import build_dry_run_report
from tradingx.journal import SqliteOmsJournal
from tradingx.persistence import FilesystemArtifactStore
from tradingx.snapshots import (
    CandidateIntentSnapshot,
    ContentAddressedSnapshotStore,
    DecisionSnapshotV1,
)
from tradingx.types import ServiceCycleSnapshot, ServiceSymbolResult


def test_build_dry_run_report_summarizes_cycles_decisions_and_simulations(
    tmp_path,
) -> None:
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    snapshot_store = ContentAddressedSnapshotStore(tmp_path / "data" / "snapshots")
    journal = SqliteOmsJournal(tmp_path / "data" / "journal.db")

    first_snapshot = DecisionSnapshotV1(
        schema_version=1,
        timestamp_utc=datetime(2026, 4, 20, 13, 45, tzinfo=UTC),
        cycle_correlation_id="cycle-1",
        session_snapshot_id="session-1",
        universe_snapshot_id="week1-spy",
        policy_snapshot_id="policy-1",
        model_snapshot_id="baseline",
        strategy_version="baseline-long-only-v1",
        strategy_config_hash="cfg-1",
        git_sha="abc1234",
        dry_run=True,
        market_data_window_hash="market-1",
        feature_snapshot_id="feature-1",
        session_start_equity=Decimal("100000"),
        candidate_intents=(
            CandidateIntentSnapshot(
                symbol="SPY",
                selected=True,
                terminal_reason="baseline_long_entry",
                base_score=Decimal("1.0"),
                final_score=Decimal("0.8"),
                eligibility="eligible",
                risk_status="approved",
            ),
        ),
        final_action="dry_run",
        risk_verdict_id="risk-1",
    )
    blocked_snapshot = DecisionSnapshotV1(
        schema_version=1,
        timestamp_utc=datetime(2026, 4, 20, 14, 0, tzinfo=UTC),
        cycle_correlation_id="cycle-2",
        session_snapshot_id="session-1",
        universe_snapshot_id="week1-spy",
        policy_snapshot_id="policy-1",
        model_snapshot_id="baseline",
        strategy_version="baseline-long-only-v1",
        strategy_config_hash="cfg-1",
        git_sha="abc1234",
        dry_run=True,
        market_data_window_hash="market-2",
        feature_snapshot_id="feature-2",
        session_start_equity=Decimal("100000"),
        candidate_intents=(
            CandidateIntentSnapshot(
                symbol="SPY",
                selected=True,
                terminal_reason="daily_entry_cap_reached",
                base_score=Decimal("1.0"),
                final_score=Decimal("0.3"),
                eligibility="eligible",
                risk_status="blocked",
            ),
        ),
        final_action="blocked_trade",
        risk_verdict_id="risk-2",
    )
    snapshot_store.write_decision_snapshot(first_snapshot)
    snapshot_store.write_decision_snapshot(blocked_snapshot)

    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=datetime(2026, 4, 20, 13, 45, tzinfo=UTC),
            completed_at_utc=datetime(2026, 4, 20, 13, 45, tzinfo=UTC),
            cycle_status="executed",
            symbols=("SPY",),
            symbol_results=(
                ServiceSymbolResult(
                    symbol="SPY",
                    terminal_state="dry_run",
                    reason_code="baseline_long_entry",
                    recovered=False,
                ),
            ),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            open_position_symbols=(),
            cash=Decimal("100000"),
            equity=Decimal("100000"),
            buying_power=Decimal("100000"),
        )
    )
    paper_store.write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-2",
            started_at_utc=datetime(2026, 4, 20, 14, 0, tzinfo=UTC),
            completed_at_utc=datetime(2026, 4, 20, 14, 0, tzinfo=UTC),
            cycle_status="cycle_overrun",
            symbols=("SPY",),
            symbol_results=(
                ServiceSymbolResult(
                    symbol="SPY",
                    terminal_state="blocked_trade",
                    reason_code="daily_entry_cap_reached",
                    recovered=False,
                ),
            ),
            blocked_trade_count=1,
            reconciliation_failure_count=1,
            open_position_symbols=(),
            cash=Decimal("100000"),
            equity=Decimal("99950"),
            buying_power=Decimal("99950"),
        )
    )

    journal.append_event(
        event_type="simulated",
        recorded_at_utc=datetime(2026, 4, 20, 13, 45, tzinfo=UTC),
        decision_snapshot_id=first_snapshot.decision_snapshot_id,
        cycle_correlation_id="cycle-1",
        client_order_id="cid-1",
        broker_order_id="",
        symbol="SPY",
        side="buy",
        payload={
            "quantity": "1",
            "reason_code": "baseline_long_entry",
            "reference_price": "600.10",
            "would_submit_limit_price": "600.70",
        },
    )

    report = build_dry_run_report(
        paper_store=paper_store,
        snapshot_store=snapshot_store,
        journal=journal,
    )

    assert report["trading_day"] == "2026-04-20"
    assert report["dry_run"] is True
    assert report["cycle_count"] == 2
    assert len(report["decision_snapshots"]) == 2
    assert report["blocked_intents"] == [
        {
            "decision_snapshot_id": blocked_snapshot.decision_snapshot_id,
            "symbol": "SPY",
            "reason": "daily_entry_cap_reached",
        }
    ]
    assert report["simulated_orders"] == [
        {
            "decision_snapshot_id": first_snapshot.decision_snapshot_id,
            "client_order_id": "cid-1",
            "symbol": "SPY",
            "side": "buy",
            "quantity": "1",
            "reason_code": "baseline_long_entry",
            "reference_price": "600.10",
            "would_submit_limit_price": "600.70",
        }
    ]
    assert report["major_path_coverage"] == {
        "entry": True,
        "exit": False,
        "halt": False,
        "reject": False,
        "recovery": True,
    }
    assert report["anomalies"]["cycle_overruns"] == ["cycle-2"]
    assert report["anomalies"]["reconciliation_flags"] == ["cycle-2"]
    assert report["simulated_pnl_vs_spy_buy_hold"]["status"] == (
        "insufficient_simulated_closes"
    )
