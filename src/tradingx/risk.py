from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alpaca.trading.enums import OrderSide

from tradingx.config import TradingConfig
from tradingx.types import MarketSnapshot, PortfolioState, RiskControlEvent, TradeIntent

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


@dataclass(frozen=True)
class RiskDecision:
    decision: str
    control_code: str
    event: RiskControlEvent | None


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
        control_code = self._evaluate_context(context, is_live_order=is_live_order)
        if control_code is not None:
            raise RiskViolation(self._message_for_control_code(control_code))

    def evaluate_trade_intent(
        self,
        intent: TradeIntent,
        market_snapshot: MarketSnapshot,
        portfolio_state: PortfolioState,
        *,
        broker_state_timestamp: datetime,
        kill_switch_active: bool = False,
        is_live_order: bool = False,
    ) -> RiskDecision:
        quantity = intent.quantity or Decimal("0")
        context = PreTradeRiskContext(
            symbol=intent.symbol,
            side=OrderSide.BUY if intent.side == "buy" else OrderSide.SELL,
            quantity=quantity,
            last_trade_price=market_snapshot.last_trade_price,
            average_daily_volume_30d=market_snapshot.average_daily_volume_30d,
            market_data_timestamp=market_snapshot.timestamp,
            account_equity=portfolio_state.equity,
            buying_power=portfolio_state.buying_power,
            current_position_quantity=self._current_position_quantity(
                portfolio_state, intent.symbol
            ),
            broker_state_timestamp=broker_state_timestamp,
            kill_switch_active=kill_switch_active,
        )
        control_code = self._evaluate_context(context, is_live_order=is_live_order)
        if control_code is None:
            return RiskDecision(
                decision="approved",
                control_code="passed",
                event=None,
            )

        event = RiskControlEvent(
            event_id=f"risk-{intent.intent_id}",
            intent_id=intent.intent_id,
            severity=self._severity_for_control_code(control_code),
            control_type=control_code,
            blocked=True,
            recorded_at_utc=self._now_provider(),
            operator_visible=True,
        )
        return RiskDecision(
            decision="blocked",
            control_code=control_code,
            event=event,
        )

    def _evaluate_context(
        self,
        context: PreTradeRiskContext,
        *,
        is_live_order: bool,
    ) -> str | None:
        if context.quantity <= Decimal("0"):
            return "non_positive_quantity"
        if not context.symbol.strip().isupper():
            return "invalid_symbol"
        if is_live_order or self._config.live_controls.all_layers_enabled():
            return "live_mode_disabled"
        if context.average_daily_volume_30d < MINIMUM_AVERAGE_DAILY_VOLUME:
            return "liquidity_filter"
        if context.last_trade_price < MINIMUM_LAST_TRADE_PRICE:
            return "price_floor"
        concentration_result = self._check_concentration_limit(context)
        if concentration_result is not None:
            return concentration_result
        margin_result = self._check_intraday_margin(context)
        if margin_result is not None:
            return margin_result
        market_data_result = self._check_market_data_fresh(context)
        if market_data_result is not None:
            return market_data_result
        broker_state_result = self._check_broker_state_fresh(context)
        if broker_state_result is not None:
            return broker_state_result
        if context.kill_switch_active or self._config.runtime.manual_kill_switch_active:
            return "kill_switch"
        return None

    def _current_position_quantity(
        self,
        portfolio_state: PortfolioState,
        symbol: str,
    ) -> Decimal:
        for position in portfolio_state.positions:
            if position.symbol == symbol:
                return position.quantity
        return Decimal("0")

    def _message_for_control_code(self, control_code: str) -> str:
        return {
            "non_positive_quantity": "Quantity must be positive.",
            "invalid_symbol": "Symbols must be provided in uppercase.",
            "live_mode_disabled": "Live trading remains disabled until Gate 4.",
            "liquidity_filter": "Liquidity filter blocked the order.",
            "price_floor": "Price floor blocked the order.",
            "single_symbol_concentration": (
                "Order would breach the single-symbol concentration cap."
            ),
            "intraday_margin": "Intraday margin blocked the order.",
            "stale_market_data": "Market data is stale.",
            "stale_broker_state": "Broker state is stale.",
            "kill_switch": "Kill switch is active.",
        }[control_code]

    def _severity_for_control_code(self, control_code: str) -> str:
        if control_code in {"live_mode_disabled", "kill_switch", "stale_broker_state"}:
            return "critical"
        return "warning"

    def _check_concentration_limit(
        self,
        context: PreTradeRiskContext,
    ) -> str | None:
        if context.account_equity <= Decimal("0"):
            return "single_symbol_concentration"

        side_multiplier = (
            Decimal("1") if context.side == OrderSide.BUY else Decimal("-1")
        )
        resulting_position_quantity = context.current_position_quantity + (
            side_multiplier * context.quantity
        )
        resulting_exposure = abs(resulting_position_quantity) * context.last_trade_price
        concentration_limit = context.account_equity * MAX_SINGLE_SYMBOL_CONCENTRATION
        if resulting_exposure > concentration_limit:
            return "single_symbol_concentration"
        return None

    def _check_intraday_margin(self, context: PreTradeRiskContext) -> str | None:
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
            return None
        if (
            context.buying_power <= Decimal("0")
            or incremental_exposure > context.buying_power
        ):
            return "intraday_margin"
        return None

    def _check_market_data_fresh(self, context: PreTradeRiskContext) -> str | None:
        if self._now_provider() - context.market_data_timestamp > STALE_DATA_WINDOW:
            return "stale_market_data"
        return None

    def _check_broker_state_fresh(self, context: PreTradeRiskContext) -> str | None:
        if self._now_provider() - context.broker_state_timestamp > STALE_STATE_WINDOW:
            return "stale_broker_state"
        return None
