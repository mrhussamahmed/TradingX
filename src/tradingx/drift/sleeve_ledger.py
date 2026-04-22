from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import load_portfolio_blueprint
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.types import (
    BlueprintActivationRecord,
    BootstrapPositionAllocation,
    ExecutionLifecycleRecord,
    PortfolioState,
    ResidualPositionAllocation,
    ResidualReserveSnapshot,
    SleeveAttributionGapRecord,
    SleeveBootstrapAllocationRecord,
    SleeveDailyAttributionRecord,
    SleeveLedgerPosition,
    SleevePositionLedgerSnapshot,
    StrategyCandidate,
)

RESIDUAL_RESERVE_OWNER_ID = "__residual_reserve__"
_TOLERANCE = Decimal("0.000001")
_ROUNDING_TOLERANCE = Decimal("0.0001")


@dataclass(frozen=True)
class BootstrapResult:
    bootstrap_record: SleeveBootstrapAllocationRecord
    sleeve_snapshots: tuple[SleevePositionLedgerSnapshot, ...]
    residual_reserve_snapshot: ResidualReserveSnapshot


@dataclass(frozen=True)
class DailyLedgerResult:
    sleeve_snapshots: tuple[SleevePositionLedgerSnapshot, ...]
    residual_reserve_snapshot: ResidualReserveSnapshot
    attribution_records: tuple[SleeveDailyAttributionRecord, ...]
    gap_records: tuple[SleeveAttributionGapRecord, ...]


@dataclass
class _MutablePosition:
    quantity: Decimal
    average_cost: Decimal
    realized_pnl_cumulative: Decimal


@dataclass
class _MutableSleeveState:
    sleeve_id: str
    cash_balance: Decimal
    positions: dict[str, _MutablePosition]


@dataclass
class _MutableReserveState:
    cash_balance: Decimal
    positions: dict[str, ResidualPositionAllocation]


