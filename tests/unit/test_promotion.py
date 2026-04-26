from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import tradingx.promotion as promotion
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
    requested_state: str = "paper_shadow",
    max_state: str = "paper_shadow",
    target_weights: dict[str, str] | None = None,
    operator_identity_ref: str = "operator:local-a",
    role_registry_ref: str = "role-registry:local-v1",
    trust_root_fixture: bool = False,
    signature_prefix: str = "hmac",
    tamper_mandate_kind: str | None = None,
    tamper_mandate_field: str | None = None,
) -> None:
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "trend-following-v1",
                "requested_state": requested_state,
                "artifact_store_root": "cas",
                "replay_store_root": "cas",
                "ledger_root": "ledger",
                "trust_root_path": "trust_root.json",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    trust_root = TrustRoot(
        root_id="fixture-root",
        trusted_keys={"operator-key": "secret"},
        key_scopes={"operator-key": ("promotion_decision", "mandate_artifact")},
        revoked_keys=frozenset(),
        not_before_utc=datetime(2026, 1, 1, tzinfo=UTC),
        not_after_utc=datetime(2026, 12, 31, tzinfo=UTC),
        fixture_root=trust_root_fixture,
    )
    (root / "trust_root.json").write_text(
        json.dumps(trust_root.to_json(), sort_keys=True),
        encoding="utf-8",
    )
    store = FileContentAddressedStore(root / "cas")
    finalized_payloads: list[dict[str, object]] = []
    lower_bound_spec_hash = ""
    for payload in artifact_payloads:
        finalized = _finalize_test_mandate_artifact(
            payload,
            store=store,
            trust_root=trust_root,
            signature_prefix=signature_prefix,
            operator_identity_ref=operator_identity_ref,
            role_registry_ref=role_registry_ref,
            tamper_field=(
                tamper_mandate_field
                if str(payload.get("kind", "")) == tamper_mandate_kind
                else None
            ),
        )
        if str(finalized.get("kind", "")) == "lower_bound_net_edge_spec":
            lower_bound_spec_hash = str(finalized["payload_hash"])
        if str(finalized.get("kind", "")) == "lower_bound_net_edge_report":
            default_placeholder_hash = "sha256:" + "a" * 64
            if finalized.get("lower_bound_spec_hash") in {
                None,
                "",
                default_placeholder_hash,
            }:
                finalized = {
                    **finalized,
                    "lower_bound_spec_hash": lower_bound_spec_hash,
                }
        finalized_payloads.append(finalized)
    artifact_refs = tuple(store.write_json(payload) for payload in finalized_payloads)
    replay_ref = store.write_json(
        {
            "schema_version": "1.0",
            "kind": "retained_replay_input",
            "strategy_id": "trend-following-v1",
        }
    )
    decision_payload = {
        "schema_version": "1.0",
        "kind": "promotion_decision",
        "strategy_id": "trend-following-v1",
        "requested_state": requested_state,
        "max_state": max_state,
        "target_weights": target_weights or {"SPY": "0.01"},
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
            "operator_identity_ref": operator_identity_ref,
            "role_registry_ref": role_registry_ref,
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


def _finalize_test_mandate_artifact(
    payload: dict[str, object],
    *,
    store: FileContentAddressedStore,
    trust_root: TrustRoot,
    signature_prefix: str,
    operator_identity_ref: str,
    role_registry_ref: str,
    tamper_field: str | None = None,
) -> dict[str, object]:
    kind = str(payload.get("kind", ""))
    if kind not in {
        "investment_mandate",
        "benchmark_policy",
        "jurisdiction_account_use_manifest",
        "instrument_support_package",
        "strategy_capital_role",
        "wealth_thesis",
        "capital_allocation_policy",
        "lower_bound_net_edge_spec",
        "strategy_materiality_policy",
    }:
        return payload
    if "artifact_uri" not in payload:
        return payload
    finalized = dict(payload)
    replay_ref = store.write_json(
        {
            "schema_version": "1.0",
            "kind": "retained_replay_input",
            "strategy_id": str(payload.get("strategy_id", "trend-following-v1")),
            "artifact_kind": kind,
        }
    )
    finalized["ledger_sequence"] = 1
    finalized["authority_ref"] = "fixture-root"
    finalized["replay_input_refs"] = [str(replay_ref)]
    finalized["approval_record_refs"] = []
    finalized["payload_hash"] = promotion._mandate_payload_hash(finalized)
    signature_payload_hash = str(finalized["payload_hash"])
    if signature_prefix == "fixture":
        signature_ref = trust_root.sign_for_test(
            key_id="operator-key",
            payload_hash=signature_payload_hash,
            scope="mandate_artifact",
        )
    else:
        digest = hmac.new(
            b"secret",
            f"{signature_payload_hash}|mandate_artifact".encode(),
            hashlib.sha256,
        ).hexdigest()
        signature_ref = f"{signature_prefix}:operator-key:mandate_artifact:{digest}"
    approval_payload = {
        "schema_version": "1.0",
        "kind": "approval",
        "payload_hash": signature_payload_hash,
        "scope": "mandate_artifact",
        "signature_ref": signature_ref,
        "operator_identity_ref": (
            "" if tamper_field == "operator_identity_ref" else operator_identity_ref
        ),
        "role_registry_ref": (
            "" if tamper_field == "role_registry_ref" else role_registry_ref
        ),
        "authority_boundary_ref": (
            ""
            if tamper_field == "authority_boundary_ref"
            else "authority-boundary:mandate-v1"
        ),
        "risk_accepted": True,
        "signed_at_utc": "2026-04-26T00:00:00Z",
        "expires_at_utc": "2026-12-31T00:00:00Z",
    }
    approval_ref = store.write_json(approval_payload)
    finalized["approval_record_refs"] = [str(approval_ref)]
    if tamper_field == "payload_hash":
        finalized["payload_hash"] = "sha256:" + "f" * 64
    elif tamper_field == "approval_record_refs_empty":
        finalized["approval_record_refs"] = []
    elif tamper_field == "ledger_sequence":
        finalized["ledger_sequence"] = 999
    elif tamper_field == "approval_record_refs":
        finalized["approval_record_refs"] = ["sha256:" + "e" * 64]
    elif tamper_field == "replay_input_refs":
        finalized["replay_input_refs"] = ["sha256:" + "d" * 64]
    elif tamper_field == "authority_ref":
        finalized["authority_ref"] = "wrong-root"
    return finalized


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


def _common_authority_fields(kind: str) -> dict[str, object]:
    return {
        "artifact_uri": f"artifact://wave2/{kind}/trend-following-v1",
        "payload_hash": "sha256:" + "a" * 64,
        "ledger_sequence": 1,
        "approval_record_refs": ["sha256:" + "b" * 64],
        "authority_ref": "authority:wave2-test",
        "created_at_utc": "2026-04-26T00:00:00Z",
        "replay_input_refs": ["sha256:" + "c" * 64],
    }


def _wave2_mandate_artifacts(
    *,
    omit: set[str] | None = None,
    overrides: dict[str, dict[str, object]] | None = None,
) -> tuple[dict[str, object], ...]:
    omitted = omit or set()
    payloads: list[dict[str, object]] = list(_minimal_authority_artifacts())
    by_kind: dict[str, dict[str, object]] = {
        "placeholder_mandate": {
            "schema_version": "1.0",
            "kind": "placeholder_mandate",
            "strategy_id": "trend-following-v1",
            "mandate_id": "legacy-paper-shadow-placeholder",
            "capital_role": "diagnostic-paper-shadow",
            "description": "Legacy placeholder retained only for Wave 1 compatibility.",
        },
        "utility_definition": {
            "schema_version": "1.0",
            "kind": "utility_definition",
            "strategy_id": "trend-following-v1",
            "utility_name": "after_tax_compounded_wealth",
            "description": "Legacy utility definition retained only for compatibility.",
        },
        "allocation_policy": {
            "schema_version": "1.0",
            "kind": "allocation_policy",
            "strategy_id": "trend-following-v1",
            "allocation_policy_id": "legacy-zero-capital",
            "description": "Legacy allocation policy retained only for compatibility.",
        },
        "tax_account_policy": {
            "schema_version": "1.0",
            "kind": "tax_account_policy",
            "strategy_id": "trend-following-v1",
            "tax_mode": "after_tax_modeled",
            "account_type": "taxable_brokerage",
            "financing_assumption": "cash_only_no_margin",
            "description": "Explicit taxable account assumptions.",
        },
        "jurisdiction_account_use": {
            "schema_version": "1.0",
            "kind": "jurisdiction_account_use",
            "strategy_id": "trend-following-v1",
            "jurisdiction": "US",
            "account_use": "self_directed_proprietary",
            "regulatory_status": "resolved",
            "description": "Legacy jurisdiction/account-use policy.",
        },
        "instrument_package": {
            "schema_version": "1.0",
            "kind": "instrument_package",
            "strategy_id": "trend-following-v1",
            "instrument_type": "simple_equity",
            "data_semantics": "split_dividend_adjusted_total_return",
            "execution_semantics": "regular_session_marketable_orders",
            "margin_semantics": "cash_only_no_margin",
            "settlement_semantics": "T+1",
            "corporate_action_semantics": "vendor_adjusted_and_reconciled",
            "tax_semantics": "US_taxable_equity",
            "risk_semantics": "long_only_equity_delta",
            "description": "Legacy simple-equity instrument package.",
        },
        "investment_mandate": {
            "schema_version": "1.0",
            "kind": "investment_mandate",
            "strategy_id": "trend-following-v1",
            "mandate_id": "mandate-test-v1",
            "account_type": "taxable_brokerage",
            "base_currency": "USD",
            "starting_capital": "100000",
            "target_scale": "100000",
            "allowed_instruments": ["simple_equity"],
            "forbidden_instruments": ["option", "future"],
            "leverage_policy": "none",
            "shorting_policy": "not_allowed",
            "liquidity_policy": "daily_liquid",
            "tax_modeled": True,
            "tax_account_type": "taxable",
            "pre_tax_or_after_tax": "after_tax",
            "taxable_or_tax_exempt_status": "taxable",
            "tax_assumptions": "US taxable brokerage after-tax edge required.",
            "fx_policy": "base_currency_only",
            "margin_policy": "cash_only_no_margin",
            "max_drawdown_limit": "0.2",
            "cdar_limit": "0.12",
            "cdar_horizon_days": 63,
            "daily_loss_limit": "0.03",
            "weekly_loss_limit": "0.07",
            "liquidity_runway_days": 30,
            "margin_financing_stress": "cash_only_no_margin",
            "ruin_threshold": "0.3",
            "forced_de_risking_rule": "halt_and_reduce_to_zero",
            "external_cash_flow_policy": "none",
            **_common_authority_fields("investment_mandate"),
        },
        "benchmark_policy": {
            "schema_version": "1.0",
            "kind": "benchmark_policy",
            "strategy_id": "trend-following-v1",
            "benchmark_id": "benchmark-test-v1",
            "ex_ante": True,
            "benchmark_refs": ["SPY_total_return"],
            "cash_benchmark": "SOFR_cash",
            "investable_market_benchmark": "SPY_total_return",
            "allocation_alternative": "60_40_us_equity_bond",
            "no_trade_baseline": "current_holdings_cash",
            "simple_etf_alternative": "SPY",
            "exclusions": [],
            "compatibility": "tax_account_liquidity_instrument_compatible",
            **_common_authority_fields("benchmark_policy"),
        },
        "strategy_capital_role": {
            "schema_version": "1.0",
            "kind": "strategy_capital_role",
            "strategy_id": "trend-following-v1",
            "capital_role": "growth_candidate",
            **_common_authority_fields("strategy_capital_role"),
        },
        "wealth_thesis": {
            "schema_version": "1.0",
            "kind": "wealth_thesis",
            "strategy_id": "trend-following-v1",
            "mechanism": "time_series_trend_persistence",
            "persistence_reason": "behavioral_and_risk_premium_persistence",
            "beneficiary_regime": "medium_horizon_trend_regime",
            "benchmark_to_beat": "SPY_total_return",
            "failure_condition": "lower_bound_edge_not_positive",
            "edge_decay_detector": "rolling_oos_edge_decay",
            "capacity_limit": "100000",
            "kill_condition": "drawdown_or_edge_decay_breach",
            **_common_authority_fields("wealth_thesis"),
        },
        "capital_allocation_policy": {
            "schema_version": "1.0",
            "kind": "capital_allocation_policy",
            "strategy_id": "trend-following-v1",
            "allocation_policy_id": "allocation-test-v1",
            "initial_allocation": "0.01",
            "max_strategy_allocation": "0.05",
            "max_sleeve_allocation": "0.1",
            "reserve_policy": "maintain_95_percent_cash_until_live_probe",
            "reinvestment_policy": "no_reinvestment_before_recertification",
            "scale_up_rule": "only_after_lower_bound_edge_capacity_and_cooldown",
            "scale_down_rule": "reduce_on_drawdown_edge_decay_or_incident",
            "cooldown_days": 30,
            "repeated_look_control": "single_predeclared_monthly_review",
            "strategy_churn_control": "no_replacement_without_new_registration",
            **_common_authority_fields("capital_allocation_policy"),
        },
        "lower_bound_net_edge_spec": {
            "schema_version": "1.0",
            "kind": "lower_bound_net_edge_spec",
            "strategy_id": "trend-following-v1",
            "estimator_family": "hac_adjusted_mean",
            "confidence_level": "0.95",
            "return_horizon": "daily",
            "benchmark_pairing": "SPY_total_return",
            "serial_dependence_correction": "HAC",
            "fat_tail_treatment": "block_bootstrap_stress",
            "minimum_effective_sample_size": 252,
            "prior_policy": "not_bayesian",
            "stress_inputs": ["cost", "slippage", "tax", "financing", "capacity"],
            "pass_threshold": "0",
            **_common_authority_fields("lower_bound_net_edge_spec"),
        },
        "strategy_materiality_policy": {
            "schema_version": "1.0",
            "kind": "strategy_materiality_policy",
            "strategy_id": "trend-following-v1",
            "turnover_threshold": "0.25",
            "volatility_threshold": "0.05",
            "expected_edge_threshold": "0.01",
            "minimum_sample_length": 252,
            "decision_sensitivity_threshold": "0.01",
            "allocation_sensitivity_threshold": "0.005",
            "instrument_class": "simple_equity",
            "safety_rule_sensitivity": "any_breach_material",
            **_common_authority_fields("strategy_materiality_policy"),
        },
        "lower_bound_net_edge_report": {
            "schema_version": "1.0",
            "kind": "lower_bound_net_edge_report",
            "strategy_id": "trend-following-v1",
            "lower_bound_spec_ref": "artifact://wave2/lower_bound_net_edge_spec/trend-following-v1",
            "lower_bound_spec_hash": "sha256:" + "a" * 64,
            "estimator_family": "hac_adjusted_mean",
            "confidence_level": "0.95",
            "return_horizon": "daily",
            "benchmark_pairing": "SPY_total_return",
            "serial_dependence_correction": "HAC",
            "fat_tail_treatment": "block_bootstrap_stress",
            "minimum_effective_sample_size": 252,
            "pre_tax_or_after_tax": "after_tax",
            "taxable_or_tax_exempt_status": "taxable",
            "stress_inputs": ["cost", "slippage", "tax", "financing", "capacity"],
            "lower_bound_net_edge": "0.02",
            "pass_threshold": "0",
            "description": "After-tax lower-bound net edge evidence for tests.",
        },
        "jurisdiction_account_use_manifest": {
            "schema_version": "1.0",
            "kind": "jurisdiction_account_use_manifest",
            "strategy_id": "trend-following-v1",
            "jurisdiction": "US",
            "account_use": "self_directed_proprietary",
            "owner_operator_role": "owner_operator_same_person",
            "classification": "self_directed_proprietary_cash",
            "broker_permission_status": "resolved",
            "margin_permission_status": "not_used",
            "instrument_eligibility_status": "eligible",
            "short_eligibility_status": "not_used",
            "fiduciary_duty_status": "not_applicable",
            "client_suitability_status": "not_applicable",
            "marketing_status": "not_for_external_presentation",
            "custody_status": "not_applicable",
            "record_retention_status": "resolved",
            "account_restriction_status": "none",
            "compliance_review_refs": [],
            "live_trading_ceiling": "production",
            **_common_authority_fields("jurisdiction_account_use_manifest"),
        },
        "instrument_support_package": {
            "schema_version": "1.0",
            "kind": "instrument_support_package",
            "strategy_id": "trend-following-v1",
            "instrument_class": "simple_equity",
            "data_semantics": "split_dividend_adjusted_total_return",
            "corporate_action_treatment": "vendor_adjusted_and_reconciled",
            "execution_venues": ["paper_broker", "alpaca_equity"],
            "order_types": ["market", "limit"],
            "settlement_cycle": "T+1",
            "margin_requirements": "cash_only_no_margin",
            "short_borrow_semantics": "not_allowed",
            "tax_treatment": "US_taxable_equity",
            "risk_model": "long_only_equity_delta",
            "operational_controls": ["pre_trade_controls", "reconciliation"],
            "broker_permissions": ["paper_equity", "live_equity_cash"],
            "promotion_ceiling": "production",
            **_common_authority_fields("instrument_support_package"),
        },
    }
    for kind, patch in (overrides or {}).items():
        by_kind[kind] = {**by_kind[kind], **patch}
    for kind, payload in by_kind.items():
        if kind not in omitted:
            payloads.append(payload)
    return tuple(payloads)


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


def test_missing_investment_mandate_blocks_capital_bearing_promotion(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(omit={"investment_mandate"}),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert "utility_definition_missing" in decision.blocker_codes


def test_mandate_artifact_wrong_payload_hash_fails_authority(tmp_path) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(),
        requested_state="production",
        max_state="production",
        tamper_mandate_kind="investment_mandate",
        tamper_mandate_field="payload_hash",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.DISABLED
    assert "authority_artifact_invalid" in decision.blocker_codes


def test_mandate_artifact_wrong_sequence_approval_replay_or_authority_ref_fails(
    tmp_path,
) -> None:
    for tamper_field, expected_code in (
        ("ledger_sequence", "authority_artifact_invalid"),
        ("approval_record_refs_empty", "authority_artifact_invalid"),
        ("approval_record_refs", "authority_artifact_invalid"),
        ("replay_input_refs", "replay_path_missing"),
        ("authority_ref", "authority_artifact_invalid"),
        ("operator_identity_ref", "authority_artifact_invalid"),
        ("role_registry_ref", "authority_artifact_invalid"),
        ("authority_boundary_ref", "authority_artifact_invalid"),
    ):
        bundle_root = tmp_path / tamper_field / "promotion" / "trend-following-v1"
        _write_hmac_signed_bundle(
            bundle_root,
            artifact_payloads=_wave2_mandate_artifacts(),
            requested_state="production",
            max_state="production",
            tamper_mandate_kind="investment_mandate",
            tamper_mandate_field=tamper_field,
        )

        decision = load_promotion_decision(
            tmp_path / tamper_field / "promotion",
            strategy_id="trend-following-v1",
        )

        assert expected_code in decision.blocker_codes
        assert not promotion.state_allows(
            decision.max_state,
            PromotionState.TINY_LIVE_PROBE,
        )


def test_unverified_duplicate_mandate_artifact_cannot_mask_signed_role(
    tmp_path,
) -> None:
    unsigned_growth_role = {
        "schema_version": "1.0",
        "kind": "strategy_capital_role",
        "strategy_id": "trend-following-v1",
        "capital_role": "growth_candidate",
        "description": "Unsigned duplicate must not drive semantics.",
    }
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=(unsigned_growth_role,)
        + _wave2_mandate_artifacts(
            overrides={"strategy_capital_role": {"capital_role": "research_only"}}
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("capital_role_research_only",)


def test_conflicting_signed_duplicate_mandate_artifacts_fail_closed(tmp_path) -> None:
    duplicate_research_role = {
        "schema_version": "1.0",
        "kind": "strategy_capital_role",
        "strategy_id": "trend-following-v1",
        "capital_role": "research_only",
        **_common_authority_fields("strategy_capital_role_duplicate"),
    }
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts() + (duplicate_research_role,),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.DISABLED
    assert "authority_artifact_invalid" in decision.blocker_codes


def test_tax_account_financing_unspecified_caps_at_paper_shadow(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "investment_mandate": {
                    "tax_modeled": False,
                    "pre_tax_or_after_tax": "pre_tax",
                    "taxable_or_tax_exempt_status": "taxable",
                    "tax_assumptions": "unspecified",
                },
                "tax_account_policy": {
                    "tax_mode": "unspecified",
                    "financing_assumption": "unspecified",
                },
            }
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.PAPER_SHADOW
    assert decision.blocker_codes == ("tax_account_financing_unspecified",)


def test_taxable_production_without_after_tax_edge_evidence_caps_at_paper_trading(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            omit={"lower_bound_net_edge_report"}
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.PAPER_TRADING
    assert decision.blocker_codes == ("after_tax_edge_missing_for_taxable_account",)


def test_taxable_production_with_pretax_only_edge_evidence_is_not_live_capable(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "lower_bound_net_edge_report": {
                    "pre_tax_or_after_tax": "pre_tax",
                }
            }
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.PAPER_TRADING
    assert decision.blocker_codes == ("after_tax_edge_missing_for_taxable_account",)


def test_taxable_production_with_negative_lower_bound_fails_expected_wealth(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "lower_bound_net_edge_report": {
                    "lower_bound_net_edge": "-0.01",
                    "pass_threshold": "0",
                }
            }
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("net_edge_lower_bound_below_threshold",)


def test_experiment_and_dataset_provenance_blockers_cap_promotion() -> None:
    blockers = promotion.evaluate_provenance_blockers(
        artifact_payloads=(
            {
                "schema_version": "1.0",
                "kind": "trial_universe_manifest",
                "promotion_decision_scope": "scope-prod-001",
                "status": "contaminated",
                "blocker_codes": ["trial_lineage_contaminated"],
            },
            {
                "schema_version": "1.0",
                "kind": "dataset_manifest",
                "dataset_id": "dataset-spy-v1",
                "status": "replay_input_missing",
                "blocker_codes": ["replay_path_missing"],
            },
        )
    )

    assert "trial_lineage_contaminated" in tuple(blocker.code for blocker in blockers)
    assert "replay_path_missing" in tuple(blocker.code for blocker in blockers)
    assert "point_in_time_data_incomplete" in tuple(
        blocker.code for blocker in blockers
    )
    assert promotion.strictest_state_cap(blockers) == PromotionState.RESEARCH_ONLY


def test_tax_exempt_production_without_lower_bound_report_is_not_live_capable(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            omit={"lower_bound_net_edge_report"},
            overrides={
                "investment_mandate": {
                    "tax_modeled": False,
                    "tax_account_type": "tax_exempt",
                    "pre_tax_or_after_tax": "pre_tax",
                    "taxable_or_tax_exempt_status": "tax_exempt",
                    "tax_assumptions": (
                        "Account is tax-exempt; pre-tax edge still required."
                    ),
                }
            },
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("lower_bound_net_edge_undefined",)


def test_tax_exempt_production_requires_complete_lower_bound_stress_inputs(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "investment_mandate": {
                    "tax_modeled": False,
                    "tax_account_type": "tax_exempt",
                    "pre_tax_or_after_tax": "pre_tax",
                    "taxable_or_tax_exempt_status": "tax_exempt",
                    "tax_assumptions": (
                        "Account is tax-exempt; pre-tax edge still required."
                    ),
                },
                "lower_bound_net_edge_report": {
                    "pre_tax_or_after_tax": "pre_tax",
                    "taxable_or_tax_exempt_status": "tax_exempt",
                    "stress_inputs": ["cost", "financing"],
                },
            },
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("lower_bound_net_edge_undefined",)


def test_tax_exempt_production_with_complete_lower_bound_report_can_pass(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "investment_mandate": {
                    "tax_modeled": False,
                    "tax_account_type": "tax_exempt",
                    "pre_tax_or_after_tax": "pre_tax",
                    "taxable_or_tax_exempt_status": "tax_exempt",
                    "tax_assumptions": (
                        "Account is tax-exempt; pre-tax edge still required."
                    ),
                },
                "lower_bound_net_edge_report": {
                    "pre_tax_or_after_tax": "pre_tax",
                    "taxable_or_tax_exempt_status": "tax_exempt",
                },
            },
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.PRODUCTION
    assert decision.blocker_codes == ()


def test_signed_capital_allocation_policy_exports_runtime_limit(tmp_path) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.PRODUCTION
    assert decision.strategy_allocation_limits == (
        {
            "strategy_id": "trend-following-v1",
            "max_strategy_allocation": "0.05",
        },
    )


def test_lower_bound_report_missing_spec_binding_is_not_live_capable(
    tmp_path,
) -> None:
    minimal_report = {
        "schema_version": "1.0",
        "kind": "lower_bound_net_edge_report",
        "strategy_id": "trend-following-v1",
        "pre_tax_or_after_tax": "after_tax",
        "stress_inputs": ["cost", "slippage", "tax", "financing", "capacity"],
        "lower_bound_net_edge": "0.02",
        "pass_threshold": "0",
    }
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(omit={"lower_bound_net_edge_report"})
        + (minimal_report,),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("lower_bound_net_edge_undefined",)


def test_lower_bound_report_must_match_signed_spec_and_friction_fields(
    tmp_path,
) -> None:
    for field_patch in (
        {"lower_bound_spec_ref": "artifact://wrong-spec"},
        {"lower_bound_spec_hash": "sha256:" + "f" * 64},
        {"estimator_family": "point_estimate"},
        {"confidence_level": "0.5"},
        {"benchmark_pairing": "QQQ_total_return"},
        {"stress_inputs": ["cost", "tax", "financing", "capacity"]},
        {"minimum_effective_sample_size": 1},
    ):
        bundle_root = (
            tmp_path
            / str(len(field_patch))
            / next(iter(field_patch))
            / "promotion"
            / "trend-following-v1"
        )
        _write_hmac_signed_bundle(
            bundle_root,
            artifact_payloads=_wave2_mandate_artifacts(
                overrides={"lower_bound_net_edge_report": field_patch}
            ),
            requested_state="production",
            max_state="production",
        )

        decision = load_promotion_decision(
            bundle_root.parent,
            strategy_id="trend-following-v1",
        )

        assert decision.max_state == PromotionState.RESEARCH_ONLY
        assert decision.blocker_codes == ("lower_bound_net_edge_undefined",)


def test_unknown_jurisdiction_or_account_use_caps_live_at_paper_trading(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "jurisdiction_account_use_manifest": {
                    "jurisdiction": "unknown",
                    "account_use": "unknown",
                    "broker_permission_status": "unknown",
                },
                "jurisdiction_account_use": {
                    "jurisdiction": "unknown",
                    "account_use": "unknown",
                    "regulatory_status": "unknown",
                },
            }
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.PAPER_TRADING
    assert decision.blocker_codes == ("jurisdiction_account_use_unknown",)


def test_external_capital_unknown_disables_promotion(tmp_path) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "jurisdiction_account_use_manifest": {
                    "account_use": "client",
                    "classification": "client_advisory",
                    "fiduciary_duty_status": "unknown",
                    "client_suitability_status": "unknown",
                    "custody_status": "unknown",
                    "record_retention_status": "unknown",
                    "account_restriction_status": "unknown",
                },
                "jurisdiction_account_use": {
                    "account_use": "client",
                    "regulatory_status": "unknown",
                },
            }
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.DISABLED
    assert decision.blocker_codes == ("external_capital_compliance_unknown",)


def test_inactive_and_research_only_capital_roles_block_capital_promotion(
    tmp_path,
) -> None:
    for role, expected_code, expected_state in (
        ("inactive", "capital_role_inactive", PromotionState.DISABLED),
        ("research_only", "capital_role_research_only", PromotionState.RESEARCH_ONLY),
    ):
        bundle_root = tmp_path / role / "promotion" / "trend-following-v1"
        _write_hmac_signed_bundle(
            bundle_root,
            artifact_payloads=_wave2_mandate_artifacts(
                overrides={"strategy_capital_role": {"capital_role": role}}
            ),
            requested_state="production",
            max_state="production",
        )

        decision = load_promotion_decision(
            tmp_path / role / "promotion",
            strategy_id="trend-following-v1",
        )

        assert decision.max_state == expected_state
        assert decision.blocker_codes == (expected_code,)


def test_non_ex_ante_benchmark_policy_blocks_capital_promotion(tmp_path) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "benchmark_policy": {
                    "ex_ante": False,
                }
            }
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("benchmark_policy_not_ex_ante",)


def test_mandate_policy_ceiling_below_request_blocks_capital_promotion(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "jurisdiction_account_use_manifest": {
                    "live_trading_ceiling": "paper_trading",
                },
                "instrument_support_package": {
                    "promotion_ceiling": "paper_trading",
                },
            }
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("mandate_promotion_ceiling_exceeded",)


def test_allocation_policy_limit_exceeded_caps_at_paper_shadow(tmp_path) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(),
        requested_state="production",
        max_state="production",
        target_weights={"SPY": "1"},
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.PAPER_SHADOW
    assert decision.blocker_codes == ("allocation_policy_limit_exceeded",)


def test_invalid_lower_bound_spec_math_blocks_statistical_authority(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            overrides={
                "lower_bound_net_edge_spec": {
                    "confidence_level": "2",
                    "minimum_effective_sample_size": -1,
                    "stress_inputs": [],
                    "serial_dependence_correction": "none",
                    "fat_tail_treatment": "none",
                }
            }
        ),
        requested_state="production",
        max_state="production",
        target_weights={"SPY": "0.01"},
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("lower_bound_net_edge_undefined",)


def test_missing_simple_equity_instrument_support_package_blocks_promotion(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(omit={"instrument_support_package"}),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert decision.blocker_codes == ("instrument_package_missing",)


def test_missing_strategy_materiality_policy_caps_at_paper_shadow(tmp_path) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(
            omit={"strategy_materiality_policy"}
        ),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.PAPER_SHADOW
    assert decision.blocker_codes == ("strategy_materiality_policy_missing",)


def test_opportunity_cost_report_cannot_override_mandate_blocker(tmp_path) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    artifacts = _wave2_mandate_artifacts(omit={"investment_mandate"}) + (
        {
            "schema_version": "1.0",
            "kind": "opportunity_cost_report",
            "strategy_id": "trend-following-v1",
            "description": (
                "Diagnostic opportunity-cost report requests capital allocation "
                "but cannot override mandate blockers."
            ),
        },
    )
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=artifacts,
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.RESEARCH_ONLY
    assert "utility_definition_missing" in decision.blocker_codes


def test_fixture_role_registry_ref_outside_fixture_root_fails_closed(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(),
        requested_state="paper_shadow",
        max_state="paper_shadow",
        role_registry_ref="role-registry:fixture-v1",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )

    assert decision.max_state == PromotionState.DISABLED
    assert decision.blocker_codes == ("authority_artifact_invalid",)


def test_promotion_decision_json_separates_mandate_and_statistical_blockers(
    tmp_path,
) -> None:
    bundle_root = tmp_path / "promotion" / "trend-following-v1"
    _write_hmac_signed_bundle(
        bundle_root,
        artifact_payloads=_wave2_mandate_artifacts(omit={"investment_mandate"}),
        blocker_codes=("lower_bound_net_edge_undefined",),
        requested_state="production",
        max_state="production",
    )

    decision = load_promotion_decision(
        tmp_path / "promotion",
        strategy_id="trend-following-v1",
    )
    payload = decision.to_json()

    assert "utility_definition_missing" in payload["mandate_blocker_codes"]
    assert payload["statistical_blocker_codes"] == ["lower_bound_net_edge_undefined"]


def test_legacy_operator_artifacts_are_classified_non_v5_authority() -> None:
    activation_classification = promotion.classify_legacy_operator_artifact(
        artifact_type="strategy_activation_record",
        payload={
            "activation_id": "activation-1",
            "strategy_id": "trend-following-v1",
            "status": "active",
        },
    )
    weights_classification = promotion.classify_legacy_operator_artifact(
        artifact_type="approved_weight_snapshot",
        payload={
            "snapshot_id": "weights-1",
            "strategy_id": "trend-following-v1",
            "status": "approved",
        },
    )

    assert activation_classification["v5_authority"] is False
    assert activation_classification["authority_status"] == "legacy_non_authority"
    assert weights_classification["v5_authority"] is False
    assert weights_classification["authority_status"] == "legacy_non_authority"


def test_wave2_mandate_schemas_validate_minimal_authority_artifacts() -> None:
    from tradingx.authority import validate_quant_artifact
    from tradingx.promotion import _schema

    schema_by_kind = {
        "investment_mandate": "investment_mandate",
        "benchmark_policy": "benchmark_policy",
        "jurisdiction_account_use_manifest": "jurisdiction_account_use_manifest",
        "instrument_support_package": "instrument_support_package",
        "strategy_capital_role": "strategy_capital_role",
        "wealth_thesis": "wealth_thesis",
        "capital_allocation_policy": "capital_allocation_policy",
        "lower_bound_net_edge_spec": "lower_bound_net_edge_spec",
        "strategy_materiality_policy": "strategy_materiality_policy",
    }
    payloads = {
        str(payload["kind"]): payload
        for payload in _wave2_mandate_artifacts()
        if str(payload["kind"]) in schema_by_kind
    }

    for kind, schema_name in schema_by_kind.items():
        validate_quant_artifact(payloads[kind], schema=_schema(schema_name))


def test_wave2_fixture_bundles_replay_from_disk() -> None:
    expected = {
        "valid": ("paper_shadow", ()),
        "external_capital_unknown": (
            "disabled",
            ("external_capital_compliance_unknown",),
        ),
        "materiality_policy_missing": (
            "paper_shadow",
            ("strategy_materiality_policy_missing",),
        ),
        "empty_approval_refs": (
            "disabled",
            ("authority_artifact_invalid", "utility_definition_missing"),
        ),
        "unsigned_duplicate_role": (
            "research_only",
            ("capital_role_research_only",),
        ),
        "signed_duplicate_conflict": (
            "disabled",
            ("authority_artifact_invalid",),
        ),
        "tax_exempt_missing_edge": (
            "research_only",
            ("lower_bound_net_edge_undefined",),
        ),
    }
    for fixture_name, (max_state, blocker_codes) in expected.items():
        decision = evaluate_promotion_manifest(
            Path("tests/fixtures/mandate") / fixture_name
        )

        assert decision.max_state.value == max_state
        assert decision.blocker_codes == blocker_codes


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
            elif (
                kind
                in {
                    "investment_mandate",
                    "benchmark_policy",
                    "jurisdiction_account_use_manifest",
                    "instrument_support_package",
                    "strategy_capital_role",
                    "wealth_thesis",
                    "capital_allocation_policy",
                    "lower_bound_net_edge_spec",
                    "strategy_materiality_policy",
                }
                and "artifact_uri" in payload
            ):
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
