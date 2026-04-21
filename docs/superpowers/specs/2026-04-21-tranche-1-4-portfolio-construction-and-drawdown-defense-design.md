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
   alarm (stub wired for 1.5 to fill), and 3-month rolling Sharpe
   below threshold. Every termination emits an explicit sleeve
   trade with the reason code — no silent skips.
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
- Create: `tests/unit/test_portfolio_hard_halt.py`
- Modify: `tests/unit/test_runtime_host.py`

**Runtime-host change:**

```python
# src/tradingx/runtime_host.py (addition)

def trigger_hard_halt(self, *, reason: str) -> WebActionResult:
    """Transition the runtime into recovery_required state
    because a hard risk limit was breached.

    This reuses the existing reconciliation-divergence path:
    setting status to recovery_required blocks new entries
    until request_clearance() + successful reconciliation.

    The operator sees:
    - runtime state becomes `recovery_required`
    - `last_error` carries the halt reason
    - an OperatorAlert with severity `critical` is emitted
    - the operator must manually call request_clearance() to
      resume trading (same protocol as reconciliation halts).

    Returns WebActionResult with status `accepted` on success.
    Idempotent: calling when already in recovery_required is a
    no-op.
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
        self._set_state(
            status="recovery_required",
            status_reason=(
                "Hard halt triggered: "
                + reason
                + ". New entries blocked until operator clearance."
            ),
            last_error=reason,
        )
    return WebActionResult(
        action_id=f"action-{uuid.uuid4()}",
        action_type="runtime_host_hard_halt",
        status="accepted",
        message=f"Hard halt: {reason}",
        evidence_refs=(),
    )
```

**Controller contract:**

```python
# src/tradingx/portfolio/hard_halt.py

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
        blueprint.mdd_hard_halt, trigger the halt (once). The
        halt is latched — once triggered, subsequent checks are
        no-ops until the operator clears and the controller is
        reset externally (e.g., after operator clearance lands
        the runtime back in `nominal`).
        """
```

**Operator-alert shape:** severity `critical`, category
`portfolio_hard_halt`, summary referencing the observed
drawdown and the blueprint.

**Tests cover:**

- Equity curve with trailing MDD < 25% → no halt, returns None.
- Equity curve with trailing MDD == 25% → halt triggers exactly
  once, runtime host transitions to `recovery_required`, alert
  gateway publishes a `critical` alert.
- Second call with same breach → no-op (latched).
- Controller reset (external) + new check below 25% → no halt.
- Runtime host state after halt: `status == "recovery_required"`,
  `last_error` contains the halt reason text.
- Integration with `request_clearance()`: clearance flow still
  works from a hard-halt-induced `recovery_required` state
  identically to a reconciliation-induced one.

**Why this wiring closes the P1 gap.** Today
`max_drawdown_halt = 0.25` lives on `OperatingConstraintBudget`
and is emitted in benchmark-stack payloads
([validation.py:800-900](/src/tradingx/validation.py)) but no
runtime code reads it. 1.4 makes the value **load-bearing**:
`PortfolioHardHaltController` consumes it, triggers the runtime
transition, and the operator control flow (already shipped in
SPEC-0010) surfaces the halt and the clearance request. The
25% threshold becomes a real runtime gate, not documentation.

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


@dataclass(frozen=True)
class SleeveRuntimeConfig:
    three_month_sharpe_floor: Decimal  # from blueprint
    three_month_window_days: int = 63  # ~3 trading months


