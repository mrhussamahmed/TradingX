from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from collections.abc import Sequence

from datetime import UTC, datetime

from tradingx.benchmark_stack import (
    BenchmarkStack,
    CashHurdle,
    PassiveOpportunityCost,
    build_default_benchmark_stack,
)
from tradingx.config import (
    AlertingConfig,
    LiveTradingControls,
    PaperCredentials,
    RuntimeConfig,
    TradingConfig,
    WebAppConfig,
)
from tradingx.types import (
    BenchmarkCloseSeries,
    BenchmarkStackPayload,
    OperatingConstraintBudget,
)


class _FakeRiskFreeSeries:
    def __init__(self, daily_rates: dict[date, Decimal]) -> None:
        self._daily_rates = daily_rates

    def get_daily_rate(self, session_date: date) -> Decimal:
        return self._daily_rates[session_date]


class _FakeClosesProvider:
    def __init__(self, closes_by_symbol: dict[str, list[Decimal]]) -> None:
        self._closes_by_symbol = closes_by_symbol

    def get_closes(
        self,
        symbol: str,
        *,
        session_dates: Sequence[date],
    ) -> tuple[Decimal, ...]:
        del session_dates
        return tuple(self._closes_by_symbol[symbol])


class _StubMarketDataGateway:
    def __init__(self, closes_by_symbol: dict[str, list[Decimal]]) -> None:
        self._closes_by_symbol = closes_by_symbol

    def get_daily_close_series(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
        feed: str,
        adjustment: str,
    ) -> BenchmarkCloseSeries:
        del start_utc, end_utc, feed, adjustment
        return BenchmarkCloseSeries(
            symbol=symbol,
            closes=tuple(self._closes_by_symbol[symbol]),
            window_start_utc=datetime(2026, 1, 5, tzinfo=UTC),
            window_end_utc=datetime(2026, 1, 7, tzinfo=UTC),
            generated_at_utc=datetime(2026, 1, 8, tzinfo=UTC),
            feed="iex",
            adjustment="dividend",
            series_is_adjusted=True,
        )


def _build_trading_config() -> TradingConfig:
    return TradingConfig(
        paper_credentials=PaperCredentials(
            api_key="paper-key",
            api_secret="paper-secret",
            account_id="paper-account",
        ),
        live_controls=LiveTradingControls(),
        alerting=AlertingConfig(),
        runtime=RuntimeConfig(),
        web=WebAppConfig(),
    )


def test_cash_hurdle_daily_returns_uses_cached_daily_rates() -> None:
    daily_rates = {
        date(2026, 1, 5): Decimal("0.0002"),
        date(2026, 1, 6): Decimal("0.0002"),
        date(2026, 1, 7): Decimal("0.0002"),
    }
    hurdle = CashHurdle(risk_free_series=_FakeRiskFreeSeries(daily_rates))

    returns = hurdle.daily_returns(
        session_dates=(
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
        )
    )

    assert returns == (
        Decimal("0.0002"),
        Decimal("0.0002"),
        Decimal("0.0002"),
    )


def test_cash_hurdle_rejects_empty_session_dates() -> None:
    hurdle = CashHurdle(risk_free_series=_FakeRiskFreeSeries({}))

    with pytest.raises(ValueError):
        hurdle.daily_returns(session_dates=())


def test_opportunity_cost_blends_weighted_returns_without_rebalance() -> None:
    closes_provider = _FakeClosesProvider(
        {
            "SPY": [
                Decimal("100"),
                Decimal("101"),
                Decimal("99.99"),
                Decimal("101.9898"),
            ],
            "AGG": [
                Decimal("100"),
                Decimal("100"),
                Decimal("100.5"),
                Decimal("100.299"),
            ],
        }
    )
    opportunity_cost = PassiveOpportunityCost(
        closes_provider=closes_provider,
        weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )

    returns = opportunity_cost.daily_returns(
        session_dates=(
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
            date(2026, 1, 8),
        )
    )

    assert float(returns[0]) == pytest.approx(0.006, abs=1e-6)
    assert float(returns[1]) == pytest.approx(-0.0040357853, abs=1e-6)
    assert float(returns[2]) == pytest.approx(0.0111731241, abs=1e-6)


