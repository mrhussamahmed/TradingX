from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_PATH = (
    REPO_ROOT
    / "docs/superpowers/plans/"
    "2026-04-26-tradingx-quant-hardening-wave0-review-handoff.md"
)


CURRENT_BLOCKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("missing_requirements", ("src/tradingx/controlplane/projections.py",)),
    ("outbox_dedupe_constraint_missing", ("src/tradingx/controlplane/projections.py",)),
    ("missing_sources", ("src/tradingx/controlplane/projections.py",)),
    ("initial_import_incomplete", ("src/tradingx/controlplane/projections.py",)),
    ("write_path_inactive", ("src/tradingx/controlplane/projections.py",)),
    ("unprojected_sources", ("src/tradingx/controlplane/projections.py",)),
    ("stale_sources", ("src/tradingx/controlplane/projections.py",)),
    ("lagging_sources", ("src/tradingx/controlplane/projections.py",)),
    ("not_ready_sources", ("src/tradingx/controlplane/projections.py",)),
    ("operator_hold", ("tests/unit/test_controlplane_repository_contracts.py",)),
    ("requested_mode_unknown", ("src/tradingx/controlplane/projectors.py",)),
    ("dry_run_enabled", ("src/tradingx/config.py",)),
    ("live_enable_evidence_missing", ("src/tradingx/controlplane/projectors.py",)),
    ("manual_kill_switch_active", ("src/tradingx/config.py",)),
    ("market_data_degraded", ("src/tradingx/controlplane/projectors.py",)),
    ("insufficient_bars", ("src/tradingx/historical.py",)),
    ("cpcv_insufficient_history", ("src/tradingx/validation.py",)),
    ("halt_by_operator", ("src/tradingx/types.py",)),
    ("drift_alarm_live", ("src/tradingx/types.py",)),
    ("sleeve_sharpe_below_threshold_6m", ("src/tradingx/types.py",)),
    ("regime_stressed", ("src/tradingx/types.py",)),
    ("regime_stressed_liquidate", ("src/tradingx/sleeves/regime_gate.py",)),
    ("insufficient_history", ("src/tradingx/types.py",)),
    ("broker_mode_not_live", ("src/tradingx/config.py",)),
    ("missing_live_credentials", ("src/tradingx/config.py",)),
    ("config_layer_disabled", ("src/tradingx/config.py",)),
    ("env_layer_disabled", ("src/tradingx/config.py",)),
    ("code_layer_disabled", ("src/tradingx/config.py",)),
    ("web_write_signing_unconfigured", ("src/tradingx/config.py",)),
    ("operator_signoff_missing", ("src/tradingx/web/app.py",)),
    ("gate4_checklist_missing", ("src/tradingx/web/app.py",)),
    ("non_positive_quantity", ("src/tradingx/risk.py",)),
    ("invalid_symbol", ("src/tradingx/risk.py",)),
    ("live_mode_disabled", ("src/tradingx/risk.py",)),
    ("liquidity_filter", ("src/tradingx/risk.py",)),
    ("price_floor", ("src/tradingx/risk.py", "src/tradingx/opportunity.py")),
    ("single_symbol_concentration", ("src/tradingx/risk.py",)),
    ("intraday_margin", ("src/tradingx/risk.py",)),
    ("stale_market_data", ("src/tradingx/risk.py",)),
    ("stale_broker_state", ("src/tradingx/risk.py",)),
    ("kill_switch", ("src/tradingx/risk.py",)),
    ("operator_halt", ("src/tradingx/controller.py",)),
    ("outside_regular_hours", ("src/tradingx/controller.py", "src/tradingx/policy.py")),
    ("insufficient_buying_power", ("src/tradingx/execution.py",)),
    ("restricted_symbol", ("src/tradingx/execution.py",)),
    ("symbol_halted", ("src/tradingx/execution.py",)),
    ("after_hours", ("src/tradingx/execution.py",)),
    ("market_closed", ("src/tradingx/execution.py", "src/tradingx/service.py")),
    ("malformed_payload", ("src/tradingx/execution.py",)),
    ("broker_rejected", ("src/tradingx/execution.py",)),
    ("kill_switch_active", ("src/tradingx/policy.py",)),
    ("daily_drawdown_halt_sticky", ("src/tradingx/policy.py",)),
    ("daily_drawdown_halt", ("src/tradingx/policy.py",)),
    ("close_window_entry_blocked", ("src/tradingx/policy.py",)),
    ("stale_quote", ("src/tradingx/policy.py",)),
    ("spread_absolute_cap", ("src/tradingx/policy.py",)),
    ("spread_relative_cap", ("src/tradingx/policy.py",)),
    ("daily_entry_cap_reached", ("src/tradingx/policy.py",)),
    ("per_symbol_entry_cap_reached", ("src/tradingx/policy.py",)),
    ("max_concurrent_positions_reached", ("src/tradingx/policy.py",)),
    ("same_session_reentry_cooldown", ("src/tradingx/policy.py",)),
    ("total_deployed_cap_reached", ("src/tradingx/policy.py",)),
)