class SleeveRuntimeController:
    """Wraps a sleeve with runtime termination rules.

    When plan_for_bar is called, the controller first checks the
    three termination sources:

    1. operator_halt_store.is_halted(sleeve_id) → emit hold-or-
       sell trades with rationale = HALT_BY_OPERATOR.
    2. drift_alarm_gateway.has_alarm(sleeve_id) → emit with
       rationale = DRIFT_ALARM_LIVE. Gateway is a stub in 1.4
       (always returns False); 1.5 fills it in.
    3. trials_ledger recent 3-month rolling Sharpe for the
       sleeve < config.three_month_sharpe_floor → emit with
       rationale = SLEEVE_SHARPE_BELOW_THRESHOLD_6M.

    If none fire, delegates to sleeve.plan_for_bar.

    Termination produces explicit SleeveTrade entries with
    side="sell" (if current weight > 0) or side="hold" (if no
    current weight), target_weight_of_sleeve_budget=0, and the
    appropriate rationale — never an empty tuple (§P3).

    Note on the rationale string: SLEEVE_SHARPE_BELOW_THRESHOLD_6M
    is the constant name shipped in 1.3; in tranche-1 we use a
    3-month Sharpe floor for the *threshold computation*, and
    reuse the existing constant string for the rationale. If
    Codex prefers renaming the constant to make this less
    confusing (`SLEEVE_SHARPE_BELOW_THRESHOLD_ROLLING` or
    similar), call that out in review — it's a low-risk rename
    that propagates to tests and the docstring; all current
    usages are in 1.4 code we are adding in this same tranche.
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

**3-month Sharpe computation.** The controller queries the
trials ledger for records matching the sleeve's `candidate_id`
(= `sleeve_id`) within the last 63 trading days, computes a
Sharpe on the trials' `observed_sharpe_net_of_costs` field, and
compares to the floor. If fewer than 30 records exist, the check
is skipped (insufficient evidence → same-semantics as
`out_of_sample_profile` `pending` in Gate 1).

**Tests cover:**

- No halts, no alarm, ledger ok → controller delegates and
  returns exactly the sleeve's own output.
- Operator halt → all in-universe symbols produce explicit
  termination trades.
- Drift alarm gateway returns True → same behavior with
  `DRIFT_ALARM_LIVE` rationale (1.5 will provide a real
  gateway; 1.4 tests use a stub).
- Trials ledger with rolling Sharpe < floor → termination with
  `SLEEVE_SHARPE_BELOW_THRESHOLD_6M` rationale.
- Trials ledger with < 30 records → no check fires; delegates
  as normal.
- Precedence order: if multiple conditions fire, operator halt
  wins (operator authority is absolute), then drift alarm, then
  Sharpe floor. Rationale reflects the winning condition only.

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
    portfolio_without_candidate_returns: tuple[Decimal, ...] | None,
    portfolio_with_candidate_returns: tuple[Decimal, ...] | None,
) -> ValidationCriterionResult:
    """Evaluate whether adding the candidate to the book improves
    Sharpe, Calmar, and CDaR of the portfolio.

    Per ADR-0022 §"Deferred to tranche 1 hardening", this
    criterion supplements — does not replace — the four
    operational Gate 1 criteria.

    If either portfolio series is None, the criterion is
    `pending` (cannot evaluate without both), status stored as
    passed=False but details indicate the pending reason. The
    overall Gate 1 status downstream handles `pending` as
    separate from pass/fail — see _build_gate1_candidate_result.

    Pass rule (all must hold):
        sharpe_with > sharpe_without
        calmar_with > calmar_without
        cdar_with  <= cdar_without   (CDaR is a bad — lower is better)

    Returns ValidationCriterionResult with criterion_id =
    "marginal_portfolio_contribution" and details containing the
    three observed deltas.
    """
```

**Integration into the Gate 1 report.** The current
`build_gate_report` loop evaluates candidates independently. 1.4
restructures the Gate 1 branch into a **two-pass** flow:

```python
# Pseudocode inside build_gate_report (gate_id == "1")

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

# Pass 2: for each candidate, compute portfolio-with/without
# and evaluate the marginal criterion.
for candidate_id, (candidate, cand_returns, ...) in pass1_results.items():
    others = [
        (c, returns) for c_id, (c, returns, ...) in pass1_results.items()
        if c_id != candidate_id and pass1_results[c_id][3].status == "pass"
    ]
    if not others:
        marginal_criterion = ValidationCriterionResult(
            criterion_id="marginal_portfolio_contribution",
            passed=False,
            threshold="adding candidate improves portfolio Sharpe, Calmar, CDaR",
            details="pending: no other passing sleeves to form a book",
        )
        marginal_status = "pending"
    else:
        portfolio_without = _simulate_book([c for c, _ in others], ...)
        portfolio_with = _simulate_book([candidate] + [c for c, _ in others], ...)
        marginal_criterion = evaluate_marginal_portfolio_contribution(...)
        marginal_status = "pass" if marginal_criterion.passed else "fail"

    # Final criteria = four existing + marginal
    final_criteria = pass1_results[candidate_id][3].criteria + (marginal_criterion,)
    final_status = _reconcile_status(pass1_results[candidate_id][3].status, marginal_status)
```

**Status reconciliation rule.** The final Gate 1 status for a
candidate combines the four-criteria pass1 status with the
marginal criterion status:

| pass1 status | marginal status | final |
|---|---|---|
| `fail` | any | `fail` |
| `pending` | any | `pending` |
| `pass` | `pass` | `pass` |
| `pass` | `fail` | `fail` |
| `pass` | `pending` | `pending` |

**Simulating portfolio-with/without.** Uses
`simulate_portfolio_returns` from W2, parameterized with a
per-evaluation `PortfolioBlueprint` that assigns equal budgets
to the sleeves being combined. Equal budgets is a tranche-1
simplification; tranche 2+ may use blueprint-configured budgets
once live data informs budget allocation.

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

- Two passing sleeves, `trend + vol_managed_beta`: for each
  candidate, the marginal criterion evaluates against the other
  sleeve alone. Result is deterministic on canned data.
- Single passing sleeve: the lone candidate gets
  `marginal_status = pending`; final status is `pending`.
- One passing and one failing (pass1) sleeve: the passing
  sleeve's marginal check is against the empty other-book;
  marginal = `pending`, final = `pending`. Failing sleeve
  stays failed regardless.
- Both sleeves pass pass1 AND marginal → both end `pass`.
- Both sleeves pass pass1; neither adds marginal value → both
  end `fail` with `marginal_sharpe_delta <= 0` (for instance).
- `EvaluationEvidencePack.marginal_*_delta` populated for
  candidates that ran pass-2 evaluation; `None` for candidates
  that did not (pending or skipped).
- `ValidationCandidateResult.marginal_*_delta` mirrors the
  evidence pack's value.
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
11. Gate 1 evaluation against the benchmark stack now emits the
    five-criterion Gate 1 result for every sleeve-backed
    candidate. For the two shipped sleeves
    (`trend-following-v1`, `vol-target-v1`), the pass/fail
    outcome of the marginal criterion is **not** gated on; we
    are validating plumbing, not edge.

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
4. **Constant naming for sleeve-Sharpe termination.** W6 reuses
   the existing `SLEEVE_SHARPE_BELOW_THRESHOLD_6M` string but
   the computation is 3-month. If Codex prefers renaming the
   constant to match the computation window
   (`SLEEVE_SHARPE_BELOW_THRESHOLD_ROLLING` or
   `_3M` suffix), it's a low-risk rename we resolve in the
   implementation plan.

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
