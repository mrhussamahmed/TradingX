"""Active-sleeve daily attribution helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from tradingx.types import (
    PortfolioState,
    SleeveDailyAttributionRecord,
    StrategyActivationRecord,
    StrategyCandidate,
)


class AttributionStoreProtocol(Protocol):
    def write_sleeve_daily_attribution_record(
        self,
        record: SleeveDailyAttributionRecord,
    ) -> object: ...


class ActivationGatewayProtocol(Protocol):
    def get_latest_activation(self) -> StrategyActivationRecord | None: ...
    def get_active_candidate(self) -> StrategyCandidate | None: ...


def build_sleeve_daily_attribution_record(
    *,
    attribution_id: str,
    trading_day: str,
    active_sleeve_id: str,
    open_portfolio_state: PortfolioState,
    close_portfolio_state: PortfolioState,
    recorded_at_utc: datetime,
) -> SleeveDailyAttributionRecord:
    if open_portfolio_state.equity <= Decimal("0"):
        raise ValueError("starting_equity must be > 0 for an attribution record")
    daily_return = (
        close_portfolio_state.equity - open_portfolio_state.equity
    ) / open_portfolio_state.equity
    return SleeveDailyAttributionRecord(
        attribution_id=attribution_id,
        sleeve_id=active_sleeve_id,
        trading_day=trading_day,
        recorded_at_utc=recorded_at_utc.astimezone(UTC),
        starting_equity=open_portfolio_state.equity,
        ending_equity=close_portfolio_state.equity,
        daily_return=daily_return,
        per_symbol_open_weight=_state_to_weights(open_portfolio_state),
        per_symbol_close_weight=_state_to_weights(close_portfolio_state),
    )


class SleeveAttributionRecorder:
    def __init__(
        self,
        *,
        activation_gateway: ActivationGatewayProtocol,
        attribution_store: AttributionStoreProtocol,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._activation_gateway = activation_gateway
        self._store = attribution_store
        self._now_provider = now_provider

    def record_session(
        self,
        *,
        trading_day: str,
        open_portfolio_state: PortfolioState,
        close_portfolio_state: PortfolioState,
    ) -> SleeveDailyAttributionRecord | None:
        candidate = self._activation_gateway.get_active_candidate()
        if candidate is None or candidate.sleeve_class_path is None:
            return None
        record = build_sleeve_daily_attribution_record(
            attribution_id=f"{candidate.candidate_id}__{trading_day}",
            trading_day=trading_day,
            active_sleeve_id=candidate.candidate_id,
            open_portfolio_state=open_portfolio_state,
            close_portfolio_state=close_portfolio_state,
            recorded_at_utc=self._now_provider(),
        )
        self._store.write_sleeve_daily_attribution_record(record)
        return record


def _state_to_weights(state: PortfolioState) -> tuple[tuple[str, Decimal], ...]:
    if state.equity <= Decimal("0"):
        return ()
    return tuple(
        (position.symbol, position.market_value / state.equity)
        for position in state.positions
    )


__all__ = (
    "ActivationGatewayProtocol",
    "AttributionStoreProtocol",
    "SleeveAttributionRecorder",
    "build_sleeve_daily_attribution_record",
)
