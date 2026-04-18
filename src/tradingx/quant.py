from __future__ import annotations

from decimal import Decimal
from math import sqrt

from tradingx.types import MarketSnapshot

ZERO = Decimal("0")
ONE = Decimal("1")
ADV_FLOOR = Decimal(
    "1000000"
)  # source: .specify/memory/constitution.md (retrieved 2026-04-19)
PRICE_FLOOR = Decimal(
    "5.00"
)  # source: .specify/memory/constitution.md (retrieved 2026-04-19)


def decimal_mean(values: tuple[Decimal, ...] | list[Decimal]) -> Decimal:
    if not values:
        return ZERO
    return sum(values, ZERO) / Decimal(len(values))


def decimal_stddev(values: tuple[Decimal, ...] | list[Decimal]) -> Decimal:
    if len(values) < 2:
        return ZERO
    mean = decimal_mean(values)
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values))
    return Decimal(str(sqrt(float(variance))))


def spread_bps(snapshot: MarketSnapshot) -> Decimal:
    if snapshot.last_trade_price <= ZERO:
        return ZERO
    spread = snapshot.ask_price - snapshot.bid_price
    return (spread / snapshot.last_trade_price) * Decimal("10000")


def liquidity_weight(average_daily_volume_30d: Decimal) -> Decimal:
    if average_daily_volume_30d <= ZERO:
        return ZERO
    return min(Decimal("1.5"), average_daily_volume_30d / ADV_FLOOR)


def binomial_lower_bound(successes: int, total: int) -> Decimal:
    if total <= 0:
        return ZERO
    probability = successes / total
    standard_error = sqrt((probability * (1 - probability)) / total)
    lower_bound = probability - (1.96 * standard_error)
    return max(ZERO, Decimal(str(lower_bound)))


__all__ = (
    "ADV_FLOOR",
    "PRICE_FLOOR",
    "ZERO",
    "binomial_lower_bound",
    "decimal_mean",
    "decimal_stddev",
    "liquidity_weight",
    "spread_bps",
)
