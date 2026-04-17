from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alpaca.trading.enums import OrderSide

from tradingx.config import TradingConfig

# source: .specify/memory/constitution.md (CONST-0001 v3.0.1, retrieved 2026-04-17)
MINIMUM_AVERAGE_DAILY_VOLUME = Decimal("1000000")
# source: .specify/memory/constitution.md (CONST-0001 v3.0.1, retrieved 2026-04-17)
MINIMUM_LAST_TRADE_PRICE = Decimal("5.00")
# source: docs/archive/implementation_constraints.md
# (CONSTRAINTS-0001 v1.0.0, retrieved 2026-04-17)
MAX_SINGLE_SYMBOL_CONCENTRATION = Decimal("0.20")
# source: docs/archive/implementation_constraints.md
# (CONSTRAINTS-0001 v1.0.0, retrieved 2026-04-17)
STALE_DATA_WINDOW = timedelta(seconds=60)
# source: .specify/memory/constitution.md (CONST-0001 v3.0.1, retrieved 2026-04-17)
STALE_STATE_WINDOW = timedelta(minutes=5)


class RiskViolation(ValueError):
    """Raised when an order violates a non-negotiable safety constraint."""


@dataclass(frozen=True)
class PreTradeRiskContext:
    symbol: str
    side: OrderSide
    quantity: Decimal
    last_trade_price: Decimal
    average_daily_volume_30d: Decimal
    market_data_timestamp: datetime
    account_equity: Decimal
    buying_power: Decimal
    current_position_quantity: Decimal
    broker_state_timestamp: datetime
    kill_switch_active: bool = False


class PaperOnlyRiskEngine:
    def __init__(
        self,
        config: TradingConfig,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    def assert_order_allowed(
        self,
        context: PreTradeRiskContext,
        *,
        is_live_order: bool,
    ) -> None:
        if context.quantity <= Decimal("0"):
            raise RiskViolation("Quantity must be positive.")
        if not context.symbol.strip().isupper():
            raise RiskViolation("Symbols must be provided in uppercase.")
        if is_live_order or self._config.live_controls.all_layers_enabled():
            raise RiskViolation("Live trading remains disabled until Gate 4.")
        if context.average_daily_volume_30d < MINIMUM_AVERAGE_DAILY_VOLUME:
            raise RiskViolation("Liquidity filter blocked the order.")
        if context.last_trade_price < MINIMUM_LAST_TRADE_PRICE:
            raise RiskViolation("Price floor blocked the order.")
        self._assert_concentration_limit(context)
        self._assert_intraday_margin(context)
        self._assert_market_data_fresh(context)
        self._assert_broker_state_fresh(context)
        if context.kill_switch_active:
            raise RiskViolation("Kill switch is active.")

    def _assert_concentration_limit(self, context: PreTradeRiskContext) -> None:
        if context.account_equity <= Decimal("0"):
            raise RiskViolation("Account equity must be positive.")

        side_multiplier = (
            Decimal("1") if context.side == OrderSide.BUY else Decimal("-1")
        )
        resulting_position_quantity = context.current_position_quantity + (
            side_multiplier * context.quantity
        )
        resulting_exposure = abs(resulting_position_quantity) * context.last_trade_price
        concentration_limit = context.account_equity * MAX_SINGLE_SYMBOL_CONCENTRATION
        if resulting_exposure > concentration_limit:
            raise RiskViolation(
                "Order would breach the single-symbol concentration cap."
            )

    def _assert_intraday_margin(self, context: PreTradeRiskContext) -> None:
        side_multiplier = (
            Decimal("1") if context.side == OrderSide.BUY else Decimal("-1")
        )
        current_exposure = (
            abs(context.current_position_quantity) * context.last_trade_price
        )
        resulting_exposure = (
            abs(
                context.current_position_quantity + (side_multiplier * context.quantity)
            )
            * context.last_trade_price
        )
        incremental_exposure = resulting_exposure - current_exposure
        if incremental_exposure <= Decimal("0"):
            return
        if (
            context.buying_power <= Decimal("0")
            or incremental_exposure > context.buying_power
        ):
            raise RiskViolation("Intraday margin blocked the order.")

    def _assert_market_data_fresh(self, context: PreTradeRiskContext) -> None:
        if self._now_provider() - context.market_data_timestamp > STALE_DATA_WINDOW:
            raise RiskViolation("Market data is stale.")

    def _assert_broker_state_fresh(self, context: PreTradeRiskContext) -> None:
        if self._now_provider() - context.broker_state_timestamp > STALE_STATE_WINDOW:
            raise RiskViolation("Broker state is stale.")
