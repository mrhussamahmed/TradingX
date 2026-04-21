from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from tradingx.controller import GateValidationController
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import BenchmarkStackPayload, OperatingConstraintBudget


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


def _benchmark_stack_payload(
    *,
    periods: int,
    hurdle_return: Decimal = Decimal("0.0002"),
    opportunity_cost_return: Decimal = Decimal("0.0004"),
) -> BenchmarkStackPayload:
    return BenchmarkStackPayload(
        hurdle_returns=tuple(hurdle_return for _ in range(periods)),
        opportunity_cost_returns=tuple(opportunity_cost_return for _ in range(periods)),
        opportunity_cost_weights=(
            ("SPY", Decimal("0.6")),
            ("AGG", Decimal("0.4")),
        ),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal("0.15"),
            max_drawdown_halt=Decimal("0.25"),
            cdar_threshold=Decimal("0.12"),
            cdar_confidence=Decimal("0.95"),
        ),
    )


class FakeHistoricalMarketDataGateway:
    def __init__(self) -> None:
        self.requested_symbols: list[str] = []
        self._bars_by_symbol = {
            "SPY": _ohlcv_frame(
                [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]
            ),
            "QQQ": _ohlcv_frame(
                [100.0, 100.5, 101.0, 102.0, 101.0, 102.5, 103.0, 104.0]
            ),
        }

    def get_daily_bar_history(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
        feed: str = "iex",
        adjustment: str = "dividend",
    ) -> pd.DataFrame:
        del start_utc, end_utc, feed, adjustment
        self.requested_symbols.append(symbol)
        return self._bars_by_symbol[symbol].copy()


def test_gate_validation_pipeline_persists_report_and_assessment(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )

    result = controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=8),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 1, 12, tzinfo=UTC),
        universe=("SPY", "QQQ"),
    )

    assert result.report.gate_id == "1"
    assert result.gate_assessment.gate_id == "1"
    assert result.report.benchmark_symbol == "SPY+AGG"
    report_files = sorted((tmp_path / "validation_reports").glob("*.json"))
    assessment_files = sorted((tmp_path / "gate_assessments").glob("*.json"))
    assert len(report_files) == 1
    assert len(assessment_files) == 1


def test_gate_validation_pipeline_rejects_mismatched_benchmark_stack(tmp_path) -> None:
    controller = GateValidationController(
        artifacts=FilesystemArtifactStore(tmp_path),
        market_data=FakeHistoricalMarketDataGateway(),
    )

    with pytest.raises(
        ValueError,
        match="benchmark_stack_payload.hurdle_returns must align",
    ):
        controller.generate_gate_report(
            gate_id="1",
            benchmark_stack_payload=_benchmark_stack_payload(periods=7),
            window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
            window_end_utc=datetime(2023, 1, 12, tzinfo=UTC),
            universe=("SPY", "QQQ"),
        )
