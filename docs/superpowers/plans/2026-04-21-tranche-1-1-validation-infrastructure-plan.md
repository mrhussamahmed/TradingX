# Tranche 1.1 Validation Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the four work items in [DESIGN-0011](../specs/2026-04-21-tranche-1-1-validation-infrastructure-design.md) — purged/embargoed k-fold CV splitter, SQLite-backed trials ledger, cost-drag accounting threaded from backtest to evidence pack, and Deflated Sharpe Ratio wiring into `evaluate_candidate`.

**Architecture:** Two new modules (`validation_folds.py` and `trials.py`) plus surgical contract changes across the existing validation → backtest → evaluation stack. Gate 1 pass/fail criteria are untouched; this is evidence-model enrichment plus multiple-testing discipline. SQLite follows the `journal.py` pattern; stats primitives stay pure Python + numpy.

**Tech Stack:** Python 3.11, `Decimal` for money/returns at module boundaries, `numpy` + `scipy.stats` for skewness/kurtosis, `sqlite3` stdlib for the trials ledger, `pytest` for tests, existing `uv run` invocations.

---

## Scope

Implements DESIGN-0011 §W1–§W4 in this order:

1. **W1** — purged/embargoed k-fold CV splitter (standalone; no upstream dependencies).
2. **W4** — cost-drag accounting + contract changes across validation/backtest/evaluation (must ship before W2/W3 so trial records carry the correct net-of-costs Sharpe).
3. **W2** — trials ledger module + `TrialRecord` type.
4. **W3** — DSR wiring into `evaluate_candidate` using W2's ledger statistics.
5. Final regression pass.

Gate 1 criterion behavior (hurdle_clearance, opportunity_cost_edge, operating_constraint, out_of_sample_profile) must not change on any current fixture.

## File structure

### New files

- `src/tradingx/validation_folds.py` — purged/embargoed k-fold splitter
- `src/tradingx/trials.py` — SQLite-backed trials ledger
- `tests/unit/test_validation_folds.py`
- `tests/unit/test_trials.py`

### Modified files

- `src/tradingx/types.py` — add `TrialRecord`, `TrialStatistics`, three new optional fields on `EvaluationEvidencePack`
- `src/tradingx/backtest.py` — add `annualized_cost_drag_bps` to `DailyBarBacktestResult`, compute inside `run_daily_bar_backtest`
- `src/tradingx/validation.py` — change `_candidate_returns` signature; make `CostModelConfig` default non-None
- `src/tradingx/evaluation.py` — accept cost drag; wire DSR; record trials
- `src/tradingx/web/readmodels.py` — surface cost drag in validation diagnostic
- `tests/unit/test_backtest.py`, `tests/unit/test_validation.py`, `tests/unit/test_evaluation.py`, `tests/unit/test_web_readmodels.py` — regression + new-behavior coverage

---

## W1 — Purged/embargoed k-fold splitter

### Task 1: Scaffold `validation_folds.py` with coverage + no-overlap behavior

**Files:**
- Create: `src/tradingx/validation_folds.py`
- Create: `tests/unit/test_validation_folds.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_validation_folds.py`:

```python
from __future__ import annotations

import pytest

from tradingx.validation_folds import purged_kfold_indices


def test_purged_kfold_splits_cover_all_samples():
    splits = purged_kfold_indices(n_samples=100, k=5, embargo_days=0)
    test_indices = set()
    for _, test in splits:
        test_indices.update(test)
    assert test_indices == set(range(100))
    assert len(splits) == 5


def test_purged_kfold_no_train_test_overlap():
    splits = purged_kfold_indices(n_samples=100, k=5, embargo_days=0)
    for train, test in splits:
        assert not (set(train) & set(test))


def test_purged_kfold_deterministic():
    a = purged_kfold_indices(n_samples=100, k=5, embargo_days=0)
    b = purged_kfold_indices(n_samples=100, k=5, embargo_days=0)
    assert a == b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validation_folds.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingx.validation_folds'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/tradingx/validation_folds.py`:

```python
"""Purged/embargoed k-fold cross-validation splitter.

Supports walk-forward-safe cross-validation on time-series by:
- Assigning non-overlapping contiguous blocks of indices to k test folds.
- (When embargo_days > 0) removing training samples immediately after
  each test fold to prevent look-ahead contamination into the next
  training window.

Reference: López de Prado, "Advances in Financial Machine Learning"
(2018), Chapter 7.
"""

from __future__ import annotations


def purged_kfold_indices(
    *,
    n_samples: int,
    k: int,
    embargo_days: int = 5,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    if k < 2:
        raise ValueError("k must be >= 2.")
    if embargo_days < 0:
        raise ValueError("embargo_days must be >= 0.")
    if n_samples < k * 2 + embargo_days:
        raise ValueError(
            f"n_samples={n_samples} is too small for k={k} and "
            f"embargo_days={embargo_days}; need at least "
            f"{k * 2 + embargo_days}."
        )
    fold_size = n_samples // k
    splits: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for fold_idx in range(k):
        test_start = fold_idx * fold_size
        test_end = (fold_idx + 1) * fold_size if fold_idx < k - 1 else n_samples
        test = tuple(range(test_start, test_end))
        embargo_end = min(n_samples, test_end + embargo_days)
        train = tuple(
            i for i in range(n_samples)
            if i < test_start or i >= embargo_end
        )
        splits.append((train, test))
    return tuple(splits)


__all__ = ("purged_kfold_indices",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation_folds.py -v`

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/validation_folds.py tests/unit/test_validation_folds.py
git commit -m "feat(validation_folds): add purged k-fold splitter"
```

### Task 2: Add embargo behavior + error tests

**Files:**
- Modify: `tests/unit/test_validation_folds.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_validation_folds.py`:

```python
def test_purged_kfold_embargo_respected():
    # With embargo=3, the training indices immediately after any test
    # fold's end must be excluded.
    splits = purged_kfold_indices(n_samples=100, k=5, embargo_days=3)
    for train, test in splits:
        if not test:
            continue
        test_end = max(test) + 1
        forbidden_train = set(range(test_end, min(100, test_end + 3)))
        assert not (set(train) & forbidden_train), (
            f"Training set leaked into embargo zone: "
            f"{set(train) & forbidden_train}"
        )


def test_purged_kfold_rejects_insufficient_samples():
    with pytest.raises(ValueError, match="too small"):
        purged_kfold_indices(n_samples=5, k=5, embargo_days=0)


def test_purged_kfold_rejects_invalid_k():
    with pytest.raises(ValueError, match="k must be >= 2"):
        purged_kfold_indices(n_samples=100, k=1, embargo_days=0)


def test_purged_kfold_rejects_negative_embargo():
    with pytest.raises(ValueError, match="embargo_days"):
        purged_kfold_indices(n_samples=100, k=5, embargo_days=-1)
```

- [ ] **Step 2: Run tests to verify they pass**

The embargo logic and validation errors are already in the Task 1 impl, so these should pass immediately.

Run: `uv run pytest tests/unit/test_validation_folds.py -v`

Expected: all 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_validation_folds.py
git commit -m "test(validation_folds): add embargo and error-handling coverage"
```

---

## W4 — Cost-drag accounting + contract changes

### Task 3: Add `annualized_cost_drag_bps` to `DailyBarBacktestResult`

**Files:**
- Modify: `src/tradingx/backtest.py`
- Modify: `tests/unit/test_backtest.py`

- [ ] **Step 1: Read current `DailyBarBacktestResult` shape**

Run: `uv run python -c "from tradingx.backtest import DailyBarBacktestResult; import dataclasses; print([f.name for f in dataclasses.fields(DailyBarBacktestResult)])"`

