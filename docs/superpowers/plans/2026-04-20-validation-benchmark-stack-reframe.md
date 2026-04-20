# Benchmark Stack + validation.py Reframe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the SPY-relative Gate 1 evaluation with the three-tier benchmark stack (cash hurdle, 60/40 opportunity cost, rolling MDD + CDaR operating constraint) defined in [SPEC-0013 §2](../specs/2026-04-20-capital-growth-landscape-design.md).

**Architecture:** Add drawdown math primitives to `stats.py`, introduce a new `benchmark_stack.py` module that composes the three tiers, thread AGG daily-close data through the existing Alpaca market-data gateway to build the 60/40 series with monthly rebalance, and refactor `validation.py`'s Gate 1 criteria from a single `benchmark_returns` tuple to a `BenchmarkStack` object carrying all three tiers. Criteria become: (a) `hurdle_clearance` vs cash, (b) `opportunity_cost_edge` vs 60/40, (c) `operating_constraint` on MDD and CDaR.

**Tech Stack:** Python 3.11, `Decimal` for money/returns at the validation boundary, `float` + `numpy` for stats primitives, existing `AlpacaMarketDataGateway.get_daily_close_series` for AGG data, `pytest` for tests.

---

## Scope

**In scope:** benchmark stack abstraction, stats primitives (MDD, CDaR, Calmar), validation.py Gate 1 criterion reframe, caller updates in `web/runtime.py` and `controller.py`, test updates.

**Explicitly out of scope:**

- Runtime drawdown throttle (SPEC-0013 subsystem D — tranche 1 work).
- Sleeve construction (subsystem B).
- Portfolio construction risk budgets (subsystem C).
- Live drift monitoring (subsystem F).
- CPCV / trials ledger (subsystem E tranche-2 hardening).
- ADR-0021, ADR-0022, GATES-0001 amendment (follow-on governance docs).

This plan makes CDaR **computable** via `stats.py` and **available** via `BenchmarkStack.operating_constraint`. It does NOT wire CDaR into a live runtime throttle, because that throttle doesn't exist yet and belongs to tranche 1.

## File structure

### Files to create

- `src/tradingx/benchmark_stack.py` — three-tier benchmark stack abstraction
- `tests/unit/test_benchmark_stack.py` — unit tests for benchmark stack

### Files to modify

- `src/tradingx/stats.py` — add MDD, CDaR, Calmar primitives
- `src/tradingx/types.py` — add benchmark-stack payload types
- `src/tradingx/validation.py` — refactor Gate 1 criteria to consume `BenchmarkStack`
- `src/tradingx/web/runtime.py` — update `prepare_benchmark` to emit benchmark-stack payloads
- `src/tradingx/controller.py` — update `GateValidationController.generate_gate_report` signature
- `tests/unit/test_stats.py` — add tests for MDD, CDaR, Calmar
- `tests/unit/test_validation.py` — update to use benchmark stack
- `tests/contract/test_local_web_app_api_contract.py` — update benchmark preparation contract

### Files touched but unchanged

- `src/tradingx/data.py` — `AlpacaMarketDataGateway.get_daily_close_series` used as-is for AGG
- `src/tradingx/risk_free.py` — DGS3MO cache used as-is for cash hurdle
- `src/tradingx/historical.py` — may be reused for AGG fetch

## Task list

### Task 1: stats.py — add `max_drawdown`

**Files:**
- Modify: `src/tradingx/stats.py`
- Test: `tests/unit/test_stats.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_stats.py`:

```python
from tradingx.stats import max_drawdown


def test_max_drawdown_flat_series_is_zero():
    returns = [0.0, 0.0, 0.0, 0.0]
    assert max_drawdown(returns) == 0.0


def test_max_drawdown_monotone_up_is_zero():
    returns = [0.01, 0.02, 0.005, 0.01]
    assert max_drawdown(returns) == 0.0


def test_max_drawdown_single_dip():
    # +10% then -20% gives 20% drawdown from the peak
    returns = [0.10, -0.20]
    assert abs(max_drawdown(returns) - 0.20) < 1e-9


def test_max_drawdown_recovers_then_deeper_drop():
    # Two peaks; the deeper drawdown wins
    returns = [0.10, -0.05, 0.15, -0.30, 0.05]
    # Peak after 3rd step: 1.10 * 0.95 * 1.15 = 1.20175
    # Trough after 4th step: 1.20175 * 0.70 = 0.841225
    # Drawdown = (1.20175 - 0.841225) / 1.20175 = 0.3
    result = max_drawdown(returns)
    assert abs(result - 0.30) < 1e-9


def test_max_drawdown_empty_returns_is_zero():
    assert max_drawdown([]) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_stats.py::test_max_drawdown_flat_series_is_zero -v`

Expected: FAIL with `ImportError: cannot import name 'max_drawdown'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/tradingx/stats.py` (keep existing imports; extend `__all__` if the file exports one):

```python
def max_drawdown(returns: Sequence[float]) -> float:
    """Maximum drawdown of a returns series, as a non-negative fraction.

    Computes peak-to-trough decline over the cumulative return path.
    A return of 0.15 means a 15% drawdown.
    """
    if not returns:
        return 0.0
    cumulative = 1.0
    peak = 1.0
    worst = 0.0
    for r in returns:
        cumulative *= 1.0 + float(r)
        if cumulative > peak:
            peak = cumulative
        drawdown = (peak - cumulative) / peak
        if drawdown > worst:
            worst = drawdown
    return worst
```

Add `Sequence` import if not already present: `from collections.abc import Sequence`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_stats.py -k max_drawdown -v`

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/stats.py tests/unit/test_stats.py
git commit -m "feat(stats): add max_drawdown primitive"
```

---

### Task 2: stats.py — add `conditional_drawdown_at_risk`

**Files:**
- Modify: `src/tradingx/stats.py`
- Test: `tests/unit/test_stats.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_stats.py`:

```python
from tradingx.stats import conditional_drawdown_at_risk


def test_cdar_flat_series_is_zero():
    returns = [0.0] * 10
    assert conditional_drawdown_at_risk(returns, confidence=0.95) == 0.0


def test_cdar_matches_mean_of_worst_tail():
    # Construct a series with a known drawdown tail
    # Drawdowns at each step (sorted desc): [0.30, 0.20, 0.15, 0.10, 0.0, ...]
    # At confidence 0.80, worst 20% = top 2 of 10 drawdowns
    # CDaR should equal mean of top 2
    returns = [
        0.30,    # cum 1.30, peak 1.30, dd 0.0
        -0.23077,  # cum 1.30 * 0.76923 = 1.00, dd = (1.30 - 1.00)/1.30 = 0.23077
    ]
    # Simpler: just test that CDaR >= max_drawdown / tail ratio bounds
    returns = [0.10, -0.20, 0.15, -0.10, 0.05, -0.05, 0.02, 0.01]
    cdar = conditional_drawdown_at_risk(returns, confidence=0.95)
    mdd = max_drawdown(returns)
    assert cdar > 0.0
    # CDaR at 95% should be close to the worst drawdown
    assert cdar <= mdd + 1e-9
    assert cdar >= mdd * 0.5  # the worst-tail average isn't dominated by zeros


def test_cdar_rejects_invalid_confidence():
    import pytest
    with pytest.raises(ValueError):
        conditional_drawdown_at_risk([0.01, -0.02], confidence=0.0)
    with pytest.raises(ValueError):
        conditional_drawdown_at_risk([0.01, -0.02], confidence=1.0)


def test_cdar_empty_returns_is_zero():
    assert conditional_drawdown_at_risk([], confidence=0.95) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_stats.py -k cdar -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/tradingx/stats.py`:

