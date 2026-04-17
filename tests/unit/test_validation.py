from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from decimal import Decimal

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


def test_validation_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.validation")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_build_gate1_report_passes_for_a_candidate_with_acceptability_edge() -> None:
    benchmark_closes = _build_close_series(
        periods=1200,
        up_return=Decimal("0.0030"),
        down_return=Decimal("-0.0015"),
        down_every=23,
    )
    report = build_gate_report(
        gate_id="1",
        benchmark_closes=benchmark_closes,
        candidates=build_mandatory_candidate_registry(("SPY", "QQQ")),
        window_start_utc=datetime(2023, 1, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        benchmark_series_is_adjusted=True,
    )

    trend_following = next(
        result
        for result in report.candidate_results
        if result.candidate_id == "trend-following-v1"
    )

    assert report.gate_id == "1"
    assert report.status == "pass"
    assert trend_following.status == "pass"
    assert any(
        criterion.criterion_id == "benchmark_edge" and criterion.passed
        for criterion in trend_following.criteria
    )
    assert any(
        criterion.criterion_id == "out_of_sample_profile" and criterion.passed
        for criterion in trend_following.criteria
    )


def test_build_gate2_report_is_pending_when_history_is_too_short() -> None:
    benchmark_closes = _build_close_series(
        periods=150,
        up_return=Decimal("0.0025"),
        down_return=Decimal("-0.0005"),
        down_every=19,
    )
    report = build_gate_report(
        gate_id="2",
        benchmark_closes=benchmark_closes,
        candidates=build_mandatory_candidate_registry(("SPY",)),
        window_start_utc=datetime(2025, 1, 1, tzinfo=UTC),
        window_end_utc=datetime(2025, 7, 1, tzinfo=UTC),
        benchmark_series_is_adjusted=True,
    )

    assert report.status == "pending"
    assert all(result.status == "pending" for result in report.candidate_results)
    assert any(
        criterion.criterion_id == "walk_forward_window"
        and not criterion.passed
        and "252 trading days" in criterion.details
        for criterion in report.candidate_results[0].criteria
    )


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
