from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tradingx.config import TradingConfig
from tradingx.controller import (
    build_default_controller,
    build_default_paper_trading_controller,
)
from tradingx.persistence import FilesystemArtifactStore


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

    recover_parser = subparsers.add_parser("paper-recover")
    recover_parser.add_argument("--env-file", default=".env")
    recover_parser.add_argument("--symbol", default="SPY")

    live_disable_parser = subparsers.add_parser("live-disable-status")
    live_disable_parser.add_argument("--env-file", default=".env")

    evidence_parser = subparsers.add_parser("evidence-report")
    evidence_parser.add_argument("--artifact-root", default="artifacts/paper_loop")
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