def build_bootstrap_allocation(
    *,
    active_activation: BlueprintActivationRecord,
    snapshot_store: FilesystemArtifactStore,
    open_portfolio_state: PortfolioState,
    historical_execution_records: tuple[ExecutionLifecycleRecord, ...],
    recorded_at_utc: datetime,
) -> BootstrapResult:
    active_blueprint = load_portfolio_blueprint(active_activation.source_blueprint_path)
    budget_by_sleeve_id = {
        budget.sleeve_id: budget
        for budget in active_blueprint.sleeve_budgets
        if budget.sleeve_id
        in {
            binding.sleeve_id
            for binding in active_activation.sleeve_activation_bindings
        }
    }
    candidate_by_strategy_id = {
        candidate.candidate_id: candidate
        for candidate in build_mandatory_candidate_registry()
    }
    owner_sleeve_ids = tuple(
        sorted(
            binding.sleeve_id
            for binding in active_activation.sleeve_activation_bindings
        )
    )
    allocations: list[BootstrapPositionAllocation] = []
    residual_positions: list[ResidualPositionAllocation] = []

    for position in sorted(
        open_portfolio_state.positions, key=lambda item: item.symbol
    ):
        if position.quantity <= Decimal("0"):
            continue
        history_allocations = _history_allocations_for_symbol(
            symbol=position.symbol,
            broker_quantity=position.quantity,
            execution_records=historical_execution_records,
            broker_average_entry_price=position.average_entry_price,
            broker_market_value=position.market_value,
        )
        if history_allocations is not None:
            allocations.extend(history_allocations)
            continue

        fallback = _blueprint_fallback_allocations_for_symbol(
            symbol=position.symbol,
            broker_quantity=position.quantity,
            broker_average_entry_price=position.average_entry_price,
            broker_market_value=position.market_value,
            active_activation=active_activation,
            snapshot_store=snapshot_store,
            budget_by_sleeve_id=budget_by_sleeve_id,
            candidate_by_strategy_id=candidate_by_strategy_id,
        )
        if fallback:
            allocations.extend(fallback)
            continue

        residual_positions.append(
            ResidualPositionAllocation(
                symbol=position.symbol,
                quantity=position.quantity,
                average_cost=position.average_entry_price,
                market_value=position.market_value,
                reason="no_active_owner",
                evidence_refs=(),
            )
        )

    payload = "|".join(
        [
            active_activation.activation_id,
            open_portfolio_state.as_of_utc.astimezone(UTC).isoformat(),
            *(
                f"{position.symbol}:{position.quantity}:{position.average_entry_price}"
                for position in sorted(
                    open_portfolio_state.positions, key=lambda item: item.symbol
                )
                if position.quantity > Decimal("0")
            ),
        ]
    )
    ledger_genesis_id = f"ledger-{uuid.uuid5(uuid.NAMESPACE_URL, payload)}"
    bootstrap_id = f"bootstrap-{uuid.uuid5(uuid.NAMESPACE_OID, payload)}"
    bootstrap_record = SleeveBootstrapAllocationRecord(
        bootstrap_id=bootstrap_id,
        ledger_genesis_id=ledger_genesis_id,
        bootstrapped_from_activation_id=active_activation.activation_id,
        trading_day=open_portfolio_state.as_of_utc.date().isoformat(),
        recorded_at_utc=recorded_at_utc.astimezone(UTC),
        position_allocations=tuple(
            sorted(allocations, key=lambda item: (item.sleeve_id, item.symbol))
        ),
        residual_cash_balance=open_portfolio_state.cash,
        residual_positions=tuple(
            sorted(residual_positions, key=lambda item: item.symbol)
        ),
        notes=(),
    )

    position_allocations_by_sleeve: dict[str, list[SleeveLedgerPosition]] = {
        sleeve_id: [] for sleeve_id in owner_sleeve_ids
    }
    for allocation in bootstrap_record.position_allocations:
        position_allocations_by_sleeve.setdefault(allocation.sleeve_id, []).append(
            SleeveLedgerPosition(
                sleeve_id=allocation.sleeve_id,
                symbol=allocation.symbol,
                quantity=allocation.quantity,
                average_cost=allocation.average_cost,
                realized_pnl_cumulative=Decimal("0"),
            )
        )

    sleeve_snapshots = tuple(
        SleevePositionLedgerSnapshot(
            snapshot_id=f"bootstrap-{ledger_genesis_id}__{sleeve_id}",
            ledger_genesis_id=ledger_genesis_id,
            active_blueprint_activation_id=active_activation.activation_id,
            trading_day=bootstrap_record.trading_day,
            recorded_at_utc=recorded_at_utc.astimezone(UTC),
            sleeve_id=sleeve_id,
            cash_balance=Decimal("0"),
            positions=tuple(
                sorted(
                    position_allocations_by_sleeve.get(sleeve_id, ()),
                    key=lambda item: item.symbol,
                )
            ),
            bootstrap_id=bootstrap_id,
        )
        for sleeve_id in owner_sleeve_ids
    )
    residual_reserve_snapshot = ResidualReserveSnapshot(
        snapshot_id=f"bootstrap-{ledger_genesis_id}__reserve",
        ledger_genesis_id=ledger_genesis_id,
        active_blueprint_activation_id=active_activation.activation_id,
        trading_day=bootstrap_record.trading_day,
        recorded_at_utc=recorded_at_utc.astimezone(UTC),
        cash_balance=open_portfolio_state.cash,
        positions=bootstrap_record.residual_positions,
        bootstrap_id=bootstrap_id,
    )
    return BootstrapResult(
        bootstrap_record=bootstrap_record,
        sleeve_snapshots=sleeve_snapshots,
        residual_reserve_snapshot=residual_reserve_snapshot,
    )


