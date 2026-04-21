from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from tradingx.runtime_portfolio import RuntimePortfolioPlan, RuntimePortfolioTrade
from tradingx.strategy import DeterministicBaselineStrategy
from tradingx.types import (
    MarketSnapshot,
    OpportunitySelectionRecord,
    PortfolioState,
    PositionSnapshot,
    TradeIntent,
)


class MarketDataGatewayProtocol(Protocol):
    def get_market_snapshot(self, symbol: str) -> MarketSnapshot: ...


class OpportunitySelectorProtocol(Protocol):
    def select_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
    ) -> OpportunitySelectionRecord: ...


class BaselineLongOnlyPlanner:
    def __init__(
        self,
        *,
        market_data: MarketDataGatewayProtocol,
        strategy: DeterministicBaselineStrategy | None = None,
        selector: OpportunitySelectorProtocol | None = None,
        benchmark_symbol: str = "SPY",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._market_data = market_data
        self._strategy = strategy or DeterministicBaselineStrategy()
        self._selector = selector
        self._benchmark_symbol = benchmark_symbol
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def plan_for_service(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        default_quantity: Decimal,
    ) -> RuntimePortfolioPlan:
        symbols = tuple(dict.fromkeys(symbols))
        current_weights = _current_weights(portfolio_state)
        target_weights = dict(current_weights)
        market_snapshots: dict[str, MarketSnapshot] = {}
        trade_intents: list[TradeIntent] = []
        planned_trades: list[RuntimePortfolioTrade] = []

        open_symbols = tuple(
            symbol
            for symbol in symbols
            if _position_for_symbol(portfolio_state, symbol) is not None
        )
        candidate_symbols = tuple(
            symbol for symbol in symbols if symbol not in set(open_symbols)
        )

        for symbol in open_symbols:
            snapshot = self._market_data.get_market_snapshot(symbol)
            market_snapshots[symbol] = snapshot
            intent = self._strategy.generate_trade_intent(
                market_snapshot=snapshot,
                portfolio_state=portfolio_state,
                quantity=default_quantity,
            )
            trade_intents.append(intent)
            planned_trades.append(
                _planned_trade_for_intent(
                    intent=intent,
                    portfolio_state=portfolio_state,
                    market_snapshot=snapshot,
                )
            )
            target_weights[symbol] = _weight_for_quantity(
                account_equity=portfolio_state.equity,
                quantity=planned_trades[-1].target_quantity,
                last_trade_price=snapshot.last_trade_price,
            )

        selected_entry_symbols = candidate_symbols
        if self._selector is not None and candidate_symbols:
            selection = self._selector.select_for_service(
                symbols=candidate_symbols,
                portfolio_state=portfolio_state,
            )
            if selection.decision == "selected" and selection.selected_symbol:
                selected_entry_symbols = (selection.selected_symbol,)
            else:
                selected_entry_symbols = ()

        for symbol in selected_entry_symbols:
            snapshot = self._market_data.get_market_snapshot(symbol)
            market_snapshots[symbol] = snapshot
            intent = self._strategy.generate_trade_intent(
                market_snapshot=snapshot,
                portfolio_state=portfolio_state,
                quantity=default_quantity,
            )
            trade_intents.append(intent)
            planned_trades.append(
                _planned_trade_for_intent(
                    intent=intent,
                    portfolio_state=portfolio_state,
                    market_snapshot=snapshot,
                )
            )
            target_weights[symbol] = _weight_for_quantity(
                account_equity=portfolio_state.equity,
                quantity=planned_trades[-1].target_quantity,
                last_trade_price=snapshot.last_trade_price,
            )

        tracked_symbols = tuple(
            dict.fromkeys(
                [
                    *open_symbols,
                    *selected_entry_symbols,
                    *(
                        position.symbol
                        for position in portfolio_state.positions
                        if position.quantity != Decimal("0")
                    ),
                ]
            )
        )
        return RuntimePortfolioPlan(
            plan_id=f"runtime-plan-{uuid.uuid4()}",
            generated_at_utc=self._now_provider(),
            strategy_id=self._strategy.candidate_id,
            universe_snapshot_id=_universe_snapshot_id(symbols),
            benchmark_symbol=self._benchmark_symbol,
            crash_overlay_active=False,
            symbols_considered=tracked_symbols,
            current_weights={
                symbol: current_weights.get(symbol, Decimal("0"))
                for symbol in tracked_symbols
            },
            target_weights={
                symbol: target_weights.get(symbol, Decimal("0"))
                for symbol in tracked_symbols
            },
            trade_intents=tuple(trade_intents),
            planned_trades=tuple(planned_trades),
            market_snapshots=market_snapshots,
        )


def _current_weights(portfolio_state: PortfolioState) -> dict[str, Decimal]:
    if portfolio_state.equity <= Decimal("0"):
        return {}
    return {
        position.symbol: position.market_value / portfolio_state.equity
        for position in portfolio_state.positions
        if position.quantity != Decimal("0")
    }


def _position_for_symbol(
    portfolio_state: PortfolioState,
    symbol: str,
) -> PositionSnapshot | None:
    for position in portfolio_state.positions:
        if position.symbol == symbol and position.quantity != Decimal("0"):
            return position
    return None


def _planned_trade_for_intent(
    *,
    intent: TradeIntent,
    portfolio_state: PortfolioState,
    market_snapshot: MarketSnapshot,
) -> RuntimePortfolioTrade:
    position = _position_for_symbol(portfolio_state, intent.symbol)
    current_quantity = Decimal("0") if position is None else position.quantity
    current_weight = (
        Decimal("0")
        if position is None or portfolio_state.equity <= Decimal("0")
        else position.market_value / portfolio_state.equity
    )
    target_quantity = _target_quantity_for_intent(
        intent=intent,
        current_quantity=current_quantity,
    )
    target_weight = _weight_for_quantity(
        account_equity=portfolio_state.equity,
        quantity=target_quantity,
        last_trade_price=market_snapshot.last_trade_price,
    )
    return RuntimePortfolioTrade(
        symbol=intent.symbol,
        side=intent.side,
        reason_code=intent.reason_code,
        last_trade_price=market_snapshot.last_trade_price,
        current_weight=current_weight,
        target_weight=target_weight,
        current_quantity=current_quantity,
        target_quantity=target_quantity,
        delta_quantity=target_quantity - current_quantity,
        no_trade_band_applied=False,
    )


def _target_quantity_for_intent(
    *,
    intent: TradeIntent,
    current_quantity: Decimal,
) -> Decimal:
    if intent.side == "buy":
        return current_quantity + (intent.quantity or Decimal("0"))
    if intent.side in {"sell", "reduce"}:
        return max(Decimal("0"), current_quantity - (intent.quantity or Decimal("0")))
    return current_quantity


def _weight_for_quantity(
    *,
    account_equity: Decimal,
    quantity: Decimal,
    last_trade_price: Decimal,
) -> Decimal:
    if (
        account_equity <= Decimal("0")
        or quantity <= Decimal("0")
        or last_trade_price <= Decimal("0")
    ):
        return Decimal("0")
    return (quantity * last_trade_price) / account_equity


def _universe_snapshot_id(symbols: tuple[str, ...]) -> str:
    normalized = tuple(
        sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    )
    if not normalized:
        return "universe-empty"
    return "universe-" + "-".join(symbol.lower() for symbol in normalized)


__all__ = ("BaselineLongOnlyPlanner",)