ROADMAP_BLOCKERS: tuple[tuple[str, str], ...] = (
    ("authority_artifact_invalid", "disabled"),
    ("ledger_key_worm_controls_missing", "disabled"),
    ("state_action_contract_missing", "disabled"),
    ("replay_path_missing", "research_only"),
    ("tax_account_financing_unspecified", "paper_shadow"),
    ("after_tax_edge_missing_for_taxable_account", "paper_trading"),
    ("jurisdiction_account_use_unknown", "paper_trading"),
    ("external_capital_compliance_unknown", "disabled"),
    ("utility_definition_missing", "research_only"),
    ("strategy_materiality_policy_missing", "paper_shadow"),
    ("lower_bound_net_edge_undefined", "research_only"),
    ("net_edge_lower_bound_below_threshold", "research_only"),
    ("trial_lineage_contaminated", "research_only"),
    ("trial_universe_incomplete", "paper_shadow"),
    ("dsr_pbo_inputs_incomplete", "paper_shadow"),
    ("point_in_time_data_incomplete", "research_only"),
    ("execution_semantics_incomplete", "paper_shadow"),
    ("execution_sample_power_missing", "paper_shadow"),
    ("capacity_lower_bound_missing", "paper_shadow"),
    ("live_sample_requirement_unmet", "tiny_live_probe"),
    ("pre_trade_control_missing", "paper_trading"),
    ("short_legal_mechanics_missing", "research_only"),
    ("instrument_package_missing", "research_only"),
    ("optimizer_or_sizing_lockbox_missing", "paper_shadow"),
    ("drift_monitor_spec_missing", "paper_shadow"),
    ("capacity_extrapolation_risk", "paper_shadow"),
    ("unsupported_side", "research_only"),
    ("short_support_missing", "research_only"),
    ("pending_threshold", "paper_shadow"),
    ("legacy_statistical_evidence", "paper_shadow"),
    ("unsupported_cost_bucket", "paper_shadow"),
    ("unrecorded_material_change", "paper_shadow"),
    ("dependency_scope_unresolved", "paper_shadow"),
)