def build_daily_ledger_result(
    *,
    opening_snapshots: tuple[SleevePositionLedgerSnapshot, ...],
    opening_reserve_snapshot: ResidualReserveSnapshot,
    bootstrap_record: SleeveBootstrapAllocationRecord,
    execution_records: tuple[ExecutionLifecycleRecord, ...],
    open_portfolio_state: PortfolioState,
    close_portfolio_state: PortfolioState,
    trading_day: str,
    recorded_at_utc: datetime,
    active_blueprint_activation_id: str,
) -> DailyLedgerResult:
    mutable_sleeves = {
        snapshot.sleeve_id: _MutableSleeveState(
            sleeve_id=snapshot.sleeve_id,
            cash_balance=snapshot.cash_balance,
            positions={
                position.symbol: _MutablePosition(
                    quantity=position.quantity,
                    average_cost=position.average_cost,
                    realized_pnl_cumulative=position.realized_pnl_cumulative,
                )
                for position in snapshot.positions
            },
        )
        for snapshot in opening_snapshots
    }
    mutable_reserve = _MutableReserveState(
        cash_balance=opening_reserve_snapshot.cash_balance,
        positions={
            position.symbol: position for position in opening_reserve_snapshot.positions
        },
    )
    opening_realized_by_sleeve = {
        snapshot.sleeve_id: sum(
            (position.realized_pnl_cumulative for position in snapshot.positions),
            start=Decimal("0"),
        )
        for snapshot in opening_snapshots
    }
    cash_flows_by_sleeve: dict[str, list[tuple[datetime, Decimal]]] = {
        snapshot.sleeve_id: [] for snapshot in opening_snapshots
    }
    gap_by_sleeve_id: dict[str, SleeveAttributionGapRecord] = {}

    for execution in sorted(
        execution_records,
        key=lambda item: (item.filled_at_utc, item.execution_id),
    ):
        gap = _apply_execution(
            execution=execution,
            sleeves=mutable_sleeves,
            reserve=mutable_reserve,
            cash_flows_by_sleeve=cash_flows_by_sleeve,
            trading_day=trading_day,
            recorded_at_utc=recorded_at_utc,
        )
        for sleeve_id, record in gap.items():
            gap_by_sleeve_id.setdefault(sleeve_id, record)

    closing_snapshots = tuple(
        SleevePositionLedgerSnapshot(
            snapshot_id=f"close-{opening_snapshot.ledger_genesis_id}__{opening_snapshot.sleeve_id}__{trading_day}",
            ledger_genesis_id=opening_snapshot.ledger_genesis_id,
            active_blueprint_activation_id=active_blueprint_activation_id,
            trading_day=trading_day,
            recorded_at_utc=recorded_at_utc.astimezone(UTC),
            sleeve_id=opening_snapshot.sleeve_id,
            cash_balance=mutable_sleeves[opening_snapshot.sleeve_id].cash_balance,
            positions=tuple(
                sorted(
                    (
                        SleeveLedgerPosition(
                            sleeve_id=opening_snapshot.sleeve_id,
                            symbol=symbol,
                            quantity=position.quantity,
                            average_cost=position.average_cost,
                            realized_pnl_cumulative=position.realized_pnl_cumulative,
                        )
                        for symbol, position in mutable_sleeves[
                            opening_snapshot.sleeve_id
                        ].positions.items()
                        if position.quantity > _TOLERANCE
                    ),
                    key=lambda item: item.symbol,
                )
            ),
            bootstrap_id=opening_snapshot.bootstrap_id,
        )
        for opening_snapshot in opening_snapshots
    )
    closing_reserve_snapshot = ResidualReserveSnapshot(
        snapshot_id=f"close-{opening_reserve_snapshot.ledger_genesis_id}__reserve__{trading_day}",
        ledger_genesis_id=opening_reserve_snapshot.ledger_genesis_id,
        active_blueprint_activation_id=active_blueprint_activation_id,
        trading_day=trading_day,
        recorded_at_utc=recorded_at_utc.astimezone(UTC),
        cash_balance=mutable_reserve.cash_balance,
        positions=tuple(
            sorted(mutable_reserve.positions.values(), key=lambda item: item.symbol)
        ),
        bootstrap_id=opening_reserve_snapshot.bootstrap_id,
    )

    attribution_records: list[SleeveDailyAttributionRecord] = []
    bootstrap_confidence_by_sleeve = _bootstrap_confidence_by_sleeve(bootstrap_record)
    for opening_snapshot, closing_snapshot in zip(
        sorted(opening_snapshots, key=lambda item: item.sleeve_id),
        sorted(closing_snapshots, key=lambda item: item.sleeve_id),
        strict=True,
    ):
        if opening_snapshot.sleeve_id in gap_by_sleeve_id:
            continue
        opening_market_values = _marked_values_for_snapshot(
            snapshot=opening_snapshot,
            portfolio_state=open_portfolio_state,
        )
        closing_market_values = _marked_values_for_snapshot(
            snapshot=closing_snapshot,
            portfolio_state=close_portfolio_state,
        )
        starting_equity = opening_snapshot.cash_balance + sum(
            opening_market_values.values(), start=Decimal("0")
        )
        ending_equity = closing_snapshot.cash_balance + sum(
            closing_market_values.values(), start=Decimal("0")
        )
        flows = tuple(cash_flows_by_sleeve.get(opening_snapshot.sleeve_id, ()))
        attribution_records.append(
            SleeveDailyAttributionRecord(
                attribution_id=f"{opening_snapshot.sleeve_id}__{trading_day}",
                sleeve_id=opening_snapshot.sleeve_id,
                trading_day=trading_day,
                recorded_at_utc=recorded_at_utc.astimezone(UTC),
                starting_equity=starting_equity,
                ending_equity=ending_equity,
                daily_return=compute_modified_dietz_return(
                    opening_equity=starting_equity,
                    closing_equity=ending_equity,
                    cash_flows=flows,
                    session_open_utc=open_portfolio_state.as_of_utc,
                    session_close_utc=close_portfolio_state.as_of_utc,
                ),
                per_symbol_open_weight=_weights_from_market_values(
                    market_values=opening_market_values,
                    equity=starting_equity,
                ),
                per_symbol_close_weight=_weights_from_market_values(
                    market_values=closing_market_values,
                    equity=ending_equity,
                ),
                realized_pnl=(
                    sum(
                        (
                            position.realized_pnl_cumulative
                            for position in closing_snapshot.positions
                        ),
                        start=Decimal("0"),
                    )
                    - opening_realized_by_sleeve.get(
                        opening_snapshot.sleeve_id, Decimal("0")
                    )
                ),
                unrealized_pnl=sum(
                    (
                        closing_market_values.get(position.symbol, Decimal("0"))
                        - (position.quantity * position.average_cost)
                        for position in closing_snapshot.positions
                    ),
                    start=Decimal("0"),
                ),
                cash_balance=closing_snapshot.cash_balance,
                calculation_mode="sleeve_ledger_mark_to_market",
                bootstrap_confidence=bootstrap_confidence_by_sleeve.get(
                    opening_snapshot.sleeve_id
                ),
                ledger_genesis_id=opening_snapshot.ledger_genesis_id,
            )
        )

    return DailyLedgerResult(
        sleeve_snapshots=tuple(
            sorted(closing_snapshots, key=lambda item: item.sleeve_id)
        ),
        residual_reserve_snapshot=closing_reserve_snapshot,
        attribution_records=tuple(
            sorted(attribution_records, key=lambda item: item.sleeve_id)
        ),
        gap_records=tuple(
            sorted(gap_by_sleeve_id.values(), key=lambda item: item.sleeve_id)
        ),
    )