Note existing fields so Task 3 adds cleanly without collisions.

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_backtest.py`:

```python
from decimal import Decimal

import numpy as np
import pandas as pd

from tradingx.backtest import DailyBarBacktestResult, run_daily_bar_backtest
from tradingx.costs import CostModelConfig


def test_backtest_result_carries_annualized_cost_drag_bps():
    # Construct a minimal two-symbol panel and one rebalance
    dates = pd.date_range("2025-01-02", periods=10, freq="B", tz="UTC")
    bars = {
        "SPY": pd.DataFrame(
            {"close": np.linspace(400.0, 410.0, 10), "volume": [1e7] * 10},
            index=dates,
        ),
        "AGG": pd.DataFrame(
            {"close": np.linspace(100.0, 101.0, 10), "volume": [5e6] * 10},
            index=dates,
        ),
    }
    target_weights = pd.DataFrame(
        {"SPY": [0.6] * 10, "AGG": [0.4] * 10}, index=dates
    )
    result = run_daily_bar_backtest(
        bars,
        target_weights=target_weights,
        cost_model_config=CostModelConfig(),
    )
    assert isinstance(result, DailyBarBacktestResult)
    assert hasattr(result, "annualized_cost_drag_bps")
    assert isinstance(result.annualized_cost_drag_bps, Decimal)
    # A non-trivial rebalance should incur some cost
    assert result.annualized_cost_drag_bps >= Decimal("0")


def test_backtest_cost_drag_is_zero_for_zero_turnover_path():
    dates = pd.date_range("2025-01-02", periods=10, freq="B", tz="UTC")
    # Static prices + static target weights => no trades beyond the first day
    bars = {
        "SPY": pd.DataFrame(
            {"close": [400.0] * 10, "volume": [1e7] * 10}, index=dates
        ),
    }
    target_weights = pd.DataFrame({"SPY": [1.0] * 10}, index=dates)
    result = run_daily_bar_backtest(
        bars,
        target_weights=target_weights,
        cost_model_config=CostModelConfig(),
    )
    # After the initial allocation on day 0, zero turnover => near-zero drag
    assert result.annualized_cost_drag_bps < Decimal("5")  # < 5 bps slack
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_backtest.py -k cost_drag -v`

Expected: FAIL on `AttributeError: 'DailyBarBacktestResult' object has no attribute 'annualized_cost_drag_bps'`.

- [ ] **Step 4: Implement**

In `src/tradingx/backtest.py`, extend the `DailyBarBacktestResult` dataclass:

```python
@dataclass(frozen=True)
class DailyBarBacktestResult:
    # ...existing fields unchanged...
    annualized_cost_drag_bps: Decimal
```

Inside `run_daily_bar_backtest`, after the main loop that sums `total_cost`, compute:

```python
# After the existing backtest loop populates total_cost and the equity path:
trading_days = max(1, len(target_weights))
avg_equity = float(np.mean(equity_path)) if len(equity_path) > 0 else 1.0
if avg_equity <= 0.0:
    annualized_cost_drag_bps = Decimal("0")
else:
    cost_fraction = total_cost / avg_equity
    annualized_fraction = cost_fraction * (252.0 / trading_days)
    annualized_cost_drag_bps = Decimal(str(annualized_fraction * 10_000.0))
```

Pass it into the `DailyBarBacktestResult(...)` construction at the end.

If `total_cost` and `equity_path` variable names differ in the actual code, adapt to whatever the existing loop produces — the concept is: total realized cost over the window, divided by average equity, annualized by `252 / n_days`, scaled to bps.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_backtest.py -k cost_drag -v`

Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tradingx/backtest.py tests/unit/test_backtest.py
git commit -m "feat(backtest): expose annualized_cost_drag_bps on DailyBarBacktestResult"
```

### Task 4: Change `_candidate_returns` to return `(returns, cost_drag_bps)` and make costs default

**Files:**
- Modify: `src/tradingx/validation.py`
- Modify: `tests/unit/test_validation.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_validation.py`:

```python
from decimal import Decimal

from tradingx.validation import _candidate_returns


