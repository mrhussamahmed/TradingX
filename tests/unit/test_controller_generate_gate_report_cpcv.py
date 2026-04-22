from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from tradingx.controller import GateValidationController
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import BenchmarkStackPayload, OperatingConstraintBudget


def _ohlcv_frame(*, periods: int) -> pd.DataFrame:
    index = pd.date_range("2023-01-03", periods=periods, freq="B", tz="UTC")
    close_series = pd.Series(
        [100.0 + (index_value * 0.25) for index_value in range(periods)],
        index=index,
        dtype=float,
    )
    return pd.DataFrame(
        {
            "open": close_series,
            "high": close_series * 1.01,
            "low": close_series * 0.99,
            "close": close_series,
            "bid": close_series - 0.05,
            "ask": close_series + 0.05,
            "volume": 1_000_000.0,
        },
        index=index,
    )


def _benchmark_stack_payload(*, periods: int) -> BenchmarkStackPayload:
    return BenchmarkStackPayload(
        hurdle_returns=tuple(Decimal("0.0002") for _ in range(periods)),
        opportunity_cost_returns=tuple(Decimal("0.0004") for _ in range(periods)),
        opportunity_cost_weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal("0.15"),
            max_drawdown_halt=Decimal("0.25"),
            cdar_threshold=Decimal("0.12"),
            cdar_confidence=Decimal("0.95"),
        ),
    )


class FakeHistoricalMarketDataGateway:
    def __init__(self, *, periods: int = 200) -> None:
        self.requested_symbols: list[str] = []
        self._bars_by_symbol = {
            "SPY": _ohlcv_frame(periods=periods),
            "QQQ": _ohlcv_frame(periods=periods),
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


def test_gate_validation_controller_writes_cpcv_trials_for_gate_1(tmp_path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )

    result = controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 6, 19, tzinfo=UTC),
        universe=("SPY", "QQQ"),
    )

    evidence_report = store.build_operator_evidence_report()

    assert result.report.gate_id == "1"
    assert evidence_report["counts"]["cpcv_trials"] == 90
    assert evidence_report["counts"]["pbo_reports"] == 0


def test_gate_validation_controller_does_not_write_cpcv_trials_for_gate_2(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )

    controller.generate_gate_report(
        gate_id="2",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 6, 19, tzinfo=UTC),
        universe=("SPY", "QQQ"),
    )

    evidence_report = store.build_operator_evidence_report()

    assert evidence_report["counts"]["cpcv_trials"] == 0


def test_gate_validation_controller_logs_and_continues_when_cpcv_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    controller = GateValidationController(
        artifacts=store,
        market_data=FakeHistoricalMarketDataGateway(),
    )

    def _boom(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise RuntimeError("boom")

    import tradingx.controller as controller_module

    monkeypatch.setattr(controller_module, "_run_cpcv_for_candidate", _boom)
    caplog.set_level("ERROR")

    result = controller.generate_gate_report(
        gate_id="1",
        benchmark_stack_payload=_benchmark_stack_payload(periods=200),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2023, 6, 19, tzinfo=UTC),
        universe=("SPY", "QQQ"),
    )

    assert result.report.gate_id == "1"
    assert store.build_operator_evidence_report()["counts"]["cpcv_trials"] == 0
    assert any("cpcv_run_failed" in record.message for record in caplog.records)