def compute_modified_dietz_return(
    *,
    opening_equity: Decimal,
    closing_equity: Decimal,
    cash_flows: tuple[tuple[datetime, Decimal], ...],
    session_open_utc: datetime,
    session_close_utc: datetime,
) -> Decimal:
    total_flow = sum((amount for _, amount in cash_flows), start=Decimal("0"))
    total_seconds = Decimal(
        str(max((session_close_utc - session_open_utc).total_seconds(), 0.0))
    )
    weighted_flows = Decimal("0")
    if total_seconds > Decimal("0"):
        for timestamp, amount in cash_flows:
            remaining = Decimal(
                str(max((session_close_utc - timestamp).total_seconds(), 0.0))
            )
            weighted_flows += amount * (remaining / total_seconds)
    denominator = opening_equity + weighted_flows
    if denominator == Decimal("0"):
        return Decimal("0")
    numerator = closing_equity - opening_equity - total_flow
    return numerator / denominator


def _history_allocations_for_symbol(
    *,
    symbol: str,
    broker_quantity: Decimal,
    execution_records: tuple[ExecutionLifecycleRecord, ...],
    broker_average_entry_price: Decimal,
    broker_market_value: Decimal,
) -> list[BootstrapPositionAllocation] | None:
    owner_state: dict[str, _MutablePosition] = {}
    evidence_refs: set[str] = set()
    for execution in sorted(
        (record for record in execution_records if record.symbol == symbol),
        key=lambda item: (item.filled_at_utc, item.execution_id),
    ):
        if not execution.sleeve_attributions:
            continue
        if any(
            owner_id == RESIDUAL_RESERVE_OWNER_ID
            for owner_id, _ in execution.sleeve_attributions
        ):
            continue
        evidence_refs.add(execution.execution_id)
        for owner_id, fraction in execution.sleeve_attributions:
            state = owner_state.setdefault(
                owner_id,
                _MutablePosition(
                    quantity=Decimal("0"),
                    average_cost=broker_average_entry_price,
                    realized_pnl_cumulative=Decimal("0"),
                ),
            )
            attributed_quantity = execution.filled_qty * fraction
            if execution.side == "buy":
                new_quantity = state.quantity + attributed_quantity
                if new_quantity <= Decimal("0"):
                    continue
                new_notional = (state.quantity * state.average_cost) + (
                    attributed_quantity * execution.fill_price
                )
                state.quantity = new_quantity
                state.average_cost = new_notional / new_quantity
            elif execution.side in {"sell", "reduce"}:
                if attributed_quantity > state.quantity + _ROUNDING_TOLERANCE:
                    return None
                realized = (
                    execution.fill_price - state.average_cost
                ) * attributed_quantity
                state.quantity = max(Decimal("0"), state.quantity - attributed_quantity)
                state.realized_pnl_cumulative += realized
                if state.quantity <= _TOLERANCE:
                    state.quantity = Decimal("0")
    positive_positions = {
        owner_id: state
        for owner_id, state in owner_state.items()
        if state.quantity > _TOLERANCE
    }
    if not positive_positions:
        return None
    total_quantity = sum(
        (state.quantity for state in positive_positions.values()), start=Decimal("0")
    )
    allocations: list[BootstrapPositionAllocation] = []
    if abs(total_quantity - broker_quantity) <= _TOLERANCE:
        source = "history_exact"
        confidence = "high"
    elif abs(total_quantity - broker_quantity) <= _ROUNDING_TOLERANCE:
        source = "history_rounding_adjusted"
        confidence = "medium"
        owner_id = max(
            positive_positions,
            key=lambda candidate_owner: positive_positions[candidate_owner].quantity,
        )
        positive_positions[owner_id].quantity += broker_quantity - total_quantity
        total_quantity = broker_quantity
    else:
        return None
    for owner_id, state in sorted(positive_positions.items()):
        market_value = (
            Decimal("0")
            if total_quantity <= Decimal("0")
            else broker_market_value * (state.quantity / total_quantity)
        )
        allocations.append(
            BootstrapPositionAllocation(
                sleeve_id=owner_id,
                symbol=symbol,
                quantity=state.quantity,
                average_cost=state.average_cost,
                market_value=market_value,
                allocation_source=source,
                confidence=confidence,
                evidence_refs=tuple(sorted(evidence_refs)),
            )
        )
    return allocations