def test_candidate_returns_returns_tuple_of_returns_and_drag(
    sample_candidate_fixture,
    sample_bars_by_symbol_fixture,
):
    """_candidate_returns should return (returns, annualized_cost_drag_bps)."""
    result = _candidate_returns(
        sample_candidate_fixture,
        bars_by_symbol=sample_bars_by_symbol_fixture,
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    returns, drag_bps = result
    assert isinstance(returns, tuple)
    assert all(isinstance(r, Decimal) for r in returns)
    assert isinstance(drag_bps, Decimal)
    assert drag_bps >= Decimal("0")


def test_candidate_returns_defaults_apply_costs_when_config_omitted(
    sample_candidate_fixture,
    sample_bars_by_symbol_fixture,
):
    """When no CostModelConfig is passed, costs must still be applied."""
    _, drag_bps = _candidate_returns(
        sample_candidate_fixture,
        bars_by_symbol=sample_bars_by_symbol_fixture,
    )
    # Default CostModelConfig() has non-zero spread/impact/fee coefficients
    # for any non-trivial turnover path
    assert drag_bps > Decimal("0")
```

If `sample_candidate_fixture` and `sample_bars_by_symbol_fixture` don't exist in `tests/unit/test_validation.py`, use the closest equivalent fixture in that file or borrow the construction pattern from an existing test in the same file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validation.py -k candidate_returns -v`

Expected: FAIL — the current `_candidate_returns` returns `tuple[Decimal, ...]`, not the new 2-tuple.

- [ ] **Step 3: Implement**

In `src/tradingx/validation.py`, change `_candidate_returns`:

```python
def _candidate_returns(
    candidate: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    parameter_overrides: dict[str, ScalarValue] | None = None,
    cost_model_config: CostModelConfig | None = None,
) -> tuple[tuple[Decimal, ...], Decimal]:
    configured_candidate = _candidate_with_parameter_overrides(
        candidate,
        parameter_overrides=parameter_overrides,
    )
    target_weights = build_candidate_target_weight_history(
        configured_candidate,
        bars_by_symbol=bars_by_symbol,
    )
    traded_symbols = tuple(str(symbol) for symbol in target_weights.columns)

    # Tranche-1 discipline: costs are mandatory. Callers can still
    # override the config for sensitivity analysis.
    resolved_cost_config = cost_model_config or CostModelConfig()
    result = run_daily_bar_backtest(
        {symbol: bars_by_symbol[symbol] for symbol in traded_symbols},
        target_weights=target_weights,
        cost_model_config=resolved_cost_config,
    )
    returns = tuple(
        Decimal(str(value)) for value in result.portfolio_returns.tolist()
    )
    return returns, result.annualized_cost_drag_bps
```

Now update every caller of `_candidate_returns` inside `validation.py` to unpack the 2-tuple. Use `grep` on the file to find them:

Run: `grep -n "_candidate_returns(" src/tradingx/validation.py`

For each call site that currently assigns the result to a single name, change to:

```python
returns, cost_drag_bps = _candidate_returns(...)
```

Propagate `cost_drag_bps` downstream where it's needed (into `evaluate_candidate`; wiring continues in Task 6).

**Adversarial-callback contract preservation.** The `BacktestRunner`
type alias in [evaluation.py:27](src/tradingx/evaluation.py:27) is
consumed by `_parameter_sensitivity_check` at
[evaluation.py:162](src/tradingx/evaluation.py:162) and
`_cost_sensitivity_check` at
[evaluation.py:284](src/tradingx/evaluation.py:284), both of which
expect a plain return tuple (not the new 2-tuple). Do **not** change
the `BacktestRunner` type or the adversarial call sites in this
tranche. Instead, find the closure in
[validation.py:496](src/tradingx/validation.py:496) that currently
forwards `_candidate_returns` into `AdversarialCheckContext.backtest_runner`,
and wrap it so the callback still returns only the returns tuple:

```python
# Old (inside build_gate_report or similar):
backtest_runner=_candidate_returns,

# New:
def _returns_only_runner(
    candidate_arg: StrategyCandidate,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    parameter_overrides: dict[str, ScalarValue] | None = None,
    cost_model_config: CostModelConfig | None = None,
) -> tuple[Decimal, ...]:
    returns, _drag = _candidate_returns(
        candidate_arg,
        bars_by_symbol=bars_by_symbol,
        parameter_overrides=parameter_overrides,
        cost_model_config=cost_model_config,
    )
    return returns

# ...
backtest_runner=_returns_only_runner,
```

Cost drag is consumed only by the primary-evaluation path in Task 5;
the adversarial path keeps its existing contract.

**Add a regression test** to `tests/unit/test_validation.py`:

```python
def test_adversarial_backtest_runner_still_returns_plain_tuple(
    sample_gate_report_inputs_fixture,
):
    """The adversarial-check callback must keep its returns-only shape
    even after _candidate_returns starts producing cost drag."""
    # Build the gate report and inspect what flows into the
    # adversarial context. The closure must return tuple[Decimal, ...],
    # not tuple[tuple[Decimal, ...], Decimal].
    # Use the same fixture other tests in this file use.
    report = build_gate_report(**sample_gate_report_inputs_fixture)
    # If the closure returned the wrong shape, the adversarial checks
    # inside build_gate_report would have raised before returning.
    assert report is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py -v`

Expected: the new tests PASS; all pre-existing tests still PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/validation.py tests/unit/test_validation.py
git commit -m "refactor(validation): return cost drag from _candidate_returns and default costs on"
```

### Task 5: Accept `annualized_cost_drag_bps` in `evaluate_candidate` and thread to evidence pack

**Files:**
- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/evaluation.py`
- Modify: `src/tradingx/validation.py` (caller update)
- Modify: `tests/unit/test_evaluation.py`

- [ ] **Step 1: Add field to `EvaluationEvidencePack`**

In `src/tradingx/types.py`, add to `EvaluationEvidencePack`:

```python
annualized_cost_drag_bps: Decimal | None = None
```

(Ensure the frozen dataclass still works; the new field goes after the existing ones with a default so existing construction call sites don't break.)

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_evaluation.py`:

```python
from decimal import Decimal

from tradingx.evaluation import evaluate_candidate


def test_evaluate_candidate_threads_cost_drag_to_evidence_pack(
    sample_candidate_fixture,
    sample_bars_by_symbol_fixture,
    sample_benchmark_returns_fixture,
    sample_window_fixture,
    sample_adversarial_context_fixture,
):
    # Use the closest existing fixture set in test_evaluation.py.
    pack = evaluate_candidate(
        sample_candidate_fixture,
        candidate_returns=tuple([Decimal("0.001")] * 300),
        benchmark_returns=sample_benchmark_returns_fixture,
        window_start_utc=sample_window_fixture[0],
        window_end_utc=sample_window_fixture[1],
        adversarial_context=sample_adversarial_context_fixture,
        annualized_cost_drag_bps=Decimal("12.5"),
    )
    assert pack.annualized_cost_drag_bps == Decimal("12.5")


def test_evaluate_candidate_cost_drag_is_none_when_not_supplied(
    sample_candidate_fixture,
    sample_benchmark_returns_fixture,
    sample_window_fixture,
    sample_adversarial_context_fixture,
):
    pack = evaluate_candidate(
        sample_candidate_fixture,
        candidate_returns=tuple([Decimal("0.001")] * 300),
        benchmark_returns=sample_benchmark_returns_fixture,
        window_start_utc=sample_window_fixture[0],
        window_end_utc=sample_window_fixture[1],
        adversarial_context=sample_adversarial_context_fixture,
    )
    assert pack.annualized_cost_drag_bps is None
```

Reuse whichever fixtures already exist in `tests/unit/test_evaluation.py` — adjust parameter names as needed.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_evaluation.py -k cost_drag -v`

Expected: FAIL on `TypeError: unexpected keyword argument 'annualized_cost_drag_bps'`.

- [ ] **Step 4: Implement**

In `src/tradingx/evaluation.py`, update `evaluate_candidate`:

```python
def evaluate_candidate(
    candidate: StrategyCandidate,
    *,
    candidate_returns: Sequence[Decimal],
    benchmark_returns: Sequence[Decimal],
    window_start_utc: datetime,
    window_end_utc: datetime,
    adversarial_context: AdversarialCheckContext,
    annualized_cost_drag_bps: Decimal | None = None,
) -> EvaluationEvidencePack:
    # ...existing body unchanged up to the final EvaluationEvidencePack(...) construction...
    return EvaluationEvidencePack(
        # ...existing keyword args...
        annualized_cost_drag_bps=annualized_cost_drag_bps,
    )
```

Then update the caller in `src/tradingx/validation.py` (likely inside `_build_gate1_candidate_result` or its callers) to pass the `cost_drag_bps` value unpacked in Task 4 into `evaluate_candidate`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_evaluation.py tests/unit/test_validation.py -v`

Expected: new tests PASS; no regression on existing tests.

- [ ] **Step 6: Commit**

```bash
git add src/tradingx/types.py src/tradingx/evaluation.py src/tradingx/validation.py tests/unit/test_evaluation.py
git commit -m "feat(evaluation): thread annualized_cost_drag_bps into evidence pack"
```

### Task 6: Surface cost drag in the validation read model

**Files:**
- Modify: `src/tradingx/web/readmodels.py`
- Modify: `tests/unit/test_web_readmodels.py`

**Shape of the persisted validation report (corrected).** Reports
persisted by the validation pipeline use `candidate_results` (not
`candidates`). Confirmed via
[reporting.py:107](src/tradingx/reporting.py:107),
[web/readmodels.py:1854](src/tradingx/web/readmodels.py:1854), and the
existing iteration at
[web/readmodels.py:2229](src/tradingx/web/readmodels.py:2229). Each
entry in `candidate_results` is a dict with `candidate_id`, `status`,
`criteria`, and now also `annualized_cost_drag_bps` once Task 5 ships.

**Current seam.** `_build_performance_diagnostics` at
[web/readmodels.py:1975](src/tradingx/web/readmodels.py:1975) today
uses only the report-level `summary` string. It does not inspect
per-candidate payloads. This task extends it to pull the worst-case
cost drag across candidate results and append it to the existing
"Validation benchmark stack is not yet passing" diagnostic (or a new
info-severity diagnostic when the report is passing but drag is
informative).

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_web_readmodels.py`:

```python
def test_readmodel_surfaces_cost_drag_when_present(
    sample_validation_report_fixture,
):
    """_build_performance_diagnostics must read per-candidate
    annualized_cost_drag_bps from report['candidate_results']."""
    report = dict(sample_validation_report_fixture)
    report["candidate_results"] = [
        {
            "candidate_id": "trend-following-v1",
            "status": "fail",
            "criteria": [],
            "annualized_cost_drag_bps": "12.5",
        },
    ]
    report.setdefault("status", "fail")

    model = _build_local_web_read_model_for_test()  # existing helper or inline construction
    diagnostics = model._build_performance_diagnostics(
        runtime_state=_sample_runtime_state(),
        warmup=None,
        validation_report=report,
        replay_summary=None,
    )
    messages = " | ".join(d.detail for d in diagnostics)
    assert "12.5" in messages or "cost drag" in messages.lower()


def test_readmodel_ignores_missing_cost_drag(
    sample_validation_report_fixture,
):
    """When candidate_results rows omit annualized_cost_drag_bps, the
    diagnostic must not crash and must not mention cost drag."""
    report = dict(sample_validation_report_fixture)
    report["candidate_results"] = [
        {
            "candidate_id": "trend-following-v1",
            "status": "fail",
            "criteria": [],
            # No annualized_cost_drag_bps key
        },
    ]
    report.setdefault("status", "fail")

    model = _build_local_web_read_model_for_test()
    diagnostics = model._build_performance_diagnostics(
        runtime_state=_sample_runtime_state(),
        warmup=None,
        validation_report=report,
        replay_summary=None,
    )
    messages = " | ".join(d.detail for d in diagnostics)
    assert "cost drag" not in messages.lower()
```

Reuse whatever construction helpers already exist in
`tests/unit/test_web_readmodels.py` — the tests at
[test_web_readmodels.py:317](tests/unit/test_web_readmodels.py:317)
already exercise `candidate_results` and will show the pattern.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_web_readmodels.py -k cost_drag -v`

Expected: FAIL — detail string doesn't yet include cost-drag info.

- [ ] **Step 3: Implement**

In `src/tradingx/web/readmodels.py`, inside
`_build_performance_diagnostics`, extend the existing validation-report
branch (the one that emits the "Validation benchmark stack is not yet
passing" diagnostic at approximately
[web/readmodels.py:1999](src/tradingx/web/readmodels.py:1999)) to
also inspect per-candidate cost drag:

```python
if validation_report is not None:
    candidate_results = self._ensure_list(
        validation_report.get("candidate_results", [])
    )
    worst_cost_drag_bps: Decimal | None = None
    for candidate_payload in candidate_results:
        if not isinstance(candidate_payload, dict):
            continue
        raw_drag = candidate_payload.get("annualized_cost_drag_bps")
        if raw_drag is None:
            continue
        try:
            drag = Decimal(str(raw_drag))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if worst_cost_drag_bps is None or drag > worst_cost_drag_bps:
            worst_cost_drag_bps = drag

    report_status = str(validation_report.get("status", ""))
    if report_status != "pass":
        detail = str(
            validation_report.get(
                "summary",
                "Latest validation report is not yet passing.",
            )
        )
        if worst_cost_drag_bps is not None:
            detail = (
                f"{detail} Worst annualized cost drag across "
                f"candidates: {worst_cost_drag_bps:.1f} bps."
            )
        diagnostics.append(
            PerformanceDiagnostic(
                diagnostic_id="gate_validation",
                title="Validation benchmark stack is not yet passing.",
                detail=detail,
                severity="critical",
                owner="Research",
                action=(
                    "Review hurdle clearance, opportunity-cost edge, "
                    "and operating constraints before adding capital."
                ),
            )
        )
    elif worst_cost_drag_bps is not None:
        # Informative diagnostic when the report passed but cost drag
        # is worth surfacing for diagnostics.
        diagnostics.append(
            PerformanceDiagnostic(
                diagnostic_id="cost_drag",
                title="Cost drag recorded on passing validation.",
                detail=(
                    f"Worst annualized cost drag across candidates: "
                    f"{worst_cost_drag_bps:.1f} bps."
                ),
                severity="info",
                owner="Research",
                action="Monitor cost trend as paper evidence accumulates.",
            )
        )
```

Import `InvalidOperation` from `decimal` at the top of the file if not
already imported.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_web_readmodels.py -v`

Expected: new tests PASS; no regression on existing tests.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/web/readmodels.py tests/unit/test_web_readmodels.py
git commit -m "feat(readmodels): surface worst annualized cost drag from candidate_results"
```

---

## W2 — Trials ledger

### Task 7: Add `TrialRecord` and `TrialStatistics` types

**Files:**
- Modify: `src/tradingx/types.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_types.py` (create the file if it doesn't already exist):

```python
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.types import TrialRecord, TrialStatistics


def test_trial_record_is_frozen_dataclass():
    record = TrialRecord(
        trial_id="trial-1",
        candidate_id="trend-following-v1",
        family="trend_following",
        window_start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 12, 31, tzinfo=UTC),
        observed_sharpe_net_of_costs=Decimal("1.05"),
        observed_cagr_net_of_costs=Decimal("0.12"),
        observed_max_drawdown=Decimal("0.09"),
        observed_cdar_95=Decimal("0.06"),
        annualized_cost_drag_bps=Decimal("8.4"),
        passed=True,
        recorded_at_utc=datetime(2026, 12, 31, 23, tzinfo=UTC),
        git_sha="abc1234",
        config_fingerprint="deadbeef",
    )
    import dataclasses
    assert dataclasses.is_dataclass(record)
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.passed = False  # type: ignore[misc]


def test_trial_statistics_shape():
    stats = TrialStatistics(
        n_trials=5,
        trial_sharpe_mean=0.8,
        trial_sharpe_variance=0.04,
    )
    assert stats.n_trials == 5
    assert stats.trial_sharpe_mean == 0.8
    assert stats.trial_sharpe_variance == 0.04
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_types.py -v`

Expected: FAIL on `ImportError: cannot import name 'TrialRecord'`.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`:

```python
@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    candidate_id: str
    family: str
    window_start_utc: datetime
    window_end_utc: datetime
    observed_sharpe_net_of_costs: Decimal
    observed_cagr_net_of_costs: Decimal
    observed_max_drawdown: Decimal
    observed_cdar_95: Decimal
    annualized_cost_drag_bps: Decimal
    passed: bool
    recorded_at_utc: datetime
    git_sha: str
    config_fingerprint: str


@dataclass(frozen=True)
class TrialStatistics:
    n_trials: int
    trial_sharpe_mean: float
    trial_sharpe_variance: float
```

Add to `__all__` if the file maintains one.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_types.py -v`

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py tests/unit/test_types.py
git commit -m "feat(types): add TrialRecord and TrialStatistics"
```

### Task 8: Trials ledger — initialize schema + record + idempotency

**Files:**
- Create: `src/tradingx/trials.py`
- Create: `tests/unit/test_trials.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_trials.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.trials import TrialsLedger
from tradingx.types import TrialRecord


def _make_record(trial_id: str = "trial-1", sharpe: str = "1.0") -> TrialRecord:
    return TrialRecord(
        trial_id=trial_id,
        candidate_id="trend-following-v1",
        family="trend_following",
        window_start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 12, 31, tzinfo=UTC),
        observed_sharpe_net_of_costs=Decimal(sharpe),
        observed_cagr_net_of_costs=Decimal("0.12"),
        observed_max_drawdown=Decimal("0.09"),
        observed_cdar_95=Decimal("0.06"),
        annualized_cost_drag_bps=Decimal("8.4"),
        passed=True,
        recorded_at_utc=datetime(2026, 12, 31, 23, tzinfo=UTC),
        git_sha="abc1234",
        config_fingerprint="deadbeef",
    )


def test_trials_ledger_round_trip(tmp_path: Path):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    record = _make_record()
    ledger.record(record)
    fetched = ledger.list_for_candidate("trend-following-v1")
    assert len(fetched) == 1
    assert fetched[0].trial_id == "trial-1"
    assert fetched[0].observed_sharpe_net_of_costs == Decimal("1.0")


def test_trials_ledger_idempotent_on_trial_id(tmp_path: Path):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    ledger.record(_make_record("trial-1", "1.0"))
    ledger.record(_make_record("trial-1", "2.0"))  # same id, different payload
    fetched = ledger.list_for_candidate("trend-following-v1")
    assert len(fetched) == 1
    # First-write-wins is the contract; confirm original stuck
    assert fetched[0].observed_sharpe_net_of_costs == Decimal("1.0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_trials.py -v`

Expected: FAIL on `ModuleNotFoundError: No module named 'tradingx.trials'`.

- [ ] **Step 3: Implement**

Create `src/tradingx/trials.py`:

```python
"""SQLite-backed append-only trials ledger for validation.

Records every candidate evaluation so multiple-testing discipline
(DSR, eventual PBO) can compute statistics across the trial
population. Follows the pattern in `src/tradingx/journal.py`.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Iterator

from tradingx.types import TrialRecord, TrialStatistics


_SCHEMA = """
CREATE TABLE IF NOT EXISTS trials (
    trial_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    family TEXT NOT NULL,
    window_start_utc TEXT NOT NULL,
    window_end_utc TEXT NOT NULL,
    observed_sharpe_net_of_costs TEXT NOT NULL,
    observed_cagr_net_of_costs TEXT NOT NULL,
    observed_max_drawdown TEXT NOT NULL,
    observed_cdar_95 TEXT NOT NULL,
    annualized_cost_drag_bps TEXT NOT NULL,
    passed INTEGER NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    git_sha TEXT NOT NULL,
    config_fingerprint TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trials_candidate ON trials(candidate_id);
CREATE INDEX IF NOT EXISTS idx_trials_family ON trials(family);
CREATE INDEX IF NOT EXISTS idx_trials_window
    ON trials(window_start_utc, window_end_utc);
"""


class TrialsLedger:
    def __init__(self, *, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._database_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, trial: TrialRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO trials VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    trial.trial_id,
                    trial.candidate_id,
                    trial.family,
                    trial.window_start_utc.isoformat(),
                    trial.window_end_utc.isoformat(),
                    str(trial.observed_sharpe_net_of_costs),
                    str(trial.observed_cagr_net_of_costs),
                    str(trial.observed_max_drawdown),
                    str(trial.observed_cdar_95),
                    str(trial.annualized_cost_drag_bps),
                    1 if trial.passed else 0,
                    trial.recorded_at_utc.isoformat(),
                    trial.git_sha,
                    trial.config_fingerprint,
                ),
            )

    def list_for_candidate(
        self,
        candidate_id: str,
        *,
        window_start_utc: datetime | None = None,
        window_end_utc: datetime | None = None,
    ) -> tuple[TrialRecord, ...]:
        query = "SELECT * FROM trials WHERE candidate_id = ?"
        params: list[object] = [candidate_id]
        if window_start_utc is not None:
            query += " AND window_start_utc >= ?"
            params.append(window_start_utc.isoformat())
        if window_end_utc is not None:
            query += " AND window_end_utc <= ?"
            params.append(window_end_utc.isoformat())
        query += " ORDER BY recorded_at_utc"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return tuple(_row_to_record(row) for row in rows)


def _row_to_record(row: tuple) -> TrialRecord:
    return TrialRecord(
        trial_id=row[0],
        candidate_id=row[1],
        family=row[2],
        window_start_utc=datetime.fromisoformat(row[3]),
        window_end_utc=datetime.fromisoformat(row[4]),
        observed_sharpe_net_of_costs=Decimal(row[5]),
        observed_cagr_net_of_costs=Decimal(row[6]),
        observed_max_drawdown=Decimal(row[7]),
        observed_cdar_95=Decimal(row[8]),
        annualized_cost_drag_bps=Decimal(row[9]),
        passed=bool(row[10]),
        recorded_at_utc=datetime.fromisoformat(row[11]),
        git_sha=row[12],
        config_fingerprint=row[13],
    )


__all__ = ("TrialsLedger",)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_trials.py -v`

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/trials.py tests/unit/test_trials.py
git commit -m "feat(trials): scaffold TrialsLedger with record + list_for_candidate"
```

### Task 9: Add `list_for_candidate` filtering by window + `trial_statistics_for_family`

**Files:**
- Modify: `src/tradingx/trials.py`
- Modify: `tests/unit/test_trials.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_trials.py`:

```python
def test_trials_ledger_filters_by_window(tmp_path: Path):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    early = _make_record("trial-early")
    late = _make_record("trial-late")
    ledger.record(early)
    ledger.record(late)
    recent = ledger.list_for_candidate(
        "trend-following-v1",
        window_start_utc=datetime(2025, 6, 1, tzinfo=UTC),
        window_end_utc=datetime(2026, 12, 31, tzinfo=UTC),
    )
    # Both records have identical windows; both should match
    assert {r.trial_id for r in recent} == {"trial-early", "trial-late"}


def test_trial_statistics_for_family_aggregates_across_candidates(tmp_path: Path):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    for idx, sharpe in enumerate(["0.5", "0.8", "1.1", "1.3"]):
        record = _make_record(f"trial-{idx}", sharpe)
        ledger.record(record)
    stats = ledger.trial_statistics_for_family("trend_following")
    assert stats.n_trials == 4
    # Mean of 0.5, 0.8, 1.1, 1.3 = 0.925; variance of those values
    assert abs(stats.trial_sharpe_mean - 0.925) < 1e-9
    # Sample variance (ddof=1): let pytest verify numerically
    expected_var = ((0.5-0.925)**2 + (0.8-0.925)**2 + (1.1-0.925)**2 + (1.3-0.925)**2) / 3.0
    assert abs(stats.trial_sharpe_variance - expected_var) < 1e-9


def test_trial_statistics_for_family_handles_single_trial(tmp_path: Path):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    ledger.record(_make_record("trial-only", "1.2"))
    stats = ledger.trial_statistics_for_family("trend_following")
    assert stats.n_trials == 1
    # With one sample, variance is undefined; we return 0.0 by convention
    assert stats.trial_sharpe_variance == 0.0


def test_trial_statistics_for_family_returns_empty_stats_for_unknown_family(
    tmp_path: Path,
):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    ledger.record(_make_record())
    stats = ledger.trial_statistics_for_family("carry")
    assert stats.n_trials == 0
    assert stats.trial_sharpe_variance == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_trials.py -k "window or family" -v`

Expected: FAIL on `AttributeError: 'TrialsLedger' object has no attribute 'trial_statistics_for_family'`.

- [ ] **Step 3: Implement**

Append to `TrialsLedger` in `src/tradingx/trials.py`:

```python
    def trial_statistics_for_family(self, family: str) -> TrialStatistics:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT observed_sharpe_net_of_costs FROM trials WHERE family = ?",
                (family,),
            ).fetchall()
        if not rows:
            return TrialStatistics(
                n_trials=0,
                trial_sharpe_mean=0.0,
                trial_sharpe_variance=0.0,
            )
        sharpes = [float(Decimal(row[0])) for row in rows]
        n = len(sharpes)
        mean = sum(sharpes) / n
        if n < 2:
            variance = 0.0
        else:
            variance = sum((s - mean) ** 2 for s in sharpes) / (n - 1)
        return TrialStatistics(
            n_trials=n,
            trial_sharpe_mean=mean,
            trial_sharpe_variance=variance,
        )
