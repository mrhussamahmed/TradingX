from __future__ import annotations

import pytest

from tradingx.activation import LocalActivationGateway
from tradingx.persistence import FilesystemArtifactStore
from tradingx.runtime_strategy_registry import RuntimeStrategyRegistry
from tradingx.types import PortfolioState


class FakeResolver:
    def plan_for_service(
        self,
        *,
        symbols,
        portfolio_state: PortfolioState,
        default_quantity,
    ):
        del symbols, portfolio_state, default_quantity
        return None


def test_local_activation_gateway_loads_committed_weights_outside_repo_cwd(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    registry = RuntimeStrategyRegistry()
    registry.register("baseline-long-only-v1", FakeResolver())
    gateway = LocalActivationGateway(
        store=FilesystemArtifactStore(tmp_path / "operator_platform"),
        strategy_id_validator=registry.can_resolve,
        legacy_non_authority_mode=True,
    )

    activation, snapshot = gateway.load_or_create_active_records(("SPY",))

    assert registry.can_resolve(activation.strategy_id)
    assert snapshot.snapshot_id == "approved-baseline-long-only-v1"
    assert snapshot.weights["signal"] == 1


def test_local_activation_gateway_rejects_unresolvable_default_before_persisting(
    tmp_path,
) -> None:
    gateway = LocalActivationGateway(
        store=FilesystemArtifactStore(tmp_path / "operator_platform"),
        strategy_id_validator=lambda strategy_id: strategy_id == "trend-following-v1",
    )

    with pytest.raises(
        ValueError,
        match="is not resolvable by the runtime planner",
    ):
        gateway.load_or_create_active_records(("SPY",))

    assert gateway.get_latest_activation() is None
