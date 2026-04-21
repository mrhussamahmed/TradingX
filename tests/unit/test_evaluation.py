from __future__ import annotations

import importlib
import logging
import math
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from tradingx.costs import CostModelConfig
from tradingx.evaluation import (
    AdversarialCheckContext,
    _cost_sensitivity_check,
    _oos_check,
    _parameter_sensitivity_check,
    _perturb_value,
    _regime_behavior_check,
    _sharpe_ratio,
    evaluate_candidate,
)
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.trials import TrialsLedger
from tradingx.types import ScalarValue, TrialRecord


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


def _benchmark_returns(periods: int) -> tuple[Decimal, ...]:
    return tuple(
        Decimal("0.004") if index % 3 else Decimal("-0.001")
        for index in range(periods)
    )


def _moderate_positive_returns(periods: int = 1200) -> tuple[Decimal, ...]:
    return tuple(
        Decimal(str(0.0001 + 0.001 * math.sin(index * 0.17)))
        for index in range(periods)
    )


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
        self.cost_calls: list[CostModelConfig] = []

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
        if cost_model_config is not None:
            self.cost_calls.append(cost_model_config)
        if cost_model_config is not None and (
            cost_model_config.half_spread_multiplier > 1.0
            or cost_model_config.impact_coefficient > 10.0
            or cost_model_config.commission_per_share > 0.0
        ):
            return self.cost_returns
        return self.base_returns


def _seed_family_trials(ledger: TrialsLedger, family: str, sharpes: list[str]) -> None:
    for index, sharpe in enumerate(sharpes):
        ledger.record(
            TrialRecord(
                trial_id=str(uuid.uuid4()),
                candidate_id=f"{family}-v{index}",
                family=family,
                window_start_utc=datetime(2025, 1, 1, tzinfo=UTC),
                window_end_utc=datetime(2025, 12, 31, tzinfo=UTC),
                observed_sharpe_net_of_costs=Decimal(sharpe),
                observed_cagr_net_of_costs=Decimal("0.10"),
                observed_max_drawdown=Decimal("0.08"),
                observed_cdar_95=Decimal("0.05"),
                annualized_cost_drag_bps=Decimal("6"),
                passed=True,
                recorded_at_utc=datetime(2025, 12, 31, tzinfo=UTC),
                git_sha="seed",
                config_fingerprint="seed",
            )
        )


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
        benchmark_returns=_benchmark_returns(len(base_returns)),
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


def test_evaluate_candidate_threads_cost_drag_to_evidence_pack() -> None:
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
        benchmark_returns=_benchmark_returns(len(base_returns)),
        window_start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        adversarial_context=context,
        annualized_cost_drag_bps=Decimal("12.5"),
    )

    assert evidence.annualized_cost_drag_bps == Decimal("12.5")


def test_evaluate_candidate_cost_drag_is_none_when_not_supplied() -> None:
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
        benchmark_returns=_benchmark_returns(len(base_returns)),
        window_start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        adversarial_context=context,
    )

    assert evidence.annualized_cost_drag_bps is None


def test_evaluate_candidate_populates_dsr_when_trials_sufficient(
    tmp_path,
) -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    base_returns = _moderate_positive_returns()
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    _seed_family_trials(
        ledger,
        family="trend_following",
        sharpes=["0.5", "0.8", "1.1", "1.3"],
    )
    context = AdversarialCheckContext(
        benchmark_bars=_benchmark_bars(),
        backtest_runner=FakeBacktestRunner(base_returns=base_returns),
        base_cost_model_config=CostModelConfig(),
    )

    evidence = evaluate_candidate(
        candidate,
        candidate_returns=base_returns,
        benchmark_returns=_benchmark_returns(len(base_returns)),
        window_start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        adversarial_context=context,
        annualized_cost_drag_bps=Decimal("7.0"),
        trials_ledger=ledger,
    )

    assert evidence.deflated_sharpe_ratio is not None
    assert isinstance(evidence.deflated_sharpe_ratio, Decimal)


