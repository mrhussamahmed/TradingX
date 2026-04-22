from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.config import TradingConfig
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    BotRuntimeState,
    OperatorAlert,
    ServiceCycleSnapshot,
    SleeveDailyAttributionRecord,
    WebServiceState,
)
from tradingx.web.readmodels import LocalWebReadModel


class _ServiceManager:
    def get_state(self) -> WebServiceState:
        return WebServiceState(
            status="running",
            active_symbols=("SPY", "QQQ"),
            interval_seconds=300,
            cycles_completed=1,
            started_at_utc=datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
            last_completed_at_utc=datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
            last_error="",
        )


class _RuntimeHostManager:
    def get_state(self) -> BotRuntimeState:
        timestamp = datetime(2026, 4, 22, 14, 0, tzinfo=UTC)
        return BotRuntimeState(
            status="trading_ready",
            status_reason="Runtime boot complete.",
            active_symbols=("SPY", "QQQ"),
            started_at_utc=timestamp,
            updated_at_utc=timestamp,
            last_error="",
            active_strategy_id="bp-default-v1",
            active_model_snapshot_id="approved-bp-default-v1",
            latest_selection_id="selection-1",
        )


def _read_model(tmp_path) -> LocalWebReadModel:
    config = TradingConfig.from_mapping(
        {
            "TRADINGX_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
            "TRADINGX_DATA_ROOT": str(tmp_path / "data"),
        }
    )
    return LocalWebReadModel(
        config=config,
        paper_store=FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop"),
        validation_store=FilesystemArtifactStore(tmp_path / "artifacts" / "validation"),
        docs_root=tmp_path / "docs",
        repo_root=tmp_path,
        service_manager=_ServiceManager(),
        runtime_host_manager=_RuntimeHostManager(),
    )


def _write_minimal_cycle(tmp_path) -> None:
    FilesystemArtifactStore(
        tmp_path / "artifacts" / "paper_loop"
    ).write_service_cycle_snapshot(
        ServiceCycleSnapshot(
            cycle_id="cycle-1",
            started_at_utc=datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
            completed_at_utc=datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
            cycle_status="executed",
            symbols=("SPY", "QQQ"),
            symbol_results=(),
            blocked_trade_count=0,
            reconciliation_failure_count=0,
            open_position_symbols=("SPY",),
            cash=Decimal("100000"),
            equity=Decimal("101000"),
            buying_power=Decimal("200000"),
        )
    )


def test_dashboard_shows_active_blueprint_and_per_sleeve_rows(tmp_path) -> None:
    _write_minimal_cycle(tmp_path)
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    runtime_store = FilesystemArtifactStore(tmp_path / "artifacts")
    operator_store.write_blueprint_activation_record(
        BlueprintActivationRecord(
            activation_id="activation-1",
            blueprint_id="bp-default-v1",
            sleeve_activation_bindings=(
                BlueprintSleeveBinding(
                    sleeve_id="trend-following-v1",
                    strategy_id="trend-following-v1",
                    captured_snapshot_id="snap-trend",
                ),
                BlueprintSleeveBinding(
                    sleeve_id="vol-target-v1",
                    strategy_id="vol-target-v1",
                    captured_snapshot_id="snap-vol",
                ),
            ),
            status="active",
            approved_at_utc=datetime(2026, 4, 22, 9, 0, tzinfo=UTC),
            approved_by="operator:test",
            source_blueprint_path=Path("bp-default.yaml"),
        )
    )
    runtime_store.write_sleeve_daily_attribution_record(
        SleeveDailyAttributionRecord(
            attribution_id="trend-following-v1__2026-04-22",
            sleeve_id="trend-following-v1",
            trading_day="2026-04-22",
            recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
            starting_equity=Decimal("50000"),
            ending_equity=Decimal("51000"),
            daily_return=Decimal("0.02"),
            per_symbol_open_weight=(("SPY", Decimal("0.5")),),
            per_symbol_close_weight=(("SPY", Decimal("0.5")),),
        )
    )
    runtime_store.write_sleeve_daily_attribution_record(
        SleeveDailyAttributionRecord(
            attribution_id="vol-target-v1__2026-04-22",
            sleeve_id="vol-target-v1",
            trading_day="2026-04-22",
            recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
            starting_equity=Decimal("50000"),
            ending_equity=Decimal("49500"),
            daily_return=Decimal("-0.01"),
            per_symbol_open_weight=(("SPY", Decimal("0.2")),),
            per_symbol_close_weight=(("SPY", Decimal("0.1")),),
        )
    )
    runtime_store.write_operator_alert(
        OperatorAlert(
            alert_id="drift-1",
            severity="critical",
            category="portfolio_drift_alarm",
            summary="ks::trend-following-v1 CRITICAL: divergence detected",
            evidence_refs=(),
            delivery_targets=("operator_dashboard",),
            sent_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
        )
    )

    snapshot = _read_model(tmp_path).build_portfolio_workspace_snapshot()

    assert snapshot.strategy_panel.active_blueprint_id == "bp-default-v1"
    assert set(snapshot.strategy_panel.constituent_sleeve_ids) == {
        "trend-following-v1",
        "vol-target-v1",
    }
    rows = {row.strategy_id: row for row in snapshot.strategy_panel.strategies}
    assert set(rows) == {"trend-following-v1", "vol-target-v1"}
    assert rows["trend-following-v1"].drift_severity == "critical"
    assert rows["vol-target-v1"].drift_severity == "pending"


def test_dashboard_preserves_legacy_layout_without_blueprint(tmp_path) -> None:
    snapshot = _read_model(tmp_path).build_portfolio_workspace_snapshot()

    assert snapshot.strategy_panel.active_blueprint_id is None
    assert snapshot.strategy_panel.constituent_sleeve_ids == ()


def test_dashboard_surfaces_narrowing_notice(tmp_path) -> None:
    _write_minimal_cycle(tmp_path)
    operator_store = FilesystemArtifactStore(
        tmp_path / "artifacts" / "operator_platform"
    )
    paper_store = FilesystemArtifactStore(tmp_path / "artifacts" / "paper_loop")
    operator_store.write_blueprint_activation_record(
        BlueprintActivationRecord(
            activation_id="activation-2",
            blueprint_id="bp-default-v1--narrowed",
            sleeve_activation_bindings=(
                BlueprintSleeveBinding(
                    sleeve_id="trend-following-v1",
                    strategy_id="trend-following-v1",
                    captured_snapshot_id="snap-trend",
                ),
            ),
            status="active",
            approved_at_utc=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
            approved_by="operator:test",
            source_blueprint_path=Path("bp-default.yaml"),
        )
    )
    paper_store.write_operator_alert(
        OperatorAlert(
            alert_id="blueprint-narrowed-1",
            severity="warning",
            category="blueprint_narrowed",
            summary=(
                "Blueprint narrowed after 'vol-target-v1' triggered "
                "drift_alarm_live."
            ),
            evidence_refs=(),
            delivery_targets=("operator_dashboard",),
            sent_at_utc=datetime(2026, 4, 22, 10, 5, tzinfo=UTC),
        )
    )

    snapshot = _read_model(tmp_path).build_portfolio_workspace_snapshot()

    assert snapshot.strategy_panel.active_blueprint_id == "bp-default-v1--narrowed"
    assert snapshot.strategy_panel.narrowing_notice is not None
    assert "vol-target-v1" in snapshot.strategy_panel.narrowing_notice
