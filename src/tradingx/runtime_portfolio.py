from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Protocol

from tradingx.portfolio_construction import (
    CandidateRuntimeWeights,
    build_candidate_runtime_weights,
)
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.types import (
    ApprovedWeightSnapshot,
    MarketSnapshot,
    PortfolioState,
    StrategyActivationRecord,
    TradeIntent,
)

HISTORY_LOOKBACK_DAYS = 1200


class UnsupportedRuntimePortfolioPlanError(ValueError):
    """Raised when an activated research strategy cannot be executed safely."""


class MarketDataGatewayProtocol(Protocol):
    def get_daily_bar_history(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
    ): ...

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot: ...


class ActivationGatewayProtocol(Protocol):
    def load_or_create_active_records(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[StrategyActivationRecord, ApprovedWeightSnapshot]: ...


@dataclass(frozen=True)
class RuntimePortfolioTrade:
    symbol: str
    side: str
    reason_code: str
    last_trade_price: Decimal
    current_weight: Decimal
    target_weight: Decimal
    current_quantity: Decimal
    target_quantity: Decimal
    delta_quantity: Decimal
    no_trade_band_applied: bool


@dataclass(frozen=True)
class RuntimePortfolioPlan:
    plan_id: str
    generated_at_utc: datetime
    strategy_id: str
    universe_snapshot_id: str
    benchmark_symbol: str
    crash_overlay_active: bool
    symbols_considered: tuple[str, ...]
    current_weights: dict[str, Decimal]
    target_weights: dict[str, Decimal]
    trade_intents: tuple[TradeIntent, ...]
    planned_trades: tuple[RuntimePortfolioTrade, ...]
    market_snapshots: dict[str, MarketSnapshot]


class RuntimePortfolioPlanner:
    def __init__(
        self,
        *,
        market_data: MarketDataGatewayProtocol,
        activation_gateway: ActivationGatewayProtocol | None = None,
        history_lookback_days: int = HISTORY_LOOKBACK_DAYS,
        now_provider=None,
    ) -> None:
        self._market_data = market_data
        self._activation_gateway = activation_gateway
        self._history_lookback_days = history_lookback_days
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
    ) -> RuntimePortfolioPlan | None:
        if self._activation_gateway is None:
            return None
        generated_at = self._now_provider()
        activation, _snapshot = self._activation_gateway.load_or_create_active_records(
            symbols
        )
        runtime_symbols = activation.approved_symbols or symbols
        candidate = self._candidate_for_strategy(
            strategy_id=activation.strategy_id,
            symbols=runtime_symbols,
        )
        if candidate is None:
            return None

        bars_by_symbol = self._load_bars(
            symbols=tuple(
                sorted(
                    {candidate.benchmark_symbol, *candidate.universe}
                    | {
                        position.symbol
                        for position in portfolio_state.positions
                        if position.quantity != Decimal("0")
                    }
                )
            )
        )
        current_weights = _current_weights(portfolio_state)
        runtime_weights = build_candidate_runtime_weights(
            candidate,
            bars_by_symbol=bars_by_symbol,
            current_positions=current_weights,
            account_equity=portfolio_state.equity,
        )
        if any(weight < Decimal("0") for weight in runtime_weights.target_weights.values()):
            raise UnsupportedRuntimePortfolioPlanError(
                "Runtime portfolio planner only supports non-negative target weights "
                f"for {candidate.candidate_id}."
            )
        tracked_symbols = tuple(
            sorted(set(runtime_weights.target_weights) | set(current_weights))
        )
        market_snapshots: dict[str, MarketSnapshot] = {}
        planned_trade_rows: list[RuntimePortfolioTrade] = []
        for symbol in tracked_symbols:
            current_quantity = _current_quantity(portfolio_state, symbol)
            last_trade_price = _position_price_hint(portfolio_state, symbol)
            if last_trade_price is None:
                snapshot = self._market_data.get_market_snapshot(symbol)
                market_snapshots[symbol] = snapshot
                last_trade_price = snapshot.last_trade_price
            trade = self._build_planned_trade(
                symbol=symbol,
                current_weight=current_weights.get(symbol, Decimal("0")),
                target_weight=runtime_weights.target_weights.get(symbol, Decimal("0")),
                raw_target_weight=runtime_weights.raw_weights.get(symbol, Decimal("0")),
                current_quantity=current_quantity,
                last_trade_price=last_trade_price,
                candidate_id=candidate.candidate_id,
                generated_at=generated_at,
                account_equity=portfolio_state.equity,
            )
            if trade.side in {"buy", "sell", "reduce"} and symbol not in market_snapshots:
                snapshot = self._market_data.get_market_snapshot(symbol)
                market_snapshots[symbol] = snapshot
                trade = self._build_planned_trade(
                    symbol=symbol,
                    current_weight=current_weights.get(symbol, Decimal("0")),
                    target_weight=runtime_weights.target_weights.get(symbol, Decimal("0")),
                    raw_target_weight=runtime_weights.raw_weights.get(symbol, Decimal("0")),
                    current_quantity=current_quantity,
                    last_trade_price=snapshot.last_trade_price,
                    candidate_id=candidate.candidate_id,
                    generated_at=generated_at,
                    account_equity=portfolio_state.equity,
                )
            planned_trade_rows.append(trade)
        planned_trades = tuple(planned_trade_rows)
        ordered_trades = tuple(
            sorted(
                planned_trades,
                key=lambda trade: (_side_priority(trade.side), trade.symbol),
            )
        )
        trade_intents = tuple(
            _trade_intent_for_plan_item(
                trade,
                candidate_id=candidate.candidate_id,
                generated_at=generated_at,
            )
            for trade in ordered_trades
        )
        return RuntimePortfolioPlan(
            plan_id=f"runtime-plan-{uuid.uuid4()}",
            generated_at_utc=generated_at,
            strategy_id=candidate.candidate_id,
            universe_snapshot_id=_universe_snapshot_id(runtime_symbols),
            benchmark_symbol=candidate.benchmark_symbol,
            crash_overlay_active=runtime_weights.crash_overlay_active,
            symbols_considered=tracked_symbols,
            current_weights={symbol: current_weights.get(symbol, Decimal("0")) for symbol in tracked_symbols},
            target_weights={
                symbol: runtime_weights.target_weights.get(symbol, Decimal("0"))
                for symbol in tracked_symbols
            },
            trade_intents=trade_intents,
            planned_trades=ordered_trades,
            market_snapshots=market_snapshots,
        )

    def _candidate_for_strategy(
        self,
        *,
        strategy_id: str,
        symbols: tuple[str, ...],
    ):
        for candidate in build_mandatory_candidate_registry(symbols):
            if candidate.candidate_id == strategy_id:
                return candidate
        return None

    def _load_bars(self, *, symbols: tuple[str, ...]):
        end_utc = self._now_provider()
        start_utc = end_utc - timedelta(days=self._history_lookback_days)
        return {
            symbol: self._market_data.get_daily_bar_history(
                symbol,
                start_utc=start_utc,
                end_utc=end_utc,
            )
            for symbol in symbols
        }

    def _build_planned_trade(
        self,
        *,
        symbol: str,
        current_weight: Decimal,
        target_weight: Decimal,
        raw_target_weight: Decimal,
        current_quantity: Decimal,
        last_trade_price: Decimal,
        candidate_id: str,
        generated_at: datetime,
        account_equity: Decimal,
    ) -> RuntimePortfolioTrade:
        del candidate_id, generated_at
        target_quantity = _target_quantity(
            target_weight=target_weight,
            account_equity=account_equity,
            last_trade_price=last_trade_price,
        )
        delta_quantity = target_quantity - current_quantity
        if delta_quantity > Decimal("0"):
            side = "buy"
            quantity = delta_quantity
            reason_code = "target_weight_entry"
        elif delta_quantity < Decimal("0"):
            quantity = abs(delta_quantity)
            side = "sell" if target_quantity == Decimal("0") else "reduce"
            reason_code = (
                "target_weight_exit" if target_quantity == Decimal("0") else "target_weight_reduce"
            )
        else:
            side = "hold"
            quantity = Decimal("0")
            reason_code = "target_weight_hold"

        return RuntimePortfolioTrade(
            symbol=symbol,
            side=side,
            reason_code=reason_code,
            last_trade_price=last_trade_price,
            current_weight=current_weight,
            target_weight=target_weight,
            current_quantity=current_quantity,
            target_quantity=target_quantity,
            delta_quantity=delta_quantity,
            no_trade_band_applied=target_weight != raw_target_weight,
        )