def _blueprint_fallback_allocations_for_symbol(
    *,
    symbol: str,
    broker_quantity: Decimal,
    broker_average_entry_price: Decimal,
    broker_market_value: Decimal,
    active_activation: BlueprintActivationRecord,
    snapshot_store: FilesystemArtifactStore,
    budget_by_sleeve_id: Mapping[str, object],
    candidate_by_strategy_id: Mapping[str, StrategyCandidate],
) -> list[BootstrapPositionAllocation]:
    owners: list[tuple[str, Decimal]] = []
    for binding in active_activation.sleeve_activation_bindings:
        snapshot_store.load_approved_weight_snapshot_by_snapshot_id(
            snapshot_id=binding.captured_snapshot_id
        )
        candidate = candidate_by_strategy_id.get(binding.strategy_id)
        if candidate is None:
            continue
        if symbol not in getattr(candidate, "universe", ()):
            continue
        budget = budget_by_sleeve_id.get(binding.sleeve_id)
        budget_fraction = getattr(budget, "budget_fraction_of_equity", Decimal("0"))
        owners.append((binding.sleeve_id, budget_fraction))
    positive_owners = [
        (owner_id, weight) for owner_id, weight in owners if weight > Decimal("0")
    ]
    if not positive_owners:
        return []
    total_weight = sum((weight for _, weight in positive_owners), start=Decimal("0"))
    allocations: list[BootstrapPositionAllocation] = []
    remaining_quantity = broker_quantity
    remaining_value = broker_market_value
    for index, (owner_id, weight) in enumerate(sorted(positive_owners)):
        if index == len(positive_owners) - 1:
            quantity = remaining_quantity
            market_value = remaining_value
        else:
            fraction = weight / total_weight
            quantity = broker_quantity * fraction
            market_value = broker_market_value * fraction
            remaining_quantity -= quantity
            remaining_value -= market_value
        allocations.append(
            BootstrapPositionAllocation(
                sleeve_id=owner_id,
                symbol=symbol,
                quantity=quantity,
                average_cost=broker_average_entry_price,
                market_value=market_value,
                allocation_source="blueprint_fallback",
                confidence="low",
                evidence_refs=(binding_snapshot_ref(active_activation, owner_id),),
            )
        )
    return allocations


