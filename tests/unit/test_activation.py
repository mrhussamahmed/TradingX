from __future__ import annotations

from decimal import Decimal

import pytest

from tradingx.activation import LocalActivationGateway
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.promotion import PromotionDecision, PromotionState
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


def test_local_activation_gateway_derives_verified_allocation_limits(tmp_path) -> None:
    blueprint = PortfolioBlueprint(
        blueprint_id="bp-runtime",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                strategy_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.10"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    decision = PromotionDecision(
        strategy_id="trend-following-v1",
        requested_state=PromotionState.PRODUCTION,
        max_state=PromotionState.PRODUCTION,
        blockers=(),
        artifact_refs=("sha256:" + "1" * 64,),
        ledger_sequence=1,
        ledger_hash="sha256:" + "2" * 64,
        state_action_contracts={
            "production": {
                "disallowed_actions": [],
            },
        },
        strategy_allocation_limits=(
            {
                "strategy_id": "trend-following-v1",
                "max_strategy_allocation": "0.05",
            },
        ),
    )
    gateway = LocalActivationGateway(
        store=FilesystemArtifactStore(tmp_path / "operator_platform"),
        promotion_decision_provider=lambda strategy_id: decision,
        required_promotion_state=PromotionState.PRODUCTION,
        state_action_contracts={"production": {"disallowed_actions": []}},
    )

    limits = gateway.get_strategy_allocation_limits(blueprint)

    actual_limits = tuple(
        (limit.strategy_id, limit.max_strategy_allocation) for limit in limits
    )

    assert actual_limits == (("trend-following-v1", Decimal("0.05")),)
