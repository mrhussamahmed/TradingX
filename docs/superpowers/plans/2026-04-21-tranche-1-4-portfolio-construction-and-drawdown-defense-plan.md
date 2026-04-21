# Tranche 1.4 Portfolio Construction and Drawdown Defense Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute [DESIGN-0015](../specs/2026-04-21-tranche-1-4-portfolio-construction-and-drawdown-defense-design.md) — combine the two merged sleeves (`TrendSleeve`, `VolManagedBetaSleeve`) into a portfolio with per-sleeve risk budgets + correlation caps + gross/net caps; layer on MDD design throttle (15% proportional), CDaR soft-throttle, and the 25% MDD runtime hard halt wired to the existing operator-clearance flow; add sleeve-termination runtime controller with operator halt + drift-alarm stub + trial-summary Sharpe gate; and wire the marginal-portfolio-contribution criterion as the fifth Gate 1 hard-pass criterion.

**Architecture:** New `src/tradingx/portfolio/` package containing blueprint, construction, throttle, hard-halt controller, and sleeve-runtime controller. No new execution model — portfolio construction composes sleeve target-weight histories into a single combined DataFrame that `run_daily_bar_backtest` executes (single-execution-engine discipline per DESIGN-0015 §P1). Hard halt reuses the existing `_run_clearance_reconciliation` path by calling `service_manager.stop()` first so the stop-then-start sequence is valid. Marginal-contribution evaluation uses a two-pass restructure of `build_gate_report` restricted to the tranche-1 two-sleeve case.

**Tech Stack:** Python 3.11, `Decimal` for money/weights at module boundaries, `pandas` for target-weight DataFrames and equity curves, `pytest` for tests, existing `uv run` invocations, no new runtime dependencies.

---

## Scope

Implements DESIGN-0015 §W1–§W8 in this order:

1. **W1** — `SleeveRiskBudget`, `PortfolioBlueprint` (config primitives).
2. **W2** — `build_portfolio_target_weight_history`, `simulate_portfolio_returns`, `PortfolioSimulationResult`.
3. **W3** — `apply_mdd_design_throttle` (15% proportional linear scale to 25%).
4. **W4** — `apply_cdar_soft_throttle` (soft 0.5 floor when CDaR@95% > threshold).
5. **W5** — `SERVICE_STOP_SUCCESS_STATUSES`, `trigger_hard_halt`, `PortfolioHardHaltController`, `is_portfolio_hard_halted`, entry-gate integration in `RuntimeOpportunityPlanner`.
6. **W6** — `RollingWindowSource`, `SleeveRuntimeConfig`, `SleeveRuntimeController`, operator-halt store surface.
7. **W7** — `marginal_*_delta` fields on evidence pack + candidate result; `evaluate_marginal_portfolio_contribution`; two-pass restructure of `build_gate_report`.
8. **W8** — Integration test, full regression (pytest + mypy + ruff + check_index + validate), GATES-0001 activation, INDEX bump.

Gate 1 pass/fail outcomes against existing fixtures must remain unchanged for non-sleeve candidates. Sleeve-backed candidates (`trend-following-v1`, `vol-target-v1`) now evaluate five criteria instead of four; if either fails the new marginal-contribution criterion on existing data, that is a real Gate 1 failure — the plan ships the machinery, not edge remediation.

## File structure

### New files

- `src/tradingx/portfolio/__init__.py`
- `src/tradingx/portfolio/blueprint.py` — `SleeveRiskBudget`, `PortfolioBlueprint`
- `src/tradingx/portfolio/construction.py` — `build_portfolio_target_weight_history`, `simulate_portfolio_returns`, `PortfolioSimulationResult`
- `src/tradingx/portfolio/throttle.py` — `apply_mdd_design_throttle`, `apply_cdar_soft_throttle`, composition helper
- `src/tradingx/portfolio/hard_halt.py` — `is_portfolio_hard_halted`, `OperatorAlertGatewayProtocol`, `PortfolioHardHaltController`
- `src/tradingx/portfolio/sleeve_runtime.py` — `RollingWindowSource`, `SleeveRuntimeConfig`, `SleeveOperatorHaltStoreProtocol`, `DriftAlarmGatewayProtocol`, `SleeveRuntimeController`
- `tests/unit/test_portfolio_blueprint.py`
- `tests/unit/test_portfolio_construction.py`
- `tests/unit/test_portfolio_throttle.py`
- `tests/unit/test_portfolio_hard_halt.py`
- `tests/unit/test_sleeve_runtime_controller.py`
- `tests/unit/test_marginal_portfolio_contribution.py`
- `tests/integration/test_portfolio_end_to_end.py`

### Modified files

- `src/tradingx/types.py` — `EvaluationEvidencePack` and `ValidationCandidateResult` each gain `marginal_sharpe_delta`, `marginal_calmar_delta`, `marginal_cdar_delta` (`Decimal | None = None`).
- `src/tradingx/evaluation.py` — `evaluate_candidate` accepts optional marginal-delta inputs and forwards them to the evidence pack.
- `src/tradingx/validation.py` — `evaluate_marginal_portfolio_contribution`; two-pass restructure of the Gate 1 branch in `build_gate_report`.
- `src/tradingx/runtime_host.py` — `SERVICE_STOP_SUCCESS_STATUSES` constant; `trigger_hard_halt(reason)` method with full failure-mode handling.
- `src/tradingx/opportunity.py` — `RuntimeOpportunityPlanner` accepts an optional `hard_halt_gate: Callable[[], bool]`; returns an empty selection with `decision_reason='hard_halt_active'` when the gate is True.
- `src/tradingx/operator_control.py` — optional new store keys under `sleeve_halts/` for per-sleeve operator halt records (W6).
- `docs/validation/acceptance_gates.md` — GATES-0001 v1.1.0 → v1.2.0 moves the marginal-portfolio-contribution criterion from "Deferred to tranche 1 hardening" into "Pass criteria (hard-pass, all required)".
- `docs/INDEX.md` — bump GATES-0001 row version and INDEX version.
- `tests/unit/test_types.py` — assertions on the new dataclass fields.
- `tests/unit/test_evaluation.py` — forwarding regression.
- `tests/unit/test_validation.py` — two-pass Gate 1 regression + guardrail for ≠ 2 sleeve-backed candidates.
- `tests/unit/test_runtime_host.py` — halt ordering + failure-mode tests.
- `tests/unit/test_opportunity.py` — entry-gate regression.
- `tests/unit/test_operator_control.py` — sleeve-halt store regression.

### Untouched (intentional)

- `src/tradingx/portfolio_construction.py` — the legacy candidate-weight path remains for `mean-reversion-v1` and the baseline planner. The new `src/tradingx/portfolio/*` package is the home for sleeve-based portfolio work. Consolidation is deferred.
- `src/tradingx/runtime_strategy_registry.py`, `src/tradingx/baseline_runtime_planner.py` — the runtime-planner protocol continues to coexist with `SleeveProtocol` (same rationale as DESIGN-0014).
- `src/tradingx/benchmark_stack.py` — benchmark-stack generation is unchanged.

---

## W1 — Portfolio blueprint + sleeve risk budgets

### Task 1: `SleeveRiskBudget` + `PortfolioBlueprint` + package init

**Files:**
- Create: `src/tradingx/portfolio/__init__.py`
- Create: `src/tradingx/portfolio/blueprint.py`
- Create: `tests/unit/test_portfolio_blueprint.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_portfolio_blueprint.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget


def _sleeve(sid: str, budget: str, corr: str = "0.85") -> SleeveRiskBudget:
    return SleeveRiskBudget(
        sleeve_id=sid,
        budget_fraction_of_equity=Decimal(budget),
        max_correlation_with_other_sleeves=Decimal(corr),
    )


def test_blueprint_accepts_budgets_summing_to_one():
    bp = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(_sleeve("a", "0.5"), _sleeve("b", "0.5")),
    )
    assert sum((sb.budget_fraction_of_equity for sb in bp.sleeve_budgets), Decimal("0")) == Decimal("1")


def test_blueprint_accepts_budgets_summing_below_one():
    bp = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(_sleeve("a", "0.4"), _sleeve("b", "0.4")),
    )
    total = sum((sb.budget_fraction_of_equity for sb in bp.sleeve_budgets), Decimal("0"))
    assert total == Decimal("0.8")  # residual 0.2 is cash per D4


def test_blueprint_rejects_budgets_summing_above_one():
    with pytest.raises(ValueError, match="sleeve budgets sum to"):
        PortfolioBlueprint(
            blueprint_id="bp-1",
            sleeve_budgets=(_sleeve("a", "0.6"), _sleeve("b", "0.6")),
        )


def test_blueprint_defaults_match_adr_0021():
    bp = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(_sleeve("a", "1.0"),),
    )
    assert bp.mdd_design_target == Decimal("0.15")
    assert bp.mdd_hard_halt == Decimal("0.25")
    assert bp.cdar_confidence == Decimal("0.95")
    assert bp.cdar_soft_throttle_threshold == Decimal("0.08")
    assert bp.annualized_turnover_budget == Decimal("3.0")


def test_blueprint_is_frozen():
    import dataclasses

    bp = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(_sleeve("a", "0.5"), _sleeve("b", "0.5")),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        bp.blueprint_id = "bp-2"  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_portfolio_blueprint.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'tradingx.portfolio'`.

- [ ] **Step 3: Implement**

Create `src/tradingx/portfolio/__init__.py`:

```python
"""Portfolio construction + drawdown defense package.

Implements DESIGN-0015: combine per-sleeve target-weight histories
into a single portfolio target-weight DataFrame, apply risk budgets,
throttle exposure on drawdown, and halt at 25% MDD via the existing
operator-clearance flow.
"""

from __future__ import annotations
```

Create `src/tradingx/portfolio/blueprint.py`:

```python
"""Portfolio-level construction parameters per DESIGN-0015 W1."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SleeveRiskBudget:
    """Per-sleeve risk-budget configuration.

    `budget_fraction_of_equity` is the sleeve's allocated share
    of portfolio equity in [0, 1]. Budgets across sleeves sum to
    at most 1.0; the residual is cash per D4 ("cash is a
    consequence, not a goal"). Portfolio-level throttles may
    REDUCE a sleeve's effective allocation further but never
    above 1.0.
    """

    sleeve_id: str
    budget_fraction_of_equity: Decimal
    max_correlation_with_other_sleeves: Decimal


@dataclass(frozen=True)
class PortfolioBlueprint:
    """Portfolio blueprint carrying per-sleeve budgets and the
    throttle / halt thresholds from ADR-0021."""

    blueprint_id: str
    sleeve_budgets: tuple[SleeveRiskBudget, ...]
    max_gross_exposure: Decimal = Decimal("1.0")
    max_net_exposure: Decimal = Decimal("1.0")
    mdd_design_target: Decimal = Decimal("0.15")
    mdd_hard_halt: Decimal = Decimal("0.25")
    cdar_confidence: Decimal = Decimal("0.95")
    cdar_soft_throttle_threshold: Decimal = Decimal("0.08")
    annualized_turnover_budget: Decimal = Decimal("3.0")
    sleeve_three_month_sharpe_floor: Decimal = Decimal("0.0")

    def __post_init__(self) -> None:
        total = sum(
            (sb.budget_fraction_of_equity for sb in self.sleeve_budgets),
            start=Decimal("0"),
        )
        if total > Decimal("1.0"):
            raise ValueError(
                f"sleeve budgets sum to {total}, must be <= 1.0"
            )


__all__ = ("PortfolioBlueprint", "SleeveRiskBudget")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_portfolio_blueprint.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/__init__.py src/tradingx/portfolio/blueprint.py tests/unit/test_portfolio_blueprint.py
git commit -m "feat(portfolio): add PortfolioBlueprint and SleeveRiskBudget"
```

---

## W2 — Portfolio target-weight construction

### Task 2: `build_portfolio_target_weight_history`

**Files:**
- Create: `src/tradingx/portfolio/construction.py`
- Create: `tests/unit/test_portfolio_construction.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_portfolio_construction.py`:

```python
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from tradingx.features.regime import classify_regime
from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.construction import build_portfolio_target_weight_history
from tradingx.sleeves.trend import TrendSleeve
from tradingx.sleeves.vol_managed_beta import VolManagedBetaSleeve
from tradingx.types import RegimeSnapshot


def _bars(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed=seed)
    returns = rng.normal(scale=0.01, size=n)
    closes = 100.0 * np.cumprod(1.0 + returns)
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": [1e7] * n,
        },
        index=dates,
    )


def _regimes(
    bars: pd.DataFrame,
    force_state: str | None = None,
) -> dict[date, RegimeSnapshot]:
    closes = bars["close"].astype(float)
    sma = closes.rolling(200).mean()
    regimes: dict[date, RegimeSnapshot] = {}
    for ts in bars.index:
        obs = ts.date()
        if pd.isna(sma.loc[ts]):
            continue
        if force_state is not None:
            regimes[obs] = RegimeSnapshot(
                observation_date=obs,
                regime=force_state,
                above_sma_200=True,
                vix_elevated=False,
                vix_stressed=False,
                yield_curve_inverted=False,
                spy_close=Decimal(str(float(closes.loc[ts]))),
                spy_sma_200=Decimal(str(float(sma.loc[ts]))),
                vix_close=None,
                yield_curve_spread_bps=None,
            )
        else:
            regimes[obs] = classify_regime(
                observation_date=obs,
                spy_close=Decimal(str(float(closes.loc[ts]))),
                spy_sma_200=Decimal(str(float(sma.loc[ts]))),
                vix_close=None,
                yield_curve_spread_bps=None,
            )
    return regimes


def test_combines_two_sleeves_with_equal_budgets():
    spy_bars = _bars(400)
    qqq_bars = _bars(400, seed=11)
    regimes = _regimes(spy_bars)
    bp = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    target_weights = build_portfolio_target_weight_history(
        sleeves,
        blueprint=bp,
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )
    assert isinstance(target_weights, pd.DataFrame)
    assert set(target_weights.columns) == {"SPY", "QQQ"}
    assert target_weights.shape[0] == spy_bars.shape[0]
    # Gross exposure never exceeds 1.0 in any row.
    assert float(target_weights.sum(axis=1).max()) <= 1.0 + 1e-9


def test_stressed_regime_zeros_vol_managed_beta_and_does_not_redistribute():
    spy_bars = _bars(300)
    qqq_bars = _bars(300, seed=13)
    regimes = _regimes(spy_bars, force_state="stressed")
    bp = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    target_weights = build_portfolio_target_weight_history(
        sleeves,
        blueprint=bp,
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )
    # Stressed regime: vol-managed beta zeroes (0% exposure per
    # DESIGN-0013 + D4); its 0.5 budget becomes cash, NOT
    # redistributed to trend. Trend also zeroes because its
    # exposure floor is also 0 in stressed (per DESIGN-0014).
    # Result: every row is all-zero weights; residual is cash.
    latest = target_weights.iloc[-1]
    assert float(latest["SPY"]) == 0.0
    assert float(latest["QQQ"]) == 0.0


def test_gross_exposure_cap_scales_uniformly_when_exceeded():
    # Force a scenario where summed sleeve contributions would
    # exceed max_gross_exposure; verify uniform scaling.
    # Uses monkeypatch / dummy sleeves to avoid depending on
    # the fitted signal values.
    ...  # See Step 3 for dummy-sleeve helper.


def test_output_dataframe_passes_backtest_validation():
    from tradingx.backtest import _validate_inputs  # type: ignore[attr-defined]

    spy_bars = _bars(300)
    qqq_bars = _bars(300, seed=17)
    regimes = _regimes(spy_bars)
    bp = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    target_weights = build_portfolio_target_weight_history(
        sleeves,
        blueprint=bp,
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )
    # Must match run_daily_bar_backtest's input validation:
    # columns match bars_by_symbol keys; aligned index.
    _validate_inputs({"SPY": spy_bars, "QQQ": qqq_bars}, target_weights)
```