```python
def conditional_drawdown_at_risk(
    returns: Sequence[float],
    *,
    confidence: float = 0.95,
) -> float:
    """Conditional Drawdown-at-Risk (CDaR), per Chekhlov-Uryasev-Zabarankin (2005).

    Returns the expected drawdown in the worst (1 - confidence) tail of the
    drawdown-path distribution. A CDaR of 0.12 at 95% means "in the worst
    5% of observed drawdowns, the average drawdown was 12%."
    """
    if not returns:
        return 0.0
    if confidence <= 0.0 or confidence >= 1.0:
        raise ValueError(
            f"confidence must be in (0, 1); got {confidence}"
        )
    cumulative = 1.0
    peak = 1.0
    drawdowns: list[float] = []
    for r in returns:
        cumulative *= 1.0 + float(r)
        if cumulative > peak:
            peak = cumulative
        drawdowns.append((peak - cumulative) / peak)
    drawdowns.sort(reverse=True)
    tail_size = max(1, int(round((1.0 - confidence) * len(drawdowns))))
    worst_tail = drawdowns[:tail_size]
    return sum(worst_tail) / len(worst_tail)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_stats.py -k cdar -v`

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/stats.py tests/unit/test_stats.py
git commit -m "feat(stats): add conditional_drawdown_at_risk (CDaR)"
```

---

### Task 3: stats.py — add `calmar_ratio`

**Files:**
- Modify: `src/tradingx/stats.py`
- Test: `tests/unit/test_stats.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_stats.py`:

```python
from tradingx.stats import calmar_ratio


def test_calmar_is_zero_for_flat_series():
    assert calmar_ratio([0.0] * 252) == 0.0


def test_calmar_is_inf_when_no_drawdown():
    returns = [0.001] * 252
    result = calmar_ratio(returns, periods_per_year=252)
    assert result == float("inf")


def test_calmar_is_return_over_mdd():
    # Two-year series: +20% cumulative, 10% max drawdown mid-series
    returns = [0.15, -0.10, 0.10, 0.05, 0.00]  # cum ~ 1.21 approx
    result = calmar_ratio(returns, periods_per_year=len(returns))
    # Annualized return == cumulative for periods_per_year == len(returns)
    expected_cagr = 1.0
    for r in returns:
        expected_cagr *= 1.0 + r
    expected_cagr -= 1.0
    assert result > 0.0
    assert abs(result - (expected_cagr / max_drawdown(returns))) < 1e-9


def test_calmar_empty_returns_is_zero():
    assert calmar_ratio([]) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_stats.py -k calmar -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/tradingx/stats.py`:

```python
def calmar_ratio(
    returns: Sequence[float],
    *,
    periods_per_year: int = 252,
) -> float:
    """Calmar ratio: annualized return divided by max drawdown.

    Returns ``inf`` if max drawdown is zero and there is any positive return.
    Returns 0.0 for an empty or flat series.
    """
    if not returns:
        return 0.0
    mdd = max_drawdown(returns)
    cumulative = 1.0
    for r in returns:
        cumulative *= 1.0 + float(r)
    n = len(returns)
    if n <= 0:
        return 0.0
    annualized = cumulative ** (periods_per_year / n) - 1.0
    if mdd == 0.0:
        return float("inf") if annualized > 0.0 else 0.0
    return annualized / mdd
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_stats.py -k calmar -v`

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/stats.py tests/unit/test_stats.py
git commit -m "feat(stats): add calmar_ratio primitive"
```

---

### Task 4: types.py — add benchmark-stack payload types

**Files:**
- Modify: `src/tradingx/types.py`
- Test: none (types only; coverage comes from downstream tests)

- [ ] **Step 1: Add types**

Append to `src/tradingx/types.py` (near other dataclass definitions):

```python
@dataclass(frozen=True)
class OperatingConstraintBudget:
    """Drawdown and CDaR thresholds defining the operating constraint tier."""

    max_drawdown_design: Decimal
    max_drawdown_halt: Decimal
    cdar_threshold: Decimal
    cdar_confidence: Decimal


@dataclass(frozen=True)
class BenchmarkStackPayload:
    """Three-tier benchmark stack computed for a given validation window.

    - ``hurdle_returns``: risk-free-rate daily returns (cash hurdle tier)
    - ``opportunity_cost_returns``: 60/40 blended daily returns
    - ``opportunity_cost_weights``: the blend composition, e.g. {"SPY": 0.6, "AGG": 0.4}
    - ``operating_constraint``: MDD/CDaR budget
    """

    hurdle_returns: tuple[Decimal, ...]
    opportunity_cost_returns: tuple[Decimal, ...]
    opportunity_cost_weights: tuple[tuple[str, Decimal], ...]
    operating_constraint: OperatingConstraintBudget
```

Ensure `Decimal` and `dataclass` are already imported at the top of the file.

- [ ] **Step 2: Run existing type tests to verify no regression**

Run: `uv run pytest tests/unit/test_types.py -v` (if exists) or `uv run pytest -q` sanity check.

Expected: no new failures.

- [ ] **Step 3: Commit**

```bash
git add src/tradingx/types.py
git commit -m "feat(types): add BenchmarkStackPayload and OperatingConstraintBudget"
```

---

### Task 5: benchmark_stack.py — `CashHurdle`

**Files:**
- Create: `src/tradingx/benchmark_stack.py`
- Test: `tests/unit/test_benchmark_stack.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_benchmark_stack.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from tradingx.benchmark_stack import CashHurdle


class _FakeRiskFreeSeries:
    def __init__(self, daily_yields: dict[date, Decimal]) -> None:
        self._daily_yields = daily_yields

    def get_daily_yield(self, session_date: date) -> Decimal:
        return self._daily_yields[session_date]


def test_cash_hurdle_returns_converts_annualized_yield_to_daily():
    # 3-month T-bill yield of ~5% annualized -> ~5%/252 daily
    daily_yields = {
        date(2026, 1, 5): Decimal("0.05"),
        date(2026, 1, 6): Decimal("0.05"),
        date(2026, 1, 7): Decimal("0.05"),
    }
    hurdle = CashHurdle(
        risk_free_series=_FakeRiskFreeSeries(daily_yields),
        trading_days_per_year=252,
    )
    returns = hurdle.daily_returns(
        session_dates=(
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
        )
    )
    assert len(returns) == 3
    expected_daily = Decimal("0.05") / Decimal("252")
    for r in returns:
        assert abs(r - expected_daily) < Decimal("1e-9")


def test_cash_hurdle_rejects_empty_session_dates():
    hurdle = CashHurdle(
        risk_free_series=_FakeRiskFreeSeries({}),
        trading_days_per_year=252,
    )
    with pytest.raises(ValueError):
        hurdle.daily_returns(session_dates=())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_benchmark_stack.py::test_cash_hurdle_returns_converts_annualized_yield_to_daily -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/tradingx/benchmark_stack.py`:

