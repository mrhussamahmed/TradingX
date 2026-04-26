from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.activation import LocalActivationGateway
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.types import ApprovedWeightSnapshot


def _snapshot(strategy_id: str, snapshot_id: str) -> ApprovedWeightSnapshot:
    return ApprovedWeightSnapshot(
        snapshot_id=snapshot_id,
        strategy_id=strategy_id,
        status="approved",
        generated_at_utc=datetime(2026, 4, 22, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={"signal": Decimal("1")},
    )


class _SnapshotStore:
    def __init__(self, snapshots: dict[str, ApprovedWeightSnapshot]) -> None:
        self._snapshots = snapshots

    def load_by_strategy_id(self, strategy_id: str) -> ApprovedWeightSnapshot:
        return self._snapshots[strategy_id]


def _blueprint() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="bp-test-v1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )


def test_load_or_create_active_records_mirrors_snapshot_to_runtime_store(
    tmp_path,
) -> None:
    operator_store = FilesystemArtifactStore(tmp_path / "operator")
    runtime_store = FilesystemArtifactStore(tmp_path / "runtime")
    gateway = LocalActivationGateway(
        store=operator_store,
        runtime_snapshot_store=runtime_store,
        snapshot_store=_SnapshotStore(
            {"baseline-long-only-v1": _snapshot("baseline-long-only-v1", "snap-1")}
        ),
        strategy_id_validator=lambda _: True,
        legacy_non_authority_mode=True,
    )

    _activation, snapshot = gateway.load_or_create_active_records(("SPY",))

    assert (
        operator_store.load_approved_weight_snapshot_by_snapshot_id(
            snapshot_id=snapshot.snapshot_id
        )
        == snapshot
    )
    assert (
        runtime_store.load_approved_weight_snapshot_by_snapshot_id(
            snapshot_id=snapshot.snapshot_id
        )
        == snapshot
    )


def test_load_or_activate_blueprint_backfills_runtime_snapshot_on_reuse(
    tmp_path,
) -> None:
    operator_store = FilesystemArtifactStore(tmp_path / "operator")
    runtime_store = FilesystemArtifactStore(tmp_path / "runtime")
    snapshot = _snapshot("trend-following-v1", "snap-trend-1")
    gateway = LocalActivationGateway(
        store=operator_store,
        runtime_snapshot_store=runtime_store,
        snapshot_store=_SnapshotStore({"trend-following-v1": snapshot}),
        strategy_id_validator=lambda _: True,
        now_provider=lambda: datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
        legacy_non_authority_mode=True,
    )

    record = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("bp.yaml"),
    )
    mirrored_path = runtime_store._path_for(  # type: ignore[attr-defined]
        "model_weight_snapshots",
        f"{snapshot.snapshot_id}.json",
    )
    mirrored_path.unlink()

    reused = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("bp.yaml"),
    )

    assert reused.activation_id == record.activation_id
    assert (
        runtime_store.load_approved_weight_snapshot_by_snapshot_id(
            snapshot_id=snapshot.snapshot_id
        )
        == snapshot
    )