For the uniform-scaling test, use a dummy sleeve defined within the test module:

```python
from dataclasses import dataclass

from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import SleeveContext, SleeveTrade


@dataclass(frozen=True)
class _ConstantWeightSleeve:
    sleeve_id: str
    family: str = "dummy"
    allowed_instruments: tuple[str, ...] = ("SPY",)
    target_weight: Decimal = Decimal("1.0")

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        return (
            SleeveTrade(
                sleeve_id=self.sleeve_id,
                symbol="SPY",
                side="buy",
                target_weight_of_sleeve_budget=self.target_weight,
                rationale="constant",
                regime=context.regime.regime,
            ),
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_portfolio_construction.py -v`

Expected: FAIL on `ImportError` (the module does not exist yet).

- [ ] **Step 3: Implement**

Create `src/tradingx/portfolio/construction.py`:

```python
"""Portfolio target-weight construction per DESIGN-0015 W2."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.sleeves.base import SleeveProtocol
from tradingx.sleeves.evaluation import build_sleeve_target_weight_history
from tradingx.types import RegimeSnapshot


def build_portfolio_target_weight_history(
    sleeves: tuple[SleeveProtocol, ...],
    *,
    blueprint: PortfolioBlueprint,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
) -> pd.DataFrame:
    """Combine per-sleeve target-weight histories into a single
    portfolio target-weight DataFrame.

    Per DESIGN-0015 §W2:
    1. For each sleeve, call build_sleeve_target_weight_history
       to get W_s (dates x sleeve.allowed_instruments).
    2. For each date and each symbol in the union of
       allowed_instruments, sum
           portfolio_weight[symbol] = sum over s of
               (W_s[symbol] * budget_fraction_s)
    3. Apply the correlation cap: for symbols held by >=2
       sleeves, the combined weight is capped at
       min(max_gross_exposure,
           strictest_sleeve.max_correlation_with_other_sleeves
           * max_gross_exposure).
    4. Cap the row at max_gross_exposure by uniform scaling
       across all columns.
    5. Net-exposure cap is symbolically enforced (no-op for
       long-only tranche-1 sleeves).

    Per D4: a sleeve that produces zero weights (regime
    stressed) does NOT have its budget redistributed to other
    sleeves — residual becomes cash.
    """
    if not sleeves:
        raise ValueError("sleeves must not be empty")

    budget_by_sleeve_id = {
        sb.sleeve_id: sb for sb in blueprint.sleeve_budgets
    }
    missing = tuple(
        s.sleeve_id for s in sleeves if s.sleeve_id not in budget_by_sleeve_id
    )
    if missing:
        raise ValueError(
            f"sleeves {missing!r} missing from blueprint.sleeve_budgets"
        )

    # Build per-sleeve histories.
    sleeve_frames: list[tuple[SleeveProtocol, SleeveRiskBudget, pd.DataFrame]] = []
    union_symbols: set[str] = set()
    for sleeve in sleeves:
        frame = build_sleeve_target_weight_history(
            sleeve,
            bars_by_symbol=bars_by_symbol,
            regime_snapshots_by_date=regime_snapshots_by_date,
            sleeve_budget_equity=Decimal("1.0"),  # unit budget; scaling below
        )
        sleeve_frames.append((sleeve, budget_by_sleeve_id[sleeve.sleeve_id], frame))
        union_symbols.update(str(c) for c in frame.columns)

    # Reference index (use first sleeve's frame index; all share it
    # because build_sleeve_target_weight_history drives from
    # bars_by_symbol's index).
    reference_index = sleeve_frames[0][2].index

    columns = sorted(union_symbols)
    combined = pd.DataFrame(0.0, index=reference_index, columns=columns, dtype=float)

    for _sleeve, budget, frame in sleeve_frames:
        budget_f = float(budget.budget_fraction_of_equity)
        aligned = frame.reindex(columns=columns, fill_value=0.0)
        combined = combined + aligned * budget_f

    # Correlation cap per symbol.
    multi_holder_symbols = _symbols_held_by_multiple_sleeves(sleeve_frames)
    if multi_holder_symbols:
        strictest = min(
            (
                float(sb.max_correlation_with_other_sleeves)
                for _s, sb, _f in sleeve_frames
            ),
            default=1.0,
        )
        cap = float(blueprint.max_gross_exposure) * strictest
        for symbol in multi_holder_symbols:
            # Scale contributions down to cap where exceeded.
            mask = combined[symbol] > cap
            if mask.any():
                combined.loc[mask, symbol] = cap

    # Row-level gross exposure cap.
    row_sums = combined.sum(axis=1)
    max_gross = float(blueprint.max_gross_exposure)
    over = row_sums > max_gross
    if over.any():
        scale = (max_gross / row_sums.where(over, 1.0)).astype(float)
        combined.loc[over, :] = combined.loc[over, :].multiply(scale[over], axis=0)

    return combined


def _symbols_held_by_multiple_sleeves(
    sleeve_frames: list[tuple[SleeveProtocol, SleeveRiskBudget, pd.DataFrame]],
) -> set[str]:
    counts: dict[str, int] = {}
    for _s, _b, frame in sleeve_frames:
        for col in frame.columns:
            counts[str(col)] = counts.get(str(col), 0) + 1
    return {sym for sym, n in counts.items() if n >= 2}


__all__ = ("build_portfolio_target_weight_history",)
```

**Design note — dimensional correctness.** `budget_fraction_of_equity` is dimensionless (a fraction of portfolio equity). Per-sleeve frames are in sleeve-budget-fraction space (each sleeve allocated a unit budget of 1.0 in the inner `build_sleeve_target_weight_history` call). Multiplying by `budget_f` moves the sleeve's weights into portfolio-equity space. The combined DataFrame therefore has values in `[0, max_gross_exposure]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_portfolio_construction.py -v`

Expected: all pass. The `test_gross_exposure_cap_scales_uniformly_when_exceeded` test uses two `_ConstantWeightSleeve` instances each claiming 100% SPY with budgets summing to 1.0 (so combined SPY = 1.0, at the cap) and a dummy third-sleeve variant (for cap testing) with total sums > 1.0 to exercise the scaling path — write the variant as an additional test if the two-sleeve case cannot trigger it naturally.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/construction.py tests/unit/test_portfolio_construction.py
git commit -m "feat(portfolio): add build_portfolio_target_weight_history"
```

### Task 3: `simulate_portfolio_returns` + `PortfolioSimulationResult`

**Files:**
- Modify: `src/tradingx/portfolio/construction.py`
- Modify: `tests/unit/test_portfolio_construction.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_portfolio_construction.py`:

```python
def test_simulate_portfolio_returns_delegates_to_run_daily_bar_backtest():
    """Prove the single-execution-engine guarantee: simulating
    a portfolio produces identical returns and cost drag to
    calling run_daily_bar_backtest directly on the combined
    target-weight frame."""
    from tradingx.backtest import run_daily_bar_backtest
    from tradingx.costs import CostModelConfig
    from tradingx.portfolio.construction import (
        PortfolioSimulationResult,
        simulate_portfolio_returns,
    )

    spy_bars = _bars(300)
    qqq_bars = _bars(300, seed=23)
    regimes = _regimes(spy_bars)
    bp = PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    result = simulate_portfolio_returns(
        sleeves,
        blueprint=bp,
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )
    assert isinstance(result, PortfolioSimulationResult)

    # Rebuild the combined frame and run_daily_bar_backtest directly.
    combined = build_portfolio_target_weight_history(
        sleeves,
        blueprint=bp,
        bars_by_symbol={"SPY": spy_bars, "QQQ": qqq_bars},
        regime_snapshots_by_date=regimes,
    )
    direct = run_daily_bar_backtest(
        {"SPY": spy_bars, "QQQ": qqq_bars},
        target_weights=combined,
        cost_model_config=CostModelConfig(),
    )
    # Returns must match element-wise.
    assert list(result.backtest_result.portfolio_returns) == list(direct.portfolio_returns)
    assert result.backtest_result.annualized_cost_drag_bps == direct.annualized_cost_drag_bps
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_portfolio_construction.py -k simulate -v`

Expected: FAIL on `ImportError` for `PortfolioSimulationResult` / `simulate_portfolio_returns`.

- [ ] **Step 3: Implement**

Append to `src/tradingx/portfolio/construction.py`:

```python
from dataclasses import dataclass

from tradingx.backtest import DailyBarBacktestResult, run_daily_bar_backtest
from tradingx.costs import CostModelConfig


@dataclass(frozen=True)
class PortfolioSimulationResult:
    """Thin wrapper over DailyBarBacktestResult carrying the
    combined target-weight DataFrame and any throttle sidecar.

    Per DESIGN-0015 §P1: simulate_portfolio_returns delegates
    fill, cost, and P&L mechanics to run_daily_bar_backtest.
    This result type holds the engine's output plus the input
    DataFrame for attribution. A future work item (1.4 W3/W4)
    adds the throttle_scale_series sidecar; the field is
    present on the dataclass from day one to avoid churn.
    """

    backtest_result: DailyBarBacktestResult
    combined_target_weights: pd.DataFrame
    throttle_scale_series: pd.Series | None = None


def simulate_portfolio_returns(
    sleeves: tuple[SleeveProtocol, ...],
    *,
    blueprint: PortfolioBlueprint,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    cost_model_config: CostModelConfig | None = None,
) -> PortfolioSimulationResult:
    """Build the combined target-weight DataFrame and hand it to
    run_daily_bar_backtest. Returns PortfolioSimulationResult.

    Per DESIGN-0015 §P1: this function does NOT simulate fills,
    costs, or P&L — those belong to run_daily_bar_backtest. If
    the execution model changes in backtest.py, portfolio
    simulation tracks automatically.
    """
    combined = build_portfolio_target_weight_history(
        sleeves,
        blueprint=blueprint,
        bars_by_symbol=bars_by_symbol,
        regime_snapshots_by_date=regime_snapshots_by_date,
    )
    traded_symbols = tuple(str(col) for col in combined.columns)
    result = run_daily_bar_backtest(
        {symbol: bars_by_symbol[symbol] for symbol in traded_symbols},
        target_weights=combined,
        cost_model_config=cost_model_config or CostModelConfig(),
    )
    return PortfolioSimulationResult(
        backtest_result=result,
        combined_target_weights=combined,
        throttle_scale_series=None,
    )
```

Update `__all__` in `construction.py`:

```python
__all__ = (
    "PortfolioSimulationResult",
    "build_portfolio_target_weight_history",
    "simulate_portfolio_returns",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_portfolio_construction.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/construction.py tests/unit/test_portfolio_construction.py
git commit -m "feat(portfolio): add simulate_portfolio_returns thin wrapper over run_daily_bar_backtest"
```

---

## W3 — MDD design throttle

### Task 4: `apply_mdd_design_throttle`

**Files:**
- Create: `src/tradingx/portfolio/throttle.py`
- Create: `tests/unit/test_portfolio_throttle.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_portfolio_throttle.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest

from tranche_one_four_fixtures import single_symbol_target_weights  # placeholder; match project fixture style

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.throttle import apply_mdd_design_throttle


def _blueprint() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="s",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
        ),
    )


def _weights(n: int = 5) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({"SPY": [1.0] * n}, index=dates, dtype=float)


def test_no_throttle_below_design_target():
    weights = _weights(5)
    dd = pd.Series([0.05, 0.08, 0.10, 0.12, 0.14], index=weights.index)
    throttled, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=dd,
        blueprint=_blueprint(),
    )
    assert list(scale) == [1.0, 1.0, 1.0, 1.0, 1.0]
    pd.testing.assert_frame_equal(throttled, weights)


def test_scale_at_design_boundary_is_one():
    weights = _weights(1)
    dd = pd.Series([0.15], index=weights.index)
    _, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=dd,
        blueprint=_blueprint(),
    )
    assert list(scale) == [1.0]


def test_scale_midpoint_is_one_half():
    weights = _weights(1)
    dd = pd.Series([0.20], index=weights.index)
    _, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=dd,
        blueprint=_blueprint(),
    )
    assert list(scale) == pytest.approx([0.5])


def test_scale_at_halt_boundary_is_zero():
    weights = _weights(1)
    dd = pd.Series([0.25], index=weights.index)
    _, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=dd,
        blueprint=_blueprint(),
    )
    assert list(scale) == [0.0]


def test_scale_clamps_to_zero_above_halt():
    weights = _weights(1)
    dd = pd.Series([0.30], index=weights.index)
    _, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=dd,
        blueprint=_blueprint(),
    )
    assert list(scale) == [0.0]


