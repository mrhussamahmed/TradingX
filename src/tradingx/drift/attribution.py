"""Active-sleeve daily attribution helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from tradingx.types import (
    PortfolioState,
    SleeveDailyAttributionRecord,
    SleeveDecompositionRecord,
    StrategyActivationRecord,
    StrategyCandidate,
)


class AttributionStoreProtocol(Protocol):
    def write_sleeve_daily_attribution_record(
        self,
        record: SleeveDailyAttributionRecord,
    ) -> object: ...


class DecompositionStoreProtocol(Protocol):
    def list_sleeve_decomposition_records(
        self,
        *,
        trading_day: str,
    ) -> tuple[SleeveDecompositionRecord, ...]: ...


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
        decomposition_store: DecompositionStoreProtocol | None = None,
    ) -> None:
        self._activation_gateway = activation_gateway
        self._store = attribution_store
        self._now_provider = now_provider
        self._decomposition_store = decomposition_store

    def record_session(
        self,
        *,
        trading_day: str,
        open_portfolio_state: PortfolioState,
        close_portfolio_state: PortfolioState,
    ) -> tuple[SleeveDailyAttributionRecord, ...]:
        if self._decomposition_store is not None:
            decomposition_records = (
                self._decomposition_store.list_sleeve_decomposition_records(
                    trading_day=trading_day
                )
            )
            if decomposition_records:
                return self._record_from_decomposition(
                    trading_day=trading_day,
                    decomposition_records=decomposition_records,
                    open_portfolio_state=open_portfolio_state,
                    close_portfolio_state=close_portfolio_state,
                )
        candidate = self._activation_gateway.get_active_candidate()
        if candidate is None or candidate.sleeve_class_path is None:
            return ()
        record = build_sleeve_daily_attribution_record(
            attribution_id=f"{candidate.candidate_id}__{trading_day}",
            trading_day=trading_day,
            active_sleeve_id=candidate.candidate_id,
            open_portfolio_state=open_portfolio_state,
            close_portfolio_state=close_portfolio_state,
            recorded_at_utc=self._now_provider(),
        )
        self._store.write_sleeve_daily_attribution_record(record)
        return (record,)

    def _record_from_decomposition(
        self,
        *,
        trading_day: str,
        decomposition_records: tuple[SleeveDecompositionRecord, ...],
        open_portfolio_state: PortfolioState,
        close_portfolio_state: PortfolioState,
    ) -> tuple[SleeveDailyAttributionRecord, ...]:
        earliest = min(
            decomposition_records,
            key=lambda record: record.recorded_at_utc,
        )
        latest = max(
            decomposition_records,
            key=lambda record: record.recorded_at_utc,
        )
        open_weights_by_sleeve = {
            entry.sleeve_id: dict(entry.target_weights_by_symbol)
            for entry in earliest.per_sleeve_target_weights
        }
        close_weights_by_sleeve = {
            entry.sleeve_id: dict(entry.target_weights_by_symbol)
            for entry in latest.per_sleeve_target_weights
        }
        records: list[SleeveDailyAttributionRecord] = []
        recorded_at_utc = self._now_provider()
        portfolio_daily_return = (
            (close_portfolio_state.equity - open_portfolio_state.equity)
            / open_portfolio_state.equity
            if open_portfolio_state.equity > Decimal("0")
            else Decimal("0")
        )
        for sleeve_id in sorted(
            set(open_weights_by_sleeve) | set(close_weights_by_sleeve)
        ):
            open_weights = open_weights_by_sleeve.get(sleeve_id, {})
            close_weights = close_weights_by_sleeve.get(sleeve_id, {})
            open_fraction = sum(open_weights.values(), start=Decimal("0"))
            if open_fraction <= Decimal("0"):
                continue
            starting_equity = open_portfolio_state.equity * open_fraction
            ending_equity = starting_equity * (Decimal("1") + portfolio_daily_return)
            record = SleeveDailyAttributionRecord(
                attribution_id=f"{sleeve_id}__{trading_day}",
                sleeve_id=sleeve_id,
                trading_day=trading_day,
                recorded_at_utc=recorded_at_utc,
                starting_equity=starting_equity,
                ending_equity=ending_equity,
                daily_return=portfolio_daily_return,
                per_symbol_open_weight=tuple(sorted(open_weights.items())),
                per_symbol_close_weight=tuple(sorted(close_weights.items())),
            )
            self._store.write_sleeve_daily_attribution_record(record)
            records.append(record)
        return tuple(records)


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
    "DecompositionStoreProtocol",
    "SleeveAttributionRecorder",
    "build_sleeve_daily_attribution_record",
)