METRIC_SURFACES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("`gate-report` CLI", "src/tradingx/__main__.py", ("gate-report",)),
    ("build_gate_report", "src/tradingx/validation.py", ("build_gate_report",)),
    (
        "GateValidationController.generate_gate_report",
        "src/tradingx/controller.py",
        ("generate_gate_report",),
    ),
    (
        "Gate report web action",
        "src/tradingx/web/app.py",
        ("/api/actions/gate-report",),
    ),
    ("Web read models", "src/tradingx/web/readmodels.py", ("recommendations",)),
    ("Gate decision brief/reporting", "src/tradingx/reporting.py", ("decision",)),
    ("evaluate_candidate", "src/tradingx/evaluation.py", ("recommendation", "sharpe")),
    (
        "run_buy_and_hold_smoke_backtest",
        "src/tradingx/backtest.py",
        ("cagr", "sharpe_ratio", "max_drawdown"),
    ),
    ("scripts/run_backtest.py", "scripts/run_backtest.py", ("print(json.dumps",)),
    (
        "scripts/compare_vol_forecasts.py",
        "scripts/compare_vol_forecasts.py",
        ("forecast_metrics", "backtest_metrics", "write_text", "print(json.dumps"),
    ),
    ("StructuredRuntimeLogger.log", "src/tradingx/runtime_logging.py", ("log",)),
    ("Filesystem evidence", "src/tradingx/persistence/__init__.py", ("write_",)),
)


def _read_repo_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _handoff_rows_by_code(handoff: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in handoff.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        match = re.fullmatch(r"`([^`]+)`", cells[0])
        if match:
            rows[match.group(1)] = cells
    return rows


def _source_contains(code: str, paths: tuple[str, ...]) -> bool:
    return any(code in _read_repo_text(path) for path in paths)


def _check_blocker_rows(
    *,
    handoff_rows: dict[str, list[str]],
    failures: list[str],
) -> int:
    checked = 0
    for code, paths in CURRENT_BLOCKERS:
        checked += 1
        if not _source_contains(code, paths):
            failures.append(f"{code}: source literal not found in {paths!r}")
        row = handoff_rows.get(code)
        if row is None:
            failures.append(f"{code}: missing handoff table row")
            continue
        if len(row) < 6 or not row[4] or not row[5]:
            failures.append(f"{code}: missing cap or registry treatment")

    roadmap_text = _read_repo_text(
        "docs/roadmap/tradingx_quant_hardening_execution_plan.md"
    )
    for code, expected_cap in ROADMAP_BLOCKERS:
        checked += 1
        if code not in roadmap_text:
            failures.append(f"{code}: roadmap literal not found")
        row = handoff_rows.get(code)
        if row is None:
            failures.append(f"{code}: missing roadmap handoff table row")
            continue
        if len(row) < 6:
            failures.append(f"{code}: malformed roadmap handoff row")
            continue
        if row[4] != f"`{expected_cap}`":
            failures.append(
                f"{code}: expected cap `{expected_cap}`, observed {row[4]!r}"
            )
        if not row[5]:
            failures.append(f"{code}: missing registry treatment")
    return checked


def _check_metric_surfaces(*, handoff: str, failures: list[str]) -> int:
    checked = 0
    for surface, relative_path, source_tokens in METRIC_SURFACES:
        checked += 1
        if surface not in handoff:
            failures.append(f"{surface}: missing handoff surface row")
        source = _read_repo_text(relative_path)
        missing_tokens = tuple(token for token in source_tokens if token not in source)
        if missing_tokens:
            failures.append(
                f"{surface}: missing source tokens {missing_tokens!r} "
                f"in {relative_path}"
            )
    return checked


def _build_report() -> tuple[bool, str]:
    handoff = HANDOFF_PATH.read_text(encoding="utf-8")
    rows = _handoff_rows_by_code(handoff)
    failures: list[str] = []
    blocker_count = _check_blocker_rows(handoff_rows=rows, failures=failures)
    metric_count = _check_metric_surfaces(handoff=handoff, failures=failures)

    report_lines = [
        "Wave 0 inventory checker",
        f"handoff={HANDOFF_PATH.relative_to(REPO_ROOT)}",
        f"blocker_rows_checked={blocker_count}",
        f"metric_surfaces_checked={metric_count}",
    ]
    if failures:
        report_lines.append("status=FAIL")
        report_lines.extend(f"- {failure}" for failure in failures)
        return False, "\n".join(report_lines) + "\n"
    report_lines.append("status=PASS")
    return True, "\n".join(report_lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    passed, report = _build_report()
    print(report, end="")
    if args.output is not None:
        args.output.write_text(report, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