def test_scale_applied_uniformly_across_symbols():
    dates = pd.date_range("2020-01-01", periods=2, freq="B", tz="UTC")
    weights = pd.DataFrame({"SPY": [0.6, 0.6], "QQQ": [0.4, 0.4]}, index=dates, dtype=float)
    dd = pd.Series([0.10, 0.20], index=dates)
    throttled, scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=dd,
        blueprint=_blueprint(),
    )
    assert list(scale) == pytest.approx([1.0, 0.5])
    assert float(throttled.iloc[1]["SPY"]) == pytest.approx(0.3)
    assert float(throttled.iloc[1]["QQQ"]) == pytest.approx(0.2)
```

Note: remove the `from tranche_one_four_fixtures import ...` import — that was a placeholder; the module-local `_weights` helper is what the tests actually use. Leave a comment explaining that test fixtures in this file are self-contained because the throttle is a pure function requiring no global setup.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_portfolio_throttle.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/portfolio/throttle.py`:

```python
"""Drawdown throttle helpers per DESIGN-0015 W3 + W4."""

from __future__ import annotations

from decimal import Decimal
from typing import Final

import pandas as pd  # type: ignore[import-untyped]

from tradingx.portfolio.blueprint import PortfolioBlueprint


MDD_DESIGN_THROTTLE_FLOOR: Final[Decimal] = Decimal("0.0")


def apply_mdd_design_throttle(
    *,
    target_weights: pd.DataFrame,
    trailing_drawdown_series: pd.Series,
    blueprint: PortfolioBlueprint,
) -> tuple[pd.DataFrame, pd.Series]:
    """Apply a linear proportional throttle to portfolio weights
    based on trailing drawdown.

    Scale rule:
        dd <= design:           scale = 1.0
        design < dd < halt:     scale = (halt - dd) / (halt - design)
        dd >= halt:             scale = 0.0

    where design = blueprint.mdd_design_target (default 0.15)
    and halt = blueprint.mdd_hard_halt (default 0.25).

    trailing_drawdown_series carries POSITIVE fractions (e.g.,
    0.17 for a -17% drawdown), aligned with target_weights.index.

    Returns (throttled_weights, scale_series). Pure function; no
    I/O or side effects.
    """
    if not target_weights.index.equals(trailing_drawdown_series.index):
        raise ValueError(
            "trailing_drawdown_series must share target_weights index"
        )
    design = float(blueprint.mdd_design_target)
    halt = float(blueprint.mdd_hard_halt)
    if halt <= design:
        raise ValueError(
            "PortfolioBlueprint.mdd_hard_halt must exceed mdd_design_target"
        )
    dd = trailing_drawdown_series.astype(float).clip(lower=0.0)
    scale = ((halt - dd) / (halt - design)).clip(lower=0.0, upper=1.0)
    # At or below design: pass-through (scale=1.0).
    scale = scale.where(dd > design, 1.0)
    throttled = target_weights.multiply(scale, axis=0)
    return throttled, scale


__all__ = (
    "MDD_DESIGN_THROTTLE_FLOOR",
    "apply_mdd_design_throttle",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_portfolio_throttle.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/throttle.py tests/unit/test_portfolio_throttle.py
git commit -m "feat(portfolio): add apply_mdd_design_throttle (15% proportional)"
```

---

## W4 — CDaR soft-throttle

### Task 5: `apply_cdar_soft_throttle` + composition

**Files:**
- Modify: `src/tradingx/portfolio/throttle.py`
- Modify: `tests/unit/test_portfolio_throttle.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_portfolio_throttle.py`:

```python
def test_cdar_no_throttle_below_threshold():
    weights = _weights(3)
    cdar = pd.Series([0.05, 0.06, 0.07], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == [1.0, 1.0, 1.0]


def test_cdar_at_threshold_boundary_is_one():
    weights = _weights(1)
    cdar = pd.Series([0.08], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == [1.0]


def test_cdar_midpoint_is_three_quarters():
    # threshold=0.08, 2*threshold=0.16, halfway=0.12 → scale=0.75
    weights = _weights(1)
    cdar = pd.Series([0.12], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == pytest.approx([0.75])


def test_cdar_at_two_threshold_floor_half():
    weights = _weights(1)
    cdar = pd.Series([0.16], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == [0.5]


def test_cdar_above_two_threshold_clamped_to_half():
    weights = _weights(1)
    cdar = pd.Series([0.25], index=weights.index)
    _, scale = apply_cdar_soft_throttle(
        target_weights=weights,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(scale) == [0.5]


def test_mdd_and_cdar_compose_multiplicatively():
    weights = _weights(1)
    dd = pd.Series([0.20], index=weights.index)  # mdd scale=0.5
    cdar = pd.Series([0.12], index=weights.index)  # cdar scale=0.75
    mdd_throttled, mdd_scale = apply_mdd_design_throttle(
        target_weights=weights,
        trailing_drawdown_series=dd,
        blueprint=_blueprint(),
    )
    final_throttled, cdar_scale = apply_cdar_soft_throttle(
        target_weights=mdd_throttled,
        trailing_cdar_series=cdar,
        blueprint=_blueprint(),
    )
    assert list(mdd_scale * cdar_scale) == pytest.approx([0.375])
    assert float(final_throttled.iloc[0]["SPY"]) == pytest.approx(0.375)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_portfolio_throttle.py -k cdar -v`

Expected: FAIL on `ImportError` for `apply_cdar_soft_throttle`.

- [ ] **Step 3: Implement**

Append to `src/tradingx/portfolio/throttle.py`:

```python
CDAR_SOFT_THROTTLE_FLOOR: Final[Decimal] = Decimal("0.5")


def apply_cdar_soft_throttle(
    *,
    target_weights: pd.DataFrame,
    trailing_cdar_series: pd.Series,
    blueprint: PortfolioBlueprint,
) -> tuple[pd.DataFrame, pd.Series]:
    """Soft throttle driven by trailing CDaR@95%.

    Scale rule:
        cdar <= threshold:           scale = 1.0
        threshold < cdar < 2*thr:    scale linearly from 1.0 to 0.5
        cdar >= 2 * threshold:       scale = 0.5

    Floor is 0.5 (by design). This is a SOFT throttle; the hard
    MDD halt remains the actual stop mechanism.

    Pure function. Composes multiplicatively with
    apply_mdd_design_throttle at the caller.
    """
    if not target_weights.index.equals(trailing_cdar_series.index):
        raise ValueError(
            "trailing_cdar_series must share target_weights index"
        )
    threshold = float(blueprint.cdar_soft_throttle_threshold)
    cdar = trailing_cdar_series.astype(float).clip(lower=0.0)
    # Linear from (threshold, 1.0) to (2*threshold, 0.5).
    linear = 1.0 - 0.5 * ((cdar - threshold) / threshold)
    scale = linear.clip(lower=0.5, upper=1.0)
    scale = scale.where(cdar > threshold, 1.0)
    throttled = target_weights.multiply(scale, axis=0)
    return throttled, scale
```

Update `__all__`:

```python
__all__ = (
    "CDAR_SOFT_THROTTLE_FLOOR",
    "MDD_DESIGN_THROTTLE_FLOOR",
    "apply_cdar_soft_throttle",
    "apply_mdd_design_throttle",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_portfolio_throttle.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/throttle.py tests/unit/test_portfolio_throttle.py
git commit -m "feat(portfolio): add apply_cdar_soft_throttle composing with MDD throttle"
```

---

## W5 — 25% MDD runtime hard halt

### Task 6: `SERVICE_STOP_SUCCESS_STATUSES` + `trigger_hard_halt` on runtime host

**Files:**
- Modify: `src/tradingx/runtime_host.py`
- Modify: `tests/unit/test_runtime_host.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_runtime_host.py` (match the existing fixture style; replace any placeholder fixture names with the real ones in the file):

```python
def test_trigger_hard_halt_stops_service_then_transitions_state(runtime_host_fixture):
    # Arrange: runtime_host_fixture provides a manager + mock
    # service manager where service_manager.stop() returns
    # WebActionResult(status="accepted"). The fixture should
    # record the order of calls (stop, then _set_state).
    host = runtime_host_fixture.host
    service_manager = runtime_host_fixture.service_manager

    result = host.trigger_hard_halt(reason="portfolio_hard_halt: trailing MDD 26%")

    assert result.status == "accepted"
    assert service_manager.stop_called_before_state_transition is True
    assert host.get_state().status == "recovery_required"
    assert "portfolio_hard_halt" in host.get_state().last_error


def test_trigger_hard_halt_raises_is_recorded_as_halted(runtime_host_fixture_with_raising_stop):
    host = runtime_host_fixture_with_raising_stop.host

    result = host.trigger_hard_halt(reason="test")

    assert result.status == "error"
    assert host.get_state().status == "halted"
    assert "test" in host.get_state().last_error


def test_trigger_hard_halt_non_success_status_is_recorded_as_halted(
    runtime_host_fixture_with_blocked_stop,
):
    host = runtime_host_fixture_with_blocked_stop.host

    result = host.trigger_hard_halt(reason="test")

    # Per DESIGN-0015 W5 round-2 amendment: non-success stop
    # statuses (blocked, error, ...) are halt failures; state
    # transitions to halted, not recovery_required.
    assert result.status == "error"
    assert host.get_state().status == "halted"


def test_trigger_hard_halt_is_idempotent_when_already_recovery_required(runtime_host_fixture):
    host = runtime_host_fixture.host
    host.trigger_hard_halt(reason="first")
    service_manager = runtime_host_fixture.service_manager
    service_manager.reset_call_log()

    result = host.trigger_hard_halt(reason="second")

    assert result.status == "noop"
    assert service_manager.stop_call_count == 0
```

Fixtures `runtime_host_fixture`, `runtime_host_fixture_with_raising_stop`, and `runtime_host_fixture_with_blocked_stop` should follow the existing test-file's fixture factory pattern. If that style uses `pytest.fixture` helpers local to the test file, define them in the same way; the key behaviors are:

- `runtime_host_fixture`: `service_manager.stop()` returns `WebActionResult(status="accepted", ...)`; records call order.
- `runtime_host_fixture_with_raising_stop`: `service_manager.stop()` raises `RuntimeError("boom")`.
- `runtime_host_fixture_with_blocked_stop`: `service_manager.stop()` returns `WebActionResult(status="blocked", message="locked", ...)`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_runtime_host.py -k trigger_hard_halt -v`

Expected: FAIL on `AttributeError: 'LocalRuntimeHostManager' object has no attribute 'trigger_hard_halt'`.

- [ ] **Step 3: Implement**

In `src/tradingx/runtime_host.py`:

- Add `Final` to the existing typing import (`from typing import Any, Final, Protocol, cast`).
- Add the module-level constant near the other constants:

```python
SERVICE_STOP_SUCCESS_STATUSES: Final[frozenset[str]] = frozenset(
    {"accepted", "completed"}
)
```

- Add the method to `LocalRuntimeHostManager`:

```python
def trigger_hard_halt(self, *, reason: str) -> WebActionResult:
    """Halt the runtime because a hard risk limit was breached.

    Ordering is load-bearing:
    1. self._service_manager.stop() — actually stops the
       trading loop. A non-success WebActionResult (status not
       in SERVICE_STOP_SUCCESS_STATUSES) or a raise is treated
       as a halt failure; state transitions to `halted`.
    2. If stop succeeded, set state to `recovery_required`
       with the halt reason on `last_error`.

    _pending_start_request is preserved from the original
    start() call, so the subsequent request_clearance() takes
    _run_clearance_reconciliation through service_manager.start
    (stop-then-start is a valid service-manager operation).

    Idempotent: calling when already `recovery_required` is a
    no-op.

    Returns WebActionResult with status=accepted on success;
    status=noop on idempotent call; status=error on stop
    failure.
    """
    with self._lock:
        if self._state.status == "recovery_required":
            return WebActionResult(
                action_id=f"action-{uuid.uuid4()}",
                action_type="runtime_host_hard_halt",
                status="noop",
                message="Runtime host already in recovery_required.",
                evidence_refs=(),
            )
        try:
            stop_result = self._service_manager.stop()
        except Exception as exc:
            self._set_state(
                status="halted",
                status_reason="Hard halt requested; service stop raised.",
                last_error=f"{reason}; service stop error: {exc}",
            )
            return WebActionResult(
                action_id=f"action-{uuid.uuid4()}",
                action_type="runtime_host_hard_halt",
                status="error",
                message=f"Hard halt service stop raised: {exc}",
                evidence_refs=(),
            )
        if stop_result.status not in SERVICE_STOP_SUCCESS_STATUSES:
            self._set_state(
                status="halted",
                status_reason=(
                    "Hard halt requested; service stop returned "
                    f"{stop_result.status!r}."
                ),
                last_error=(
                    f"{reason}; service stop returned "
                    f"{stop_result.status}: {stop_result.message}"
                ),
            )
            return WebActionResult(
                action_id=f"action-{uuid.uuid4()}",
                action_type="runtime_host_hard_halt",
                status="error",
                message=(
                    f"Hard halt service stop did not succeed "
                    f"({stop_result.status}): {stop_result.message}"
                ),
                evidence_refs=stop_result.evidence_refs,
            )
        self._set_state(
            status="recovery_required",
            status_reason=(
                f"Hard halt triggered: {reason}. "
                "Service stopped; operator clearance required."
            ),
            last_error=reason,
        )
    return WebActionResult(
        action_id=f"action-{uuid.uuid4()}",
        action_type="runtime_host_hard_halt",
        status="accepted",
        message=f"Hard halt: {reason}",
        evidence_refs=stop_result.evidence_refs,
    )
```

Extend `__all__` if it exists at the bottom of the module. If the module does not currently export a constant, just leave `SERVICE_STOP_SUCCESS_STATUSES` module-public (no leading underscore).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_runtime_host.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/runtime_host.py tests/unit/test_runtime_host.py
git commit -m "feat(runtime_host): add trigger_hard_halt with SERVICE_STOP_SUCCESS_STATUSES check"
```

### Task 7: `is_portfolio_hard_halted` helper + `PortfolioHardHaltController`

