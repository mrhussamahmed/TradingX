from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.trading.client import TradingClient

from tradingx.activation import LocalActivationGateway
from tradingx.alerts import build_gate_decision_alert
from tradingx.authority import validate_quant_artifact as _validate_quant_artifact
from tradingx.automation import build_default_market_day_automation_runner
from tradingx.benchmark_stack import build_default_benchmark_stack
from tradingx.config import TradingConfig
from tradingx.controller import (
    build_default_controller,
    build_default_gate_validation_controller,
    build_default_paper_trading_controller,
)
from tradingx.costs import (
    build_capacity_curve_report,
    build_cost_model_report,
    build_quote_quality_record,
)
from tradingx.data import (
    AlpacaRegularHoursCalendar,
    build_default_market_data_gateway,
    build_market_data_gateway_for_mode,
)
from tradingx.data_fingerprint import (
    build_dataset_manifest,
    compare_dataset_manifests,
    invalidate_evidence_from_restatement,
    load_json_object,
)
from tradingx.dry_run_report import build_dry_run_report, write_dry_run_report
from tradingx.experiments import (
    ExperimentLedger,
    build_trial_universe_manifest,
    resolve_metric_visibility_context,
)
from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.historical import HistoricalWarmupService
from tradingx.journal import SqliteOmsJournal
from tradingx.launcher import ControlCenterLaunchError, launch_control_center
from tradingx.live_enablement import (
    build_trading_client_for_mode,
    resolve_broker_mode,
)
from tradingx.opportunity import RuntimeOpportunityPlanner
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.process_lock import RuntimeLockError, runtime_process_lock
from tradingx.promotion import (
    PromotionState,
    build_artifact_promotion_decision_provider,
    evaluate_promotion_manifest,
)
from tradingx.replay_slippage import generate_replay_slippage_evidence
from tradingx.reporting import build_gate_decision_brief
from tradingx.risk_free import (
    DEFAULT_RISK_FREE_CACHE_PATH,
    build_default_risk_free_series,
    needs_risk_free_refresh,
    refresh_risk_free_cache,
)
from tradingx.runtime_portfolio import (
    RuntimePortfolioPlanner,
    UnsupportedRuntimePortfolioPlanError,
)
from tradingx.scheduler import build_default_market_day_scheduler
from tradingx.service import (
    build_default_paper_service,
    build_runtime_host_trading_service,
)
from tradingx.snapshots import ContentAddressedSnapshotStore
from tradingx.stats import build_statistical_validation_report
from tradingx.supervisor import build_default_operator_supervisor
from tradingx.types import BotRuntimeState
from tradingx.validation import (
    load_benchmark_stack_payload,
    write_benchmark_stack_payload,
)
from tradingx.web.app import run_web_app
from tradingx.week1_drills import run_week1_rehearsal
from tradingx.week1_readiness import build_gates_0001_status


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _serialize(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


_QUANT_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "quant"


def _load_quant_schema(name: str) -> dict[str, object]:
    payload = json.loads(
        (_QUANT_SCHEMA_ROOT / f"{name}.schema.json").read_text(encoding="utf-8")
    )
    if not isinstance(payload, dict):
        raise ValueError(f"{name} schema must be an object")
    return payload


def _format_promotion_summary(payload: dict[str, object]) -> str:
    blocker_summary = _format_code_list(payload.get("blocker_codes", []))
    mandate_summary = _format_code_list(payload.get("mandate_blocker_codes", []))
    statistical_summary = _format_code_list(
        payload.get("statistical_blocker_codes", [])
    )
    return "\n".join(
        (
            f"strategy_id: {payload['strategy_id']}",
            f"requested_state: {payload['requested_state']}",
            f"max_state: {payload['max_state']}",
            f"blocker_codes: {blocker_summary}",
            f"mandate_blocker_codes: {mandate_summary}",
            f"statistical_blocker_codes: {statistical_summary}",
        )
    )


def _format_code_list(value: object) -> str:
    if isinstance(value, list) and value:
        return ", ".join(str(item) for item in value)
    return "none"


def _runtime_lock_path(config: TradingConfig) -> Path:
    return config.runtime.data_root / "runtime.pid"


def _parse_iso_date(value: str) -> date:
    return datetime.fromisoformat(value).date()


def _run_with_runtime_lock(
    config: TradingConfig,
    action: Callable[[], tuple[int, Any]],
) -> int:
    try:
        with runtime_process_lock(_runtime_lock_path(config)):
            result = action()
    except RuntimeLockError as error:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 1
    exit_code, payload = result
    print(json.dumps(_serialize(payload), sort_keys=True))
    return exit_code


_WAVE_ARTIFACT_EVALUATORS: dict[str, str] = {
    # Wave 6 — portfolio / optimizer / forecast / sizing
    "portfolio-utility": "evaluate_portfolio_optimizer_blockers",
    "optimizer-validation": "evaluate_portfolio_optimizer_blockers",
    "optimizer-fallback": "evaluate_portfolio_optimizer_blockers",
    "forecast-manifest": "evaluate_forecast_sizing_blockers",
    "sizing-policy": "evaluate_forecast_sizing_blockers",
    # Wave 7 — short side
    "short-capability": "evaluate_short_blockers",
    "borrow-snapshot": "evaluate_short_blockers",
    "short-financing": "evaluate_short_blockers",
    "short-risk-report": "evaluate_short_blockers",
    # Wave 8 — live probe & operational safety
    "live-probe-plan": "evaluate_live_probe_blockers",
    "live-probe-run": "evaluate_live_probe_blockers",
    "live-probe-recertification": "evaluate_live_probe_blockers",
    # Wave 9 — change control / recertification
    "change-control": "evaluate_change_control_blockers",
    "replay-equivalence": "evaluate_change_control_blockers",
    "recertification": "evaluate_change_control_blockers",
    "drift-monitor-spec": "evaluate_change_control_blockers",
    # Wave 10 — legacy retirement
    "legacy-migration-report": "evaluate_change_control_blockers",
}


# Defect 8 hardening — subcommand -> set of allowed payload "kind"
# values. The dispatcher uses this to reject ``--ref`` paths whose
# payload kind does not match the subcommand. Earlier the dispatcher
# would silently emit no blockers if the wrong file was supplied.
_WAVE_ARTIFACT_ALLOWED_KINDS: dict[str, frozenset[str]] = {
    # Wave 6
    "portfolio-utility": frozenset({"portfolio_utility_definition"}),
    "optimizer-validation": frozenset({"optimizer_validation_report"}),
    "optimizer-fallback": frozenset({"optimizer_fallback_record"}),
    "forecast-manifest": frozenset(
        {"forecast_model_manifest", "feature_manifest", "label_definition"}
    ),
    "sizing-policy": frozenset({"sizing_policy", "expected_return_report"}),
    # Wave 7
    "short-capability": frozenset({"short_capability_manifest"}),
    "borrow-snapshot": frozenset({"borrow_availability_snapshot"}),
    "short-financing": frozenset({"short_financing_model"}),
    "short-risk-report": frozenset({"short_risk_report"}),
    # Wave 8
    "live-probe-plan": frozenset({"live_probe_plan"}),
    "live-probe-run": frozenset({"live_probe_run_record"}),
    "live-probe-recertification": frozenset(
        {"live_probe_recertification_report"}
    ),
    # Wave 9
    "change-control": frozenset({"change_control_record"}),
    "replay-equivalence": frozenset({"replay_equivalence_report"}),
    "recertification": frozenset({"recertification_report"}),
    "drift-monitor-spec": frozenset({"drift_monitor_spec"}),
    # Wave 10
    "legacy-migration-report": frozenset({"legacy_artifact_migration_report"}),
}


def _run_wave_artifact_check(command: str, refs: list[str]) -> int:
    """Defect 8 — generic Wave 4-10 artifact CLI dispatcher.

    Loads each ``--ref`` path as JSON, runs the matching evaluator from
    :mod:`tradingx.promotion`, prints a canonical JSON payload listing
    blocker codes per artifact, and returns ``1`` if any blockers were
    emitted (``0`` otherwise).
    """

    from tradingx import promotion as _promotion

    if not refs:
        print(
            json.dumps(
                {
                    "command": command,
                    "blocker_codes": ["missing_sources"],
                    "error": "at least one --ref must be supplied",
                },
                sort_keys=True,
            )
        )
        return 1
    payloads: list[dict[str, object]] = []
    for ref in refs:
        try:
            payload = json.loads(Path(ref).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {
                        "command": command,
                        "ref": ref,
                        "blocker_codes": ["authority_artifact_invalid"],
                        "error": str(exc),
                    },
                    sort_keys=True,
                )
            )
            return 1
        if not isinstance(payload, dict):
            print(
                json.dumps(
                    {
                        "command": command,
                        "ref": ref,
                        "blocker_codes": ["authority_artifact_invalid"],
                        "error": "payload is not a JSON object",
                    },
                    sort_keys=True,
                )
            )
            return 1
        # Defect 8 hardening — validate payload kind matches subcommand.
        # Without this check, ``forecast-manifest --ref short_risk.json``
        # would silently emit no blockers because the evaluator simply
        # ignores artifact kinds it does not recognise.
        allowed_kinds = _WAVE_ARTIFACT_ALLOWED_KINDS.get(command)
        payload_kind = str(payload.get("kind", "")).strip()
        if allowed_kinds is not None and payload_kind not in allowed_kinds:
            print(
                json.dumps(
                    {
                        "command": command,
                        "ref": ref,
                        "blocker_codes": ["authority_artifact_invalid"],
                        "error": (
                            f"payload kind {payload_kind!r} does not match "
                            f"subcommand {command!r}; expected one of "
                            f"{sorted(allowed_kinds)}"
                        ),
                    },
                    sort_keys=True,
                )
            )
            return 1
        payloads.append(payload)
    evaluator_name = _WAVE_ARTIFACT_EVALUATORS.get(command)
    if evaluator_name is None:
        print(
            json.dumps(
                {
                    "command": command,
                    "blocker_codes": ["authority_artifact_invalid"],
                    "error": f"no evaluator registered for {command}",
                },
                sort_keys=True,
            )
        )
        return 1
    evaluator = getattr(_promotion, evaluator_name)
    blockers = evaluator(artifact_payloads=tuple(payloads))
    blocker_codes = [blocker.code for blocker in blockers]
    print(
        json.dumps(
            {
                "command": command,
                "evaluator": evaluator_name,
                "ref_count": len(refs),
                "blocker_codes": blocker_codes,
            },
            sort_keys=True,
        )
    )
    return 1 if blocker_codes else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tradingx")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config-summary")
    config_parser.add_argument("--env-file", default=".env")

    paper_parser = subparsers.add_parser("paper-roundtrip")
    paper_parser.add_argument("--env-file", default=".env")
    paper_parser.add_argument("--symbol", default="SPY")
    paper_parser.add_argument("--quantity", default="1")
    paper_parser.add_argument("--log-dir", default=None)

    paper_loop_parser = subparsers.add_parser("paper-loop")
    paper_loop_parser.add_argument("--env-file", default=".env")
    paper_loop_parser.add_argument("--symbol", default="SPY")
    paper_loop_parser.add_argument("--quantity", default="1")

    paper_service_parser = subparsers.add_parser("run-paper-service")
    paper_service_parser.add_argument("--env-file", default=".env")
    paper_service_parser.add_argument("--symbols", default=None)
    paper_service_parser.add_argument("--quantity", default="1")
    paper_service_parser.add_argument("--interval-seconds", type=int, default=None)
    paper_service_parser.add_argument("--max-cycles", type=int, default=None)

    runtime_start_parser = subparsers.add_parser("runtime-start")
    runtime_start_parser.add_argument("--env-file", default=".env")
    runtime_start_parser.add_argument("--symbols", default=None)
    runtime_start_parser.add_argument("--quantity", default="1")
    runtime_start_parser.add_argument("--interval-seconds", type=int, default=None)
    runtime_start_parser.add_argument("--max-cycles", type=int, default=1)

    runtime_plan_parser = subparsers.add_parser("runtime-plan")
    runtime_plan_parser.add_argument("--env-file", default=".env")
    runtime_plan_parser.add_argument("--symbols", default=None)
    runtime_plan_parser.add_argument(
        "--output-dir",
        default="artifacts/runtime_plans",
    )

    market_day_parser = subparsers.add_parser("run-market-day")
    market_day_parser.add_argument("--env-file", default=".env")
    market_day_parser.add_argument("--symbols", default=None)
    market_day_parser.add_argument("--quantity", default="1")
    market_day_parser.add_argument("--interval-seconds", type=int, default=None)
    market_day_parser.add_argument("--max-heartbeats", type=int, default=None)

    market_scheduler_parser = subparsers.add_parser("run-market-scheduler")
    market_scheduler_parser.add_argument("--env-file", default=".env")
    market_scheduler_parser.add_argument("--symbols", default=None)
    market_scheduler_parser.add_argument("--quantity", default="1")
    market_scheduler_parser.add_argument("--interval-seconds", type=int, default=None)
    market_scheduler_parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=None,
    )
    market_scheduler_parser.add_argument("--max-scheduled-days", type=int, default=None)

    recover_parser = subparsers.add_parser("paper-recover")
    recover_parser.add_argument("--env-file", default=".env")
    recover_parser.add_argument("--symbol", default="SPY")

    live_disable_parser = subparsers.add_parser("live-disable-status")
    live_disable_parser.add_argument("--env-file", default=".env")

    promotion_parser = subparsers.add_parser("promotion-check")
    promotion_parser.add_argument("--strategy-id", required=True)
    promotion_parser.add_argument(
        "--artifact-root",
        default="config/strategy/promotion",
    )
    promotion_parser.add_argument(
        "--format",
        choices=("json", "summary"),
        default="json",
    )

    evidence_parser = subparsers.add_parser("evidence-report")
    evidence_parser.add_argument("--artifact-root", default="artifacts/paper_loop")

    decision_parser = subparsers.add_parser("decision-report")
    decision_parser.add_argument("--gate", default=None)
    decision_parser.add_argument(
        "--validation-artifact-root",
        default="artifacts/validation",
    )
    decision_parser.add_argument(
        "--paper-artifact-root",
        default="artifacts/paper_loop",
    )

    benchmark_prep_parser = subparsers.add_parser(
        "prepare-benchmark-closes",
        aliases=["prepare-benchmark-stack"],
    )
    benchmark_prep_parser.add_argument("--env-file", default=".env")
    benchmark_prep_parser.add_argument("--symbol", default="SPY")
    benchmark_prep_parser.add_argument("--window-start", required=True)
    benchmark_prep_parser.add_argument("--window-end", required=True)
    benchmark_prep_parser.add_argument(
        "--feed",
        choices=tuple(feed.value for feed in DataFeed),
        default=DataFeed.IEX.value,
    )
    benchmark_prep_parser.add_argument(
        "--adjustment",
        choices=tuple(adjustment.value for adjustment in Adjustment),
        default=Adjustment.DIVIDEND.value,
    )
    benchmark_prep_parser.add_argument("--output-file", default=None)

    risk_free_parser = subparsers.add_parser("refresh-risk-free-cache")
    risk_free_parser.add_argument(
        "--output-file",
        default=str(DEFAULT_RISK_FREE_CACHE_PATH),
    )
    risk_free_parser.add_argument("--start", default="2000-01-01")
    risk_free_parser.add_argument("--end", default=None)
    risk_free_parser.add_argument("--max-age-days", type=int, default=7)
    risk_free_parser.add_argument("--force", action="store_true")

    gate_parser = subparsers.add_parser("gate-report")
    gate_parser.add_argument("--env-file", default=".env")
    gate_parser.add_argument("--gate", choices=("1", "2"), required=True)
    gate_parser.add_argument(
        "--benchmark-stack-file",
        "--benchmark-closes-file",
        dest="benchmark_stack_file",
        required=True,
    )
    gate_parser.add_argument("--window-start", required=True)
    gate_parser.add_argument("--window-end", required=True)
    gate_parser.add_argument("--artifact-root", default="artifacts/validation")
    gate_parser.add_argument("--universe", default=None)
    gate_parser.add_argument("--benchmark-adjusted", action="store_true")
    gate_parser.add_argument("--experiment-id", default=None)
    gate_parser.add_argument("--run-id", default=None)
    gate_parser.add_argument("--promotion-decision-scope", default=None)
    gate_parser.add_argument("--metric-release-token", default=None)
    gate_parser.add_argument("--dataset-manifest-id", default=None)
    gate_parser.add_argument("--experiment-ledger-root", default=None)
    gate_parser.add_argument("--dataset-manifest-file", default=None)

    register_experiment_parser = subparsers.add_parser("register-experiment")
    register_experiment_parser.add_argument("--ledger-root", required=True)
    register_experiment_parser.add_argument("--registration-file", required=True)

    start_experiment_run_parser = subparsers.add_parser("start-experiment-run")
    start_experiment_run_parser.add_argument("--ledger-root", required=True)
    start_experiment_run_parser.add_argument("--run-file", required=True)

    complete_experiment_run_parser = subparsers.add_parser("complete-experiment-run")
    complete_experiment_run_parser.add_argument("--ledger-root", required=True)
    complete_experiment_run_parser.add_argument("--run-file", required=True)

    trial_universe_parser = subparsers.add_parser("trial-universe")
    trial_universe_parser.add_argument("--ledger-root", required=True)
    trial_universe_parser.add_argument("--promotion-decision-scope", required=True)
    trial_universe_parser.add_argument("--output-file", default=None)

    dataset_manifest_parser = subparsers.add_parser("dataset-manifest")
    dataset_manifest_parser.add_argument("--dataset-id", required=True)
    dataset_manifest_parser.add_argument("--vendor", default="unknown")
    dataset_manifest_parser.add_argument("--symbols", required=True)
    dataset_manifest_parser.add_argument("--window-start", required=True)
    dataset_manifest_parser.add_argument("--window-end", required=True)
    dataset_manifest_parser.add_argument(
        "--raw-payload-ref", action="append", default=[]
    )
    dataset_manifest_parser.add_argument(
        "--normalized-frame-ref",
        action="append",
        default=[],
    )
    dataset_manifest_parser.add_argument("--pit-universe-ref", required=True)
    dataset_manifest_parser.add_argument("--pit-symbol-map-ref", required=True)
    dataset_manifest_parser.add_argument("--delisting-inputs-ref", required=True)
    dataset_manifest_parser.add_argument("--vendor-observation-ref", required=True)
    dataset_manifest_parser.add_argument("--vendor-availability-ref", required=True)
    dataset_manifest_parser.add_argument("--normalization-code-hash", required=True)
    dataset_manifest_parser.add_argument("--normalization-policy-hash", required=True)
    dataset_manifest_parser.add_argument("--corporate-action-hash", required=True)
    dataset_manifest_parser.add_argument("--benchmark-hash", required=True)
    dataset_manifest_parser.add_argument("--cash-curve-hash", required=True)
    dataset_manifest_parser.add_argument("--output-file", default=None)

    compare_dataset_parser = subparsers.add_parser("compare-dataset")
    compare_dataset_parser.add_argument("--old", required=True)
    compare_dataset_parser.add_argument("--new", required=True)
    compare_dataset_parser.add_argument(
        "--old-raw-unavailable",
        action="store_true",
    )
    compare_dataset_parser.add_argument("--output-file", default=None)

    invalidate_evidence_parser = subparsers.add_parser("invalidate-evidence")
    invalidate_evidence_parser.add_argument("--restatement-report", required=True)
    invalidate_evidence_parser.add_argument("--dependency-index", default=None)
    invalidate_evidence_parser.add_argument("--output-file", default=None)

    statistical_report_parser = subparsers.add_parser("statistical-report")
    statistical_report_parser.add_argument("--strategy-id", required=True)
    statistical_report_parser.add_argument("--threshold-justification", required=True)
    statistical_report_parser.add_argument("--power-report", required=True)
    statistical_report_parser.add_argument("--bootstrap-report", required=True)
    statistical_report_parser.add_argument("--paired-benchmark-report", required=True)
    statistical_report_parser.add_argument("--trial-universe-manifest", required=True)
    statistical_report_parser.add_argument("--pbo-report", required=True)
    statistical_report_parser.add_argument("--output-file", default=None)

    quote_quality_parser = subparsers.add_parser("quote-quality-report")
    quote_quality_parser.add_argument("--inputs-file", required=True)
    quote_quality_parser.add_argument("--output-file", default=None)

    cost_model_parser = subparsers.add_parser("cost-model-report")
    cost_model_parser.add_argument("--inputs-file", required=True)
    cost_model_parser.add_argument("--output-file", default=None)

    capacity_curve_parser = subparsers.add_parser("capacity-curve")
    capacity_curve_parser.add_argument("--inputs-file", required=True)
    capacity_curve_parser.add_argument("--output-file", default=None)

    gate3_report_parser = subparsers.add_parser("gate3-report")
    gate3_report_parser.add_argument("--env-file", default=".env")
    gate3_report_parser.add_argument(
        "--paper-artifact-root",
        default="artifacts/paper_loop",
    )
    gate3_report_parser.add_argument(
        "--validation-artifact-root",
        default="artifacts/validation",
    )

    gate3_package_parser = subparsers.add_parser("gate3-package")
    gate3_package_parser.add_argument("--env-file", default=".env")
    gate3_package_parser.add_argument(
        "--paper-artifact-root",
        default="artifacts/paper_loop",
    )
    gate3_package_parser.add_argument(
        "--validation-artifact-root",
        default="artifacts/validation",
    )

    recovery_drill_parser = subparsers.add_parser("recovery-drill")
    recovery_drill_parser.add_argument("--env-file", default=".env")
    recovery_drill_parser.add_argument("--symbol", default="SPY")

    alert_drill_parser = subparsers.add_parser("alert-drill")
    alert_drill_parser.add_argument("--env-file", default=".env")
    alert_drill_parser.add_argument("--channel", default="smtp")

    replay_slippage_parser = subparsers.add_parser("replay-slippage-report")
    replay_slippage_parser.add_argument(
        "--paper-artifact-root",
        default="artifacts/paper_loop",
    )
    replay_slippage_parser.add_argument(
        "--validation-artifact-root",
        default="artifacts/validation",
    )
    replay_slippage_parser.add_argument(
        "--include-quote-quality",
        action="store_true",
        help=(
            "Include quote-quality state in replay-slippage records and tag the "
            "summary as Wave 5 cost-evidence-aware. Without this flag, the "
            "summary is classified as legacy_cost_evidence."
        ),
    )

    dry_run_report_parser = subparsers.add_parser("dry-run-report")
    dry_run_report_parser.add_argument(
        "--paper-artifact-root",
        default="artifacts/paper_loop",
    )
    dry_run_report_parser.add_argument(
        "--snapshot-root",
        default="data/snapshots",
    )
    dry_run_report_parser.add_argument(
        "--journal-path",
        default="data/journal.db",
    )
    dry_run_report_parser.add_argument(
        "--output-dir",
        default="artifacts/dry_run_reports",
    )

    gates_parser = subparsers.add_parser("gates-0001-status")
    gates_parser.add_argument(
        "--dry-run-report-path",
        required=True,
    )
    gates_parser.add_argument(
        "--ops-artifact-root",
        default="artifacts/ops",
    )

    rehearsal_parser = subparsers.add_parser("week1-rehearsal")
    rehearsal_parser.add_argument("--env-file", default=".env")
    rehearsal_parser.add_argument(
        "--output-dir",
        default="artifacts/ops",
    )

    supervisor_parser = subparsers.add_parser("run-operator-supervisor")
    supervisor_parser.add_argument("--env-file", default=".env")
    supervisor_parser.add_argument("--symbols", default=None)
    supervisor_parser.add_argument("--quantity", default="1")
    supervisor_parser.add_argument("--interval-seconds", type=int, default=None)
    supervisor_parser.add_argument("--poll-interval-seconds", type=int, default=None)
    supervisor_parser.add_argument("--telegram-poll-seconds", type=int, default=None)
    supervisor_parser.add_argument("--max-loops", type=int, default=None)

    launch_control_center_parser = subparsers.add_parser("launch-control-center")
    launch_control_center_parser.add_argument("--env-file", default=".env")

    web_parser = subparsers.add_parser("web")
    web_parser.add_argument("--env-file", default=".env")
    web_parser.add_argument("--host", default=None)
    web_parser.add_argument("--port", type=int, default=None)

    # Defect 8 — Wave 4-10 artifact CLI subcommands.
    # Each accepts --ref <path> (repeatable) pointing to an artifact JSON
    # file, runs the matching evaluator, prints canonical JSON, and exits
    # non-zero when the evaluator emits any blocker_codes.
    for _name in (
        "portfolio-utility",
        "optimizer-validation",
        "optimizer-fallback",
        "forecast-manifest",
        "sizing-policy",
        "short-capability",
        "borrow-snapshot",
        "short-financing",
        "short-risk-report",
        "live-probe-plan",
        "live-probe-run",
        "live-probe-recertification",
        "change-control",
        "replay-equivalence",
        "recertification",
        "drift-monitor-spec",
        "legacy-migration-report",
    ):
        wave_parser = subparsers.add_parser(_name)
        wave_parser.add_argument(
            "--ref",
            dest="refs",
            action="append",
            default=[],
            help="Path to an artifact JSON file. May be specified multiple times.",
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "promotion-check":
        artifact_root = Path(args.artifact_root)
        candidate_root = artifact_root / args.strategy_id
        if candidate_root.exists():
            artifact_root = candidate_root
        promotion_decision = evaluate_promotion_manifest(artifact_root)
        promotion_payload = promotion_decision.to_json()
        if promotion_payload["strategy_id"] != args.strategy_id:
            promotion_payload = {
                "schema_version": "1.0",
                "strategy_id": args.strategy_id,
                "requested_state": "disabled",
                "max_state": "disabled",
                "blocker_codes": ["authority_artifact_invalid"],
                "mandate_blocker_codes": [],
                "statistical_blocker_codes": [],
                "authority_blocker_codes": ["authority_artifact_invalid"],
                "artifact_refs": [],
                "ledger_sequence": None,
                "ledger_hash": None,
                "mismatched_artifact_strategy_id": promotion_payload["strategy_id"],
            }
            exit_code = 1
        else:
            exit_code = 0
        if args.format == "summary":
            print(_format_promotion_summary(promotion_payload))
        else:
            print(json.dumps(_serialize(promotion_payload), sort_keys=True))
        return exit_code

    if args.command == "config-summary":
        config = TradingConfig.from_env_file(Path(args.env_file))
        print(json.dumps(config.to_safe_summary(), sort_keys=True))
        return 0

    if args.command == "refresh-risk-free-cache":
        now_utc = datetime.now(UTC)
        output_file = Path(args.output_file)
        start_date = _parse_iso_date(args.start)
        end_date = _parse_iso_date(args.end) if args.end else now_utc.date()
        max_age = timedelta(days=args.max_age_days)
        should_refresh = args.force or needs_risk_free_refresh(
            output_file,
            now_utc=now_utc,
            max_age=max_age,
        )
        if should_refresh:
            refresh_risk_free_cache(
                output_file,
                start_date=start_date,
                end_date=end_date,
                now_utc=now_utc,
            )
            status = "refreshed"
        else:
            status = "fresh"
        print(
            json.dumps(
                {
                    "status": status,
                    "output_file": str(output_file),
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "paper-loop":
        config = TradingConfig.from_env_file(Path(args.env_file))
        return _run_with_runtime_lock(
            config,
            lambda: (
                0,
                build_default_paper_trading_controller(config).run_trading_cycle(
                    args.symbol,
                    Decimal(args.quantity),
                ),
            ),
        )

    if args.command == "run-paper-service":
        config = TradingConfig.from_env_file(Path(args.env_file))
        symbols = (
            tuple(
                item.strip().upper() for item in args.symbols.split(",") if item.strip()
            )
            if args.symbols
            else config.runtime.symbol_universe
        )
        return _run_with_runtime_lock(
            config,
            lambda: (
                0,
                build_default_paper_service(config).run(
                    symbols=symbols,
                    quantity=Decimal(args.quantity),
                    interval_seconds=(
                        args.interval_seconds or config.runtime.service_interval_seconds
                    ),
                    max_cycles=args.max_cycles,
                ),
            ),
        )

    if args.command == "runtime-plan":
        config = TradingConfig.from_env_file(Path(args.env_file))
        symbols = (
            tuple(
                item.strip().upper() for item in args.symbols.split(",") if item.strip()
            )
            if args.symbols
            else config.runtime.symbol_universe
        )
        decision = resolve_broker_mode(config)
        operator_store = FilesystemArtifactStore(
            config.runtime.artifact_root / "operator_platform"
        )
        runtime_store = FilesystemArtifactStore(config.runtime.artifact_root)
        activation_gateway = LocalActivationGateway(
            store=operator_store,
            runtime_snapshot_store=runtime_store,
            promotion_decision_provider=build_artifact_promotion_decision_provider(
                config.runtime.artifact_root / "quant" / "promotion"
            ),
            required_promotion_state=PromotionState.PAPER_TRADING,
            projection_root=Path("config/strategy/promotion"),
        )
        activation, _snapshot = activation_gateway.load_or_create_active_records(
            symbols
        )
        planner = RuntimePortfolioPlanner(
            market_data=build_market_data_gateway_for_mode(
                config,
                broker_mode=decision.requested_mode,
            ),
            activation_gateway=activation_gateway,
        )
        trading_client = build_trading_client_for_mode(config, decision)
        portfolio_state = AlpacaPortfolioGateway(
            trading_client=trading_client
        ).get_portfolio_state()
        try:
            plan = planner.plan_for_service(
                symbols=symbols,
                portfolio_state=portfolio_state,
            )
        except UnsupportedRuntimePortfolioPlanError as error:
            print(
                json.dumps(
                    {
                        "status": "portfolio_planner_blocked",
                        "strategy_id": activation.strategy_id,
                        "message": str(error),
                    },
                    sort_keys=True,
                )
            )
            return 0
        if plan is None:
            print(
                json.dumps(
                    {
                        "status": "legacy_strategy_active",
                        "strategy_id": activation.strategy_id,
                        "message": (
                            "Active strategy does not use the runtime portfolio "
                            "planner."
                        ),
                    },
                    sort_keys=True,
                )
            )
            return 0
        artifact_path = FilesystemArtifactStore(
            Path(args.output_dir)
        ).write_runtime_portfolio_plan(plan)
        payload = _serialize(plan)
        payload["artifact_path"] = str(artifact_path)
        print(json.dumps(payload, sort_keys=True))
        return 0

    if args.command == "runtime-start":
        config = TradingConfig.from_env_file(Path(args.env_file))
        symbols = (
            tuple(
                item.strip().upper() for item in args.symbols.split(",") if item.strip()
            )
            if args.symbols
            else config.runtime.symbol_universe
        )

        def _start_runtime() -> tuple[int, dict[str, Any]]:
            decision = resolve_broker_mode(config)
            operator_store = FilesystemArtifactStore(
                config.runtime.artifact_root / "operator_platform"
            )
            runtime_store = FilesystemArtifactStore(config.runtime.artifact_root)
            market_data_gateway = build_market_data_gateway_for_mode(
                config,
                broker_mode=decision.requested_mode,
            )
            activation_gateway = LocalActivationGateway(
                store=operator_store,
                runtime_snapshot_store=runtime_store,
                promotion_decision_provider=build_artifact_promotion_decision_provider(
                    config.runtime.artifact_root / "quant" / "promotion"
                ),
                required_promotion_state=PromotionState.PAPER_TRADING,
                projection_root=Path("config/strategy/promotion"),
            )
            activation, snapshot = activation_gateway.load_or_create_active_records(
                symbols
            )
            warmup = HistoricalWarmupService(
                market_data_gateway=market_data_gateway,
            ).build_warmup(
                symbols=symbols,
                benchmark_symbol="SPY",
                warmup_days=60,
                required_bar_count=30,
            )
            warmup_path = operator_store.write_historical_warmup_record(warmup)
            trading_client = build_trading_client_for_mode(config, decision)
            portfolio_gateway = AlpacaPortfolioGateway(trading_client=trading_client)
            selection = RuntimeOpportunityPlanner(
                market_data_gateway=market_data_gateway,
            ).plan(
                symbols=symbols,
                portfolio_state=portfolio_gateway.get_portfolio_state(),
                activation=activation,
                model_snapshot=snapshot,
                warmup=warmup,
            )
            selection_path = operator_store.write_opportunity_selection_record(
                selection
            )
            warmup_complete = all(symbol in warmup.symbols_ready for symbol in symbols)
            runtime_state = BotRuntimeState(
                status="trading_ready" if warmup_complete else "halted",
                status_reason=(
                    "Runtime boot complete."
                    if warmup_complete
                    else "Warmup incomplete for one or more configured symbols."
                ),
                active_symbols=symbols,
                started_at_utc=datetime.now(UTC),
                updated_at_utc=datetime.now(UTC),
                last_error=(
                    ""
                    if warmup_complete
                    else "Warmup incomplete for symbols: "
                    + ", ".join(
                        symbol
                        for symbol in symbols
                        if symbol not in warmup.symbols_ready
                    )
                ),
                active_strategy_id=activation.strategy_id,
                active_model_snapshot_id=snapshot.snapshot_id,
                latest_selection_id=selection.selection_id,
            )
            runtime_state_path = operator_store.write_runtime_host_state(runtime_state)
            runtime_service_result: Any | None = None
            if warmup_complete:
                runtime_service_result = build_runtime_host_trading_service(config).run(
                    symbols=symbols,
                    quantity=Decimal(args.quantity),
                    interval_seconds=(
                        args.interval_seconds or config.runtime.service_interval_seconds
                    ),
                    max_cycles=args.max_cycles,
                )
            return (
                0,
                {
                    "runtime_state": runtime_state,
                    "runtime_state_path": runtime_state_path,
                    "warmup": warmup,
                    "warmup_path": warmup_path,
                    "activation": activation,
                    "model_snapshot": snapshot,
                    "selection": selection,
                    "selection_path": selection_path,
                    "service_result": runtime_service_result,
                },
            )

        return _run_with_runtime_lock(config, _start_runtime)

    if args.command == "run-market-day":
        config = TradingConfig.from_env_file(Path(args.env_file))
        symbols = (
            tuple(
                item.strip().upper() for item in args.symbols.split(",") if item.strip()
            )
            if args.symbols
            else config.runtime.symbol_universe
        )
        return _run_with_runtime_lock(
            config,
            lambda: (
                0,
                build_default_market_day_automation_runner(config).run_market_day(
                    symbols=symbols,
                    quantity=Decimal(args.quantity),
                    interval_seconds=(
                        args.interval_seconds or config.runtime.service_interval_seconds
                    ),
                    max_heartbeats=args.max_heartbeats,
                ),
            ),
        )

    if args.command == "run-market-scheduler":
        config = TradingConfig.from_env_file(Path(args.env_file))
        symbols = (
            tuple(
                item.strip().upper() for item in args.symbols.split(",") if item.strip()
            )
            if args.symbols
            else config.runtime.symbol_universe
        )
        return _run_with_runtime_lock(
            config,
            lambda: (
                0,
                build_default_market_day_scheduler(config).run(
                    symbols=symbols,
                    quantity=Decimal(args.quantity),
                    interval_seconds=(
                        args.interval_seconds or config.runtime.service_interval_seconds
                    ),
                    poll_interval_seconds=(
                        args.poll_interval_seconds
                        or config.runtime.scheduler_poll_seconds
                    ),
                    max_scheduled_days=args.max_scheduled_days,
                ),
            ),
        )

    if args.command == "paper-recover":
        config = TradingConfig.from_env_file(Path(args.env_file))
        return _run_with_runtime_lock(
            config,
            lambda: (
                0,
                build_default_paper_trading_controller(config).recover_trading_cycle(
                    args.symbol
                )
                or {},
            ),
        )

    if args.command == "live-disable-status":
        config = TradingConfig.from_env_file(Path(args.env_file))
        print(json.dumps(config.live_disable_report(), sort_keys=True))
        return 0

    if args.command == "evidence-report":
        store = FilesystemArtifactStore(Path(args.artifact_root))
        print(
            json.dumps(
                _serialize(store.build_operator_evidence_report()),
                sort_keys=True,
            )
        )
        return 0

    if args.command == "decision-report":
        brief = build_gate_decision_brief(
            validation_store=FilesystemArtifactStore(
                Path(args.validation_artifact_root)
            ),
            paper_store=FilesystemArtifactStore(Path(args.paper_artifact_root)),
            gate_id=args.gate,
        )
        print(
            json.dumps(
                _serialize(
                    {
                        "brief": brief,
                        "alert": build_gate_decision_alert(brief),
                    }
                ),
                sort_keys=True,
            )
        )
        return 0

    if args.command in {"prepare-benchmark-closes", "prepare-benchmark-stack"}:
        config = TradingConfig.from_env_file(Path(args.env_file))
        market_data_gateway = build_default_market_data_gateway(config)
        risk_free_series = build_default_risk_free_series(config)
        benchmark_stack = build_default_benchmark_stack(
            config,
            market_data_gateway=market_data_gateway,
            risk_free_series=risk_free_series,
        )
        window_start_utc = datetime.fromisoformat(args.window_start).replace(tzinfo=UTC)
        window_end_utc = datetime.fromisoformat(args.window_end).replace(tzinfo=UTC)
        session_dates = AlpacaRegularHoursCalendar().session_dates_between(
            window_start_utc,
            window_end_utc,
        )
        benchmark_stack_payload = benchmark_stack.materialize(
            session_dates=session_dates
        )
        output_file = (
            Path(args.output_file)
            if args.output_file is not None
            else config.runtime.artifact_root
            / "validation"
            / "benchmark_stacks"
            / (
                "stack-"
                f"{window_start_utc.date().isoformat()}-"
                f"{window_end_utc.date().isoformat()}.json"
            )
        )
        write_benchmark_stack_payload(output_file, benchmark_stack_payload)
        print(
            json.dumps(
                _serialize(
                    {
                        "output_file": output_file,
                        "benchmark_stack": benchmark_stack_payload,
                    }
                ),
                sort_keys=True,
            )
        )
        return 0

    if args.command == "register-experiment":
        ledger = ExperimentLedger(ledger_root=Path(args.ledger_root))
        payload = load_json_object(Path(args.registration_file))
        ledger.append_registration(payload)
        print(
            json.dumps(
                _serialize({"status": "registered", "registration": payload}),
                sort_keys=True,
            )
        )
        return 0

    if args.command in {"start-experiment-run", "complete-experiment-run"}:
        ledger = ExperimentLedger(ledger_root=Path(args.ledger_root))
        payload = load_json_object(Path(args.run_file))
        ledger.append_run_record(payload)
        print(
            json.dumps(
                _serialize({"status": "recorded", "run": payload}), sort_keys=True
            )
        )
        return 0

    if args.command == "trial-universe":
        ledger = ExperimentLedger(ledger_root=Path(args.ledger_root))
        manifest = build_trial_universe_manifest(
            promotion_decision_scope=args.promotion_decision_scope,
            registrations=ledger.registrations(),
            run_records=ledger.run_records(),
            amendments=ledger.amendments(),
        )
        if args.output_file:
            output_file = Path(args.output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(_serialize(manifest), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(_serialize(manifest), sort_keys=True))
        return 0

    if args.command == "dataset-manifest":
        manifest = build_dataset_manifest(
            dataset_id=args.dataset_id,
            vendor=args.vendor,
            symbols=tuple(
                item.strip() for item in args.symbols.split(",") if item.strip()
            ),
            window_start_utc=args.window_start,
            window_end_utc=args.window_end,
            raw_payload_refs=tuple(args.raw_payload_ref),
            normalized_frame_refs=tuple(args.normalized_frame_ref),
            point_in_time_universe_membership_ref=args.pit_universe_ref,
            point_in_time_symbol_mapping_ref=args.pit_symbol_map_ref,
            delisting_return_inputs_ref=args.delisting_inputs_ref,
            vendor_observation_timestamp_ref=args.vendor_observation_ref,
            vendor_availability_timestamp_ref=args.vendor_availability_ref,
            normalization_code_hash=args.normalization_code_hash,
            normalization_policy_hash=args.normalization_policy_hash,
            corporate_action_hash=args.corporate_action_hash,
            benchmark_hash=args.benchmark_hash,
            cash_curve_hash=args.cash_curve_hash,
        )
        if args.output_file:
            output_file = Path(args.output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(_serialize(manifest), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(_serialize(manifest), sort_keys=True))
        return 0

    if args.command == "compare-dataset":
        report = compare_dataset_manifests(
            old_manifest=load_json_object(Path(args.old)),
            new_manifest=load_json_object(Path(args.new)),
            old_raw_payload_available=not args.old_raw_unavailable,
        )
        if args.output_file:
            output_file = Path(args.output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(_serialize(report), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(_serialize(report), sort_keys=True))
        return 0

    if args.command == "invalidate-evidence":
        dependency_index = (
            load_json_object(Path(args.dependency_index))
            if args.dependency_index
            else None
        )
        report = invalidate_evidence_from_restatement(
            restatement_report=load_json_object(Path(args.restatement_report)),
            dependency_index=dependency_index,
        )
        if args.output_file:
            output_file = Path(args.output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(_serialize(report), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(_serialize(report), sort_keys=True))
        return 0

    if args.command == "statistical-report":
        report = build_statistical_validation_report(
            strategy_id=args.strategy_id,
            threshold_justification=load_json_object(
                Path(args.threshold_justification)
            ),
            power_report=load_json_object(Path(args.power_report)),
            bootstrap_report=load_json_object(Path(args.bootstrap_report)),
            paired_benchmark_report=load_json_object(
                Path(args.paired_benchmark_report)
            ),
            trial_universe_manifest=load_json_object(
                Path(args.trial_universe_manifest)
            ),
            pbo_report=load_json_object(Path(args.pbo_report)),
        )
        if args.output_file:
            output_file = Path(args.output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(_serialize(report), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(_serialize(report), sort_keys=True))
        return 0

    if args.command == "quote-quality-report":
        inputs_any: Any = load_json_object(Path(args.inputs_file))
        record = build_quote_quality_record(
            record_id=str(inputs_any["record_id"]),
            symbol=str(inputs_any["symbol"]),
            quote_timestamp_utc=datetime.fromisoformat(
                str(inputs_any["quote_timestamp_utc"]).replace("Z", "+00:00")
            ),
            system_receive_at_utc=datetime.fromisoformat(
                str(inputs_any["system_receive_at_utc"]).replace("Z", "+00:00")
            ),
            source=str(inputs_any["source"]),
            vendor=str(inputs_any["vendor"]),
            trading_session=str(inputs_any["trading_session"]),
            bid_price=Decimal(str(inputs_any["bid_price"])),
            ask_price=Decimal(str(inputs_any["ask_price"])),
            handling_policy=str(
                inputs_any.get("handling_policy", "no_trade_on_bad_quote")
            ),
            quote_age_milliseconds=int(inputs_any.get("quote_age_milliseconds", 0)),
            latency_milliseconds=int(inputs_any.get("latency_milliseconds", 0)),
            is_locked=bool(inputs_any.get("is_locked", False)),
            is_crossed=bool(inputs_any.get("is_crossed", False)),
            is_stale=bool(inputs_any.get("is_stale", False)),
            outage_adjacent=bool(inputs_any.get("outage_adjacent", False)),
        )
        _validate_quant_artifact(
            record, schema=_load_quant_schema("quote_quality_record")
        )
        if args.output_file:
            output_file = Path(args.output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(_serialize(record), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(_serialize(record), sort_keys=True))
        return 0

    if args.command == "cost-model-report":
        inputs_any2: Any = load_json_object(Path(args.inputs_file))
        report = build_cost_model_report(
            report_id=str(inputs_any2["report_id"]),
            strategy_id=str(inputs_any2["strategy_id"]),
            model_version=str(inputs_any2["model_version"]),
            cost_feature_hash=str(inputs_any2["cost_feature_hash"]),
            bucket_assignment_policy=str(inputs_any2["bucket_assignment_policy"]),
            training_dataset_ref=str(inputs_any2["training_dataset_ref"]),
            sample_window_start_utc=datetime.fromisoformat(
                str(inputs_any2["sample_window_start_utc"]).replace("Z", "+00:00")
            ),
            sample_window_end_utc=datetime.fromisoformat(
                str(inputs_any2["sample_window_end_utc"]).replace("Z", "+00:00")
            ),
            bucket_definitions=tuple(
                str(value) for value in inputs_any2.get("bucket_definitions", ())
            ),
            minimum_bucket_sample_size=int(
                inputs_any2.get("minimum_bucket_sample_size", 0)
            ),
            bucket_power_target=Decimal(
                str(inputs_any2.get("bucket_power_target", "0"))
            ),
            bucket_confidence=Decimal(str(inputs_any2.get("bucket_confidence", "0"))),
            powered_bucket_coverage={
                str(bucket): bool(value)
                for bucket, value in dict(
                    inputs_any2.get("powered_bucket_coverage", {})
                ).items()
            },
            sparse_bucket_fallback_policy=str(
                inputs_any2.get("sparse_bucket_fallback_policy", "no_fallback")
            ),
            clean_estimate_bps=Decimal(str(inputs_any2.get("clean_estimate_bps", "0"))),
            all_events_stress_bps=Decimal(
                str(inputs_any2.get("all_events_stress_bps", "0"))
            ),
            adverse_p90_bps=Decimal(str(inputs_any2.get("adverse_p90_bps", "0"))),
            adverse_p95_bps=Decimal(str(inputs_any2.get("adverse_p95_bps", "0"))),
            bucket_sample_sizes={
                str(bucket): int(value)
                for bucket, value in dict(
                    inputs_any2.get("bucket_sample_sizes", {})
                ).items()
            },
            unsupported_buckets=tuple(
                str(bucket) for bucket in inputs_any2.get("unsupported_buckets", ())
            ),
            non_fill_opportunity_cost_bps=Decimal(
                str(inputs_any2.get("non_fill_opportunity_cost_bps", "0"))
            ),
            queue_adverse_selection_bps=Decimal(
                str(inputs_any2.get("queue_adverse_selection_bps", "0"))
            ),
            counterfactual_quality=str(
                inputs_any2.get("counterfactual_quality", "medium")
            ),
            paper_observation_count=int(inputs_any2.get("paper_observation_count", 0)),
            live_probe_observation_count=int(
                inputs_any2.get("live_probe_observation_count", 0)
            ),
            live_observation_count=int(inputs_any2.get("live_observation_count", 0)),
            minimum_live_sample_requirement=int(
                inputs_any2.get("minimum_live_sample_requirement", 0)
            ),
            calibration_source=str(inputs_any2.get("calibration_source", "")),
            runtime_no_trade_rule_enforced=bool(
                inputs_any2.get("runtime_no_trade_rule_enforced", False)
            ),
            impact_claim_requested=bool(
                inputs_any2.get("impact_claim_requested", False)
            ),
            generated_at_utc=(
                datetime.fromisoformat(
                    str(inputs_any2["generated_at_utc"]).replace("Z", "+00:00")
                )
                if "generated_at_utc" in inputs_any2
                and str(inputs_any2["generated_at_utc"]).strip()
                else None
            ),
        )
        _validate_quant_artifact(report, schema=_load_quant_schema("cost_model_report"))
        if args.output_file:
            output_file = Path(args.output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(_serialize(report), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(_serialize(report), sort_keys=True))
        return 0

    if args.command == "capacity-curve":
        inputs_any3: Any = load_json_object(Path(args.inputs_file))
        report = build_capacity_curve_report(
            report_id=str(inputs_any3["report_id"]),
            strategy_id=str(inputs_any3["strategy_id"]),
            target_capital_scale=Decimal(str(inputs_any3["target_capital_scale"])),
            tested_scales=tuple(
                Decimal(str(scale)) for scale in inputs_any3.get("tested_scales", ())
            ),
            validated_range_min=Decimal(str(inputs_any3["validated_range_min"])),
            validated_range_max=Decimal(str(inputs_any3["validated_range_max"])),
            max_participation_rate=Decimal(str(inputs_any3["max_participation_rate"])),
            expected_turnover=Decimal(str(inputs_any3["expected_turnover"])),
            orders_per_day=Decimal(str(inputs_any3["orders_per_day"])),
            rebalance_frequency=str(inputs_any3["rebalance_frequency"]),
            annualized_cost_drag_by_scale={
                str(scale): Decimal(str(value))
                for scale, value in dict(
                    inputs_any3.get("annualized_cost_drag_by_scale", {})
                ).items()
            },
            capacity_under_turnover_assumption=Decimal(
                str(inputs_any3.get("capacity_under_turnover_assumption", "0"))
            ),
            lower_bound_capacity_curve={
                str(scale): Decimal(str(value))
                for scale, value in dict(
                    inputs_any3.get("lower_bound_capacity_curve", {})
                ).items()
            }
            or None,
            expected_cost_curve={
                str(scale): Decimal(str(value))
                for scale, value in dict(
                    inputs_any3.get("expected_cost_curve", {})
                ).items()
            },
            net_edge_curve={
                str(scale): Decimal(str(value))
                for scale, value in dict(inputs_any3.get("net_edge_curve", {})).items()
            },
            lower_bound_net_edge_by_scale={
                str(scale): Decimal(str(value))
                for scale, value in dict(
                    inputs_any3.get("lower_bound_net_edge_by_scale", {})
                ).items()
            }
            or None,
            lower_bound_capacity_limit=(
                Decimal(str(inputs_any3["lower_bound_capacity_limit"]))
                if "lower_bound_capacity_limit" in inputs_any3
                and str(inputs_any3["lower_bound_capacity_limit"]).strip()
                else None
            ),
            generated_at_utc=(
                datetime.fromisoformat(
                    str(inputs_any3["generated_at_utc"]).replace("Z", "+00:00")
                )
                if "generated_at_utc" in inputs_any3
                and str(inputs_any3["generated_at_utc"]).strip()
                else None
            ),
        )
        _validate_quant_artifact(
            report, schema=_load_quant_schema("capacity_curve_report")
        )
        if args.output_file:
            output_file = Path(args.output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(_serialize(report), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        print(json.dumps(_serialize(report), sort_keys=True))
        return 0

    if args.command == "gate-report":
        config = TradingConfig.from_env_file(Path(args.env_file))
        controller = build_default_gate_validation_controller(
            config,
            artifact_root=Path(args.artifact_root),
        )
        window_start_utc = datetime.fromisoformat(args.window_start).replace(tzinfo=UTC)
        window_end_utc = datetime.fromisoformat(args.window_end).replace(tzinfo=UTC)
        benchmark_stack_payload = load_benchmark_stack_payload(
            Path(args.benchmark_stack_file)
        )
        universe = (
            tuple(
                item.strip().upper()
                for item in args.universe.split(",")
                if item.strip()
            )
            if args.universe
            else config.runtime.symbol_universe
        )
        metric_visibility_context = None
        if args.experiment_id:
            metric_visibility_context, resolved_dataset_manifest_id = (
                resolve_metric_visibility_context(
                    experiment_id=args.experiment_id,
                    run_id=args.run_id or "",
                    promotion_decision_scope=args.promotion_decision_scope or "",
                    metric_release_token_ref=args.metric_release_token or "",
                    ledger=(
                        ExperimentLedger(ledger_root=Path(args.experiment_ledger_root))
                        if args.experiment_ledger_root
                        else None
                    ),
                    dataset_manifest_path=(
                        Path(args.dataset_manifest_file)
                        if args.dataset_manifest_file
                        else None
                    ),
                    dataset_manifest_id=args.dataset_manifest_id,
                )
            )
            if resolved_dataset_manifest_id:
                args.dataset_manifest_id = resolved_dataset_manifest_id
        gate_result = controller.generate_gate_report(
            gate_id=args.gate,
            benchmark_stack_payload=benchmark_stack_payload,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            universe=universe,
            metric_visibility_context=metric_visibility_context,
            dataset_manifest_id=args.dataset_manifest_id,
        )
        print(json.dumps(_serialize(gate_result), sort_keys=True))
        return 0

    if args.command == "gate3-report":
        validation_store = FilesystemArtifactStore(Path(args.validation_artifact_root))
        gate3_readiness_report = build_gate3_readiness_report(
            paper_store=FilesystemArtifactStore(Path(args.paper_artifact_root)),
            validation_store=validation_store,
        )
        validation_store.write_gate3_readiness_report(gate3_readiness_report)
        print(json.dumps(_serialize(gate3_readiness_report), sort_keys=True))
        return 0

    if args.command == "gate3-package":
        validation_store = FilesystemArtifactStore(Path(args.validation_artifact_root))
        gate3_readiness_report = build_gate3_readiness_report(
            paper_store=FilesystemArtifactStore(Path(args.paper_artifact_root)),
            validation_store=validation_store,
        )
        validation_store.write_gate3_readiness_report(gate3_readiness_report)
        package = build_gate3_promotion_package(gate3_readiness_report)
        validation_store.write_gate3_promotion_package(package)
        print(
            json.dumps(
                _serialize({"report": gate3_readiness_report, "package": package}),
                sort_keys=True,
            )
        )
        return 0

    if args.command in {"recovery-drill", "alert-drill"}:
        config = TradingConfig.from_env_file(Path(args.env_file))
        from tradingx.web.runtime import build_default_local_web_components

        _, action_runner = build_default_local_web_components(config)
        result = (
            action_runner.run_recovery_drill(symbol=args.symbol)
            if args.command == "recovery-drill"
            else action_runner.run_alert_drill(channel=args.channel)
        )
        print(json.dumps(_serialize(result), sort_keys=True))
        return 0

    if args.command == "replay-slippage-report":
        replay_result = generate_replay_slippage_evidence(
            paper_store=FilesystemArtifactStore(Path(args.paper_artifact_root)),
            validation_store=FilesystemArtifactStore(
                Path(args.validation_artifact_root)
            ),
            include_quote_quality=bool(getattr(args, "include_quote_quality", False)),
        )
        print(json.dumps(_serialize(replay_result), sort_keys=True))
        return 0

    if args.command == "dry-run-report":
        dry_run_report = build_dry_run_report(
            paper_store=FilesystemArtifactStore(Path(args.paper_artifact_root)),
            snapshot_store=ContentAddressedSnapshotStore(Path(args.snapshot_root)),
            journal=SqliteOmsJournal(Path(args.journal_path)),
        )
        artifact_path = write_dry_run_report(
            report=dry_run_report,
            output_dir=Path(args.output_dir),
        )
        payload = dict(dry_run_report)
        payload["artifact_path"] = str(artifact_path)
        print(json.dumps(_serialize(payload), sort_keys=True))
        return 0

    if args.command == "gates-0001-status":
        payload = build_gates_0001_status(
            dry_run_report_path=Path(args.dry_run_report_path),
            ops_artifact_root=Path(args.ops_artifact_root),
        )
        print(json.dumps(_serialize(payload), sort_keys=True))
        return 0

    if args.command == "week1-rehearsal":
        config = TradingConfig.from_env_file(Path(args.env_file))

        def _paper_account_state_provider() -> dict[str, Any]:
            if not config.has_real_paper_credentials():
                return {
                    "status": "skipped",
                    "reason": "Paper credentials are placeholders.",
                }
            trading_client = TradingClient(
                config.paper_credentials.api_key,
                config.paper_credentials.api_secret,
                paper=True,
            )
            portfolio_state = AlpacaPortfolioGateway(
                trading_client=trading_client
            ).get_portfolio_state()
            return {
                "status": "recorded",
                "cash": str(portfolio_state.cash),
                "equity": str(portfolio_state.equity),
                "buying_power": str(portfolio_state.buying_power),
                "positions": [
                    {
                        "symbol": position.symbol,
                        "quantity": str(position.quantity),
                    }
                    for position in portfolio_state.positions
                ],
                "open_orders": list(portfolio_state.open_orders),
            }

        payload = run_week1_rehearsal(
            output_dir=Path(args.output_dir),
            account_state_provider=_paper_account_state_provider,
        )
        print(json.dumps(_serialize(payload), sort_keys=True))
        return 0

    if args.command == "run-operator-supervisor":
        config = TradingConfig.from_env_file(Path(args.env_file))
        symbols = (
            tuple(
                item.strip().upper() for item in args.symbols.split(",") if item.strip()
            )
            if args.symbols
            else config.runtime.symbol_universe
        )
        supervisor = build_default_operator_supervisor(
            config,
            env_file=Path(args.env_file),
            symbols=symbols,
            quantity=Decimal(args.quantity),
            interval_seconds=(
                args.interval_seconds or config.runtime.service_interval_seconds
            ),
            poll_interval_seconds=(
                args.poll_interval_seconds or config.runtime.scheduler_poll_seconds
            ),
        )
        try:
            with runtime_process_lock(_runtime_lock_path(config)):
                state = supervisor.run(
                    poll_interval_seconds=(
                        args.poll_interval_seconds
                        or config.runtime.scheduler_poll_seconds
                    ),
                    telegram_poll_seconds=args.telegram_poll_seconds or 5,
                    max_loops=args.max_loops,
                )
        except RuntimeLockError as error:
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "error": str(error),
                    },
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(_serialize(state), sort_keys=True))
        return 0

    if args.command == "launch-control-center":
        config = TradingConfig.from_env_file(Path(args.env_file))
        try:
            launch_result = launch_control_center(
                config=config,
                repo_root=Path.cwd(),
                env_file=Path(args.env_file),
            )
        except ControlCenterLaunchError as error:
            print(
                json.dumps(
                    {
                        "status": "error",
                        "message": str(error),
                    },
                    sort_keys=True,
                )
            )
            return 1
        print(json.dumps(_serialize(launch_result), sort_keys=True))
        return 0

    if args.command == "web":
        config = TradingConfig.from_env_file(Path(args.env_file))
        run_web_app(
            config,
            host=args.host or config.web.host,
            port=args.port or config.web.port,
        )
        return 0

    # Defect 8 — Wave 4-10 artifact CLI subcommand dispatcher.
    if args.command in {
        "portfolio-utility",
        "optimizer-validation",
        "optimizer-fallback",
        "forecast-manifest",
        "sizing-policy",
        "short-capability",
        "borrow-snapshot",
        "short-financing",
        "short-risk-report",
        "live-probe-plan",
        "live-probe-run",
        "live-probe-recertification",
        "change-control",
        "replay-equivalence",
        "recertification",
        "drift-monitor-spec",
        "legacy-migration-report",
    }:
        return _run_wave_artifact_check(args.command, list(args.refs or []))

    config = TradingConfig.from_env_file(Path(args.env_file))
    log_dir = (
        Path(args.log_dir)
        if args.log_dir is not None
        else config.runtime.artifact_root / "smoke"
    )

    return _run_with_runtime_lock(
        config,
        lambda: (
            0,
            {
                "symbol": (
                    result := build_default_controller(config).run_paper_roundtrip(
                        args.symbol,
                        Decimal(args.quantity),
                        log_dir=log_dir,
                    )
                ).symbol,
                "quantity": result.quantity,
                "quote": asdict(result.quote),
                "buy_order": asdict(result.buy_order),
                "sell_order": asdict(result.sell_order),
                "final_account": asdict(result.final_account),
                "final_position_quantity": result.final_position_quantity,
                "cash_delta": result.cash_delta,
                "log_path": result.log_path,
            },
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
