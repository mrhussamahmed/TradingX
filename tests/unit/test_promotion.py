from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tradingx.authority import (
    AuthorityLedger,
    FileContentAddressedStore,
    TrustRoot,
    canonical_payload_hash,
)
from tradingx.promotion import (
    PromotionDecision,
    PromotionState,
    StateActionContractError,
    check_projection_drift,
    evaluate_promotion_manifest,
    load_promotion_decision,
    load_state_action_contracts,
    validate_state_action_contracts,
)


def _fixture_root(name: str) -> Path:
    return Path("tests/fixtures/promotion") / name


def _valid_state_action_contracts() -> dict[str, dict[str, object]]:
    return {
        "disabled": {
            "data_access": "none",
            "broker_access": "none",
            "order_permission": "none",
            "capital_ceiling": "0",
            "short_permission": "none",
            "required_runtime_controls": [],
            "route_constraints": {"allowed_routes": [], "max_order_notional": "0"},
            "disallowed_actions": ["activation", "paper_order", "live_order"],
        },
        "research_only": {
            "data_access": "historical",
            "broker_access": "none",
            "order_permission": "none",
            "capital_ceiling": "0",
            "short_permission": "none",
            "required_runtime_controls": ["legacy_non_authority_label"],
            "route_constraints": {"allowed_routes": [], "max_order_notional": "0"},
            "disallowed_actions": ["paper_order", "live_order"],
        },
        "paper_shadow": {
            "data_access": "realtime",
            "broker_access": "read_only",
            "order_permission": "shadow_decisions",
            "capital_ceiling": "0",
            "short_permission": "none",
            "required_runtime_controls": ["projection_drift_check"],
            "route_constraints": {
                "allowed_routes": ["shadow_decision"],
                "max_order_notional": "0",
            },
            "disallowed_actions": ["paper_order", "live_order"],
        },
        "paper_trading": {
            "data_access": "realtime",
            "broker_access": "paper",
            "order_permission": "paper_orders",
            "capital_ceiling": "100000",
            "short_permission": "none",
            "required_runtime_controls": [
                "projection_drift_check",
                "paper_order_reconciliation",
            ],
            "route_constraints": {
                "allowed_routes": ["paper_order"],
                "max_order_notional": "10000",
            },
            "disallowed_actions": ["live_order"],
        },
        "tiny_live_probe": {
            "data_access": "realtime",
            "broker_access": "live",
            "order_permission": "live_probe_orders",
            "capital_ceiling": "1000",
            "short_permission": "none",
            "required_runtime_controls": [
                "projection_drift_check",
                "pre_trade_controls",
            ],
            "route_constraints": {
                "allowed_routes": ["live_probe_order"],
                "max_order_notional": "100",
            },
            "disallowed_actions": ["production_live_order"],
        },
        "production": {
            "data_access": "realtime",
            "broker_access": "live",
            "order_permission": "live_orders",
            "capital_ceiling": "100000",
            "short_permission": "none",
            "required_runtime_controls": [
                "projection_drift_check",
                "pre_trade_controls",
                "kill_switch",
            ],
            "route_constraints": {
                "allowed_routes": ["live_order"],
                "max_order_notional": "10000",
            },
            "disallowed_actions": [],
        },
    }


