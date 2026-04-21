---
id: DESIGN-0014
title: Tranche 1.3 sleeves — trend-following and vol-managed beta
version: 0.1.0
status: draft
created: 2026-04-21
last_amended: 2026-04-21
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# DESIGN-0014: Tranche 1.3 sleeves — trend-following and vol-managed beta

## Status

Draft on 2026-04-21. Third sub-tranche under
[BRIEF-0002](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
tranche-1 plan. Pending Hussam approval.

## Purpose

Turn the two existing signal functions
([signals/trend.py](/src/tradingx/signals/trend.py) and
[signals/vol_target_spy.py](/src/tradingx/signals/vol_target_spy.py))
into full **sleeves**, per the atomic-unit definition in
[BRIEF-0002](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md):
each sleeve owns its **signal, sizing, regime filter, allowed
instruments, and failure rules**.

Scope:

1. A minimal `SleeveProtocol` + shared base class that captures the
   five ownership responsibilities.
2. Explicit **regime → exposure-floor mapping** codified for both
   sleeves (mandated by BRIEF-0002's D4 resolution).
3. **`TrendSleeve`** — time-series momentum (Moskowitz-Ooi-Pedersen
   2012) productionized with vol-targeted sizing, regime filter,
   and failure rules.
4. **`VolManagedBetaSleeve`** — volatility-managed long equity
   (Moreira-Muir 2017) productionized with regime filter and
   failure rules. Sizing is intrinsic to the signal (pre-sized via
   `volatility_scale`).
5. **Sleeve-level evaluation wiring** — each sleeve runs through
   `evaluate_candidate` against the three-tier benchmark stack and
   produces its own `EvaluationEvidencePack`.

**Not in scope** (deferred per BRIEF-0002 sub-tranche boundaries):

- Portfolio construction combining the two sleeves — ships in 1.4.
- Runtime MDD throttle at 15% / hard halt at 25% — ships in 1.4.
- Marginal-portfolio-contribution Gate 1 criterion — ships in 1.4.
- Live drift monitoring (PSI, KS, execution drift, live-vs-backtest
  divergence) — ships in 1.5.
- Fractional Kelly sizing — deferred to
  [FFL-0001-01](/docs/roadmap/future-features-ledger.md).
- Mean-reversion sleeve — deferred per
  [FFL-0001-03](/docs/roadmap/future-features-ledger.md).
- Options / tail hedging — deferred per
  [FFL-0001-02](/docs/roadmap/future-features-ledger.md).

## Prerequisites

- `main` at or beyond the tranche-1.2 merge (`8af741c`): brings
  HAR-RV, Treasury 2s10s, `RegimeSnapshot`, `classify_regime`, and
  the corrected vol-estimator comparison that retuned
  `trend-following-v1.forecast_method` to `ewma`.
- `main` at or beyond the tranche-1.1 merge: brings purged k-fold
  CV, trials ledger, DSR wiring, cost-drag reporting.
- Existing scaffolds already present:
  - `src/tradingx/signals/trend.py` — `generate_trend_signal`
  - `src/tradingx/signals/vol_target_spy.py` —
    `generate_vol_target_spy_signal`
  - `src/tradingx/features/regime.py` — `classify_regime`
  - `src/tradingx/features/volatility.py` — `forecast_volatility`,
    `volatility_scale`
  - `src/tradingx/strategy.py` — candidate registry with
    `trend-following-v1` and `vol-target-v1`
- **All D1–D5 resolutions in BRIEF-0002 are locked** — this spec
  implements them, it does not re-open them.

## D4 regime → exposure-floor mapping (codified)

Per BRIEF-0002's D4 resolution, this spec MUST codify the exact
mapping. Both sleeves apply the **same** mapping logic; no future
sleeve is free to reinterpret the four regime states.

| Regime state | Trend sleeve exposure floor | Vol-managed beta exposure floor |
|---|---|---|
| `risk_on` | 100% of sleeve budget (subject to signal + vol sizing) | 100% of sleeve budget (subject to vol target) |
| `neutral` | 100% of sleeve budget (subject to signal + vol sizing) | 100% of sleeve budget |
| `risk_off` | 100% of sleeve budget, but **no new entries**; existing positions held until signal flips | 100% of sleeve budget (Moreira-Muir's own vol scaling will naturally reduce exposure in elevated vol) |
| `stressed` | **0% exposure.** No new entries. Existing positions liquidated at the next bar. | **0% exposure.** Existing positions liquidated at the next bar. |

Rationale for the asymmetry between `risk_off` and `stressed`:

- `risk_off` is an elevated-caution state (SPY below SMA-200 OR VIX
  ≥ 25). Forcing immediate liquidation on every regime flip to
  `risk_off` would churn turnover. Better: pause new entries,
  let existing positions ride unless a deeper signal fires or
  `stressed` is reached.
- `stressed` is the 35+ VIX / inverted-curve-with-SPY-below-SMA
  state. This is the "something is breaking" regime. BRIEF-0002's
  D4 resolution explicitly names this as the exposure-zero state.

**Important**: the trend sleeve's "no new entries" behavior in
`risk_off` is distinct from its signal. If the signal would have
said "enter long SPY" and the regime is `risk_off`, the signal is
suppressed to `hold`. Existing positions flow through normal
signal-driven exits.

## Architecture overview

### New modules

1. **`src/tradingx/sleeves/__init__.py`** — package init.
2. **`src/tradingx/sleeves/base.py`** — `SleeveProtocol`,
   `SleeveContext`, and `SleeveTrade` result type.
3. **`src/tradingx/sleeves/trend.py`** — `TrendSleeve`
   implementation.
4. **`src/tradingx/sleeves/vol_managed_beta.py`** —
   `VolManagedBetaSleeve` implementation.
5. **`src/tradingx/sleeves/regime_gate.py`** — shared regime
   → exposure-floor mapping function (so the two sleeves call the
   same source).

### New dataclasses

6. **`SleeveContext`** — per-evaluation inputs (bars, regime
   snapshot, vol forecast, sizing parameters, turnover budget).
7. **`SleeveTrade`** — per-bar sleeve output (symbol, direction,
   target-weight, rationale).
8. **`SleeveFailureReason`** — enum-like string constant set for
   failure-rule diagnostics.

### Modified files

- `src/tradingx/types.py` — add the three new dataclasses.
- `src/tradingx/strategy.py` — extend `StrategyCandidate` with an
  optional `sleeve_class_path` field (dotted-path string) that
  links the registry entry to the sleeve implementation. No
  default; if absent, the legacy planner path handles the
  candidate.
- `tests/unit/test_types.py`, new `tests/unit/test_sleeves_*.py`,
  regression updates to `test_strategy.py` and
  `test_validation.py`.

### Not touched in this tranche

- `runtime_strategy_registry.py` and `baseline_runtime_planner.py`
  — the `SleevePlannerProtocol` rename noted in
  [SPEC-0013 Appendix A](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
  remains deferred. 1.3 introduces a **new** `SleeveProtocol`
  alongside the existing runtime-planner layer. The two protocols
  coexist without conflict because sleeves produce target weights
  per bar while the runtime planner exposes
  `plan_for_service(symbols, portfolio_state)`. Merging the two
  abstractions into a single protocol is a 1.4 (portfolio
  construction) decision, not 1.3.

## Work items

### W1 — `SleeveProtocol` and shared types

**Files:**
- Create: `src/tradingx/sleeves/__init__.py`
- Create: `src/tradingx/sleeves/base.py`
- Modify: `src/tradingx/types.py`
- Create: `tests/unit/test_sleeve_base.py`

**Contract:**

```python
# src/tradingx/sleeves/base.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

import pandas as pd

from tradingx.types import RegimeSnapshot, SleeveTrade, SleeveContext


class SleeveProtocol(Protocol):
    """An atomic trading unit.

    A sleeve owns five responsibilities per BRIEF-0002:
    - signal: generate a directional or target-weight view
    - sizing: convert view into position size within its budget
    - regime filter: apply the regime → exposure-floor mapping
    - allowed instruments: declare the universe it may trade
    - failure rules: declare termination triggers

    plan_for_bar consumes a single-bar SleeveContext and returns a
    tuple of SleeveTrades (one per instrument the sleeve touched).
    """

    @property
    def sleeve_id(self) -> str: ...

    @property
    def family(self) -> str: ...

    @property
    def allowed_instruments(self) -> tuple[str, ...]: ...

    def plan_for_bar(
        self,
        context: SleeveContext,
    ) -> tuple[SleeveTrade, ...]: ...
```

**`SleeveContext`** (in `types.py`):

```python
@dataclass(frozen=True)
class SleeveContext:
    observation_date: date
    bars_by_symbol: dict[str, pd.DataFrame]  # historical bars up to and including observation_date
    regime: RegimeSnapshot
    current_positions: dict[str, Decimal]  # symbol → quantity held
    sleeve_budget_equity: Decimal  # the sleeve's allocated portion of portfolio equity
    # no forward data — validate upstream
```

**`SleeveTrade`** (in `types.py`):

```python
@dataclass(frozen=True)
class SleeveTrade:
    sleeve_id: str
    symbol: str
    side: str  # "buy" | "sell" | "reduce" | "hold"
    target_weight_of_sleeve_budget: Decimal  # 0.0 to 1.0
    rationale: str  # human-readable, e.g. "tsmom_long_on_spy", "regime_stressed_liquidate"
    regime: str  # echo of context.regime.regime for traceability
```

**`SleeveFailureReason`** enum-like string set:
- `"halt_by_operator"`
- `"drift_alarm_live"` (triggers only after 1.5 ships)
- `"sleeve_sharpe_below_threshold_6m"` (triggers only after 6m of live evidence)
- `"regime_stressed"`
- `"insufficient_history"`

Tests cover: protocol conformance, frozen dataclass shape,
round-trip serialization.

### W2 — Regime gate helper

**Files:**
- Create: `src/tradingx/sleeves/regime_gate.py`
- Create: `tests/unit/test_regime_gate.py`

**Contract:**

```python
# src/tradingx/sleeves/regime_gate.py

from decimal import Decimal
from tradingx.types import RegimeSnapshot


def apply_regime_exposure_floor(
    *,
    sleeve_id: str,
    proposed_target_weight: Decimal,  # what the sleeve's own signal/sizing proposed
    current_position_weight: Decimal,  # what the sleeve currently holds
    regime: RegimeSnapshot,
    sleeve_family: str,  # "trend_following" | "vol_target"
) -> tuple[Decimal, str]:
    """Apply the regime → exposure-floor mapping from DESIGN-0014.

    Returns (adjusted_target_weight, rationale_string).

    Mapping:
    - risk_on / neutral: pass through proposed_target_weight.
    - risk_off:
        * trend_following family: if current_position_weight == 0
          and proposed > 0, suppress to 0 ("regime_risk_off_suppress_entry").
          Otherwise pass through.
        * vol_target family: pass through (Moreira-Muir scales
          naturally).
    - stressed: return Decimal("0") regardless of proposed or
      current. Rationale: "regime_stressed_liquidate".
    """
```

Tests cover:
- Pass-through in `risk_on` and `neutral` for both families
- Entry suppression in `risk_off` for trend, pass-through for
  vol_target
- Zero return in `stressed` for both families regardless of
  current position
- Rationale string exact match

### W3 — `TrendSleeve`

**Files:**
- Create: `src/tradingx/sleeves/trend.py`
- Create: `tests/unit/test_trend_sleeve.py`

**Responsibilities (per BRIEF-0002's sleeve definition):**

| Responsibility | Implementation |
|---|---|
| Signal | `generate_trend_signal` from `signals/trend.py` (already shipped) |
| Sizing | Vol-targeted per D1: target the sleeve-level annualized vol using `forecast_volatility(returns, forecast_method="ewma")` (tranche 1.2 retune) |
| Regime filter | `apply_regime_exposure_floor` with `sleeve_family="trend_following"` |
| Allowed instruments | `CANONICAL_STAGE1_UNIVERSE` from `strategy.py` (8 ETFs) |
| Failure rules | `regime_stressed` (handled by gate); `insufficient_history` (bars < 252); `halt_by_operator` (read from OperatorControlStore) |

**Contract:**

```python
# src/tradingx/sleeves/trend.py

from dataclasses import dataclass
from decimal import Decimal

from tradingx.features.volatility import forecast_volatility
from tradingx.signals.trend import generate_trend_signal
from tradingx.sleeves.base import SleeveProtocol
from tradingx.sleeves.regime_gate import apply_regime_exposure_floor
from tradingx.strategy import CANONICAL_STAGE1_UNIVERSE
from tradingx.types import SleeveContext, SleeveTrade


@dataclass(frozen=True)
class TrendSleeve:
    sleeve_id: str = "trend-following-v1"
    family: str = "trend_following"
    target_sleeve_vol: Decimal = Decimal("0.12")  # 12% annualized
    lookback_days: int = 252
    sma_window_days: int = 200
    skip_recent_days: int = 1
    allowed_instruments: tuple[str, ...] = CANONICAL_STAGE1_UNIVERSE

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        trades: list[SleeveTrade] = []
        for symbol in self.allowed_instruments:
            bars = context.bars_by_symbol.get(symbol)
            if bars is None or len(bars) < self.lookback_days:
                continue  # insufficient_history — silently skip

            signal = generate_trend_signal(
                bars,
                lookback_days=self.lookback_days,
                sma_window_days=self.sma_window_days,
                skip_recent_days=self.skip_recent_days,
            ).iloc[-1]

            # Vol-targeted sizing: leverage = target_vol / forecast_vol
            returns = bars["close"].astype(float).pct_change()
            vol_forecast = forecast_volatility(
                returns,
                lookback_days=20,
                forecast_method="ewma",  # per 1.2 retune
            ).iloc[-1]
            if vol_forecast is None or vol_forecast <= 0 or pd.isna(vol_forecast):
                continue

            # Signal is +1 (long), 0 (flat), or negative (skip — long-only).
            raw_weight = Decimal("0")
            if signal > 0:
                leverage = float(self.target_sleeve_vol) / float(vol_forecast)
                raw_weight = Decimal(str(min(leverage, 1.0)))  # no gross > 100% per D2/Moreira-Muir norm

            # Current weight of this symbol inside the sleeve
            current_qty = context.current_positions.get(symbol, Decimal("0"))
            last_close = Decimal(str(bars["close"].iloc[-1]))
            current_weight = (
                current_qty * last_close / context.sleeve_budget_equity
                if context.sleeve_budget_equity > Decimal("0")
                else Decimal("0")
            )

            # Regime gate
            adjusted_weight, rationale = apply_regime_exposure_floor(
                sleeve_id=self.sleeve_id,
                proposed_target_weight=raw_weight,
                current_position_weight=current_weight,
                regime=context.regime,
                sleeve_family=self.family,
            )

            # Derive side
            side = _derive_side(current_weight, adjusted_weight)
            trades.append(
                SleeveTrade(
                    sleeve_id=self.sleeve_id,
                    symbol=symbol,
                    side=side,
                    target_weight_of_sleeve_budget=adjusted_weight,
                    rationale=rationale or _signal_rationale(signal, adjusted_weight),
                    regime=context.regime.regime,
                )
            )
        return tuple(trades)


def _derive_side(current: Decimal, target: Decimal) -> str:
    if target > current:
        return "buy"
    if target < current and target == Decimal("0"):
        return "sell"
    if target < current:
        return "reduce"
    return "hold"


def _signal_rationale(signal_value: float, adjusted_weight: Decimal) -> str:
    if signal_value > 0 and adjusted_weight > Decimal("0"):
        return "tsmom_long_vol_targeted"
    if signal_value <= 0:
        return "tsmom_no_signal"
    return "tsmom_long_regime_suppressed"
```

Tests cover:
- Long entry on positive signal in `risk_on` → non-zero target weight
- Vol-target-adjusted sizing: leverage inversely proportional to
  forecast vol (low vol → higher weight, up to 1.0 cap)
- Insufficient history → symbol skipped (no trade emitted)
- Regime `stressed` → target weight 0, side reflects liquidation
- Regime `risk_off` with no current position → entry suppressed
- Regime `risk_off` with existing position → pass-through
- All trades cite `regime` correctly for traceability

### W4 — `VolManagedBetaSleeve`

**Files:**
- Create: `src/tradingx/sleeves/vol_managed_beta.py`
- Create: `tests/unit/test_vol_managed_beta_sleeve.py`

**Responsibilities:**

| Responsibility | Implementation |
|---|---|
| Signal | `generate_vol_target_spy_signal` (already pre-sized via Moreira-Muir) |
| Sizing | Intrinsic to the signal — already vol-scaled. No additional vol-target layer. |
| Regime filter | `apply_regime_exposure_floor` with `sleeve_family="vol_target"` |
| Allowed instruments | `("SPY",)` only |
| Failure rules | Same base set as trend sleeve |

**Contract:**

```python
# src/tradingx/sleeves/vol_managed_beta.py

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from tradingx.signals.vol_target_spy import generate_vol_target_spy_signal
from tradingx.sleeves.base import SleeveProtocol
from tradingx.sleeves.regime_gate import apply_regime_exposure_floor
from tradingx.types import SleeveContext, SleeveTrade


@dataclass(frozen=True)
class VolManagedBetaSleeve:
    sleeve_id: str = "vol-target-v1"
    family: str = "vol_target"
    target_volatility: float = 0.12
    realized_vol_window_days: int = 60
    max_gross_leverage: float = 1.0
    forecast_method: str = "garch"  # per candidate registry; not retuned in 1.2
    allowed_instruments: tuple[str, ...] = ("SPY",)

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        spy_bars = context.bars_by_symbol.get("SPY")
        if spy_bars is None or len(spy_bars) < self.realized_vol_window_days + 20:
            return ()  # insufficient_history

        signal_series = generate_vol_target_spy_signal(
            spy_bars,
            target_volatility=self.target_volatility,
            realized_vol_window_days=self.realized_vol_window_days,
            max_gross_leverage=self.max_gross_leverage,
            forecast_method=self.forecast_method,
        )
        raw_weight = Decimal(str(signal_series.iloc[-1]))
        if pd.isna(raw_weight):
            return ()

        current_qty = context.current_positions.get("SPY", Decimal("0"))
        last_close = Decimal(str(spy_bars["close"].iloc[-1]))
        current_weight = (
            current_qty * last_close / context.sleeve_budget_equity
            if context.sleeve_budget_equity > Decimal("0")
            else Decimal("0")
        )

        adjusted_weight, rationale = apply_regime_exposure_floor(
            sleeve_id=self.sleeve_id,
            proposed_target_weight=raw_weight,
            current_position_weight=current_weight,
            regime=context.regime,
            sleeve_family=self.family,
        )

        side = _derive_side(current_weight, adjusted_weight)
        return (
            SleeveTrade(
                sleeve_id=self.sleeve_id,
                symbol="SPY",
                side=side,
                target_weight_of_sleeve_budget=adjusted_weight,
                rationale=rationale or "moreira_muir_vol_managed",
                regime=context.regime.regime,
            ),
        )


def _derive_side(current: Decimal, target: Decimal) -> str:
    # Same helper as trend.py — duplicated here for single-module
    # import clarity. Codex may extract into sleeves/base.py if
    # duplication feels wrong.
    if target > current:
        return "buy"
    if target < current and target == Decimal("0"):
        return "sell"
    if target < current:
        return "reduce"
    return "hold"
```

Tests cover:
- Non-SPY symbols ignored (only SPY in allowed_instruments)
- Insufficient history → empty trade tuple
- Regime `stressed` → target 0, `sell` side if holding
- Regime `risk_off` → pass-through (Moreira-Muir's own scaling
  does the work)
- Moreira-Muir's natural vol-scaling produces weights < 1.0 in
  elevated-vol bars

### W5 — Sleeve-to-evidence-pack bridge

**Files:**
- Create: `src/tradingx/sleeves/evaluation.py`
- Modify: `tests/unit/test_validation.py` (regression) + new
  `tests/unit/test_sleeve_evaluation.py`

**Purpose:** Each sleeve must be evaluable against the three-tier
benchmark stack so Gate 1 criteria apply to it. This work item
provides a helper that converts a sleeve's historical trade stream
into a `candidate_returns` series suitable for
`evaluate_candidate`.

**Contract:**

```python
# src/tradingx/sleeves/evaluation.py

from decimal import Decimal

import pandas as pd

from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import RegimeSnapshot


def simulate_sleeve_returns(
    sleeve: SleeveProtocol,
    *,
    bars_by_symbol: dict[str, pd.DataFrame],
    regime_snapshots_by_date: dict,  # date -> RegimeSnapshot
    sleeve_budget_equity: Decimal,
) -> tuple[Decimal, ...]:
    """Walk the sleeve bar-by-bar, accumulate daily portfolio
    returns from its SleeveTrade outputs, and return them as a
    Decimal tuple suitable for _candidate_returns replacement.

    This is not a full backtest — it does not simulate fills,
    slippage, or rebalance cadence. It assumes the target weights
    produced by plan_for_bar are achieved at the next bar's open.
    Costs are layered on via the existing cost model in 1.1.
    """
```

Tests cover:
- Deterministic output for a fixed input
- Costs (from 1.1's cost-drag accounting) are applied
- Regime snapshots threaded correctly per date
- Insufficient-history bars produce zero return for that day

### W6 — Strategy-registry integration + regression

**Files:**
- Modify: `src/tradingx/strategy.py`
- Modify: `tests/unit/test_strategy.py`

**Behavior change:**

1. `StrategyCandidate` gets an optional
   `sleeve_class_path: str | None = None` field. When populated,
   this dotted path points at a sleeve class (e.g.
   `"tradingx.sleeves.trend.TrendSleeve"`).
2. Update `build_mandatory_candidate_registry` entries for
   `trend-following-v1` and `vol-target-v1` to set the new field.
   Mean-reversion entry leaves it `None` (FFL-0001-03 defers the
   sleeve).
3. The legacy `BaselineLongOnlyPlanner` still handles
   `baseline-long-only-v1` unchanged.

Tests cover:
- `StrategyCandidate` construction with and without
  `sleeve_class_path`
- Registry contains the expected sleeve paths

### W7 — Full regression + lint + typecheck + index + validate

Standard closing pass. Same pattern as 1.2 Task 10.

## Testing approach

Standard TDD per repo convention. Each work item produces unit
tests before implementation. Integration test
`tests/integration/test_sleeves_end_to_end.py` (new) exercises a
canned 300-day historical sequence through both sleeves and
confirms:

- Both sleeves produce non-empty trade streams for the bulk of
  the window
- Regime transitions flip exposure correctly (especially the
  `stressed` liquidation path)
- Evaluation against benchmark stack produces a non-None
  `EvaluationEvidencePack` with valid `candidate_metrics`

## Acceptance criteria

Sub-tranche 1.3 is complete when:

1. `SleeveProtocol` and its supporting types are defined and
   tested.
2. `apply_regime_exposure_floor` enforces the exact mapping
   table in §D4 of this spec.
3. `TrendSleeve` produces valid `SleeveTrade` outputs across the
   canonical 8-ETF universe, with vol-targeted sizing and regime
   filter applied.
4. `VolManagedBetaSleeve` produces valid `SleeveTrade` outputs
   for SPY with Moreira-Muir's intrinsic sizing preserved and
   regime filter applied.
5. `simulate_sleeve_returns` bridges sleeve output into
   `candidate_returns` for Gate 1 evaluation.
6. Both sleeves are linked from the strategy registry via
   `sleeve_class_path`.
7. `uv run pytest -q`, `uv run mypy src/tradingx`,
   `uv run ruff check`, `python3 scripts/check_index.py`, and
   `./scripts/validate` all pass.
8. Gate 1 evaluation against the benchmark stack runs for both
   sleeves and produces evidence packs. Pass/fail outcomes are
   not gated on — we're validating the plumbing, not the edge.

## Decisions resolved (no open items)

All D1–D5 resolutions from BRIEF-0002 are implemented here. No
new open decisions introduced.

Two implementation-level judgment calls for Codex:

1. **Where does `_derive_side` live?** Currently duplicated in
   `trend.py` and `vol_managed_beta.py` for module-local clarity.
   Codex may extract to `sleeves/base.py` if the duplication feels
   wrong. Either is fine.
2. **Exact liquidation timing in `stressed` regime.** The spec
   says "next bar." If Codex sees a reason to make it "same bar"
   (equivalent to a market order at today's close), that's
   defensible — flag the choice in the commit message.

## Governance impact

- Register `DESIGN-0014` in INDEX.
- No new ADRs. The three-tier benchmark stack (ADR-0021) and
  reframed Gate 1 (ADR-0022) remain the evaluation authority.
- No GATES-0001 amendment — Gate 1 criteria unchanged.
- No BRIEF-0002 amendment — D1–D5 resolutions stand as-is; this
  spec implements them.

## References

### Repo documents

- [BRIEF-0002](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
- [FFL-0001](/docs/roadmap/future-features-ledger.md) — deferred items
- [SPEC-0013](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [DESIGN-0011](/docs/superpowers/specs/2026-04-21-tranche-1-1-validation-infrastructure-design.md)
- [DESIGN-0013](/docs/superpowers/specs/2026-04-21-tranche-1-2-market-state-features-design.md)
- [ADR-0021](/docs/adrs/ADR-0021-benchmark-stack.md)
- [ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)

### Existing source files

- [src/tradingx/signals/trend.py](/src/tradingx/signals/trend.py) —
  TSMOM signal scaffold
- [src/tradingx/signals/vol_target_spy.py](/src/tradingx/signals/vol_target_spy.py)
  — Moreira-Muir vol-managed signal scaffold
- [src/tradingx/features/regime.py](/src/tradingx/features/regime.py)
  — `classify_regime`
- [src/tradingx/features/volatility.py](/src/tradingx/features/volatility.py)
  — `forecast_volatility`
- [src/tradingx/strategy.py](/src/tradingx/strategy.py) — candidate
  registry

### External references

- Moskowitz, T. J., Ooi, Y. H., & Pedersen, L. H. (2012). "Time
  Series Momentum." *Journal of Financial Economics.*
- Moreira, A., & Muir, T. (2017). "Volatility-Managed Portfolios."
  *Journal of Finance.* https://www.nber.org/papers/w22208
- Corsi, F. (2009). "A Simple Approximate Long-Memory Model of
  Realized Volatility." (HAR-RV; currently available in
  `forecast_volatility` but not selected for either sleeve in
  this tranche — EWMA wins for trend per 1.2's retune; GARCH
  remains the vol-target default.)