def binding_snapshot_ref(
    active_activation: BlueprintActivationRecord,
    sleeve_id: str,
) -> str:
    for binding in active_activation.sleeve_activation_bindings:
        if binding.sleeve_id == sleeve_id:
            return f"snapshot:{binding.captured_snapshot_id}"
    return "snapshot:missing"


def _apply_execution(
    *,
    execution: ExecutionLifecycleRecord,
    sleeves: dict[str, _MutableSleeveState],
    reserve: _MutableReserveState,
    cash_flows_by_sleeve: dict[str, list[tuple[datetime, Decimal]]],
    trading_day: str,
    recorded_at_utc: datetime,
) -> dict[str, SleeveAttributionGapRecord]:
    attrs = execution.sleeve_attributions
    if not attrs:
        return {
            sleeve_id: _gap_record(
                sleeve_id=sleeve_id,
                trading_day=trading_day,
                recorded_at_utc=recorded_at_utc,
                reason="missing_attribution",
                evidence_refs=(execution.execution_id,),
            )
            for sleeve_id in sleeves
        }
    fraction_total = sum((fraction for _, fraction in attrs), start=Decimal("0"))
    if abs(fraction_total - Decimal("1")) > _ROUNDING_TOLERANCE:
        return {
            sleeve_id: _gap_record(
                sleeve_id=sleeve_id,
                trading_day=trading_day,
                recorded_at_utc=recorded_at_utc,
                reason="fraction_sum_invalid",
                evidence_refs=(execution.execution_id,),
            )
            for sleeve_id, _ in attrs
            if sleeve_id != RESIDUAL_RESERVE_OWNER_ID
        }

    owner_ids = {owner_id for owner_id, _ in attrs}
    if owner_ids == {RESIDUAL_RESERVE_OWNER_ID}:
        return _apply_reserve_execution(
            execution=execution,
            reserve=reserve,
            sleeves=sleeves,
            trading_day=trading_day,
            recorded_at_utc=recorded_at_utc,
        )

    if (
        execution.symbol in reserve.positions
        and reserve.positions[execution.symbol].quantity > _TOLERANCE
    ):
        return {
            sleeve_id: _gap_record(
                sleeve_id=sleeve_id,
                trading_day=trading_day,
                recorded_at_utc=recorded_at_utc,
                reason="reserve_inventory_conflict",
                evidence_refs=(execution.execution_id,),
            )
            for sleeve_id, _ in attrs
        }

    for sleeve_id, fraction in attrs:
        if sleeve_id not in sleeves:
            return {
                known_sleeve_id: _gap_record(
                    sleeve_id=known_sleeve_id,
                    trading_day=trading_day,
                    recorded_at_utc=recorded_at_utc,
                    reason="unknown_owner_id",
                    evidence_refs=(execution.execution_id,),
                )
                for known_sleeve_id, _ in attrs
                if known_sleeve_id != RESIDUAL_RESERVE_OWNER_ID
            }
        attributed_quantity = execution.filled_qty * fraction
        notional = attributed_quantity * execution.fill_price
        sleeve = sleeves[sleeve_id]
        position = sleeve.positions.setdefault(
            execution.symbol,
            _MutablePosition(
                quantity=Decimal("0"),
                average_cost=execution.fill_price,
                realized_pnl_cumulative=Decimal("0"),
            ),
        )
        if execution.side == "buy":
            reserve.cash_balance -= notional
            cash_flows_by_sleeve[sleeve_id].append((execution.filled_at_utc, notional))
            new_quantity = position.quantity + attributed_quantity
            total_cost = (position.quantity * position.average_cost) + notional
            position.quantity = new_quantity
            position.average_cost = (
                total_cost / new_quantity
                if new_quantity > Decimal("0")
                else execution.fill_price
            )
            continue
        if execution.side not in {"sell", "reduce"}:
            continue
        if attributed_quantity > position.quantity + _ROUNDING_TOLERANCE:
            return {
                sleeve_id: _gap_record(
                    sleeve_id=sleeve_id,
                    trading_day=trading_day,
                    recorded_at_utc=recorded_at_utc,
                    reason="negative_position_violation",
                    evidence_refs=(execution.execution_id,),
                )
            }
        realized = (execution.fill_price - position.average_cost) * attributed_quantity
        position.quantity = max(Decimal("0"), position.quantity - attributed_quantity)
        position.realized_pnl_cumulative += realized
        reserve.cash_balance += notional
        cash_flows_by_sleeve[sleeve_id].append((execution.filled_at_utc, -notional))
        if position.quantity <= _TOLERANCE:
            sleeve.positions.pop(execution.symbol, None)
    return {}


