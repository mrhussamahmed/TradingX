from __future__ import annotations

import importlib

import pytest


def test_costs_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.costs")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_estimate_trade_costs_uses_bid_ask_impact_and_sell_fees() -> None:
    module = importlib.import_module("tradingx.costs")
    costs = module.estimate_trade_costs(
        side="sell",
        quantity=100.0,
        fill_price=100.0,
        bid_price=99.98,
        ask_price=100.02,
        daily_dollar_volume=10_000_000.0,
        sigma_20d_bps=25.0,
    )

    assert costs.half_spread == pytest.approx(2.0)
    assert costs.impact > 0.0
    assert costs.commission == pytest.approx(0.0)
    assert costs.sec_fee == pytest.approx(0.206)
    assert costs.finra_taf == pytest.approx(0.0195)
    assert costs.total == pytest.approx(
        costs.half_spread
        + costs.impact
        + costs.commission
        + costs.sec_fee
        + costs.finra_taf
    )


def test_estimate_trade_costs_requires_bid_ask_when_spread_multiplier_is_nonzero(
) -> None:
    module = importlib.import_module("tradingx.costs")

    with pytest.raises(ValueError, match="bid and ask prices are required"):
        module.estimate_trade_costs(
            side="buy",
            quantity=10.0,
            fill_price=100.0,
            bid_price=None,
            ask_price=None,
            daily_dollar_volume=1_000_000.0,
            sigma_20d_bps=15.0,
        )
