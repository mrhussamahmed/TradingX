"""Turnover-aware trading cost estimates for daily-bar research.

Sources:
- Alpaca commission disclosure, which states that commission-free
  trading is available to Alpaca retail customers and that relevant
  regulatory fees may still apply:
  https://alpaca.markets/ (retrieved 2026-04-19)
- SEC Section 31 Transaction Fee Rate Advisory for Fiscal Year 2026:
  https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2
  (retrieved 2026-04-19)
- FINRA fee adjustment schedule:
  https://www.finra.org/rules-guidance/rule-filings/sr-finra-2024-019/fee-adjustment-schedule
  (retrieved 2026-04-19)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CostModelConfig:
    half_spread_multiplier: float = 1.0
    impact_coefficient: float = 10.0
    commission_per_share: float = 0.0
    sec_fee_per_dollar: float = 20.60 / 1_000_000.0
    finra_taf_per_share: float = 0.000195
    finra_taf_max_per_trade: float = 9.79


@dataclass(frozen=True)
class TradeCostBreakdown:
    half_spread: float
    impact: float
    commission: float
    sec_fee: float
    finra_taf: float
    total: float


def estimate_trade_costs(
    *,
    side: str,
    quantity: float,
    fill_price: float,
    bid_price: float | None,
    ask_price: float | None,
    daily_dollar_volume: float,
    sigma_20d_bps: float,
    config: CostModelConfig | None = None,
) -> TradeCostBreakdown:
    resolved_config = config or CostModelConfig()
    absolute_quantity = abs(float(quantity))
    if absolute_quantity == 0.0:
        return TradeCostBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    if resolved_config.half_spread_multiplier > 0.0 and (
        bid_price is None or ask_price is None
    ):
        raise ValueError("bid and ask prices are required for half-spread costs.")

    trade_notional = absolute_quantity * float(fill_price)
    half_spread = 0.0
    if bid_price is not None and ask_price is not None:
        half_spread = (
            max(float(ask_price) - float(bid_price), 0.0)
            / 2.0
            * absolute_quantity
            * resolved_config.half_spread_multiplier
        )

    impact = 0.0
    if daily_dollar_volume > 0.0 and sigma_20d_bps > 0.0:
        impact_bps = (
            resolved_config.impact_coefficient
            * math.sqrt(trade_notional / daily_dollar_volume)
            * sigma_20d_bps
        )
        impact = trade_notional * (impact_bps / 10_000.0)

    commission = absolute_quantity * resolved_config.commission_per_share
    is_sell = side.lower() == "sell"
    sec_fee = trade_notional * resolved_config.sec_fee_per_dollar if is_sell else 0.0
    finra_taf = (
        min(
            absolute_quantity * resolved_config.finra_taf_per_share,
            resolved_config.finra_taf_max_per_trade,
        )
        if is_sell
        else 0.0
    )
    total = half_spread + impact + commission + sec_fee + finra_taf
    return TradeCostBreakdown(
        half_spread=half_spread,
        impact=impact,
        commission=commission,
        sec_fee=sec_fee,
        finra_taf=finra_taf,
        total=total,
    )


__all__ = (
    "CostModelConfig",
    "TradeCostBreakdown",
    "estimate_trade_costs",
)
