from __future__ import annotations

import importlib

from prometheus_client import CollectorRegistry

from tradingx.monitoring import StageMetrics


def test_monitoring_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.monitoring")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_stage_metrics_records_trade_terminal_states() -> None:
    registry = CollectorRegistry()
    metrics = StageMetrics(registry=registry)

    metrics.record_trade_terminal_state("reconciled_trade")
    metrics.record_trade_terminal_state("blocked_trade")

    assert (
        registry.get_sample_value(
            "tradingx_trade_terminal_states_total",
            {"terminal_state": "reconciled_trade"},
        )
        == 1
    )
    assert (
        registry.get_sample_value(
            "tradingx_trade_terminal_states_total",
            {"terminal_state": "blocked_trade"},
        )
        == 1
    )


def test_stage_metrics_records_alerts_and_reconciliation_age() -> None:
    registry = CollectorRegistry()
    metrics = StageMetrics(registry=registry, namespace="custombot")

    metrics.record_operator_alert("critical")
    metrics.record_reconciliation_age_seconds(42.5)

    assert (
        registry.get_sample_value(
            "custombot_operator_alerts_total",
            {"severity": "critical"},
        )
        == 1
    )
    assert registry.get_sample_value("custombot_reconciliation_age_seconds") == 42.5


def test_stage_metrics_records_evidence_and_live_disable_state() -> None:
    registry = CollectorRegistry()
    metrics = StageMetrics(registry=registry)

    metrics.record_evidence_artifact("trade_intent")
    metrics.record_live_disable_state(True)
    metrics.record_manual_halt_state(True)

    assert (
        registry.get_sample_value(
            "tradingx_evidence_artifacts_total",
            {"category": "trade_intent"},
        )
        == 1
    )
    assert registry.get_sample_value("tradingx_live_trading_disabled") == 1
    assert registry.get_sample_value("tradingx_manual_halt_active") == 1


def test_stage_metrics_records_service_and_portfolio_metrics() -> None:
    registry = CollectorRegistry()
    metrics = StageMetrics(registry=registry)

    metrics.record_service_cycle("executed")
    metrics.record_symbols_scanned(3)
    metrics.record_open_positions(2)
    metrics.record_account_snapshot(
        cash="10025.00",
        equity="10030.00",
        daily_pnl="30.00",
    )
    metrics.record_blocked_trade("liquidity_filter")
    metrics.record_candidate_recommendation("keep")

    assert (
        registry.get_sample_value(
            "tradingx_service_cycles_total",
            {"cycle_status": "executed"},
        )
        == 1
    )
    assert registry.get_sample_value("tradingx_symbols_scanned_total") == 3
    assert registry.get_sample_value("tradingx_open_positions") == 2
    assert registry.get_sample_value("tradingx_paper_cash") == 10025.0
    assert registry.get_sample_value("tradingx_paper_equity") == 10030.0
    assert registry.get_sample_value("tradingx_paper_daily_pnl") == 30.0
    assert (
        registry.get_sample_value(
            "tradingx_blocked_trades_total",
            {"control_type": "liquidity_filter"},
        )
        == 1
    )
    assert (
        registry.get_sample_value(
            "tradingx_candidate_recommendations_total",
            {"recommendation": "keep"},
        )
        == 1
    )