**Files:**
- Create: `src/tradingx/portfolio/hard_halt.py`
- Create: `tests/unit/test_portfolio_hard_halt.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_portfolio_hard_halt.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.hard_halt import (
    PortfolioHardHaltController,
    is_portfolio_hard_halted,
)
from tradingx.types import OperatorAlert, WebActionResult


HALT_REASON_PREFIX = "portfolio_hard_halt"


def _blueprint() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="bp-1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="s",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
        ),
    )


class _FakeRuntimeHost:
    def __init__(self) -> None:
        self.halt_reasons: list[str] = []

    def trigger_hard_halt(self, *, reason: str) -> WebActionResult:
        self.halt_reasons.append(reason)
        return WebActionResult(
            action_id="action-test",
            action_type="runtime_host_hard_halt",
            status="accepted",
            message="ok",
            evidence_refs=(),
        )


class _FakeAlertGateway:
    def __init__(self) -> None:
        self.published: list[OperatorAlert] = []

    def publish(self, alert: OperatorAlert) -> None:
        self.published.append(alert)


def _equity_curve(peak: float, trough: float) -> pd.Series:
    dates = pd.date_range("2020-01-01", periods=2, freq="B", tz="UTC")
    return pd.Series([peak, trough], index=dates, dtype=float)


def test_controller_no_halt_below_25pct_drawdown():
    host = _FakeRuntimeHost()
    alerts = _FakeAlertGateway()
    controller = PortfolioHardHaltController(
        runtime_host=host,
        alert_gateway=alerts,
        blueprint=_blueprint(),
    )
    result = controller.check(equity_curve=_equity_curve(1.0, 0.80))  # -20%
    assert result is None
    assert host.halt_reasons == []
    assert alerts.published == []


def test_controller_triggers_halt_at_25pct_drawdown():
    host = _FakeRuntimeHost()
    alerts = _FakeAlertGateway()
    controller = PortfolioHardHaltController(
        runtime_host=host,
        alert_gateway=alerts,
        blueprint=_blueprint(),
    )
    result = controller.check(equity_curve=_equity_curve(1.0, 0.75))  # -25%
    assert result is not None
    assert result.status == "accepted"
    assert len(host.halt_reasons) == 1
    assert host.halt_reasons[0].startswith(HALT_REASON_PREFIX)
    assert len(alerts.published) == 1
    assert alerts.published[0].severity == "critical"
    assert alerts.published[0].category == "portfolio_hard_halt"


def test_controller_is_latched():
    host = _FakeRuntimeHost()
    alerts = _FakeAlertGateway()
    controller = PortfolioHardHaltController(
        runtime_host=host,
        alert_gateway=alerts,
        blueprint=_blueprint(),
    )
    controller.check(equity_curve=_equity_curve(1.0, 0.70))  # -30%
    # Second call with same breach should be a no-op.
    second = controller.check(equity_curve=_equity_curve(1.0, 0.70))
    assert second is None
    assert len(host.halt_reasons) == 1


def test_controller_reset_clears_latch():
    host = _FakeRuntimeHost()
    alerts = _FakeAlertGateway()
    controller = PortfolioHardHaltController(
        runtime_host=host,
        alert_gateway=alerts,
        blueprint=_blueprint(),
    )
    controller.check(equity_curve=_equity_curve(1.0, 0.70))
    controller.reset()
    # After reset, a below-threshold check is fine.
    result = controller.check(equity_curve=_equity_curve(1.0, 0.90))  # -10%
    assert result is None


def test_is_portfolio_hard_halted_true_when_state_file_has_halt_prefix(tmp_path: Path):
    # Arrange: write a runtime host state artifact with the
    # halt prefix on last_error.
    state_dir = tmp_path / "operator"
    state_dir.mkdir()
    (state_dir / "runtime_host_state.json").write_text(
        '{"status": "recovery_required",'
        f' "last_error": "{HALT_REASON_PREFIX}: trailing MDD 0.26",'
        ' "status_reason": "Hard halt"}',
        encoding="utf-8",
    )
    # Act
    result = is_portfolio_hard_halted(state_dir)
    # Assert
    assert result is True


def test_is_portfolio_hard_halted_false_for_reconciliation_halt(tmp_path: Path):
    state_dir = tmp_path / "operator"
    state_dir.mkdir()
    (state_dir / "runtime_host_state.json").write_text(
        '{"status": "recovery_required",'
        ' "last_error": "Reconciliation divergence detected",'
        ' "status_reason": "Reconciliation"}',
        encoding="utf-8",
    )
    assert is_portfolio_hard_halted(state_dir) is False


def test_is_portfolio_hard_halted_false_when_nominal(tmp_path: Path):
    state_dir = tmp_path / "operator"
    state_dir.mkdir()
    (state_dir / "runtime_host_state.json").write_text(
        '{"status": "nominal", "last_error": "", "status_reason": "ok"}',
        encoding="utf-8",
    )
    assert is_portfolio_hard_halted(state_dir) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_portfolio_hard_halt.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/portfolio/hard_halt.py`:

```python
"""Portfolio hard-halt controller and entry-gate helper.

Per DESIGN-0015 §W5, the controller:
- reads the portfolio equity curve,
- detects trailing drawdown >= blueprint.mdd_hard_halt (25%),
- triggers the runtime host's hard-halt path once (latched),
- publishes a critical operator alert.

The is_portfolio_hard_halted helper is the entry-gate file-read
helper consumed by RuntimeOpportunityPlanner.plan() as defense
in depth against races between halt-firing and service-stop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, Protocol

import pandas as pd  # type: ignore[import-untyped]

from tradingx.portfolio.blueprint import PortfolioBlueprint
from tradingx.types import OperatorAlert, WebActionResult


HALT_REASON_PREFIX: Final[str] = "portfolio_hard_halt"
HALT_CATEGORY: Final[str] = "portfolio_hard_halt"


class RuntimeHostHaltProtocol(Protocol):
    def trigger_hard_halt(self, *, reason: str) -> WebActionResult: ...


class OperatorAlertGatewayProtocol(Protocol):
    def publish(self, alert: OperatorAlert) -> None: ...


def is_portfolio_hard_halted(operator_store_root: Path) -> bool:
    """Read the runtime host state artifact and return True when
    the state reports recovery_required AND last_error begins
    with HALT_REASON_PREFIX.

    This is a file-read; it works across processes and is idempotent.
    Missing or malformed state files return False (fail-open for
    the gate; the gate is defense-in-depth, the primary control
    is service_manager.stop() in trigger_hard_halt).
    """
    path = operator_store_root / "runtime_host_state.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    status = str(payload.get("status") or "")
    last_error = str(payload.get("last_error") or "")
    return status == "recovery_required" and last_error.startswith(
        HALT_REASON_PREFIX
    )


class PortfolioHardHaltController:
    def __init__(
        self,
        *,
        runtime_host: RuntimeHostHaltProtocol,
        alert_gateway: OperatorAlertGatewayProtocol,
        blueprint: PortfolioBlueprint,
    ) -> None:
        self._runtime_host = runtime_host
        self._alert_gateway = alert_gateway
        self._blueprint = blueprint
        self._halt_latched = False

    def check(self, *, equity_curve: pd.Series) -> WebActionResult | None:
        if self._halt_latched:
            return None
        dd = _trailing_drawdown(equity_curve)
        halt_threshold = float(self._blueprint.mdd_hard_halt)
        if dd < halt_threshold:
            return None
        reason = f"{HALT_REASON_PREFIX}: trailing MDD {dd:.4f}"
        halt_result = self._runtime_host.trigger_hard_halt(reason=reason)
        self._halt_latched = True
        self._alert_gateway.publish(
            OperatorAlert(
                alert_id=f"alert-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
                severity="critical",
                category=HALT_CATEGORY,
                summary=(
                    f"Portfolio hard halt: trailing MDD {dd:.2%} >= "
                    f"{halt_threshold:.0%}. Service stopped; operator "
                    "clearance required."
                ),
                evidence_refs=(),
                delivery_targets=("operator_dashboard",),
                sent_at_utc=datetime.now(UTC),
            )
        )
        return halt_result

    def reset(self) -> None:
        """Clear the latch. Intended to be called after operator
        clearance returns the runtime to `nominal`."""
        self._halt_latched = False


def _trailing_drawdown(equity_curve: pd.Series) -> float:
    values = equity_curve.astype(float)
    peak = float(values.cummax().max())
    current = float(values.iloc[-1])
    if peak <= 0.0:
        return 0.0
    return max(0.0, (peak - current) / peak)


__all__ = (
    "HALT_CATEGORY",
    "HALT_REASON_PREFIX",
    "OperatorAlertGatewayProtocol",
    "PortfolioHardHaltController",
    "RuntimeHostHaltProtocol",
    "is_portfolio_hard_halted",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_portfolio_hard_halt.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/hard_halt.py tests/unit/test_portfolio_hard_halt.py
git commit -m "feat(portfolio): add PortfolioHardHaltController and is_portfolio_hard_halted gate"
```

### Task 8: Entry-gate integration in `RuntimeOpportunityPlanner`

**Files:**
- Modify: `src/tradingx/opportunity.py`
- Modify: `tests/unit/test_opportunity.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_opportunity.py` (match the existing test-style in the file):

```python
def test_runtime_planner_short_circuits_when_hard_halt_gate_is_true():
    from tradingx.opportunity import RuntimeOpportunityPlanner

    calls: list[str] = []

    class _MarketDataGateway:
        def get_market_snapshot(self, symbol):  # pragma: no cover
            calls.append(symbol)
            raise AssertionError("gateway must not be called during halt")

    def _gate() -> bool:
        return True

    planner = RuntimeOpportunityPlanner(
        market_data_gateway=_MarketDataGateway(),
        hard_halt_gate=_gate,
    )
    # Use minimal placeholder inputs matching existing fixtures.
    selection = planner.plan(
        symbols=("SPY",),
        portfolio_state=_minimal_portfolio_state(),
        activation=_minimal_activation(),
        model_snapshot=_minimal_snapshot(),
        warmup=_minimal_warmup(),
    )
    assert selection.decision_reason == "hard_halt_active"
    assert selection.ranked_opportunities == ()
    assert selection.selected_symbol == ""
    assert calls == []


def test_runtime_planner_passes_through_when_hard_halt_gate_is_false():
    from tradingx.opportunity import RuntimeOpportunityPlanner

    # Existing fixture style: use existing regression harness.
    planner = RuntimeOpportunityPlanner(
        market_data_gateway=_existing_market_data_gateway_fixture(),
        hard_halt_gate=lambda: False,
    )
    selection = planner.plan(...)  # match existing happy-path call site
    assert selection.decision_reason != "hard_halt_active"
```

Use the same minimal-fixture helpers the existing tests in this file use. If there is no `_minimal_portfolio_state`/etc helper, build small inline fixtures that satisfy the dataclass constructors — this is preferred over complex mocks because the planner short-circuits before touching the inputs.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_opportunity.py -k hard_halt -v`

Expected: FAIL on `TypeError` (unknown `hard_halt_gate` argument to `RuntimeOpportunityPlanner.__init__`).

- [ ] **Step 3: Implement**

In `src/tradingx/opportunity.py`, extend `RuntimeOpportunityPlanner`:

```python
from collections.abc import Callable


class RuntimeOpportunityPlanner:
    def __init__(
        self,
        *,
        market_data_gateway: MarketSnapshotGatewayProtocol,
        selector: OpportunitySelector | None = None,
        hard_halt_gate: Callable[[], bool] | None = None,
    ) -> None:
        self._market_data_gateway = market_data_gateway
        self._selector = selector or OpportunitySelector()
        self._hard_halt_gate = hard_halt_gate

    def plan(
        self,
        *,
        symbols: tuple[str, ...],
        portfolio_state: PortfolioState,
        activation: StrategyActivationRecord,
        model_snapshot: ApprovedWeightSnapshot,
        warmup: HistoricalWarmupRecord,
    ) -> OpportunitySelectionRecord:
        if self._hard_halt_gate is not None and self._hard_halt_gate():
            return OpportunitySelectionRecord(
                selection_id=f"selection-{uuid.uuid4()}",
                generated_at_utc=datetime.now(UTC),
                strategy_id=activation.strategy_id,
                model_snapshot_id=model_snapshot.snapshot_id,
                symbols_considered=symbols,
                ranked_opportunities=(),
                selected_symbol="",
                decision="abort",
                decision_reason="hard_halt_active",
            )
        market_snapshots = {
            symbol: self._market_data_gateway.get_market_snapshot(symbol)
            for symbol in symbols
        }
        return self._selector.select(
            symbols=symbols,
            portfolio_state=portfolio_state,
            market_snapshots=market_snapshots,
            warmup=warmup,
            activation=activation,
            model_snapshot=model_snapshot,
        )
```

Add `import uuid` and `from datetime import UTC, datetime` if they are not already present in the file. Check imports before adding.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_opportunity.py -v`

Expected: all pass. Existing non-halt tests must continue to pass because the new `hard_halt_gate` parameter defaults to `None`.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/opportunity.py tests/unit/test_opportunity.py
git commit -m "feat(opportunity): add hard_halt_gate defense-in-depth on RuntimeOpportunityPlanner"
```

---

## W6 — Sleeve termination rules (runtime-observable)

### Task 9: Operator-halt store surface

**Files:**
- Modify: `src/tradingx/operator_control.py`
- Modify: `tests/unit/test_operator_control.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_operator_control.py`:

```python
def test_sleeve_halt_store_records_and_reads_halt(operator_control_fixture):
    # Fixture provides an operator control surface with a tmp
    # store root. Match the existing fixture style in this file.
    surface = operator_control_fixture.surface

    surface.halt_sleeve(sleeve_id="trend-following-v1", reason="signal drift")
    assert surface.is_sleeve_halted(sleeve_id="trend-following-v1") is True
    assert surface.is_sleeve_halted(sleeve_id="vol-target-v1") is False

    surface.resume_sleeve(sleeve_id="trend-following-v1")
    assert surface.is_sleeve_halted(sleeve_id="trend-following-v1") is False


