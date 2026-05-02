from __future__ import annotations

from datetime import date
from decimal import Decimal

from tradingx.sleeves.baseline_long_only import BaselineLongOnlySleeve
from tradingx.types import RegimeSnapshot, SleeveContext


def test_baseline_long_only_sleeve_returns_no_trades_without_allowed_universe() -> None:
    sleeve = BaselineLongOnlySleeve(allowed_instruments=())

    trades = sleeve.plan_for_bar(
        SleeveContext(
            observation_date=date(2026, 4, 30),
            bars_by_symbol={},
            regime=RegimeSnapshot(
                observation_date=date(2026, 4, 30),
                regime="normal",
                above_sma_200=True,
                vix_elevated=False,
                vix_stressed=False,
                yield_curve_inverted=False,
                spy_close=Decimal("500"),
                spy_sma_200=Decimal("450"),
                vix_close=Decimal("15"),
                yield_curve_spread_bps=Decimal("50"),
            ),
            current_weights_by_symbol={},
            sleeve_budget_equity=Decimal("10000"),
        )
    )

    assert trades == ()
