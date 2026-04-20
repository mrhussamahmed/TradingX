from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.historical import HistoricalWarmupService
from tradingx.types import BenchmarkCloseSeries


class _FakeHistoricalSeriesGateway:
    def get_daily_close_series(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> BenchmarkCloseSeries:
        del start_utc, end_utc
        closes = tuple(Decimal("100") + Decimal(index) for index in range(35))
        return BenchmarkCloseSeries(
            symbol=symbol,
            closes=closes,
            window_start_utc=datetime(2026, 2, 1, tzinfo=UTC),
            window_end_utc=datetime(2026, 4, 20, tzinfo=UTC),
            generated_at_utc=datetime(2026, 4, 20, tzinfo=UTC),
            feed="iex",
            adjustment="dividend",
            series_is_adjusted=True,
        )


def test_historical_warmup_marks_symbol_ready_when_symbol_matches_benchmark() -> None:
    service = HistoricalWarmupService(
        market_data_gateway=_FakeHistoricalSeriesGateway(),
        now_provider=lambda: datetime(2026, 4, 20, 14, 20, tzinfo=UTC),
    )

    warmup = service.build_warmup(
        symbols=("SPY",),
        benchmark_symbol="SPY",
        warmup_days=60,
        required_bar_count=30,
    )

    assert warmup.symbols_ready == ("SPY",)
    assert warmup.symbols_blocked == {}
    assert "SPY" in warmup.return_summary
