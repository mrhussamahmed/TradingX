"""Active-sleeve daily attribution helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from tradingx.drift.sleeve_ledger import (
    build_bootstrap_allocation,
    build_daily_ledger_result,
)
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    ExecutionLifecycleRecord,
    PortfolioState,
    ResidualReserveSnapshot,
    SleeveAttributionGapRecord,
    SleeveBootstrapAllocationRecord,
    SleeveDailyAttributionRecord,
    SleeveDecompositionRecord,
    SleevePositionLedgerSnapshot,
    StrategyActivationRecord,
    StrategyCandidate,
)


class AttributionStoreProtocol(Protocol):
    def latest_sleeve_bootstrap_allocation(
        self,
    ) -> SleeveBootstrapAllocationRecord | None: ...

    def latest_sleeve_position_ledger_snapshot(
        self,
        *,
        sleeve_id: str,
        before_trading_day: str | None = None,
        include_same_day_bootstrap: bool = False,
    ) -> SleevePositionLedgerSnapshot | None: ...

    def latest_residual_reserve_snapshot(
        self,
        *,
        before_trading_day: str | None = None,
        include_same_day_bootstrap: bool = False,
    ) -> ResidualReserveSnapshot | None: ...

    def write_sleeve_bootstrap_allocation_record(
        self,
        record: SleeveBootstrapAllocationRecord,
    ) -> object: ...

    def write_sleeve_position_ledger_snapshot(
        self,
        record: SleevePositionLedgerSnapshot,
    ) -> object: ...

    def write_residual_reserve_snapshot(
        self,
        record: ResidualReserveSnapshot,
    ) -> object: ...

    def write_sleeve_attribution_gap_record(
        self,
        record: SleeveAttributionGapRecord,
    ) -> object: ...

    def load_approved_weight_snapshot_by_snapshot_id(
        self, *, snapshot_id: str
    ) -> ApprovedWeightSnapshot: ...

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


class ExecutionStoreProtocol(Protocol):
    def list_execution_lifecycle_records(
        self,
        *,
        trading_day: str | None = None,
    ) -> tuple[ExecutionLifecycleRecord, ...]: ...


class ActivationGatewayProtocol(Protocol):
    def get_latest_activation(self) -> StrategyActivationRecord | None: ...
    def get_active_candidate(self) -> StrategyCandidate | None: ...
    def get_active_blueprint_activation(self) -> BlueprintActivationRecord | None: ...


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
        execution_store: ExecutionStoreProtocol | None = None,
    ) -> None:
        self._activation_gateway = activation_gateway
        self._store = attribution_store
        self._now_provider = now_provider
        self._decomposition_store = decomposition_store
        self._execution_store = execution_store

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
                return self._record_from_ledger(
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

    def _record_from_ledger(
        self,
        *,
        trading_day: str,
        decomposition_records: tuple[SleeveDecompositionRecord, ...],
        open_portfolio_state: PortfolioState,
        close_portfolio_state: PortfolioState,
    ) -> tuple[SleeveDailyAttributionRecord, ...]:
        recorded_at_utc = self._now_provider()
        activation_getter = getattr(
            self._activation_gateway,
            "get_active_blueprint_activation",
            None,
        )
        if not callable(activation_getter):
            return self._record_from_decomposition_legacy(
                trading_day=trading_day,
                decomposition_records=decomposition_records,
                open_portfolio_state=open_portfolio_state,
                close_portfolio_state=close_portfolio_state,
            )
        active_activation = activation_getter()
        if active_activation is None:
            return self._record_from_decomposition_legacy(
                trading_day=trading_day,
                decomposition_records=decomposition_records,
                open_portfolio_state=open_portfolio_state,
                close_portfolio_state=close_portfolio_state,
            )
        sleeve_ids = tuple(
            sorted(
                {
                    entry.sleeve_id
                    for record in decomposition_records
                    for entry in record.per_sleeve_target_weights
                }
            )
        )
        execution_records = (
            self._execution_store.list_execution_lifecycle_records(
                trading_day=trading_day
            )
            if self._execution_store is not None
            else ()
        )
        bootstrap_record = self._store.latest_sleeve_bootstrap_allocation()
        opening_snapshots = tuple(
            snapshot
            for sleeve_id in sleeve_ids
            if (
                snapshot := self._store.latest_sleeve_position_ledger_snapshot(
                    sleeve_id=sleeve_id,
                    before_trading_day=trading_day,
                    include_same_day_bootstrap=True,
                )
            )
            is not None
        )
        opening_reserve = self._store.latest_residual_reserve_snapshot(
            before_trading_day=trading_day,
            include_same_day_bootstrap=True,
        )
        if (
            bootstrap_record is None
            or len(opening_snapshots) != len(sleeve_ids)
            or opening_reserve is None
        ):
            if self._execution_store is None:
                return ()
            bootstrap = build_bootstrap_allocation(
                active_activation=active_activation,
                snapshot_store=self._store,  # type: ignore[arg-type]
                open_portfolio_state=open_portfolio_state,
                historical_execution_records=self._execution_store.list_execution_lifecycle_records(),
                recorded_at_utc=recorded_at_utc,
            )
            bootstrap_record = bootstrap.bootstrap_record
            opening_snapshots = bootstrap.sleeve_snapshots
            opening_reserve = bootstrap.residual_reserve_snapshot
            self._store.write_sleeve_bootstrap_allocation_record(
                bootstrap.bootstrap_record
            )
            for snapshot in bootstrap.sleeve_snapshots:
                self._store.write_sleeve_position_ledger_snapshot(snapshot)
            self._store.write_residual_reserve_snapshot(
                bootstrap.residual_reserve_snapshot
            )

        result = build_daily_ledger_result(
            opening_snapshots=opening_snapshots,
            opening_reserve_snapshot=opening_reserve,
            bootstrap_record=bootstrap_record,
            execution_records=execution_records,
            open_portfolio_state=open_portfolio_state,
            close_portfolio_state=close_portfolio_state,
            trading_day=trading_day,
            recorded_at_utc=recorded_at_utc,
            active_blueprint_activation_id=active_activation.activation_id,
        )
        for snapshot in result.sleeve_snapshots:
            self._store.write_sleeve_position_ledger_snapshot(snapshot)
        self._store.write_residual_reserve_snapshot(result.residual_reserve_snapshot)
        for record in result.attribution_records:
            self._store.write_sleeve_daily_attribution_record(record)
        for gap in result.gap_records:
            self._store.write_sleeve_attribution_gap_record(gap)
        return result.attribution_records

    def _record_from_decomposition_legacy(
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
    "ExecutionStoreProtocol",
    "SleeveAttributionRecorder",
    "build_sleeve_daily_attribution_record",
)
