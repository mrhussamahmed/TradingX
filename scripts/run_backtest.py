#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


def build_parser() -> argparse.ArgumentParser:
    from tradingx.risk_free import DEFAULT_RISK_FREE_CACHE_PATH

    parser = argparse.ArgumentParser(
        description="Run the TradingX SPY buy-and-hold smoke backtest."
    )
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--ohlcv-csv", required=True)
    parser.add_argument(
        "--risk-free-csv",
        default=str(DEFAULT_RISK_FREE_CACHE_PATH),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from tradingx.backtest import load_ohlcv_csv, run_buy_and_hold_smoke_backtest

    args = build_parser().parse_args(argv)
    bars = load_ohlcv_csv(Path(args.ohlcv_csv))
    summary = run_buy_and_hold_smoke_backtest(
        symbol=args.symbol,
        bars=bars,
        risk_free_cache_path=Path(args.risk_free_csv),
    )
    print(json.dumps(_serialize(summary), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