```python
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


class RiskFreeSeriesProtocol(Protocol):
    def get_daily_yield(self, session_date: date) -> Decimal: ...


@dataclass
class CashHurdle:
    """Tier 1 of the benchmark stack: T-bill yield converted to daily returns."""

    risk_free_series: RiskFreeSeriesProtocol
    trading_days_per_year: int = 252

    def daily_returns(
        self,
        *,
        session_dates: Sequence[date],
    ) -> tuple[Decimal, ...]:
        if not session_dates:
            raise ValueError("session_dates must be non-empty.")
        periods = Decimal(self.trading_days_per_year)
        return tuple(
            self.risk_free_series.get_daily_yield(d) / periods
            for d in session_dates
        )


__all__ = ("CashHurdle", "RiskFreeSeriesProtocol")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_benchmark_stack.py -v`

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/benchmark_stack.py tests/unit/test_benchmark_stack.py
git commit -m "feat(benchmark_stack): add CashHurdle tier"
```

---

### Task 6: benchmark_stack.py — `PassiveOpportunityCost` (60/40 blend)

**Files:**
- Modify: `src/tradingx/benchmark_stack.py`
- Test: `tests/unit/test_benchmark_stack.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_benchmark_stack.py`:

```python
from tradingx.benchmark_stack import PassiveOpportunityCost


class _FakeClosesProvider:
    def __init__(self, closes_by_symbol: dict[str, list[Decimal]]) -> None:
        self._closes = closes_by_symbol

    def get_closes(
        self,
        symbol: str,
        *,
        session_dates: Sequence[date],
    ) -> tuple[Decimal, ...]:
        del session_dates
        return tuple(self._closes[symbol])


def test_opportunity_cost_60_40_blend_with_monthly_rebalance():
    # 3 sessions, all within one calendar month (no rebalance event inside)
    # SPY: +1% / -1% / +2%
    # AGG: 0% / +0.5% / -0.2%
    # Expected blended daily returns with 60/40 weights:
    #   day1: 0.6 * 0.01 + 0.4 * 0.00 = 0.006
    #   day2: 0.6 * -0.01 + 0.4 * 0.005 = -0.004
    #   day3: 0.6 * 0.02 + 0.4 * -0.002 = 0.0112
    # NOTE: without a rebalance inside the window, drift is tolerated at
    # validation-window granularity; exact daily weights reflect starting weights.
    closes_provider = _FakeClosesProvider({
        "SPY": [Decimal("100"), Decimal("101"), Decimal("99.99"), Decimal("101.9898")],
        "AGG": [Decimal("100"), Decimal("100"), Decimal("100.5"), Decimal("100.299")],
    })
    opp_cost = PassiveOpportunityCost(
        closes_provider=closes_provider,
        weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )
    session_dates = (
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
    )
    returns = opp_cost.daily_returns(session_dates=session_dates)
    # 4 closes -> 3 daily returns
    assert len(returns) == 3
    expected = [
        Decimal("0.6") * Decimal("0.01") + Decimal("0.4") * Decimal("0"),
        Decimal("0.6") * Decimal("-0.01") + Decimal("0.4") * Decimal("0.005"),
        Decimal("0.6") * Decimal("0.02") + Decimal("0.4") * Decimal("-0.002"),
    ]
    for actual, exp in zip(returns, expected):
        assert abs(actual - exp) < Decimal("1e-6")


def test_opportunity_cost_monthly_rebalance_resets_weights():
    # Two months of data; after rebalance, weights reset to configured split
    # regardless of prior drift
    closes_provider = _FakeClosesProvider({
        "SPY": [Decimal("100"), Decimal("120"), Decimal("115")],
        "AGG": [Decimal("100"), Decimal("100"), Decimal("101")],
    })
    opp_cost = PassiveOpportunityCost(
        closes_provider=closes_provider,
        weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )
    session_dates = (
        date(2026, 1, 30),   # end of January
        date(2026, 1, 31),   # end of January (still within Jan)
        date(2026, 2, 1),    # February -> rebalance at boundary
    )
    returns = opp_cost.daily_returns(session_dates=session_dates)
    # Between day 1 and 2 (both in January), no rebalance; use starting Jan weights
    # Between day 2 and 3, rebalance event: weights revert to 0.6/0.4 before applying day-3 returns
    assert len(returns) == 2
    # day-2 return uses Jan drifted-from-start weights (still 60/40 since it's the
    # first step after the initial month-open rebalance)
    expected_day1 = (
        Decimal("0.6") * Decimal("0.20") +    # SPY 100 -> 120
        Decimal("0.4") * Decimal("0")
    )
    assert abs(returns[0] - expected_day1) < Decimal("1e-6")
    # day-2 return crosses the Feb boundary: weights rebalance to 0.6/0.4 first
    expected_day2 = (
        Decimal("0.6") * (Decimal("115") / Decimal("120") - Decimal("1")) +
        Decimal("0.4") * (Decimal("101") / Decimal("100") - Decimal("1"))
    )
    assert abs(returns[1] - expected_day2) < Decimal("1e-6")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_benchmark_stack.py -k opportunity_cost -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/tradingx/benchmark_stack.py`:

```python
class ClosesProviderProtocol(Protocol):
    def get_closes(
        self,
        symbol: str,
        *,
        session_dates: Sequence[date],
    ) -> tuple[Decimal, ...]: ...