def test_sleeve_halt_store_persists_reason_and_timestamp(operator_control_fixture):
    surface = operator_control_fixture.surface
    surface.halt_sleeve(sleeve_id="trend-following-v1", reason="drift alarm")
    record = surface.get_sleeve_halt_record(sleeve_id="trend-following-v1")
    assert record is not None
    assert record["reason"] == "drift alarm"
    assert record["halted"] is True
    assert record["at_utc"].endswith("Z")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_operator_control.py -k sleeve_halt -v`

Expected: FAIL on `AttributeError: surface has no method 'halt_sleeve'`.

- [ ] **Step 3: Implement**

In `src/tradingx/operator_control.py`, add the sleeve-halt methods to the operator-control surface class. The exact class name and method-signing convention must match the file's existing pattern — scan the file first with `grep -n "class " src/tradingx/operator_control.py` to find the right class.

Template:

```python
def halt_sleeve(self, *, sleeve_id: str, reason: str) -> None:
    """Record that the operator has halted the sleeve."""
    path = self._store_root / "sleeve_halts" / f"{sleeve_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sleeve_id": sleeve_id,
        "halted": True,
        "reason": reason,
        "at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

def resume_sleeve(self, *, sleeve_id: str) -> None:
    path = self._store_root / "sleeve_halts" / f"{sleeve_id}.json"
    if path.exists():
        path.unlink()

def is_sleeve_halted(self, *, sleeve_id: str) -> bool:
    path = self._store_root / "sleeve_halts" / f"{sleeve_id}.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(payload.get("halted", False))

def get_sleeve_halt_record(self, *, sleeve_id: str) -> dict | None:
    path = self._store_root / "sleeve_halts" / f"{sleeve_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
```

Add `import json` if not already present. Add `from datetime import UTC, datetime` if not already present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_operator_control.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/operator_control.py tests/unit/test_operator_control.py
git commit -m "feat(operator_control): add sleeve-halt store surface (halt/resume/is_halted/get_record)"
```

### Task 10: `RollingWindowSource` + `SleeveRuntimeConfig` + `SleeveRuntimeController`

**Files:**
- Create: `src/tradingx/portfolio/sleeve_runtime.py`
- Create: `tests/unit/test_sleeve_runtime_controller.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_sleeve_runtime_controller.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from tradingx.portfolio.sleeve_runtime import (
    DriftAlarmGatewayProtocol,
    RollingWindowSource,
    SleeveOperatorHaltStoreProtocol,
    SleeveRuntimeConfig,
    SleeveRuntimeController,
)
from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import (
    RegimeSnapshot,
    SleeveContext,
    SleeveFailureReason,
    SleeveTrade,
    TrialRecord,
)


class _FakeSleeve:
    sleeve_id = "trend-following-v1"
    family = "trend_following"
    allowed_instruments = ("SPY",)

    def __init__(self, response: tuple[SleeveTrade, ...]) -> None:
        self._response = response

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        return self._response


class _FakeHaltStore:
    def __init__(self, halted_ids: set[str]) -> None:
        self._halted = halted_ids

    def is_halted(self, *, sleeve_id: str) -> bool:
        return sleeve_id in self._halted


class _FakeDriftGateway:
    def __init__(self, alarmed: set[str]) -> None:
        self._alarmed = alarmed

    def has_alarm(self, *, sleeve_id: str) -> bool:
        return sleeve_id in self._alarmed


class _FakeTrialsLedger:
    def __init__(self, trials: tuple[TrialRecord, ...]) -> None:
        self._trials = trials

    def records_for_candidate(self, candidate_id: str) -> tuple[TrialRecord, ...]:
        return tuple(t for t in self._trials if t.candidate_id == candidate_id)


def _regime(state: str = "risk_on") -> RegimeSnapshot:
    from datetime import date

    return RegimeSnapshot(
        observation_date=date(2026, 4, 21),
        regime=state,
        above_sma_200=True,
        vix_elevated=False,
        vix_stressed=False,
        yield_curve_inverted=False,
        spy_close=Decimal("500"),
        spy_sma_200=Decimal("480"),
        vix_close=Decimal("15"),
        yield_curve_spread_bps=Decimal("35"),
    )


def _context() -> SleeveContext:
    from datetime import date

    return SleeveContext(
        observation_date=date(2026, 4, 21),
        bars_by_symbol={"SPY": pd.DataFrame()},
        regime=_regime(),
        current_weights_by_symbol={"SPY": Decimal("0.4")},
        sleeve_budget_equity=Decimal("100000"),
    )


def _trial(
    *,
    candidate_id: str,
    sharpe: str,
    window_days: int = 63,
    days_ago: int = 1,
) -> TrialRecord:
    end = datetime.now(UTC) - timedelta(days=days_ago)
    start = end - timedelta(days=window_days)
    return TrialRecord(
        trial_id=f"trial-{candidate_id}-{days_ago}",
        candidate_id=candidate_id,
        family="trend_following",
        window_start_utc=start,
        window_end_utc=end,
        observed_sharpe_net_of_costs=Decimal(sharpe),
        observed_cagr_net_of_costs=Decimal("0.05"),
        observed_max_drawdown=Decimal("0.10"),
        observed_cdar_95=Decimal("0.05"),
        annualized_cost_drag_bps=Decimal("20"),
        passed=False,
        recorded_at_utc=end,
        git_sha="test",
        config_fingerprint="test",
    )


def _sleeve_delegates_trade(side: str = "buy") -> tuple[SleeveTrade, ...]:
    return (
        SleeveTrade(
            sleeve_id="trend-following-v1",
            symbol="SPY",
            side=side,
            target_weight_of_sleeve_budget=Decimal("0.6"),
            rationale="tsmom_long_vol_targeted",
            regime="risk_on",
        ),
    )


def _config() -> SleeveRuntimeConfig:
    return SleeveRuntimeConfig(
        three_month_sharpe_floor=Decimal("0.0"),
        three_month_window_days=63,
        trial_lookback=3,
        rolling_window_source=RollingWindowSource.TRIAL_SUMMARY,
    )


def test_controller_delegates_when_no_termination_fires():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=_config(),
    )
    out = controller.plan_for_bar(_context())
    assert len(out) == 1
    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_operator_halt_precedes_sleeve():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore({"trend-following-v1"}),
        drift_alarm_gateway=_FakeDriftGateway({"trend-following-v1"}),
        trials_ledger=_FakeTrialsLedger(()),
        config=_config(),
    )
    out = controller.plan_for_bar(_context())
    assert out[0].rationale == SleeveFailureReason.HALT_BY_OPERATOR


def test_drift_alarm_precedes_sharpe_gate():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    # Trial records all below floor, but drift alarm should
    # take precedence.
    failing = tuple(
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=d)
        for d in (1, 2, 3)
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway({"trend-following-v1"}),
        trials_ledger=_FakeTrialsLedger(failing),
        config=_config(),
    )
    out = controller.plan_for_bar(_context())
    assert out[0].rationale == SleeveFailureReason.DRIFT_ALARM_LIVE


def test_sharpe_gate_fires_when_lookback_consecutive_trials_below_floor():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    failing = tuple(
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=d)
        for d in (1, 2, 3)
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(failing),
        config=_config(),
    )
    out = controller.plan_for_bar(_context())
    assert out[0].rationale == SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M


def test_sharpe_gate_does_not_fire_when_one_recent_trial_passes():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    mixed = (
        _trial(candidate_id="trend-following-v1", sharpe="0.5", days_ago=1),  # passes
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=2),
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=3),
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(mixed),
        config=_config(),
    )
    out = controller.plan_for_bar(_context())
    assert out[0].rationale == "tsmom_long_vol_targeted"  # sleeve delegates


def test_sharpe_gate_skips_when_fewer_than_lookback_qualifying_trials():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    # Only 2 trials (lookback requires 3).
    short = tuple(
        _trial(candidate_id="trend-following-v1", sharpe="-0.5", days_ago=d)
        for d in (1, 2)
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(short),
        config=_config(),
    )
    out = controller.plan_for_bar(_context())
    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_sharpe_gate_ignores_short_window_trials():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    # Three trials, but each has a 30-day window (< 63 required).
    short_windows = tuple(
        _trial(
            candidate_id="trend-following-v1",
            sharpe="-0.5",
            window_days=30,
            days_ago=d,
        )
        for d in (1, 2, 3)
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(short_windows),
        config=_config(),
    )
    out = controller.plan_for_bar(_context())
    # Short-window trials filtered out → fewer than lookback →
    # gate skipped → sleeve delegates.
    assert out[0].rationale == "tsmom_long_vol_targeted"


def test_live_daily_returns_source_raises_not_implemented_in_14():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    config = SleeveRuntimeConfig(
        three_month_sharpe_floor=Decimal("0.0"),
        three_month_window_days=63,
        trial_lookback=3,
        rolling_window_source=RollingWindowSource.LIVE_DAILY_RETURNS,
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore(set()),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=config,
    )
    with pytest.raises(NotImplementedError, match="1.5"):
        controller.plan_for_bar(_context())


def test_termination_emits_side_sell_when_currently_holding():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore({"trend-following-v1"}),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=_config(),
    )
    # Context has current_weights_by_symbol={"SPY": 0.4}, so
    # termination emits sell (weight > 0 → sell-to-zero).
    out = controller.plan_for_bar(_context())
    assert out[0].side == "sell"
    assert out[0].target_weight_of_sleeve_budget == Decimal("0")


def test_termination_emits_side_hold_when_not_holding():
    sleeve = _FakeSleeve(_sleeve_delegates_trade())
    from datetime import date

    ctx = SleeveContext(
        observation_date=date(2026, 4, 21),
        bars_by_symbol={"SPY": pd.DataFrame()},
        regime=_regime(),
        current_weights_by_symbol={"SPY": Decimal("0")},
        sleeve_budget_equity=Decimal("100000"),
    )
    controller = SleeveRuntimeController(
        wrapped_sleeve=sleeve,
        operator_halt_store=_FakeHaltStore({"trend-following-v1"}),
        drift_alarm_gateway=_FakeDriftGateway(set()),
        trials_ledger=_FakeTrialsLedger(()),
        config=_config(),
    )
    out = controller.plan_for_bar(ctx)
    assert out[0].side == "hold"
    assert out[0].target_weight_of_sleeve_budget == Decimal("0")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_sleeve_runtime_controller.py -v`

Expected: FAIL on `ImportError`.

- [ ] **Step 3: Implement**

Create `src/tradingx/portfolio/sleeve_runtime.py`:

```python
"""Sleeve runtime controller with observable termination rules
per DESIGN-0015 §W6."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import Final, Protocol

from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import (
    SleeveContext,
    SleeveFailureReason,
    SleeveTrade,
    TrialRecord,
)


class RollingWindowSource(str, Enum):
    """Where SleeveRuntimeController reads sleeve Sharpe history.

    TRIAL_SUMMARY      — 1.4 default. Reads per-trial
                         observed_sharpe_net_of_costs from the
                         trials ledger, filtered to trial windows
                         >= three_month_window_days.
    LIVE_DAILY_RETURNS — 1.5 future. Reads live per-sleeve
                         daily return series (not yet shipped;
                         controller raises NotImplementedError
                         on 1.4 if selected).
    """

    TRIAL_SUMMARY = "trial_summary"
    LIVE_DAILY_RETURNS = "live_daily_returns"


@dataclass(frozen=True)
class SleeveRuntimeConfig:
    three_month_sharpe_floor: Decimal
    three_month_window_days: int = 63
    trial_lookback: int = 3
    rolling_window_source: RollingWindowSource = (
        RollingWindowSource.TRIAL_SUMMARY
    )


class SleeveOperatorHaltStoreProtocol(Protocol):
    def is_halted(self, *, sleeve_id: str) -> bool: ...


class DriftAlarmGatewayProtocol(Protocol):
    def has_alarm(self, *, sleeve_id: str) -> bool: ...


class TrialsLedgerReadProtocol(Protocol):
    def records_for_candidate(self, candidate_id: str) -> tuple[TrialRecord, ...]: ...


class SleeveRuntimeController:
    """Wraps a sleeve with runtime termination rules.

    Precedence (first firing wins):
    1. operator halt  → HALT_BY_OPERATOR
    2. drift alarm    → DRIFT_ALARM_LIVE
    3. trial-summary Sharpe gate → SLEEVE_SHARPE_BELOW_THRESHOLD_6M
       (the 1.3 constant; the `_6M` suffix is a known naming
       imperfection per DESIGN-0015 §W6 "Constant-naming note")

    If none fire, delegates to the wrapped sleeve's plan_for_bar.

    Per DESIGN-0015 §P3: terminations emit explicit SleeveTrade
    entries (side=sell if current weight > 0, else hold) with
    target_weight_of_sleeve_budget=0 and the failure rationale —
    never an empty tuple for an in-universe symbol.
    """

    def __init__(
        self,
        *,
        wrapped_sleeve: SleeveProtocol,
        operator_halt_store: SleeveOperatorHaltStoreProtocol,
        drift_alarm_gateway: DriftAlarmGatewayProtocol | None,
        trials_ledger: TrialsLedgerReadProtocol | None,
        config: SleeveRuntimeConfig,
    ) -> None:
        self._sleeve = wrapped_sleeve
        self._halt_store = operator_halt_store
        self._drift_gateway = drift_alarm_gateway
        self._ledger = trials_ledger
        self._config = config

    @property
    def sleeve_id(self) -> str:
        return self._sleeve.sleeve_id

    @property
    def family(self) -> str:
        return self._sleeve.family

    @property
    def allowed_instruments(self) -> tuple[str, ...]:
        return self._sleeve.allowed_instruments

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        if self._config.rolling_window_source == RollingWindowSource.LIVE_DAILY_RETURNS:
            raise NotImplementedError(
                "RollingWindowSource.LIVE_DAILY_RETURNS is a tranche-1.5 "
                "capability that requires live per-sleeve daily return "
                "history; 1.4 supports only TRIAL_SUMMARY."
            )

        if self._halt_store.is_halted(sleeve_id=self._sleeve.sleeve_id):
            return self._emit_termination(
                context,
                rationale=SleeveFailureReason.HALT_BY_OPERATOR,
            )

        if self._drift_gateway is not None and self._drift_gateway.has_alarm(
            sleeve_id=self._sleeve.sleeve_id
        ):
            return self._emit_termination(
                context,
                rationale=SleeveFailureReason.DRIFT_ALARM_LIVE,
            )

        if self._should_trigger_sharpe_gate():
            return self._emit_termination(
                context,
                rationale=SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M,
            )

        return self._sleeve.plan_for_bar(context)

    def _should_trigger_sharpe_gate(self) -> bool:
        if self._ledger is None:
            return False
        records = self._ledger.records_for_candidate(self._sleeve.sleeve_id)
        qualifying = tuple(
            r
            for r in records
            if (r.window_end_utc - r.window_start_utc)
            >= timedelta(days=self._config.three_month_window_days)
        )
        if len(qualifying) < self._config.trial_lookback:
            return False
        # Sort by recency (latest first) and take the last `trial_lookback`.
        latest = sorted(qualifying, key=lambda r: r.window_end_utc, reverse=True)[
            : self._config.trial_lookback
        ]
        floor = self._config.three_month_sharpe_floor
        return all(r.observed_sharpe_net_of_costs < floor for r in latest)

    def _emit_termination(
        self,
        context: SleeveContext,
        *,
        rationale: str,
    ) -> tuple[SleeveTrade, ...]:
        trades: list[SleeveTrade] = []
        for symbol in self._sleeve.allowed_instruments:
            current = context.current_weights_by_symbol.get(symbol, Decimal("0"))
            side = "sell" if current > Decimal("0") else "hold"
            trades.append(
                SleeveTrade(
                    sleeve_id=self._sleeve.sleeve_id,
                    symbol=symbol,
                    side=side,
                    target_weight_of_sleeve_budget=Decimal("0"),
                    rationale=rationale,
                    regime=context.regime.regime,
                )
            )
        return tuple(trades)


__all__ = (
    "DriftAlarmGatewayProtocol",
    "RollingWindowSource",
    "SleeveOperatorHaltStoreProtocol",
    "SleeveRuntimeConfig",
    "SleeveRuntimeController",
    "TrialsLedgerReadProtocol",
)
```

