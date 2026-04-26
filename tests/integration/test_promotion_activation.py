from __future__ import annotations

from pathlib import Path

import pytest

from tradingx.activation import LocalActivationGateway
from tradingx.persistence import FilesystemArtifactStore
from tradingx.promotion import (
    DEFAULT_STATE_ACTION_CONTRACTS,
    PromotionDecision,
    PromotionState,
)


def test_activation_refuses_when_promotion_below_requested_runtime_route(
    tmp_path,
) -> None:
    gateway = LocalActivationGateway(
        store=FilesystemArtifactStore(tmp_path / "operator_platform"),
        promotion_decision_provider=lambda strategy_id: PromotionDecision(
            strategy_id=strategy_id,
            requested_state=PromotionState.PAPER_TRADING,
            max_state=PromotionState.RESEARCH_ONLY,
            blockers=(),
            artifact_refs=("sha256:" + "1" * 64,),
            ledger_sequence=None,
            ledger_hash=None,
        ),
        required_promotion_state=PromotionState.PAPER_TRADING,
        projection_root=tmp_path / "config/strategy/promotion",
    )

    with pytest.raises(ValueError, match="artifact_refs=sha256"):
        gateway.load_or_create_active_records(("SPY",))


def test_activation_refuses_hand_edited_projection_drift(tmp_path) -> None:
    projection_root = tmp_path / "config/strategy/promotion"
    projection_root.mkdir(parents=True)
    projection_path = projection_root / "baseline-long-only-v1.json"
    projection_path.write_text(
        (
            '{"schema_version":"1.0","strategy_id":"baseline-long-only-v1",'
            '"promotion_state":"production","source_decision_hash":"sha256:bad"}'
        ),
        encoding="utf-8",
    )
    decision = PromotionDecision(
        strategy_id="baseline-long-only-v1",
        requested_state=PromotionState.PAPER_TRADING,
        max_state=PromotionState.PAPER_TRADING,
        blockers=(),
        artifact_refs=(),
        ledger_sequence=None,
        ledger_hash=None,
    )
    gateway = LocalActivationGateway(
        store=FilesystemArtifactStore(tmp_path / "operator_platform"),
        promotion_decision_provider=lambda strategy_id: decision,
        required_promotion_state=PromotionState.PAPER_TRADING,
        projection_root=projection_root,
    )

    with pytest.raises(ValueError, match="projection drift"):
        gateway.load_or_create_active_records(("SPY",))


def test_activation_allows_legacy_default_when_no_v5_policy_configured(
    tmp_path,
) -> None:
    gateway = LocalActivationGateway(
        store=FilesystemArtifactStore(tmp_path / "operator_platform"),
        legacy_non_authority_mode=True,
    )

    activation, _snapshot = gateway.load_or_create_active_records(("SPY",))

    assert activation.strategy_id == "baseline-long-only-v1"
    assert not (Path(tmp_path) / "config/strategy/promotion").exists()


def test_activation_refuses_when_v5_authority_is_not_configured(tmp_path) -> None:
    gateway = LocalActivationGateway(
        store=FilesystemArtifactStore(tmp_path / "operator_platform"),
    )

    with pytest.raises(ValueError, match="authority_artifact_invalid"):
        gateway.load_or_create_active_records(("SPY",))


def test_activation_refuses_malformed_state_action_contract(tmp_path) -> None:
    decision = PromotionDecision(
        strategy_id="baseline-long-only-v1",
        requested_state=PromotionState.PAPER_TRADING,
        max_state=PromotionState.PAPER_TRADING,
        blockers=(),
        artifact_refs=("sha256:" + "1" * 64,),
        ledger_sequence=1,
        ledger_hash="sha256:" + "2" * 64,
    )
    gateway = LocalActivationGateway(
        store=FilesystemArtifactStore(tmp_path / "operator_platform"),
        promotion_decision_provider=lambda strategy_id: decision,
        required_promotion_state=PromotionState.PAPER_TRADING,
        state_action_contracts={
            "paper_shadow": {
                "order_permission": "paper_orders",
            }
        },
    )

    with pytest.raises(ValueError, match="state_action_contract_missing"):
        gateway.load_or_create_active_records(("SPY",))


def test_activation_allows_sufficient_state_with_valid_state_action_contract(
    tmp_path,
) -> None:
    decision = PromotionDecision(
        strategy_id="baseline-long-only-v1",
        requested_state=PromotionState.PAPER_TRADING,
        max_state=PromotionState.PAPER_TRADING,
        blockers=(),
        artifact_refs=("sha256:" + "1" * 64,),
        ledger_sequence=1,
        ledger_hash="sha256:" + "2" * 64,
    )
    gateway = LocalActivationGateway(
        store=FilesystemArtifactStore(tmp_path / "operator_platform"),
        promotion_decision_provider=lambda strategy_id: decision,
        required_promotion_state=PromotionState.PAPER_TRADING,
        state_action_contracts=DEFAULT_STATE_ACTION_CONTRACTS,
    )

    activation, _snapshot = gateway.load_or_create_active_records(("SPY",))

    assert activation.strategy_id == "baseline-long-only-v1"