def _apply_reserve_execution(
    *,
    execution: ExecutionLifecycleRecord,
    reserve: _MutableReserveState,
    sleeves: dict[str, _MutableSleeveState],
    trading_day: str,
    recorded_at_utc: datetime,
) -> dict[str, SleeveAttributionGapRecord]:
    if any(
        execution.symbol in sleeve.positions
        and sleeve.positions[execution.symbol].quantity > _TOLERANCE
        for sleeve in sleeves.values()
    ):
        return {
            sleeve_id: _gap_record(
                sleeve_id=sleeve_id,
                trading_day=trading_day,
                recorded_at_utc=recorded_at_utc,
                reason="mixed_reserve_and_sleeve_ownership",
                evidence_refs=(execution.execution_id,),
            )
            for sleeve_id in sleeves
            if execution.symbol in sleeves[sleeve_id].positions
        }
    reserve_position = reserve.positions.get(execution.symbol)
    if reserve_position is None:
        return {}
    if execution.side in {"sell", "reduce"}:
        if execution.filled_qty > reserve_position.quantity + _ROUNDING_TOLERANCE:
            return {}
        new_quantity = max(
            Decimal("0"), reserve_position.quantity - execution.filled_qty
        )
        reserve.cash_balance += execution.filled_qty * execution.fill_price
        if new_quantity <= _TOLERANCE:
            reserve.positions.pop(execution.symbol, None)
        else:
            reserve.positions[execution.symbol] = ResidualPositionAllocation(
                symbol=reserve_position.symbol,
                quantity=new_quantity,
                average_cost=reserve_position.average_cost,
                market_value=reserve_position.market_value,
                reason=reserve_position.reason,
                evidence_refs=reserve_position.evidence_refs,
            )
    return {}


