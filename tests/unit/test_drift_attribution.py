from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingx.drift.attribution import (
    SleeveAttributionRecorder,
    build_sleeve_daily_attribution_record,
)
from tradingx.types import (
    PortfolioState,
    PositionSnapshot,
    StrategyCandidate,
)


def _state(
    *,
    equity: Decimal,
    spy_quantity: Decimal = Decimal("0"),
    spy_price: Decimal = Decimal("100"),
) -> PortfolioState:
    positions = ()
    if spy_quantity > 0:
        positions = (
            PositionSnapshot(
                symbol="SPY",
                quantity=spy_quantity,
                average_entry_price=spy_price,
                market_value=spy_quantity * spy_price,
            ),
        )
    return PortfolioState(
        as_of_utc=datetime(2026, 4, 21, 14, 30, tzinfo=UTC),
        cash=equity - (spy_quantity * spy_price),
        equity=equity,
        buying_power=equity,
        positions=positions,
        open_orders=(),
    )


def test_build_record_captures_daily_return() -> None:
    record = build_sleeve_daily_attribution_record(
        attribution_id="attr-1",
        trading_day="2026-04-21",
        active_sleeve_id="trend-following-v1",
        open_portfolio_state=_state(
            equity=Decimal("100000"),
            spy_quantity=Decimal("400"),
        ),
        close_portfolio_state=_state(
            equity=Decimal("101000"),
            spy_quantity=Decimal("400"),
            spy_price=Decimal("102.5"),
        ),
        recorded_at_utc=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
    )
    assert record.sleeve_id == "trend-following-v1"
    assert record.trading_day == "2026-04-21"
    assert record.starting_equity == Decimal("100000")
    assert record.ending_equity == Decimal("101000")
    assert record.daily_return == Decimal("0.01")


def test_build_record_raises_on_zero_open_equity() -> None:
    with pytest.raises(ValueError, match="starting_equity"):
        build_sleeve_daily_attribution_record(
            attribution_id="attr-x",
            trading_day="2026-04-21",
            active_sleeve_id="x-v1",
            open_portfolio_state=_state(equity=Decimal("0")),
            close_portfolio_state=_state(equity=Decimal("0")),
            recorded_at_utc=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
        )


class _FakeActivationGateway:
    def __init__(self, *, candidate: StrategyCandidate | None) -> None:
        self._candidate = candidate

    def get_latest_activation(self):
        return None

    def get_active_candidate(self) -> StrategyCandidate | None:
        return self._candidate


class _FakeStore:
    def __init__(self) -> None:
        self.written = []

    def write_sleeve_daily_attribution_record(self, record):
        self.written.append(record)


def test_recorder_skips_non_sleeve_active_strategy() -> None:
    candidate = StrategyCandidate(
        candidate_id="baseline-long-only-v1",
        family="baseline",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="active",
        sleeve_class_path=None,
    )
    recorder = SleeveAttributionRecorder(
        activation_gateway=_FakeActivationGateway(candidate=candidate),
        attribution_store=_FakeStore(),
        now_provider=lambda: datetime(2026, 4, 21, tzinfo=UTC),
    )

    result = recorder.record_session(
        trading_day="2026-04-21",
        open_portfolio_state=_state(equity=Decimal("100000")),
        close_portfolio_state=_state(equity=Decimal("101000")),
    )

    assert result is None


def test_recorder_writes_record_for_sleeve_backed_active_strategy() -> None:
    candidate = StrategyCandidate(
        candidate_id="trend-following-v1",
        family="trend_following",
        benchmark_symbol="SPY",
        universe=("SPY",),
        parameter_set={},
        status="active",
        sleeve_class_path="tradingx.sleeves.trend.TrendSleeve",
    )
    store = _FakeStore()
    recorder = SleeveAttributionRecorder(
        activation_gateway=_FakeActivationGateway(candidate=candidate),
        attribution_store=store,
        now_provider=lambda: datetime(2026, 4, 21, tzinfo=UTC),
    )

    result = recorder.record_session(
        trading_day="2026-04-21",
        open_portfolio_state=_state(equity=Decimal("100000")),
        close_portfolio_state=_state(equity=Decimal("101000")),
    )

    assert result is not None
    assert result.sleeve_id == "trend-following-v1"
    assert store.written == [result]
