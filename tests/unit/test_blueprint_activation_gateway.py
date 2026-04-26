from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.activation import (
    BlueprintActivationValidationError,
    LocalActivationGateway,
)
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.types import ApprovedWeightSnapshot


def _snapshot(strategy_id: str, snapshot_id: str) -> ApprovedWeightSnapshot:
    return ApprovedWeightSnapshot(
        snapshot_id=snapshot_id,
        strategy_id=strategy_id,
        status="active",
        generated_at_utc=datetime(2026, 4, 22, tzinfo=UTC),
        minimum_supporting_trades=0,
        weights={"SPY": Decimal("1.0")},
    )


class _StubSnapshotStore:
    def __init__(self, snapshots: dict[str, ApprovedWeightSnapshot]) -> None:
        self._snapshots = snapshots

    def load_by_strategy_id(self, strategy_id: str) -> ApprovedWeightSnapshot:
        if strategy_id not in self._snapshots:
            from tradingx.weights import ApprovedWeightSnapshotNotFoundError

            raise ApprovedWeightSnapshotNotFoundError(strategy_id)
        return self._snapshots[strategy_id]


def _blueprint(
    strategy_overrides: dict[str, str] | None = None,
) -> PortfolioBlueprint:
    overrides = strategy_overrides or {}
    return PortfolioBlueprint(
        blueprint_id="bp-test-v1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
                strategy_id=overrides.get("trend-following-v1"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
                strategy_id=overrides.get("vol-target-v1"),
            ),
        ),
    )


def _gateway(
    tmp_path: Path,
    snapshot_store: _StubSnapshotStore,
) -> LocalActivationGateway:
    operator_store = FilesystemArtifactStore(tmp_path)
    return LocalActivationGateway(
        store=operator_store,
        strategy_id_validator=lambda _: True,
        snapshot_store=snapshot_store,
        now_provider=lambda: datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
        legacy_non_authority_mode=True,
    )


def test_activate_blueprint_fresh_writes_record(tmp_path: Path) -> None:
    snapshots = {
        "trend-following-v1": _snapshot("trend-following-v1", "snap-trend-1"),
        "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
    }
    gateway = _gateway(tmp_path, _StubSnapshotStore(snapshots))

    record = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )

    assert record.status == "active"
    assert record.blueprint_id == "bp-test-v1"
    assert len(record.sleeve_activation_bindings) == 2
    bindings_by_sleeve = {
        binding.sleeve_id: binding for binding in record.sleeve_activation_bindings
    }
    assert (
        bindings_by_sleeve["trend-following-v1"].captured_snapshot_id == "snap-trend-1"
    )
    assert bindings_by_sleeve["vol-target-v1"].captured_snapshot_id == "snap-vol-1"


def test_activate_blueprint_idempotent_when_snapshots_unchanged(tmp_path: Path) -> None:
    store = _StubSnapshotStore(
        {
            "trend-following-v1": _snapshot("trend-following-v1", "snap-trend-1"),
            "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
        }
    )
    gateway = _gateway(tmp_path, store)
    record_a = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )
    record_b = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )
    assert record_a.activation_id == record_b.activation_id


def test_activate_blueprint_new_activation_id_when_snapshot_changes(
    tmp_path: Path,
) -> None:
    snapshot_v1 = {
        "trend-following-v1": _snapshot("trend-following-v1", "snap-trend-v1"),
        "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
    }
    gateway = _gateway(tmp_path, _StubSnapshotStore(snapshot_v1))
    record_v1 = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )

    snapshot_v2 = {
        "trend-following-v1": _snapshot("trend-following-v1", "snap-trend-v2"),
        "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
    }
    gateway._snapshot_store = _StubSnapshotStore(snapshot_v2)  # type: ignore[attr-defined]

    record_v2 = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )

    assert record_v1.activation_id != record_v2.activation_id
    trend_binding = next(
        binding
        for binding in record_v2.sleeve_activation_bindings
        if binding.sleeve_id == "trend-following-v1"
    )
    assert trend_binding.captured_snapshot_id == "snap-trend-v2"


def test_activate_blueprint_missing_snapshot_raises_validation_error(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path, _StubSnapshotStore({}))

    with pytest.raises(BlueprintActivationValidationError):
        gateway.load_or_activate_blueprint(
            blueprint=_blueprint(),
            operator_identifier="operator:test",
            source_blueprint_path=Path("bp.yaml"),
        )
    assert gateway.get_active_blueprint_activation() is None


def test_get_active_blueprint_activation_returns_none_when_no_active_record(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path, _StubSnapshotStore({}))
    assert gateway.get_active_blueprint_activation() is None


def test_supersede_active_blueprint_updates_predecessor(tmp_path: Path) -> None:
    store = _StubSnapshotStore(
        {
            "trend-following-v1": _snapshot("trend-following-v1", "snap-trend-1"),
            "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
        }
    )
    gateway = _gateway(tmp_path, store)
    original = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("bp.yaml"),
    )
    narrowed_blueprint = PortfolioBlueprint(
        blueprint_id="bp-narrowed-v1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    narrowed = gateway.load_or_activate_blueprint(
        blueprint=narrowed_blueprint,
        operator_identifier="operator:test",
        source_blueprint_path=Path("bp-narrowed.yaml"),
    )
    updated_predecessor = gateway.supersede_active_blueprint(
        new_activation=narrowed,
        now=datetime(2026, 4, 22, 15, 0, tzinfo=UTC),
    )
    assert updated_predecessor.status == "superseded"
    assert updated_predecessor.superseded_at_utc is not None
    assert updated_predecessor.supersedes_activation_id is None
    assert updated_predecessor.activation_id == original.activation_id
    active = gateway.get_active_blueprint_activation()
    assert active is not None
    assert active.activation_id == narrowed.activation_id
