"""Signal sizing for research backtests.

Non-pre-sized strategies use generic volatility targeting and a fixed
fractional Kelly multiplier. Pre-sized strategies pass through
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Literal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.features.volatility import forecast_volatility, volatility_scale
from tradingx.signals.trend import REQUIRED_OHLCV_COLUMNS
from tradingx.types import MarketSnapshot, PortfolioState

KELLY_FRACTION = 0.33
TARGET_VOLATILITY = 0.12
REALIZED_VOL_WINDOW_DAYS = 20
MAX_GROSS_LEVERAGE = 1.0
DEFAULT_ENTRY_MARKETABLE_LIMIT_BPS = Decimal("10")
CENT = Decimal("0.01")

RuntimeSizingMode = Literal["fixed_shares", "percent_equity"]


@dataclass(frozen=True)
class RuntimeSizingPolicy:
    mode: RuntimeSizingMode = "fixed_shares"
    fixed_quantity: Decimal = Decimal("1")
    equity_percent: Decimal = Decimal("5")
    max_order_notional: Decimal | None = None
    cash_reserve_percent: Decimal = Decimal("20")
    entry_marketable_limit_bps: Decimal = DEFAULT_ENTRY_MARKETABLE_LIMIT_BPS


@dataclass
class RuntimeSizingBudget:
    remaining_notional: Decimal

    def consume(self, notional: Decimal) -> None:
        if notional <= Decimal("0"):
            return
        self.remaining_notional = max(
            Decimal("0"),
            self.remaining_notional - notional,
        )


def build_runtime_sizing_budget(
    *,
    policy: RuntimeSizingPolicy,
    portfolio_state: PortfolioState,
) -> RuntimeSizingBudget:
    return RuntimeSizingBudget(
        remaining_notional=_max_cycle_notional(
            policy=policy,
            portfolio_state=portfolio_state,
        )
    )


def resolve_entry_quantity(
    *,
    policy: RuntimeSizingPolicy | None,
    portfolio_state: PortfolioState,
    market_snapshot: MarketSnapshot,
    fallback_quantity: Decimal,
    sizing_budget: RuntimeSizingBudget | None = None,
) -> Decimal:
    if policy is None:
        return max(Decimal("0"), fallback_quantity)

    last_trade_price = market_snapshot.last_trade_price
    if last_trade_price <= Decimal("0"):
        return Decimal("0")
    entry_price = entry_marketable_limit_price(
        market_snapshot,
        buffer_bps=policy.entry_marketable_limit_bps,
    )
    if entry_price <= Decimal("0"):
        return Decimal("0")

    return cap_entry_quantity(
        policy=policy,
        portfolio_state=portfolio_state,
        last_trade_price=last_trade_price,
        entry_price=entry_price,
        requested_quantity=_requested_quantity_from_policy(
            policy=policy,
            portfolio_state=portfolio_state,
            last_trade_price=entry_price,
        ),
        sizing_budget=sizing_budget,
    )


def cap_entry_quantity(
    *,
    policy: RuntimeSizingPolicy,
    portfolio_state: PortfolioState,
    last_trade_price: Decimal,
    requested_quantity: Decimal,
    sizing_budget: RuntimeSizingBudget | None = None,
    entry_price: Decimal | None = None,
) -> Decimal:
    if last_trade_price <= Decimal("0"):
        return Decimal("0")
    sizing_price = entry_price if entry_price is not None else last_trade_price
    if sizing_price <= Decimal("0"):
        return Decimal("0")

    policy_quantity = _requested_quantity_from_policy(
        policy=policy,
        portfolio_state=portfolio_state,
        last_trade_price=sizing_price,
    )
    requested_quantity = min(_whole_share_quantity(requested_quantity), policy_quantity)
    if requested_quantity <= Decimal("0"):
        return Decimal("0")

    max_entry_notional = _max_entry_notional(
        policy=policy,
        portfolio_state=portfolio_state,
        sizing_budget=sizing_budget,
    )
    max_quantity = _quantity_from_notional(
        notional=max_entry_notional,
        last_trade_price=sizing_price,
    )
    return min(requested_quantity, max_quantity)


def entry_marketable_limit_price(
    market_snapshot: MarketSnapshot,
    *,
    buffer_bps: Decimal = DEFAULT_ENTRY_MARKETABLE_LIMIT_BPS,
) -> Decimal:
    reference_price = (
        market_snapshot.ask_price
        if market_snapshot.ask_price > Decimal("0")
        else market_snapshot.last_trade_price
    )
    if reference_price <= Decimal("0"):
        return Decimal("0")
    multiplier = Decimal("1") + (buffer_bps / Decimal("10000"))
    return (reference_price * multiplier).quantize(CENT, rounding=ROUND_HALF_UP)


def _percent_of(value: Decimal, percent: Decimal) -> Decimal:
    if value <= Decimal("0") or percent <= Decimal("0"):
        return Decimal("0")
    return value * percent / Decimal("100")


def _requested_quantity_from_policy(
    *,
    policy: RuntimeSizingPolicy,
    portfolio_state: PortfolioState,
    last_trade_price: Decimal,
) -> Decimal:
    if policy.mode == "fixed_shares":
        return _whole_share_quantity(policy.fixed_quantity)
    if policy.mode == "percent_equity":
        target_notional = _percent_of(
            portfolio_state.equity,
            policy.equity_percent,
        )
        return _quantity_from_notional(
            notional=target_notional,
            last_trade_price=last_trade_price,
        )
    raise ValueError(f"Unsupported runtime sizing mode: {policy.mode!r}.")


def _max_entry_notional(
    *,
    policy: RuntimeSizingPolicy,
    portfolio_state: PortfolioState,
    sizing_budget: RuntimeSizingBudget | None = None,
) -> Decimal:
    max_notional = (
        sizing_budget.remaining_notional
        if sizing_budget is not None
        else _max_cycle_notional(policy=policy, portfolio_state=portfolio_state)
    )
    if policy.max_order_notional is not None:
        max_notional = min(max_notional, max(Decimal("0"), policy.max_order_notional))
    return max_notional


def _max_cycle_notional(
    *,
    policy: RuntimeSizingPolicy,
    portfolio_state: PortfolioState,
) -> Decimal:
    reserve_notional = _percent_of(
        portfolio_state.equity,
        max(Decimal("0"), policy.cash_reserve_percent),
    )
    cash_after_reserve = max(Decimal("0"), portfolio_state.cash - reserve_notional)
    buying_power = max(Decimal("0"), portfolio_state.buying_power)
    return min(cash_after_reserve, buying_power)


def _quantity_from_notional(
    *,
    notional: Decimal,
    last_trade_price: Decimal,
) -> Decimal:
    if notional <= Decimal("0") or last_trade_price <= Decimal("0"):
        return Decimal("0")
    return _whole_share_quantity(notional / last_trade_price)


def _whole_share_quantity(quantity: Decimal) -> Decimal:
    if quantity <= Decimal("0"):
        return Decimal("0")
    return quantity.quantize(Decimal("1"), rounding=ROUND_DOWN)


def apply_position_sizing(
    ohlcv: pd.DataFrame,
    *,
    signal: pd.Series,
    pre_sized: bool,
    kelly_fraction: float = KELLY_FRACTION,
    target_volatility: float = TARGET_VOLATILITY,
    realized_vol_window_days: int = REALIZED_VOL_WINDOW_DAYS,
    max_gross_leverage: float = MAX_GROSS_LEVERAGE,
    forecast_method: str = "realized",
) -> pd.Series:
    _validate_ohlcv(ohlcv)
    if not signal.index.equals(ohlcv.index):
        raise ValueError("signal must share the OHLCV index.")
    if pre_sized:
        return signal.astype(float).copy()

    close_returns = ohlcv["close"].astype(float).pct_change()
    leverage = volatility_scale(
        target_vol=target_volatility,
        realized_vol=forecast_volatility(
            close_returns,
            lookback_days=realized_vol_window_days,
            forecast_method=forecast_method,
        ),
        max_gross_leverage=max_gross_leverage,
    )
    sized_signal = signal.astype(float) * kelly_fraction * leverage
    return sized_signal.clip(
        lower=-max_gross_leverage,
        upper=max_gross_leverage,
    )


def _validate_ohlcv(ohlcv: pd.DataFrame) -> None:
    missing = tuple(column for column in REQUIRED_OHLCV_COLUMNS if column not in ohlcv)
    if missing:
        missing_columns = ", ".join(missing)
        raise ValueError(f"OHLCV frame is missing required columns: {missing_columns}.")


__all__ = (
    "KELLY_FRACTION",
    "MAX_GROSS_LEVERAGE",
    "REALIZED_VOL_WINDOW_DAYS",
    "RuntimeSizingBudget",
    "RuntimeSizingPolicy",
    "TARGET_VOLATILITY",
    "apply_position_sizing",
    "build_runtime_sizing_budget",
    "cap_entry_quantity",
    "entry_marketable_limit_price",
    "resolve_entry_quantity",
)