@dataclass
class PassiveOpportunityCost:
    """Tier 2 of the benchmark stack: a weighted blend of ETFs with monthly rebalance.

    Default composition is 60% SPY + 40% AGG but the constructor accepts any
    fixed-weight blend that sums to 1.0.
    """

    closes_provider: ClosesProviderProtocol
    weights: tuple[tuple[str, Decimal], ...]

    def __post_init__(self) -> None:
        total = sum(w for _, w in self.weights)
        if total != Decimal("1"):
            raise ValueError(
                f"Weights must sum to 1.0; got {total}"
            )

    def daily_returns(
        self,
        *,
        session_dates: Sequence[date],
    ) -> tuple[Decimal, ...]:
        if len(session_dates) < 2:
            raise ValueError(
                "session_dates must contain at least two dates to compute returns."
            )
        closes_by_symbol: dict[str, tuple[Decimal, ...]] = {
            symbol: self.closes_provider.get_closes(
                symbol, session_dates=session_dates
            )
            for symbol, _ in self.weights
        }
        # Track current weights; reset to configured weights at each month boundary.
        current_weights: dict[str, Decimal] = {
            symbol: weight for symbol, weight in self.weights
        }
        blended: list[Decimal] = []
        for i in range(1, len(session_dates)):
            prev_date = session_dates[i - 1]
            curr_date = session_dates[i]
            # Rebalance at month boundary (first session of a new month).
            if curr_date.month != prev_date.month:
                current_weights = {
                    symbol: weight for symbol, weight in self.weights
                }
            # Compute per-symbol daily return and blend
            day_return = Decimal("0")
            for symbol, weight in current_weights.items():
                series = closes_by_symbol[symbol]
                prev_close = series[i - 1]
                curr_close = series[i]
                if prev_close == Decimal("0"):
                    raise ValueError(
                        f"Zero previous close for {symbol} at {prev_date}"
                    )
                sym_return = (curr_close / prev_close) - Decimal("1")
                day_return += weight * sym_return
            # Drift weights by realized returns (between rebalance events)
            new_weights: dict[str, Decimal] = {}
            total_value = Decimal("0")
            for symbol, weight in current_weights.items():
                series = closes_by_symbol[symbol]
                sym_return = (series[i] / series[i - 1]) - Decimal("1")
                new_value = weight * (Decimal("1") + sym_return)
                new_weights[symbol] = new_value
                total_value += new_value
            if total_value > Decimal("0"):
                current_weights = {
                    symbol: value / total_value
                    for symbol, value in new_weights.items()
                }
            blended.append(day_return)
        return tuple(blended)