def _write_hmac_signed_bundle(
    root: Path,
    *,
    artifact_payloads: tuple[dict[str, object], ...],
    blocker_codes: tuple[str, ...] = (),
    trust_root_fixture: bool = False,
    signature_prefix: str = "hmac",
) -> None:
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "trend-following-v1",
                "requested_state": "paper_shadow",
                "artifact_store_root": "cas",
                "replay_store_root": "cas",
                "ledger_root": "ledger",
                "trust_root_path": "trust_root.json",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    store = FileContentAddressedStore(root / "cas")
    artifact_refs = tuple(store.write_json(payload) for payload in artifact_payloads)
    replay_ref = store.write_json(
        {
            "schema_version": "1.0",
            "kind": "retained_replay_input",
            "strategy_id": "trend-following-v1",
        }
    )
    trust_root = TrustRoot(
        root_id="fixture-root",
        trusted_keys={"operator-key": "secret"},
        key_scopes={"operator-key": ("promotion_decision",)},
        revoked_keys=frozenset(),
        not_before_utc=datetime(2026, 1, 1, tzinfo=UTC),
        not_after_utc=datetime(2026, 12, 31, tzinfo=UTC),
        fixture_root=trust_root_fixture,
    )
    (root / "trust_root.json").write_text(
        json.dumps(trust_root.to_json(), sort_keys=True),
        encoding="utf-8",
    )
    decision_payload = {
        "schema_version": "1.0",
        "kind": "promotion_decision",
        "strategy_id": "trend-following-v1",
        "requested_state": "paper_shadow",
        "max_state": "paper_shadow",
        "target_weights": {"SPY": "1"},
        "blocker_codes": list(blocker_codes),
    }
    payload_hash = canonical_payload_hash(decision_payload)
    if signature_prefix == "fixture":
        signature_ref = trust_root.sign_for_test(
            key_id="operator-key",
            payload_hash=payload_hash,
            scope="promotion_decision",
        )
    else:
        digest = hmac.new(
            b"secret",
            f"{payload_hash}|promotion_decision".encode(),
            hashlib.sha256,
        ).hexdigest()
        signature_ref = f"{signature_prefix}:operator-key:promotion_decision:{digest}"
    approval_ref = store.write_json(
        {
            "schema_version": "1.0",
            "kind": "approval",
            "payload_hash": payload_hash,
            "scope": "promotion_decision",
            "signature_ref": signature_ref,
            "operator_identity_ref": "operator:fixture-a",
            "role_registry_ref": "role-registry:fixture-v1",
            "authority_boundary_ref": "authority-boundary:promotion-v1",
            "risk_accepted": True,
            "signed_at_utc": "2026-04-26T00:00:00Z",
            "expires_at_utc": "2026-12-31T00:00:00Z",
        }
    )
    AuthorityLedger(root / "ledger").append(
        payload=decision_payload,
        artifact_refs=artifact_refs,
        replay_refs=(replay_ref,),
        writer_identity="operator-a",
        approval_refs=(str(approval_ref),),
    )


def _minimal_authority_artifacts() -> tuple[dict[str, object], ...]:
    return (
        {
            "schema_version": "1.0",
            "kind": "strategy_capability_manifest",
            "strategy_id": "trend-following-v1",
            "supported_sides": ["long"],
            "instrument_types": ["equity"],
        },
        {
            "schema_version": "1.0",
            "kind": "promotion_evidence",
            "strategy_id": "trend-following-v1",
            "evidence_class": "valid",
            "artifact_refs": [],
        },
        {
            "schema_version": "1.0",
            "kind": "ledger_key_management_policy",
            "root_id": "fixture-root",
            "worm_controls": True,
        },
        {
            "schema_version": "1.0",
            "kind": "state_action_contract",
            "contracts": _valid_state_action_contracts(),
        },
    )


def test_wave1_golden_fixture_inventory_is_present() -> None:
    expected_fixture_dirs = {
        "valid",
        "legacy",
        "stale",
        "invalid",
        "projection_drift",
        "unsigned_approval",
        "key_policy_missing",
        "sequence_gap",
        "missing_replay_input",
        "unsupported_short_side",
        "paper_shadow_placeholder",
        "wrong_scope_approval",
        "expired_approval",
        "missing_state_action_contract",
        "missing_first_slice_evidence",
    }

    existing_fixture_dirs = {
        path.name
        for path in Path("tests/fixtures/promotion").iterdir()
        if path.is_dir()
    }

    assert expected_fixture_dirs <= existing_fixture_dirs


def test_missing_key_policy_yields_disabled_key_management_blocker() -> None:
    decision = evaluate_promotion_manifest(_fixture_root("key_policy_missing"))

    assert decision.strategy_id == "trend-following-v1"
    assert decision.max_state == PromotionState.DISABLED
    assert decision.blocker_codes == ("ledger_key_worm_controls_missing",)