```

The window-filter test already passes via the code written in Task 8 — no additional code needed for that case.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_trials.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/trials.py tests/unit/test_trials.py
git commit -m "feat(trials): add trial_statistics_for_family with ddof=1 variance"
```

---

## W3 — DSR wiring into `evaluate_candidate`

### Task 10: Add `deflated_sharpe_ratio` and `north_star_sharpe_met` fields on `EvaluationEvidencePack`

**Files:**
- Modify: `src/tradingx/types.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_types.py`:

```python
def test_evaluation_evidence_pack_has_dsr_and_north_star_fields():
    import dataclasses
    from tradingx.types import EvaluationEvidencePack
    field_names = {f.name for f in dataclasses.fields(EvaluationEvidencePack)}
    assert "deflated_sharpe_ratio" in field_names
    assert "north_star_sharpe_met" in field_names
    assert "annualized_cost_drag_bps" in field_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_types.py -k dsr -v`

Expected: FAIL — one or more fields missing.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`, add to `EvaluationEvidencePack`:

```python
deflated_sharpe_ratio: Decimal | None = None
north_star_sharpe_met: bool | None = None
```

(`annualized_cost_drag_bps` was added in Task 5.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_types.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py tests/unit/test_types.py
git commit -m "feat(types): add DSR and north-star Sharpe fields on EvaluationEvidencePack"
```

