from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

from tradingx.authority import (
    AuthorityLedger,
    AuthorityLedgerError,
    AuthorityLedgerRecord,
    ContentAddressedRef,
    FileContentAddressedStore,
    TrustRoot,
    TrustRootError,
    canonical_payload_hash,
    validate_quant_artifact,
    verify_approval_signature,
)
from tradingx.data_fingerprint import dataset_manifest_blocker_codes

LEGACY_NON_AUTHORITY_STATUS = "legacy_non_authority"
NOT_RUNTIME_APPLICABLE = "not_runtime_applicable"
DEFAULT_STATE_ACTION_CONTRACTS: dict[str, dict[str, object]] = {
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

_CLI_OUTPUT_FIELDS = {
    "promotion-check.blockers",
    "promotion-check.max_state",
    "promotion-check.artifact_refs",
    "promotion-check.mandate_blockers",
    "promotion-check.statistical_blockers",
}
_WEB_REPORT_FIELDS = {
    "dashboard.document_summary.v5_authority_status",
    "dashboard.gate_authority_statuses",
    "dashboard.recommendation_authority_statuses",
}
_RUNTIME_ENFORCEMENT_POINTS = {
    "activation_refusal",
    "order_route_refusal",
    "promotion_check_refusal",
}
_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "quant"
_FIRST_SLICE_REQUIRED_ARTIFACT_BLOCKERS = {
    "placeholder_mandate": "utility_definition_missing",
    "benchmark_policy": "utility_definition_missing",
    "wealth_thesis": "utility_definition_missing",
    "utility_definition": "utility_definition_missing",
    "allocation_policy": "utility_definition_missing",
    "tax_account_policy": "tax_account_financing_unspecified",
    "jurisdiction_account_use": "jurisdiction_account_use_unknown",
    "instrument_package": "instrument_package_missing",
}
_FIRST_SLICE_EQUIVALENT_KINDS = {
    "placeholder_mandate": ("investment_mandate",),
    "benchmark_policy": ("benchmark_policy",),
    "wealth_thesis": ("wealth_thesis",),
    "utility_definition": (
        "investment_mandate",
        "strategy_capital_role",
        "wealth_thesis",
    ),
    "allocation_policy": ("capital_allocation_policy",),
    "tax_account_policy": ("investment_mandate",),
    "jurisdiction_account_use": ("jurisdiction_account_use_manifest",),
    "instrument_package": ("instrument_support_package",),
}
_MANDATE_ARTIFACT_SCHEMA_NAMES = {
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
_MANDATE_REQUIRED_ARTIFACT_BLOCKERS = {
    "investment_mandate": "utility_definition_missing",
    "benchmark_policy": "utility_definition_missing",
    "strategy_capital_role": "utility_definition_missing",
    "wealth_thesis": "utility_definition_missing",
    "capital_allocation_policy": "utility_definition_missing",
    "lower_bound_net_edge_spec": "utility_definition_missing",
    "jurisdiction_account_use_manifest": "jurisdiction_account_use_unknown",
    "instrument_support_package": "instrument_package_missing",
    "strategy_materiality_policy": "strategy_materiality_policy_missing",
}
_MANDATE_BLOCKER_CODES = {
    "utility_definition_missing",
    "tax_account_financing_unspecified",
    "jurisdiction_account_use_unknown",
    "external_capital_compliance_unknown",
    "after_tax_edge_missing_for_taxable_account",
    "instrument_package_missing",
    "strategy_materiality_policy_missing",
    "capital_role_inactive",
    "capital_role_research_only",
    "benchmark_policy_not_ex_ante",
    "mandate_promotion_ceiling_exceeded",
    "allocation_policy_limit_exceeded",
}
_STATISTICAL_BLOCKER_CODES = {
    "lower_bound_net_edge_undefined",
    "net_edge_lower_bound_below_threshold",
    "trial_lineage_contaminated",
    "trial_universe_incomplete",
    "dsr_pbo_inputs_incomplete",
    "point_in_time_data_incomplete",
    "legacy_statistical_evidence",
    "pending_threshold",
}
_AUTHORITY_BLOCKER_CODES = {
    "authority_artifact_invalid",
    "ledger_integrity_violation",
    "ledger_key_worm_controls_missing",
    "state_action_contract_missing",
    "replay_path_missing",
}
_UNKNOWN_DECLARATIONS = {
    "",
    "unknown",
    "unspecified",
    "not_declared",
    "missing",
    "unresolved",
    "none",
}
_EXTERNAL_ACCOUNT_USES = {
    "advisory",
    "client",
    "client_advisory",
    "external_capital",
    "fund",
    "retirement",
}
_FIXTURE_MARKERS = ("fixture", "test-only", "test_only")
_LOWER_BOUND_REQUIRED_STRESS_INPUTS = frozenset(
    {"cost", "slippage", "tax", "financing", "capacity"}
)
_AUTHORITY_EVIDENCE_ARTIFACT_KINDS = {
    "strategy_capability_manifest",
    "promotion_evidence",
}
_EMITTED_BLOCKERS_REQUIRING_REAL_COVERAGE = {
    "authority_artifact_invalid",
    "ledger_key_worm_controls_missing",
    "state_action_contract_missing",
    "replay_path_missing",
    "tax_account_financing_unspecified",
    "jurisdiction_account_use_unknown",
    "utility_definition_missing",
    "instrument_package_missing",
    "external_capital_compliance_unknown",
    "strategy_materiality_policy_missing",
    "capital_role_inactive",
    "capital_role_research_only",
    "benchmark_policy_not_ex_ante",
    "mandate_promotion_ceiling_exceeded",
    "allocation_policy_limit_exceeded",
    "lower_bound_net_edge_undefined",
    "net_edge_lower_bound_below_threshold",
    "unsupported_side",
    "short_support_missing",
    "legacy_statistical_evidence",
    "stale_sources",
}


class PromotionState(StrEnum):
    DISABLED = "disabled"
    RESEARCH_ONLY = "research_only"
    PAPER_SHADOW = "paper_shadow"
    PAPER_TRADING = "paper_trading"
    TINY_LIVE_PROBE = "tiny_live_probe"
    PRODUCTION = "production"


_STATE_ORDER = {
    PromotionState.DISABLED: 0,
    PromotionState.RESEARCH_ONLY: 1,
    PromotionState.PAPER_SHADOW: 2,
    PromotionState.PAPER_TRADING: 3,
    PromotionState.TINY_LIVE_PROBE: 4,
    PromotionState.PRODUCTION: 5,
}


class StateActionContractError(ValueError):
    """Raised when a state/action contract is more permissive than allowed."""


@dataclass(frozen=True)
class Blocker:
    code: str

    @property
    def max_state(self) -> PromotionState:
        return BLOCKER_REGISTRY[self.code].max_state


@dataclass(frozen=True)
class BlockerRegistryRecord:
    code: str
    owning_wave: str
    max_state: PromotionState
    condition: str
    remediation: str
    migration_behavior: str
    schema_field: str
    evaluator: str
    red_test: str
    fixture: str
    cli_output: str
    web_report_field: str
    runtime_enforcement: str

    def without_runtime_mapping(self) -> BlockerRegistryRecord:
        return replace(self, runtime_enforcement="")


def _record(
    code: str,
    max_state: PromotionState,
    *,
    condition: str | None = None,
    owning_wave: str = "legacy_inventory",
    fixture: str = NOT_RUNTIME_APPLICABLE,
    evaluator: str = NOT_RUNTIME_APPLICABLE,
    red_test: str = NOT_RUNTIME_APPLICABLE,
    cli_output: str = NOT_RUNTIME_APPLICABLE,
    web_report_field: str = NOT_RUNTIME_APPLICABLE,
    runtime_enforcement: str = NOT_RUNTIME_APPLICABLE,
) -> BlockerRegistryRecord:
    return BlockerRegistryRecord(
        code=code,
        owning_wave=owning_wave,
        max_state=max_state,
        condition=condition or f"{code} condition is present.",
        remediation=f"Resolve {code} and append a replacement authority artifact.",
        migration_behavior=(
            "Legacy artifacts remain diagnostic until this blocker is absent."
        ),
        schema_field=f"blockers.{code}",
        evaluator=evaluator,
        red_test=red_test,
        fixture=fixture,
        cli_output=cli_output,
        web_report_field=web_report_field,
        runtime_enforcement=runtime_enforcement,
    )


_REGISTRY_SEEDS: tuple[tuple[str, PromotionState], ...] = (
    ("authority_artifact_invalid", PromotionState.DISABLED),
    ("ledger_integrity_violation", PromotionState.DISABLED),
    ("ledger_key_worm_controls_missing", PromotionState.DISABLED),
    ("state_action_contract_missing", PromotionState.DISABLED),
    ("replay_path_missing", PromotionState.RESEARCH_ONLY),
    ("tax_account_financing_unspecified", PromotionState.PAPER_SHADOW),
    ("after_tax_edge_missing_for_taxable_account", PromotionState.PAPER_TRADING),
    ("jurisdiction_account_use_unknown", PromotionState.PAPER_TRADING),
    ("external_capital_compliance_unknown", PromotionState.DISABLED),
    ("utility_definition_missing", PromotionState.RESEARCH_ONLY),
    ("strategy_materiality_policy_missing", PromotionState.PAPER_SHADOW),
    ("capital_role_inactive", PromotionState.DISABLED),
    ("capital_role_research_only", PromotionState.RESEARCH_ONLY),
    ("benchmark_policy_not_ex_ante", PromotionState.RESEARCH_ONLY),
    ("mandate_promotion_ceiling_exceeded", PromotionState.RESEARCH_ONLY),
    ("allocation_policy_limit_exceeded", PromotionState.PAPER_SHADOW),
    ("lower_bound_net_edge_undefined", PromotionState.RESEARCH_ONLY),
    ("net_edge_lower_bound_below_threshold", PromotionState.RESEARCH_ONLY),
    ("trial_lineage_contaminated", PromotionState.RESEARCH_ONLY),
    ("trial_universe_incomplete", PromotionState.PAPER_SHADOW),
    ("dsr_pbo_inputs_incomplete", PromotionState.PAPER_SHADOW),
    ("point_in_time_data_incomplete", PromotionState.RESEARCH_ONLY),
    ("execution_semantics_incomplete", PromotionState.PAPER_SHADOW),
    ("execution_sample_power_missing", PromotionState.PAPER_SHADOW),
    ("capacity_lower_bound_missing", PromotionState.PAPER_SHADOW),
    ("live_sample_requirement_unmet", PromotionState.TINY_LIVE_PROBE),
    ("pre_trade_control_missing", PromotionState.PAPER_TRADING),
    ("short_legal_mechanics_missing", PromotionState.RESEARCH_ONLY),
    ("instrument_package_missing", PromotionState.RESEARCH_ONLY),
    ("optimizer_or_sizing_lockbox_missing", PromotionState.PAPER_SHADOW),
    ("drift_monitor_spec_missing", PromotionState.PAPER_SHADOW),
    ("capacity_extrapolation_risk", PromotionState.PAPER_SHADOW),
    ("unsupported_side", PromotionState.RESEARCH_ONLY),
    ("short_support_missing", PromotionState.RESEARCH_ONLY),
    ("pending_threshold", PromotionState.PAPER_SHADOW),
    ("legacy_statistical_evidence", PromotionState.PAPER_SHADOW),
    ("unsupported_cost_bucket", PromotionState.PAPER_SHADOW),
    ("unrecorded_material_change", PromotionState.PAPER_SHADOW),
    ("dependency_scope_unresolved", PromotionState.PAPER_SHADOW),
    ("missing_requirements", PromotionState.PAPER_SHADOW),
    ("outbox_dedupe_constraint_missing", PromotionState.PAPER_SHADOW),
    ("missing_sources", PromotionState.PAPER_SHADOW),
    ("initial_import_incomplete", PromotionState.PAPER_SHADOW),
    ("write_path_inactive", PromotionState.PAPER_SHADOW),
    ("unprojected_sources", PromotionState.PAPER_SHADOW),
    ("stale_sources", PromotionState.PAPER_SHADOW),
    ("lagging_sources", PromotionState.PAPER_SHADOW),
    ("not_ready_sources", PromotionState.PAPER_SHADOW),
    ("operator_hold", PromotionState.PAPER_TRADING),
    ("requested_mode_unknown", PromotionState.PAPER_TRADING),
    ("dry_run_enabled", PromotionState.PAPER_TRADING),
    ("live_enable_evidence_missing", PromotionState.PAPER_TRADING),
    ("manual_kill_switch_active", PromotionState.PAPER_TRADING),
    ("market_data_degraded", PromotionState.PAPER_TRADING),
    ("insufficient_bars", PromotionState.PAPER_SHADOW),
    ("cpcv_insufficient_history", PromotionState.PAPER_SHADOW),
    ("halt_by_operator", PromotionState.PAPER_TRADING),
    ("drift_alarm_live", PromotionState.PAPER_SHADOW),
    ("sleeve_sharpe_below_threshold_6m", PromotionState.PAPER_SHADOW),
    ("regime_stressed", PromotionState.PAPER_SHADOW),
    ("regime_stressed_liquidate", PromotionState.PAPER_SHADOW),
    ("insufficient_history", PromotionState.PAPER_SHADOW),
    ("broker_mode_not_live", PromotionState.PAPER_TRADING),
    ("missing_live_credentials", PromotionState.PAPER_TRADING),
    ("config_layer_disabled", PromotionState.PAPER_TRADING),
    ("env_layer_disabled", PromotionState.PAPER_TRADING),
    ("code_layer_disabled", PromotionState.PAPER_TRADING),
    ("web_write_signing_unconfigured", PromotionState.PAPER_TRADING),
    ("operator_signoff_missing", PromotionState.PAPER_TRADING),
    ("gate4_checklist_missing", PromotionState.PAPER_TRADING),
    ("non_positive_quantity", PromotionState.PAPER_TRADING),
    ("invalid_symbol", PromotionState.PAPER_TRADING),
    ("live_mode_disabled", PromotionState.PAPER_TRADING),
    ("liquidity_filter", PromotionState.PAPER_TRADING),
    ("price_floor", PromotionState.PAPER_TRADING),
    ("single_symbol_concentration", PromotionState.PAPER_TRADING),
    ("intraday_margin", PromotionState.PAPER_TRADING),
    ("stale_market_data", PromotionState.PAPER_TRADING),
    ("stale_broker_state", PromotionState.PAPER_TRADING),
    ("kill_switch", PromotionState.PAPER_TRADING),
    ("operator_halt", PromotionState.PAPER_TRADING),
    ("outside_regular_hours", PromotionState.PAPER_TRADING),
    ("insufficient_buying_power", PromotionState.PAPER_TRADING),
    ("restricted_symbol", PromotionState.PAPER_TRADING),
    ("symbol_halted", PromotionState.PAPER_TRADING),
    ("after_hours", PromotionState.PAPER_TRADING),
    ("market_closed", PromotionState.PAPER_TRADING),
    ("malformed_payload", PromotionState.PAPER_TRADING),
    ("broker_rejected", PromotionState.PAPER_TRADING),
    ("kill_switch_active", PromotionState.PAPER_TRADING),
    ("daily_drawdown_halt_sticky", PromotionState.PAPER_TRADING),
    ("daily_drawdown_halt", PromotionState.PAPER_TRADING),
    ("close_window_entry_blocked", PromotionState.PAPER_TRADING),
    ("stale_quote", PromotionState.PAPER_TRADING),
    ("spread_absolute_cap", PromotionState.PAPER_TRADING),
    ("spread_relative_cap", PromotionState.PAPER_TRADING),
    ("daily_entry_cap_reached", PromotionState.PAPER_TRADING),
    ("per_symbol_entry_cap_reached", PromotionState.PAPER_TRADING),
    ("max_concurrent_positions_reached", PromotionState.PAPER_TRADING),
    ("same_session_reentry_cooldown", PromotionState.PAPER_TRADING),
    ("total_deployed_cap_reached", PromotionState.PAPER_TRADING),
)

BLOCKER_REGISTRY: dict[str, BlockerRegistryRecord] = {
    code: _record(code, max_state) for code, max_state in _REGISTRY_SEEDS
}

for _code, _fixture, _red_test in (
    (
        "authority_artifact_invalid",
        "tests/fixtures/promotion/invalid",
        "test_mutable_manifest_claims_without_ledger_are_not_authority",
    ),
    (
        "ledger_key_worm_controls_missing",
        "tests/fixtures/promotion/key_policy_missing",
        "test_missing_key_policy_yields_disabled_key_management_blocker",
    ),
    (
        "state_action_contract_missing",
        "tests/fixtures/promotion/missing_state_action_contract",
        "test_missing_state_action_contract_blocks_promotion",
    ),
    (
        "replay_path_missing",
        "tests/fixtures/promotion/missing_replay_input",
        "test_missing_replay_input_makes_hash_insufficient",
    ),
    (
        "tax_account_financing_unspecified",
        "tests/fixtures/promotion/missing_first_slice_evidence",
        "test_missing_first_slice_evidence_recomputes_blockers_from_artifacts",
    ),
    (
        "jurisdiction_account_use_unknown",
        "tests/fixtures/promotion/missing_first_slice_evidence",
        "test_missing_first_slice_evidence_recomputes_blockers_from_artifacts",
    ),
    (
        "utility_definition_missing",
        "tests/fixtures/promotion/missing_first_slice_evidence",
        "test_missing_first_slice_evidence_recomputes_blockers_from_artifacts",
    ),
    (
        "instrument_package_missing",
        "tests/fixtures/promotion/missing_first_slice_evidence",
        "test_missing_first_slice_evidence_recomputes_blockers_from_artifacts",
    ),
    (
        "external_capital_compliance_unknown",
        "tests/fixtures/mandate/external_capital_unknown",
        "test_external_capital_unknown_disables_promotion",
    ),
    (
        "strategy_materiality_policy_missing",
        "tests/fixtures/mandate/materiality_policy_missing",
        "test_missing_strategy_materiality_policy_caps_at_paper_shadow",
    ),
    (
        "capital_role_inactive",
        "tests/fixtures/mandate/inactive_role",
        "test_inactive_and_research_only_capital_roles_block_capital_promotion",
    ),
    (
        "capital_role_research_only",
        "tests/fixtures/mandate/research_only_role",
        "test_inactive_and_research_only_capital_roles_block_capital_promotion",
    ),
    (
        "benchmark_policy_not_ex_ante",
        "tests/fixtures/mandate/non_ex_ante_benchmark",
        "test_non_ex_ante_benchmark_policy_blocks_capital_promotion",
    ),
    (
        "mandate_promotion_ceiling_exceeded",
        "tests/fixtures/mandate/ceiling_exceeded",
        "test_mandate_policy_ceiling_below_request_blocks_capital_promotion",
    ),
    (
        "allocation_policy_limit_exceeded",
        "tests/fixtures/mandate/allocation_limit_exceeded",
        "test_allocation_policy_limit_exceeded_caps_at_paper_shadow",
    ),
    (
        "lower_bound_net_edge_undefined",
        "tests/fixtures/mandate/invalid_lower_bound_spec",
        "test_invalid_lower_bound_spec_math_blocks_statistical_authority",
    ),
    (
        "net_edge_lower_bound_below_threshold",
        "tests/fixtures/mandate/net_edge_below_threshold",
        "test_taxable_production_with_negative_lower_bound_fails_expected_wealth",
    ),
    (
        "unsupported_side",
        "tests/fixtures/promotion/unsupported_short_side",
        "test_negative_weight_without_short_package_blocks_before_long_only",
    ),
    (
        "short_support_missing",
        "tests/fixtures/promotion/unsupported_short_side",
        "test_negative_weight_without_short_package_blocks_before_long_only",
    ),
    (
        "legacy_statistical_evidence",
        "tests/fixtures/promotion/legacy",
        "test_wave1_golden_fixture_inventory_is_present",
    ),
    (
        "stale_sources",
        "tests/fixtures/promotion/stale",
        "test_wave1_golden_fixture_inventory_is_present",
    ),
):
    _existing = BLOCKER_REGISTRY[_code]
    BLOCKER_REGISTRY[_code] = _record(
        _code,
        _existing.max_state,
        owning_wave="wave_1",
        fixture=_fixture,
        evaluator=f"evaluate_{_code}",
        red_test=_red_test,
        cli_output="promotion-check.blockers",
        web_report_field="dashboard.document_summary.v5_authority_status",
        runtime_enforcement=(
            "order_route_refusal"
            if _code in {"unsupported_side", "short_support_missing"}
            else "activation_refusal"
        ),
    )


def evaluate_authority_artifact_invalid() -> str:
    return "authority_artifact_invalid"


def evaluate_ledger_integrity_violation() -> str:
    return "ledger_integrity_violation"


def evaluate_ledger_key_worm_controls_missing() -> str:
    return "ledger_key_worm_controls_missing"


def evaluate_replay_path_missing() -> str:
    return "replay_path_missing"


def evaluate_tax_account_financing_unspecified() -> str:
    return "tax_account_financing_unspecified"


def evaluate_jurisdiction_account_use_unknown() -> str:
    return "jurisdiction_account_use_unknown"


def evaluate_utility_definition_missing() -> str:
    return "utility_definition_missing"


def evaluate_instrument_package_missing() -> str:
    return "instrument_package_missing"


def evaluate_external_capital_compliance_unknown() -> str:
    return "external_capital_compliance_unknown"


def evaluate_strategy_materiality_policy_missing() -> str:
    return "strategy_materiality_policy_missing"


def evaluate_capital_role_inactive() -> str:
    return "capital_role_inactive"


def evaluate_capital_role_research_only() -> str:
    return "capital_role_research_only"


def evaluate_benchmark_policy_not_ex_ante() -> str:
    return "benchmark_policy_not_ex_ante"


def evaluate_mandate_promotion_ceiling_exceeded() -> str:
    return "mandate_promotion_ceiling_exceeded"


def evaluate_allocation_policy_limit_exceeded() -> str:
    return "allocation_policy_limit_exceeded"


def evaluate_lower_bound_net_edge_undefined() -> str:
    return "lower_bound_net_edge_undefined"


def evaluate_net_edge_lower_bound_below_threshold() -> str:
    return "net_edge_lower_bound_below_threshold"


def evaluate_state_action_contract_missing() -> str:
    return "state_action_contract_missing"


def evaluate_unsupported_side() -> str:
    return "unsupported_side"


def evaluate_short_support_missing() -> str:
    return "short_support_missing"


def evaluate_legacy_statistical_evidence() -> str:
    return "legacy_statistical_evidence"


def evaluate_stale_sources() -> str:
    return "stale_sources"


def _schema(name: str) -> dict[str, object]:
    payload = json.loads((_SCHEMA_ROOT / f"{name}.schema.json").read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"{name} schema must be an object")
    return payload


def validate_blocker_registry_coverage(
    registry: Mapping[str, BlockerRegistryRecord] = BLOCKER_REGISTRY,
    *,
    repo_root: Path = Path("."),
) -> None:
    discovered = _discover_blocker_codes(repo_root)
    missing_codes = sorted(discovered.difference(registry))
    if missing_codes:
        raise ValueError(
            "blocker codes missing from registry: " + ", ".join(missing_codes)
        )
    for code, record in registry.items():
        missing = [
            field
            for field in (
                "owning_wave",
                "max_state",
                "condition",
                "remediation",
                "migration_behavior",
                "schema_field",
                "evaluator",
                "red_test",
                "fixture",
                "cli_output",
                "web_report_field",
                "runtime_enforcement",
            )
            if not getattr(record, field)
        ]
        if missing:
            raise ValueError(f"{code} missing coverage fields: {', '.join(missing)}")
        if code in _EMITTED_BLOCKERS_REQUIRING_REAL_COVERAGE:
            synthetic_fields = [
                field
                for field in (
                    "evaluator",
                    "red_test",
                    "fixture",
                    "cli_output",
                    "web_report_field",
                )
                if getattr(record, field) == NOT_RUNTIME_APPLICABLE
            ]
            if synthetic_fields:
                raise ValueError(
                    f"{code} has synthetic coverage fields: "
                    f"{', '.join(synthetic_fields)}"
                )
            if record.runtime_enforcement == NOT_RUNTIME_APPLICABLE:
                raise ValueError(f"{code} has synthetic runtime enforcement coverage")
        if record.fixture != NOT_RUNTIME_APPLICABLE:
            fixture_path = repo_root / record.fixture
            if not fixture_path.exists():
                raise ValueError(f"{code} registry fixture is missing: {fixture_path}")
        if (
            record.evaluator != NOT_RUNTIME_APPLICABLE
            and record.evaluator not in globals()
        ):
            raise ValueError(
                f"{code} registry evaluator is missing: {record.evaluator}"
            )
        if record.red_test != NOT_RUNTIME_APPLICABLE and not _red_test_exists(
            repo_root,
            record.red_test,
        ):
            raise ValueError(f"{code} registry red test is missing: {record.red_test}")
        if (
            record.cli_output != NOT_RUNTIME_APPLICABLE
            and record.cli_output not in _CLI_OUTPUT_FIELDS
        ):
            raise ValueError(
                f"{code} registry CLI field is missing: {record.cli_output}"
            )
        if (
            record.web_report_field != NOT_RUNTIME_APPLICABLE
            and record.web_report_field not in _WEB_REPORT_FIELDS
        ):
            raise ValueError(
                f"{code} registry web/report field is missing: "
                f"{record.web_report_field}"
            )
        if (
            record.runtime_enforcement != NOT_RUNTIME_APPLICABLE
            and record.runtime_enforcement not in _RUNTIME_ENFORCEMENT_POINTS
        ):
            raise ValueError(
                f"{code} registry runtime enforcement is missing: "
                f"{record.runtime_enforcement}"
            )


def blocker_registry_coverage_rows() -> tuple[dict[str, str], ...]:
    validate_blocker_registry_coverage()
    return tuple(
        {
            "blocker": record.code,
            "owning_wave": record.owning_wave,
            "max_state": record.max_state.value,
            "schema_field": record.schema_field,
            "evaluator": record.evaluator,
            "red_test": record.red_test,
            "fixture": record.fixture,
            "cli_output": record.cli_output,
            "web_report_field": record.web_report_field,
            "runtime_enforcement": record.runtime_enforcement,
        }
        for record in BLOCKER_REGISTRY.values()
    )


def _red_test_exists(repo_root: Path, red_test: str) -> bool:
    test_root = repo_root / "tests"
    if not test_root.exists():
        return False
    return any(
        red_test in path.read_text(encoding="utf-8")
        for path in test_root.rglob("test_*.py")
        if path.is_file() and path.name != "test_blocker_registry.py"
    )


def _discover_blocker_codes(repo_root: Path) -> set[str]:
    discovered: set[str] = set()
    patterns = (
        re.compile(r"""Blocker\(["']([a-z][a-z0-9_]+)["']\)"""),
        re.compile(r"""["']blocker_codes["']\s*:\s*\[([^\]]*)\]"""),
    )
    roots = (
        repo_root / "src",
        repo_root / "tests",
        repo_root / "schemas",
        repo_root / "config",
        repo_root / "docs" / "roadmap",
        repo_root / "docs" / "reports",
    )
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".json", ".md"} or not path.is_file():
                continue
            if path.name == "test_blocker_registry.py":
                continue
            text = path.read_text(encoding="utf-8")
            for match in patterns[0].finditer(text):
                discovered.add(match.group(1))
            for match in patterns[1].finditer(text):
                discovered.update(
                    item
                    for item in re.findall(
                        r"[\"']([a-z][a-z0-9_]+)[\"']",
                        match.group(1),
                    )
                )
    return discovered


def state_allows(max_state: PromotionState, required_state: PromotionState) -> bool:
    return _STATE_ORDER[max_state] >= _STATE_ORDER[required_state]


def strictest_state_cap(blockers: tuple[Blocker, ...]) -> PromotionState:
    if not blockers:
        return PromotionState.PRODUCTION
    return min(
        (blocker.max_state for blocker in blockers),
        key=lambda state: _STATE_ORDER[state],
    )


@dataclass(frozen=True)
class PromotionDecision:
    strategy_id: str
    requested_state: PromotionState
    max_state: PromotionState
    blockers: tuple[Blocker, ...]
    artifact_refs: tuple[str, ...]
    ledger_sequence: int | None
    ledger_hash: str | None
    state_action_contracts: dict[str, dict[str, object]] | None = None
    strategy_allocation_limits: tuple[dict[str, str], ...] = ()

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(blocker.code for blocker in self.blockers)

    @property
    def mandate_blocker_codes(self) -> tuple[str, ...]:
        return tuple(
            code for code in self.blocker_codes if code in _MANDATE_BLOCKER_CODES
        )

    @property
    def statistical_blocker_codes(self) -> tuple[str, ...]:
        return tuple(
            code for code in self.blocker_codes if code in _STATISTICAL_BLOCKER_CODES
        )

    @property
    def authority_blocker_codes(self) -> tuple[str, ...]:
        return tuple(
            code for code in self.blocker_codes if code in _AUTHORITY_BLOCKER_CODES
        )

    @property
    def decision_hash(self) -> str:
        return canonical_payload_hash(self.to_json())

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "strategy_id": self.strategy_id,
            "requested_state": self.requested_state.value,
            "max_state": self.max_state.value,
            "blocker_codes": list(self.blocker_codes),
            "mandate_blocker_codes": list(self.mandate_blocker_codes),
            "statistical_blocker_codes": list(self.statistical_blocker_codes),
            "authority_blocker_codes": list(self.authority_blocker_codes),
            "strategy_allocation_limits": [
                dict(limit) for limit in self.strategy_allocation_limits
            ],
            "artifact_refs": list(self.artifact_refs),
            "ledger_sequence": self.ledger_sequence,
            "ledger_hash": self.ledger_hash,
        }