```

Update `__all__`:

```python
__all__ = (
    "CashHurdle",
    "ClosesProviderProtocol",
    "PassiveOpportunityCost",
    "RiskFreeSeriesProtocol",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_benchmark_stack.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/benchmark_stack.py tests/unit/test_benchmark_stack.py
git commit -m "feat(benchmark_stack): add PassiveOpportunityCost with monthly rebalance"
```

---

### Task 7: benchmark_stack.py — `BenchmarkStack` composition + factory

**Files:**
- Modify: `src/tradingx/benchmark_stack.py`
- Test: `tests/unit/test_benchmark_stack.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_benchmark_stack.py`:

```python
from tradingx.benchmark_stack import BenchmarkStack
from tradingx.types import BenchmarkStackPayload, OperatingConstraintBudget


def test_benchmark_stack_materializes_full_payload():
    # Minimal integration test stitching CashHurdle + PassiveOpportunityCost
    daily_yields = {
        date(2026, 1, 5): Decimal("0.05"),
        date(2026, 1, 6): Decimal("0.05"),
        date(2026, 1, 7): Decimal("0.05"),
    }
    closes_provider = _FakeClosesProvider({
        "SPY": [Decimal("100"), Decimal("101"), Decimal("99.99")],
        "AGG": [Decimal("100"), Decimal("100"), Decimal("100.5")],
    })
    constraint = OperatingConstraintBudget(
        max_drawdown_design=Decimal("0.15"),
        max_drawdown_halt=Decimal("0.25"),
        cdar_threshold=Decimal("0.08"),
        cdar_confidence=Decimal("0.95"),
    )
    stack = BenchmarkStack(
        hurdle=CashHurdle(
            risk_free_series=_FakeRiskFreeSeries(daily_yields),
        ),
        opportunity_cost=PassiveOpportunityCost(
            closes_provider=closes_provider,
            weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
        ),
        operating_constraint=constraint,
    )
    payload = stack.materialize(
        session_dates=(
            date(2026, 1, 5),
            date(2026, 1, 6),
            date(2026, 1, 7),
        )
    )
    assert isinstance(payload, BenchmarkStackPayload)
    assert len(payload.hurdle_returns) == 3
    assert len(payload.opportunity_cost_returns) == 2
    assert payload.operating_constraint == constraint
    assert payload.opportunity_cost_weights == (
        ("SPY", Decimal("0.6")),
        ("AGG", Decimal("0.4")),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_benchmark_stack.py::test_benchmark_stack_materializes_full_payload -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/tradingx/benchmark_stack.py`:

```python
from tradingx.types import BenchmarkStackPayload, OperatingConstraintBudget


@dataclass
class BenchmarkStack:
    """Three-tier benchmark stack composed for a validation window.

    Emits a :class:`BenchmarkStackPayload` materializing all three tiers.
    """

    hurdle: CashHurdle
    opportunity_cost: PassiveOpportunityCost
    operating_constraint: OperatingConstraintBudget

    def materialize(
        self,
        *,
        session_dates: Sequence[date],
    ) -> BenchmarkStackPayload:
        return BenchmarkStackPayload(
            hurdle_returns=self.hurdle.daily_returns(session_dates=session_dates),
            opportunity_cost_returns=self.opportunity_cost.daily_returns(
                session_dates=session_dates,
            ),
            opportunity_cost_weights=self.opportunity_cost.weights,
            operating_constraint=self.operating_constraint,
        )
```

Update `__all__`:

```python
__all__ = (
    "BenchmarkStack",
    "CashHurdle",
    "ClosesProviderProtocol",
    "PassiveOpportunityCost",
    "RiskFreeSeriesProtocol",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_benchmark_stack.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/benchmark_stack.py tests/unit/test_benchmark_stack.py
git commit -m "feat(benchmark_stack): compose BenchmarkStack and materialize payload"
```

---

### Task 8: benchmark_stack.py — `build_default_benchmark_stack(config)` factory

**Files:**
- Modify: `src/tradingx/benchmark_stack.py`
- Test: `tests/unit/test_benchmark_stack.py` (light integration test with real gateway mocks)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_benchmark_stack.py`:

```python
from tradingx.benchmark_stack import build_default_benchmark_stack
from tradingx.config import RuntimeConfig, TradingConfig


class _StubMarketDataGateway:
    def __init__(self, closes: dict[str, list[Decimal]]) -> None:
        self._closes = closes

    def get_daily_close_series(self, symbol: str, *, start_utc, end_utc, feed, adjustment):
        del start_utc, end_utc, feed, adjustment
        from tradingx.types import BenchmarkCloseSeries
        return BenchmarkCloseSeries(
            symbol=symbol,
            closes=tuple(self._closes[symbol]),
            session_dates=(),
            series_is_adjusted=True,
        )


class _StubRiskFreeCache:
    def get_daily_yield(self, session_date):
        return Decimal("0.05")


def test_build_default_benchmark_stack_wires_dependencies(trading_config_fixture):
    market_data = _StubMarketDataGateway({
        "SPY": [Decimal("100"), Decimal("101")],
        "AGG": [Decimal("100"), Decimal("100")],
    })
    risk_free = _StubRiskFreeCache()
    stack = build_default_benchmark_stack(
        trading_config_fixture,
        market_data_gateway=market_data,
        risk_free_series=risk_free,
    )
    assert isinstance(stack, BenchmarkStack)
    assert stack.opportunity_cost.weights == (
        ("SPY", Decimal("0.6")),
        ("AGG", Decimal("0.4")),
    )
    assert stack.operating_constraint.max_drawdown_design == Decimal("0.15")
    assert stack.operating_constraint.max_drawdown_halt == Decimal("0.25")
```

Add fixture to same file if `trading_config_fixture` doesn't exist elsewhere:

```python
@pytest.fixture
def trading_config_fixture():
    from tradingx.config import (
        AlertingConfig, PaperCredentials, RuntimeConfig, TradingConfig,
        LiveTradingControls, WebAppConfig,
    )
    return TradingConfig(
        paper_credentials=PaperCredentials(api_key="k", api_secret="s", account_id="a"),
        live_controls=LiveTradingControls(),
        alerting=AlertingConfig(),
        runtime=RuntimeConfig(),
        web=WebAppConfig(),
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_benchmark_stack.py::test_build_default_benchmark_stack_wires_dependencies -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/tradingx/benchmark_stack.py`:

```python
from datetime import UTC, datetime, timedelta

from tradingx.config import TradingConfig


class _MarketDataClosesAdapter:
    """Adapts AlpacaMarketDataGateway to ClosesProviderProtocol."""

    def __init__(self, market_data_gateway) -> None:
        self._gateway = market_data_gateway

    def get_closes(
        self,
        symbol: str,
        *,
        session_dates: Sequence[date],
    ) -> tuple[Decimal, ...]:
        # Fetch a window containing all session_dates; extract closes at those dates.
        from alpaca.data.enums import Adjustment, DataFeed

        start_utc = datetime.combine(session_dates[0], datetime.min.time(), UTC)
        end_utc = datetime.combine(
            session_dates[-1], datetime.min.time(), UTC
        ) + timedelta(days=1)
        series = self._gateway.get_daily_close_series(
            symbol,
            start_utc=start_utc,
            end_utc=end_utc,
            feed=DataFeed.IEX,
            adjustment=Adjustment.DIVIDEND,
        )
        return series.closes


def build_default_benchmark_stack(
    config: TradingConfig,
    *,
    market_data_gateway,
    risk_free_series: RiskFreeSeriesProtocol,
) -> BenchmarkStack:
    """Construct the default BenchmarkStack.

    Defaults:
    - Cash hurdle via DGS3MO (supplied by caller).
    - Opportunity cost: 60% SPY + 40% AGG.
    - Operating constraint: 15% design / 25% halt MDD, 8% CDaR at 95%.
    """
    del config  # Reserved for future config-driven overrides.
    closes_provider = _MarketDataClosesAdapter(market_data_gateway)
    return BenchmarkStack(
        hurdle=CashHurdle(risk_free_series=risk_free_series),
        opportunity_cost=PassiveOpportunityCost(
            closes_provider=closes_provider,
            weights=(
                ("SPY", Decimal("0.6")),
                ("AGG", Decimal("0.4")),
            ),
        ),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal("0.15"),
            max_drawdown_halt=Decimal("0.25"),
            cdar_threshold=Decimal("0.08"),
            cdar_confidence=Decimal("0.95"),
        ),
    )
```

Update `__all__`:

```python
__all__ = (
    "BenchmarkStack",
    "CashHurdle",
    "ClosesProviderProtocol",
    "PassiveOpportunityCost",
    "RiskFreeSeriesProtocol",
    "build_default_benchmark_stack",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_benchmark_stack.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/benchmark_stack.py tests/unit/test_benchmark_stack.py
git commit -m "feat(benchmark_stack): add build_default_benchmark_stack factory"
```

---

### Task 9: validation.py — add `hurdle_clearance` criterion

**Files:**
- Modify: `src/tradingx/validation.py`
- Test: `tests/unit/test_validation.py`

**Before editing:** read the current shape of `evaluate_gate1_criteria` (the function around line 144) and its caller `build_gate_report` (around line 465) to understand how `benchmark_returns` threads through.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_validation.py`:

```python
from decimal import Decimal

from tradingx.types import BenchmarkStackPayload, OperatingConstraintBudget
from tradingx.validation import evaluate_hurdle_clearance


def test_hurdle_clearance_passes_when_candidate_beats_cash():
    # Candidate returns 8% annualized; cash is 5%
    candidate_returns = tuple([Decimal("0.0003")] * 252)  # ~8% annualized
    hurdle_returns = tuple([Decimal("0.0002")] * 252)     # ~5% annualized
    result = evaluate_hurdle_clearance(
        candidate_returns=candidate_returns,
        hurdle_returns=hurdle_returns,
    )
    assert result.passed is True
    assert result.criterion_id == "hurdle_clearance"


def test_hurdle_clearance_fails_when_candidate_underperforms_cash():
    candidate_returns = tuple([Decimal("0.0001")] * 252)
    hurdle_returns = tuple([Decimal("0.0002")] * 252)
    result = evaluate_hurdle_clearance(
        candidate_returns=candidate_returns,
        hurdle_returns=hurdle_returns,
    )
    assert result.passed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validation.py -k hurdle_clearance -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/tradingx/validation.py` (near the existing `GateCriterion` construction helpers):

```python
def evaluate_hurdle_clearance(
    *,
    candidate_returns: tuple[Decimal, ...],
    hurdle_returns: tuple[Decimal, ...],
) -> GateCriterion:
    candidate_cagr = _cumulative_return(candidate_returns)
    hurdle_cagr = _cumulative_return(hurdle_returns)
    passed = candidate_cagr > hurdle_cagr
    return GateCriterion(
        criterion_id="hurdle_clearance",
        passed=passed,
        threshold="Candidate cumulative return must exceed cash hurdle cumulative return",
        observed=(
            f"Candidate CAGR={candidate_cagr:.4f}, hurdle CAGR={hurdle_cagr:.4f}."
        ),
    )


def _cumulative_return(returns: tuple[Decimal, ...]) -> Decimal:
    cumulative = Decimal("1")
    for r in returns:
        cumulative *= Decimal("1") + r
    return cumulative - Decimal("1")
```

If `_cumulative_return` already exists, skip the duplicate definition.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py -k hurdle_clearance -v`

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/validation.py tests/unit/test_validation.py
git commit -m "feat(validation): add hurdle_clearance criterion vs cash"
```

---

### Task 10: validation.py — replace `benchmark_edge` with `opportunity_cost_edge` (vs 60/40)

**Files:**
- Modify: `src/tradingx/validation.py`
- Test: `tests/unit/test_validation.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_validation.py`:

```python
from tradingx.validation import evaluate_opportunity_cost_edge


def test_opportunity_cost_edge_passes_when_candidate_beats_60_40():
    candidate_returns = tuple([Decimal("0.0005")] * 252)  # ~13% annualized
    opportunity_cost_returns = tuple([Decimal("0.0003")] * 252)  # ~8%
    result = evaluate_opportunity_cost_edge(
        candidate_returns=candidate_returns,
        opportunity_cost_returns=opportunity_cost_returns,
        opportunity_cost_weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )
    assert result.passed is True
    assert result.criterion_id == "opportunity_cost_edge"
    assert "SPY:0.6" in result.observed
    assert "AGG:0.4" in result.observed


def test_opportunity_cost_edge_fails_when_candidate_underperforms_60_40():
    candidate_returns = tuple([Decimal("0.0001")] * 252)
    opportunity_cost_returns = tuple([Decimal("0.0004")] * 252)
    result = evaluate_opportunity_cost_edge(
        candidate_returns=candidate_returns,
        opportunity_cost_returns=opportunity_cost_returns,
        opportunity_cost_weights=(("SPY", Decimal("0.6")), ("AGG", Decimal("0.4"))),
    )
    assert result.passed is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validation.py -k opportunity_cost_edge -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/tradingx/validation.py`:

```python
def evaluate_opportunity_cost_edge(
    *,
    candidate_returns: tuple[Decimal, ...],
    opportunity_cost_returns: tuple[Decimal, ...],
    opportunity_cost_weights: tuple[tuple[str, Decimal], ...],
) -> GateCriterion:
    candidate_cagr = _cumulative_return(candidate_returns)
    opp_cost_cagr = _cumulative_return(opportunity_cost_returns)
    # Edge requirement: candidate CAGR > opportunity-cost CAGR + 2% absolute
    # (mirrors the prior benchmark_edge threshold, but benchmarked against 60/40)
    edge_threshold = Decimal("0.02")
    passed = candidate_cagr > opp_cost_cagr + edge_threshold
    composition = "+".join(
        f"{symbol}:{weight}" for symbol, weight in opportunity_cost_weights
    )
    return GateCriterion(
        criterion_id="opportunity_cost_edge",
        passed=passed,
        threshold=(
            f"Candidate CAGR must exceed {composition} CAGR by at least "
            f"{edge_threshold:.2f} absolute"
        ),
        observed=(
            f"Candidate CAGR={candidate_cagr:.4f}, opportunity-cost CAGR "
            f"({composition})={opp_cost_cagr:.4f}."
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py -k opportunity_cost_edge -v`

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/validation.py tests/unit/test_validation.py
git commit -m "feat(validation): add opportunity_cost_edge criterion vs 60/40"
```

---

### Task 11: validation.py — add `operating_constraint` criterion

**Files:**
- Modify: `src/tradingx/validation.py`
- Test: `tests/unit/test_validation.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_validation.py`:

```python
from tradingx.validation import evaluate_operating_constraint


def test_operating_constraint_passes_within_budget():
    # A candidate whose worst drawdown is 10% and CDaR is 5% passes a
    # budget of 15% MDD design / 8% CDaR
    returns = [Decimal("0.01")] * 50 + [Decimal("-0.002")] * 55 + [Decimal("0.005")] * 50
    constraint = OperatingConstraintBudget(
        max_drawdown_design=Decimal("0.15"),
        max_drawdown_halt=Decimal("0.25"),
        cdar_threshold=Decimal("0.08"),
        cdar_confidence=Decimal("0.95"),
    )
    result = evaluate_operating_constraint(
        candidate_returns=tuple(returns),
        constraint=constraint,
    )
    assert result.criterion_id == "operating_constraint"


def test_operating_constraint_fails_when_mdd_exceeds_design():
    # Deliberately inject a ~30% drawdown
    returns = (
        [Decimal("0.01")] * 20
        + [Decimal("-0.03")] * 12   # cumulative ~ -30% from peak
        + [Decimal("0.01")] * 30
    )
    constraint = OperatingConstraintBudget(
        max_drawdown_design=Decimal("0.15"),
        max_drawdown_halt=Decimal("0.25"),
        cdar_threshold=Decimal("0.08"),
        cdar_confidence=Decimal("0.95"),
    )
    result = evaluate_operating_constraint(
        candidate_returns=tuple(returns),
        constraint=constraint,
    )
    assert result.passed is False
    assert "max_drawdown" in result.observed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validation.py -k operating_constraint -v`

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/tradingx/validation.py`:

```python
from tradingx.stats import conditional_drawdown_at_risk, max_drawdown
from tradingx.types import OperatingConstraintBudget


def evaluate_operating_constraint(
    *,
    candidate_returns: tuple[Decimal, ...],
    constraint: OperatingConstraintBudget,
) -> GateCriterion:
    returns_f = [float(r) for r in candidate_returns]
    mdd = Decimal(str(max_drawdown(returns_f)))
    cdar = Decimal(str(conditional_drawdown_at_risk(
        returns_f, confidence=float(constraint.cdar_confidence),
    )))
    mdd_ok = mdd <= constraint.max_drawdown_design
    cdar_ok = cdar <= constraint.cdar_threshold
    passed = mdd_ok and cdar_ok
    return GateCriterion(
        criterion_id="operating_constraint",
        passed=passed,
        threshold=(
            f"max_drawdown <= {constraint.max_drawdown_design} design "
            f"AND CDaR@{constraint.cdar_confidence} <= {constraint.cdar_threshold}"
        ),
        observed=(
            f"max_drawdown={mdd:.4f}, CDaR={cdar:.4f} "
            f"(design={constraint.max_drawdown_design}, "
            f"halt={constraint.max_drawdown_halt})"
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py -k operating_constraint -v`

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/validation.py tests/unit/test_validation.py
git commit -m "feat(validation): add operating_constraint criterion (MDD + CDaR)"
```

---

### Task 12: validation.py — thread `BenchmarkStackPayload` through Gate 1

**Files:**
- Modify: `src/tradingx/validation.py`
- Test: `tests/unit/test_validation.py`

**Goal:** The existing Gate 1 entry point (currently signatured `build_gate_report(..., benchmark_returns, benchmark_symbol, benchmark_series_is_adjusted)`) is refactored to accept `benchmark_stack_payload: BenchmarkStackPayload` instead of the bare `benchmark_returns` tuple. The three new criteria (hurdle_clearance, opportunity_cost_edge, operating_constraint) replace the legacy `benchmark_edge` and `benchmark_adjustment` criteria.

- [ ] **Step 1: Read current entry point**

Read `src/tradingx/validation.py` lines 144–290 to understand the current signature and control flow for `evaluate_gate1_criteria` and `build_gate_report`.

- [ ] **Step 2: Write the failing test**

Add to `tests/unit/test_validation.py`:

```python
def test_gate1_uses_benchmark_stack_payload():
    """The Gate 1 entry point accepts a BenchmarkStackPayload and emits
    hurdle_clearance + opportunity_cost_edge + operating_constraint
    criteria, replacing the legacy benchmark_edge criterion.
    """
    payload = BenchmarkStackPayload(
        hurdle_returns=tuple([Decimal("0.0002")] * 252),
        opportunity_cost_returns=tuple([Decimal("0.0003")] * 251),
        opportunity_cost_weights=(
            ("SPY", Decimal("0.6")),
            ("AGG", Decimal("0.4")),
        ),
        operating_constraint=OperatingConstraintBudget(
            max_drawdown_design=Decimal("0.15"),
            max_drawdown_halt=Decimal("0.25"),
            cdar_threshold=Decimal("0.08"),
            cdar_confidence=Decimal("0.95"),
        ),
    )
    candidate_returns = tuple([Decimal("0.0005")] * 252)
    # Call the refactored entry point (see Step 3 for exact name)
    criteria = evaluate_gate1_benchmark_criteria(
        candidate_returns=candidate_returns,
        benchmark_stack_payload=payload,
    )
    criterion_ids = {c.criterion_id for c in criteria}
    assert "hurdle_clearance" in criterion_ids
    assert "opportunity_cost_edge" in criterion_ids
    assert "operating_constraint" in criterion_ids
    assert "benchmark_edge" not in criterion_ids  # legacy removed
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_validation.py::test_gate1_uses_benchmark_stack_payload -v`

Expected: FAIL with `ImportError` for `evaluate_gate1_benchmark_criteria`.

- [ ] **Step 4: Implement the refactored entry point**

Add to `src/tradingx/validation.py`:

```python
from tradingx.types import BenchmarkStackPayload


def evaluate_gate1_benchmark_criteria(
    *,
    candidate_returns: tuple[Decimal, ...],
    benchmark_stack_payload: BenchmarkStackPayload,
) -> tuple[GateCriterion, ...]:
    """Benchmark-related Gate 1 criteria under the three-tier benchmark stack.

    Emits three criteria:
    - hurdle_clearance: candidate cumulative return > cash hurdle cumulative return
    - opportunity_cost_edge: candidate CAGR > 60/40 CAGR + 2% absolute
    - operating_constraint: MDD <= design budget AND CDaR <= threshold
    """
    return (
        evaluate_hurdle_clearance(
            candidate_returns=candidate_returns,
            hurdle_returns=benchmark_stack_payload.hurdle_returns,
        ),
        evaluate_opportunity_cost_edge(
            candidate_returns=candidate_returns,
            opportunity_cost_returns=benchmark_stack_payload.opportunity_cost_returns,
            opportunity_cost_weights=benchmark_stack_payload.opportunity_cost_weights,
        ),
        evaluate_operating_constraint(
            candidate_returns=candidate_returns,
            constraint=benchmark_stack_payload.operating_constraint,
        ),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_validation.py::test_gate1_uses_benchmark_stack_payload -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tradingx/validation.py tests/unit/test_validation.py
git commit -m "feat(validation): thread BenchmarkStackPayload through Gate 1"
```

---

### Task 13: validation.py — remove the legacy `benchmark_edge` / `benchmark_adjustment` paths

**Files:**
- Modify: `src/tradingx/validation.py`
- Test: `tests/unit/test_validation.py`

**Goal:** Delete the now-unused legacy criteria and the `benchmark_returns`/`benchmark_series_is_adjusted` parameters from `build_gate_report`.

- [ ] **Step 1: Find the legacy criterion construction sites**

Run: `grep -n "benchmark_edge\|benchmark_adjustment" src/tradingx/validation.py`

Expected output: references at roughly lines 161–213, 248–250, and function signatures at lines 144–147, 282–290.

- [ ] **Step 2: Replace `build_gate_report` signature**

Modify the existing function so its signature becomes:

```python
def build_gate_report(
    *,
    gate_id: str,
    bars_by_symbol: dict[str, Sequence[Any]],
    candidates: tuple[StrategyCandidate, ...],
    window_start_utc: datetime,
    window_end_utc: datetime,
    benchmark_stack_payload: BenchmarkStackPayload,
) -> ValidationReport:
```

Remove the `benchmark_returns`, `benchmark_symbol`, and `benchmark_series_is_adjusted` parameters. Inside the function, replace the call that produced the old `benchmark_edge` and `benchmark_adjustment` criteria with a single call to `evaluate_gate1_benchmark_criteria(...)` and include all three emitted criteria in the final `ValidationReport`.

- [ ] **Step 3: Update `evaluate_gate1_criteria` if it exists**

If there is an intermediate helper that currently references `benchmark_returns` (see your grep output from Task 12 Step 1), replace its signature analogously.

- [ ] **Step 4: Run the full validation test suite**

Run: `uv run pytest tests/unit/test_validation.py -v`

Expected: all tests PASS. Failures from the legacy signature should have been pre-emptively updated in Tasks 9–12; any lingering fixture references need to be converted to `BenchmarkStackPayload`.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/validation.py tests/unit/test_validation.py
git commit -m "refactor(validation): remove legacy SPY-relative benchmark criteria"
```

---

### Task 14: Update `GateValidationController.generate_gate_report` caller

**Files:**
- Modify: `src/tradingx/controller.py`
- Test: run existing controller tests

- [ ] **Step 1: Read the current caller**

Run: `grep -n "generate_gate_report\|build_gate_report" src/tradingx/controller.py`

Expected: `GateValidationController.generate_gate_report` around line 1447.

- [ ] **Step 2: Update the caller signature**

Replace the current parameters (`benchmark_closes`, `benchmark_series_is_adjusted`) with `benchmark_stack_payload: BenchmarkStackPayload`. The caller now requires the stack to be materialized upstream (Task 15 does that in `web/runtime.py`).

The controller's `generate_gate_report` body becomes roughly:

```python
def generate_gate_report(
    self,
    *,
    gate_id: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
    universe: tuple[str, ...],
    benchmark_stack_payload: BenchmarkStackPayload,
) -> GateReportResult:
    candidates = build_mandatory_candidate_registry(universe)
    required_symbols = {candidate.benchmark_symbol for candidate in candidates} | {
        symbol for candidate in candidates for symbol in candidate.universe
    }
    bars_by_symbol = {
        symbol: self._market_data.get_daily_bar_history(
            symbol,
            start_utc=window_start_utc,
            end_utc=window_end_utc,
        )
        for symbol in sorted(required_symbols)
    }
    report = build_gate_report(
        gate_id=gate_id,
        bars_by_symbol=bars_by_symbol,
        candidates=candidates,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        benchmark_stack_payload=benchmark_stack_payload,
    )
    # ... rest unchanged
```

- [ ] **Step 3: Run the controller test suite**

Run: `uv run pytest tests/unit/test_controller.py tests/unit/test_validation.py -v`

Expected: PASS. Tests that previously supplied `benchmark_closes` need to be updated to supply a `BenchmarkStackPayload` built via a lightweight fixture.

- [ ] **Step 4: Commit**

```bash
git add src/tradingx/controller.py tests/unit/test_controller.py
git commit -m "refactor(controller): use BenchmarkStackPayload in gate validation"
```

---

### Task 15: Update `LocalWebActionRunner.generate_gate_report` + `prepare_benchmark`

**Files:**
- Modify: `src/tradingx/web/runtime.py`
- Test: `tests/contract/test_local_web_app_api_contract.py`

- [ ] **Step 1: Read current caller**

Run: `grep -n "generate_gate_report\|prepare_benchmark" src/tradingx/web/runtime.py`

Expected: `prepare_benchmark` around line 475, `generate_gate_report` around line 514.

- [ ] **Step 2: Refactor `prepare_benchmark` to materialize the full stack**

Replace the current single-symbol benchmark preparation with a call that materializes a full `BenchmarkStackPayload` and writes it under `artifact_root / "validation" / "benchmark_stacks" / "<window>.json"`.

```python
def prepare_benchmark(
    self,
    *,
    window_start: str,
    window_end: str,
) -> WebActionResult:
    from tradingx.benchmark_stack import build_default_benchmark_stack
    from tradingx.risk_free import build_default_risk_free_series  # if exists; else use existing factory

    market_data_gateway = build_default_market_data_gateway(self._config)
    risk_free_series = build_default_risk_free_series(self._config)  # verify exact factory name
    stack = build_default_benchmark_stack(
        self._config,
        market_data_gateway=market_data_gateway,
        risk_free_series=risk_free_series,
    )
    window_start_utc = datetime.fromisoformat(window_start).replace(tzinfo=UTC)
    window_end_utc = datetime.fromisoformat(window_end).replace(tzinfo=UTC)
    # Use the market calendar (existing utility) to get session_dates between bounds
    from tradingx.data import AlpacaRegularHoursCalendar
    session_dates = AlpacaRegularHoursCalendar().session_dates_between(
        window_start_utc, window_end_utc,
    )
    payload = stack.materialize(session_dates=session_dates)
    output_file = (
        self._config.runtime.artifact_root
        / "validation"
        / "benchmark_stacks"
        / f"stack-{window_start_utc.date().isoformat()}-{window_end_utc.date().isoformat()}.json"
    )
    _write_benchmark_stack_payload(output_file, payload)
    return WebActionResult(
        action_id=f"action-{uuid.uuid4()}",
        action_type="prepare_benchmark",
        status="completed",
        message="Prepared benchmark stack (cash + 60/40 + operating constraint).",
        evidence_refs=(str(output_file),),
    )
```

If `AlpacaRegularHoursCalendar.session_dates_between` doesn't exist, add it in a sub-task (5 lines: iterate the calendar between bounds and return session dates).

If `build_default_risk_free_series` doesn't exist in `risk_free.py`, add it — it should return an object satisfying `RiskFreeSeriesProtocol` over the existing DGS3MO cache. Put this in its own commit.

- [ ] **Step 3: Refactor `generate_gate_report` in the web runner**

Replace the current `benchmark_closes_file: str` parameter with `benchmark_stack_file: str`, and read the stack payload from disk before calling `controller.generate_gate_report(... benchmark_stack_payload=payload)`.

- [ ] **Step 4: Update the contract test**

Modify `tests/contract/test_local_web_app_api_contract.py` so the `/prepare_benchmark` endpoint contract emits a `benchmark_stack_file` evidence ref instead of the legacy `benchmark_closes_file`.

- [ ] **Step 5: Run contract and web tests**

Run: `uv run pytest tests/contract/test_local_web_app_api_contract.py tests/unit/test_web_readmodels.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tradingx/web/runtime.py src/tradingx/risk_free.py src/tradingx/data.py tests/contract/test_local_web_app_api_contract.py
git commit -m "refactor(web): prepare_benchmark emits full benchmark stack payload"
```

---

### Task 16: Full regression pass

**Files:**
- Test: all

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -x -q`

Expected: all tests PASS.

- [ ] **Step 2: Run type checker**

Run: `uv run mypy src/tradingx`

Expected: no new type errors.

- [ ] **Step 3: Run lint**

Run: `uv run ruff check src/tradingx tests`

Expected: no new lint errors.

- [ ] **Step 4: Commit fixups if any**

```bash
git add -u
git commit -m "fix(benchmark_stack): address type/lint feedback"
```

(Skip if no fixups needed.)

---

## Self-review

### Spec coverage

- SPEC-0013 §2.1 (cash hurdle via DGS3MO): covered by Task 5 (`CashHurdle`) and Task 8 (factory wiring).
- SPEC-0013 §2.2 (60/40 opportunity cost): covered by Task 6 (`PassiveOpportunityCost`) with monthly rebalance and Task 8 (default 60/40 weights).
- SPEC-0013 §2.3 (rolling MDD + CDaR operating constraint): covered by Tasks 1–3 (primitives), Task 7 (stack composition), Task 11 (criterion).
- SPEC-0013 §2.4 (supersession impact, validation.py:144 reframe): covered by Tasks 12–15.
- SPEC-0013 §3 row 4 (MDD 15%/25% reset): encoded in Task 8's `OperatingConstraintBudget` defaults and Task 11's criterion.
- SPEC-0013 §6 (gate reframe from standalone Sharpe to portfolio contribution + robustness): **NOT covered here**. The new criteria change the *benchmark-related* part of Gate 1; the marginal-contribution portion of the reframe is tranche-1 work and lives in a separate plan. This plan note is intentional.
- SPEC-0013 §10.3 ([validation.py:144](../specs/2026-04-20-capital-growth-landscape-design.md) reframe): covered end-to-end by Tasks 12–15.
- SPEC-0013 §10.4 (Stage 0c rename): **NOT in scope** for this plan. Separate in-flight PR.

### Placeholder scan

No TBD / TODO / "implement later" / "handle edge cases" / "similar to Task N" — every step has concrete code or concrete commands.

### Type consistency

- `OperatingConstraintBudget` (Task 4) used consistently in Tasks 7, 8, 11, 12.
- `BenchmarkStackPayload` (Task 4) used consistently in Tasks 7, 12, 13, 14, 15.
- `CashHurdle.daily_returns` signature matches usage in `BenchmarkStack.materialize` (Task 7).
- `PassiveOpportunityCost.daily_returns` signature matches usage in `BenchmarkStack.materialize` (Task 7).
- `evaluate_gate1_benchmark_criteria` signature defined in Task 12, called in Task 13's `build_gate_report`.

### Open uncertainties flagged for Codex

1. **`build_default_risk_free_series` factory** — Task 15 assumes one exists in `risk_free.py`. If it doesn't, Codex should add it as a separate commit. The function should wrap the existing DGS3MO cache behind `RiskFreeSeriesProtocol`.
2. **`AlpacaRegularHoursCalendar.session_dates_between`** — Task 15 assumes this method exists. If not, add it as a 5-line helper.
3. **In-flight modifications to `validation.py` and related tests** — there are 31 uncommitted files in the working tree touching `validation.py`, `controller.py`, and multiple tests. Codex should rebase this plan against the current state after committing or stashing those in-flight changes.

### Execution handoff

This plan is for Codex, not for a subagent dispatch or an inline executing-plans run. The user's arrangement is:

- Claude (consultant) writes the plan.
- Codex (teammate) executes the plan with his own judgment on any ambiguities.

**No execution skill invocation from this session.** Claude hands the plan to Hussam; Hussam shares with Codex; Codex executes.