**Note on `TrialsLedger` surface.** The spec's `TrialsLedger` at `src/tradingx/trials.py` may or may not expose `records_for_candidate`. If it doesn't, add it in a separate small commit before this task, or adapt `SleeveRuntimeController` to consume a protocol that the implementer then satisfies. Keep the protocol shape stable: `records_for_candidate(candidate_id: str) -> tuple[TrialRecord, ...]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_sleeve_runtime_controller.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/sleeve_runtime.py tests/unit/test_sleeve_runtime_controller.py
git commit -m "feat(portfolio): add SleeveRuntimeController with halt/drift/trial-sharpe termination"
```

---

## W7 — Marginal-portfolio-contribution Gate 1 criterion

### Task 11: New evidence-pack + candidate-result fields

**Files:**
- Modify: `src/tradingx/types.py`
- Modify: `tests/unit/test_types.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_types.py`:

```python
def test_evaluation_evidence_pack_accepts_marginal_deltas():
    from datetime import UTC, datetime
    from decimal import Decimal

    from tradingx.types import EvaluationEvidencePack

    now = datetime(2026, 1, 1, tzinfo=UTC)
    pack = EvaluationEvidencePack(
        evidence_pack_id="pack-1",
        candidate_id="c-1",
        window_start_utc=now,
        window_end_utc=now,
        benchmark_metrics={},
        candidate_metrics={},
        adversarial_checks=(),
        recommendation="",
        assumptions=(),
        marginal_sharpe_delta=Decimal("0.05"),
        marginal_calmar_delta=Decimal("0.03"),
        marginal_cdar_delta=Decimal("-0.01"),
    )
    assert pack.marginal_sharpe_delta == Decimal("0.05")
    assert pack.marginal_calmar_delta == Decimal("0.03")
    assert pack.marginal_cdar_delta == Decimal("-0.01")


def test_evaluation_evidence_pack_marginal_deltas_default_to_none():
    from datetime import UTC, datetime
    from tradingx.types import EvaluationEvidencePack

    now = datetime(2026, 1, 1, tzinfo=UTC)
    pack = EvaluationEvidencePack(
        evidence_pack_id="pack-1",
        candidate_id="c-1",
        window_start_utc=now,
        window_end_utc=now,
        benchmark_metrics={},
        candidate_metrics={},
        adversarial_checks=(),
        recommendation="",
        assumptions=(),
    )
    assert pack.marginal_sharpe_delta is None
    assert pack.marginal_calmar_delta is None
    assert pack.marginal_cdar_delta is None


def test_validation_candidate_result_accepts_marginal_deltas():
    from decimal import Decimal

    from tradingx.types import ValidationCandidateResult

    result = ValidationCandidateResult(
        candidate_id="c-1",
        gate_id="1",
        status="pass",
        evidence_pack_id="pack-1",
        criteria=(),
        summary="",
        marginal_sharpe_delta=Decimal("0.05"),
        marginal_calmar_delta=Decimal("0.03"),
        marginal_cdar_delta=Decimal("-0.01"),
    )
    assert result.marginal_sharpe_delta == Decimal("0.05")
    assert result.marginal_calmar_delta == Decimal("0.03")
    assert result.marginal_cdar_delta == Decimal("-0.01")


def test_validation_candidate_result_marginal_deltas_default_to_none():
    from tradingx.types import ValidationCandidateResult

    result = ValidationCandidateResult(
        candidate_id="c-1",
        gate_id="1",
        status="pass",
        evidence_pack_id="pack-1",
        criteria=(),
        summary="",
    )
    assert result.marginal_sharpe_delta is None
    assert result.marginal_calmar_delta is None
    assert result.marginal_cdar_delta is None


def test_evaluate_candidate_forwards_marginal_inputs_to_evidence_pack(
    sample_evaluate_candidate_inputs,
):
    """DESIGN-0015 §P2 + §P5: if a caller supplies marginal-delta
    kwargs to evaluate_candidate, they MUST land on the returned
    EvaluationEvidencePack. Without this forwarding contract, the
    two-pass Gate 1 restructure in W7/Task 13 could build results
    whose persisted evidence pack is missing the deltas."""
    from decimal import Decimal

    from tradingx.evaluation import evaluate_candidate

    pack = evaluate_candidate(
        sample_evaluate_candidate_inputs.candidate,
        candidate_returns=sample_evaluate_candidate_inputs.candidate_returns,
        benchmark_returns=sample_evaluate_candidate_inputs.benchmark_returns,
        window_start_utc=sample_evaluate_candidate_inputs.window_start_utc,
        window_end_utc=sample_evaluate_candidate_inputs.window_end_utc,
        adversarial_context=sample_evaluate_candidate_inputs.adversarial_context,
        marginal_sharpe_delta=Decimal("0.12"),
        marginal_calmar_delta=Decimal("0.04"),
        marginal_cdar_delta=Decimal("-0.02"),
    )
    assert pack.marginal_sharpe_delta == Decimal("0.12")
    assert pack.marginal_calmar_delta == Decimal("0.04")
    assert pack.marginal_cdar_delta == Decimal("-0.02")


def test_evaluate_candidate_marginal_inputs_default_to_none(
    sample_evaluate_candidate_inputs,
):
    """When callers omit marginal-delta kwargs (the existing
    default), the returned pack's marginal fields remain None so
    the non-Gate-1 evaluation paths continue to deserialize
    unchanged."""
    from tradingx.evaluation import evaluate_candidate

    pack = evaluate_candidate(
        sample_evaluate_candidate_inputs.candidate,
        candidate_returns=sample_evaluate_candidate_inputs.candidate_returns,
        benchmark_returns=sample_evaluate_candidate_inputs.benchmark_returns,
        window_start_utc=sample_evaluate_candidate_inputs.window_start_utc,
        window_end_utc=sample_evaluate_candidate_inputs.window_end_utc,
        adversarial_context=sample_evaluate_candidate_inputs.adversarial_context,
    )
    assert pack.marginal_sharpe_delta is None
    assert pack.marginal_calmar_delta is None
    assert pack.marginal_cdar_delta is None
```

`sample_evaluate_candidate_inputs` is a small fixture that provides a valid `StrategyCandidate` plus the positional/keyword inputs `evaluate_candidate` requires today (candidate returns, benchmark returns, window timestamps, adversarial context). Match the fixture style already used in `tests/unit/test_evaluation.py` — if no ready-made fixture exists there, define one inline at the top of this test or create a `conftest.py` helper that mirrors the existing evaluation-test setup.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_types.py -k marginal -v`

Expected: FAIL with `TypeError: unexpected keyword 'marginal_sharpe_delta'`.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`, extend both dataclasses:

```python
@dataclass(frozen=True)
class EvaluationEvidencePack:
    evidence_pack_id: str
    candidate_id: str
    window_start_utc: datetime
    window_end_utc: datetime
    benchmark_metrics: dict[str, ScalarValue]
    candidate_metrics: dict[str, ScalarValue]
    adversarial_checks: tuple[str, ...]
    recommendation: str
    assumptions: tuple[str, ...]
    annualized_cost_drag_bps: Decimal | None = None
    deflated_sharpe_ratio: Decimal | None = None
    north_star_sharpe_met: bool | None = None
    marginal_sharpe_delta: Decimal | None = None
    marginal_calmar_delta: Decimal | None = None
    marginal_cdar_delta: Decimal | None = None


@dataclass(frozen=True)
class ValidationCandidateResult:
    candidate_id: str
    gate_id: str
    status: str
    evidence_pack_id: str
    criteria: tuple[ValidationCriterionResult, ...]
    summary: str
    annualized_cost_drag_bps: Decimal | None = None
    marginal_sharpe_delta: Decimal | None = None
    marginal_calmar_delta: Decimal | None = None
    marginal_cdar_delta: Decimal | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_types.py -v`

Expected: all pass. Run `uv run pytest` at the repo root to verify nothing else breaks on the defaulted fields.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py tests/unit/test_types.py
git commit -m "feat(types): add marginal_*_delta fields to evidence pack and candidate result"
```

### Task 12: `evaluate_marginal_portfolio_contribution`

**Files:**
- Modify: `src/tradingx/validation.py`
- Create: `tests/unit/test_marginal_portfolio_contribution.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_marginal_portfolio_contribution.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from tradingx.validation import evaluate_marginal_portfolio_contribution


def _rets(*vals: str) -> tuple[Decimal, ...]:
    return tuple(Decimal(v) for v in vals)


def test_marginal_pass_when_all_three_metrics_improve():
    # A synthetic scenario: adding the candidate boosts Sharpe
    # and Calmar, and CDaR (a bad — lower is better) stays the
    # same or improves.
    without = _rets("0.001", "0.001", "0.001", "0.001", "0.001")  # low, steady
    with_ = _rets("0.005", "0.004", "0.006", "0.005", "0.004")    # higher, still steady
    candidate = _rets("0.01", "0.01", "0.01", "0.01", "0.01")

    result = evaluate_marginal_portfolio_contribution(
        candidate_returns=candidate,
        portfolio_without_candidate_returns=without,
        portfolio_with_candidate_returns=with_,
    )
    assert result.criterion_id == "marginal_portfolio_contribution"
    assert result.passed is True


def test_marginal_fail_when_sharpe_degrades():
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


def test_marginal_fail_when_cdar_worsens():
    # Equal Sharpe and Calmar but CDaR worse with candidate.
    without = _rets("0.001", "0.001", "0.001", "-0.001", "0.001")
    with_ = _rets("0.001", "0.001", "0.001", "-0.02", "0.001")  # deeper tail
    candidate = _rets("0.0", "0.0", "0.0", "-0.04", "0.0")

    result = evaluate_marginal_portfolio_contribution(
        candidate_returns=candidate,
        portfolio_without_candidate_returns=without,
        portfolio_with_candidate_returns=with_,
    )
    # CDaR with > without → fail.
    assert result.passed is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_marginal_portfolio_contribution.py -v`

Expected: FAIL on `ImportError: cannot import name 'evaluate_marginal_portfolio_contribution'`.

- [ ] **Step 3: Implement**

Append to `src/tradingx/validation.py`:

```python
def evaluate_marginal_portfolio_contribution(
    *,
    candidate_returns: tuple[Decimal, ...],
    portfolio_without_candidate_returns: tuple[Decimal, ...],
    portfolio_with_candidate_returns: tuple[Decimal, ...],
) -> ValidationCriterionResult:
    """Evaluate whether adding the candidate to the book improves
    Sharpe, Calmar, and CDaR of the portfolio.

    Pass rule (all must hold):
        sharpe_with  > sharpe_without
        calmar_with  > calmar_without
        cdar_with    <= cdar_without   (CDaR is a bad — lower better)

    HARD-PASS criterion — a candidate that fails this fails
    Gate 1, per ADR-0022 §"Deferred to tranche 1 hardening".
    """
    del candidate_returns  # presently unused; accepted for future cost-aware form.
    without_pack = _metric_pack(portfolio_without_candidate_returns)
    with_pack = _metric_pack(portfolio_with_candidate_returns)
    without_cdar = float(
        conditional_drawdown_at_risk(
            _to_float_sequence(portfolio_without_candidate_returns),
            confidence=0.95,
        )
    )
    with_cdar = float(
        conditional_drawdown_at_risk(
            _to_float_sequence(portfolio_with_candidate_returns),
            confidence=0.95,
        )
    )
    sharpe_delta = with_pack["sharpe_ratio"] - without_pack["sharpe_ratio"]
    calmar_delta = with_pack["calmar_ratio"] - without_pack["calmar_ratio"]
    cdar_delta = with_cdar - without_cdar  # positive means worse

    passed = sharpe_delta > 0 and calmar_delta > 0 and cdar_delta <= 0
    return ValidationCriterionResult(
        criterion_id="marginal_portfolio_contribution",
        passed=passed,
        threshold=(
            "Adding candidate improves portfolio Sharpe AND Calmar "
            "AND does not worsen CDaR@95%"
        ),
        details=(
            f"sharpe_delta={sharpe_delta:.4f}, "
            f"calmar_delta={calmar_delta:.4f}, "
            f"cdar_delta={cdar_delta:.4f} "
            "(cdar_delta <= 0 required; sharpe and calmar > 0 required)."
        ),
    )
```

Update `__all__` in `validation.py` to include `evaluate_marginal_portfolio_contribution`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_marginal_portfolio_contribution.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/validation.py tests/unit/test_marginal_portfolio_contribution.py
git commit -m "feat(validation): add evaluate_marginal_portfolio_contribution (Gate 1 hard-pass)"
```

