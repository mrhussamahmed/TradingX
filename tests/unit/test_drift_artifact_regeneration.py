from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pandas as pd  # type: ignore[import-untyped]

from tradingx.activation import LocalActivationGateway
from tradingx.automation import (
    _last_activation_bookkeeping_path,
    _resolve_drift_reference_snapshot,
)
from tradingx.config import TradingConfig
from tradingx.drift.backtest_reference import artifact_path as backtest_reference_path
from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.operator_control import OperatorControlStore
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import BlueprintActivationRecord, BlueprintSleeveBinding


class _StaticFeatureReader:
    def live_samples(self, feature_name: str, *, window_days: int) -> pd.Series:
        del feature_name
        return pd.Series(
            [1.0 + (index / 1000.0) for index in range(window_days)],
            dtype=float,
        )


class _StaticSignalReader:
    def live_samples(self, sleeve_id: str, *, window_days: int) -> pd.Series:
        del sleeve_id
        return pd.Series(
            [0.2 + (index / 1000.0) for index in range(window_days)],
            dtype=float,
        )


class _MarketDataStub:
    def __init__(self) -> None:
        index = pd.date_range("2024-01-01", periods=600, freq="D", tz="UTC")
        self._frame = pd.DataFrame(
            {
                "open": [100.0 + (index_ * 0.1) for index_ in range(len(index))],
                "high": [101.0 + (index_ * 0.1) for index_ in range(len(index))],
                "low": [99.0 + (index_ * 0.1) for index_ in range(len(index))],
                "close": [100.0 + (index_ * 0.1) for index_ in range(len(index))],
                "bid": [99.95 + (index_ * 0.1) for index_ in range(len(index))],
                "ask": [100.05 + (index_ * 0.1) for index_ in range(len(index))],
                "volume": [1_000_000.0 for _ in range(len(index))],
            },
            index=index,
        )

    def get_daily_bar_history(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> pd.DataFrame:
        del symbol
        return self._frame.loc[
            (self._frame.index >= start_utc) & (self._frame.index <= end_utc)
        ].copy()


class _DriftRegenerationFixture:
    def __init__(self, tmp_path) -> None:
        self.artifact_root = tmp_path / "artifacts"
        self.data_root = tmp_path / "data"
        self.config = TradingConfig.from_mapping(
            {
                "TRADINGX_ARTIFACT_ROOT": str(self.artifact_root),
                "TRADINGX_DATA_ROOT": str(self.data_root),
                "TRADINGX_SYMBOL_UNIVERSE": "SPY,QQQ,IWM,XLK,XLF,XLE,EEM,TLT",
            }
        )
        self.operator_platform_store = FilesystemArtifactStore(
            self.artifact_root / "operator_platform"
        )
        self.activation_gateway = LocalActivationGateway(
            store=self.operator_platform_store,
            strategy_id_validator=lambda _: True,
            legacy_non_authority_mode=True,
        )
        self.operator_control_store = OperatorControlStore(self.data_root / "control")
        self.blueprint = DriftMonitorBlueprint(blueprint_id="drift-default-v1")
        self.feature_reader = _StaticFeatureReader()
        self.signal_reader = _StaticSignalReader()
        self.market_data = _MarketDataStub()
        self._now = datetime(2026, 4, 22, 14, 0, tzinfo=UTC)

    @property
    def reference_path(self):
        return self.artifact_root / "drift" / "reference_distribution_snapshot.json"

    @property
    def bookkeeping_path(self):
        return _last_activation_bookkeeping_path(artifact_root=self.artifact_root)

    def now(self) -> datetime:
        return self._now

    def advance(self, *, minutes: int = 1) -> None:
        self._now = self._now + timedelta(minutes=minutes)

    def activate(
        self,
        *,
        activation_id: str,
        blueprint_id: str = "bp-default-v1",
        snapshot_suffix: str = "snap-1",
    ) -> BlueprintActivationRecord:
        record = BlueprintActivationRecord(
            activation_id=activation_id,
            blueprint_id=blueprint_id,
            sleeve_activation_bindings=(
                BlueprintSleeveBinding(
                    sleeve_id="trend-following-v1",
                    strategy_id="trend-following-v1",
                    captured_snapshot_id=f"trend-{snapshot_suffix}",
                ),
                BlueprintSleeveBinding(
                    sleeve_id="vol-target-v1",
                    strategy_id="vol-target-v1",
                    captured_snapshot_id=f"vol-{snapshot_suffix}",
                ),
            ),
            status="active",
            approved_at_utc=self.now(),
            approved_by="operator:test",
            source_blueprint_path=self.artifact_root / "bp-default-v1.yaml",
        )
        self.operator_platform_store.write_blueprint_activation_record(record)
        return record

    def rebuild(self):
        return _resolve_drift_reference_snapshot(
            config=self.config,
            activation_gateway=self.activation_gateway,
            blueprint=self.blueprint,
            feature_reader=self.feature_reader,
            signal_reader=self.signal_reader,
            market_data_gateway=self.market_data,
            now_provider=self.now,
        )

    def make_secondary_operator_store(self) -> OperatorControlStore:
        return OperatorControlStore(self.operator_control_store._root_dir)


def test_activation_change_with_same_blueprint_id_forces_regeneration(tmp_path) -> None:
    fixture = _DriftRegenerationFixture(tmp_path)
    fixture.activate(activation_id="activation-a1", snapshot_suffix="snap-1")
    first_snapshot = fixture.rebuild()
    assert first_snapshot.reference_snapshot_id.startswith("drift-ref-")

    fixture.advance(minutes=5)
    fixture.activate(activation_id="activation-a2", snapshot_suffix="snap-2")
    second_snapshot = fixture.rebuild()

    assert second_snapshot.reference_snapshot_id != first_snapshot.reference_snapshot_id
    bookkeeping = json.loads(fixture.bookkeeping_path.read_text(encoding="utf-8"))
    assert bookkeeping["activation_id"] == "activation-a2"


def test_operator_recalibrate_triggers_regeneration_without_deleting_audit_marker(
    tmp_path,
) -> None:
    fixture = _DriftRegenerationFixture(tmp_path)
    fixture.activate(activation_id="activation-a1", snapshot_suffix="snap-1")
    first_snapshot = fixture.rebuild()

    fixture.advance(minutes=5)
    fixture.operator_control_store.recalibrate_drift_reference(
        snapshot_id="ref-operator-1",
        now=fixture.now(),
    )
    audit_marker_path = (
        fixture.operator_control_store._root_dir / "drift_reference_recalibration.json"
    )
    assert audit_marker_path.exists()

    fixture.advance(minutes=5)
    second_snapshot = fixture.rebuild()

    assert second_snapshot.reference_snapshot_id != first_snapshot.reference_snapshot_id
    assert audit_marker_path.exists()

    bookkeeping = json.loads(fixture.bookkeeping_path.read_text(encoding="utf-8"))
    assert bookkeeping["last_processed_recalibration_at"] is not None

    fixture.advance(minutes=5)
    third_snapshot = fixture.rebuild()
    assert third_snapshot.reference_snapshot_id == second_snapshot.reference_snapshot_id


def test_secondary_operator_store_recalibration_triggers_regeneration(tmp_path) -> None:
    fixture = _DriftRegenerationFixture(tmp_path)
    fixture.activate(activation_id="activation-a1", snapshot_suffix="snap-1")
    first_snapshot = fixture.rebuild()
    secondary_store = fixture.make_secondary_operator_store()

    fixture.advance(minutes=5)
    secondary_store.recalibrate_drift_reference(
        snapshot_id="ref-from-service",
        now=fixture.now(),
    )

    fixture.advance(minutes=5)
    second_snapshot = fixture.rebuild()

    assert second_snapshot.reference_snapshot_id != first_snapshot.reference_snapshot_id
    for sleeve_id in ("trend-following-v1", "vol-target-v1"):
        assert backtest_reference_path(
            artifact_root=fixture.artifact_root,
            sleeve_id=sleeve_id,
        ).exists()