def test_missing_replay_input_makes_hash_insufficient() -> None:
    decision = evaluate_promotion_manifest(_fixture_root("missing_replay_input"))

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert "replay_path_missing" in decision.blocker_codes


def test_negative_weight_without_short_package_blocks_before_long_only() -> None:
    decision = evaluate_promotion_manifest(_fixture_root("unsupported_short_side"))

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("unsupported_side", "short_support_missing")


def test_paper_shadow_placeholder_decision_loads_from_artifacts() -> None:
    decision = evaluate_promotion_manifest(_fixture_root("paper_shadow_placeholder"))

    assert decision.strategy_id == "trend-following-v1"
    assert decision.max_state == PromotionState.PAPER_SHADOW
    assert decision.blocker_codes == ()
    assert decision.ledger_sequence == 1
    assert decision.ledger_hash is not None


def test_missing_first_slice_evidence_recomputes_blockers_from_artifacts(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_minimal_authority_artifacts(),
        blocker_codes=(),
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert "utility_definition_missing" in decision.blocker_codes
    assert "instrument_package_missing" in decision.blocker_codes


def test_fixture_signature_outside_test_fixture_root_fails_closed(tmp_path) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_minimal_authority_artifacts(),
        trust_root_fixture=True,
        signature_prefix="fixture",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.DISABLED
    assert decision.blocker_codes == ("authority_artifact_invalid",)


def test_schema_invalid_approval_fixtures_fail_closed() -> None:
    for fixture_name in ("wrong_scope_approval", "expired_approval"):
        decision = evaluate_promotion_manifest(_fixture_root(fixture_name))
        assert decision.max_state == PromotionState.DISABLED
        assert decision.blocker_codes == ("authority_artifact_invalid",)


def test_missing_state_action_contract_blocks_promotion() -> None:
    decision = evaluate_promotion_manifest(
        _fixture_root("missing_state_action_contract")
    )

    assert decision.max_state == PromotionState.DISABLED
    assert decision.blocker_codes == ("state_action_contract_missing",)


def test_all_promotion_fixture_manifests_and_trust_roots_are_schema_valid() -> None:
    from tradingx.authority import validate_quant_artifact
    from tradingx.promotion import _schema

    for fixture_dir in Path("tests/fixtures/promotion").iterdir():
        if not fixture_dir.is_dir():
            continue
        manifest = json.loads((fixture_dir / "manifest.json").read_text())
        validate_quant_artifact(manifest, schema=_schema("promotion_manifest"))
        trust_root = json.loads((fixture_dir / "trust_root.json").read_text())
        validate_quant_artifact(trust_root, schema=_schema("trust_root"))
        records_path = fixture_dir / "ledger" / "records.jsonl"
        if records_path.exists():
            for line in records_path.read_text(encoding="utf-8").splitlines():
                if line.startswith('{"sequence": 1') and not line.endswith("}"):
                    continue
                record = json.loads(line)
                validate_quant_artifact(
                    record,
                    schema=_schema("promotion_decision_ledger_record"),
                )
        for payload_path in (fixture_dir / "cas").glob("*/*.json"):
            payload = json.loads(payload_path.read_text())
            kind = str(payload.get("kind", ""))
            if kind == "approval":
                schema_name = "approval_record"
            elif kind == "ledger_key_management_policy":
                schema_name = "ledger_key_management_policy"
            elif kind == "state_action_contract":
                schema_name = "state_action_contract"
            elif kind in {"strategy_capability_manifest", "promotion_evidence"}:
                schema_name = kind
            else:
                schema_name = "content_addressed_artifact"
            validate_quant_artifact(payload, schema=_schema(schema_name))


def test_mutable_manifest_claims_without_ledger_are_not_authority(tmp_path) -> None:
    fixture_root = tmp_path / "fake_authority"
    fixture_root.mkdir()
    (fixture_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "trend-following-v1",
                "requested_state": "production",
                "max_state": "production",
                "artifact_refs": ["sha256:" + "1" * 64],
                "ledger_sequence": 1,
                "ledger_hash": "sha256:" + "2" * 64,
            }
        ),
        encoding="utf-8",
    )

    decision = evaluate_promotion_manifest(fixture_root)

    assert decision.max_state == PromotionState.DISABLED
    assert decision.blocker_codes == ("authority_artifact_invalid",)


