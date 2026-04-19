from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.trading.client import TradingClient

from tradingx.activation import LocalActivationGateway
from tradingx.alerts import build_gate_decision_alert
from tradingx.automation import build_default_market_day_automation_runner
from tradingx.config import TradingConfig
from tradingx.controller import (
    build_default_controller,
    build_default_gate_validation_controller,
    build_default_paper_trading_controller,
)
from tradingx.data import build_default_market_data_gateway
from tradingx.dry_run_report import build_dry_run_report, write_dry_run_report
from tradingx.gate3 import build_gate3_promotion_package, build_gate3_readiness_report
from tradingx.historical import HistoricalWarmupService
from tradingx.journal import SqliteOmsJournal
from tradingx.learning import PostTradeLearningService
from tradingx.opportunity import RuntimeOpportunityPlanner
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio import AlpacaPortfolioGateway
from tradingx.process_lock import RuntimeLockError, runtime_process_lock
from tradingx.replay_slippage import generate_replay_slippage_evidence
from tradingx.reporting import build_gate_decision_brief
from tradingx.scheduler import build_default_market_day_scheduler
from tradingx.service import (
    build_default_paper_service,
    build_runtime_host_paper_service,
)
from tradingx.snapshots import ContentAddressedSnapshotStore
from tradingx.types import BotRuntimeState
from tradingx.validation import (
    load_benchmark_close_series,
    write_benchmark_close_series,
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


def _runtime_lock_path(config: TradingConfig) -> Path:
    return config.runtime.data_root / "runtime.pid"


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

    benchmark_prep_parser = subparsers.add_parser("prepare-benchmark-closes")
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

    gate_parser = subparsers.add_parser("gate-report")
    gate_parser.add_argument("--env-file", default=".env")
    gate_parser.add_argument("--gate", choices=("1", "2"), required=True)
    gate_parser.add_argument("--benchmark-closes-file", required=True)
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

    web_parser = subparsers.add_parser("web")
    web_parser.add_argument("--env-file", default=".env")
    web_parser.add_argument("--host", default=None)
    web_parser.add_argument("--port", type=int, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "config-summary":
        config = TradingConfig.from_env_file(Path(args.env_file))
        print(json.dumps(config.to_safe_summary(), sort_keys=True))
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
            operator_store = FilesystemArtifactStore(
                config.runtime.artifact_root / "operator_platform"
            )
            market_data_gateway = build_default_market_data_gateway(config)
            activation_gateway = LocalActivationGateway(store=operator_store)
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
            trading_client = TradingClient(
                config.paper_credentials.api_key,
                config.paper_credentials.api_secret,
                paper=True,
            )
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
            learning_proposal = PostTradeLearningService().generate_from_artifact_store(
                paper_store=FilesystemArtifactStore(
                    config.runtime.artifact_root / "paper_loop"
                ),
                activation=activation,
                baseline_snapshot=snapshot,
                minimum_supporting_trades=snapshot.minimum_supporting_trades,
            )
            if learning_proposal is not None:
                operator_store.write_model_weight_proposal(learning_proposal)
            runtime_service_result: Any | None = None
            if warmup_complete:
                runtime_service_result = build_runtime_host_paper_service(config).run(
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
                    "learning_proposal": learning_proposal,
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

    if args.command == "prepare-benchmark-closes":
        config = TradingConfig.from_env_file(Path(args.env_file))
        market_data_gateway = build_default_market_data_gateway(config)
        window_start_utc = datetime.fromisoformat(args.window_start).replace(tzinfo=UTC)
        window_end_utc = datetime.fromisoformat(args.window_end).replace(tzinfo=UTC)
        series = market_data_gateway.get_daily_close_series(
            args.symbol,
            start_utc=window_start_utc,
            end_utc=window_end_utc,
            feed=args.feed,
            adjustment=args.adjustment,
        )
        output_file = (
            Path(args.output_file)
            if args.output_file is not None
            else config.runtime.artifact_root
            / "validation"
            / "benchmarks"
            / (
                f"{args.symbol.lower()}-"
                f"{window_start_utc.date().isoformat()}-"
                f"{window_end_utc.date().isoformat()}-"
                f"{args.adjustment}.json"
            )
        )
        write_benchmark_close_series(output_file, series)
        print(
            json.dumps(
                _serialize(
                    {
                        "output_file": output_file,
                        "series": series,
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
        benchmark_series = load_benchmark_close_series(Path(args.benchmark_closes_file))
        if (
            benchmark_series.window_start_utc is not None
            and benchmark_series.window_start_utc != window_start_utc
        ):
            raise ValueError(
                "Benchmark closes artifact window start does not match "
                "the requested gate-report window."
            )
        if (
            benchmark_series.window_end_utc is not None
            and benchmark_series.window_end_utc != window_end_utc
        ):
            raise ValueError(
                "Benchmark closes artifact window end does not match "
                "the requested gate-report window."
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
            benchmark_closes=benchmark_series.closes,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            universe=universe,
            benchmark_series_is_adjusted=(
                args.benchmark_adjusted or benchmark_series.series_is_adjusted
            ),
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