### Task 13: Two-pass Gate 1 restructure in `build_gate_report`

**Files:**
- Modify: `src/tradingx/validation.py`
- Modify: `src/tradingx/evaluation.py`
- Modify: `tests/unit/test_validation.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_validation.py`:

```python
def test_gate1_rejects_registry_with_not_two_sleeve_backed_candidates():
    from tradingx.types import StrategyCandidate

    one_sleeve = (
        StrategyCandidate(
            candidate_id="only-sleeve-v1",
            family="x",
            benchmark_symbol="SPY",
            universe=("SPY",),
            parameter_set={},
            status="under_evaluation",
            sleeve_class_path="tradingx.sleeves.trend.TrendSleeve",
        ),
    )
    with pytest.raises(NotImplementedError, match="two-sleeve case"):
        build_gate_report(
            gate_id="1",
            bars_by_symbol=...,  # match existing fixture
            candidates=one_sleeve,
            benchmark_stack_payload=...,
            window_start_utc=...,
            window_end_utc=...,
        )


def test_gate1_evaluates_marginal_contribution_for_two_sleeves(sample_fixtures):
    # Two sleeve-backed candidates plus one non-sleeve candidate.
    # Each sleeve-backed result carries populated marginal_*_delta
    # on the ValidationCandidateResult.
    report = build_gate_report(
        gate_id="1",
        bars_by_symbol=sample_fixtures.bars,
        candidates=sample_fixtures.two_sleeves_plus_mean_reversion,
        benchmark_stack_payload=sample_fixtures.benchmark_stack,
        window_start_utc=sample_fixtures.window_start,
        window_end_utc=sample_fixtures.window_end,
    )
    by_id = {r.candidate_id: r for r in report.candidate_results}
    trend = by_id["trend-following-v1"]
    vol = by_id["vol-target-v1"]
    mr = by_id["mean-reversion-v1"]
    # Sleeve-backed candidates have the marginal criterion in their tuple.
    trend_crits = {c.criterion_id for c in trend.criteria}
    vol_crits = {c.criterion_id for c in vol.criteria}
    assert "marginal_portfolio_contribution" in trend_crits
    assert "marginal_portfolio_contribution" in vol_crits
    # Non-sleeve candidate does not.
    mr_crits = {c.criterion_id for c in mr.criteria}
    assert "marginal_portfolio_contribution" not in mr_crits
    # Deltas populated on the persisted ValidationCandidateResult.
    assert trend.marginal_sharpe_delta is not None
    assert vol.marginal_sharpe_delta is not None
    assert mr.marginal_sharpe_delta is None


def test_gate1_marginal_deltas_land_on_evidence_pack_not_just_result(sample_fixtures):
    """DESIGN-0015 §P2 (round-1 plan review P1): the marginal
    deltas MUST be populated on the pass-2 EvaluationEvidencePack
    as well as on the ValidationCandidateResult, so evidence-pack
    consumers do not silently lose the data. The evidence pack is
    not exposed by ValidationReport (which carries pack IDs only),
    so we assert on it via the testable pass-2 helper."""
    from tradingx.validation import _apply_marginal_pass_to_gate1_result

    pass1_result, pass1_pack, pass1_returns = (
        sample_fixtures.trend_pass1_triplet
    )
    final_result, final_pack = _apply_marginal_pass_to_gate1_result(
        candidate=sample_fixtures.trend_candidate,
        pass1_result=pass1_result,
        pass1_pack=pass1_pack,
        pass1_returns=pass1_returns,
        annualized_cost_drag_bps=sample_fixtures.trend_cost_drag_bps,
        sibling_candidate=sample_fixtures.vol_candidate,
        bars_by_symbol=sample_fixtures.bars,
        regime_snapshots_by_date=sample_fixtures.regime_snapshots,
        benchmark_stack_payload=sample_fixtures.benchmark_stack,
        window_start_utc=sample_fixtures.window_start,
        window_end_utc=sample_fixtures.window_end,
        adversarial_context=sample_fixtures.adversarial_context,
        base_cost_model_config=sample_fixtures.base_cost_model_config,
    )
    # Direct assertion on the PACK object, not just the result.
    assert final_pack.marginal_sharpe_delta is not None
    assert final_pack.marginal_calmar_delta is not None
    assert final_pack.marginal_cdar_delta is not None
    # The result's evidence_pack_id points at the pass-2 pack
    # (not the pass-1 pack), so downstream consumers that look
    # up packs by ID will see the marginal fields.
    assert final_result.evidence_pack_id == final_pack.evidence_pack_id
    assert final_result.evidence_pack_id != pass1_pack.evidence_pack_id
    # Result and pack carry the same delta values.
    assert final_result.marginal_sharpe_delta == final_pack.marginal_sharpe_delta
    assert final_result.marginal_calmar_delta == final_pack.marginal_calmar_delta
    assert final_result.marginal_cdar_delta == final_pack.marginal_cdar_delta
```

`sample_fixtures` must expose a `trend_pass1_triplet` tuple `(pass1_result, pass1_pack, pass1_returns)` matching what the pass-1 branch of `build_gate_report` would produce for the trend candidate, plus the other inputs `_apply_marginal_pass_to_gate1_result` needs. Mirror the factory style in `test_validation.py` — the fixture builds these via the same helpers the production code uses (just exposing intermediate values).

`sample_fixtures` should produce deterministic canned bars for SPY + QQQ, a benchmark-stack payload aligned with the window, and the three-candidate registry. Reuse whatever fixture harness other `test_validation.py` tests already rely on; if none exists, create helpers inline in this test module.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_validation.py -k "marginal or not_two_sleeve" -v`

Expected: FAIL on the fixture build (marginal fields not yet populated by `build_gate_report`).

- [ ] **Step 3: Implement — extend `evaluate_candidate` to accept optional marginal inputs**

In `src/tradingx/evaluation.py`, extend `evaluate_candidate` to accept three optional keyword arguments and forward them onto the evidence pack. The function body is primarily a constructor call for `EvaluationEvidencePack`; just thread the fields through.

```python
def evaluate_candidate(
    candidate: StrategyCandidate,
    *,
    candidate_returns: tuple[Decimal, ...],
    benchmark_returns: tuple[Decimal, ...],
    window_start_utc: datetime,
    window_end_utc: datetime,
    adversarial_context: AdversarialCheckContext,
    annualized_cost_drag_bps: Decimal | None = None,
    trials_ledger: TrialsLedger | None = None,
    marginal_sharpe_delta: Decimal | None = None,
    marginal_calmar_delta: Decimal | None = None,
    marginal_cdar_delta: Decimal | None = None,
) -> EvaluationEvidencePack:
    # ...existing body unchanged...
    return EvaluationEvidencePack(
        # ...existing fields...
        marginal_sharpe_delta=marginal_sharpe_delta,
        marginal_calmar_delta=marginal_calmar_delta,
        marginal_cdar_delta=marginal_cdar_delta,
    )
```

- [ ] **Step 4: Implement — two-pass Gate 1 restructure in `build_gate_report`**

In `src/tradingx/validation.py`, restructure the `gate_id == "1"` branch of `build_gate_report`. Pseudocode from DESIGN-0015 W7 is the source of truth; the real code follows the existing pattern of `_build_gate1_candidate_result`. Key pieces:

- Defensive assertion at Gate 1 entry: count sleeve-backed candidates (candidates with `sleeve_class_path is not None`); raise `NotImplementedError` if `!= 2`.
- Introduce a helper `_build_gate1_candidate_result_pass1` that produces the four-criteria `ValidationCandidateResult` (what `_build_gate1_candidate_result` does today).
- Introduce a helper `_simulate_two_sleeve_book` that takes `(candidates: tuple[StrategyCandidate, ...], bars_by_symbol, regime_snapshots_by_date, cost_model_config)` and returns a `tuple[Decimal, ...]` via `simulate_portfolio_returns` with a per-evaluation `PortfolioBlueprint` using equal budgets.
- Build pass 1 results (dict keyed by `candidate_id`).
- For each sleeve-backed candidate: determine sibling from the registry, simulate with/without, call `evaluate_marginal_portfolio_contribution`, compute deltas, build a replacement `ValidationCandidateResult` that adds the marginal criterion and reconciles status.
- For non-sleeve candidates: pass-1 result is the final result; no pass 2.

Status reconciliation helper:

```python
def _reconcile_gate1_status(pass1_status: str, marginal_status: str) -> str:
    if pass1_status in {"fail", "pending"}:
        return pass1_status
    return "pass" if marginal_status == "pass" else marginal_status
```

Sample book-sim helper:

```python
def _simulate_two_sleeve_book(
    candidates: tuple[StrategyCandidate, ...],
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    cost_model_config: CostModelConfig | None,
) -> tuple[Decimal, ...]:
    from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
    from tradingx.portfolio.construction import simulate_portfolio_returns
    from tradingx.sleeves.base import build_sleeve_from_candidate

    sleeves = tuple(build_sleeve_from_candidate(c) for c in candidates)
    budget_per = Decimal("1") / Decimal(len(sleeves))
    blueprint = PortfolioBlueprint(
        blueprint_id="gate1-marginal-eval",
        sleeve_budgets=tuple(
            SleeveRiskBudget(
                sleeve_id=s.sleeve_id,
                budget_fraction_of_equity=budget_per,
                max_correlation_with_other_sleeves=Decimal("0.85"),
            )
            for s in sleeves
        ),
    )
    result = simulate_portfolio_returns(
        sleeves,
        blueprint=blueprint,
        bars_by_symbol=bars_by_symbol,
        regime_snapshots_by_date=regime_snapshots_by_date,
        cost_model_config=cost_model_config,
    )
    return tuple(
        Decimal(str(v)) for v in result.backtest_result.portfolio_returns.tolist()
    )
```

Pass-2 logic (inside the `gate_id == "1"` branch):

```python
# After pass 1 builds the initial dict.
sleeve_candidates = tuple(c for c in candidates if c.sleeve_class_path is not None)
if len(sleeve_candidates) != 2:
    raise NotImplementedError(
        "Marginal-portfolio-contribution criterion in tranche 1.4 is "
        "scoped to the two-sleeve case; found "
        f"{len(sleeve_candidates)} sleeve-backed candidates. "
        "Generalization for 3+ sleeves is deferred."
    )

# Pass 1 (existing logic refactored): populate four parallel dicts
# rather than returning ValidationCandidateResult alone. The pack
# and the raw returns are load-bearing for pass 2.
pass1_results: dict[str, ValidationCandidateResult] = {}
pass1_packs: dict[str, EvaluationEvidencePack] = {}
pass1_returns: dict[str, tuple[Decimal, ...]] = {}
pass1_cost_drag: dict[str, Decimal | None] = {}

# ...pass-1 loop populates all four dicts (not shown)...

# Pass 2: for each sleeve-backed candidate, apply the marginal
# criterion against the registry-pinned sibling book.
regimes_for_book = _build_default_regime_snapshots(
    sleeve_candidates[0],
    bars_by_symbol=aligned_bars,
)
final_results: list[ValidationCandidateResult] = []
for candidate in candidates:
    pass1_entry = pass1_results[candidate.candidate_id]
    if candidate.sleeve_class_path is None:
        # Non-sleeve candidate (e.g., mean-reversion-v1): pass 2
        # does not run; the pass-1 result is the final result.
        final_results.append(pass1_entry)
        continue
    sibling = next(
        c for c in sleeve_candidates if c.candidate_id != candidate.candidate_id
    )
    # Call the extracted helper below for the (result, pack) pair.
    final_result, _pass2_pack = _apply_marginal_pass_to_gate1_result(
        candidate=candidate,
        pass1_result=pass1_entry,
        pass1_pack=pass1_packs[candidate.candidate_id],
        pass1_returns=pass1_returns[candidate.candidate_id],
        annualized_cost_drag_bps=pass1_cost_drag[candidate.candidate_id],
        sibling_candidate=sibling,
        bars_by_symbol=aligned_bars,
        regime_snapshots_by_date=regimes_for_book,
        benchmark_stack_payload=benchmark_stack_payload,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        adversarial_context=adversarial_context,
        base_cost_model_config=base_cost_model_config,
        trials_ledger=trials_ledger,
    )
    final_results.append(final_result)
```

The helper shown below is the sole home for `_simulate_two_sleeve_book`, `evaluate_marginal_portfolio_contribution`, the `evaluate_candidate` re-invocation with marginal kwargs, the `_reconcile_gate1_status` reconciliation, and the final `dataclasses.replace` on the result. Keeping all of that inside the helper is what makes Task 13's `test_gate1_marginal_deltas_land_on_evidence_pack_not_just_result` a one-call direct test against the `(result, pack)` pair.

**Pass-2 implementation is binding — single path, not a choice.** DESIGN-0015 §P2 and §P5 require `marginal_*_delta` to land on BOTH the `ValidationCandidateResult` AND the `EvaluationEvidencePack`. The marginal-delta population must therefore happen via **re-invoking `evaluate_candidate`** with the three marginal inputs — this reuses the forwarding contract pinned by `test_evaluate_candidate_forwards_marginal_inputs_to_evidence_pack` in Task 11, so the returned pack carries the deltas by construction. `dataclasses.replace` on the pass-1 pack is NOT a permitted alternative because it skirts the single-source-of-truth population rule.

Extract pass-2 into a **named helper** that returns a `(result, pack)` tuple so both objects are directly testable — required by Task 13's
`test_gate1_marginal_deltas_land_on_evidence_pack_not_just_result`:

```python
def _apply_marginal_pass_to_gate1_result(
    *,
    candidate: StrategyCandidate,
    pass1_result: ValidationCandidateResult,
    pass1_pack: EvaluationEvidencePack,
    pass1_returns: tuple[Decimal, ...],
    annualized_cost_drag_bps: Decimal | None,
    sibling_candidate: StrategyCandidate,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    benchmark_stack_payload: BenchmarkStackPayload,
    window_start_utc: datetime,
    window_end_utc: datetime,
    adversarial_context: AdversarialCheckContext,
    base_cost_model_config: CostModelConfig | None,
    trials_ledger: TrialsLedger | None = None,
) -> tuple[ValidationCandidateResult, EvaluationEvidencePack]:
    """Produce the final (result, pack) pair for a sleeve-backed
    candidate's pass-2 marginal-contribution evaluation.

    Steps:
    1. Simulate the portfolio WITHOUT the candidate (sibling alone)
       and WITH (candidate + sibling) via _simulate_two_sleeve_book.
    2. Call evaluate_marginal_portfolio_contribution to produce the
       ValidationCriterionResult; extract the three observed deltas
       from its details string (or compute them locally from the
       metric packs and thread them through).
    3. RE-INVOKE evaluate_candidate with the marginal deltas supplied
       so the returned EvaluationEvidencePack carries them. This is
       the ONLY blessed path.
    4. Build the final ValidationCandidateResult via dataclasses.replace
       on pass1_result with the new evidence_pack_id, combined criteria
       (pass1 four + marginal), reconciled status, marginal_*_delta,
       and summary.
    5. Return (final_result, pass2_pack).
    """