def _current_weights(portfolio_state: PortfolioState) -> dict[str, Decimal]:
    if portfolio_state.equity <= Decimal("0"):
        return {}
    return {
        position.symbol: position.market_value / portfolio_state.equity
        for position in portfolio_state.positions
        if position.quantity != Decimal("0")
    }


def _current_quantity(portfolio_state: PortfolioState, symbol: str) -> Decimal:
    for position in portfolio_state.positions:
        if position.symbol == symbol:
            return position.quantity
    return Decimal("0")


def _position_price_hint(
    portfolio_state: PortfolioState,
    symbol: str,
) -> Decimal | None:
    for position in portfolio_state.positions:
        if (
            position.symbol == symbol
            and position.quantity != Decimal("0")
            and position.market_value > Decimal("0")
        ):
            return position.market_value / position.quantity
    return None


def _target_quantity(
    *,
    target_weight: Decimal,
    account_equity: Decimal,
    last_trade_price: Decimal,
) -> Decimal:
    if target_weight <= Decimal("0") or account_equity <= Decimal("0") or last_trade_price <= Decimal("0"):
        return Decimal("0")
    raw_quantity = (target_weight * account_equity) / last_trade_price
    return raw_quantity.quantize(Decimal("1"), rounding=ROUND_DOWN)


def _trade_intent_for_plan_item(
    trade: RuntimePortfolioTrade,
    *,
    candidate_id: str,
    generated_at: datetime,
) -> TradeIntent:
    payload = "|".join(
        (
            candidate_id,
            trade.symbol,
            trade.side,
            str(trade.delta_quantity),
            generated_at.astimezone(UTC).isoformat(),
        )
    )
    return TradeIntent(
        intent_id=str(uuid.uuid5(uuid.NAMESPACE_URL, payload)),
        candidate_id=candidate_id,
        symbol=trade.symbol,
        side=trade.side,
        quantity=(
            None if trade.side == "hold" else abs(trade.delta_quantity)
        ),
        reason_code=trade.reason_code,
        generated_at_utc=generated_at,
    )


def _side_priority(side: str) -> int:
    if side in {"sell", "reduce"}:
        return 0
    if side == "hold":
        return 1
    return 2


def _universe_snapshot_id(symbols: tuple[str, ...]) -> str:
    normalized = tuple(
        sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    )
    if not normalized:
        return "universe-empty"
    return "universe-" + "-".join(symbol.lower() for symbol in normalized)


__all__ = (
    "RuntimePortfolioPlan",
    "RuntimePortfolioPlanner",
    "RuntimePortfolioTrade",
    "UnsupportedRuntimePortfolioPlanError",
)