def _gap_record(
    *,
    sleeve_id: str,
    trading_day: str,
    recorded_at_utc: datetime,
    reason: str,
    evidence_refs: tuple[str, ...],
) -> SleeveAttributionGapRecord:
    payload = "|".join((sleeve_id, trading_day, reason, *evidence_refs))
    return SleeveAttributionGapRecord(
        gap_id=f"gap-{uuid.uuid5(uuid.NAMESPACE_URL, payload)}",
        sleeve_id=sleeve_id,
        trading_day=trading_day,
        recorded_at_utc=recorded_at_utc.astimezone(UTC),
        severity="warning",
        reason=reason,
        evidence_refs=evidence_refs,
    )


def _marked_values_for_snapshot(
    *,
    snapshot: SleevePositionLedgerSnapshot,
    portfolio_state: PortfolioState,
) -> dict[str, Decimal]:
    broker_positions = {
        position.symbol: position for position in portfolio_state.positions
    }
    market_values: dict[str, Decimal] = {}
    for position in snapshot.positions:
        broker_position = broker_positions.get(position.symbol)
        if broker_position is None or broker_position.quantity <= Decimal("0"):
            market_values[position.symbol] = Decimal("0")
            continue
        market_values[position.symbol] = broker_position.market_value * (
            position.quantity / broker_position.quantity
        )
    return market_values


def _weights_from_market_values(
    *,
    market_values: dict[str, Decimal],
    equity: Decimal,
) -> tuple[tuple[str, Decimal], ...]:
    if equity == Decimal("0"):
        return ()
    return tuple(
        sorted(
            (
                (symbol, value / equity)
                for symbol, value in market_values.items()
                if value != Decimal("0")
            ),
            key=lambda item: item[0],
        )
    )


def _bootstrap_confidence_by_sleeve(
    bootstrap_record: SleeveBootstrapAllocationRecord,
) -> dict[str, str]:
    confidence_values: dict[str, set[str]] = {}
    for allocation in bootstrap_record.position_allocations:
        confidence_values.setdefault(allocation.sleeve_id, set()).add(
            allocation.confidence
        )
    result: dict[str, str] = {}
    for sleeve_id, confidences in confidence_values.items():
        if len(confidences) == 1:
            result[sleeve_id] = next(iter(confidences))
        else:
            result[sleeve_id] = "mixed"
    return result


__all__ = (
    "BootstrapResult",
    "DailyLedgerResult",
    "RESIDUAL_RESERVE_OWNER_ID",
    "build_bootstrap_allocation",
    "build_daily_ledger_result",
    "compute_modified_dietz_return",
)