def test_hand_edited_projection_to_production_is_projection_drift(tmp_path) -> None:
    decision = PromotionDecision(
        strategy_id="trend-following-v1",
        requested_state=PromotionState.PRODUCTION,
        max_state=PromotionState.PAPER_SHADOW,
        blockers=(),
        artifact_refs=("sha256:" + "1" * 64,),
        ledger_sequence=1,
        ledger_hash="sha256:" + "2" * 64,
    )
    projection_path = tmp_path / "config/strategy/promotion/trend-following-v1.json"
    projection_path.parent.mkdir(parents=True)
    projection_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "trend-following-v1",
                "promotion_state": "production",
                "source_decision_hash": decision.decision_hash,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    drift = check_projection_drift(projection_path, decision)

    assert drift.detected
    assert drift.blocker_code == "authority_artifact_invalid"


def test_projection_without_source_decision_hash_is_projection_drift(tmp_path) -> None:
    decision = PromotionDecision(
        strategy_id="trend-following-v1",
        requested_state=PromotionState.PAPER_TRADING,
        max_state=PromotionState.PAPER_TRADING,
        blockers=(),
        artifact_refs=("sha256:" + "1" * 64,),
        ledger_sequence=1,
        ledger_hash="sha256:" + "2" * 64,
    )
    projection_path = tmp_path / "trend-following-v1.json"
    projection_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "trend-following-v1",
                "promotion_state": "paper_trading",
            }
        ),
        encoding="utf-8",
    )

    drift = check_projection_drift(projection_path, decision)

    assert drift.detected
    assert drift.reason == "projection source decision hash is missing"


def test_state_action_contract_rejects_paper_orders_in_paper_shadow() -> None:
    with pytest.raises(StateActionContractError, match="state_action_contract_missing"):
        validate_state_action_contracts(
            {
                "paper_shadow": {
                    "data_access": "realtime",
                    "order_permission": "paper_orders",
                    "capital_ceiling": "none",
                    "short_permission": "shadow_only",
                }
            }
        )


def test_state_action_contract_requires_roadmap_runtime_semantics() -> None:
    with pytest.raises(StateActionContractError, match="state_action_contract_missing"):
        validate_state_action_contracts(
            {
                "paper_shadow": {
                    "order_permission": "shadow_decisions",
                }
            }
        )


def test_state_action_contracts_load_from_validated_artifact(tmp_path) -> None:
    contract_path = tmp_path / "state_action_contract.json"
    contract_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "kind": "state_action_contract",
                "contracts": _valid_state_action_contracts(),
            }
        ),
        encoding="utf-8",
    )

    contracts = load_state_action_contracts(contract_path)

    assert contracts["paper_shadow"]["order_permission"] == "shadow_decisions"


def test_load_promotion_decision_returns_missing_authority_when_no_artifact(
    tmp_path,
) -> None:
    decision = load_promotion_decision(
        tmp_path / "config/strategy/promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.DISABLED
    assert decision.blocker_codes == ("authority_artifact_invalid",)


def test_load_promotion_decision_ignores_projection_file_claims(tmp_path) -> None:
    projection_root = tmp_path / "config/strategy/promotion"
    projection_root.mkdir(parents=True)
    (projection_root / "trend-following-v1.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "trend-following-v1",
                "promotion_state": "production",
                "max_state": "production",
            }
        ),
        encoding="utf-8",
    )

    decision = load_promotion_decision(
        projection_root,
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.DISABLED
    assert decision.blocker_codes == ("authority_artifact_invalid",)
