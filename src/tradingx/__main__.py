from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alpaca.data.enums import Adjustment, DataFeed

from tradingx.alerts import build_gate_decision_alert
from tradingx.config import TradingConfig
from tradingx.controller import (
    build_default_controller,
    build_default_gate_validation_controller,
    build_default_paper_trading_controller,
)
from tradingx.data import build_default_market_data_gateway
from tradingx.persistence import FilesystemArtifactStore
from tradingx.reporting import build_gate_decision_brief
from tradingx.service import build_default_paper_service
from tradingx.validation import (
    load_benchmark_close_series,
    write_benchmark_close_series,
)


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
        paper_controller = build_default_paper_trading_controller(config)
        loop_result = paper_controller.run_trading_cycle(
            args.symbol, Decimal(args.quantity)
        )
        print(json.dumps(_serialize(loop_result), sort_keys=True))
        return 0

    if args.command == "run-paper-service":
        config = TradingConfig.from_env_file(Path(args.env_file))
        service = build_default_paper_service(config)
        symbols = (
            tuple(
                item.strip().upper() for item in args.symbols.split(",") if item.strip()
            )
            if args.symbols
            else config.runtime.symbol_universe
        )
        service_result = service.run(
            symbols=symbols,
            quantity=Decimal(args.quantity),
            interval_seconds=(
                args.interval_seconds or config.runtime.service_interval_seconds
            ),
            max_cycles=args.max_cycles,
        )
        print(json.dumps(_serialize(service_result), sort_keys=True))
        return 0

    if args.command == "paper-recover":
        config = TradingConfig.from_env_file(Path(args.env_file))
        paper_controller = build_default_paper_trading_controller(config)
        recovery_result = paper_controller.recover_trading_cycle(args.symbol)
        print(json.dumps(_serialize(recovery_result or {}), sort_keys=True))
        return 0

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

    config = TradingConfig.from_env_file(Path(args.env_file))
    roundtrip_controller = build_default_controller(config)
    log_dir = (
        Path(args.log_dir)
        if args.log_dir is not None
        else config.runtime.artifact_root / "smoke"
    )
    roundtrip_result = roundtrip_controller.run_paper_roundtrip(
        args.symbol,
        Decimal(args.quantity),
        log_dir=log_dir,
    )
    payload = {
        "symbol": roundtrip_result.symbol,
        "quantity": roundtrip_result.quantity,
        "quote": asdict(roundtrip_result.quote),
        "buy_order": asdict(roundtrip_result.buy_order),
        "sell_order": asdict(roundtrip_result.sell_order),
        "final_account": asdict(roundtrip_result.final_account),
        "final_position_quantity": roundtrip_result.final_position_quantity,
        "cash_delta": roundtrip_result.cash_delta,
        "log_path": roundtrip_result.log_path,
    }
    print(json.dumps(_serialize(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
