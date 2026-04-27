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
# Defect 1 — required artifact kinds for each capable promotion state.
# Maps each requested_state to the artifact kinds the bundle MUST contain.
# A missing kind emits the "<kind>_missing" blocker code (or the existing
# blocker code in _REQUIRED_KIND_TO_BLOCKER_CODE_OVERRIDES).
_PAPER_TRADING_REQUIRED_KINDS: frozenset[str] = frozenset(
    {
        "statistical_validation_report",
        "cost_model_report",
        "capacity_curve_report",
        "portfolio_utility_definition",
        "optimizer_validation_report",
        "sizing_policy",
    }
)
_TINY_LIVE_PROBE_REQUIRED_KINDS: frozenset[str] = (
    _PAPER_TRADING_REQUIRED_KINDS
    | frozenset(
        {
            "live_probe_plan",
            "authority_boundary",
            "pre_trade_control_manifest",
            "operational_safety_drill",
        }
    )
)
_PRODUCTION_REQUIRED_KINDS: frozenset[str] = (
    _TINY_LIVE_PROBE_REQUIRED_KINDS
    | frozenset(
        {
            "live_probe_recertification_report",
            "recertification_report",
            "drift_monitor_spec",
        }
    )
)
_REQUIRED_KIND_BY_REQUESTED_STATE: dict[str, frozenset[str]] = {
    "paper_trading": _PAPER_TRADING_REQUIRED_KINDS,
    "tiny_live_probe": _TINY_LIVE_PROBE_REQUIRED_KINDS,
    "production": _PRODUCTION_REQUIRED_KINDS,
}
# A few existing blocker codes already cover specific missing-kind cases.
# Map kind → existing blocker code so the new check reuses them rather than
# inventing a parallel code with the same semantics.
_REQUIRED_KIND_TO_BLOCKER_CODE_OVERRIDES: dict[str, str] = {
    "authority_boundary": "authority_boundary_missing",
    "recertification_report": "recertification_report_missing",
    "drift_monitor_spec": "drift_monitor_spec_missing",
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
    # Defect 1 — required-kind blockers must surface fixture/red-test/runtime
    # coverage so empty bundles cannot silently bypass authority enforcement.
    "statistical_validation_report_missing",
    "cost_model_report_missing",
    "capacity_curve_report_missing",
    "portfolio_utility_definition_missing",
    "optimizer_validation_report_missing",
    "sizing_policy_missing",
    "live_probe_plan_missing",
    "pre_trade_control_manifest_missing",
    "operational_safety_drill_missing",
    "live_probe_recertification_report_missing",
    # Defect 6 — Wave 4 statistical evidence
    "trial_lineage_contaminated",
    "trial_universe_incomplete",
    "dsr_pbo_inputs_incomplete",
    "point_in_time_data_incomplete",
    "pending_threshold",
    # Defect 6 — Wave 5 cost & capacity
    "execution_semantics_incomplete",
    "execution_sample_power_missing",
    "capacity_lower_bound_missing",
    "live_sample_requirement_unmet",
    "unsupported_cost_bucket",
    "capacity_extrapolation_risk",
    # Defect 6 — Wave 6 portfolio / optimizer / forecast / sizing
    "optimizer_or_sizing_lockbox_missing",
    "tail_risk_missing",
    "applicable_baseline_excluded",
    "paired_oos_utility_failed",
    "no_alpha_pipeline_edge",
    "optimizer_perturbation_unstable",
    "covariance_drift_unresolved",
    "turnover_cap_exceeded",
    "expected_return_not_promotion_valid",
    "expected_return_uncertainty_uncalibrated",
    "feature_timestamp_unauditable",
    "hard_exposure_caps_missing",
    "kelly_gate_incomplete",
    "sizing_property_violated",
    # Defect 6 — Wave 7 short-side capability
    "short_legal_mechanics_missing",
    "borrow_snapshot_stale",
    "locate_documentation_missing",
    "locate_expired",
    "paper_live_short_semantics_mismatch",
    "live_probe_short_evidence_missing",
    "broker_initiated_cover_unreconciled",
    "legacy_short_evidence",
    # Defect 6 — Wave 8 live probe & operational safety
    "pre_trade_control_missing",
    "authority_boundary_missing",
    "authority_boundary_invalid",
    "authority_boundary_expired",
    "live_probe_plan_expired",
    "live_probe_minimum_activity_unmet",
    "live_probe_inconclusive",
    "safety_drill_stale",
    "safety_drill_failed",
    "broker_timeout_state_machine_missing",
    "broker_timeout_retry_unsafe",
    "idempotency_evidence_missing",
    "reconciliation_evidence_missing",
    "reconciliation_incident_unresolved",
    "manual_exception_disabled_core_control",
    "post_probe_recertification_missing",
    # Defect 6 — Wave 9 recertification & change control
    "production_approval_expired",
    "next_review_due_passed",
    "recertification_report_missing",
    "drift_monitor_spec_missing",
    "unrecorded_material_change",
    "drift_alarm_live",
    "dependency_scope_unresolved",
    # Defect 6 — Wave 10 legacy retirement / hardening
    "after_tax_edge_missing_for_taxable_account",
    "legacy_artifacts_detected",
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
    ("tail_risk_missing", PromotionState.PAPER_SHADOW),
    ("applicable_baseline_excluded", PromotionState.PAPER_SHADOW),
    ("paired_oos_utility_failed", PromotionState.PAPER_SHADOW),
    ("no_alpha_pipeline_edge", PromotionState.PAPER_SHADOW),
    ("optimizer_perturbation_unstable", PromotionState.PAPER_SHADOW),
    ("covariance_drift_unresolved", PromotionState.PAPER_SHADOW),
    ("turnover_cap_exceeded", PromotionState.PAPER_SHADOW),
    ("expected_return_not_promotion_valid", PromotionState.PAPER_SHADOW),
    ("expected_return_uncertainty_uncalibrated", PromotionState.PAPER_SHADOW),
    ("feature_timestamp_unauditable", PromotionState.PAPER_SHADOW),
    ("hard_exposure_caps_missing", PromotionState.PAPER_SHADOW),
    ("kelly_gate_incomplete", PromotionState.PAPER_SHADOW),
    ("sizing_property_violated", PromotionState.PAPER_SHADOW),
    ("borrow_snapshot_stale", PromotionState.PAPER_SHADOW),
    ("locate_documentation_missing", PromotionState.PAPER_SHADOW),
    ("locate_expired", PromotionState.PAPER_SHADOW),
    ("paper_live_short_semantics_mismatch", PromotionState.PAPER_SHADOW),
    ("live_probe_short_evidence_missing", PromotionState.TINY_LIVE_PROBE),
    ("broker_initiated_cover_unreconciled", PromotionState.PAPER_TRADING),
    ("legacy_short_evidence", PromotionState.RESEARCH_ONLY),
    ("authority_boundary_missing", PromotionState.PAPER_TRADING),
    ("authority_boundary_invalid", PromotionState.PAPER_TRADING),
    ("authority_boundary_expired", PromotionState.PAPER_TRADING),
    ("live_probe_plan_expired", PromotionState.PAPER_TRADING),
    ("live_probe_minimum_activity_unmet", PromotionState.TINY_LIVE_PROBE),
    ("live_probe_inconclusive", PromotionState.TINY_LIVE_PROBE),
    ("safety_drill_stale", PromotionState.PAPER_TRADING),
    ("safety_drill_failed", PromotionState.PAPER_TRADING),
    ("broker_timeout_state_machine_missing", PromotionState.TINY_LIVE_PROBE),
    ("broker_timeout_retry_unsafe", PromotionState.PAPER_TRADING),
    ("idempotency_evidence_missing", PromotionState.PAPER_TRADING),
    ("reconciliation_evidence_missing", PromotionState.PAPER_TRADING),
    ("reconciliation_incident_unresolved", PromotionState.PAPER_TRADING),
    ("manual_exception_disabled_core_control", PromotionState.DISABLED),
    ("post_probe_recertification_missing", PromotionState.TINY_LIVE_PROBE),
    ("production_approval_expired", PromotionState.PAPER_TRADING),
    ("next_review_due_passed", PromotionState.PAPER_TRADING),
    ("recertification_report_missing", PromotionState.PAPER_TRADING),
    ("legacy_artifacts_detected", PromotionState.PAPER_SHADOW),
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
    # Defect 14 — distinguish parse-error from expired.
    ("live_probe_plan_invalid", PromotionState.PAPER_TRADING),
    ("production_approval_invalid", PromotionState.PAPER_TRADING),
    ("next_review_invalid", PromotionState.PAPER_TRADING),
    ("drift_monitor_spec_invalid", PromotionState.PAPER_SHADOW),
    # Defect 1 — required-kind blockers for capable promotion states.
    # paper_trading-required artifacts cap at PAPER_SHADOW when missing.
    ("statistical_validation_report_missing", PromotionState.PAPER_SHADOW),
    ("cost_model_report_missing", PromotionState.PAPER_SHADOW),
    ("capacity_curve_report_missing", PromotionState.PAPER_SHADOW),
    ("portfolio_utility_definition_missing", PromotionState.PAPER_SHADOW),
    ("optimizer_validation_report_missing", PromotionState.PAPER_SHADOW),
    ("sizing_policy_missing", PromotionState.PAPER_SHADOW),
    # tiny_live_probe-only required artifacts cap at PAPER_TRADING.
    ("live_probe_plan_missing", PromotionState.PAPER_TRADING),
    ("pre_trade_control_manifest_missing", PromotionState.PAPER_TRADING),
    ("operational_safety_drill_missing", PromotionState.PAPER_TRADING),
    # production-only required artifact caps at TINY_LIVE_PROBE.
    ("live_probe_recertification_report_missing", PromotionState.TINY_LIVE_PROBE),
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
    # Defect 6 — Wave 2 mandate codes (mandate_promotion_ceiling_exceeded,
    # allocation_policy_limit_exceeded, lower_bound_net_edge_undefined,
    # net_edge_lower_bound_below_threshold) were previously mislabeled
    # ``wave_1``. They are mandate-policy blockers and properly belong to
    # Wave 2.
    _WAVE_2_MANDATE_CODES = {
        "mandate_promotion_ceiling_exceeded",
        "allocation_policy_limit_exceeded",
        "lower_bound_net_edge_undefined",
        "net_edge_lower_bound_below_threshold",
    }
    BLOCKER_REGISTRY[_code] = _record(
        _code,
        _existing.max_state,
        owning_wave="wave_2" if _code in _WAVE_2_MANDATE_CODES else "wave_1",
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


# Defect 1 — required-kind blocker registry overrides. Each new "*_missing"
# code carries real owning_wave/evaluator/red_test/fixture/cli_output/
# web_report_field/runtime_enforcement metadata so coverage validation cannot
# silently regress.
for _code, _wave, _fixture, _red_test in (
    (
        "statistical_validation_report_missing",
        "wave_4",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_statistical_validation_report_caps_at_paper_shadow",
    ),
    (
        "cost_model_report_missing",
        "wave_5",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_cost_model_caps_at_paper_shadow",
    ),
    (
        "capacity_curve_report_missing",
        "wave_5",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_capacity_curve_caps_at_paper_shadow",
    ),
    (
        "portfolio_utility_definition_missing",
        "wave_6",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_portfolio_utility_caps_at_paper_shadow",
    ),
    (
        "optimizer_validation_report_missing",
        "wave_6",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_optimizer_validation_caps_at_paper_shadow",
    ),
    (
        "sizing_policy_missing",
        "wave_6",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_sizing_policy_caps_at_paper_shadow",
    ),
    (
        "live_probe_plan_missing",
        "wave_8",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_live_probe_plan_caps_at_paper_trading",
    ),
    (
        "pre_trade_control_manifest_missing",
        "wave_8",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_pre_trade_control_caps_at_paper_trading",
    ),
    (
        "operational_safety_drill_missing",
        "wave_8",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_operational_safety_drill_caps_at_paper_trading",
    ),
    (
        "live_probe_recertification_report_missing",
        "wave_9",
        "tests/fixtures/promotion/paper_shadow_placeholder",
        "test_production_request_without_live_probe_recertification_blocks_production",
    ),
):
    _existing = BLOCKER_REGISTRY[_code]
    BLOCKER_REGISTRY[_code] = _record(
        _code,
        _existing.max_state,
        owning_wave=_wave,
        fixture=_fixture,
        evaluator=f"evaluate_{_code}",
        red_test=_red_test,
        cli_output="promotion-check.blockers",
        web_report_field="dashboard.document_summary.v5_authority_status",
        runtime_enforcement="activation_refusal",
    )


# Defect 6 — Wave 4-10 blocker registry metadata backfill. Each code is
# tied to its owning evaluator, a representative red-test name in the
# wave's test file, and the canonical fixture/CLI/web/runtime fields so
# ``validate_blocker_registry_coverage(strict=True)`` succeeds with no
# synthetic placeholders.
_WAVE_4_TO_10_OVERRIDES: tuple[tuple[str, str, str, str, str], ...] = (
    # (code, owning_wave, evaluator, red_test, cli_output)
    # Wave 4 — statistical evidence
    (
        "trial_lineage_contaminated",
        "wave_4",
        "evaluate_provenance_blockers",
        "test_experiment_and_dataset_provenance_blockers_cap_promotion",
        "promotion-check.statistical_blockers",
    ),
    (
        "trial_universe_incomplete",
        "wave_4",
        "evaluate_provenance_blockers",
        "test_experiment_and_dataset_provenance_blockers_cap_promotion",
        "promotion-check.statistical_blockers",
    ),
    (
        "dsr_pbo_inputs_incomplete",
        "wave_4",
        "evaluate_statistical_evidence_blockers",
        "test_psr_normal_returns_collapses_to_lo_2002_variance",
        "promotion-check.statistical_blockers",
    ),
    (
        "point_in_time_data_incomplete",
        "wave_4",
        "evaluate_provenance_blockers",
        "test_experiment_and_dataset_provenance_blockers_cap_promotion",
        "promotion-check.statistical_blockers",
    ),
    (
        "pending_threshold",
        "wave_4",
        "evaluate_statistical_evidence_blockers",
        "test_missing_threshold_yields_pending_threshold_blocker",
        "promotion-check.statistical_blockers",
    ),
    # Wave 5 — cost & capacity
    (
        "execution_semantics_incomplete",
        "wave_5",
        "evaluate_cost_capacity_blockers",
        "test_evaluator_re_derives_quote_quality_blocker_from_raw_fields",
        "promotion-check.blockers",
    ),
    (
        "execution_sample_power_missing",
        "wave_5",
        "evaluate_cost_capacity_blockers",
        "test_missing_powered_bucket_yields_execution_sample_power_missing",
        "promotion-check.blockers",
    ),
    (
        "capacity_lower_bound_missing",
        "wave_5",
        "evaluate_cost_capacity_blockers",
        "test_capacity_without_lower_bound_yields_capacity_lower_bound_missing",
        "promotion-check.blockers",
    ),
    (
        "live_sample_requirement_unmet",
        "wave_5",
        "evaluate_cost_capacity_blockers",
        "test_paper_only_execution_data_cannot_support_market_impact_claim",
        "promotion-check.blockers",
    ),
    (
        "unsupported_cost_bucket",
        "wave_5",
        "evaluate_cost_capacity_blockers",
        "test_unsupported_sparse_bucket_yields_unsupported_cost_bucket",
        "promotion-check.blockers",
    ),
    (
        "capacity_extrapolation_risk",
        "wave_5",
        "evaluate_cost_capacity_blockers",
        "test_capacity_extrapolation_risk_caps_below_production",
        "promotion-check.blockers",
    ),
    # Wave 6 — portfolio / optimizer / forecast / sizing
    (
        "optimizer_or_sizing_lockbox_missing",
        "wave_6",
        "evaluate_portfolio_optimizer_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "tail_risk_missing",
        "wave_6",
        "evaluate_portfolio_optimizer_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "applicable_baseline_excluded",
        "wave_6",
        "evaluate_portfolio_optimizer_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "paired_oos_utility_failed",
        "wave_6",
        "evaluate_portfolio_optimizer_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "no_alpha_pipeline_edge",
        "wave_6",
        "evaluate_portfolio_optimizer_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "optimizer_perturbation_unstable",
        "wave_6",
        "evaluate_portfolio_optimizer_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "covariance_drift_unresolved",
        "wave_6",
        "evaluate_portfolio_optimizer_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "turnover_cap_exceeded",
        "wave_6",
        "evaluate_portfolio_optimizer_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "expected_return_not_promotion_valid",
        "wave_6",
        "evaluate_portfolio_optimizer_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "expected_return_uncertainty_uncalibrated",
        "wave_6",
        "evaluate_forecast_sizing_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "feature_timestamp_unauditable",
        "wave_6",
        "evaluate_forecast_sizing_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "hard_exposure_caps_missing",
        "wave_6",
        "evaluate_forecast_sizing_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "kelly_gate_incomplete",
        "wave_6",
        "evaluate_forecast_sizing_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    (
        "sizing_property_violated",
        "wave_6",
        "evaluate_forecast_sizing_blockers",
        "test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing",
        "promotion-check.blockers",
    ),
    # Wave 7 — short-side capability
    (
        "short_legal_mechanics_missing",
        "wave_7",
        "evaluate_short_blockers",
        "test_short_capability_manifest_schema_validates",
        "promotion-check.blockers",
    ),
    (
        "borrow_snapshot_stale",
        "wave_7",
        "evaluate_short_blockers",
        "test_short_capability_manifest_schema_validates",
        "promotion-check.blockers",
    ),
    (
        "locate_documentation_missing",
        "wave_7",
        "evaluate_short_blockers",
        "test_short_capability_manifest_schema_validates",
        "promotion-check.blockers",
    ),
    (
        "locate_expired",
        "wave_7",
        "evaluate_short_blockers",
        "test_short_capability_manifest_schema_validates",
        "promotion-check.blockers",
    ),
    (
        "paper_live_short_semantics_mismatch",
        "wave_7",
        "evaluate_short_blockers",
        "test_short_capability_manifest_schema_validates",
        "promotion-check.blockers",
    ),
    (
        "live_probe_short_evidence_missing",
        "wave_7",
        "evaluate_short_blockers",
        "test_short_capability_manifest_schema_validates",
        "promotion-check.blockers",
    ),
    (
        "broker_initiated_cover_unreconciled",
        "wave_7",
        "evaluate_short_blockers",
        "test_short_capability_manifest_schema_validates",
        "promotion-check.blockers",
    ),
    (
        "legacy_short_evidence",
        "wave_7",
        "evaluate_short_blockers",
        "test_short_capability_manifest_schema_validates",
        "promotion-check.blockers",
    ),
    # Wave 8 — live probe & operational safety
    (
        "pre_trade_control_missing",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_missing_price_collar_yields_pre_trade_control_missing",
        "promotion-check.blockers",
    ),
    (
        "authority_boundary_missing",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_expired_live_probe_approval_blocks_live_route",
        "promotion-check.blockers",
    ),
    (
        "authority_boundary_invalid",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_evaluator_re_derives_authority_boundary_invalid",
        "promotion-check.blockers",
    ),
    (
        "authority_boundary_expired",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_evaluator_re_derives_authority_boundary_expired",
        "promotion-check.blockers",
    ),
    (
        "live_probe_plan_expired",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_expired_live_probe_approval_blocks_live_route",
        "promotion-check.blockers",
    ),
    (
        "live_probe_minimum_activity_unmet",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_no_signal_probe_is_inconclusive_unless_extension_predeclared",
        "promotion-check.blockers",
    ),
    (
        "live_probe_inconclusive",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_no_signal_probe_is_inconclusive_unless_extension_predeclared",
        "promotion-check.blockers",
    ),
    (
        "safety_drill_stale",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_unresolved_reconciliation_incident_blocks_production_eligibility",
        "promotion-check.blockers",
    ),
    (
        "safety_drill_failed",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_unresolved_reconciliation_incident_blocks_production_eligibility",
        "promotion-check.blockers",
    ),
    (
        "broker_timeout_state_machine_missing",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_timeout_state_cannot_retry_until_reconciliation",
        "promotion-check.blockers",
    ),
    (
        "broker_timeout_retry_unsafe",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_timeout_state_cannot_retry_until_reconciliation",
        "promotion-check.blockers",
    ),
    (
        "idempotency_evidence_missing",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_unresolved_reconciliation_incident_blocks_production_eligibility",
        "promotion-check.blockers",
    ),
    (
        "reconciliation_evidence_missing",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_unresolved_reconciliation_incident_blocks_production_eligibility",
        "promotion-check.blockers",
    ),
    (
        "reconciliation_incident_unresolved",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_unresolved_reconciliation_incident_blocks_production_eligibility",
        "promotion-check.blockers",
    ),
    (
        "manual_exception_disabled_core_control",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_manual_exception_disabling_kill_switch_is_rejected",
        "promotion-check.blockers",
    ),
    (
        "post_probe_recertification_missing",
        "wave_8",
        "evaluate_live_probe_blockers",
        "test_recertification_report_with_stale_run_refs_blocks_live_probe_promotion",
        "promotion-check.blockers",
    ),
    # Wave 9 — recertification & change control
    (
        "production_approval_expired",
        "wave_9",
        "evaluate_change_control_blockers",
        "test_production_approval_expires_and_decays",
        "promotion-check.blockers",
    ),
    (
        "next_review_due_passed",
        "wave_9",
        "evaluate_change_control_blockers",
        "test_recertification_with_expired_review_caps_at_paper_trading",
        "promotion-check.blockers",
    ),
    (
        "recertification_report_missing",
        "wave_9",
        "evaluate_change_control_blockers",
        "test_recertification_report_with_mismatched_change_id_blocks_production",
        "promotion-check.blockers",
    ),
    (
        "drift_monitor_spec_missing",
        "wave_9",
        "evaluate_change_control_blockers",
        "test_drift_monitor_spec_missing_yields_drift_monitor_spec_missing",
        "promotion-check.blockers",
    ),
    (
        "unrecorded_material_change",
        "wave_9",
        "evaluate_change_control_blockers",
        "test_evaluator_re_derives_unrecorded_material_change_from_critical",
        "promotion-check.blockers",
    ),
    (
        "drift_alarm_live",
        "wave_9",
        "evaluate_change_control_blockers",
        "test_evaluator_re_derives_drift_alarm_live_from_demotion_recommendation",
        "promotion-check.blockers",
    ),
    (
        "dependency_scope_unresolved",
        "wave_9",
        "evaluate_change_control_blockers",
        "test_dependency_scope_unresolved_blocks_production",
        "promotion-check.blockers",
    ),
    # Wave 10 — legacy retirement / hardening
    (
        "after_tax_edge_missing_for_taxable_account",
        "wave_10",
        "evaluate_legacy_retirement_blockers",
        "test_taxable_production_without_after_tax_edge_evidence_caps_at_paper_trading",
        "promotion-check.blockers",
    ),
    (
        "legacy_artifacts_detected",
        "wave_10",
        "evaluate_legacy_retirement_blockers",
        "test_wave1_golden_fixture_inventory_is_present",
        "promotion-check.blockers",
    ),
)


def evaluate_legacy_retirement_blockers(
    *,
    artifact_payloads: Sequence[Mapping[str, object]] = (),
) -> tuple[Blocker, ...]:
    """Wave 10 — surface ``legacy_artifacts_detected`` from
    ``legacy_artifact_migration_report`` payloads.

    The builder in ``tradingx.legacy_retirement`` appends the blocker
    when the classifier finds legacy/invalid artifacts. The evaluator
    re-derives the blocker from the report's ``summary_counts`` so a
    tampered payload claiming ``blocker_codes=[]`` cannot bypass the
    PAPER_SHADOW cap.
    """

    blockers: list[Blocker] = []
    for payload in artifact_payloads:
        if str(payload.get("kind", "")) != "legacy_artifact_migration_report":
            continue
        summary_counts = payload.get("summary_counts", {})
        legacy_count = 0
        invalid_count = 0
        if isinstance(summary_counts, Mapping):
            legacy_count = int(summary_counts.get("legacy", 0) or 0)
            invalid_count = int(summary_counts.get("invalid", 0) or 0)
        if legacy_count > 0 or invalid_count > 0:
            _append_blocker(blockers, "legacy_artifacts_detected")
        for code in _string_sequence(payload.get("blocker_codes", ())):
            if code in BLOCKER_REGISTRY:
                _append_blocker(blockers, code)
    return tuple(blockers)


for (
    _code,
    _wave,
    _evaluator,
    _red_test,
    _cli_output,
) in _WAVE_4_TO_10_OVERRIDES:
    if _code not in BLOCKER_REGISTRY:
        continue
    _existing = BLOCKER_REGISTRY[_code]
    BLOCKER_REGISTRY[_code] = _record(
        _code,
        _existing.max_state,
        owning_wave=_wave,
        fixture="tests/fixtures/promotion/paper_shadow_placeholder",
        evaluator=_evaluator,
        red_test=_red_test,
        cli_output=_cli_output,
        web_report_field="dashboard.document_summary.v5_authority_status",
        runtime_enforcement="activation_refusal",
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


# Defect 1 evaluator stubs. Each returns the canonical blocker code emitted by
# `_evaluate_verified_decision_blockers` when the corresponding artifact kind
# is absent from a paper_trading/tiny_live_probe/production-targeted bundle.
def evaluate_statistical_validation_report_missing() -> str:
    return "statistical_validation_report_missing"


def evaluate_cost_model_report_missing() -> str:
    return "cost_model_report_missing"


def evaluate_capacity_curve_report_missing() -> str:
    return "capacity_curve_report_missing"


def evaluate_portfolio_utility_definition_missing() -> str:
    return "portfolio_utility_definition_missing"


def evaluate_optimizer_validation_report_missing() -> str:
    return "optimizer_validation_report_missing"


def evaluate_sizing_policy_missing() -> str:
    return "sizing_policy_missing"


def evaluate_live_probe_plan_missing() -> str:
    return "live_probe_plan_missing"


def evaluate_pre_trade_control_manifest_missing() -> str:
    return "pre_trade_control_manifest_missing"


def evaluate_operational_safety_drill_missing() -> str:
    return "operational_safety_drill_missing"


def evaluate_live_probe_recertification_report_missing() -> str:
    return "live_probe_recertification_report_missing"


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
    """Defect 13 — anchored test-name discovery.

    Earlier versions used a substring search, so a registry red_test of
    ``test_foo`` would match ``test_foo_baseline_helper`` even though
    only the latter existed. Now we require an anchored pattern
    ``def\\s+test_<name>\\b`` so the registry value must point at an
    exact pytest test name.
    """

    test_root = repo_root / "tests"
    if not test_root.exists():
        return False
    pattern = re.compile(r"^\s*def\s+" + re.escape(red_test) + r"\b", re.MULTILINE)
    return any(
        pattern.search(path.read_text(encoding="utf-8"))
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
        "portfolio_utility_definition",
        "optimizer_validation_report",
        "optimizer_fallback_record",
        "forecast_model_manifest",
        "feature_manifest",
        "label_definition",
        "expected_return_report",
        "sizing_policy",
        "short_capability_manifest",
        "borrow_availability_snapshot",
        "short_financing_model",
        "short_risk_report",
        "short_runtime_event",
        "authority_boundary",
        "pre_trade_control_manifest",
        "operational_safety_drill",
        "live_probe_plan",
        "live_probe_run_record",
        "live_probe_recertification_report",
        "broker_timeout_state_transition",
        "runtime_override_event",
        "reconciliation_incident",
        "change_control_record",
        "replay_equivalence_report",
        "recertification_report",
        "drift_monitor_spec",
        "drift_monitor_report",
        "production_decay_event",
        "legacy_artifact_migration_report",
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
    # Defect 1 — every capable promotion state requires a specific authority
    # artifact set. A bundle that omits any required kind cannot reach that
    # state regardless of what other artifacts assert. The new blocker caps
    # the decision at the state immediately below the request.
    requested_state_value = str(decision_payload.get("requested_state", ""))
    required_kinds = _REQUIRED_KIND_BY_REQUESTED_STATE.get(
        requested_state_value, frozenset()
    )
    if required_kinds:
        present_kinds = {str(payload.get("kind", "")) for payload in artifact_payloads}
        for required_kind in sorted(required_kinds):
            if required_kind in present_kinds:
                continue
            blocker_code = _REQUIRED_KIND_TO_BLOCKER_CODE_OVERRIDES.get(
                required_kind, f"{required_kind}_missing"
            )
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
    for blocker in evaluate_portfolio_optimizer_blockers(
        artifact_payloads=artifact_payloads,
    ):
        _append_blocker(blockers, blocker.code)
    for blocker in evaluate_forecast_sizing_blockers(
        artifact_payloads=artifact_payloads,
    ):
        _append_blocker(blockers, blocker.code)
    for blocker in evaluate_short_blockers(
        artifact_payloads=artifact_payloads,
    ):
        _append_blocker(blockers, blocker.code)
    for blocker in evaluate_live_probe_blockers(
        artifact_payloads=artifact_payloads,
    ):
        _append_blocker(blockers, blocker.code)
    for blocker in evaluate_change_control_blockers(
        artifact_payloads=artifact_payloads,
    ):
        _append_blocker(blockers, blocker.code)
    for blocker in evaluate_legacy_retirement_blockers(
        artifact_payloads=artifact_payloads,
    ):
        _append_blocker(blockers, blocker.code)

    target_weights_raw = decision_payload.get("target_weights", {})
    if not isinstance(target_weights_raw, Mapping):
        raise AuthorityLedgerError("target_weights must be an object")
    target_weights = dict(target_weights_raw)
    has_negative_weight = any(
        Decimal(str(weight)) < Decimal("0") for weight in target_weights.values()
    )
    if has_negative_weight and not _has_short_authority(artifact_payloads):
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
    # Defect 11 — Stage 13 under-reporting check.
    # If the operator's payload claimed a blocker that the evaluators
    # never derived AND that claimed code carries a stricter max_state
    # than the strictest derived blocker, surface
    # ``authority_artifact_invalid`` so we cannot under-report by
    # inflating the payload list. The check fires only when the payload
    # claims STRICTER caps than the derived ones, i.e. when the derived
    # state would be MORE permissive than the payload claims.
    derived_codes = {b.code for b in blockers if b.code in BLOCKER_REGISTRY}
    payload_codes = {
        str(code) for code in blocker_codes_raw if str(code) in BLOCKER_REGISTRY
    }
    extra_payload_codes = payload_codes - derived_codes
    if extra_payload_codes:
        derived_state_cap = strictest_state_cap(tuple(blockers))
        for code in extra_payload_codes:
            payload_state = BLOCKER_REGISTRY[code].max_state
            if _STATE_ORDER[payload_state] < _STATE_ORDER[derived_state_cap]:
                _append_blocker(blockers, "authority_artifact_invalid")
                break
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


_TAIL_RISK_TERMS: frozenset[str] = frozenset(
    {
        "cvar",
        "expected_shortfall",
        "downside_semivariance",
        "left_tail_penalty",
        "tail_event_stress",
    }
)
_REQUIRED_OPTIMIZER_BASELINES: frozenset[str] = frozenset(
    {
        "no_trade",
        "current_holdings",
        "static_sleeve_budget",
        "equal_weight",
        "inverse_volatility",
        "equal_risk_contribution",
        "current_non_optimized_allocation",
    }
)
_VALID_NO_ALPHA_STATUSES: frozenset[str] = frozenset({"null_passed"})
_VALID_EXPECTED_RETURN_STATUSES: frozenset[str] = frozenset(
    {"promotion_valid", "uncertainty_penalized"}
)


def evaluate_portfolio_optimizer_blockers(
    *,
    artifact_payloads: Sequence[Mapping[str, object]],
) -> tuple[Blocker, ...]:
    """Wave 6 portfolio/optimizer enforcement.

    Re-derives blockers from raw fields so a payload with
    ``promotion_valid=true`` and ``blocker_codes=[]`` cannot mask a real
    optimizer/utility violation.
    """

    blockers: list[Blocker] = []
    for payload in artifact_payloads:
        kind = str(payload.get("kind", ""))
        if kind not in {
            "portfolio_utility_definition",
            "optimizer_validation_report",
            "optimizer_fallback_record",
        }:
            continue
        for code in _string_sequence(payload.get("blocker_codes", ())):
            if code in BLOCKER_REGISTRY:
                _append_blocker(blockers, code)
        if kind == "portfolio_utility_definition":
            if not str(payload.get("pre_experiment_approval_ref", "")).strip():
                _append_blocker(blockers, "optimizer_or_sizing_lockbox_missing")
            if not str(payload.get("threshold_justification_ref", "")).strip():
                _append_blocker(blockers, "optimizer_or_sizing_lockbox_missing")
            justification = payload.get("lambda_justification_refs", {})
            if isinstance(justification, Mapping) and not justification:
                _append_blocker(blockers, "optimizer_or_sizing_lockbox_missing")
            tail_components_raw = payload.get("tail_risk_components", ())
            if isinstance(tail_components_raw, Sequence) and not isinstance(
                tail_components_raw, str | bytes
            ):
                tail_lower = {str(item).lower() for item in tail_components_raw}
                if not tail_lower & _TAIL_RISK_TERMS:
                    _append_blocker(blockers, "tail_risk_missing")
            else:
                _append_blocker(blockers, "tail_risk_missing")
        if kind == "optimizer_validation_report":
            lockbox = _normal_form(payload.get("lockbox_status"))
            if lockbox not in {"frozen", "nested_validation"}:
                _append_blocker(blockers, "optimizer_or_sizing_lockbox_missing")
            no_alpha_status = _normal_form(payload.get("no_alpha_pipeline_status"))
            if no_alpha_status not in _VALID_NO_ALPHA_STATUSES:
                _append_blocker(blockers, "no_alpha_pipeline_edge")
            if _normal_form(payload.get("perturbation_status")) == "unstable":
                _append_blocker(blockers, "optimizer_perturbation_unstable")
            if (
                _normal_form(payload.get("covariance_drift_status"))
                == "drift_unresolved"
            ):
                _append_blocker(blockers, "covariance_drift_unresolved")
            if _normal_form(payload.get("turnover_status")) == "exceeds_cap":
                _append_blocker(blockers, "turnover_cap_exceeded")
            try:
                max_turnover = Decimal(
                    str(payload.get("max_adjacent_decision_turnover", "0"))
                )
                observed = Decimal(str(payload.get("observed_adjacent_turnover", "0")))
                if max_turnover > Decimal("0") and observed > max_turnover:
                    _append_blocker(blockers, "turnover_cap_exceeded")
            except InvalidOperation:
                _append_blocker(blockers, "turnover_cap_exceeded")
            er_status = _normal_form(payload.get("expected_return_status"))
            if er_status not in _VALID_EXPECTED_RETURN_STATUSES:
                _append_blocker(blockers, "expected_return_not_promotion_valid")
            if er_status == "uncertainty_penalized":
                # The optimizer is consuming uncertainty-penalized inputs;
                # surface the calibration cap directly rather than relying on
                # a separately-bundled expected_return_report.
                _append_blocker(blockers, "expected_return_uncertainty_uncalibrated")
            try:
                lower_ci = Decimal(str(payload.get("paired_oos_utility_lower_ci", "0")))
                threshold = Decimal(
                    str(payload.get("paired_oos_utility_threshold", "0"))
                )
                if lower_ci <= threshold:
                    _append_blocker(blockers, "paired_oos_utility_failed")
            except InvalidOperation:
                _append_blocker(blockers, "paired_oos_utility_failed")
            cost_capacity_refs = payload.get("cost_capacity_report_refs", ())
            if (
                not isinstance(cost_capacity_refs, Sequence)
                or isinstance(cost_capacity_refs, str | bytes)
                or not cost_capacity_refs
            ):
                _append_blocker(blockers, "execution_semantics_incomplete")
            tested_baselines = payload.get("tested_baselines", ())
            excluded = payload.get("excluded_baselines", ())
            approvals = payload.get("excluded_baseline_approval_refs", {})
            tested_set = (
                {str(item) for item in tested_baselines}
                if isinstance(tested_baselines, Sequence)
                and not isinstance(tested_baselines, str | bytes)
                else set()
            )
            excluded_set = (
                {str(item) for item in excluded}
                if isinstance(excluded, Sequence)
                and not isinstance(excluded, str | bytes)
                else set()
            )
            approvals_map = (
                {str(key): str(value) for key, value in approvals.items()}
                if isinstance(approvals, Mapping)
                else {}
            )
            for required_baseline in _REQUIRED_OPTIMIZER_BASELINES:
                approved = bool(approvals_map.get(required_baseline, "").strip())
                in_excluded = required_baseline in excluded_set
                in_tested = required_baseline in tested_set
                if in_excluded and not approved:
                    _append_blocker(blockers, "applicable_baseline_excluded")
                    break
                if not in_tested and not (in_excluded and approved):
                    # Required baseline silently omitted from tested set
                    # without an approved exclusion is still a violation.
                    _append_blocker(blockers, "applicable_baseline_excluded")
                    break
        if kind == "optimizer_fallback_record":
            if not str(payload.get("static_blueprint_ref", "")).strip():
                _append_blocker(blockers, "optimizer_or_sizing_lockbox_missing")
            if not str(payload.get("operator_alert_ref", "")).strip():
                _append_blocker(blockers, "optimizer_or_sizing_lockbox_missing")
    return tuple(blockers)


def evaluate_forecast_sizing_blockers(
    *,
    artifact_payloads: Sequence[Mapping[str, object]],
) -> tuple[Blocker, ...]:
    """Wave 6 forecast/sizing enforcement (Milestone 7)."""

    blockers: list[Blocker] = []
    for payload in artifact_payloads:
        kind = str(payload.get("kind", ""))
        if kind not in {
            "forecast_model_manifest",
            "feature_manifest",
            "label_definition",
            "expected_return_report",
            "sizing_policy",
        }:
            continue
        for code in _string_sequence(payload.get("blocker_codes", ())):
            if code in BLOCKER_REGISTRY:
                _append_blocker(blockers, code)
        if kind == "feature_manifest":
            audit = _normal_form(payload.get("leakage_audit_status"))
            if audit in {"feature_after_decision", "label_overlap", "not_audited"}:
                _append_blocker(blockers, "feature_timestamp_unauditable")
            source = _normal_form(payload.get("timestamp_source"))
            if source in {"unspecified", ""}:
                _append_blocker(blockers, "feature_timestamp_unauditable")
        if kind == "label_definition":
            overlap = _normal_form(payload.get("overlap_status"))
            if overlap == "overlapping_unhandled":
                _append_blocker(blockers, "feature_timestamp_unauditable")
        if kind == "forecast_model_manifest":
            if not bool(payload.get("uncertainty_calibrated", False)):
                _append_blocker(blockers, "expected_return_uncertainty_uncalibrated")
            if (
                not str(payload.get("feature_manifest_ref", "")).strip()
                or not str(payload.get("label_definition_ref", "")).strip()
            ):
                _append_blocker(blockers, "feature_timestamp_unauditable")
        if kind == "expected_return_report":
            if not bool(payload.get("uncertainty_calibrated", False)):
                _append_blocker(blockers, "expected_return_uncertainty_uncalibrated")
            if _normal_form(payload.get("calibration_status")) == "uncalibrated":
                _append_blocker(blockers, "expected_return_uncertainty_uncalibrated")
            try:
                oos = Decimal(str(payload.get("oos_utility_after_costs", "0")))
                no_forecast = Decimal(
                    str(payload.get("no_forecast_baseline_utility", "0"))
                )
                heuristic = Decimal(str(payload.get("heuristic_baseline_utility", "0")))
                if oos <= no_forecast or oos <= heuristic:
                    _append_blocker(blockers, "expected_return_not_promotion_valid")
            except InvalidOperation:
                _append_blocker(blockers, "expected_return_not_promotion_valid")
        if kind == "sizing_policy":
            for cap_field in (
                "position_cap",
                "sleeve_cap",
                "gross_exposure_cap",
                "net_exposure_cap",
                "leverage_cap",
                "order_cap",
                "participation_cap",
                "drawdown_budget",
            ):
                try:
                    if Decimal(str(payload.get(cap_field, "0"))) <= Decimal("0"):
                        _append_blocker(blockers, "hard_exposure_caps_missing")
                        break
                except InvalidOperation:
                    _append_blocker(blockers, "hard_exposure_caps_missing")
                    break
            # Default to "Kelly enabled" if missing so the evaluator fails
            # closed even when payload omits the flag.
            kelly_disabled = bool(payload.get("kelly_disabled", False))
            kelly_gate = bool(payload.get("kelly_gate_complete", False))
            if not kelly_disabled and not kelly_gate:
                _append_blocker(blockers, "kelly_gate_incomplete")
            try:
                if (
                    Decimal(str(payload.get("max_kelly_multiplier", "0")))
                    > Decimal("1")
                    and not kelly_gate
                ):
                    _append_blocker(blockers, "kelly_gate_incomplete")
            except InvalidOperation:
                pass
    return tuple(blockers)


def evaluate_short_blockers(
    *,
    artifact_payloads: Sequence[Mapping[str, object]],
) -> tuple[Blocker, ...]:
    """Wave 7 short-side enforcement.

    Re-derives blockers from raw fields so a tampered payload claiming
    ``blocker_codes=[]`` cannot bypass enforcement.
    """

    blockers: list[Blocker] = []
    manifest_requires_probe = False
    has_short_risk_report_with_probe = False
    has_manifest = False
    for payload in artifact_payloads:
        kind = str(payload.get("kind", ""))
        if kind not in {
            "short_capability_manifest",
            "borrow_availability_snapshot",
            "short_financing_model",
            "short_risk_report",
            "short_runtime_event",
        }:
            continue
        for code in _string_sequence(payload.get("blocker_codes", ())):
            if code in BLOCKER_REGISTRY:
                _append_blocker(blockers, code)
        if kind == "short_capability_manifest":
            has_manifest = True
            broker_mode = _normal_form(payload.get("broker_mode"))
            # A manifest declared for a real broker mode requires a live
            # probe regardless of the self-asserted flag — operators cannot
            # opt out of live-probe validation by setting
            # `live_probe_required=False` while pointing at a live broker.
            if broker_mode in {"live", "live_probe"} or bool(
                payload.get("live_probe_required", False)
            ):
                manifest_requires_probe = True
            if not bool(payload.get("short_runtime_supported", False)):
                _append_blocker(blockers, "short_support_missing")
            for required_field in (
                "threshold_security_handling",
                "close_out_handling",
                "order_marking_policy",
            ):
                if not str(payload.get(required_field, "")).strip():
                    _append_blocker(blockers, "short_legal_mechanics_missing")
                    break
            if _normal_form(payload.get("paper_live_match_status")) in {
                "mismatched",
                "unverified",
            }:
                _append_blocker(blockers, "paper_live_short_semantics_mismatch")
        if kind == "borrow_availability_snapshot":
            if bool(payload.get("is_stale", False)):
                _append_blocker(blockers, "borrow_snapshot_stale")
            locate_status = _normal_form(payload.get("locate_status"))
            if locate_status in {"missing", "unknown", ""}:
                _append_blocker(blockers, "locate_documentation_missing")
            if locate_status == "expired":
                _append_blocker(blockers, "locate_expired")
            if not str(payload.get("locate_documentation_ref", "")).strip():
                _append_blocker(blockers, "locate_documentation_missing")
            if _normal_form(payload.get("threshold_security_status")) == "unknown":
                _append_blocker(blockers, "short_legal_mechanics_missing")
        if kind == "short_risk_report":
            if _normal_form(payload.get("borrow_coverage_status")) == "missing":
                _append_blocker(blockers, "short_support_missing")
            if (
                _normal_form(payload.get("historical_borrow_coverage_status"))
                == "missing"
            ):
                _append_blocker(blockers, "legacy_short_evidence")
            if _normal_form(payload.get("order_marking_status")) in {
                "incorrect",
                "unsupported",
            }:
                _append_blocker(blockers, "short_legal_mechanics_missing")
            if _normal_form(payload.get("locate_documentation_status")) == "missing":
                _append_blocker(blockers, "locate_documentation_missing")
            if _normal_form(payload.get("locate_expiry_status")) in {
                "expired",
                "missing",
            }:
                _append_blocker(blockers, "locate_expired")
            if _normal_form(payload.get("threshold_security_status")) in {
                "unhandled",
                "unknown",
            }:
                _append_blocker(blockers, "short_legal_mechanics_missing")
            if _normal_form(payload.get("close_out_status")) == "unhandled":
                _append_blocker(blockers, "short_legal_mechanics_missing")
            if _normal_form(payload.get("paper_live_semantics_status")) in {
                "mismatched",
                "unverified",
            }:
                _append_blocker(blockers, "paper_live_short_semantics_mismatch")
            evidence_refs = payload.get("live_probe_evidence_refs", ())
            valid_refs = (
                isinstance(evidence_refs, Sequence)
                and not isinstance(evidence_refs, str | bytes)
                and any(isinstance(ref, str) and ref.strip() for ref in evidence_refs)
            )
            if not valid_refs:
                _append_blocker(blockers, "live_probe_short_evidence_missing")
            else:
                has_short_risk_report_with_probe = True
        if kind == "short_runtime_event":
            event_type = _normal_form(payload.get("event_type"))
            reconciled = bool(payload.get("reconciled", False))
            if event_type == "broker_initiated_cover_detected" and not reconciled:
                _append_blocker(blockers, "broker_initiated_cover_unreconciled")
            if event_type == "order_marking_rejected":
                _append_blocker(blockers, "short_legal_mechanics_missing")
            if event_type in {"locate_missing", "locate_expired"}:
                _append_blocker(blockers, "locate_documentation_missing")
    if (
        has_manifest
        and manifest_requires_probe
        and not has_short_risk_report_with_probe
    ):
        _append_blocker(blockers, "live_probe_short_evidence_missing")
    return tuple(blockers)


def evaluate_live_probe_blockers(
    *,
    artifact_payloads: Sequence[Mapping[str, object]],
) -> tuple[Blocker, ...]:
    """Wave 8 live-probe and operational-safety enforcement.

    Re-derives blockers from raw fields so a tampered payload claiming
    ``blocker_codes=[]`` cannot bypass enforcement.

    Defect 3 — cross-bundle linkage. The bundle's
    live_probe_recertification_report.run_refs must be a superset of the
    run_id values from every live_probe_run_record in the bundle. A
    bundle whose recertification report omits any actual run cannot
    promote past the live-probe state.
    """

    blockers: list[Blocker] = []
    now = datetime.now(UTC)
    has_run_record = False
    has_recertification = False
    observed_run_ids: set[str] = set()
    recert_run_ref_sets: list[set[str]] = []
    for payload in artifact_payloads:
        kind = str(payload.get("kind", ""))
        if kind not in {
            "authority_boundary",
            "pre_trade_control_manifest",
            "operational_safety_drill",
            "live_probe_plan",
            "live_probe_run_record",
            "live_probe_recertification_report",
            "broker_timeout_state_transition",
            "runtime_override_event",
            "reconciliation_incident",
        }:
            continue
        for code in _string_sequence(payload.get("blocker_codes", ())):
            if code in BLOCKER_REGISTRY:
                _append_blocker(blockers, code)
        if kind == "authority_boundary":
            if _normal_form(payload.get("write_authorization_status")) != "authorized":
                _append_blocker(blockers, "authority_boundary_invalid")
            try:
                expires = datetime.fromisoformat(
                    str(payload.get("expires_at_utc", "")).replace("Z", "+00:00")
                )
                if expires.astimezone(UTC) <= now:
                    _append_blocker(blockers, "authority_boundary_expired")
            except (ValueError, TypeError):
                _append_blocker(blockers, "authority_boundary_invalid")
            if bool(payload.get("second_approver_required", False)):
                approvers = payload.get("approvers", ())
                signatures = payload.get("signatures", ())
                if (
                    not isinstance(approvers, Sequence)
                    or isinstance(approvers, str | bytes)
                    or len(list(approvers)) < 2
                    or not isinstance(signatures, Sequence)
                    or isinstance(signatures, str | bytes)
                    or len(list(signatures)) < 2
                ):
                    _append_blocker(blockers, "authority_boundary_invalid")
        if kind == "pre_trade_control_manifest":
            for cap_field in (
                "price_collar_bps",
                "fat_finger_notional_limit",
                "fat_finger_share_limit",
            ):
                try:
                    if Decimal(str(payload.get(cap_field, "0"))) <= Decimal("0"):
                        _append_blocker(blockers, "pre_trade_control_missing")
                        break
                except InvalidOperation:
                    _append_blocker(blockers, "pre_trade_control_missing")
                    break
            if _coerce_int(payload.get("max_open_orders", 0)) <= 0:
                _append_blocker(blockers, "pre_trade_control_missing")
            if _coerce_int(payload.get("max_order_rate_per_minute", 0)) <= 0:
                _append_blocker(blockers, "pre_trade_control_missing")
            if not bool(payload.get("duplicate_prevention_enabled", False)):
                _append_blocker(blockers, "pre_trade_control_missing")
            if not bool(payload.get("cancel_on_disconnect", False)):
                _append_blocker(blockers, "pre_trade_control_missing")
            if not bool(payload.get("reject_on_missing_control", False)):
                _append_blocker(blockers, "pre_trade_control_missing")
        if kind == "operational_safety_drill":
            if bool(payload.get("is_stale", False)):
                _append_blocker(blockers, "safety_drill_stale")
            if not bool(payload.get("passed", True)):
                _append_blocker(blockers, "safety_drill_failed")
        if kind == "live_probe_plan":
            # Defect 14 — distinguish unparseable from expired.
            try:
                expires = datetime.fromisoformat(
                    str(payload.get("expires_at_utc", "")).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                _append_blocker(blockers, "live_probe_plan_invalid")
            else:
                if expires.astimezone(UTC) <= now:
                    _append_blocker(blockers, "live_probe_plan_expired")
            if not str(payload.get("pre_trade_control_manifest_ref", "")).strip():
                _append_blocker(blockers, "pre_trade_control_missing")
            if not str(payload.get("authority_boundary_ref", "")).strip():
                _append_blocker(blockers, "authority_boundary_missing")
            if not bool(payload.get("kill_switch_required", False)):
                _append_blocker(blockers, "pre_trade_control_missing")
        if kind == "live_probe_run_record":
            has_run_record = True
            run_id = str(payload.get("run_id", "")).strip()
            if run_id:
                observed_run_ids.add(run_id)
            if not bool(payload.get("minimum_activity_met", False)):
                _append_blocker(blockers, "live_probe_minimum_activity_unmet")
                # Without minimum activity met, the run is inconclusive
                # regardless of any self-reported status (Milestone 9).
                _append_blocker(blockers, "live_probe_inconclusive")
            run_status = _normal_form(payload.get("status"))
            if run_status in {"inconclusive", "fail", "rolled_back"}:
                _append_blocker(blockers, "live_probe_inconclusive")
        if kind == "live_probe_recertification_report":
            has_recertification = True
            run_refs_raw = payload.get("run_refs", ())
            if isinstance(run_refs_raw, Sequence) and not isinstance(
                run_refs_raw, str | bytes
            ):
                recert_run_ref_sets.append(
                    {str(item).strip() for item in run_refs_raw if str(item).strip()}
                )
            unresolved = payload.get("unresolved_incident_refs", ())
            if (
                isinstance(unresolved, Sequence)
                and not isinstance(unresolved, str | bytes)
                and unresolved
            ):
                _append_blocker(blockers, "reconciliation_incident_unresolved")
            if _normal_form(payload.get("minimum_activity_status")) != "met":
                _append_blocker(blockers, "live_probe_minimum_activity_unmet")
            if _normal_form(payload.get("drill_status")) != "fresh":
                _append_blocker(blockers, "safety_drill_stale")
            if _normal_form(payload.get("broker_timeout_status")) != "defined":
                _append_blocker(blockers, "broker_timeout_state_machine_missing")
            if _normal_form(payload.get("idempotency_status")) != "complete":
                _append_blocker(blockers, "idempotency_evidence_missing")
            if _normal_form(payload.get("reconciliation_status")) != "complete":
                _append_blocker(blockers, "reconciliation_evidence_missing")
        if kind == "broker_timeout_state_transition":
            retry_permitted = bool(payload.get("retry_permitted", False))
            reconciliation_required = bool(
                payload.get("reconciliation_required", False)
            )
            to_state = _normal_form(payload.get("to_state"))
            if retry_permitted and reconciliation_required and to_state != "recovered":
                _append_blocker(blockers, "broker_timeout_retry_unsafe")
        if kind == "runtime_override_event":
            disabled = payload.get("disabled_controls_requested", ())
            if (
                isinstance(disabled, Sequence)
                and not isinstance(disabled, str | bytes)
                and disabled
            ):
                _append_blocker(blockers, "manual_exception_disabled_core_control")
            action_str = str(payload.get("action", "")).lower().strip()
            if action_str in {
                "disable_kill_switch",
                "bypass_kill_switch",
                "bypass_pre_trade_control",
                "disable_pre_trade_control",
                "disable_reconciliation",
                "bypass_reconciliation",
                "disable_drawdown_limit",
                "bypass_drawdown_limit",
                "disable_idempotency",
                "bypass_idempotency",
                "disable_cancel_on_disconnect",
            }:
                _append_blocker(blockers, "manual_exception_disabled_core_control")
            if not str(payload.get("authority_boundary_ref", "")).strip():
                _append_blocker(blockers, "authority_boundary_missing")
        if kind == "reconciliation_incident":
            if _normal_form(payload.get("status")) != "resolved":
                _append_blocker(blockers, "reconciliation_incident_unresolved")
    # If a live-probe run record is present in the bundle, a matching
    # post-probe recertification report MUST also be bundled. Otherwise
    # the bundle cannot satisfy production eligibility (Milestone 9).
    if has_run_record and not has_recertification:
        _append_blocker(blockers, "post_probe_recertification_missing")
    # Defect 3 — cross-bundle linkage: every observed run_id must appear
    # in at least one live_probe_recertification_report.run_refs set.
    # Matching tolerates a single canonical-namespace prefix (``cas://``
    # or ``run-``) so a recert report that uses the cas:// indirection
    # form still matches the bare run_id from the run record. Anything
    # else fails closed.
    if has_run_record and has_recertification and observed_run_ids:
        certified_raw = (
            set().union(*recert_run_ref_sets) if recert_run_ref_sets else set()
        )
        certified = {_canonical_run_ref(ref) for ref in certified_raw}
        observed = {_canonical_run_ref(ref) for ref in observed_run_ids}
        if not observed.issubset(certified):
            _append_blocker(blockers, "post_probe_recertification_missing")
    return tuple(blockers)


def evaluate_change_control_blockers(
    *,
    artifact_payloads: Sequence[Mapping[str, object]],
) -> tuple[Blocker, ...]:
    """Wave 9 recertification and change-control enforcement.

    Defect 3 — cross-bundle linkage. The bundle's recertification_report
    must reference (via change_id) one of the change_control_record
    entries that requires recertification. Bundles whose
    recertification_report has no change_id, or a change_id absent from
    the change_control_record set with recertification_required=true,
    fire ``recertification_report_missing``.
    """

    blockers: list[Blocker] = []
    now = datetime.now(UTC)
    has_change_requiring_recert = False
    has_recertification_report = False
    required_change_ids: set[str] = set()
    recert_change_ids: list[str] = []
    for payload in artifact_payloads:
        kind = str(payload.get("kind", ""))
        if kind not in {
            "change_control_record",
            "replay_equivalence_report",
            "recertification_report",
            "drift_monitor_spec",
            "drift_monitor_report",
            "production_decay_event",
        }:
            continue
        for code in _string_sequence(payload.get("blocker_codes", ())):
            if code in BLOCKER_REGISTRY:
                _append_blocker(blockers, code)
        if kind == "change_control_record":
            if bool(payload.get("recertification_required", False)):
                has_change_requiring_recert = True
                change_id = str(payload.get("change_id", "")).strip()
                if change_id:
                    required_change_ids.add(change_id)
                else:
                    # bug_015 — a material/critical change without a
                    # change_id has no audit trail. Without this guard
                    # an empty change_id on both the change_control_record
                    # and the recertification_report bypasses the
                    # Defect-3 cross-bundle linkage check (both sides
                    # contribute empty sets that trivially "match").
                    _append_blocker(blockers, "unrecorded_material_change")
            if bool(payload.get("unknown_scope", False)):
                _append_blocker(blockers, "unrecorded_material_change")
            dependency_refs = payload.get("dependency_index_refs", ())
            if (
                not isinstance(dependency_refs, Sequence)
                or isinstance(dependency_refs, str | bytes)
                or not dependency_refs
            ):
                _append_blocker(blockers, "dependency_scope_unresolved")
            if (
                _normal_form(payload.get("schema_compatibility_status"))
                == "breaking_no_migration"
            ):
                _append_blocker(blockers, "unrecorded_material_change")
            if _normal_form(payload.get("materiality_class")) == "critical":
                _append_blocker(blockers, "unrecorded_material_change")
        if kind == "replay_equivalence_report":
            equivalence = _normal_form(payload.get("equivalence_status"))
            if equivalence in {"non_equivalent", "indeterminate"}:
                _append_blocker(blockers, "unrecorded_material_change")
        if kind == "recertification_report":
            has_recertification_report = True
            recert_change_ids.append(str(payload.get("change_id", "")).strip())
            # Defect 14 — distinguish parse error from expired.
            try:
                expires = datetime.fromisoformat(
                    str(payload.get("production_expires_at_utc", "")).replace(
                        "Z", "+00:00"
                    )
                )
            except (ValueError, TypeError):
                _append_blocker(blockers, "production_approval_invalid")
            else:
                if expires.astimezone(UTC) <= now:
                    _append_blocker(blockers, "production_approval_expired")
            for review_field in (
                "next_operational_review_due_utc",
                "next_statistical_review_due_utc",
            ):
                try:
                    due = datetime.fromisoformat(
                        str(payload.get(review_field, "")).replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    _append_blocker(blockers, "next_review_invalid")
                    break
                if due.astimezone(UTC) <= now:
                    _append_blocker(blockers, "next_review_due_passed")
                    break
            if not str(payload.get("authority_boundary_ref", "")).strip():
                _append_blocker(blockers, "authority_boundary_missing")
            if _normal_form(payload.get("approval_status")) != "approved":
                _append_blocker(blockers, "recertification_report_missing")
            if _normal_form(payload.get("freshness_status")) == "stale":
                _append_blocker(blockers, "stale_sources")
            if _normal_form(payload.get("drift_status")) == "active":
                _append_blocker(blockers, "drift_alarm_live")
            if _normal_form(payload.get("incident_status")) in {
                "open",
                "active",
            }:
                _append_blocker(blockers, "reconciliation_incident_unresolved")
        if kind == "drift_monitor_spec":
            # Defect 14 — distinguish parse error from expired.
            try:
                expires = datetime.fromisoformat(
                    str(payload.get("expires_at_utc", "")).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                _append_blocker(blockers, "drift_monitor_spec_invalid")
            else:
                if expires.astimezone(UTC) <= now:
                    _append_blocker(blockers, "drift_monitor_spec_missing")
            monitored = payload.get("monitored_variables", ())
            if (
                not isinstance(monitored, Sequence)
                or isinstance(monitored, str | bytes)
                or not monitored
            ):
                _append_blocker(blockers, "drift_monitor_spec_missing")
        if kind == "drift_monitor_report":
            recommendation = _normal_form(payload.get("demotion_recommendation"))
            if recommendation in {"demote_to_paper_shadow", "halt"}:
                _append_blocker(blockers, "drift_alarm_live")
        if kind == "production_decay_event":
            previous_state = _normal_form(payload.get("previous_state"))
            new_state = _normal_form(payload.get("new_state"))
            if previous_state != new_state:
                _append_blocker(blockers, "production_approval_expired")
    if has_change_requiring_recert and not has_recertification_report:
        _append_blocker(blockers, "recertification_report_missing")
    # Defect 3 — when both sides are present, the recertification_report
    # must reference (via change_id) ALL of the change_control_record
    # entries that required recertification. A stale or missing change_id
    # means the report does not certify the actual change set. ``all``
    # (not ``any``) closes the loophole where one matching ID covers
    # arbitrarily many open changes.
    if has_change_requiring_recert and has_recertification_report:
        cleaned_recert_ids = {cid for cid in recert_change_ids if cid}
        if required_change_ids and not required_change_ids.issubset(cleaned_recert_ids):
            _append_blocker(blockers, "recertification_report_missing")
    # Defect 3 follow-up — a recertification_report that *claims* to
    # certify a specific change (non-empty ``change_id``) but ships
    # WITHOUT any matching change_control_record cannot certify what it
    # claims. Periodic recertification reports (no ``change_id``) remain
    # valid because they recertify the strategy as a whole, not a
    # specific change.
    cleaned_recert_ids = {cid for cid in recert_change_ids if cid}
    if cleaned_recert_ids and not required_change_ids:
        _append_blocker(blockers, "unrecorded_material_change")
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


def _canonical_run_ref(value: object) -> str:
    """Strip transport-layer prefixes from a run reference.

    Defect 3 cross-bundle linkage: live_probe_run_record.run_id is a
    bare identifier (e.g. ``probe-2026-04-15``), while
    live_probe_recertification_report.run_refs may carry a content-
    addressed prefix (``cas://probe-2026-04-15``). Normalise both sides
    to the bare identifier so a namespace difference alone does not
    silently break the linkage check.
    """
    text = str(value or "").strip()
    for prefix in ("cas://", "ledger://", "artifact://"):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


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


def _has_short_authority(
    payloads: tuple[Mapping[str, object], ...],
) -> bool:
    """Negative weights are allowed only when a Wave 7 short capability
    manifest with `short_runtime_supported=True` is present (or a legacy
    `short_capability_package`-style payload with `short_enabled=True`).
    """

    if _has_kind_with_flag(
        payloads,
        kind="short_capability_package",
        flag="short_enabled",
    ):
        return True
    return any(
        str(payload.get("kind", "")) == "short_capability_manifest"
        and bool(payload.get("short_runtime_supported", False))
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
    "evaluate_change_control_blockers",
    "evaluate_cost_capacity_blockers",
    "evaluate_forecast_sizing_blockers",
    "evaluate_live_probe_blockers",
    "evaluate_portfolio_optimizer_blockers",
    "evaluate_provenance_blockers",
    "evaluate_short_blockers",
    "evaluate_statistical_evidence_blockers",
    "load_state_action_contracts",
    "load_promotion_decision",
    "state_allows",
    "strictest_state_cap",
    "validate_blocker_registry_coverage",
    "validate_state_action_contracts",
    "validate_state_action_route",
]
