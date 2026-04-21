from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest


def test_approved_weight_snapshot_store_loads_committed_yaml(tmp_path) -> None:
    weights_root = tmp_path / "config" / "strategy" / "weights"
    weights_root.mkdir(parents=True)
    (weights_root / "baseline-long-only-v1.yaml").write_text(
        "\n".join(
            (
                "snapshot_id: approved-baseline-long-only-v1",
                "strategy_id: baseline-long-only-v1",
                "status: approved",
                "generated_at_utc: 2026-04-19T09:55:00+00:00",
                "minimum_supporting_trades: 5",
                "weights:",
                "  signal: 1.0",
                "  regime: 1.0",
                "  liquidity: 1.0",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    from tradingx.types import ApprovedWeightSnapshot
    from tradingx.weights import ApprovedWeightSnapshotStore

    store = ApprovedWeightSnapshotStore(weights_root)

    snapshot = store.load_by_strategy_id("baseline-long-only-v1")

    assert snapshot == ApprovedWeightSnapshot(
        snapshot_id="approved-baseline-long-only-v1",
        strategy_id="baseline-long-only-v1",
        status="approved",
        generated_at_utc=datetime(2026, 4, 19, 9, 55, tzinfo=UTC),
        minimum_supporting_trades=5,
        weights={
            "signal": Decimal("1.0"),
            "regime": Decimal("1.0"),
            "liquidity": Decimal("1.0"),
        },
    )


def test_approved_weight_snapshot_store_rejects_missing_committed_yaml(
    tmp_path,
) -> None:
    from tradingx.weights import (
        ApprovedWeightSnapshotNotFoundError,
        ApprovedWeightSnapshotStore,
    )

    store = ApprovedWeightSnapshotStore(tmp_path / "config" / "strategy" / "weights")

    with pytest.raises(ApprovedWeightSnapshotNotFoundError):
        store.load_by_strategy_id("baseline-long-only-v1")


def test_approved_weight_snapshot_store_rejects_naive_generated_at_utc(
    tmp_path,
) -> None:
    weights_root = tmp_path / "config" / "strategy" / "weights"
    weights_root.mkdir(parents=True)
    (weights_root / "baseline-long-only-v1.yaml").write_text(
        "\n".join(
            (
                "snapshot_id: approved-baseline-long-only-v1",
                "strategy_id: baseline-long-only-v1",
                "status: approved",
                "generated_at_utc: 2026-04-19T09:55:00",
                "minimum_supporting_trades: 5",
                "weights:",
                "  signal: 1.0",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    from tradingx.weights import ApprovedWeightSnapshotStore

    store = ApprovedWeightSnapshotStore(weights_root)

    with pytest.raises(ValueError, match="timezone-aware"):
        store.load_by_strategy_id("baseline-long-only-v1")