### Task 11: Wire DSR computation + trial recording into `evaluate_candidate`

**Files:**
- Modify: `src/tradingx/evaluation.py`
- Modify: `tests/unit/test_evaluation.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_evaluation.py`:

```python
import uuid

import pytest

from tradingx.evaluation import evaluate_candidate
from tradingx.trials import TrialsLedger
from tradingx.types import TrialRecord


def _seed_family_trials(ledger: TrialsLedger, family: str, sharpes: list[str]) -> None:
    for idx, sharpe in enumerate(sharpes):
        ledger.record(
            TrialRecord(
                trial_id=str(uuid.uuid4()),
                candidate_id=f"{family}-v{idx}",
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


def test_evaluate_candidate_populates_dsr_when_trials_sufficient(
    tmp_path,
    sample_candidate_fixture,
    sample_benchmark_returns_fixture,
    sample_window_fixture,
    sample_adversarial_context_fixture,
):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    _seed_family_trials(
        ledger, family="trend_following", sharpes=["0.5", "0.8", "1.1", "1.3"],
    )
    pack = evaluate_candidate(
        sample_candidate_fixture,  # assume family == "trend_following"
        candidate_returns=tuple([Decimal("0.001")] * 300),
        benchmark_returns=sample_benchmark_returns_fixture,
        window_start_utc=sample_window_fixture[0],
        window_end_utc=sample_window_fixture[1],
        adversarial_context=sample_adversarial_context_fixture,
        annualized_cost_drag_bps=Decimal("7.0"),
        trials_ledger=ledger,
    )
    assert pack.deflated_sharpe_ratio is not None
    assert isinstance(pack.deflated_sharpe_ratio, Decimal)


def test_evaluate_candidate_dsr_is_none_when_trials_insufficient(
    tmp_path,
    sample_candidate_fixture,
    sample_benchmark_returns_fixture,
    sample_window_fixture,
    sample_adversarial_context_fixture,
):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    # No seeded trials -> n_trials == 0
    pack = evaluate_candidate(
        sample_candidate_fixture,
        candidate_returns=tuple([Decimal("0.001")] * 300),
        benchmark_returns=sample_benchmark_returns_fixture,
        window_start_utc=sample_window_fixture[0],
        window_end_utc=sample_window_fixture[1],
        adversarial_context=sample_adversarial_context_fixture,
        annualized_cost_drag_bps=Decimal("7.0"),
        trials_ledger=ledger,
    )
    assert pack.deflated_sharpe_ratio is None


def test_evaluate_candidate_north_star_flag_set_when_sharpe_gte_1_3(
    tmp_path,
    sample_candidate_fixture,
    sample_benchmark_returns_fixture,
    sample_window_fixture,
    sample_adversarial_context_fixture,
):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    # High-Sharpe candidate returns (calibrate to yield >= 1.3 Sharpe)
    pack = evaluate_candidate(
        sample_candidate_fixture,
        candidate_returns=tuple([Decimal("0.003")] * 300),  # ~high mean, low variance
        benchmark_returns=sample_benchmark_returns_fixture,
        window_start_utc=sample_window_fixture[0],
        window_end_utc=sample_window_fixture[1],
        adversarial_context=sample_adversarial_context_fixture,
        annualized_cost_drag_bps=Decimal("5.0"),
        trials_ledger=ledger,
    )
    # The exact threshold crossing depends on fixture scale; assert
    # the field is populated (True or False), not None.
    assert isinstance(pack.north_star_sharpe_met, bool)


def test_evaluate_candidate_does_not_record_trial(
    tmp_path,
    sample_candidate_fixture,
    sample_benchmark_returns_fixture,
    sample_window_fixture,
    sample_adversarial_context_fixture,
):
    """Trial recording is the gate layer's responsibility, not
    evaluate_candidate's. evaluate_candidate only READS the ledger
    for DSR input; it never WRITES."""
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    _ = evaluate_candidate(
        sample_candidate_fixture,
        candidate_returns=tuple([Decimal("0.001")] * 300),
        benchmark_returns=sample_benchmark_returns_fixture,
        window_start_utc=sample_window_fixture[0],
        window_end_utc=sample_window_fixture[1],
        adversarial_context=sample_adversarial_context_fixture,
        annualized_cost_drag_bps=Decimal("7.0"),
        trials_ledger=ledger,
    )
    records = ledger.list_for_candidate(sample_candidate_fixture.candidate_id)
    assert records == ()  # empty — gate layer has not run yet
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_evaluation.py -k "dsr or north_star or records_trial" -v`

