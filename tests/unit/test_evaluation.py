from __future__ import annotations

import importlib
import logging
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from tradingx.costs import CostModelConfig
from tradingx.evaluation import (
    AdversarialCheckContext,
    _cost_sensitivity_check,
    _oos_check,
    _parameter_sensitivity_check,
    _regime_behavior_check,
    _sharpe_ratio,
    evaluate_candidate,
)
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.types import ScalarValue


def test_evaluation_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.evaluation")

    assert module.__doc__
    assert hasattr(module, "__all__")


def _benchmark_bars(periods: int = 1200) -> pd.DataFrame:
    index = pd.date_range("2021-01-04", periods=periods, freq="B", tz="UTC")
    closes: list[float] = []
    price = 100.0
    for position in range(periods):
        if position < periods // 3:
            daily_return = 0.001 if position % 2 == 0 else 0.0004
        elif position < (2 * periods) // 3:
            daily_return = 0.02 if position % 2 == 0 else -0.015
        else:
            daily_return = -0.002 if position % 2 == 0 else 0.001
        price *= 1.0 + daily_return
        closes.append(price)
    close_series = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close_series,
            "high": close_series * 1.01,
            "low": close_series * 0.99,
            "close": close_series,
            "volume": 1_000_000.0,
        },
        index=index,
    )


def _stable_returns(periods: int = 1200) -> tuple[Decimal, ...]:
    pattern = (
        Decimal("0.010"),
        Decimal("0.004"),
        Decimal("-0.002"),
        Decimal("0.008"),
    )
    return tuple(pattern[index % len(pattern)] for index in range(periods))


class FakeBacktestRunner:
    def __init__(
        self,
        *,
        base_returns: tuple[Decimal, ...],
        parameter_returns: tuple[Decimal, ...] | None = None,
        cost_returns: tuple[Decimal, ...] | None = None,
    ) -> None:
        self.base_returns = base_returns
        self.parameter_returns = parameter_returns or base_returns
        self.cost_returns = cost_returns or base_returns
        self.parameter_calls: list[dict[str, object]] = []

    def __call__(
        self,
        candidate,
        *,
        parameter_overrides: dict[str, ScalarValue] | None = None,
        cost_model_config: CostModelConfig | None = None,
    ) -> tuple[Decimal, ...]:
        del candidate
        if parameter_overrides is not None:
            self.parameter_calls.append(parameter_overrides)
            return self.parameter_returns
        if cost_model_config is not None and (
            cost_model_config.half_spread_multiplier > 1.0
            or cost_model_config.impact_coefficient > 10.0
            or cost_model_config.commission_per_share > 0.0
        ):
            return self.cost_returns
        return self.base_returns


def test_evaluate_candidate_produces_benchmark_relative_evidence_pack() -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    base_returns = _stable_returns()
    context = AdversarialCheckContext(
        benchmark_bars=_benchmark_bars(),
        backtest_runner=FakeBacktestRunner(base_returns=base_returns),
        base_cost_model_config=CostModelConfig(),
    )

    evidence = evaluate_candidate(
        candidate,
        candidate_returns=base_returns,
        benchmark_returns=tuple(
            Decimal("0.004") if index % 3 else Decimal("-0.001")
            for index in range(len(base_returns))
        ),
        window_start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        adversarial_context=context,
    )

    assert evidence.candidate_id == candidate.candidate_id
    assert evidence.recommendation == "keep"
    assert evidence.candidate_metrics["excess_return"] > 0
    assert set(evidence.adversarial_checks) == {
        "cost_sensitivity_pass",
        "out_of_sample_pass",
        "parameter_sensitivity_pass",
        "regime_behavior_pass",
    }


def test_oos_check_uses_settled_thirty_percent_tolerance_rule() -> None:
    base_returns = tuple([Decimal("0.010")] * 252 + [Decimal("-0.010")] * 756)

    result = _oos_check(base_returns)

    assert result == "out_of_sample_fail"


def test_parameter_sensitivity_check_fails_on_large_sharpe_drop() -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    runner = FakeBacktestRunner(
        base_returns=_stable_returns(),
        parameter_returns=tuple(Decimal("-0.005") for _ in range(1200)),
    )

    result = _parameter_sensitivity_check(
        candidate,
        backtest_runner=runner,
        base_returns=_stable_returns(),
    )

    assert result == "parameter_sensitivity_fail"
    assert runner.parameter_calls


def test_regime_behavior_check_fails_when_a_populated_regime_has_negative_sharpe() -> (
    None
):
    result = _regime_behavior_check(
        tuple(Decimal("-0.010") for _ in range(1200)),
        benchmark_bars=_benchmark_bars(),
    )

    assert result == "regime_behavior_fail"


def test_cost_sensitivity_check_requires_profitability_under_all_stresses() -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    runner = FakeBacktestRunner(
        base_returns=_stable_returns(),
        cost_returns=tuple(Decimal("-0.020") for _ in range(1200)),
    )

    result = _cost_sensitivity_check(
        candidate,
        backtest_runner=runner,
        base_cost_model_config=CostModelConfig(),
    )

    assert result == "cost_sensitivity_fail"


def test_sharpe_ratio_returns_none_for_constant_return_series(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        sharpe_ratio = _sharpe_ratio(
            returns=[0.01] * 40,
            risk_free_daily_rates=[0.0] * 40,
        )

    assert sharpe_ratio is None
    assert "variance is zero" in caplog.text
