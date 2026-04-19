from __future__ import annotations

import importlib
import logging
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.evaluation import (
    _sharpe_ratio,
    evaluate_candidate,
)
from tradingx.strategy import build_mandatory_candidate_registry


def test_evaluation_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.evaluation")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_evaluate_candidate_produces_benchmark_relative_evidence_pack() -> None:
    candidate = build_mandatory_candidate_registry(("SPY",))[0]

    evidence = evaluate_candidate(
        candidate,
        candidate_returns=(
            Decimal("0.010"),
            Decimal("0.012"),
            Decimal("-0.002"),
            Decimal("0.009"),
        ),
        benchmark_returns=(
            Decimal("0.004"),
            Decimal("0.005"),
            Decimal("-0.001"),
            Decimal("0.003"),
        ),
        window_start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 17, tzinfo=UTC),
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


def test_sharpe_ratio_returns_none_for_constant_return_series(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        sharpe_ratio = _sharpe_ratio(
            returns=[0.01] * 40,
            risk_free_daily_rates=[0.0] * 40,
        )

    assert sharpe_ratio is None
    assert "variance is zero" in caplog.text
