from __future__ import annotations

import importlib
import json
from decimal import Decimal

import pandas as pd

from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.validation import build_gate_report


def _build_close_series(
    *,
    periods: int,
    up_return: Decimal,
    down_return: Decimal,
    down_every: int,
    start_price: Decimal = Decimal("100"),
) -> tuple[Decimal, ...]:
    closes = [start_price]
    price = start_price
    for index in range(periods):
        daily_return = down_return if index % down_every == 0 else up_return
        price *= Decimal("1") + daily_return
        closes.append(price.quantize(Decimal("0.0001")))
    return tuple(closes)


def _ohlcv_frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2023-01-03", periods=len(closes), freq="B", tz="UTC")
    close_series = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close_series,
            "high": close_series * 1.01,
            "low": close_series * 0.99,
            "close": close_series,
            "volume": 1_000_000.0,
        },
        index=index,
    )


def test_validation_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.validation")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_build_gate_report_runs_real_backtests_from_daily_bars() -> None:
    bars_by_symbol = {
        "SPY": _ohlcv_frame(
            [
                100.0,
                101.0,
                102.0,
                103.0,
                104.0,
                105.0,
                106.0,
                107.0,
                108.0,
                109.0,
            ]
        ),
        "QQQ": _ohlcv_frame(
            [
                100.0,
                100.5,
                101.0,
                102.0,
                101.0,
                102.5,
                103.0,
                104.0,
                103.5,
                104.5,
            ]
        ),
    }
    candidates = build_mandatory_candidate_registry(("SPY", "QQQ"))

    report = build_gate_report(
        gate_id="1",
        bars_by_symbol=bars_by_symbol,
        candidates=candidates,
        benchmark_symbol="SPY",
        window_start_utc=bars_by_symbol["SPY"].index[0].to_pydatetime(),
        window_end_utc=bars_by_symbol["SPY"].index[-1].to_pydatetime(),
        benchmark_series_is_adjusted=True,
    )

    assert report.gate_id == "1"
    assert report.benchmark_symbol == "SPY"
    assert len(report.candidate_results) == 3
    assert {result.candidate_id for result in report.candidate_results} == {
        "trend-following-v1",
        "vol-target-v1",
        "mean-reversion-v1",
    }
    assert all(result.evidence_pack_id for result in report.candidate_results)


def test_load_benchmark_close_series_reads_metadata_rich_artifact(tmp_path) -> None:
    module = importlib.import_module("tradingx.validation")
    artifact_file = tmp_path / "spy-dividend-benchmark.json"
    artifact_file.write_text(
        json.dumps(
            {
                "symbol": "SPY",
                "window_start_utc": "2023-01-01T00:00:00+00:00",
                "window_end_utc": "2026-04-17T00:00:00+00:00",
                "generated_at_utc": "2026-04-17T21:15:00+00:00",
                "feed": "iex",
                "adjustment": "dividend",
                "series_is_adjusted": True,
                "closes": ["100", "101.5", "102.25"],
            }
        ),
        encoding="utf-8",
    )

    series = module.load_benchmark_close_series(artifact_file)

    assert series.symbol == "SPY"
    assert series.series_is_adjusted is True
    assert series.feed == "iex"
    assert series.adjustment == "dividend"
    assert series.closes == (
        Decimal("100"),
        Decimal("101.5"),
        Decimal("102.25"),
    )
