"""Long-only mean-reversion sleeve."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.signals.mean_revert import generate_mean_revert_signal
from tradingx.sleeves.trend import _derive_side
from tradingx.types import SleeveContext, SleeveFailureReason, SleeveTrade


@dataclass(frozen=True)
class MeanReversionSleeve:
    sleeve_id: str = "mean-reversion-v1"
    family: str = "mean_reversion"
    benchmark_symbol: str = "SPY"
    beta_window_days: int = 60
    residual_sum_days: int = 5
    zscore_window_days: int = 60
    zscore_threshold: Decimal = Decimal("2.0")
    target_weight: Decimal = Decimal("1")
    allowed_instruments: tuple[str, ...] = ()

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        tradable_symbols = tuple(
            symbol
            for symbol in self.allowed_instruments
            if symbol != self.benchmark_symbol
        )
        trades: list[SleeveTrade] = []
        if not tradable_symbols:
            return ()

        required_symbols = (self.benchmark_symbol, *tradable_symbols)
        missing_symbols = tuple(
            symbol
            for symbol in required_symbols
            if symbol not in context.bars_by_symbol
        )
        if missing_symbols:
            return tuple(
                self._hold_trade(
                    symbol=symbol,
                    context=context,
                    rationale=SleeveFailureReason.INSUFFICIENT_HISTORY,
                )
                for symbol in tradable_symbols
            )

        min_required = (
            int(self.beta_window_days)
            + int(self.residual_sum_days)
            + int(self.zscore_window_days)
        )
        if any(
            len(context.bars_by_symbol[symbol]) < min_required
            for symbol in required_symbols
        ):
            return tuple(
                self._hold_trade(
                    symbol=symbol,
                    context=context,
                    rationale=SleeveFailureReason.INSUFFICIENT_HISTORY,
                )
                for symbol in tradable_symbols
            )

        signal_frame = generate_mean_revert_signal(
            _wide_ohlcv(context.bars_by_symbol, required_symbols),
            benchmark_symbol=self.benchmark_symbol,
            tradable_symbols=tradable_symbols,
            beta_window_days=int(self.beta_window_days),
            residual_sum_days=int(self.residual_sum_days),
            zscore_window_days=int(self.zscore_window_days),
            zscore_threshold=float(self.zscore_threshold),
        )
        for symbol in tradable_symbols:
            current_weight = context.current_weights_by_symbol.get(
                symbol,
                Decimal("0"),
            )
            if symbol not in signal_frame.columns or signal_frame.empty:
                trades.append(
                    self._hold_trade(
                        symbol=symbol,
                        context=context,
                        rationale=SleeveFailureReason.INSUFFICIENT_HISTORY,
                    )
                )
                continue
            signal_value = signal_frame[symbol].iloc[-1]
            if pd.isna(signal_value):
                trades.append(
                    self._hold_trade(
                        symbol=symbol,
                        context=context,
                        rationale=SleeveFailureReason.INSUFFICIENT_HISTORY,
                    )
                )
                continue
            target_weight = (
                min(max(self.target_weight, Decimal("0")), Decimal("1"))
                if float(signal_value) > 0.0
                else Decimal("0")
            )
            trades.append(
                SleeveTrade(
                    sleeve_id=self.sleeve_id,
                    symbol=symbol,
                    side=_derive_side(current_weight, target_weight),
                    target_weight_of_sleeve_budget=target_weight,
                    rationale=(
                        "mean_reversion_long"
                        if target_weight > Decimal("0")
                        else "mean_reversion_flat"
                    ),
                    regime=context.regime.regime,
                )
            )
        return tuple(trades)

    def _hold_trade(
        self,
        *,
        symbol: str,
        context: SleeveContext,
        rationale: str,
    ) -> SleeveTrade:
        current_weight = context.current_weights_by_symbol.get(symbol, Decimal("0"))
        return SleeveTrade(
            sleeve_id=self.sleeve_id,
            symbol=symbol,
            side="hold",
            target_weight_of_sleeve_budget=current_weight,
            rationale=rationale,
            regime=context.regime.regime,
        )


def _wide_ohlcv(
    bars_by_symbol: dict[str, pd.DataFrame],
    symbols: tuple[str, ...],
) -> pd.DataFrame:
    return pd.concat(
        {symbol: bars_by_symbol[symbol] for symbol in symbols},
        axis=1,
    )


__all__ = ("MeanReversionSleeve",)