def test_opportunity_cost_rebalances_at_month_boundary() -> None:
    closes_provider = _FakeClosesProvider(
        {
            "SPY": [Decimal("100"), Decimal("120"), Decimal("115")],
            "AGG": [Decimal("100"), Decimal("100"), Decimal("101")],
        }
    )
    opportunity_cost = PassiveOpportunityCost(
        closes_provider=closes_provider,
        weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )

    returns = opportunity_cost.daily_returns(
        session_dates=(
            date(2026, 1, 30),
            date(2026, 1, 31),
            date(2026, 2, 1),
        )
    )

    assert float(returns[0]) == pytest.approx(0.12, abs=1e-6)
    assert float(returns[1]) == pytest.approx(-0.021, abs=1e-6)


def test_opportunity_cost_uses_leading_prior_close_when_available() -> None:
    opportunity_cost = PassiveOpportunityCost(
        closes_provider=_FakeClosesProvider(
            {
                "SPY": [
                    Decimal("99"),
                    Decimal("100"),
                    Decimal("101"),
                    Decimal("99.99"),
                ],
                "AGG": [
                    Decimal("100"),
                    Decimal("100"),
                    Decimal("100"),
                    Decimal("100.5"),
                ],
            }
        ),
        weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )

    returns = opportunity_cost.daily_returns(
        session_dates=(
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
        )
    )

    assert len(returns) == 3
    assert float(returns[0]) == pytest.approx(0.0060606061, abs=1e-6)


def test_benchmark_stack_materializes_full_payload() -> None:
    hurdle = CashHurdle(
        risk_free_series=_FakeRiskFreeSeries(
            {
                date(2026, 1, 5): Decimal("0.0002"),
                date(2026, 1, 6): Decimal("0.0002"),
                date(2026, 1, 7): Decimal("0.0002"),
            }
        )
    )
    opportunity_cost = PassiveOpportunityCost(
        closes_provider=_FakeClosesProvider(
            {
                "SPY": [Decimal("100"), Decimal("101"), Decimal("99.99")],
                "AGG": [Decimal("100"), Decimal("100"), Decimal("100.5")],
            }
        ),
        weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )
    operating_constraint = OperatingConstraintBudget(
        max_drawdown_design=Decimal("0.15"),
        max_drawdown_halt=Decimal("0.25"),
        cdar_threshold=Decimal("0.08"),
        cdar_confidence=Decimal("0.95"),
    )
    stack = BenchmarkStack(
        hurdle=hurdle,
        opportunity_cost=opportunity_cost,
        operating_constraint=operating_constraint,
    )

    payload = stack.materialize(
        session_dates=(
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
        )
    )

    assert isinstance(payload, BenchmarkStackPayload)
    assert payload.hurdle_returns == (
        Decimal("0.0002"),
        Decimal("0.0002"),
        Decimal("0.0002"),
    )
    assert payload.opportunity_cost_returns == (
        Decimal("0.006"),
        Decimal("-0.004035785288270377733598409543"),
    )
    assert payload.opportunity_cost_weights == (
        ("SPY", Decimal("0.6")),
        ("AGG", Decimal("0.4")),
    )
    assert payload.operating_constraint == operating_constraint


def test_build_default_benchmark_stack_wires_default_dependencies() -> None:
    stack = build_default_benchmark_stack(
        _build_trading_config(),
        market_data_gateway=_StubMarketDataGateway(
            {
                "SPY": [Decimal("100"), Decimal("101")],
                "AGG": [Decimal("100"), Decimal("100")],
            }
        ),
        risk_free_series=_FakeRiskFreeSeries({date(2026, 1, 5): Decimal("0.0002")}),
    )

    assert isinstance(stack, BenchmarkStack)
    assert stack.opportunity_cost.weights == (
        ("SPY", Decimal("0.6")),
        ("AGG", Decimal("0.4")),
    )
    assert stack.operating_constraint.max_drawdown_design == Decimal("0.15")
    assert stack.operating_constraint.max_drawdown_halt == Decimal("0.25")
    assert stack.operating_constraint.cdar_threshold == Decimal("0.08")
    assert stack.operating_constraint.cdar_confidence == Decimal("0.95")
