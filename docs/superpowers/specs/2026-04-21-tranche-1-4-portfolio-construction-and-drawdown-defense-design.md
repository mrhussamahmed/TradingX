---
id: DESIGN-0015
title: Tranche 1.4 portfolio construction and drawdown defense
version: 0.1.0
status: draft
created: 2026-04-21
last_amended: 2026-04-21
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# DESIGN-0015: Tranche 1.4 portfolio construction and drawdown defense

## Status

Draft on 2026-04-21. Fourth sub-tranche under
[BRIEF-0002](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
tranche-1 plan. Pending Hussam approval and Codex peer review.

## Purpose

Turn the two merged sleeves (`TrendSleeve`,
`VolManagedBetaSleeve` — shipped in tranche 1.3) into a combined
portfolio and attach the drawdown-defense and Gate-1-marginal-
contribution machinery that
[BRIEF-0002 §Sub-tranche sequence](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
reserved for this sub-tranche.

Scope:

1. **Portfolio construction.** Combine per-sleeve target-weight
   histories into a single portfolio target-weight history with
   per-sleeve risk budgets, correlation caps, and gross/net
   exposure caps. Must flow through the existing
   [`run_daily_bar_backtest`](/src/tradingx/backtest.py:38)
   execution engine — no second execution model.
2. **MDD design throttle (15% proportional exposure reduction).**
   When the portfolio's trailing drawdown exceeds 15% but is below
   the 25% halt, scale sleeve exposures linearly down to zero.
3. **CDaR soft-throttle.** A second dampener that activates when
   trailing `CDaR@95%` exceeds the 8% `cdar_threshold` from
   [`OperatingConstraintBudget`](/src/tradingx/types.py:243),
   reducing exposure before the hard halt engages.
4. **25% MDD runtime hard halt wired to operator clearance.** The
   `max_drawdown_halt = 0.25` value currently lives as metadata on
   `OperatingConstraintBudget` (per GATES-0001 v1.1.0) but is not
   enforced by a runtime trigger. 1.4 wires it into the
   `LocalRuntimeHostManager` operator-clearance cycle so new
   entries are blocked until the operator clears the halt — closing
   the P1 gap flagged in the ADR-0021/ADR-0022 review.
5. **Sleeve termination rules (runtime-observable).** Promote the
   `SleeveFailureReason` constants shipped in 1.3 from "available
   strings" to "observable runtime events": operator halt, drift
   alarm (stub wired for 1.5 to fill), and a trial-summary
   Sharpe gate that fires when the sleeve has produced N
   consecutive ≥ 3-month-window trials below the floor. Every
   termination emits an explicit sleeve trade with the reason
   code — no silent skips. (The original "3-month rolling
   Sharpe" framing was narrowed in the round-1 review because
   the trials ledger carries per-trial summaries rather than
   daily returns; see W6.)
6. **Marginal-portfolio-contribution Gate 1 criterion.** Wire the
   criterion deferred to tranche 1 by
   [ADR-0022 §"Deferred to tranche 1 hardening"](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
   into the Gate 1 evaluation pipeline as a fifth criterion. A
   candidate that clears the four existing criteria must ALSO
   improve the portfolio's Sharpe, Calmar, and CDaR when added to
   the book of other-passing sleeves.

**Not in scope** (deferred explicitly — per BRIEF-0002 resolutions
D1–D5 and sub-tranche boundaries):

- Fractional Kelly sizing — deferred to
  [FFL-0001-01](/docs/roadmap/future-features-ledger.md). Tranche
  1 stays on vol-targeted sizing inside each sleeve.
- Options / tail hedging — deferred per
  [FFL-0001-02](/docs/roadmap/future-features-ledger.md).
- Mean-reversion sleeve — deferred per
  [FFL-0001-03](/docs/roadmap/future-features-ledger.md).
- Live drift monitoring (PSI/KS/execution drift/live-vs-backtest
  divergence alarms) — ships in 1.5. 1.4 provides the
  `drift_alarm_live` failure-reason stub only.
- Fractional-Kelly-gate evaluator (`evaluate_kelly_switch_gate`) —
  FFL-0001-01 operational accommodation; not part of 1.4.
- CPCV/PBO topology — deferred to tranche 2 per
  [FFL-0001-06](/docs/roadmap/future-features-ledger.md).
- Any runtime change to the legacy `BaselineLongOnlyPlanner` or
  `runtime_strategy_registry` — coexists untouched, consistent
  with the DESIGN-0014 "two abstractions coexist" stance.

## Prerequisites

- `main` at or beyond the tranche-1.3 merge (`e953b7e`). Brings
  the sleeve package, `SleeveProtocol`, `SleeveContext`,
  `SleeveTrade`, `SleeveFailureReason`,
  `apply_regime_exposure_floor`,
  `build_sleeve_target_weight_history`, `simulate_sleeve_returns`,
  and `build_sleeve_from_candidate`.
- `main` at or beyond the tranche-1.1 merge: purged k-fold CV,
  trials ledger, DSR wiring, cost-drag reporting,
  [`OperatingConstraintBudget`](/src/tradingx/types.py:243).
- **All BRIEF-0002 D1–D5 resolutions remain locked.** This spec
  implements them for the portfolio layer; it does not re-open
  them.
- `StrategyCandidate.sleeve_class_path` already routes the two
  merged sleeves through `_candidate_returns` →
  `simulate_sleeve_returns` → `run_daily_bar_backtest`
  (confirmed at
  [src/tradingx/validation.py:495](/src/tradingx/validation.py:495)).
  1.4 does not change that routing for individual-sleeve
  evaluation; it adds a **portfolio-aware** evaluation pass on top.

## Design principles (pre-empt Codex P1 patterns)

These principles are binding for the implementation plan and for
every work item below. They exist to pre-empt the five review
patterns that have produced P1 findings in previous tranches.

### P1 — Single execution engine

Every function that produces simulated return series in this
tranche MUST call
[`run_daily_bar_backtest`](/src/tradingx/backtest.py:38) for the
fill, cost, and P&L mechanics. No work item in this spec
reimplements next-open timing, cost application, or equity
accumulation. Portfolio construction assembles sleeve target-
weight histories into a **single combined target-weight
DataFrame** (same shape as the one `run_daily_bar_backtest`
already accepts) and hands that DataFrame to the engine. Drawdown
throttles operate on that combined DataFrame before simulation;
they do not intercept inside the engine loop.

### P2 — Preserve contracts; propagate renames

New fields on dataclasses that flow through persisted reports
(today: `EvaluationEvidencePack`, `ValidationCandidateResult`,
`TrialRecord`) MUST appear on **both** the evidence pack AND the
candidate result. Persisted reports are read by downstream tools
that see only `ValidationCandidateResult`; a field added only to
the evidence pack is invisible in reports. Renames propagate to
all consumers. Fields default to `None` so existing persisted
reports deserialize without migration.

### P3 — No silent skips; failures are observable events

Every termination or throttle decision emits a first-class event:

- A sleeve that terminates (operator halt, drift alarm, 3m-Sharpe
  below threshold, regime `stressed`) MUST emit explicit
  `SleeveTrade` entries with the relevant `SleeveFailureReason`
  as the `rationale` — never an empty tuple for an in-universe
  symbol. This is the same contract codified in DESIGN-0014 W1;
  1.4 extends it to cover the three additional failure reasons.
- A portfolio throttle that scales a sleeve's exposure below 1.0
  MUST record a `RiskControlEvent` with `control_type` set to
  one of `mdd_design_throttle`, `cdar_soft_throttle`, or
  `mdd_hard_halt`, and `blocked = (scale == 0.0)`. The event
  flows through `write_risk_control_event` on the operator store
  so the operator dashboard can surface it.
- The 25% hard halt MUST put the runtime host into
  `recovery_required` state and emit a high-severity
  `OperatorAlert`. This is the already-shipped pattern for
  reconciliation divergence at
  [src/tradingx/runtime_host.py:346](/src/tradingx/runtime_host.py:346);
  1.4 reuses it rather than inventing a new halt path.

### P4 — Dimensional correctness

When the spec talks about volatility, it means **annualized σ**
unless explicitly qualified. When it talks about variance it
means **σ²**. The portfolio construction code uses
**correlation** (dimensionless, in `[-1, 1]`) for correlation
caps — not covariance.

All portfolio weights are `Decimal` values in `[0, 1]` that refer
to the portfolio's **equity share**, not quantities. Sleeve
target-weight histories already have this shape. When the spec
says "scale a sleeve by 0.75", it means multiply every sleeve
target-weight value in the combined DataFrame row by 0.75 — not
scale share counts or notional.

Sleeve budgets are **Decimal fractions of portfolio equity**
(e.g., `Decimal("0.5")` for a 50% budget allocation) that sum to
at most 1.0 across all sleeves. Cash is the residual
(`1.0 - sum(sleeve_budgets_after_throttle)`) — never a reserved
input; see §D4 below.

### P5 — Single source of truth for every new field and criterion

For every new dataclass field (e.g.,
`marginal_sharpe_delta`), the spec specifies:

1. The dataclass(es) that carry it (evidence pack AND candidate
   result for persisted fields).
2. The single function that populates it.
3. The defaulting rule (`None` means "not evaluated" — distinct
   from "evaluated and zero").

For every new criterion, the spec specifies: the evaluator
function, the inputs it requires, the threshold, and the
`criterion_id` string. No criterion is added to a gate's tuple
unless its evaluator is implemented in this tranche.

## D4 re-affirmed: cash is a consequence, not a goal

BRIEF-0002 D4 is load-bearing for the portfolio layer. This spec
implements it as follows:

- **No portfolio-level minimum cash buffer.** The portfolio's
  target-weight DataFrame is the raw sum of (sleeve_weight ×
  sleeve_budget_fraction) across sleeves, capped by gross/net
  exposure caps. Cash is whatever is left.
- **Vol-managed beta goes to 0% exposure ONLY when the regime is
  `stressed`.** The DESIGN-0013 regime composite is load-bearing;
  portfolio construction MUST NOT override a sleeve's regime-
  driven flat state. If `VolManagedBetaSleeve` returns a
  `target_weight_of_sleeve_budget` of `0` because
  `apply_regime_exposure_floor` said `stressed`, the portfolio
  layer MUST NOT re-allocate that freed budget to another sleeve
  whose signal would expand. Free budget becomes cash, not a
  feeding ground for siblings.
- **Portfolio-level throttles can only reduce exposure further,
  never above what the sleeves proposed.** The MDD and CDaR
  throttles apply multiplicative scaling factors in `[0, 1]` —
  they cannot go above 1.0.

A dedicated contract test on the portfolio construction module
verifies that a `stressed` regime produces zero exposure for the
vol-managed-beta sleeve in the combined DataFrame, regardless of
what the trend sleeve proposes.

## Architecture overview

### New modules

1. **`src/tradingx/portfolio/__init__.py`** — package init.
2. **`src/tradingx/portfolio/blueprint.py`** —
   `PortfolioBlueprint` dataclass: per-sleeve risk budgets,
   correlation caps, gross/net caps, turnover-budget metadata.
3. **`src/tradingx/portfolio/construction.py`** —
   `build_portfolio_target_weight_history` and
   `simulate_portfolio_returns`. Pure functions that combine
   sleeve target-weight histories and hand the combined
   DataFrame to `run_daily_bar_backtest`.
4. **`src/tradingx/portfolio/throttle.py`** — drawdown-throttle
   computation: `apply_mdd_design_throttle`,
   `apply_cdar_soft_throttle`. Pure functions that operate on
   target-weight history + equity curve / return history.
5. **`src/tradingx/portfolio/hard_halt.py`** —
   `PortfolioHardHaltController`, the runtime controller that
   reads the equity curve, detects 25% MDD breach, and drives
   the runtime host into `recovery_required`.
6. **`src/tradingx/portfolio/sleeve_runtime.py`** —
   `SleeveRuntimeController`: owns sleeve-termination decisions
   (operator halt, drift alarm stub, 3m-Sharpe check), emits
   explicit `SleeveTrade` termination events.

### New dataclasses (see §W1 for full shapes)

- `PortfolioBlueprint` (config).
- `PortfolioThrottleState` (frozen, per-bar): carries the
  throttle scaling factor, the breach type, and the
  `RiskControlEvent` reference. Stored alongside the combined
  target-weight DataFrame as a sidecar `pd.Series` of throttle
  scales indexed by date.
- `PortfolioSimulationResult` — thin wrapper over
  `DailyBarBacktestResult` adding the throttle-scale series and
  the per-sleeve contribution attribution (per-sleeve return
  series pre- and post-throttle).

### Modified files

- `src/tradingx/types.py` — add
  `marginal_sharpe_delta: Decimal | None = None`,
  `marginal_calmar_delta: Decimal | None = None`,
  `marginal_cdar_delta: Decimal | None = None` to **both**
  `EvaluationEvidencePack` AND `ValidationCandidateResult`
  (per P2 and P5). Defaults are `None` so legacy persisted
  payloads continue to deserialize unchanged.
- `src/tradingx/validation.py` — add
  `evaluate_marginal_portfolio_contribution`; extend
  `_build_gate1_candidate_result` to call it; extend
  `build_gate_report` to perform the two-pass evaluation
  (per-candidate first, then portfolio-aware marginal pass).
- `src/tradingx/evaluation.py` — extend `evaluate_candidate` to
  accept optional marginal-delta inputs and carry them onto the
  evidence pack. The function remains unchanged for callers that
  don't supply them (evaluators other than Gate 1 with
  portfolio awareness).
- `src/tradingx/runtime_host.py` — add
  `trigger_hard_halt(reason: str) -> WebActionResult` that
  transitions state into `recovery_required` and surfaces the
  reason through `last_error`. Reuses the existing
  reconciliation-divergence clearance path.
- `src/tradingx/operator_control.py` — operator-halt surface for
  individual sleeves. Reuses the existing operator control
  pattern; a new store key `sleeve_halts/<sleeve_id>.json` records
  the halt.
- `src/tradingx/portfolio_construction.py` — legacy candidate
  path is untouched. The new `src/tradingx/portfolio/*` package
  is the home for 1.4 work. Two package names coexist during
  this tranche; 1.5 or tranche 2 may consolidate them.
- New tests under `tests/unit/test_portfolio_*.py` and one
  integration test `tests/integration/test_portfolio_end_to_end.py`.

### Not touched in this tranche

- `runtime_strategy_registry.py`, `baseline_runtime_planner.py`
  — same rationale as DESIGN-0014 §"Not touched". The sleeve
  protocol and the runtime planner protocol continue to coexist.
- `portfolio_construction.py` — the legacy candidate-weight path.
  The new `portfolio/` package replaces its role for sleeve-
  based candidates; the legacy path still supports the baseline
  candidate and any future non-sleeve candidate. Consolidation
  deferred.
- `BenchmarkStack.materialize` — benchmark-stack generation is
  unchanged. Gate 1 still benchmarks candidate-and-portfolio
  returns against the three-tier stack materialized once per
  gate report.

## Work items

### W1 — `PortfolioBlueprint` + risk-budget config

**Files:**
- Create: `src/tradingx/portfolio/__init__.py`
- Create: `src/tradingx/portfolio/blueprint.py`
- Create: `tests/unit/test_portfolio_blueprint.py`

**Contract:**

```python
# src/tradingx/portfolio/blueprint.py

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class SleeveRiskBudget:
    """Per-sleeve risk-budget configuration."""

    sleeve_id: str
    budget_fraction_of_equity: Decimal  # [0, 1], sums with peers <= 1
    max_correlation_with_other_sleeves: Decimal  # [0, 1], e.g. 0.85
    # The sleeve is *allowed* to run at 100% of budget; lower
    # fractions are imposed only by throttles. No floor below 0.


@dataclass(frozen=True)
class PortfolioBlueprint:
    """Portfolio-level construction parameters.

    Per-sleeve budgets sum to <= 1.0 of portfolio equity. Remaining
    fraction is residual cash per D4 ("cash is a consequence").
    """

    blueprint_id: str
    sleeve_budgets: tuple[SleeveRiskBudget, ...]
    max_gross_exposure: Decimal = Decimal("1.0")
    max_net_exposure: Decimal = Decimal("1.0")
    mdd_design_target: Decimal = Decimal("0.15")  # from ADR-0021
    mdd_hard_halt: Decimal = Decimal("0.25")  # from ADR-0021
    cdar_confidence: Decimal = Decimal("0.95")
    cdar_soft_throttle_threshold: Decimal = Decimal("0.08")
    annualized_turnover_budget: Decimal = Decimal("3.0")  # 300%, D3
    sleeve_three_month_sharpe_floor: Decimal = Decimal("0.0")

    def __post_init__(self) -> None:
        budget_sum = sum(
            (sb.budget_fraction_of_equity for sb in self.sleeve_budgets),
            start=Decimal("0"),
        )
        if budget_sum > Decimal("1.0"):
            raise ValueError(
                f"sleeve budgets sum to {budget_sum}, must be <= 1.0"
            )
```

**Tests cover:**

- Blueprint accepts two `SleeveRiskBudget` rows summing to 1.0
  (exact match allowed — zero cash is permitted by D4).
- Blueprint rejects sleeve budgets summing to > 1.0.
- Blueprint accepts budgets summing to < 1.0 (residual cash).
- Frozen-dataclass semantics; round-trip equality.
- Default values match ADR-0021 design-target and halt values.

**Out of scope (deferred):** dynamic reallocation of freed budget
between sleeves; any "borrow from cash" behavior. Per D4, freed
budget is residual cash, not feeding ground.

### W2 — Portfolio target-weight construction

**Files:**
- Create: `src/tradingx/portfolio/construction.py`
- Create: `tests/unit/test_portfolio_construction.py`

**Contract:**

```python
# src/tradingx/portfolio/construction.py

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from tradingx.backtest import DailyBarBacktestResult, run_daily_bar_backtest
from tradingx.costs import CostModelConfig
from tradingx.portfolio.blueprint import PortfolioBlueprint
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
    portfolio target-weight DataFrame, applying risk budgets,
    correlation caps, and gross/net exposure caps.

    Per §P1: returns a DataFrame in the exact shape
    run_daily_bar_backtest expects (dates x symbols, float,
    column-per-symbol).

    Per §P4: cells are **weights** (fractions of portfolio
    equity), not quantities, not notionals.

    Per D4: if a sleeve's target-weight row is all-zero
    (regime stressed), its budget is **not** redistributed to
    other sleeves. Residual becomes cash.

    Algorithm:
    1. For each sleeve, call build_sleeve_target_weight_history
       to get per-sleeve target-weight DataFrame W_s (dates x
       sleeve.allowed_instruments).
    2. Build portfolio DataFrame P with the union of all
       allowed_instruments columns, indexed by the common bar
       index.
    3. For each date:
       a. For each sleeve, compute
          sleeve_contribution = W_s[date] * budget_fraction_s.
       b. Sum across sleeves into P[date, symbol]
          (per-symbol sum, because two sleeves may hold SPY).
       c. Apply correlation cap: if the post-sum weight on any
          symbol held by multiple sleeves exceeds the
          configured max_correlation weight, scale those
          contributions proportionally.
       d. Cap P[date] at max_gross_exposure. Scaling is
          uniform across the row so relative allocations are
          preserved.
       e. (Net-exposure cap is a no-op in tranche 1 because
          all sleeves are long-only; enforced symbolically
          for future sleeve families.)
    4. Return P (does not simulate; that is W3).
    """


def simulate_portfolio_returns(
    sleeves: tuple[SleeveProtocol, ...],
    *,
    blueprint: PortfolioBlueprint,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict[date, RegimeSnapshot],
    cost_model_config: CostModelConfig | None = None,
    throttle_controller: "DrawdownThrottleController | None" = None,
) -> "PortfolioSimulationResult":
    """Build the combined target-weight DataFrame (via
    build_portfolio_target_weight_history), optionally apply the
    drawdown throttle controller (W4+W5), and hand the final
    DataFrame to run_daily_bar_backtest.

    Per §P1: this function does NOT simulate fills, costs, or
    P&L. It only composes target weights and delegates to the
    engine.

    Returns PortfolioSimulationResult wrapping the
    DailyBarBacktestResult, the throttle-scale sidecar Series,
    and per-sleeve contribution attribution.
    """
```

**Correlation-cap semantics:**

In tranche 1, both `TrendSleeve` and `VolManagedBetaSleeve` may
hold SPY. The correlation cap bounds the combined per-symbol
weight. Concretely:

- For each symbol held by `k ≥ 2` sleeves with contributions
  `c_1, …, c_k` (each = sleeve_weight × budget_fraction), the
  combined weight is `sum(c_i)`.
- The cap is `blueprint.max_gross_exposure × max_{i}(c_i.max_correlation_with_other_sleeves)`
  — interpreted as "the combined per-symbol weight cannot exceed
  the strictest sleeve's correlation-cap fraction of gross
  exposure." If the combined weight exceeds this cap, the
  contributions are scaled proportionally to land exactly at the
  cap, preserving relative sleeve intents.

This is a judgment call; Codex may flag it. If so, we drop it to
a simpler rule: "the combined weight on any symbol cannot exceed
`max_gross_exposure × 0.85`" as a single per-symbol cap. The
spec's correlation-cap math is a sharper version; if Codex
prefers the flat rule, we simplify in the implementation plan
and amend this spec.

**Tests cover:**

- Two sleeves with identical SPY weights combine to the sum, not
  the max, up to the correlation cap.
- A sleeve with all-zero target row (stressed regime) does not
  have its budget redistributed (D4).
- Per-sleeve budget fractions apply correctly (0.5 + 0.5 =
  identical coverage; 0.7 + 0.3 biases toward first sleeve).
- Output DataFrame passes `_validate_inputs` checks that
  `run_daily_bar_backtest` applies (columns match
  `bars_by_symbol` keys, aligned index).
- `simulate_portfolio_returns` without a throttle controller
  produces identical results to a direct
  `run_daily_bar_backtest` call on the same combined DataFrame
  (single-execution-engine guarantee).

### W3 — MDD design throttle (15% proportional)

**Files:**
- Create: `src/tradingx/portfolio/throttle.py`
- Create: `tests/unit/test_portfolio_throttle.py`

**Contract:**

```python
# src/tradingx/portfolio/throttle.py (partial; see also W4)

from decimal import Decimal
from typing import Final

import pandas as pd  # type: ignore[import-untyped]

from tradingx.portfolio.blueprint import PortfolioBlueprint


MDD_DESIGN_THROTTLE_FLOOR: Final[Decimal] = Decimal("0.0")


def apply_mdd_design_throttle(
    *,
    target_weights: pd.DataFrame,
    trailing_drawdown_series: pd.Series,  # indexed by target_weights.index
    blueprint: PortfolioBlueprint,
) -> tuple[pd.DataFrame, pd.Series]:
    """For each bar, compute a scaling factor in [0, 1] based on
    trailing drawdown:

        if dd <= design:     scale = 1.0
        elif dd >= halt:     scale = 0.0
        else:                scale = (halt - dd) / (halt - design)

    where design = blueprint.mdd_design_target (0.15) and
    halt = blueprint.mdd_hard_halt (0.25). Scale is applied
    multiplicatively to every weight in the target_weights row.

    Returns (throttled_target_weights, scale_series).

    Per §P4: trailing_drawdown_series values are positive
    fractions (e.g., 0.17 for -17% dd), NOT raw returns.

    Per §P3: for each bar with scale < 1.0, a RiskControlEvent
    is logged upstream by simulate_portfolio_returns when this
    is used inside the simulation path (not by this function).

    Pure function; no I/O.
    """
```

**Drawdown bookkeeping.** The trailing drawdown series is
computed on the portfolio's simulated equity curve **up to and
including the prior bar** — the throttle applies at the next-open
rebalance, consistent with
[backtest.py:38](/src/tradingx/backtest.py:38)'s execution model.
Using the current bar's equity would be look-ahead; using the
prior bar's equity is the correct next-open semantics.

**Tests cover:**

- dd = 10% → scale = 1.0.
- dd = 15% → scale = 1.0 (boundary — throttle begins **above**
  the design target, not at it).
- dd = 20% → scale = 0.5.
- dd = 25% → scale = 0.0.
- dd > 25% → scale = 0.0 (no negative scale).
- Scaling is uniform across all symbols in the row.
- Function does not emit events (that is the
  simulate-portfolio layer's job).

### W4 — CDaR soft-throttle

**Files:**
- Modify: `src/tradingx/portfolio/throttle.py`
- Extend: `tests/unit/test_portfolio_throttle.py`

**Contract:**

```python
def apply_cdar_soft_throttle(
    *,
    target_weights: pd.DataFrame,
    trailing_cdar_series: pd.Series,  # CDaR@95% per bar
    blueprint: PortfolioBlueprint,
) -> tuple[pd.DataFrame, pd.Series]:
    """For each bar, compute a scaling factor in [0, 1] based on
    trailing CDaR@95%:

        if cdar <= threshold:           scale = 1.0
        elif cdar >= 2 * threshold:     scale = 0.5
        else:                           scale linearly from 1.0 to 0.5

    where threshold = blueprint.cdar_soft_throttle_threshold
    (0.08 default per OperatingConstraintBudget).

    The CDaR throttle is a SOFT throttle — it caps the scale at
    0.5, not 0.0. Its purpose is to dampen exposure BEFORE the
    hard 25% MDD halt fires, not to replace the hard halt.

    Pure function. Composes multiplicatively with the MDD
    design throttle: final_scale = mdd_scale * cdar_scale.

    Per §P3, compose-and-log at the simulation layer.
    """
```

**Composition rule.** The two throttles apply
multiplicatively — if MDD throttle says 0.5 and CDaR throttle
says 0.75, the final scale is 0.375. This is intentional: CDaR
dampening piles on MDD dampening. Both scales are in `[0, 1]` so
the composed scale is bounded below by `0`.

**Tests cover:**

- cdar = 5% → scale = 1.0.
- cdar = 8% → scale = 1.0 (boundary — soft throttle begins
  **above** the threshold).
- cdar = 12% → scale = 0.75 (halfway).
- cdar = 16% → scale = 0.5 (floor).
- Floor is 0.5, not 0.0 (by design).
- Multiplicative composition with MDD throttle is associative
  and commutative.

### W5 — 25% MDD runtime hard halt wired to operator clearance

**Files:**
- Create: `src/tradingx/portfolio/hard_halt.py`
- Modify: `src/tradingx/runtime_host.py` (add
  `trigger_hard_halt`)
- Modify: `src/tradingx/opportunity.py` (entry-gate check before
  emitting a selection)
- Create: `tests/unit/test_portfolio_hard_halt.py`
- Modify: `tests/unit/test_runtime_host.py`
- Modify: `tests/unit/test_opportunity.py`

**Corrected model of the existing clearance flow.** Codex's
round-1 review flagged an overclaim in the first draft: the
current `LocalRuntimeHostManager` only **records** state. It does
not halt an already-running service loop. New entries continue
to flow from the service manager until the service is actually
stopped. The correct wiring therefore has **three** pieces, all
of which must land together for the 25% halt to be meaningful at
runtime:

1. A **service stop**. `trigger_hard_halt` MUST call
   `self._service_manager.stop()` so the live trading loop
   actually exits. Setting `recovery_required` without stopping
   the service stops nothing.
2. A **state transition** into `recovery_required` with the
   halt reason in `last_error`. This lights up the operator
   surface and enables `request_clearance()` to engage.
3. An **entry gate** (defense in depth) that any intent-
   producing layer consults before emitting new trades, so that
   a race between `stop()` returning and the service loop
   draining its last tick cannot slip an entry through.

The existing `_pending_start_request` carries the original
`start()` parameters; it is never cleared by `stop()` or by
state transitions, so `request_clearance()` can drive
`_run_clearance_reconciliation`, which already restarts the
service via `service_manager.start(_pending_start_request)`
after successful reconciliation
([runtime_host.py:316](/src/tradingx/runtime_host.py:316)). The
"reuse the existing clearance flow" claim in this spec is
grounded on that restart path — it is load-bearing that the
service is stopped FIRST by `trigger_hard_halt` so the restart
is a valid service-manager operation (stop → start) rather than
a double-start (which the service manager would reject as
`blocked`).

**Runtime-host change:**

```python
# src/tradingx/runtime_host.py (addition)

SERVICE_STOP_SUCCESS_STATUSES: Final[frozenset[str]] = frozenset(
    {"accepted", "completed"}
)


def trigger_hard_halt(self, *, reason: str) -> WebActionResult:
    """Halt the runtime because a hard risk limit was breached.

    Three steps, in this order (ordering is load-bearing):

    1. Stop the service via self._service_manager.stop() and
       verify stop_result.status is in
       SERVICE_STOP_SUCCESS_STATUSES. This is what actually
       prevents new entries; flipping status alone does not,
       and a non-success WebActionResult means the service
       did NOT stop (e.g., `blocked`, `error`).
    2. Set host state to recovery_required with reason stored
       on last_error. This lights up the operator dashboard
       and enables request_clearance() to engage.
    3. Emit an OperatorAlert(severity=critical,
       category=portfolio_hard_halt) via the alert gateway.

    _pending_start_request is preserved from the original
    start() call, so a subsequent successful request_clearance
    will re-invoke service_manager.start(...) from the stored
    parameters (see _run_clearance_reconciliation in this same
    module). The stop-then-start sequence is a valid service-
    manager operation; a naive recovery_required-without-stop
    would force the clearance path to hit service.start() on an
    already-running service and come back with `blocked`.

    Failure modes:
    - service_manager.stop() raises → transition to `halted`
      (terminal error state) with last_error carrying both the
      halt reason and the exception; return status=`error`.
    - service_manager.stop() returns a WebActionResult with a
      status NOT in SERVICE_STOP_SUCCESS_STATUSES → same
      handling as the exception path: transition to `halted`,
      last_error carries the halt reason and the stop result's
      message/status, return status=`error`. An unstoppable or
      blocked service is a worse failure mode than a halted
      one and needs operator attention; we do NOT leave state
      unchanged, and we do NOT claim `accepted`.

    Idempotent: calling when status is already
    recovery_required is a no-op and does not re-stop the
    service.

    Returns WebActionResult(status=accepted) only when the
    service stop actually succeeded AND state transitioned to
    recovery_required; status=noop on idempotent call;
    status=error on any stop failure.
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
        # Step 1: actually stop the service loop.
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
        # Step 2: service is confirmed stopped; record the halt.
        self._set_state(
            status="recovery_required",
            status_reason=(
                "Hard halt triggered: "
                + reason
                + ". Service stopped; operator clearance required."
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

**Entry-gate helper (defense-in-depth):**

```python
# src/tradingx/portfolio/hard_halt.py (partial)

from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore


def is_portfolio_hard_halted(operator_store_root: Path) -> bool:
    """Read the runtime host state artifact and return True if
    status == recovery_required AND last_error begins with the
    portfolio_hard_halt reason prefix (so reconciliation-driven
    recovery_required is distinguished from halt-driven).

    The opportunity planner (and any future intent producer)
    MUST call this before emitting a non-empty selection. If it
    returns True, the producer returns an empty selection with
    `decision_reason = 'hard_halt_active'` and emits a
    RiskControlEvent with control_type='mdd_hard_halt',
    blocked=True for the operator dashboard.

    The check is a file-read, not an in-process call, so it
    works regardless of whether the intent producer lives in
    the same process as the runtime host. It is cheap and
    idempotent.
    """
```

The `opportunity.py` producer change is a 1–2 line insertion at
the top of `plan(...)` that returns an empty
`OpportunitySelectionRecord` when `is_portfolio_hard_halted` is
True. No other intent producers exist in tranche-1 scope; future
producers inherit the gate by calling the same helper.

**Controller contract:**

```python
# src/tradingx/portfolio/hard_halt.py (continued)

from decimal import Decimal
from typing import Protocol

import pandas as pd  # type: ignore[import-untyped]

from tradingx.portfolio.blueprint import PortfolioBlueprint
from tradingx.runtime_host import LocalRuntimeHostManager
from tradingx.types import OperatorAlert, WebActionResult


class OperatorAlertGatewayProtocol(Protocol):
    def publish(self, alert: OperatorAlert) -> None: ...


class PortfolioHardHaltController:
    """Reads the portfolio equity curve, detects 25% MDD breach,
    calls runtime_host.trigger_hard_halt, emits an OperatorAlert.

    Pure-enough: the only side effects are the runtime-host
    call and the alert-gateway call, both injected so tests can
    drive them deterministically.
    """

    def __init__(
        self,
        *,
        runtime_host: LocalRuntimeHostManager,
        alert_gateway: OperatorAlertGatewayProtocol,
        blueprint: PortfolioBlueprint,
    ) -> None:
        self._runtime_host = runtime_host
        self._alert_gateway = alert_gateway
        self._blueprint = blueprint
        self._halt_latched = False

    def check(
        self,
        *,
        equity_curve: pd.Series,
    ) -> WebActionResult | None:
        """Compute trailing drawdown; if it meets or exceeds
        blueprint.mdd_hard_halt, trigger the halt (once) via
        runtime_host.trigger_hard_halt and publish an
        OperatorAlert. The halt is latched — once triggered,
        subsequent checks are no-ops until the operator clears
        (state transitions back to `nominal`) and the
        controller is reset externally via reset().
        """

    def reset(self) -> None:
        """Clear the latch. Intended to be called by the
        operator-clearance reconciliation path once state has
        returned to `nominal`; not by the controller itself.
        """
```

**Operator-alert shape:** severity `critical`, category
`portfolio_hard_halt`, summary referencing the observed
drawdown and the blueprint.

**Tests cover:**

- Equity curve with trailing MDD < 25% → no halt, returns None.
- Equity curve with trailing MDD == 25% → halt triggers exactly
  once; `service_manager.stop()` is called; its
  `WebActionResult` is checked against
  `SERVICE_STOP_SUCCESS_STATUSES`; runtime host transitions to
  `recovery_required`; alert gateway publishes a `critical`
  alert.
- Service-stop call happens **before** the state transition
  (ordering regression test using a mock service manager that
  records call order).
- `service_manager.stop()` raises → state transitions to
  `halted` (terminal error); `last_error` records both the
  halt reason and the stop exception; return status=`error`.
- `service_manager.stop()` returns a `WebActionResult` with
  status ∉ `SERVICE_STOP_SUCCESS_STATUSES` (e.g., `blocked`
  or `error`) → state transitions to `halted`; `last_error`
  records the halt reason and the stop result's
  status + message; return status=`error`; state does NOT
  flip to `recovery_required` and the controller does NOT
  claim `accepted`. This is the explicit Codex-round-2
  regression: any non-success stop outcome is a halt failure,
  not a successful halt.
- Second call with same breach → no-op (latched); service
  manager's stop is NOT called again.
- Controller `reset()` + new check below 25% → no halt.
- Runtime host state after successful halt:
  `status == "recovery_required"`, `last_error` contains the
  halt reason text.
- `is_portfolio_hard_halted(operator_store_root)` returns True
  when state file reports `recovery_required` AND the halt-
  reason prefix is present; returns False for reconciliation-
  driven `recovery_required` (so reconciliation halts don't
  accidentally gate unrelated entry paths).
- Integration with `request_clearance()`: after a halt-driven
  stop, `_pending_start_request` is intact; a subsequent
  `request_clearance()` call takes the host through
  `_run_clearance_reconciliation`, which successfully restarts
  the service via `service_manager.start(_pending_start_request)`
  and lands the host at `nominal`.
- Entry-gate regression (in-loop case): when the service loop
  calls `opportunity.plan(...)` after halt, the planner
  returns an `OpportunitySelectionRecord` with an empty
  `ranked_opportunities` tuple, `selected_symbol=""`, and
  `decision_reason='hard_halt_active'`. The gate is at the
  planner's entry; upstream reads performed by
  `_bootstrap_and_start` (warmup, portfolio gateway) are NOT
  re-run during the gated call — those inputs are passed in
  by the caller and the planner short-circuits before using
  them. The gate's guarantee is "no non-empty selection is
  emitted while halted," not "no upstream work happens" (which
  is the caller's responsibility, ultimately enforced by the
  fact that the service loop itself is stopped).

**Why this wiring closes the P1 gap.** Today
`max_drawdown_halt = 0.25` lives on `OperatingConstraintBudget`
and is emitted in benchmark-stack payloads
([validation.py:800-900](/src/tradingx/validation.py)) but no
runtime code reads it. 1.4 makes the value **load-bearing** in
three layered ways: `PortfolioHardHaltController` consumes it
from the blueprint; `trigger_hard_halt` actually stops the
service (not just state); the `is_portfolio_hard_halted` entry
gate catches any intent producer that would otherwise race the
service-stop. The existing operator-clearance path in
`_run_clearance_reconciliation` then handles the restart cleanly
because `_pending_start_request` was preserved. No new clearance
pathway is invented; the stop-then-clearance sequence just feeds
the existing flow with valid inputs.

### W6 — Sleeve termination rules (runtime-observable)

**Files:**
- Create: `src/tradingx/portfolio/sleeve_runtime.py`
- Modify: `src/tradingx/operator_control.py` (new sleeve-halt
  store keys)
- Create: `tests/unit/test_sleeve_runtime_controller.py`
- Modify: `tests/unit/test_operator_control.py`

**Contract:**

```python
# src/tradingx/portfolio/sleeve_runtime.py

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Protocol

import pandas as pd  # type: ignore[import-untyped]

from tradingx.sleeves.base import SleeveProtocol
from tradingx.trials import TrialsLedger
from tradingx.types import (
    SleeveContext,
    SleeveFailureReason,
    SleeveTrade,
)


class SleeveOperatorHaltStoreProtocol(Protocol):
    def is_halted(self, *, sleeve_id: str) -> bool: ...


class RollingWindowSource(str, Enum):
    """Where SleeveRuntimeController reads sleeve Sharpe history.

    TRIAL_SUMMARY  — 1.4 default. Reads per-trial summary
                     observed_sharpe_net_of_costs from the
                     trials ledger, filtered to trial windows
                     >= three_month_window_days.
    LIVE_DAILY_RETURNS — 1.5 future. Reads the live per-sleeve
                     daily return series (not yet shipped).
    """

    TRIAL_SUMMARY = "trial_summary"
    LIVE_DAILY_RETURNS = "live_daily_returns"


@dataclass(frozen=True)
class SleeveRuntimeConfig:
    three_month_sharpe_floor: Decimal  # from blueprint
    three_month_window_days: int = 63  # ~3 trading months
    trial_lookback: int = 3  # consecutive trials below floor
    rolling_window_source: RollingWindowSource = (
        RollingWindowSource.TRIAL_SUMMARY
    )


class SleeveRuntimeController:
    """Wraps a sleeve with runtime termination rules.

    When plan_for_bar is called, the controller first checks the
    three termination sources in precedence order:

    1. operator_halt_store.is_halted(sleeve_id) → emit hold-or-
       sell trades with rationale = HALT_BY_OPERATOR.
    2. drift_alarm_gateway.has_alarm(sleeve_id) → emit with
       rationale = DRIFT_ALARM_LIVE. Gateway is a stub in 1.4
       (always returns False); 1.5 fills it in.
    3. trial-summary Sharpe gate (see below) → emit with
       rationale = SLEEVE_SHARPE_BELOW_THRESHOLD_6M (the 1.3
       constant is reused despite the window-name mismatch;
       see "Constant-naming note" below).

    If none fire, delegates to sleeve.plan_for_bar.

    Termination produces explicit SleeveTrade entries with
    side="sell" (if current weight > 0) or side="hold" (if no
    current weight), target_weight_of_sleeve_budget=0, and the
    appropriate rationale — never an empty tuple (§P3).
    """

    def __init__(
        self,
        *,
        wrapped_sleeve: SleeveProtocol,
        operator_halt_store: SleeveOperatorHaltStoreProtocol,
        drift_alarm_gateway: "DriftAlarmGatewayProtocol | None",
        trials_ledger: TrialsLedger | None,
        config: SleeveRuntimeConfig,
    ) -> None:
        ...

    def plan_for_bar(
        self, context: SleeveContext
    ) -> tuple[SleeveTrade, ...]:
        ...
```

**Operator-halt surface.** A new store key:

```
operator-control/
    sleeve_halts/
        trend-following-v1.json   # {"halted": true, "reason": "...", "at_utc": "..."}
        vol-target-v1.json
```

Operators set the halt via a new operator-control action
`halt_sleeve(sleeve_id, reason)` and clear it via
`resume_sleeve(sleeve_id)`. Both emit audit entries consistent
with the existing operator-control pattern.

**Trial-summary Sharpe gate (replaces the original round-1
"3-month rolling Sharpe" phrasing).** Codex's round-1 review
correctly pointed out that
[TrialsLedger](/src/tradingx/trials.py:15) stores per-trial
summary Sharpes on
[`TrialRecord.observed_sharpe_net_of_costs`](/src/tradingx/types.py:87),
not daily return observations, so a rolling Sharpe cannot be
reconstructed from the ledger and a Sharpe-of-Sharpes is a
different statistic. The 1.4 gate is reframed as a **trial-
summary gate** whose input is exactly what the ledger stores:

- Scan the trials ledger for records matching the sleeve's
  `candidate_id` (= `sleeve_id`).
- Keep only records whose trial window (`window_end_utc -
  window_start_utc`) is at least `three_month_window_days`
  trading days long — trials shorter than 3 months are rejected
  as evidence for a 3-month-scale health check.
- From those, take the most recent **N** trials (default:
  `trial_lookback = 3`). If fewer than `trial_lookback` exist,
  the check is **skipped** (insufficient evidence — same
  pending semantics as `out_of_sample_profile` in Gate 1).
- If every one of those trials has
  `observed_sharpe_net_of_costs < config.three_month_sharpe_floor`,
  the gate fires. Consecutive failures (not a running mean)
  protect against a single-trial outlier.

This is an honest trial-summary statistic: "the sleeve has
produced `trial_lookback` consecutive ≥ 3-month-window
evaluations below the floor." It is NOT a rolling daily-return
Sharpe; that genuinely requires live per-sleeve daily return
history, which 1.5 ships alongside the live drift monitoring
(PSI / KS / execution drift / live-vs-backtest P&L divergence).
When 1.5 lands, W6's gate can be upgraded to a real rolling-
window Sharpe on live returns; the `SleeveRuntimeConfig`
surface remains stable across that upgrade (the `config`
dataclass gains a `rolling_window_source` enum; 1.4 defaults to
`TRIAL_SUMMARY`, 1.5 defaults to `LIVE_DAILY_RETURNS`).

**Constant-naming note (rename deferred).** The 1.3 constant
[`SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M`](/src/tradingx/types.py:278)
carries a `_6M` suffix but the 1.4 gate operates on a 3-month
window. The first-round draft of this spec proposed renaming
the constant to drop the suffix; after checking cross-
references, the rename was dropped because the string is
referenced by [DESIGN-0014 §W1](/docs/superpowers/specs/2026-04-21-tranche-1-3-sleeves-design.md)
and the shipped [tranche-1.3 plan](/docs/superpowers/plans/2026-04-21-tranche-1-3-sleeves-plan.md).
Renaming in 1.4 would stale-reference active draft documents
and expand scope beyond this tranche. 1.4 **keeps the constant
stable** at `SLEEVE_SHARPE_BELOW_THRESHOLD_6M` and accepts the
window-name-vs-rationale-string inconsistency as a known
imperfection. A documentation-normalization pass in a later
tranche (or when DESIGN-0014 promotes from draft to active)
may normalize the name. Production code today does not emit
this rationale anywhere (confirmed by grep — the constant is
defined in `types.py` and pinned by `tests/unit/test_types.py`
but never produced), so the first emission happens in 1.4's
`SleeveRuntimeController` and the string is what Codex review
implemented it as.

**Tests cover:**

- No halts, no alarm, ledger ok → controller delegates and
  returns exactly the sleeve's own output.
- Operator halt → all in-universe symbols produce explicit
  termination trades with `HALT_BY_OPERATOR` rationale.
- Drift alarm gateway returns True → same behavior with
  `DRIFT_ALARM_LIVE` rationale (1.5 will provide a real
  gateway; 1.4 tests use a stub).
- Trials ledger with `trial_lookback` consecutive trials
  (window ≥ 63 days each) all below floor → termination with
  `SLEEVE_SHARPE_BELOW_THRESHOLD_6M` rationale (constant reused
  from 1.3; see "Constant-naming note" above).
- Trials ledger with `trial_lookback - 1` consecutive failures
  followed by one passing trial → no fire (single pass resets
  the streak; consecutive is the gate).
- Trials ledger with windows shorter than
  `three_month_window_days` → those trials are filtered out
  and do not count toward the lookback.
- Trials ledger with fewer than `trial_lookback` qualifying
  trials → check is skipped (pending semantics).
- Config with `rolling_window_source = LIVE_DAILY_RETURNS` in
  1.4 → raises `NotImplementedError` with a clear message
  pointing at 1.5 (guard rail against premature configuration).
- Precedence order: if multiple conditions fire, operator halt
  wins (operator authority is absolute), then drift alarm, then
  trial-summary gate. Rationale reflects the winning condition
  only.

### W7 — Marginal-portfolio-contribution Gate 1 criterion

**Files:**
- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/evaluation.py`
- Modify: `src/tradingx/validation.py`
- Create: `tests/unit/test_marginal_portfolio_contribution.py`
- Modify: `tests/unit/test_validation.py`

**Contract (criterion evaluator):**

```python
# src/tradingx/validation.py (addition)

from decimal import Decimal

from tradingx.stats import conditional_drawdown_at_risk, max_drawdown
from tradingx.types import ValidationCriterionResult


def evaluate_marginal_portfolio_contribution(
    *,
    candidate_returns: tuple[Decimal, ...],
    portfolio_without_candidate_returns: tuple[Decimal, ...],
    portfolio_with_candidate_returns: tuple[Decimal, ...],
) -> ValidationCriterionResult:
    """Evaluate whether adding the candidate to the book improves
    Sharpe, Calmar, and CDaR of the portfolio.

    Per ADR-0022 §"Deferred to tranche 1 hardening", this
    criterion supplements — does not replace — the four
    operational Gate 1 criteria. It is a HARD-PASS criterion:
    failure of this criterion fails Gate 1 for the candidate.

    Pass rule (all must hold):
        sharpe_with > sharpe_without
        calmar_with > calmar_without
        cdar_with  <= cdar_without   (CDaR is a bad — lower is better)

    Returns ValidationCriterionResult with criterion_id =
    "marginal_portfolio_contribution" and details containing the
    three observed deltas. All three inputs are required series
    (not Optional); the two-sleeve book-construction rule in
    W7 guarantees both portfolio series are always computable.
    """
```

**Integration into the Gate 1 report — narrowed to the two-
sleeve case in 1.4.** Codex's round-1 review flagged that the
first-draft pseudocode ("evaluate each candidate against other
pass1 passers") is ambiguous for 3+ sleeves: a candidate judged
marginally positive against `{A, B}` may not be positive
against `{A}` alone if `B` later fails marginal contribution
and gets removed from the book. 1.4 explicitly **restricts the
marginal criterion to the two-sleeve case** (exactly the two
shipped mandatory sleeves with non-null `sleeve_class_path`:
`trend-following-v1` and `vol-target-v1`). This keeps the book-
construction rule deterministic:

> **Book-construction rule (1.4 two-sleeve case).** For each of
> the two candidates, the reference book is exactly the OTHER
> mandatory sleeve-backed candidate in
> `build_mandatory_candidate_registry()` that has
> `sleeve_class_path is not None`. That other candidate's pass1
> status is NOT consulted — the book is fixed by the registry,
> not by the gate outcome of its sibling. The marginal
> criterion asks "does adding candidate X to a book consisting
> of sibling Y strictly improve portfolio Sharpe, Calmar, and
> CDaR?", regardless of whether Y itself passes pass1. This is
> what makes the rule deterministic in tranche 1.4.

When a future sub-tranche adds a third sleeve-backed candidate,
the two-sleeve simplification breaks down and the marginal
criterion needs a book-construction rule valid for 3+
candidates. Three plausible rules (all deferred):

- **Fixed-point iteration.** Run pass2; drop failers; re-run
  pass2 on the reduced book; iterate until the set stabilizes.
  Deterministic but expensive.
- **Stage-ordered admission.** Evaluate candidates in a fixed
  deterministic order (e.g., by registry order); admit
  marginally-positive candidates into a growing book; later
  candidates are evaluated against the current admitted book.
  Deterministic and cheap; introduces order sensitivity.
- **Registry-pinned book.** The book is the set of
  registry-listed sleeve-backed candidates minus the one
  under evaluation — `sleeve_class_path is not None` candidates
  only. Deterministic, order-insensitive, does NOT re-evaluate
  after drops. This is the simplest extension of the 1.4 two-
  sleeve rule to 3+ sleeves.

The decision between these three is deferred to the tranche
that introduces a third sleeve-backed candidate (per
[FFL-0001-03](/docs/roadmap/future-features-ledger.md) or a
later structural-alpha sleeve per
[FFL-0001-05](/docs/roadmap/future-features-ledger.md)). 1.4
hard-asserts the two-sleeve assumption at
`build_gate_report` entry with a clear error message if the
registry ever contains ≠ 2 mandatory sleeve-backed candidates;
see tests below.

```python
# Pseudocode inside build_gate_report (gate_id == "1")

# Defensive assertion: 1.4 only supports the two-sleeve case.
sleeve_candidates = tuple(
    c for c in candidates if c.sleeve_class_path is not None
)
if len(sleeve_candidates) != 2:
    raise NotImplementedError(
        "Marginal-portfolio-contribution criterion in tranche "
        "1.4 is scoped to the two-sleeve case; found "
        f"{len(sleeve_candidates)} sleeve-backed candidates. "
        "Generalization for 3+ sleeves is deferred to the "
        "tranche that introduces the third sleeve-backed "
        "candidate."
    )

# Pass 1: per-candidate, the four existing criteria (no change).
pass1_results = {}
for candidate in candidates:
    cand_returns, cand_drag = _candidate_returns(candidate, ...)
    four_criteria_result = _build_gate1_candidate_result_pass1(
        ...,
        candidate_returns=cand_returns,
    )
    pass1_results[candidate.candidate_id] = (
        candidate, cand_returns, cand_drag, four_criteria_result
    )

# Pass 2: for each sleeve-backed candidate, compute portfolio-
# with/without against the fixed sibling (registry rule above)
# and evaluate the marginal criterion. Non-sleeve candidates
# (today: mean-reversion-v1 with sleeve_class_path=None) skip
# pass 2 and keep their pass-1 status unchanged.
for candidate_id, (candidate, cand_returns, ...) in pass1_results.items():
    if candidate.sleeve_class_path is None:
        continue  # non-sleeve candidate — no marginal pass
    sibling = next(
        c for c in sleeve_candidates if c.candidate_id != candidate_id
    )
    portfolio_without = _simulate_book([sibling], ...)
    portfolio_with = _simulate_book([candidate, sibling], ...)
    marginal_criterion = evaluate_marginal_portfolio_contribution(
        candidate_returns=cand_returns,
        portfolio_without_candidate_returns=portfolio_without,
        portfolio_with_candidate_returns=portfolio_with,
    )
    marginal_status = "pass" if marginal_criterion.passed else "fail"

    # Final criteria = four existing + marginal
    final_criteria = pass1_results[candidate_id][3].criteria + (marginal_criterion,)
    final_status = _reconcile_status(
        pass1_results[candidate_id][3].status, marginal_status
    )
```

The `pending` case from the first draft (no other passing
sleeves) no longer arises: the book is pinned to the sibling,
independent of its pass1 status. This is the intentional
consequence of restricting 1.4 to two sleeves — every
sleeve-backed candidate always has exactly one sibling. The
`marginal_status = pending` branch is removed.

**Status reconciliation rule.** The final Gate 1 status for a
sleeve-backed candidate combines the four-criteria pass1 status
with the marginal criterion status:

| pass1 status | marginal status | final |
|---|---|---|
| `fail` | any | `fail` |
| `pending` | any | `pending` |
| `pass` | `pass` | `pass` |
| `pass` | `fail` | `fail` |

The `pending` + `pass`/`fail` row from the first-draft table is
removed: with the two-sleeve book-construction rule, pass 2
always produces a concrete `pass`/`fail`. Non-sleeve
candidates (today: `mean-reversion-v1`) skip pass 2 entirely
and keep their pass-1 status verbatim.

**Simulating portfolio-with/without.** Uses
`simulate_portfolio_returns` from W2, parameterized with a
per-evaluation `PortfolioBlueprint` that assigns equal budgets
to the sleeves being combined (two-sleeve case → 0.5/0.5; one-
sleeve "without" book → the sole sleeve at 1.0). Equal budgets
is a tranche-1 simplification; tranche 2+ may use blueprint-
configured budgets once live data informs budget allocation.

**Per §P1:** both `portfolio_with` and `portfolio_without`
simulations run through the same `run_daily_bar_backtest` —
no separate execution model.

**Per §P2 + §P5: field additions.**

Add to `EvaluationEvidencePack`:

```python
marginal_sharpe_delta: Decimal | None = None
marginal_calmar_delta: Decimal | None = None
marginal_cdar_delta: Decimal | None = None
```

Add to `ValidationCandidateResult`:

```python
marginal_sharpe_delta: Decimal | None = None
marginal_calmar_delta: Decimal | None = None
marginal_cdar_delta: Decimal | None = None
```

Populated only when Gate 1 runs the pass-2 evaluation. All fields
default to `None`; legacy consumers deserialize existing
reports without migration (per §P5).

**Evidence-pack population rule (single source of truth).** The
only function that sets these fields on the evidence pack is
the pass-2 branch inside `build_gate_report`. `evaluate_candidate`
continues to be agnostic; if these values are passed in, they
are forwarded to the pack; otherwise they remain `None`.

**Tests cover:**

- Two sleeve-backed candidates, `trend + vol_managed_beta`:
  for each, the marginal criterion evaluates against the other
  as the fixed sibling book, independent of its pass1 status.
  Result is deterministic on canned data.
- Registry count != 2 sleeve-backed candidates (one or three):
  `build_gate_report` raises `NotImplementedError` at entry
  with the deferred-generalization error message. This is a
  guardrail test; today's registry has exactly 2.
- Pass-1 passing candidate whose sibling fails pass 1: the
  marginal pass still runs (book is registry-pinned, not
  pass1-pinned). `marginal_sharpe_delta` etc. are populated.
  The sibling's pass1 failure does not propagate to the
  passing candidate's marginal outcome.
- Non-sleeve candidate (`mean-reversion-v1` with
  `sleeve_class_path = None`): pass 2 is skipped; final status
  equals pass-1 status; `marginal_*_delta` remains `None`.
- Both sleeves pass pass1 AND marginal → both end `pass`.
- Both sleeves pass pass1; neither adds marginal value → both
  end `fail` with `marginal_sharpe_delta <= 0` (or calmar/cdar
  violated) in the criterion details.
- `EvaluationEvidencePack.marginal_*_delta` populated for every
  sleeve-backed candidate that reached pass 2; `None` for non-
  sleeve candidates.
- `ValidationCandidateResult.marginal_*_delta` mirrors the
  evidence pack's value (§P2 regression).
- Deserialization of a pre-1.4 persisted `EvaluationEvidencePack`
  (no marginal fields on disk) produces `marginal_*_delta =
  None`.

### W8 — Closing pass + governance + validation

**Files:**
- Modify: `docs/INDEX.md` — register DESIGN-0015, bump INDEX
  version (patch).
- Modify: `docs/validation/acceptance_gates.md` — move the
  marginal-contribution criterion from "Deferred to tranche 1
  hardening" to "Pass criteria (hard-pass, all required)".
  Bump GATES-0001 to 1.2.0 (minor — a deferred criterion becomes
  operational).
- Modify: `docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md`
  — mark sub-tranche 1.4 as SHIPPED and 1.5 as NEXT (housekeeping
  amendment). Bump BRIEF-0002 to 1.1.2.
- Standard closing pass identical to DESIGN-0014 W7: `uv run pytest
  -q`, `uv run mypy src/tradingx`, `uv run ruff check`,
  `python3 scripts/check_index.py`, `./scripts/validate`.

**Important:** the GATES-0001 activation in W8 happens **in the
implementation-plan commit sequence**, not in this draft-spec
PR. The spec itself only reserves the version bump; the actual
edit to GATES-0001 ships when the implementation lands. This
draft spec's governance-impact section (§below) makes that
explicit.

## Testing approach

Standard TDD per repo convention. Each work item produces unit
tests **before** implementation. Additional integration coverage:

- `tests/integration/test_portfolio_end_to_end.py` (new): 500
  trading days of canned bars through both sleeves + portfolio
  construction + drawdown throttles + marginal-contribution
  Gate 1. Assertions:
  - Combined target-weight DataFrame satisfies
    `_validate_inputs` for `run_daily_bar_backtest`.
  - On a synthetic drawdown-inducing bar sequence, the MDD
    design throttle fires at dd > 15%, the CDaR soft throttle
    fires when trailing CDaR > 8%, and the 25% hard halt
    triggers the runtime-host transition.
  - Per D4: on a `stressed` regime bar, the vol-managed-beta
    sleeve column is 0 AND its budget is not redistributed to
    trend.
  - Gate 1 evaluation produces a
    `ValidationCandidateResult.marginal_sharpe_delta` that is
    not `None` for both sleeves.
  - `EvaluationEvidencePack` and `ValidationCandidateResult`
    fields are consistent (same value, both populated) — §P2
    regression.

- Regression: existing `test_validation.py` and
  `test_evaluation.py` continue to pass with `marginal_*` fields
  defaulting to `None`.

## Acceptance criteria

Sub-tranche 1.4 is complete when:

1. `PortfolioBlueprint` and `SleeveRiskBudget` dataclasses are
   defined and tested; budget-sum invariant enforced.
2. `build_portfolio_target_weight_history` combines sleeve
   target-weight histories with per-sleeve budgets, correlation
   caps, and gross/net caps; D4 "cash is a consequence"
   verified by contract test.
3. `simulate_portfolio_returns` wraps the combined DataFrame
   through `run_daily_bar_backtest` with no duplicate execution
   logic (§P1); produces `PortfolioSimulationResult`.
4. `apply_mdd_design_throttle` implements the linear
   15%-to-25% proportional scale per W3; tests cover the
   boundary values.
5. `apply_cdar_soft_throttle` implements the
   `threshold`-to-`2×threshold` soft-throttle with 0.5 floor;
   tests cover composition with MDD throttle.
6. `PortfolioHardHaltController` transitions the runtime host
   into `recovery_required` at 25% MDD, emits a `critical`
   operator alert, is idempotent, and reuses the existing
   operator clearance flow.
7. `SleeveRuntimeController` wraps sleeves with operator-halt,
   drift-alarm (stub), and 3-month-Sharpe termination rules;
   every termination emits explicit `SleeveTrade` entries (§P3).
8. `evaluate_marginal_portfolio_contribution` implements the
   pass rule; pass-2 integration into `build_gate_report`
   reconciles statuses per the table in W7.
9. `EvaluationEvidencePack` and `ValidationCandidateResult`
   both carry `marginal_sharpe_delta`, `marginal_calmar_delta`,
   `marginal_cdar_delta`, defaulting to `None` (§P2 + §P5).
10. `uv run pytest -q`, `uv run mypy src/tradingx`,
    `uv run ruff check`, `python3 scripts/check_index.py`,
    `./scripts/validate` all pass.
11. Gate 1 evaluation against the benchmark stack emits the
    five-criterion Gate 1 result for every sleeve-backed
    candidate, and the marginal-portfolio-contribution
    criterion is a **hard-pass criterion** — a sleeve that
    fails it fails Gate 1, per ADR-0022 §"Deferred to tranche
    1 hardening". For the two shipped sleeves
    (`trend-following-v1`, `vol-target-v1`), the marginal-delta
    evidence fields (`marginal_sharpe_delta`,
    `marginal_calmar_delta`, `marginal_cdar_delta`) are
    populated on both `EvaluationEvidencePack` and
    `ValidationCandidateResult`, regardless of the pass/fail
    outcome. If either shipped sleeve fails the marginal check
    on current historical data, that is a real Gate 1 failure
    — 1.4 ships the machinery that surfaces that fact;
    remediation of edge is out of scope for 1.4.

## Decisions resolved (no open items)

All D1–D5 resolutions from BRIEF-0002 remain load-bearing and
are implemented here without modification. This spec introduces
**no new D-level decisions**.

Implementation-level judgment calls for Codex review:

1. **Correlation-cap math.** The spec's rule (strictest sleeve's
   correlation-cap × max_gross_exposure as the combined-weight
   cap) is the sharper rule. If Codex prefers the flatter rule
   (`max_gross × 0.85` fixed), flag it and we amend this spec
   in the review loop.
2. **Equal vs blueprint-configured budgets for
   `simulate_portfolio_returns` inside
   `evaluate_marginal_portfolio_contribution`.** Spec uses
   equal budgets for tranche-1 simplicity; if Codex prefers the
   blueprint-configured budgets passed through, it's a minor
   plumbing change and we amend.
3. **Drawdown trailing window.** Spec uses "trailing up to and
   including prior bar" for next-open consistency. If Codex
   prefers "trailing up to prior day's close," it's effectively
   the same in a daily-bar engine; flag in review if preferred.
4. **Constant naming for sleeve-Sharpe termination
   (resolved in round-1 amendment).** The 1.3 constant
   `SLEEVE_SHARPE_BELOW_THRESHOLD_6M` is kept stable in 1.4 to
   avoid staling cross-references in DESIGN-0014 and the 1.3
   plan. The window-name-vs-rationale-string inconsistency is
   a known imperfection; see the W6 "Constant-naming note".

## Governance impact

- **Register `DESIGN-0015` in INDEX.** Adds a row to INDEX-0001's
  Design documents table. Bumps INDEX-0001 patch version.
- **BRIEF-0002 amended (housekeeping).** The sub-tranche-
  sequence table gains a "status" column noting which sub-tranches
  have shipped. No scope changes; no D-decision changes. Patch
  bump (1.1.0 → 1.1.1). This amendment ships alongside this
  spec's registration commit.
- **ADR impact: none.** ADR-0021 and ADR-0022 remain the
  authority for the three-tier benchmark and the Gate 1 reframe.
  1.4 implements their deferred-to-tranche-1 criterion but does
  not alter ADR content.
- **GATES-0001 amendment deferred to the implementation-plan
  commit sequence.** When the marginal-contribution
  implementation lands on main, GATES-0001 v1.1.0 → v1.2.0
  moves the criterion from "Deferred to tranche 1 hardening" to
  "Pass criteria (hard-pass, all required)". This draft spec
  does not edit GATES-0001; the implementation plan does.
- **FFL-0001 impact: none.** No deferrals move into scope; no
  new deferrals added. 1.4 does not alter the ledger.
- **CONST-0001 impact: none.** The constitution's Gate 4 live-
  trading discipline remains load-bearing; 1.4 adds
  drawdown-defense infrastructure, it does not change the
  enablement criteria.

## References

### Repo documents

- [BRIEF-0002 Tranche 1 planning brief](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
  — sub-tranche 1.4 scope + D1–D5 resolutions.
- [FFL-0001 Future features ledger](/docs/roadmap/future-features-ledger.md)
  — deferrals that remain out of scope.
- [SPEC-0013 Capital growth landscape](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
  — strategic context.
- [ADR-0021 Benchmark stack](/docs/adrs/ADR-0021-benchmark-stack.md)
  — 15% design target / 25% halt.
- [ADR-0022 Gate 1 reframe](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
  — marginal-contribution deferral.
- [GATES-0001 Acceptance gates v1.1.0](/docs/validation/acceptance_gates.md)
  — current gate definitions.
- [DESIGN-0011 Tranche 1.1 validation infrastructure](/docs/superpowers/specs/2026-04-21-tranche-1-1-validation-infrastructure-design.md).
- [DESIGN-0013 Tranche 1.2 market-state features](/docs/superpowers/specs/2026-04-21-tranche-1-2-market-state-features-design.md)
  — regime composite that is load-bearing for D4.
- [DESIGN-0014 Tranche 1.3 sleeves](/docs/superpowers/specs/2026-04-21-tranche-1-3-sleeves-design.md)
  — sleeve protocol + regime exposure floor.

### Existing source files

- [src/tradingx/backtest.py](/src/tradingx/backtest.py) —
  `run_daily_bar_backtest`, the authoritative execution engine
  (§P1).
- [src/tradingx/validation.py](/src/tradingx/validation.py) —
  `_candidate_returns`, `build_gate_report`,
  `evaluate_gate1_benchmark_criteria`.
- [src/tradingx/evaluation.py](/src/tradingx/evaluation.py) —
  `evaluate_candidate`, `AdversarialCheckContext`.
- [src/tradingx/types.py](/src/tradingx/types.py) —
  `EvaluationEvidencePack`, `ValidationCandidateResult`,
  `OperatingConstraintBudget`, `SleeveContext`,
  `SleeveFailureReason`.
- [src/tradingx/sleeves/base.py](/src/tradingx/sleeves/base.py)
  — `SleeveProtocol`, `build_sleeve_from_candidate`.
- [src/tradingx/sleeves/evaluation.py](/src/tradingx/sleeves/evaluation.py)
  — `build_sleeve_target_weight_history`,
  `simulate_sleeve_returns`.
- [src/tradingx/sleeves/regime_gate.py](/src/tradingx/sleeves/regime_gate.py)
  — `apply_regime_exposure_floor`.
- [src/tradingx/runtime_host.py](/src/tradingx/runtime_host.py)
  — `LocalRuntimeHostManager`, operator clearance flow.
- [src/tradingx/operator_control.py](/src/tradingx/operator_control.py)
  — operator-control action surface.
- [src/tradingx/trials.py](/src/tradingx/trials.py) —
  `TrialsLedger` (source for 3-month Sharpe calculation in W6).

### External references

- Prado, M. López de. *Advances in Financial Machine Learning*,
  Wiley, 2018 — §8 portfolio aggregation, §11 CDaR.
- Chekhlov, A., Uryasev, S., Zabarankin, M. (2005).
  "Drawdown measure in portfolio optimization." *International
  Journal of Theoretical and Applied Finance* — CDaR definition
  and coherence properties.