@dataclass(frozen=True)
class ProjectionDrift:
    detected: bool
    blocker_code: str
    reason: str


def evaluate_promotion_manifest(root: Path) -> PromotionDecision:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return _blocked_decision(
            strategy_id="unknown",
            requested_state=PromotionState.DISABLED,
            blockers=(Blocker("authority_artifact_invalid"),),
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("promotion manifest must be a JSON object")
    strategy_id = str(payload.get("strategy_id", "unknown"))
    requested_state = _state_from_value(str(payload.get("requested_state", "disabled")))
    try:
        validate_quant_artifact(payload, schema=_schema("promotion_manifest"))
        decision = _evaluate_authority_bundle(root=root, manifest=payload)
    except (
        AuthorityLedgerError,
        TrustRootError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
        TypeError,
    ):
        return _blocked_decision(
            strategy_id=strategy_id,
            requested_state=requested_state,
            blockers=(Blocker("authority_artifact_invalid"),),
        )
    return decision


def _evaluate_authority_bundle(
    *,
    root: Path,
    manifest: Mapping[str, object],
) -> PromotionDecision:
    strategy_id = str(manifest["strategy_id"])
    artifact_store = FileContentAddressedStore(
        root / str(manifest.get("artifact_store_root", "cas"))
    )
    replay_store = FileContentAddressedStore(
        root
        / str(
            manifest.get(
                "replay_store_root",
                manifest.get("artifact_store_root", "cas"),
            )
        )
    )
    trust_root_path = root / str(manifest.get("trust_root_path", "trust_root.json"))
    trust_root_payload = json.loads(trust_root_path.read_text(encoding="utf-8"))
    if not isinstance(trust_root_payload, dict):
        raise TrustRootError("trust root must be an object")
    validate_quant_artifact(trust_root_payload, schema=_schema("trust_root"))
    trust_root = TrustRoot.from_json(trust_root_payload)
    fixture_mode = _is_allowed_fixture_root(root)
    if trust_root.fixture_root and not fixture_mode:
        raise TrustRootError(
            "fixture trust roots are only accepted under tests/fixtures"
        )
    ledger = AuthorityLedger(root / str(manifest.get("ledger_root", "ledger")))
    records = ledger.read_records()
    if not records:
        raise AuthorityLedgerError("authority ledger is empty")
    for ledger_record in records:
        validate_quant_artifact(
            _ledger_record_payload_for_schema(ledger_record),
            schema=_schema("promotion_decision_ledger_record"),
        )
    record = _latest_strategy_record(records, strategy_id=strategy_id)
    artifact_payloads = _load_artifact_payloads(record.artifact_refs, artifact_store)
    replay_missing = _has_missing_replay_payload(record.replay_refs, replay_store)
    _verify_approval_refs(
        record.approval_refs,
        artifact_store=artifact_store,
        trust_root=trust_root,
        payload_hash=record.payload_hash,
        fixture_mode=fixture_mode,
    )
    decision_payload = record.payload
    validate_quant_artifact(decision_payload, schema=_schema("promotion_decision"))
    if str(decision_payload.get("kind", "")) != "promotion_decision":
        raise AuthorityLedgerError(
            "latest authority record is not a promotion decision"
        )
    requested_state = _state_from_value(str(decision_payload["requested_state"]))
    state_action_contracts = _state_action_contracts_from_payloads(artifact_payloads)
    blockers = _evaluate_verified_decision_blockers(
        decision_payload=decision_payload,
        artifact_payloads=artifact_payloads,
        artifact_store=artifact_store,
        replay_store=replay_store,
        trust_root=trust_root,
        ledger_sequence=record.sequence,
        state_action_contracts=state_action_contracts,
        replay_missing=replay_missing,
        fixture_mode=fixture_mode,
    )
    max_state = (
        strictest_state_cap(blockers)
        if blockers
        else _state_from_value(
            str(decision_payload.get("max_state", requested_state.value))
        )
    )
    if not state_allows(max_state, requested_state):
        max_state = strictest_state_cap(blockers) if blockers else max_state
    strategy_allocation_limits = _verified_strategy_allocation_limits(
        artifact_payloads,
        artifact_store=artifact_store,
        replay_store=replay_store,
        trust_root=trust_root,
        ledger_sequence=record.sequence,
        strategy_id=strategy_id,
        fixture_mode=fixture_mode,
    )
    return PromotionDecision(
        strategy_id=strategy_id,
        requested_state=requested_state,
        max_state=max_state,
        blockers=blockers,
        artifact_refs=record.artifact_refs,
        ledger_sequence=record.sequence,
        ledger_hash=record.ledger_hash,
        state_action_contracts=state_action_contracts,
        strategy_allocation_limits=strategy_allocation_limits,
    )


def _ledger_record_payload_for_schema(
    record: AuthorityLedgerRecord,
) -> dict[str, object]:
    return {
        "sequence": record.sequence,
        "previous_hash": record.previous_hash,
        "payload": dict(record.payload),
        "payload_hash": record.payload_hash,
        "artifact_refs": list(record.artifact_refs),
        "replay_refs": list(record.replay_refs),
        "writer_identity": record.writer_identity,
        "approval_refs": list(record.approval_refs),
        "ledger_hash": record.ledger_hash,
    }


def _is_allowed_fixture_root(root: Path) -> bool:
    try:
        root.resolve().relative_to(Path.cwd().resolve() / "tests" / "fixtures")
    except ValueError:
        return False
    return True


def _latest_strategy_record(
    records: tuple[AuthorityLedgerRecord, ...],
    *,
    strategy_id: str,
) -> AuthorityLedgerRecord:
    matching = [
        record
        for record in records
        if str(record.payload.get("strategy_id", "")) == strategy_id
    ]
    if not matching:
        raise AuthorityLedgerError(f"no promotion record for {strategy_id}")
    return matching[-1]


def _load_artifact_payloads(
    artifact_refs: tuple[str, ...],
    artifact_store: FileContentAddressedStore,
) -> tuple[dict[str, object], ...]:
    payloads: list[dict[str, object]] = []
    for ref in artifact_refs:
        payload = artifact_store.read_ref_uri(ref)
        _validate_cas_payload(payload)
        payloads.append(payload)
    return tuple(payloads)


def _validate_cas_payload(payload: Mapping[str, object]) -> None:
    kind = str(payload.get("kind", ""))
    if kind == "ledger_key_management_policy":
        validate_quant_artifact(payload, schema=_schema("ledger_key_management_policy"))
    elif kind == "state_action_contract":
        validate_quant_artifact(payload, schema=_schema("state_action_contract"))
    elif kind == "approval":
        validate_quant_artifact(payload, schema=_schema("approval_record"))
    elif kind in {"strategy_capability_manifest", "promotion_evidence"}:
        validate_quant_artifact(payload, schema=_schema(kind))
    elif kind in {
        "experiment_registration",
        "experiment_run_record",
        "experiment_amendment_record",
        "trial_universe_manifest",
        "dataset_manifest",
        "data_restatement_report",
        "evidence_dependency_index",
        "evidence_invalidation_report",
        "threshold_justification",
        "power_analysis_report",
        "bootstrap_report",
        "paired_benchmark_uncertainty_report",
        "statistical_validation_report",
        "quote_quality_record",
        "execution_cost_observation",
        "cost_model_report",
        "capacity_curve_report",
    }:
        validate_quant_artifact(payload, schema=_schema(kind))
    elif kind in _MANDATE_ARTIFACT_SCHEMA_NAMES and _has_authority_metadata(payload):
        schema_name = _MANDATE_ARTIFACT_SCHEMA_NAMES[kind]
        validate_quant_artifact(payload, schema=_schema(schema_name))
    else:
        validate_quant_artifact(payload, schema=_schema("content_addressed_artifact"))


def _has_missing_replay_payload(
    replay_refs: tuple[str, ...],
    replay_store: FileContentAddressedStore,
) -> bool:
    for ref in replay_refs:
        try:
            replay_store.read_ref_uri(ref)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return True
    return False


def _verify_approval_refs(
    approval_refs: tuple[str, ...],
    *,
    artifact_store: FileContentAddressedStore,
    trust_root: TrustRoot,
    payload_hash: str,
    fixture_mode: bool,
) -> None:
    if not approval_refs:
        raise AuthorityLedgerError("approval refs are required")
    for approval_ref in approval_refs:
        approval_payload = artifact_store.read_ref_uri(approval_ref)
        validate_quant_artifact(approval_payload, schema=_schema("approval_record"))
        if str(approval_payload.get("payload_hash", "")) != payload_hash:
            raise AuthorityLedgerError("approval payload hash mismatch")
        if not fixture_mode:
            for field in (
                "operator_identity_ref",
                "role_registry_ref",
                "authority_boundary_ref",
            ):
                if _contains_fixture_marker(str(approval_payload.get(field, ""))):
                    raise AuthorityLedgerError(
                        f"{field} uses a fixture/test-only authority marker"
                    )
        if str(approval_payload.get("scope", "")) != "promotion_decision":
            raise AuthorityLedgerError(
                "approval scope does not cover promotion_decision"
            )
        _verify_approval_payload(
            approval_payload,
            trust_root=trust_root,
            payload_hash=payload_hash,
            required_scope="promotion_decision",
        )


def _verify_approval_payload(
    approval_payload: Mapping[str, object],
    *,
    trust_root: TrustRoot,
    payload_hash: str,
    required_scope: str,
) -> None:
    if str(approval_payload.get("payload_hash", "")) != payload_hash:
        raise AuthorityLedgerError("approval payload hash mismatch")
    if str(approval_payload.get("scope", "")) != required_scope:
        raise AuthorityLedgerError(f"approval scope does not cover {required_scope}")
    if not bool(approval_payload.get("risk_accepted", False)):
        raise AuthorityLedgerError("approval risk acceptance is missing")
    signed_at = datetime.fromisoformat(
        str(approval_payload["signed_at_utc"]).replace("Z", "+00:00")
    ).astimezone(UTC)
    expires_at = datetime.fromisoformat(
        str(approval_payload["expires_at_utc"]).replace("Z", "+00:00")
    ).astimezone(UTC)
    verified_at = datetime.now(UTC)
    if signed_at > expires_at:
        raise AuthorityLedgerError("approval signed_at_utc is after expiry")
    if signed_at > verified_at:
        raise AuthorityLedgerError("approval signed_at_utc is in the future")
    if not (
        trust_root.not_before_utc.astimezone(UTC)
        <= signed_at
        <= trust_root.not_after_utc.astimezone(UTC)
    ):
        raise AuthorityLedgerError(
            "approval signed_at_utc is outside trust-root validity bounds"
        )
    if expires_at < verified_at:
        raise AuthorityLedgerError("approval record is expired")
    verify_approval_signature(
        payload_hash=payload_hash,
        signature_ref=str(approval_payload.get("signature_ref", "")),
        trust_root=trust_root,
        required_scope=required_scope,
        verified_at_utc=verified_at,
    )


def _evaluate_verified_decision_blockers(
    *,
    decision_payload: Mapping[str, object],
    artifact_payloads: tuple[Mapping[str, object], ...],
    artifact_store: FileContentAddressedStore,
    replay_store: FileContentAddressedStore,
    trust_root: TrustRoot,
    ledger_sequence: int,
    state_action_contracts: dict[str, dict[str, object]] | None,
    replay_missing: bool,
    fixture_mode: bool,
) -> tuple[Blocker, ...]:
    blockers: list[Blocker] = []
    strategy_id = str(decision_payload.get("strategy_id", ""))
    for required_kind in _AUTHORITY_EVIDENCE_ARTIFACT_KINDS:
        if not _has_valid_evidence_artifact(
            artifact_payloads,
            kind=required_kind,
            strategy_id=strategy_id,
        ):
            _append_blocker(blockers, "authority_artifact_invalid")
    for required_kind, blocker_code in _FIRST_SLICE_REQUIRED_ARTIFACT_BLOCKERS.items():
        if not _has_first_slice_required_artifact(
            artifact_payloads,
            kind=required_kind,
            strategy_id=strategy_id,
        ):
            _append_blocker(blockers, blocker_code)
    _append_mandate_blockers(
        blockers,
        artifact_payloads=artifact_payloads,
        artifact_store=artifact_store,
        replay_store=replay_store,
        trust_root=trust_root,
        ledger_sequence=ledger_sequence,
        decision_payload=decision_payload,
        fixture_mode=fixture_mode,
    )
    if not _has_kind_with_flag(
        artifact_payloads,
        kind="ledger_key_management_policy",
        flag="worm_controls",
    ):
        _append_blocker(blockers, "ledger_key_worm_controls_missing")
    if state_action_contracts is None:
        _append_blocker(blockers, "state_action_contract_missing")

    if replay_missing:
        _append_blocker(blockers, "replay_path_missing")
    for blocker in evaluate_provenance_blockers(artifact_payloads=artifact_payloads):
        _append_blocker(blockers, blocker.code)
    for blocker in evaluate_statistical_evidence_blockers(
        artifact_payloads=artifact_payloads
    ):
        _append_blocker(blockers, blocker.code)
    for blocker in evaluate_cost_capacity_blockers(
        artifact_payloads=artifact_payloads,
        decision_payload=decision_payload,
    ):
        _append_blocker(blockers, blocker.code)

    target_weights_raw = decision_payload.get("target_weights", {})
    if not isinstance(target_weights_raw, Mapping):
        raise AuthorityLedgerError("target_weights must be an object")
    target_weights = dict(target_weights_raw)
    has_negative_weight = any(
        Decimal(str(weight)) < Decimal("0") for weight in target_weights.values()
    )
    if has_negative_weight and not _has_kind_with_flag(
        artifact_payloads,
        kind="short_capability_package",
        flag="short_enabled",
    ):
        _append_blocker(blockers, "unsupported_side")
        _append_blocker(blockers, "short_support_missing")

    blocker_codes_raw = decision_payload.get("blocker_codes", ())
    if not isinstance(blocker_codes_raw, Sequence) or isinstance(
        blocker_codes_raw,
        str | bytes,
    ):
        raise AuthorityLedgerError("blocker_codes must be an array")
    for code in blocker_codes_raw:
        _append_blocker(blockers, str(code))
    return tuple(blockers)


def _append_blocker(blockers: list[Blocker], code: str) -> None:
    if code not in BLOCKER_REGISTRY:
        raise AuthorityLedgerError(f"unknown blocker code {code}")
    if code not in {blocker.code for blocker in blockers}:
        blockers.append(Blocker(code))


def evaluate_provenance_blockers(
    *,
    artifact_payloads: Sequence[Mapping[str, object]],
) -> tuple[Blocker, ...]:
    blockers: list[Blocker] = []
    for payload in artifact_payloads:
        kind = str(payload.get("kind", ""))
        if kind == "trial_universe_manifest":
            for code in _string_sequence(payload.get("blocker_codes", ())):
                if code in BLOCKER_REGISTRY:
                    _append_blocker(blockers, code)
            status = _normal_form(payload.get("status"))
            if status == "contaminated":
                _append_blocker(blockers, "trial_lineage_contaminated")
            elif status == "incomplete":
                _append_blocker(blockers, "trial_universe_incomplete")
        elif kind == "dataset_manifest":
            for code in dataset_manifest_blocker_codes(payload):
                _append_blocker(blockers, code)
        elif kind == "data_restatement_report":
            evidence_status = _normal_form(payload.get("evidence_status"))
            if evidence_status in {"stale", "manual_review_required"}:
                _append_blocker(blockers, "stale_sources")
            elif evidence_status == "invalid":
                _append_blocker(blockers, "replay_path_missing")
        elif kind == "evidence_invalidation_report":
            _append_blocker(blockers, "replay_path_missing")
    return tuple(blockers)


def evaluate_statistical_evidence_blockers(
    *,
    artifact_payloads: Sequence[Mapping[str, object]],
) -> tuple[Blocker, ...]:
    blockers: list[Blocker] = []
    for payload in artifact_payloads:
        kind = str(payload.get("kind", ""))
        if kind in {
            "threshold_justification",
            "power_analysis_report",
            "bootstrap_report",
            "paired_benchmark_uncertainty_report",
            "statistical_validation_report",
        }:
            for code in _string_sequence(payload.get("blocker_codes", ())):
                if code in BLOCKER_REGISTRY:
                    _append_blocker(blockers, code)
        if kind == "statistical_validation_report":
            if _normal_form(payload.get("evidence_class")) == "legacy":
                _append_blocker(blockers, "legacy_statistical_evidence")
            if not bool(payload.get("promotion_valid", False)):
                for code in _string_sequence(payload.get("blocker_codes", ())):
                    if code in BLOCKER_REGISTRY:
                        _append_blocker(blockers, code)
    return tuple(blockers)


def evaluate_cost_capacity_blockers(
    *,
    artifact_payloads: Sequence[Mapping[str, object]],
    decision_payload: Mapping[str, object] | None = None,
) -> tuple[Blocker, ...]:
    blockers: list[Blocker] = []
    has_cost_model_report = False
    has_capacity_curve_report = False
    has_execution_observation = False
    requested_state = ""
    if decision_payload is not None:
        requested_state = str(decision_payload.get("requested_state", ""))
    for payload in artifact_payloads:
        kind = str(payload.get("kind", ""))
        if kind in {
            "cost_model_report",
            "capacity_curve_report",
            "execution_cost_observation",
            "quote_quality_record",
        }:
            for code in _string_sequence(payload.get("blocker_codes", ())):
                if code in BLOCKER_REGISTRY:
                    _append_blocker(blockers, code)
        if kind == "cost_model_report":
            has_cost_model_report = True
            # Re-derive critical blockers from raw fields so that a payload
            # asserting promotion_valid=true with mismatched fields cannot
            # bypass enforcement.
            unsupported_buckets = _string_sequence(
                payload.get("unsupported_buckets", ())
            )
            fallback = _normal_form(payload.get("sparse_bucket_fallback_policy"))
            if unsupported_buckets and fallback == "no_fallback":
                _append_blocker(blockers, "unsupported_cost_bucket")
            powered_coverage = payload.get("powered_bucket_coverage", {})
            if isinstance(powered_coverage, Mapping):
                if any(not bool(value) for value in powered_coverage.values()):
                    _append_blocker(blockers, "execution_sample_power_missing")
            paper_count = _coerce_int(payload.get("paper_observation_count", 0))
            probe_count = _coerce_int(payload.get("live_probe_observation_count", 0))
            live_count = _coerce_int(payload.get("live_observation_count", 0))
            min_live = _coerce_int(payload.get("minimum_live_sample_requirement", 0))
            total_count = paper_count + probe_count + live_count
            if total_count <= 0:
                _append_blocker(blockers, "execution_sample_power_missing")
            if (probe_count + live_count) < min_live and min_live > 0:
                _append_blocker(blockers, "live_sample_requirement_unmet")
            if probe_count == 0 and live_count == 0 and paper_count > 0:
                # Paper-only — cannot support market-impact claim regardless of
                # the report's self-asserted impact_claim_status.
                _append_blocker(blockers, "execution_sample_power_missing")
            if _normal_form(payload.get("evidence_class")) == "legacy":
                _append_blocker(blockers, "legacy_statistical_evidence")
        if kind == "capacity_curve_report":
            has_capacity_curve_report = True
            if bool(payload.get("capacity_extrapolation_risk", False)):
                _append_blocker(blockers, "capacity_extrapolation_risk")
            for required_field in (
                "lower_bound_capacity_curve",
                "lower_bound_net_edge_by_scale",
            ):
                value = payload.get(required_field, None)
                if not isinstance(value, Mapping) or not value:
                    _append_blocker(blockers, "capacity_lower_bound_missing")
            limit_str = str(payload.get("lower_bound_capacity_limit", ""))
            try:
                if not limit_str.strip() or Decimal(limit_str) <= Decimal("0"):
                    _append_blocker(blockers, "capacity_lower_bound_missing")
            except InvalidOperation:
                _append_blocker(blockers, "capacity_lower_bound_missing")
        if kind == "execution_cost_observation":
            has_execution_observation = True
        if kind == "quote_quality_record":
            policy = _normal_form(payload.get("handling_policy"))
            quality = _normal_form(payload.get("quality_status"))
            bad_states = {"bad", "outage", "stale"}
            if quality in bad_states and policy != "no_trade_on_bad_quote":
                _append_blocker(blockers, "execution_semantics_incomplete")
        if kind == "replay_slippage_summary" and not payload.get("quote_quality_state"):
            _append_blocker(blockers, "legacy_statistical_evidence")
    # When an authoritative bundle for paper_trading or above already supplies
    # execution evidence, the bundle must include cost-model and capacity
    # reports too. Bundles without any execution evidence are evaluated only
    # for the artifacts they do provide so that tests focused on other
    # blockers (e.g. mandate authority) remain isolated.
    capable_state = requested_state in {
        PromotionState.PAPER_TRADING.value,
        PromotionState.TINY_LIVE_PROBE.value,
        PromotionState.PRODUCTION.value,
    }
    if capable_state and has_execution_observation:
        if not has_cost_model_report:
            _append_blocker(blockers, "execution_semantics_incomplete")
        if not has_capacity_curve_report:
            _append_blocker(blockers, "capacity_lower_bound_missing")
    return tuple(blockers)


@dataclass(frozen=True)
class _MandateAuthorityStatus:
    valid_payloads: Mapping[str, Mapping[str, object]]
    authority_invalid: bool = False
    replay_missing: bool = False

    @property
    def valid_kinds(self) -> frozenset[str]:
        return frozenset(self.valid_payloads)


def _mandate_authority_status(
    payloads: tuple[Mapping[str, object], ...],
    *,
    artifact_store: FileContentAddressedStore,
    replay_store: FileContentAddressedStore,
    trust_root: TrustRoot,
    ledger_sequence: int,
    strategy_id: str,
    fixture_mode: bool,
) -> _MandateAuthorityStatus:
    valid_payloads: dict[str, Mapping[str, object]] = {}
    authority_invalid = False
    replay_missing = False
    for payload in payloads:
        kind = str(payload.get("kind", ""))
        if kind not in _MANDATE_ARTIFACT_SCHEMA_NAMES:
            continue
        if str(payload.get("strategy_id", "")) != strategy_id:
            continue
        if not _has_authority_metadata(payload):
            continue
        status = _verify_mandate_artifact_authority(
            payload,
            artifact_store=artifact_store,
            replay_store=replay_store,
            trust_root=trust_root,
            ledger_sequence=ledger_sequence,
            fixture_mode=fixture_mode,
        )
        if status.authority_invalid:
            authority_invalid = True
            continue
        if status.replay_missing:
            replay_missing = True
            continue
        if kind in valid_payloads:
            authority_invalid = True
            continue
        valid_payloads[kind] = payload
    return _MandateAuthorityStatus(
        valid_payloads=valid_payloads,
        authority_invalid=authority_invalid,
        replay_missing=replay_missing,
    )


def _verify_mandate_artifact_authority(
    payload: Mapping[str, object],
    *,
    artifact_store: FileContentAddressedStore,
    replay_store: FileContentAddressedStore,
    trust_root: TrustRoot,
    ledger_sequence: int,
    fixture_mode: bool,
) -> _MandateAuthorityStatus:
    try:
        if _has_missing_mandate_replay(payload, replay_store=replay_store):
            return _MandateAuthorityStatus(
                valid_payloads={},
                replay_missing=True,
            )
        expected_hash = _mandate_payload_hash(payload)
        if str(payload.get("payload_hash", "")) != expected_hash:
            return _MandateAuthorityStatus(
                valid_payloads={},
                authority_invalid=True,
            )
        if int(str(payload.get("ledger_sequence", ""))) != ledger_sequence:
            return _MandateAuthorityStatus(
                valid_payloads={},
                authority_invalid=True,
            )
        authority_ref = str(payload.get("authority_ref", ""))
        if authority_ref not in {trust_root.root_id, f"authority:{trust_root.root_id}"}:
            return _MandateAuthorityStatus(
                valid_payloads={},
                authority_invalid=True,
            )
        approval_refs = _string_sequence(payload.get("approval_record_refs", ()))
        if not approval_refs:
            return _MandateAuthorityStatus(
                valid_payloads={},
                authority_invalid=True,
            )
        for approval_ref in approval_refs:
            approval_payload = artifact_store.read_ref_uri(approval_ref)
            validate_quant_artifact(approval_payload, schema=_schema("approval_record"))
            if not fixture_mode:
                for field in (
                    "operator_identity_ref",
                    "role_registry_ref",
                    "authority_boundary_ref",
                ):
                    if _contains_fixture_marker(str(approval_payload.get(field, ""))):
                        return _MandateAuthorityStatus(
                            valid_payloads={},
                            authority_invalid=True,
                        )
            for field in (
                "operator_identity_ref",
                "role_registry_ref",
                "authority_boundary_ref",
            ):
                if not str(approval_payload.get(field, "")).strip():
                    return _MandateAuthorityStatus(
                        valid_payloads={},
                        authority_invalid=True,
                    )
            _verify_approval_payload(
                approval_payload,
                trust_root=trust_root,
                payload_hash=expected_hash,
                required_scope="mandate_artifact",
            )
        replay_refs = _string_sequence(payload.get("replay_input_refs", ()))
        if not replay_refs:
            return _MandateAuthorityStatus(
                valid_payloads={},
                replay_missing=True,
            )
        for replay_ref in replay_refs:
            replay_store.read_ref_uri(replay_ref)
    except (
        AuthorityLedgerError,
        TrustRootError,
        FileNotFoundError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        if _has_missing_mandate_replay(payload, replay_store=replay_store):
            return _MandateAuthorityStatus(
                valid_payloads={},
                replay_missing=True,
            )
        return _MandateAuthorityStatus(
            valid_payloads={},
            authority_invalid=True,
        )
    return _MandateAuthorityStatus(valid_payloads={str(payload["kind"]): payload})


def _has_missing_mandate_replay(
    payload: Mapping[str, object],
    *,
    replay_store: FileContentAddressedStore,
) -> bool:
    try:
        replay_refs = _string_sequence(payload.get("replay_input_refs", ()))
        return not replay_refs or any(
            not replay_store.verify(ContentAddressedRef.from_uri(ref))
            for ref in replay_refs
        )
    except (TypeError, ValueError):
        return False


def _mandate_payload_hash(payload: Mapping[str, object]) -> str:
    hash_payload = {
        str(key): value
        for key, value in payload.items()
        if str(key) not in {"payload_hash", "approval_record_refs"}
    }
    return canonical_payload_hash(hash_payload)


def _append_mandate_blockers(
    blockers: list[Blocker],
    *,
    artifact_payloads: tuple[Mapping[str, object], ...],
    artifact_store: FileContentAddressedStore,
    replay_store: FileContentAddressedStore,
    trust_root: TrustRoot,
    ledger_sequence: int,
    decision_payload: Mapping[str, object],
    fixture_mode: bool,
) -> None:
    strategy_id = str(decision_payload.get("strategy_id", ""))
    requested_state = _state_from_value(str(decision_payload["requested_state"]))
    mandate_status = _mandate_authority_status(
        artifact_payloads,
        artifact_store=artifact_store,
        replay_store=replay_store,
        trust_root=trust_root,
        ledger_sequence=ledger_sequence,
        strategy_id=strategy_id,
        fixture_mode=fixture_mode,
    )
    if mandate_status.authority_invalid:
        _append_blocker(blockers, "authority_artifact_invalid")
    if mandate_status.replay_missing:
        _append_blocker(blockers, "replay_path_missing")
    if _fixture_placeholder_mandate_complete(
        artifact_payloads,
        strategy_id=strategy_id,
        requested_state=requested_state,
        fixture_mode=fixture_mode,
    ):
        return

    for required_kind, blocker_code in _MANDATE_REQUIRED_ARTIFACT_BLOCKERS.items():
        if required_kind not in mandate_status.valid_kinds:
            _append_blocker(blockers, blocker_code)

    if _tax_account_financing_unspecified(
        mandate_status.valid_payloads,
        strategy_id=strategy_id,
    ):
        _append_blocker(blockers, "tax_account_financing_unspecified")
    if _jurisdiction_or_account_use_unknown(
        mandate_status.valid_payloads,
        strategy_id=strategy_id,
    ):
        _append_blocker(blockers, "jurisdiction_account_use_unknown")
    if _external_capital_compliance_unknown(
        mandate_status.valid_payloads,
        strategy_id=strategy_id,
    ):
        _append_blocker(blockers, "external_capital_compliance_unknown")
    if _simple_equity_instrument_package_missing(
        mandate_status.valid_payloads,
        strategy_id=strategy_id,
    ):
        _append_blocker(blockers, "instrument_package_missing")
    _append_mandate_semantic_blockers(
        blockers,
        mandate_payloads=mandate_status.valid_payloads,
        artifact_payloads=artifact_payloads,
        decision_payload=decision_payload,
        requested_state=requested_state,
    )


def _fixture_placeholder_mandate_complete(
    payloads: tuple[Mapping[str, object], ...],
    *,
    strategy_id: str,
    requested_state: PromotionState,
    fixture_mode: bool,
) -> bool:
    if not fixture_mode or not state_allows(
        PromotionState.PAPER_SHADOW,
        requested_state,
    ):
        return False
    required_kinds = set(_FIRST_SLICE_REQUIRED_ARTIFACT_BLOCKERS)
    return all(
        _has_valid_evidence_artifact(payloads, kind=kind, strategy_id=strategy_id)
        for kind in required_kinds
    )


def _has_first_slice_required_artifact(
    payloads: tuple[Mapping[str, object], ...],
    *,
    kind: str,
    strategy_id: str,
) -> bool:
    if _has_valid_evidence_artifact(payloads, kind=kind, strategy_id=strategy_id):
        return True
    return any(
        _has_valid_mandate_artifact(payloads, kind=equivalent, strategy_id=strategy_id)
        for equivalent in _FIRST_SLICE_EQUIVALENT_KINDS.get(kind, ())
    )


def _has_valid_mandate_artifact(
    payloads: tuple[Mapping[str, object], ...],
    *,
    kind: str,
    strategy_id: str,
) -> bool:
    payload = _first_strategy_artifact(payloads, kind=kind, strategy_id=strategy_id)
    return payload is not None and _has_authority_metadata(payload)


def _has_authority_metadata(payload: Mapping[str, object]) -> bool:
    return all(
        field in payload
        for field in (
            "artifact_uri",
            "payload_hash",
            "ledger_sequence",
            "approval_record_refs",
            "authority_ref",
            "created_at_utc",
            "replay_input_refs",
        )
    )


def _first_strategy_artifact(
    payloads: tuple[Mapping[str, object], ...],
    *,
    kind: str,
    strategy_id: str,
) -> Mapping[str, object] | None:
    for payload in payloads:
        if str(payload.get("kind", "")) != kind:
            continue
        if str(payload.get("strategy_id", "")) != strategy_id:
            continue
        return payload
    return None


def _tax_account_financing_unspecified(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    strategy_id: str,
) -> bool:
    del strategy_id
    mandate = payloads.get("investment_mandate")
    if mandate is None:
        return False
    taxable_status = _normal_form(mandate.get("taxable_or_tax_exempt_status"))
    pre_tax_or_after_tax = _normal_form(mandate.get("pre_tax_or_after_tax"))
    tax_account_type = _normal_form(mandate.get("tax_account_type"))
    tax_assumptions = _normal_form(mandate.get("tax_assumptions"))
    if (
        _is_unknown(taxable_status)
        or _is_unknown(pre_tax_or_after_tax)
        or _is_unknown(tax_account_type)
        or _is_unknown(tax_assumptions)
    ):
        return True
    if taxable_status == "taxable" and not bool(mandate.get("tax_modeled", False)):
        return True
    if taxable_status == "taxable" and pre_tax_or_after_tax != "after_tax":
        return True
    return False


def _jurisdiction_or_account_use_unknown(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    strategy_id: str,
) -> bool:
    del strategy_id
    manifest = payloads.get("jurisdiction_account_use_manifest")
    if manifest is not None:
        return any(
            _is_unknown(manifest.get(field))
            for field in (
                "jurisdiction",
                "account_use",
                "broker_permission_status",
                "margin_permission_status",
                "instrument_eligibility_status",
            )
        )
    return False


def _external_capital_compliance_unknown(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    strategy_id: str,
) -> bool:
    del strategy_id
    manifest = payloads.get("jurisdiction_account_use_manifest")
    if manifest is not None:
        if not _is_external_account_use(manifest):
            return False
        return any(
            _is_unknown(manifest.get(field))
            for field in (
                "fiduciary_duty_status",
                "client_suitability_status",
                "marketing_status",
                "custody_status",
                "record_retention_status",
                "account_restriction_status",
            )
        )
    return False


def _simple_equity_instrument_package_missing(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    strategy_id: str,
) -> bool:
    required = _required_instrument_classes(payloads, strategy_id=strategy_id)
    if "simple_equity" not in required:
        return False
    supported = {
        _instrument_class(
            payload.get("instrument_class", payload.get("instrument_type"))
        )
        for kind, payload in payloads.items()
        if kind == "instrument_support_package"
    }
    return "simple_equity" not in supported


def _append_mandate_semantic_blockers(
    blockers: list[Blocker],
    *,
    mandate_payloads: Mapping[str, Mapping[str, object]],
    artifact_payloads: tuple[Mapping[str, object], ...],
    decision_payload: Mapping[str, object],
    requested_state: PromotionState,
) -> None:
    strategy_id = str(decision_payload.get("strategy_id", ""))
    capital_role = mandate_payloads.get("strategy_capital_role")
    if capital_role is not None:
        role = _normal_form(capital_role.get("capital_role"))
        if role == "inactive":
            _append_blocker(blockers, "capital_role_inactive")
        elif role == "research_only" and not state_allows(
            PromotionState.RESEARCH_ONLY,
            requested_state,
        ):
            _append_blocker(blockers, "capital_role_research_only")

    benchmark = mandate_payloads.get("benchmark_policy")
    if benchmark is not None and not bool(benchmark.get("ex_ante", False)):
        _append_blocker(blockers, "benchmark_policy_not_ex_ante")

    if _policy_ceiling_exceeded(
        mandate_payloads,
        strategy_id=strategy_id,
        requested_state=requested_state,
    ):
        _append_blocker(blockers, "mandate_promotion_ceiling_exceeded")

    if _allocation_policy_limit_exceeded(
        mandate_payloads,
        strategy_id=strategy_id,
        decision_payload=decision_payload,
        requested_state=requested_state,
    ):
        _append_blocker(blockers, "allocation_policy_limit_exceeded")

    if _lower_bound_spec_invalid(mandate_payloads, strategy_id=strategy_id):
        _append_blocker(blockers, "lower_bound_net_edge_undefined")

    expected_wealth_code = _expected_wealth_blocker(
        mandate_payloads,
        artifact_payloads=artifact_payloads,
        strategy_id=strategy_id,
        requested_state=requested_state,
    )
    if expected_wealth_code:
        _append_blocker(blockers, expected_wealth_code)


def _policy_ceiling_exceeded(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    strategy_id: str,
    requested_state: PromotionState,
) -> bool:
    del strategy_id
    ceilings: list[PromotionState] = []
    jurisdiction = payloads.get("jurisdiction_account_use_manifest")
    if jurisdiction is not None:
        ceiling = _optional_state(jurisdiction.get("live_trading_ceiling"))
        if ceiling is not None:
            ceilings.append(ceiling)
    for kind, payload in payloads.items():
        if kind != "instrument_support_package":
            continue
        ceiling = _optional_state(payload.get("promotion_ceiling"))
        if ceiling is not None:
            ceilings.append(ceiling)
    return any(not state_allows(ceiling, requested_state) for ceiling in ceilings)


def _allocation_policy_limit_exceeded(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    strategy_id: str,
    decision_payload: Mapping[str, object],
    requested_state: PromotionState,
) -> bool:
    del strategy_id
    if state_allows(PromotionState.PAPER_SHADOW, requested_state):
        return False
    policy = payloads.get("capital_allocation_policy")
    if policy is None:
        return False
    target_weights_raw = decision_payload.get("target_weights", {})
    if not isinstance(target_weights_raw, Mapping):
        raise AuthorityLedgerError("target_weights must be an object")
    absolute_weights = [
        abs(_decimal_value(weight)) for weight in target_weights_raw.values()
    ]
    if not absolute_weights:
        return False
    gross_weight = sum(absolute_weights, start=Decimal("0"))
    max_strategy = _decimal_value(policy.get("max_strategy_allocation"))
    max_sleeve = _decimal_value(policy.get("max_sleeve_allocation"))
    initial_allocation = _decimal_value(policy.get("initial_allocation"))
    if gross_weight > max_strategy or gross_weight > max_sleeve:
        return True
    if requested_state in {PromotionState.TINY_LIVE_PROBE, PromotionState.PRODUCTION}:
        return gross_weight > initial_allocation
    return False


def _lower_bound_spec_invalid(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    strategy_id: str,
) -> bool:
    del strategy_id
    spec = payloads.get("lower_bound_net_edge_spec")
    if spec is None:
        return False
    try:
        confidence = _decimal_value(spec.get("confidence_level"))
        sample_size = int(str(spec.get("minimum_effective_sample_size", "")))
    except (InvalidOperation, ValueError):
        return True
    if confidence <= Decimal("0") or confidence >= Decimal("1"):
        return True
    if sample_size <= 0:
        return True
    if _is_unknown(spec.get("benchmark_pairing")):
        return True
    if (
        _is_unknown(spec.get("serial_dependence_correction"))
        or _normal_form(spec.get("serial_dependence_correction")) == "none"
    ):
        return True
    if (
        _is_unknown(spec.get("fat_tail_treatment"))
        or _normal_form(spec.get("fat_tail_treatment")) == "none"
    ):
        return True
    try:
        stress_inputs = {
            _normal_form(item)
            for item in _string_sequence(spec.get("stress_inputs", ()))
        }
    except ValueError:
        return True
    if not _LOWER_BOUND_REQUIRED_STRESS_INPUTS <= stress_inputs:
        return True
    estimator = _normal_form(spec.get("estimator_family"))
    prior_policy = _normal_form(spec.get("prior_policy"))
    if "bayes" in estimator and (
        _is_unknown(prior_policy) or "sensitivity" not in prior_policy
    ):
        return True
    return False


def _expected_wealth_blocker(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    artifact_payloads: tuple[Mapping[str, object], ...],
    strategy_id: str,
    requested_state: PromotionState,
) -> str | None:
    if not state_allows(requested_state, PromotionState.TINY_LIVE_PROBE):
        return None
    if _mandate_hard_caps_below_live(payloads, strategy_id=strategy_id):
        return None
    mandate = payloads.get("investment_mandate")
    if mandate is None:
        return None
    if _tax_account_financing_unspecified(payloads, strategy_id=strategy_id):
        return None
    taxable_status = _normal_form(mandate.get("taxable_or_tax_exempt_status"))
    report = _first_strategy_artifact(
        artifact_payloads,
        kind="lower_bound_net_edge_report",
        strategy_id=strategy_id,
    )
    if report is None:
        return (
            "after_tax_edge_missing_for_taxable_account"
            if taxable_status == "taxable"
            else "lower_bound_net_edge_undefined"
        )
    if (
        taxable_status == "taxable"
        and _normal_form(report.get("pre_tax_or_after_tax")) != "after_tax"
    ):
        return "after_tax_edge_missing_for_taxable_account"
    spec = payloads.get("lower_bound_net_edge_spec")
    if _lower_bound_report_undefined(
        report=report,
        spec=spec,
        mandate=mandate,
    ):
        return "lower_bound_net_edge_undefined"
    try:
        lower_bound = _decimal_value(report.get("lower_bound_net_edge"))
        threshold = _decimal_value(report.get("pass_threshold"))
    except (InvalidOperation, ValueError):
        return "lower_bound_net_edge_undefined"
    if lower_bound < threshold:
        return "net_edge_lower_bound_below_threshold"
    return None


def _lower_bound_report_undefined(
    *,
    report: Mapping[str, object],
    spec: Mapping[str, object] | None,
    mandate: Mapping[str, object],
) -> bool:
    if spec is None:
        return True
    for field in (
        "lower_bound_spec_ref",
        "lower_bound_spec_hash",
        "estimator_family",
        "confidence_level",
        "return_horizon",
        "benchmark_pairing",
        "serial_dependence_correction",
        "fat_tail_treatment",
        "minimum_effective_sample_size",
        "pre_tax_or_after_tax",
        "taxable_or_tax_exempt_status",
        "stress_inputs",
        "lower_bound_net_edge",
        "pass_threshold",
    ):
        if field not in report or _is_unknown(report.get(field)):
            return True
    if str(report.get("lower_bound_spec_ref", "")) != str(spec.get("artifact_uri", "")):
        return True
    if str(report.get("lower_bound_spec_hash", "")) != str(
        spec.get("payload_hash", "")
    ):
        return True
    for field in (
        "estimator_family",
        "return_horizon",
        "benchmark_pairing",
        "serial_dependence_correction",
        "fat_tail_treatment",
    ):
        if _normal_form(report.get(field)) != _normal_form(spec.get(field)):
            return True
    try:
        if _decimal_value(report.get("confidence_level")) != _decimal_value(
            spec.get("confidence_level")
        ):
            return True
        if _decimal_value(report.get("pass_threshold")) != _decimal_value(
            spec.get("pass_threshold")
        ):
            return True
        report_sample = int(str(report.get("minimum_effective_sample_size", "")))
        spec_sample = int(str(spec.get("minimum_effective_sample_size", "")))
    except (InvalidOperation, ValueError):
        return True
    if report_sample < spec_sample:
        return True
    taxable_status = _normal_form(mandate.get("taxable_or_tax_exempt_status"))
    if _normal_form(report.get("taxable_or_tax_exempt_status")) != taxable_status:
        return True
    mandate_edge_basis = _normal_form(mandate.get("pre_tax_or_after_tax"))
    if (
        mandate_edge_basis
        and not _is_unknown(mandate_edge_basis)
        and _normal_form(report.get("pre_tax_or_after_tax")) != mandate_edge_basis
    ):
        return True
    try:
        stress_inputs = {
            _normal_form(item)
            for item in _string_sequence(report.get("stress_inputs", ()))
        }
    except ValueError:
        return True
    return not _LOWER_BOUND_REQUIRED_STRESS_INPUTS <= stress_inputs


def _verified_strategy_allocation_limits(
    payloads: tuple[Mapping[str, object], ...],
    *,
    artifact_store: FileContentAddressedStore,
    replay_store: FileContentAddressedStore,
    trust_root: TrustRoot,
    ledger_sequence: int,
    strategy_id: str,
    fixture_mode: bool,
) -> tuple[dict[str, str], ...]:
    mandate_status = _mandate_authority_status(
        payloads,
        artifact_store=artifact_store,
        replay_store=replay_store,
        trust_root=trust_root,
        ledger_sequence=ledger_sequence,
        strategy_id=strategy_id,
        fixture_mode=fixture_mode,
    )
    policy = mandate_status.valid_payloads.get("capital_allocation_policy")
    if policy is None:
        return ()
    return (
        {
            "strategy_id": strategy_id,
            "max_strategy_allocation": str(
                _decimal_value(policy.get("max_strategy_allocation"))
            ),
        },
    )


def _mandate_hard_caps_below_live(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    strategy_id: str,
) -> bool:
    del strategy_id
    policy = payloads.get("capital_allocation_policy")
    if (
        policy is not None
        and _decimal_value(policy.get("max_strategy_allocation")) == 0
    ):
        return True
    for kind, field in (
        ("jurisdiction_account_use_manifest", "live_trading_ceiling"),
        ("instrument_support_package", "promotion_ceiling"),
    ):
        payload = payloads.get(kind)
        if payload is None:
            continue
        ceiling = _optional_state(payload.get(field))
        if ceiling is not None and not state_allows(
            ceiling,
            PromotionState.TINY_LIVE_PROBE,
        ):
            return True
    return False


def _required_instrument_classes(
    payloads: Mapping[str, Mapping[str, object]],
    *,
    strategy_id: str,
) -> set[str]:
    del strategy_id
    result: set[str] = set()
    mandate = payloads.get("investment_mandate")
    if mandate is not None:
        instruments = mandate.get("allowed_instruments", ())
        if isinstance(instruments, Sequence) and not isinstance(
            instruments,
            str | bytes,
        ):
            result.update(_instrument_class(item) for item in instruments)
    return {item for item in result if item}


def _instrument_class(value: object) -> str:
    normalized = _normal_form(value)
    if normalized in {"equity", "equity_etf", "simple_equity", "stock"}:
        return "simple_equity"
    return normalized


def _is_external_account_use(payload: Mapping[str, object]) -> bool:
    account_use = _normal_form(payload.get("account_use"))
    classification = _normal_form(payload.get("classification"))
    return account_use in _EXTERNAL_ACCOUNT_USES or any(
        marker in classification for marker in _EXTERNAL_ACCOUNT_USES
    )


def _decimal_value(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value {value!r}") from exc


def _optional_state(value: object) -> PromotionState | None:
    if _is_unknown(value):
        return None
    try:
        return _state_from_value(str(value))
    except ValueError:
        return PromotionState.DISABLED


def _normal_form(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _is_unknown(value: object) -> bool:
    return _normal_form(value) in _UNKNOWN_DECLARATIONS


def _contains_fixture_marker(value: str) -> bool:
    normalized = _normal_form(value)
    return any(marker in normalized for marker in _FIXTURE_MARKERS)


def _has_valid_evidence_artifact(
    payloads: tuple[Mapping[str, object], ...],
    *,
    kind: str,
    strategy_id: str,
) -> bool:
    return any(
        _is_valid_evidence_artifact(payload, kind=kind, strategy_id=strategy_id)
        for payload in payloads
    )


def _is_valid_evidence_artifact(
    payload: Mapping[str, object],
    *,
    kind: str,
    strategy_id: str,
) -> bool:
    if str(payload.get("kind", "")) != kind:
        return False
    if kind in _AUTHORITY_EVIDENCE_ARTIFACT_KINDS | set(
        _FIRST_SLICE_REQUIRED_ARTIFACT_BLOCKERS
    ):
        if str(payload.get("strategy_id", "")) != strategy_id:
            return False
    if kind == "strategy_capability_manifest":
        supported_sides = payload.get("supported_sides", ())
        instrument_types = payload.get("instrument_types", ())
        return (
            isinstance(supported_sides, Sequence)
            and not isinstance(supported_sides, str | bytes)
            and bool(supported_sides)
            and isinstance(instrument_types, Sequence)
            and not isinstance(instrument_types, str | bytes)
            and bool(instrument_types)
        )
    if kind == "promotion_evidence":
        evidence_class = str(payload.get("evidence_class", ""))
        artifact_refs = payload.get("artifact_refs", ())
        return (
            evidence_class in {"valid", "legacy", "stale", "invalid"}
            and isinstance(artifact_refs, Sequence)
            and not isinstance(artifact_refs, str | bytes)
        )
    description = str(payload.get("description", ""))
    return bool(description.strip())


def _has_kind_with_flag(
    payloads: tuple[Mapping[str, object], ...],
    *,
    kind: str,
    flag: str,
) -> bool:
    return any(
        str(payload.get("kind", "")) == kind and bool(payload.get(flag, False))
        for payload in payloads
    )


def _state_action_contracts_from_payloads(
    payloads: tuple[Mapping[str, object], ...],
) -> dict[str, dict[str, object]] | None:
    for payload in payloads:
        if str(payload.get("kind", "")) != "state_action_contract":
            continue
        contracts = payload.get("contracts")
        if not isinstance(contracts, Mapping):
            return None
        result: dict[str, dict[str, object]] = {}
        for state, contract in contracts.items():
            if not isinstance(contract, Mapping):
                return None
            result[str(state)] = dict(contract)
        try:
            validate_state_action_contracts(result)
        except StateActionContractError:
            return None
        return result
    return None


def load_promotion_decision(
    authority_root: Path,
    *,
    strategy_id: str,
) -> PromotionDecision:
    roots = (authority_root / strategy_id, authority_root)
    for root in roots:
        if not (root / "manifest.json").exists():
            continue
        decision = evaluate_promotion_manifest(root)
        if decision.strategy_id == strategy_id:
            return decision
    return _blocked_decision(
        strategy_id=strategy_id,
        requested_state=PromotionState.DISABLED,
        blockers=(Blocker("authority_artifact_invalid"),),
    )


def build_artifact_promotion_decision_provider(
    promotion_root: Path,
) -> Callable[[str], PromotionDecision]:
    def _provider(strategy_id: str) -> PromotionDecision:
        return load_promotion_decision(promotion_root, strategy_id=strategy_id)

    return _provider


def load_state_action_contracts(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise StateActionContractError("state-action contract must be an object")
    validate_quant_artifact(payload, schema=_schema("state_action_contract"))
    contracts = payload["contracts"]
    if not isinstance(contracts, Mapping):
        raise StateActionContractError("contracts must be an object")
    result: dict[str, dict[str, object]] = {}
    for state, contract in contracts.items():
        if not isinstance(contract, Mapping):
            raise StateActionContractError("contract entries must be objects")
        result[str(state)] = dict(contract)
    validate_state_action_contracts(result)
    return result


def check_projection_drift(
    projection_path: Path,
    decision: PromotionDecision,
) -> ProjectionDrift:
    if not projection_path.exists():
        return ProjectionDrift(detected=False, blocker_code="", reason="")
    payload = json.loads(projection_path.read_text(encoding="utf-8"))
    projection_state = _state_from_value(
        str(payload.get("promotion_state", "disabled"))
    )
    if not state_allows(decision.max_state, projection_state):
        return ProjectionDrift(
            detected=True,
            blocker_code="authority_artifact_invalid",
            reason=(
                f"projection state {projection_state.value} exceeds decision cap "
                f"{decision.max_state.value}"
            ),
        )
    source_hash = str(payload.get("source_decision_hash", ""))
    if not source_hash:
        return ProjectionDrift(
            detected=True,
            blocker_code="authority_artifact_invalid",
            reason="projection source decision hash is missing",
        )
    if source_hash != decision.decision_hash:
        return ProjectionDrift(
            detected=True,
            blocker_code="authority_artifact_invalid",
            reason="projection source decision hash does not match authority decision",
        )
    return ProjectionDrift(detected=False, blocker_code="", reason="")


def classify_legacy_operator_artifact(
    *,
    artifact_type: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    strategy_id = str(payload.get("strategy_id", "unknown"))
    return {
        "schema_version": "1.0",
        "artifact_type": artifact_type,
        "strategy_id": strategy_id,
        "authority_status": LEGACY_NON_AUTHORITY_STATUS,
        "evidence_class": LEGACY_NON_AUTHORITY_STATUS,
        "v5_authority": False,
        "migration_behavior": (
            "Existing operator activation and approved-weight artifacts remain "
            "diagnostic legacy records. They cannot authorize V5 promotion or "
            "capital allocation without a signed promotion decision."
        ),
    }


def validate_state_action_contracts(
    contracts: Mapping[str, Mapping[str, object]],
) -> None:
    required_states = {state.value for state in PromotionState}
    missing_states = required_states.difference(contracts)
    if missing_states:
        raise StateActionContractError(
            "state_action_contract_missing: missing contracts for "
            + ", ".join(sorted(missing_states))
        )
    for state_value, contract in contracts.items():
        state = _state_from_value(state_value)
        _validate_state_action_contract_entry(state=state, contract=contract)


def validate_state_action_route(
    contracts: Mapping[str, Mapping[str, object]],
    *,
    state: PromotionState,
    route_label: str,
) -> None:
    validate_state_action_contracts(contracts)
    contract = contracts.get(state.value)
    if contract is None:
        raise StateActionContractError(
            f"state_action_contract_missing: {state.value} contract is absent"
        )
    disallowed_actions = _string_array(
        contract.get("disallowed_actions"),
        field=f"{state.value}.disallowed_actions",
    )
    if route_label in disallowed_actions:
        raise StateActionContractError(
            f"state_action_contract_missing: {state.value} disallows {route_label}"
        )
    route_constraints = contract.get("route_constraints")
    if not isinstance(route_constraints, Mapping):
        raise StateActionContractError(
            f"state_action_contract_missing: {state.value} route constraints missing"
        )
    allowed_routes = _string_array(
        route_constraints.get("allowed_routes"),
        field=f"{state.value}.route_constraints.allowed_routes",
    )
    if route_label not in allowed_routes:
        raise StateActionContractError(
            f"state_action_contract_missing: {state.value} route {route_label} "
            "is not allowed"
        )


def _validate_state_action_contract_entry(
    *,
    state: PromotionState,
    contract: Mapping[str, object],
) -> None:
    required_fields = {
        "data_access",
        "broker_access",
        "order_permission",
        "capital_ceiling",
        "short_permission",
        "required_runtime_controls",
        "route_constraints",
        "disallowed_actions",
    }
    missing_fields = required_fields.difference(contract)
    if missing_fields:
        raise StateActionContractError(
            "state_action_contract_missing: "
            f"{state.value} missing {', '.join(sorted(missing_fields))}"
        )
    order_permission = str(contract["order_permission"])
    allowed_order_permissions = {
        PromotionState.DISABLED: {"none"},
        PromotionState.RESEARCH_ONLY: {"none"},
        PromotionState.PAPER_SHADOW: {"none", "shadow_decisions"},
        PromotionState.PAPER_TRADING: {"paper_orders"},
        PromotionState.TINY_LIVE_PROBE: {"live_probe_orders"},
        PromotionState.PRODUCTION: {"live_orders"},
    }[state]
    if order_permission not in allowed_order_permissions:
        raise StateActionContractError(
            "state_action_contract_missing: "
            f"{state.value} cannot permit {order_permission}"
        )
    data_access = str(contract["data_access"])
    allowed_data_access = {
        PromotionState.DISABLED: {"none"},
        PromotionState.RESEARCH_ONLY: {"none", "historical"},
        PromotionState.PAPER_SHADOW: {"none", "historical", "delayed", "realtime"},
        PromotionState.PAPER_TRADING: {"realtime"},
        PromotionState.TINY_LIVE_PROBE: {"realtime"},
        PromotionState.PRODUCTION: {"realtime"},
    }[state]
    if data_access not in allowed_data_access:
        raise StateActionContractError(
            "state_action_contract_missing: "
            f"{state.value} cannot use data_access={data_access}"
        )
    broker_access = str(contract["broker_access"])
    allowed_broker_access = {
        PromotionState.DISABLED: {"none"},
        PromotionState.RESEARCH_ONLY: {"none"},
        PromotionState.PAPER_SHADOW: {"none", "read_only"},
        PromotionState.PAPER_TRADING: {"paper"},
        PromotionState.TINY_LIVE_PROBE: {"live"},
        PromotionState.PRODUCTION: {"live"},
    }[state]
    if broker_access not in allowed_broker_access:
        raise StateActionContractError(
            "state_action_contract_missing: "
            f"{state.value} cannot use broker_access={broker_access}"
        )
    short_permission = str(contract["short_permission"])
    allowed_short_permissions = {
        PromotionState.DISABLED: {"none"},
        PromotionState.RESEARCH_ONLY: {"none"},
        PromotionState.PAPER_SHADOW: {"none", "shadow_only"},
        PromotionState.PAPER_TRADING: {"none", "paper"},
        PromotionState.TINY_LIVE_PROBE: {"none", "live_probe"},
        PromotionState.PRODUCTION: {"none", "live"},
    }[state]
    if short_permission not in allowed_short_permissions:
        raise StateActionContractError(
            "state_action_contract_missing: "
            f"{state.value} cannot use short_permission={short_permission}"
        )
    capital_ceiling = _canonical_decimal_field(
        contract["capital_ceiling"],
        field=f"{state.value}.capital_ceiling",
    )
    if state in {
        PromotionState.DISABLED,
        PromotionState.RESEARCH_ONLY,
        PromotionState.PAPER_SHADOW,
    } and capital_ceiling != Decimal("0"):
        raise StateActionContractError(
            "state_action_contract_missing: " f"{state.value} cannot allocate capital"
        )
    _string_array(
        contract["required_runtime_controls"],
        field=f"{state.value}.required_runtime_controls",
    )
    _string_array(
        contract["disallowed_actions"],
        field=f"{state.value}.disallowed_actions",
    )
    route_constraints = contract["route_constraints"]
    if not isinstance(route_constraints, Mapping):
        raise StateActionContractError(
            "state_action_contract_missing: "
            f"{state.value}.route_constraints must be an object"
        )
    allowed_routes = _string_array(
        route_constraints.get("allowed_routes"),
        field=f"{state.value}.route_constraints.allowed_routes",
    )
    _canonical_decimal_field(
        route_constraints.get("max_order_notional"),
        field=f"{state.value}.route_constraints.max_order_notional",
    )
    expected_route_by_permission = {
        "shadow_decisions": "shadow_decision",
        "paper_orders": "paper_order",
        "live_probe_orders": "live_probe_order",
        "live_orders": "live_order",
    }
    expected_route = expected_route_by_permission.get(order_permission)
    if expected_route is not None and expected_route not in allowed_routes:
        raise StateActionContractError(
            "state_action_contract_missing: "
            f"{state.value} lacks route {expected_route}"
        )


def _string_array(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise StateActionContractError(
            f"state_action_contract_missing: {field} must be an array"
        )
    return tuple(str(item) for item in value)


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ValueError("expected an array of strings")
    return tuple(str(item) for item in value)


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return int(float(value))
            except ValueError:
                return 0
    return 0


def _canonical_decimal_field(value: object, *, field: str) -> Decimal:
    if not isinstance(value, str):
        raise StateActionContractError(
            f"state_action_contract_missing: {field} must be a decimal string"
        )
    decimal_value = Decimal(value)
    canonical_value = (
        "0" if decimal_value.is_zero() else format(decimal_value.normalize(), "f")
    )
    if value != canonical_value:
        raise StateActionContractError(
            f"state_action_contract_missing: {field} must be canonical"
        )
    return decimal_value


def _blocked_decision(
    *,
    strategy_id: str,
    requested_state: PromotionState,
    blockers: tuple[Blocker, ...],
) -> PromotionDecision:
    return PromotionDecision(
        strategy_id=strategy_id,
        requested_state=requested_state,
        max_state=strictest_state_cap(blockers),
        blockers=blockers,
        artifact_refs=(),
        ledger_sequence=None,
        ledger_hash=None,
    )


def _state_from_value(value: str) -> PromotionState:
    try:
        return PromotionState(value)
    except ValueError as exc:
        raise ValueError(f"unknown promotion state {value!r}") from exc


__all__ = [
    "BLOCKER_REGISTRY",
    "LEGACY_NON_AUTHORITY_STATUS",
    "Blocker",
    "BlockerRegistryRecord",
    "ProjectionDrift",
    "PromotionDecision",
    "PromotionState",
    "StateActionContractError",
    "blocker_registry_coverage_rows",
    "build_artifact_promotion_decision_provider",
    "check_projection_drift",
    "classify_legacy_operator_artifact",
    "evaluate_promotion_manifest",
    "evaluate_cost_capacity_blockers",
    "evaluate_provenance_blockers",
    "evaluate_statistical_evidence_blockers",
    "load_state_action_contracts",
    "load_promotion_decision",
    "state_allows",
    "strictest_state_cap",
    "validate_blocker_registry_coverage",
    "validate_state_action_contracts",
    "validate_state_action_route",
]
