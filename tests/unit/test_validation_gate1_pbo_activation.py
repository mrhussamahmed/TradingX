from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.costs import CostModelConfig
from tradingx.evaluation import AdversarialCheckContext
from tradingx.strategy import build_mandatory_candidate_registry
from tradingx.types import BenchmarkStackPayload, OperatingConstraintBudget
from tradingx.validation import _build_gate1_candidate_result_pass1


def _candidate_returns(periods: int) -> tuple[Decimal, ...]:
    pattern = (
        Decimal("0.0012"),
        Decimal("0.0011"),
        Decimal("-0.0003"),
        Decimal("0.0010"),
    )
    return tuple(pattern[index % len(pattern)] for index in range(periods))


def _benchmark_bars(periods: int) -> pd.DataFrame:
    closes = [
        100.0 + (0.12 * float(index)) + (1.5 * (-1.0 if index % 17 == 0 else 1.0))
        for index in range(periods)
    ]
    index = pd.date_range("2023-01-03", periods=periods, freq="B", tz=UTC)
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": [value + 0.6 for value in closes],
            "low": [value - 0.6 for value in closes],
            "close": closes,
            "volume": [1_000_000 + index_value for index_value in range(periods)],
        },
        index=index,
    )
    frame.index.name = "timestamp_utc"
    return frame


def _adversarial_context(
    periods: int,
    returns: tuple[Decimal, ...],
) -> AdversarialCheckContext:
    def _backtest_runner(*_args, **_kwargs) -> tuple[Decimal, ...]:
        return returns

    return AdversarialCheckContext(
        benchmark_bars=_benchmark_bars(periods),
        backtest_runner=_backtest_runner,
        base_cost_model_config=CostModelConfig(),
    )


def _benchmark_stack(periods: int) -> BenchmarkStackPayload:
    return BenchmarkStackPayload(
        hurdle_returns=tuple(Decimal("0.0001") for _ in range(periods)),
        opportunity_cost_returns=tuple(Decimal("0.0002") for _ in range(periods)),
        opportunity_cost_weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal("0.15"),
            max_drawdown_halt=Decimal("0.25"),
            cdar_threshold=Decimal("0.08"),
            cdar_confidence=Decimal("0.95"),
        ),
    )


def _criterion_by_id(result, criterion_id: str):  # type: ignore[no-untyped-def]
    return next(
        criterion
        for criterion in result.criteria
        if criterion.criterion_id == criterion_id
    )


def test_gate1_pbo_pending_keeps_candidate_pending() -> None:
    periods = 1100
    returns = _candidate_returns(periods)
    candidate = build_mandatory_candidate_registry(("SPY", "QQQ"))[0]
    result, pack = _build_gate1_candidate_result_pass1(
        candidate=candidate,
        candidate_returns=returns,
        benchmark_stack_payload=_benchmark_stack(periods),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 23, tzinfo=UTC),
        adversarial_context=_adversarial_context(periods, returns),
    )

    criterion = _criterion_by_id(result, "pbo_overfitting")
    assert result.status == "pending"
    assert criterion.status == "pending"
    assert criterion.passed is False
    assert pack.pbo_value is None
    assert pack.pbo_report_id is None


def test_gate1_pbo_pass_populates_pack_and_passes_criterion() -> None:
    periods = 1100
    returns = _candidate_returns(periods)
    candidate = build_mandatory_candidate_registry(("SPY", "QQQ"))[0]
    result, pack = _build_gate1_candidate_result_pass1(
        candidate=candidate,
        candidate_returns=returns,
        benchmark_stack_payload=_benchmark_stack(periods),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 23, tzinfo=UTC),
        adversarial_context=_adversarial_context(periods, returns),
        gate1_pbo_payload=(Decimal("0.18"), "pbo-run-1"),
    )

    criterion = _criterion_by_id(result, "pbo_overfitting")
    assert result.status == "pass"
    assert criterion.status == "pass"
    assert criterion.passed is True
    assert pack.pbo_value == Decimal("0.18")
    assert pack.pbo_report_id == "pbo-run-1"


def test_gate1_pbo_fail_fails_candidate() -> None:
    periods = 1100
    returns = _candidate_returns(periods)
    candidate = build_mandatory_candidate_registry(("SPY", "QQQ"))[0]
    result, pack = _build_gate1_candidate_result_pass1(
        candidate=candidate,
        candidate_returns=returns,
        benchmark_stack_payload=_benchmark_stack(periods),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 23, tzinfo=UTC),
        adversarial_context=_adversarial_context(periods, returns),
        gate1_pbo_payload=(Decimal("0.35"), "pbo-run-2"),
    )

    criterion = _criterion_by_id(result, "pbo_overfitting")
    assert result.status == "fail"
    assert criterion.status == "fail"
    assert criterion.passed is False
    assert pack.pbo_value == Decimal("0.35")
    assert pack.pbo_report_id == "pbo-run-2"


def test_gate1_pbo_payload_is_applied_to_non_sleeve_candidate() -> None:
    periods = 1100
    returns = _candidate_returns(periods)
    candidate = build_mandatory_candidate_registry(("SPY", "QQQ"))[2]
    result, pack = _build_gate1_candidate_result_pass1(
        candidate=candidate,
        candidate_returns=returns,
        benchmark_stack_payload=_benchmark_stack(periods),
        window_start_utc=datetime(2023, 1, 3, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 23, tzinfo=UTC),
        adversarial_context=_adversarial_context(periods, returns),
        gate1_pbo_payload=(Decimal("0.18"), "pbo-run-3"),
    )

    criterion = _criterion_by_id(result, "pbo_overfitting")
    assert result.status == "pass"
    assert criterion.status == "pass"
    assert pack.pbo_value == Decimal("0.18")
    assert pack.pbo_report_id == "pbo-run-3"