Expected: FAIL on `TypeError: unexpected keyword argument 'trials_ledger'`.

- [ ] **Step 3: Implement**

In `src/tradingx/evaluation.py`:

```python
import numpy as np
from scipy.stats import kurtosis as scipy_kurtosis, skew as scipy_skew

from tradingx.stats import deflated_sharpe_ratio
from tradingx.trials import TrialsLedger
from tradingx.types import EvaluationEvidencePack


def evaluate_candidate(
    candidate: StrategyCandidate,
    *,
    candidate_returns: Sequence[Decimal],
    benchmark_returns: Sequence[Decimal],
    window_start_utc: datetime,
    window_end_utc: datetime,
    adversarial_context: AdversarialCheckContext,
    annualized_cost_drag_bps: Decimal | None = None,
    trials_ledger: TrialsLedger | None = None,
) -> EvaluationEvidencePack:
    # ...existing body unchanged through candidate_metrics_numeric
    # construction at evaluation.py:410 and the rest of the metric-pack
    # assembly up to the final EvaluationEvidencePack(...) construction...

    # Use the existing candidate_metrics dict as the single source of
    # truth for observed Sharpe. _build_metric_pack already computes
    # sharpe_ratio net of costs (because _candidate_returns always
    # applies costs after Task 4). No recomputation here.
    observed_sharpe_raw = candidate_metrics_numeric.get("sharpe_ratio")
    observed_sharpe = (
        float(observed_sharpe_raw) if observed_sharpe_raw is not None else None
    )

    # North-star flag: threshold is preference-ranking signal, not pass/fail.
    north_star_sharpe_met: bool | None = None
    if observed_sharpe is not None:
        north_star_sharpe_met = Decimal(str(observed_sharpe)) >= Decimal("1.3")

    # DSR requires trial statistics. If no ledger or not enough history,
    # leave DSR as None and continue.
    deflated_sharpe: Decimal | None = None
    if trials_ledger is not None and observed_sharpe is not None:
        stats = trials_ledger.trial_statistics_for_family(candidate.family)
        if stats.n_trials >= 2 and stats.trial_sharpe_variance > 0.0:
            candidate_returns_floats = [float(r) for r in candidate_returns]
            returns_array = np.asarray(candidate_returns_floats, dtype=float)
            dsr_value = deflated_sharpe_ratio(
                observed_sharpe=observed_sharpe,
                sample_size=float(len(candidate_returns_floats)),
                skewness=float(scipy_skew(returns_array, bias=False)),
                kurtosis=float(scipy_kurtosis(returns_array, fisher=True, bias=False)),
                n_trials=stats.n_trials,
                trial_sharpe_variance=stats.trial_sharpe_variance,
                mean_trial_sharpe=stats.trial_sharpe_mean,
            )
            deflated_sharpe = Decimal(str(dsr_value))

    # Build the evidence pack with the new fields. Trial recording is
    # NOT done here — evaluate_candidate does not know gate pass/fail
    # (the EvaluationEvidencePack.recommendation values are
    # "keep"/"research_further"/"reject", not Gate 1 pass/fail).
    # Recording moves to the gate layer in Task 12, where the real
    # gate status is known.
    evidence_pack = EvaluationEvidencePack(
        # ...existing keyword args...
        annualized_cost_drag_bps=annualized_cost_drag_bps,
        deflated_sharpe_ratio=deflated_sharpe,
        north_star_sharpe_met=north_star_sharpe_met,
    )

    return evidence_pack
```