```

Callers inside `build_gate_report` invoke this helper per sleeve-backed candidate and append the result to `final_results`; the pack is not directly returned by `build_gate_report` but is reachable in tests via this helper. Recommended refactor: compute the three deltas locally inside the helper (rather than parsing them back out of the criterion's `details` string) and pass them both to `evaluate_candidate` and onto the replaced `ValidationCandidateResult`.

**On "persistence".** `GateValidationController` at [src/tradingx/controller.py](/src/tradingx/controller.py) persists the `ValidationReport` and `GateAssessment`, not individual `EvaluationEvidencePack` objects — the validation flow today does not write packs to disk. The accurate pass-2 goal is NOT "the final persisted pack carries the deltas" (no such persistence exists); it is "the pass-2 pack object exists with the deltas populated and its ID is the one recorded on the final `ValidationCandidateResult.evidence_pack_id`". Future work (tranche 1.5 or later) that adds evidence-pack persistence will inherit correctly populated packs without changes to this tranche. This plan does NOT introduce pack persistence.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_validation.py -v`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/tradingx/validation.py src/tradingx/evaluation.py tests/unit/test_validation.py
git commit -m "feat(validation): two-pass Gate 1 with marginal-portfolio-contribution hard-pass"
```

---

## W8 — Closing pass

### Task 14: Integration test — portfolio end-to-end

**Files:**
- Create: `tests/integration/test_portfolio_end_to_end.py`

- [ ] **Step 1: Write the integration test**

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from tradingx.features.regime import classify_regime
from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.construction import (
    build_portfolio_target_weight_history,
    simulate_portfolio_returns,
)
from tradingx.portfolio.throttle import (
    apply_cdar_soft_throttle,
    apply_mdd_design_throttle,
)
from tradingx.sleeves.trend import TrendSleeve
from tradingx.sleeves.vol_managed_beta import VolManagedBetaSleeve
from tradingx.types import RegimeSnapshot


def _bars(n: int = 500, seed: int = 29) -> pd.DataFrame:
    rng = np.random.default_rng(seed=seed)
    returns = rng.normal(scale=0.01, size=n)
    closes = 100.0 * np.cumprod(1.0 + returns)
    dates = pd.date_range("2020-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": [1e7] * n,
        },
        index=dates,
    )


def _regimes(bars: pd.DataFrame) -> dict[date, RegimeSnapshot]:
    closes = bars["close"].astype(float)
    sma = closes.rolling(200).mean()
    out: dict[date, RegimeSnapshot] = {}
    for ts in bars.index:
        if pd.isna(sma.loc[ts]):
            continue
        out[ts.date()] = classify_regime(
            observation_date=ts.date(),
            spy_close=Decimal(str(float(closes.loc[ts]))),
            spy_sma_200=Decimal(str(float(sma.loc[ts]))),
            vix_close=None,
            yield_curve_spread_bps=None,
        )
    return out


def test_portfolio_simulation_matches_validate_inputs_shape():
    from tradingx.backtest import _validate_inputs  # type: ignore[attr-defined]

    spy = _bars(500)
    qqq = _bars(500, seed=31)
    regimes = _regimes(spy)
    bp = PortfolioBlueprint(
        blueprint_id="it",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    target_weights = build_portfolio_target_weight_history(
        sleeves,
        blueprint=bp,
        bars_by_symbol={"SPY": spy, "QQQ": qqq},
        regime_snapshots_by_date=regimes,
    )
    _validate_inputs({"SPY": spy, "QQQ": qqq}, target_weights)


def test_simulation_and_throttle_compose():
    spy = _bars(500, seed=37)
    qqq = _bars(500, seed=41)
    regimes = _regimes(spy)
    bp = PortfolioBlueprint(
        blueprint_id="it",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    result = simulate_portfolio_returns(
        sleeves,
        blueprint=bp,
        bars_by_symbol={"SPY": spy, "QQQ": qqq},
        regime_snapshots_by_date=regimes,
    )
    equity = result.backtest_result.equity_curve
    peaks = equity.cummax()
    dd = ((peaks - equity) / peaks).fillna(0.0)
    throttled, mdd_scale = apply_mdd_design_throttle(
        target_weights=result.combined_target_weights,
        trailing_drawdown_series=dd,
        blueprint=bp,
    )
    # Throttle is pure: shape matches and no NaNs introduced.
    assert throttled.shape == result.combined_target_weights.shape
    assert not throttled.isna().any().any()
    # Where dd <= design, throttled == original (within tolerance).
    passthrough_rows = dd <= float(bp.mdd_design_target)
    pd.testing.assert_frame_equal(
        throttled.loc[passthrough_rows],
        result.combined_target_weights.loc[passthrough_rows],
    )
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/integration/test_portfolio_end_to_end.py -v`

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_portfolio_end_to_end.py
git commit -m "test(portfolio): add integration for sleeves + portfolio + throttle"
```

### Task 15: Activate marginal criterion in GATES-0001 + bump INDEX

**Files:**
- Modify: `docs/validation/acceptance_gates.md`
- Modify: `docs/INDEX.md`

- [ ] **Step 1: Update GATES-0001**

Front-matter: bump `version: 1.1.0` → `version: 1.2.0`; set `supersedes: GATES-0001@1.1.0`; keep `last_amended` at 2026-04-21 if that is the day of merge, otherwise use today's ISO date.

Move the marginal-portfolio-contribution criterion from the "Deferred to tranche 1 hardening" block into the "Pass criteria (hard-pass, all required)" block:

- Remove from **Deferred to tranche 1 hardening**:
  > Marginal portfolio contribution: a surviving sleeve must also improve the portfolio's Sharpe, Calmar, and CDaR when added to the existing book with cost and correlation accounted for. This criterion ships when tranche 1's multi-sleeve portfolio construction lands.

- Add to **Pass criteria (hard-pass, all required)**:
  > `marginal_portfolio_contribution`: for each sleeve-backed candidate, adding the candidate to the reference book of mandatory sleeve-backed candidates must strictly improve portfolio Sharpe AND Calmar AND not worsen portfolio CDaR@95%. For tranche 1.4, the reference book is the registry-pinned sibling — the other mandatory sleeve-backed candidate from `build_mandatory_candidate_registry()` with `sleeve_class_path is not None`, independent of the sibling's own Gate 1 outcome. Generalization for 3+ sleeve-backed candidates is deferred to the tranche that introduces a third sleeve-backed candidate.

Note: the 25% `max_drawdown_halt` text in the `operating_constraint` bullet already says it "is not yet enforced by a runtime halt trigger; runtime enforcement ships with tranche 1's drawdown-defense subsystem." Once W5 is implemented, that sentence becomes inaccurate. Replace it with:

> The 25% maximum-drawdown hard-halt threshold is enforced at runtime by `PortfolioHardHaltController` (see [DESIGN-0015](/docs/superpowers/specs/2026-04-21-tranche-1-4-portfolio-construction-and-drawdown-defense-design.md) §W5). When trailing drawdown reaches 25%, the runtime host stops the service, transitions to `recovery_required`, and emits a critical `OperatorAlert`; the operator must clear via `request_clearance()` before trading resumes.

- [ ] **Step 2: Update INDEX**

In `docs/INDEX.md`:

- Bump INDEX front-matter version (e.g., 1.2.27 → 1.2.28), bump `supersedes`, keep `last_amended`.
- Update the INDEX-0001 row in the "State files" table to match.
- Update the GATES-0001 row: `1.1.0` → `1.2.0`.

- [ ] **Step 3: Validate**

Run: `python3 scripts/check_index.py`

Expected: `INDEX validation passed.`

- [ ] **Step 4: Commit**

```bash
git add docs/validation/acceptance_gates.md docs/INDEX.md
git commit -m "gov(gates): activate marginal-portfolio-contribution Gate 1 criterion (GATES-0001 1.2.0)"
```

### Task 16: Full regression + lint + typecheck + index + validate

- [ ] **Step 1: pytest**

Run: `uv run pytest -q`

Expected: all pass. If the repository carries `--deselect` patterns from the 1.3 closing pass, preserve them (run the same command 1.3 used).

- [ ] **Step 2: mypy**

Run: `uv run mypy src/tradingx`

Expected: no issues.

- [ ] **Step 3: ruff**

Run: `uv run ruff check src/tradingx tests`

Expected: clean.

- [ ] **Step 4: check_index**

Run: `python3 scripts/check_index.py`

Expected: `INDEX validation passed.`

- [ ] **Step 5: validate**

Run: `./scripts/validate`

Expected: clean.

- [ ] **Step 6: Commit formatting fixups if any**

```bash
git status
# if auto-format diffs appear:
git add -u
git commit -m "chore: formatting fixups after tranche 1.4"
```

Skip if no fixups needed.

---

## Self-review

### Spec coverage

- DESIGN-0015 W1 (`PortfolioBlueprint`, `SleeveRiskBudget`): Task 1.
- DESIGN-0015 W2 (`build_portfolio_target_weight_history`, `simulate_portfolio_returns`, `PortfolioSimulationResult`): Tasks 2–3.
- DESIGN-0015 W3 (`apply_mdd_design_throttle`): Task 4.
- DESIGN-0015 W4 (`apply_cdar_soft_throttle` + composition): Task 5.
- DESIGN-0015 W5 (`trigger_hard_halt`, `is_portfolio_hard_halted`, `PortfolioHardHaltController`, entry-gate): Tasks 6–8.
- DESIGN-0015 W6 (operator-halt store, `RollingWindowSource`, `SleeveRuntimeConfig`, `SleeveRuntimeController`): Tasks 9–10.
- DESIGN-0015 W7 (evidence pack + candidate result fields, evaluator, two-pass Gate 1): Tasks 11–13.
- DESIGN-0015 W8 (integration, GATES activation, regression): Tasks 14–16.

### Placeholder scan

No TBD / TODO / "implement later" in production code. A small number of fixture-name placeholders (e.g., `runtime_host_fixture`, `sample_fixtures`, `operator_control_fixture`) are flagged for the implementer to match existing repo conventions — these are test-file concerns, not production code.

### Type consistency

- `SleeveRiskBudget` and `PortfolioBlueprint` from Task 1 consumed by Tasks 2, 3, 7, 13.
- `build_portfolio_target_weight_history` from Task 2 consumed by Tasks 3, 13, 14.
- `PortfolioSimulationResult` from Task 3 is the single carrier of `backtest_result`, `combined_target_weights`, `throttle_scale_series` consumed by Tasks 14, 13.
- `apply_mdd_design_throttle` / `apply_cdar_soft_throttle` both return `(pd.DataFrame, pd.Series)` scale.
- `SERVICE_STOP_SUCCESS_STATUSES` constant from Task 6 referenced by Task 6's tests (same file) only; other consumers use the method's return-value semantics.
- `HALT_REASON_PREFIX` from Task 7's `hard_halt.py` consumed by Task 7's tests and Task 8's `is_portfolio_hard_halted` tests.
- `RollingWindowSource`, `SleeveRuntimeConfig`, `SleeveRuntimeController` from Task 10 not consumed in 1.4 runtime (integration point with the service loop is deferred to 1.5 when drift alarm and live-return-source are wired).
- `marginal_*_delta` fields on `EvaluationEvidencePack` and `ValidationCandidateResult` from Task 11 populated by Task 13.
- `evaluate_marginal_portfolio_contribution` from Task 12 consumed by Task 13.

### Open judgment calls left to the implementer

1. **Sleeve-runtime controller runtime wiring.** Task 10 creates `SleeveRuntimeController` but does not wire it into the live service loop — that's a 1.5 concern (drift alarm is a stub; `LIVE_DAILY_RETURNS` raises). If the implementer finds a natural integration point during 1.4 that does not depend on 1.5-scope functionality, flag it; otherwise keep wiring deferred.
2. **Pass-2 pack population (bound, not optional — round-1 plan review P1).** The round-1 plan review correctly flagged that without a direct assertion on the pack object, an implementation could satisfy the plan by only updating `ValidationCandidateResult`. The plan now binds the path: pass-2 MUST re-invoke `evaluate_candidate` with the three marginal-delta kwargs (Task 11 pins the forwarding contract); `_apply_marginal_pass_to_gate1_result` is an extractable helper returning `(result, pack)` so both are directly testable. `dataclasses.replace` on the pass-1 pack is not permitted. Evidence-pack persistence is out of scope (it does not exist today in `GateValidationController`).
3. **`TrialsLedger.records_for_candidate`.** If this method doesn't already exist on `src/tradingx/trials.py`, add it in a small prefatory commit. The protocol shape is `records_for_candidate(candidate_id: str) -> tuple[TrialRecord, ...]`.
4. **Fixture-name placeholders** in test files — match whatever conventions already exist in the target test module (`runtime_host_fixture`, `sample_fixtures`, `operator_control_fixture`, `_minimal_portfolio_state`, etc.).
5. **Correlation-cap math.** DESIGN-0015 §W2 notes the sharper rule vs a flat `max_gross × 0.85` rule. The plan implements the sharper rule (`strictest × max_gross`). If Codex wants to simplify here during implementation review, flag it — a simpler rule is a documentation amendment on the spec plus a small code tweak.

### Execution handoff

Plan is for Codex to execute. No subagent-driven or inline execution invocation from this session. Same pattern as tranches 1.1, 1.2, and 1.3.
