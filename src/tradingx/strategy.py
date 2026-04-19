"""Deterministic Stage 1 strategy generation."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.data import close_to_close_returns
from tradingx.types import (
    MarketSnapshot,
    PortfolioState,
    PositionSnapshot,
    StrategyCandidate,
    TradeIntent,
)

DEFAULT_CANDIDATE_ID = "baseline-long-only-v1"
MAX_SPREAD_BPS = Decimal("20")


def _normalize_quantity(quantity: Decimal | None) -> str:
    if quantity is None:
        return "none"
    return format(quantity.normalize(), "f")


def build_mandatory_candidate_registry(
    universe: Sequence[str],
    *,
    benchmark_symbol: str = "SPY",
) -> tuple[StrategyCandidate, ...]:
    normalized_universe = tuple(universe)
    return (
        StrategyCandidate(
            candidate_id="trend-following-v1",
            family="trend_following",
            benchmark_symbol=benchmark_symbol,
            universe=normalized_universe,
            parameter_set={
                "lookback_days": 252,
                "sma_window_days": 200,
                "skip_recent_days": 1,
                "signal": "long_only",
            },
            status="under_evaluation",
        ),
        StrategyCandidate(
            candidate_id="vol-target-v1",
            family="vol_target",
            benchmark_symbol=benchmark_symbol,
            universe=normalized_universe,
            parameter_set={
                "target_volatility": Decimal("0.12"),
                "realized_vol_window_days": 20,
                "max_gross_leverage": Decimal("1.0"),
            },
            status="under_evaluation",
        ),
        StrategyCandidate(
            candidate_id="mean-reversion-v1",
            family="mean_reversion",
            benchmark_symbol=benchmark_symbol,
            universe=normalized_universe,
            parameter_set={
                "beta_window_days": 60,
                "residual_sum_days": 5,
                "zscore_window_days": 60,
                "zscore_threshold": Decimal("2.0"),
            },
            status="under_evaluation",
        ),
    )


def build_candidate_return_series(
    candidate: StrategyCandidate,
    benchmark_closes: Sequence[Decimal],
) -> tuple[Decimal, ...]:
    raw_returns = close_to_close_returns(benchmark_closes)
    if candidate.family == "trend_following":
        return tuple(max(Decimal("0"), value) for value in raw_returns)
    if candidate.family == "vol_target":
        return tuple(value * Decimal("0.80") for value in raw_returns)
    if candidate.family == "mean_reversion":
        return tuple(value * Decimal("0.60") for value in raw_returns)
    raise ValueError(f"Unsupported candidate family: {candidate.family}")


@dataclass(frozen=True)
class DeterministicBaselineStrategy:
    candidate_id: str = DEFAULT_CANDIDATE_ID
    max_spread_bps: Decimal = MAX_SPREAD_BPS
    take_profit_bps: Decimal = Decimal("100")
    stop_loss_bps: Decimal = Decimal("100")
    now_provider: Callable[[], datetime] = lambda: datetime.now(UTC)

    def generate_trade_intent(
        self,
        *,
        market_snapshot: MarketSnapshot,
        portfolio_state: PortfolioState,
        quantity: Decimal,
    ) -> TradeIntent:
        existing_position = self._position_for_symbol(
            portfolio_state, market_snapshot.symbol
        )
        if existing_position is not None:
            if market_snapshot.last_trade_price >= (
                existing_position.average_entry_price
                * (Decimal("1") + (self.take_profit_bps / Decimal("10000")))
            ):
                return self._build_intent(
                    symbol=market_snapshot.symbol,
                    side="sell",
                    quantity=existing_position.quantity,
                    reason_code="take_profit_exit",
                    observation_timestamp=market_snapshot.timestamp,
                )
            if market_snapshot.last_trade_price <= (
                existing_position.average_entry_price
                * (Decimal("1") - (self.stop_loss_bps / Decimal("10000")))
            ):
                return self._build_intent(
                    symbol=market_snapshot.symbol,
                    side="sell",
                    quantity=existing_position.quantity,
                    reason_code="stop_loss_exit",
                    observation_timestamp=market_snapshot.timestamp,
                )
            return self._build_intent(
                symbol=market_snapshot.symbol,
                side="hold",
                quantity=None,
                reason_code="existing_position_hold",
                observation_timestamp=market_snapshot.timestamp,
            )

        if self._spread_bps(market_snapshot) > self.max_spread_bps:
            return self._build_intent(
                symbol=market_snapshot.symbol,
                side="skip",
                quantity=None,
                reason_code="spread_too_wide",
                observation_timestamp=market_snapshot.timestamp,
            )

        return self._build_intent(
            symbol=market_snapshot.symbol,
            side="buy",
            quantity=quantity,
            reason_code="baseline_long_entry",
            observation_timestamp=market_snapshot.timestamp,
        )

    def _build_intent(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal | None,
        reason_code: str,
        observation_timestamp: datetime,
    ) -> TradeIntent:
        intent_id = self._build_intent_id(
            symbol=symbol,
            side=side,
            quantity=quantity,
            observation_timestamp=observation_timestamp,
        )
        return TradeIntent(
            intent_id=intent_id,
            candidate_id=self.candidate_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            reason_code=reason_code,
            generated_at_utc=self.now_provider(),
        )

    def _build_intent_id(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal | None,
        observation_timestamp: datetime,
    ) -> str:
        payload = "|".join(
            (
                self.candidate_id,
                symbol,
                side,
                _normalize_quantity(quantity),
                observation_timestamp.astimezone(UTC).isoformat(),
            )
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, payload))

    def _position_for_symbol(
        self,
        portfolio_state: PortfolioState,
        symbol: str,
    ) -> PositionSnapshot | None:
        for position in portfolio_state.positions:
            if position.symbol == symbol and position.quantity != Decimal("0"):
                return position
        return None

    def _spread_bps(self, market_snapshot: MarketSnapshot) -> Decimal:
        if market_snapshot.last_trade_price <= Decimal("0"):
            return Decimal("Infinity")
        spread = market_snapshot.ask_price - market_snapshot.bid_price
        return (spread / market_snapshot.last_trade_price) * Decimal("10000")


__all__ = (
    "DEFAULT_CANDIDATE_ID",
    "DeterministicBaselineStrategy",
    "build_candidate_return_series",
    "build_mandatory_candidate_registry",
)
