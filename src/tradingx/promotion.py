from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from tradingx.authority import (
    AuthorityLedger,
    AuthorityLedgerError,
    AuthorityLedgerRecord,
    FileContentAddressedStore,
    TrustRoot,
    TrustRootError,
    canonical_payload_hash,
    validate_quant_artifact,
    verify_approval_signature,
)

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
    ("ledger_key_worm_controls_missing", PromotionState.DISABLED),
    ("state_action_contract_missing", PromotionState.DISABLED),
    ("replay_path_missing", PromotionState.RESEARCH_ONLY),
    ("tax_account_financing_unspecified", PromotionState.PAPER_SHADOW),
    ("after_tax_edge_missing_for_taxable_account", PromotionState.PAPER_TRADING),
    ("jurisdiction_account_use_unknown", PromotionState.PAPER_TRADING),
    ("external_capital_compliance_unknown", PromotionState.DISABLED),
    ("utility_definition_missing", PromotionState.RESEARCH_ONLY),
    ("strategy_materiality_policy_missing", PromotionState.PAPER_SHADOW),
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
                raise ValueError(
                    f"{code} has synthetic runtime enforcement coverage"
                )
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

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(blocker.code for blocker in self.blockers)

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
    requested_state = _state_from_value(
        str(payload.get("requested_state", "disabled"))
    )
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
    if trust_root.fixture_root and not _is_allowed_fixture_root(root):
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
        state_action_contracts=state_action_contracts,
        replay_missing=replay_missing,
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
    return PromotionDecision(
        strategy_id=strategy_id,
        requested_state=requested_state,
        max_state=max_state,
        blockers=blockers,
        artifact_refs=record.artifact_refs,
        ledger_sequence=record.sequence,
        ledger_hash=record.ledger_hash,
        state_action_contracts=state_action_contracts,
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
) -> None:
    if not approval_refs:
        raise AuthorityLedgerError("approval refs are required")
    for approval_ref in approval_refs:
        approval_payload = artifact_store.read_ref_uri(approval_ref)
        validate_quant_artifact(approval_payload, schema=_schema("approval_record"))
        if str(approval_payload.get("payload_hash", "")) != payload_hash:
            raise AuthorityLedgerError("approval payload hash mismatch")
        if str(approval_payload.get("scope", "")) != "promotion_decision":
            raise AuthorityLedgerError(
                "approval scope does not cover promotion_decision"
            )
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
            required_scope="promotion_decision",
            verified_at_utc=verified_at,
        )


def _evaluate_verified_decision_blockers(
    *,
    decision_payload: Mapping[str, object],
    artifact_payloads: tuple[Mapping[str, object], ...],
    state_action_contracts: dict[str, dict[str, object]] | None,
    replay_missing: bool,
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
        if not _has_valid_evidence_artifact(
            artifact_payloads,
            kind=required_kind,
            strategy_id=strategy_id,
        ):
            _append_blocker(blockers, blocker_code)
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
            "state_action_contract_missing: "
            f"{state.value} cannot allocate capital"
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
    "evaluate_promotion_manifest",
    "load_state_action_contracts",
    "load_promotion_decision",
    "state_allows",
    "strictest_state_cap",
    "validate_blocker_registry_coverage",
    "validate_state_action_contracts",
    "validate_state_action_route",
]
