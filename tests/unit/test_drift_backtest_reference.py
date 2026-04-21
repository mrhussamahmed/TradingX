from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tradingx.drift.backtest_reference import (
    load_backtest_reference_returns,
    write_backtest_reference_returns,
)


def test_write_and_load_returns(tmp_path: Path) -> None:
    artifact_root = tmp_path / "runtime"
    returns = (Decimal("0.001"), Decimal("-0.002"), Decimal("0.003"))
    path = write_backtest_reference_returns(
        artifact_root=artifact_root,
        sleeve_id="trend-following-v1",
        returns=returns,
    )

    assert path.exists()
    assert path.parent.parent.name == "drift"
    assert "config/strategy" not in str(path)
    assert (
        load_backtest_reference_returns(
            artifact_root=artifact_root,
            sleeve_id="trend-following-v1",
        )
        == returns
    )


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert (
        load_backtest_reference_returns(
            artifact_root=tmp_path / "runtime",
            sleeve_id="trend-following-v1",
        )
        == ()
    )