def test_evaluate_candidate_dsr_is_none_when_trials_insufficient(tmp_path) -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    base_returns = _stable_returns()
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    context = AdversarialCheckContext(
        benchmark_bars=_benchmark_bars(),
        backtest_runner=FakeBacktestRunner(base_returns=base_returns),
        base_cost_model_config=CostModelConfig(),
    )

    evidence = evaluate_candidate(
        candidate,
        candidate_returns=base_returns,
        benchmark_returns=_benchmark_returns(len(base_returns)),
        window_start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        adversarial_context=context,
        annualized_cost_drag_bps=Decimal("7.0"),
        trials_ledger=ledger,
    )

    assert evidence.deflated_sharpe_ratio is None


def test_evaluate_candidate_sets_north_star_flag_when_sharpe_present(tmp_path) -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    base_returns = _stable_returns()
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    context = AdversarialCheckContext(
        benchmark_bars=_benchmark_bars(),
        backtest_runner=FakeBacktestRunner(base_returns=base_returns),
        base_cost_model_config=CostModelConfig(),
    )

    evidence = evaluate_candidate(
        candidate,
        candidate_returns=base_returns,
        benchmark_returns=_benchmark_returns(len(base_returns)),
        window_start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        adversarial_context=context,
        annualized_cost_drag_bps=Decimal("5.0"),
        trials_ledger=ledger,
    )

    assert evidence.north_star_sharpe_met is True


def test_evaluate_candidate_does_not_record_trial(tmp_path) -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    base_returns = _stable_returns()
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    context = AdversarialCheckContext(
        benchmark_bars=_benchmark_bars(),
        backtest_runner=FakeBacktestRunner(base_returns=base_returns),
        base_cost_model_config=CostModelConfig(),
    )

    _ = evaluate_candidate(
        candidate,
        candidate_returns=base_returns,
        benchmark_returns=_benchmark_returns(len(base_returns)),
        window_start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
        adversarial_context=context,
        annualized_cost_drag_bps=Decimal("7.0"),
        trials_ledger=ledger,
    )

    records = ledger.list_for_candidate(candidate.candidate_id)

    assert records == ()


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


def test_regime_behavior_check_ignores_rows_without_trend_context() -> None:
    benchmark_bars = _benchmark_bars(periods=320)
    candidate_returns = []
    for index in range(320):
        if 60 <= index < 140:
            candidate_returns.append(
                Decimal("-0.010") if index % 2 == 0 else Decimal("-0.006")
            )
        else:
            candidate_returns.append(
                Decimal("0.012") if index % 2 == 0 else Decimal("0.007")
            )

    result = _regime_behavior_check(
        tuple(candidate_returns),
        benchmark_bars=benchmark_bars,
    )

    assert result == "regime_behavior_pass"


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


def test_cost_sensitivity_check_uses_one_two_and_four_x_cost_grid() -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    runner = FakeBacktestRunner(
        base_returns=_stable_returns(),
        cost_returns=_stable_returns(),
    )

    result = _cost_sensitivity_check(
        candidate,
        backtest_runner=runner,
        base_cost_model_config=CostModelConfig(),
    )

    assert result == "cost_sensitivity_pass"
    assert {
        call.half_spread_multiplier for call in runner.cost_calls
    } >= {1.0, 2.0, 4.0}
    assert {call.impact_coefficient for call in runner.cost_calls} >= {10.0, 20.0, 40.0}


def test_cost_sensitivity_check_uses_distinct_commission_stresses_from_zero_base() -> (
    None
):
    candidate = build_mandatory_candidate_registry(("SPY",))[0]
    runner = FakeBacktestRunner(
        base_returns=_stable_returns(),
        cost_returns=_stable_returns(),
    )

    result = _cost_sensitivity_check(
        candidate,
        backtest_runner=runner,
        base_cost_model_config=CostModelConfig(),
    )

    assert result == "cost_sensitivity_pass"
    commission_levels = {call.commission_per_share for call in runner.cost_calls}
    assert commission_levels >= {0.0, 0.0002, 0.0004}


def test_perturb_value_moves_integer_one_off_the_base_value() -> None:
    assert _perturb_value(1, 0.6) != 1
    assert _perturb_value(1, 1.4) != 1


def test_sharpe_ratio_returns_none_for_constant_return_series(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        sharpe_ratio = _sharpe_ratio(
            returns=[0.01] * 40,
            risk_free_daily_rates=[0.0] * 40,
        )

    assert sharpe_ratio is None
    assert "variance is zero" in caplog.text
