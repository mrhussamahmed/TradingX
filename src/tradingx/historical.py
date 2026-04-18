from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from tradingx.data import close_to_close_returns
from tradingx.quant import decimal_mean, decimal_stddev
from tradingx.types import BenchmarkCloseSeries, HistoricalWarmupRecord


class HistoricalSeriesGatewayProtocol(Protocol):
    def get_daily_close_series(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ) -> BenchmarkCloseSeries: ...


class HistoricalWarmupService:
    def __init__(
        self,
        *,
        market_data_gateway: HistoricalSeriesGatewayProtocol,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._market_data_gateway = market_data_gateway
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def build_warmup(
        self,
        *,
        symbols: Sequence[str],
        benchmark_symbol: str,
        warmup_days: int,
        required_bar_count: int,
    ) -> HistoricalWarmupRecord:
        end_utc = self._now_provider()
        start_utc = end_utc - timedelta(days=warmup_days)
        symbols_ready: list[str] = []
        symbols_blocked: dict[str, str] = {}
        return_summary: dict[str, dict[str, Decimal]] = {}

        for symbol in tuple(symbols) + (benchmark_symbol,):
            series = self._market_data_gateway.get_daily_close_series(
                symbol,
                start_utc=start_utc,
                end_utc=end_utc,
            )
            closes = series.closes
            if len(closes) < required_bar_count:
                if symbol != benchmark_symbol:
                    symbols_blocked[symbol] = "insufficient_bars"
                continue

            returns = close_to_close_returns(closes)
            cumulative_return = (
                Decimal("0")
                if closes[0] == Decimal("0")
                else (closes[-1] - closes[0]) / closes[0]
            )
            return_summary[symbol] = {
                "cumulative_return": cumulative_return,
                "mean_return": decimal_mean(list(returns)),
                "volatility": decimal_stddev(list(returns)),
            }
            if symbol != benchmark_symbol:
                symbols_ready.append(symbol)

        return HistoricalWarmupRecord(
            warmup_id=f"warmup-{uuid.uuid4()}",
            generated_at_utc=end_utc,
            benchmark_symbol=benchmark_symbol,
            symbols=tuple(symbols),
            window_start_utc=start_utc,
            window_end_utc=end_utc,
            required_bar_count=required_bar_count,
            symbols_ready=tuple(symbols_ready),
            symbols_blocked=symbols_blocked,
            return_summary=return_summary,
        )


__all__ = ("HistoricalWarmupService",)
