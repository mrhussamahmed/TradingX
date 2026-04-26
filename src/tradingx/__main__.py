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
from tradingx.automation import build_default_market_day_automation_runner
from tradingx.benchmark_stack import build_default_benchmark_stack
from tradingx.config import TradingConfig
from tradingx.controller import (
    build_default_controller,
    build_default_gate_validation_controller,
    build_default_paper_trading_controller,
)
from tradingx.data import (
    AlpacaRegularHoursCalendar,
    build_default_market_data_gateway,
    build_market_data_gateway_for_mode,
)
from tradingx.dry_run_report import build_dry_run_report, write_dry_run_report
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
        gate_result = controller.generate_gate_report(
            gate_id=args.gate,
            benchmark_stack_payload=benchmark_stack_payload,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            universe=universe,
        )
        print(json.dumps(_serialize(gate_result), sort_keys=True))
        return 0

    if args.command == "gate3-report":
        validation_store = FilesystemArtifactStore(Path(args.validation_artifact_root))
        report = build_gate3_readiness_report(
            paper_store=FilesystemArtifactStore(Path(args.paper_artifact_root)),
            validation_store=validation_store,
        )
        validation_store.write_gate3_readiness_report(report)
        print(json.dumps(_serialize(report), sort_keys=True))
        return 0

    if args.command == "gate3-package":
        validation_store = FilesystemArtifactStore(Path(args.validation_artifact_root))
        report = build_gate3_readiness_report(
            paper_store=FilesystemArtifactStore(Path(args.paper_artifact_root)),
            validation_store=validation_store,
        )
        validation_store.write_gate3_readiness_report(report)
        package = build_gate3_promotion_package(report)
        validation_store.write_gate3_promotion_package(package)
        print(
            json.dumps(
                _serialize({"report": report, "package": package}),
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
