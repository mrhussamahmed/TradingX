from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.sizing import RuntimeSizingPolicy, resolve_entry_quantity
from tradingx.types import MarketSnapshot, PortfolioState


def _portfolio_state(
    *,
    cash: Decimal = Decimal("100000"),
    equity: Decimal = Decimal("100000"),
    buying_power: Decimal = Decimal("100000"),
) -> PortfolioState:
    return PortfolioState(
        as_of_utc=datetime(2026, 4, 29, 13, 30, tzinfo=UTC),
        cash=cash,
        equity=equity,
        buying_power=buying_power,
        positions=(),
        open_orders=(),
    )


def _market_snapshot(*, price: Decimal) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="SPY",
        last_trade_price=price,
        bid_price=price - Decimal("0.05"),
        ask_price=price + Decimal("0.05"),
        average_daily_volume_30d=Decimal("1500000"),
        timestamp=datetime(2026, 4, 29, 13, 30, tzinfo=UTC),
    )


def test_percent_equity_sizing_converts_target_notional_to_whole_shares() -> None:
    quantity = resolve_entry_quantity(
        policy=RuntimeSizingPolicy(
            mode="percent_equity",
            equity_percent=Decimal("5"),
            cash_reserve_percent=Decimal("20"),
        ),
        portfolio_state=_portfolio_state(),
        market_snapshot=_market_snapshot(price=Decimal("200")),
        fallback_quantity=Decimal("1"),
    )

    assert quantity == Decimal("24")


def test_fixed_share_sizing_is_capped_by_order_notional() -> None:
    quantity = resolve_entry_quantity(
        policy=RuntimeSizingPolicy(
            mode="fixed_shares",
            fixed_quantity=Decimal("20"),
            max_order_notional=Decimal("950"),
            cash_reserve_percent=Decimal("0"),
        ),
        portfolio_state=_portfolio_state(),
        market_snapshot=_market_snapshot(price=Decimal("100")),
        fallback_quantity=Decimal("1"),
    )

    assert quantity == Decimal("9")


def test_order_notional_cap_uses_marketable_buy_limit_price() -> None:
    quantity = resolve_entry_quantity(
        policy=RuntimeSizingPolicy(
            mode="fixed_shares",
            fixed_quantity=Decimal("20"),
            max_order_notional=Decimal("1000"),
            cash_reserve_percent=Decimal("0"),
        ),
        portfolio_state=_portfolio_state(),
        market_snapshot=_market_snapshot(price=Decimal("100")),
        fallback_quantity=Decimal("1"),
    )

    assert quantity == Decimal("9")


def test_sizing_respects_cash_reserve_before_requesting_an_entry() -> None:
    quantity = resolve_entry_quantity(
        policy=RuntimeSizingPolicy(
            mode="percent_equity",
            equity_percent=Decimal("5"),
            cash_reserve_percent=Decimal("20"),
        ),
        portfolio_state=_portfolio_state(
            cash=Decimal("1000"),
            equity=Decimal("100000"),
            buying_power=Decimal("1000"),
        ),
        market_snapshot=_market_snapshot(price=Decimal("100")),
        fallback_quantity=Decimal("1"),
    )

    assert quantity == Decimal("0")
