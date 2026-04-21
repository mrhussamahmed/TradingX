from __future__ import annotations

from decimal import Decimal

from tradingx.validation import evaluate_marginal_portfolio_contribution


def _rets(*vals: str) -> tuple[Decimal, ...]:
    return tuple(Decimal(value) for value in vals)


def test_marginal_pass_when_all_three_metrics_improve() -> None:
    without = (
        (Decimal("0.0010"),) * 20
        + (Decimal("-0.0006"),) * 10
        + (Decimal("0.0012"),) * 10
    )
    with_ = (
        (Decimal("0.0020"),) * 20
        + (Decimal("-0.0002"),) * 10
        + (Decimal("0.0024"),) * 10
    )
    candidate = (Decimal("0.0025"),) * 40

    result = evaluate_marginal_portfolio_contribution(
        candidate_returns=candidate,
        portfolio_without_candidate_returns=without,
        portfolio_with_candidate_returns=with_,
    )

    assert result.criterion_id == "marginal_portfolio_contribution"
    assert result.passed is True


def test_marginal_fail_when_sharpe_degrades() -> None:
    without = _rets("0.005", "0.004", "0.006", "0.005", "0.004")
    with_ = _rets("0.001", "0.001", "0.001", "0.001", "0.001")
    candidate = _rets("-0.01", "0.0", "-0.005", "0.0", "-0.005")

    result = evaluate_marginal_portfolio_contribution(
        candidate_returns=candidate,
        portfolio_without_candidate_returns=without,
        portfolio_with_candidate_returns=with_,
    )

    assert result.passed is False
    assert "marginal" in result.details.lower() or "sharpe" in result.details.lower()


def test_marginal_fail_when_cdar_worsens() -> None:
    without = _rets("0.001", "0.001", "0.001", "-0.001", "0.001")
    with_ = _rets("0.001", "0.001", "0.001", "-0.02", "0.001")
    candidate = _rets("0.0", "0.0", "0.0", "-0.04", "0.0")

    result = evaluate_marginal_portfolio_contribution(
        candidate_returns=candidate,
        portfolio_without_candidate_returns=without,
        portfolio_with_candidate_returns=with_,
    )

    assert result.passed is False
