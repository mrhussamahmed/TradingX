from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from tradingx.sleeves.mean_reversion import MeanReversionSleeve
from tradingx.types import RegimeSnapshot, SleeveContext


def _regime() -> RegimeSnapshot:
    return RegimeSnapshot(
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
    )


def _bars(close: tuple[float, ...]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(close), freq="D")
    return pd.DataFrame(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": [1_000_000] * len(close),
        },
        index=index,
    )


def test_mean_reversion_sleeve_flattens_negative_signals_without_shorting(
    monkeypatch,
) -> None:
    def fake_signal(*args, **kwargs):
        del args, kwargs
        return pd.DataFrame(
            {"QQQ": [-1.0]},
            index=pd.date_range("2026-04-30", periods=1, freq="D"),
        )

    monkeypatch.setattr(
        "tradingx.sleeves.mean_reversion.generate_mean_revert_signal",
        fake_signal,
    )
    sleeve = MeanReversionSleeve(
        sleeve_id="mean-reversion-v1",
        allowed_instruments=("QQQ",),
    )

    trades = sleeve.plan_for_bar(
        SleeveContext(
            observation_date=date(2026, 4, 30),
            bars_by_symbol={
                "SPY": _bars(tuple(float(100 + index) for index in range(130))),
                "QQQ": _bars(tuple(float(200 + index) for index in range(130))),
            },
            regime=_regime(),
            current_weights_by_symbol={"QQQ": Decimal("0.35")},
            sleeve_budget_equity=Decimal("20000"),
        )
    )

    assert trades[0].symbol == "QQQ"
    assert trades[0].target_weight_of_sleeve_budget == Decimal("0")
    assert trades[0].side == "sell"


def test_mean_reversion_sleeve_converts_positive_signal_to_long_target(
    monkeypatch,
) -> None:
    def fake_signal(*args, **kwargs):
        del args, kwargs
        return pd.DataFrame(
            {"QQQ": [1.0]},
            index=pd.date_range("2026-04-30", periods=1, freq="D"),
        )

    monkeypatch.setattr(
        "tradingx.sleeves.mean_reversion.generate_mean_revert_signal",
        fake_signal,
    )
    sleeve = MeanReversionSleeve(
        sleeve_id="mean-reversion-v1",
        allowed_instruments=("QQQ",),
    )

    trades = sleeve.plan_for_bar(
        SleeveContext(
            observation_date=date(2026, 4, 30),
            bars_by_symbol={
                "SPY": _bars(tuple(float(100 + index) for index in range(130))),
                "QQQ": _bars(tuple(float(200 + index) for index in range(130))),
            },
            regime=_regime(),
            current_weights_by_symbol={"QQQ": Decimal("0")},
            sleeve_budget_equity=Decimal("20000"),
        )
    )

    assert trades[0].symbol == "QQQ"
    assert trades[0].target_weight_of_sleeve_budget > Decimal("0")
    assert trades[0].side == "buy"