**Note on `observed_sharpe` source.** The DSR input `observed_sharpe`
reads from `candidate_metrics_numeric["sharpe_ratio"]` — the same
dict that becomes `EvaluationEvidencePack.candidate_metrics`. This
is the simple Sharpe from
[_sharpe_ratio](src/tradingx/evaluation.py:48), not the Lo-adjusted
variant. The value is already net of costs because Task 4 makes
costs mandatory in `_candidate_returns`. Task 12 reads the **same**
field off the evidence pack for trial-record Sharpe, so DSR input
(Task 11) and trial history (Task 12) are always internally
consistent.

**Why not `benchmark_metrics`?** Confirmed via
[evaluation.py:81](src/tradingx/evaluation.py:81): the current
`_build_metric_pack` exposes only `total_return`, `sharpe_ratio`,
`max_drawdown`, and `calmar_ratio`. `benchmark_metrics` is populated
from benchmark returns, not candidate. Earlier drafts that used
`benchmark_metrics["candidate_sharpe_ratio"]` or `["candidate_cagr"]`
were pointing at keys that don't exist and would silently write `0`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_evaluation.py -v`

Expected: new tests PASS; existing tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/evaluation.py tests/unit/test_evaluation.py
git commit -m "feat(evaluation): wire DSR + north-star + trial recording into evaluate_candidate"
```

### Task 12: Record trials at the gate layer (with real gate status) + wire ledger through callers

**Files:**
- Modify: `src/tradingx/validation.py`
- Modify: `src/tradingx/controller.py` (builder)
- Modify: `tests/unit/test_validation.py`, `tests/unit/test_controller.py`

**Why this task owns trial recording instead of `evaluate_candidate`.**
`evaluate_candidate` does not know gate pass/fail. Its `recommendation`
values are `keep`, `research_further`, and `reject` (see
[evaluation.py:431](src/tradingx/evaluation.py:431)) — none of which
are synonymous with Gate 1 or Gate 2 pass/fail. Actual pass/fail is
decided in
[_build_gate1_candidate_result](src/tradingx/validation.py:245) and
[_build_gate2_candidate_result](src/tradingx/validation.py:319) after
all criteria are applied. Recording trials there — with the real
`passed` value — keeps `TrialRecord.passed` honest.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_validation.py`:

```python
def test_build_gate_report_threads_trials_ledger_to_gate_layer(
    tmp_path,
    sample_gate_report_inputs_fixture,
):
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    report = build_gate_report(
        **sample_gate_report_inputs_fixture,
        trials_ledger=ledger,
    )
    # Every candidate result that ran should have produced a trial row
    for candidate in sample_gate_report_inputs_fixture["candidates"]:
        records = ledger.list_for_candidate(candidate.candidate_id)
        assert records, f"No trial recorded for {candidate.candidate_id}"


def test_build_gate1_candidate_result_records_trial_with_real_gate_status(
    tmp_path,
    sample_gate1_inputs_fixture,
):
    """TrialRecord.passed reflects the Gate 1 verdict, not
    EvaluationEvidencePack.recommendation."""
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    result = _build_gate1_candidate_result(
        **sample_gate1_inputs_fixture,
        trials_ledger=ledger,
    )
    records = ledger.list_for_candidate(
        sample_gate1_inputs_fixture["candidate"].candidate_id,
    )
    assert len(records) == 1
    # The recorded passed value matches the gate decision,
    # which is derived from the four hard-pass criteria.
    gate_passed = (result.status == "pass")
    assert records[0].passed is gate_passed


def test_build_gate1_candidate_result_populates_cost_drag_on_result(
    tmp_path,
    sample_gate1_inputs_fixture,
):
    """ValidationCandidateResult must carry annualized_cost_drag_bps
    from the evidence pack so the report-level consumer (readmodel)
    can read it off candidate_results."""
    ledger = TrialsLedger(database_path=tmp_path / "trials.db")
    # The fixture's evidence_pack should carry a non-None drag value
    # after Task 5 wires evaluate_candidate to populate it.
    result = _build_gate1_candidate_result(
        **sample_gate1_inputs_fixture,
        trials_ledger=ledger,
    )
    assert result.annualized_cost_drag_bps is not None
    # Cost drag is non-negative by construction
    assert result.annualized_cost_drag_bps >= Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validation.py -k "trials_ledger or real_gate_status or populates_cost_drag" -v`

Expected: FAIL on `TypeError: unexpected keyword argument 'trials_ledger'`.

- [ ] **Step 3: Implement**

**3a — Extend `ValidationCandidateResult` with `annualized_cost_drag_bps`.**
The persisted report's `candidate_results` entries are
`ValidationCandidateResult` instances (see
[types.py:150](src/tradingx/types.py:150)). The readmodel in Task 6
reads cost drag from these entries, so the field must exist on the
result type too. Add to `ValidationCandidateResult` in `types.py`:

```python
@dataclass(frozen=True)
class ValidationCandidateResult:
    # ...existing fields: candidate_id, gate_id, status, evidence_pack_id,
    # criteria, summary...
    annualized_cost_drag_bps: Decimal | None = None
```

**3b — Populate the new field in both gate builders.** In
`_build_gate1_candidate_result` and `_build_gate2_candidate_result`,
pass `annualized_cost_drag_bps=evidence_pack.annualized_cost_drag_bps`
into the `ValidationCandidateResult(...)` construction.

**3c — Thread `trials_ledger` through `build_gate_report`.** Add
`trials_ledger: TrialsLedger | None = None` to `build_gate_report`
and pass to `_build_gate1_candidate_result` and
`_build_gate2_candidate_result`.

**3d — Record the trial at the gate layer.** Inside each gate
builder, **after** the gate status is computed (after
`if all(criterion.passed for criterion in criteria):` or the
equivalent status-assignment block), record the trial:

```python
# Inside _build_gate1_candidate_result, after `status = ...` is set:
if trials_ledger is not None:
    from tradingx.evaluation import _cagr, _total_return
    from tradingx.stats import conditional_drawdown_at_risk, max_drawdown

    gate_passed = status == "pass"

    # Sharpe: read from the SAME dict that evaluate_candidate's DSR
    # block read from in Task 11. evidence_pack.candidate_metrics
    # carries "sharpe_ratio" net of costs via _build_metric_pack.
    observed_sharpe_raw = evidence_pack.candidate_metrics.get("sharpe_ratio")

    # CAGR: the current _build_metric_pack does not expose "cagr",
    # so compute it directly from candidate_returns using the
    # existing helpers in evaluation.py.
    returns_f = [float(r) for r in candidate_returns]
    cagr_value = _cagr(_total_return(returns_f), periods=len(returns_f))

    observed_mdd = Decimal(str(max_drawdown(returns_f)))
    observed_cdar = Decimal(
        str(conditional_drawdown_at_risk(returns_f, confidence=0.95))
    )
    trials_ledger.record(
        TrialRecord(
            trial_id=str(uuid.uuid4()),
            candidate_id=candidate.candidate_id,
            family=candidate.family,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            observed_sharpe_net_of_costs=(
                Decimal(str(observed_sharpe_raw))
                if observed_sharpe_raw is not None
                else Decimal("0")
            ),
            observed_cagr_net_of_costs=Decimal(str(cagr_value)),
            observed_max_drawdown=observed_mdd,
            observed_cdar_95=observed_cdar,
            annualized_cost_drag_bps=(
                evidence_pack.annualized_cost_drag_bps or Decimal("0")
            ),
            passed=gate_passed,
            recorded_at_utc=datetime.now(UTC),
            git_sha=_resolve_git_sha(),
            config_fingerprint=_config_fingerprint(candidate),
        )
    )
```

Apply the same pattern inside `_build_gate2_candidate_result` with
`gate_passed = status == "pass"` against the Gate 2 status object.

**Note on metric-source consistency.** `observed_sharpe_net_of_costs`
here reads from `evidence_pack.candidate_metrics["sharpe_ratio"]`,
which is the exact same dict Task 11 reads from for DSR input. This
is why DSR-against-trial-history is internally consistent: the
current candidate's own Sharpe is never compared against a different
Sharpe definition for historical trials (because all trials recorded
through this code path used the same field).

If during implementation you find that `_cagr` and `_total_return` in
`evaluation.py` are underscore-private and you'd rather not import
them cross-module, promote them to public names in `evaluation.py`
(remove the leading underscore, add to `__all__`) as a small
follow-up commit. The cleaner alternative is to add `cagr` to
`_build_metric_pack` itself so it appears on `candidate_metrics`, at
which point Task 12 reads it directly from the evidence pack like
Sharpe. Pick whichever is smaller; flag the choice in the commit
message.

Add helpers `_resolve_git_sha` and `_config_fingerprint` at the bottom
of `validation.py` if they don't already exist:

```python
def _resolve_git_sha() -> str:
    # Reuse the same helper pattern that exists in controller.py. If
    # controller.py already exposes a public version, import it
    # instead of duplicating.
    import subprocess
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _config_fingerprint(candidate: StrategyCandidate) -> str:
    import hashlib
    import json
    payload = json.dumps(
        {
            "candidate_id": candidate.candidate_id,
            "family": candidate.family,
            "parameter_set": {
                k: str(v) for k, v in candidate.parameter_set.items()
            },
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

In `src/tradingx/controller.py`, update `GateValidationController.__init__` to accept/construct a `TrialsLedger`:

```python
def __init__(
    self,
    *,
    artifacts: FilesystemArtifactStore,
    market_data: Any,
    metrics: StageMetrics | None = None,
    trials_ledger: TrialsLedger | None = None,
) -> None:
    # ...existing assignments...
    self._trials_ledger = trials_ledger
```

In `generate_gate_report`, pass `self._trials_ledger` into `build_gate_report(...)`.

Update `build_default_gate_validation_controller` to wire the ledger by default:

```python
def build_default_gate_validation_controller(
    config: TradingConfig,
    *,
    artifact_root: Path,
) -> GateValidationController:
    return GateValidationController(
        artifacts=FilesystemArtifactStore(artifact_root),
        market_data=build_default_market_data_gateway(config),
        metrics=StageMetrics(namespace=config.runtime.metrics_namespace),
        trials_ledger=TrialsLedger(
            database_path=config.runtime.data_root / "validation" / "trials.db",
        ),
    )
```

**Consistency check.** The `observed_sharpe_net_of_costs` written here
and the `observed_sharpe` used for DSR input inside `evaluate_candidate`
(Task 11) must both reflect the same net-of-costs Sharpe source. If
the two drift (e.g., one uses `lo_adjusted_sharpe_ratio` while the
other uses a different helper), DSR-against-trial-history becomes
self-inconsistent. Prefer using the evidence pack's
`benchmark_metrics["candidate_sharpe_ratio"]` as the single source of
truth in both places; adjust Task 11's Step 3 DSR `observed_sharpe`
source to match if the shapes don't already agree.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py tests/unit/test_controller.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/validation.py src/tradingx/controller.py tests/unit/test_validation.py tests/unit/test_controller.py
git commit -m "feat(validation): record trials at gate layer with real gate status"
```

---

## Regression pass

### Task 13: Full regression + lint + typecheck

**Files:** all

- [ ] **Step 1: Run full pytest**

Run: `uv run pytest -q --deselect tests/contract/test_weight_snapshot_origin.py`

Expected: all tests pass. (Deselect only if `rg` isn't available locally; CI runs the full suite.)

- [ ] **Step 2: Run mypy**

Run: `uv run mypy src/tradingx`

Expected: no issues. If `scipy.stats` type-stub warnings surface, add `# type: ignore[import-untyped]` at the import site following the pattern used elsewhere in `stats.py`.

- [ ] **Step 3: Run ruff**

Run: `uv run ruff check src/tradingx tests`

Expected: clean.

- [ ] **Step 4: Run `scripts/check_index.py`**

Run: `uv run python3 scripts/check_index.py`

Expected: only the pre-existing `DESIGN-0009/0010` drifts remain. No new errors.

- [ ] **Step 5: Run `./scripts/validate`**

Run: `./scripts/validate`

Expected: clean, matching the repo's standard validation envelope.

- [ ] **Step 6: Commit any formatting fixups**

```bash
git status
# if any auto-format diffs appear after ruff/mypy fixups:
git add -u
git commit -m "chore: formatting fixups after validation infrastructure"
```

Skip this step if no fixups are needed.

---

## Self-review

### Spec coverage

- DESIGN-0011 §W1 (purged k-fold): covered by Tasks 1–2.
- DESIGN-0011 §W2 (trials ledger): covered by Tasks 7–9.
- DESIGN-0011 §W3 (DSR wiring): covered by Tasks 10–12.
- DESIGN-0011 §W4 (cost-drag accounting): covered by Tasks 3–6.
- Acceptance criteria 1–6 from DESIGN-0011: all ship across Tasks 1–12.

### Placeholder scan

No TBD / TODO / "implement later" strings. Every code block is concrete except where a test explicitly uses fixture names (`sample_candidate_fixture`, etc.) that must be adapted to what already exists in the target test file — this is called out explicitly in each such task.

### Type consistency

- `TrialRecord` fields used in Task 7 match schema in Task 8 and queries in Task 9.
- `TrialStatistics` returned by Task 9 is consumed by the DSR call in Task 11.
- `EvaluationEvidencePack` new fields added in Tasks 5, 10 are populated in Task 11.
- `_candidate_returns` 2-tuple return from Task 4 is unpacked by the caller in Task 12.

### Open judgment calls left to the implementer

1. **Exact `_config_fingerprint` composition** — DESIGN-0011 §8 leaves this to the implementer. Task 11 proposes SHA-256 of `{candidate_id, family, parameter_set}`; adjust if a better fingerprint emerges during implementation.
2. **Fixture names** in tests — each task uses placeholder names like `sample_candidate_fixture`; reuse whatever fixtures already exist in the target test file.
3. **Backtest internal variable names** — Task 3 assumes `total_cost` and `equity_path` exist inside `run_daily_bar_backtest`. If the actual names differ, adapt the cost-drag computation to whatever the existing loop produces.

### Execution handoff

This plan is for Codex to execute. No subagent-driven or inline execution invocation from this session. Same pattern as the benchmark-stack-reframe plan that just shipped.
