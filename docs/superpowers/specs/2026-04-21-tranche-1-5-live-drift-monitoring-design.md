---
id: DESIGN-0016
title: Tranche 1.5 live drift monitoring
version: 0.1.0
status: draft
created: 2026-04-21
last_amended: 2026-04-21
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# DESIGN-0016: Tranche 1.5 live drift monitoring

## Status

Draft on 2026-04-21. Fifth and final sub-tranche under
[BRIEF-0002](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
tranche-1 plan. Pending Hussam approval and Codex peer review.

## Purpose

Fill the single remaining tranche-1 completion criterion as
defined by [BRIEF-0002 v1.2.0](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md):

> "Live drift diagnostics emit alarms against calibrated
> thresholds across PSI on features, KS on signal outputs,
> execution-quality drift, and live-vs-backtest P&L divergence
> for the currently-active sleeve-backed strategy. Multi-sleeve
> P&L divergence is deferred to Gate-4-enablement work — see
> DESIGN-0016 §Not in scope."

1.5 turns the drift-alarm stub shipped in
[DESIGN-0015 §W6](/docs/superpowers/specs/2026-04-21-tranche-1-4-portfolio-construction-and-drawdown-defense-design.md)
— the `DriftAlarmGatewayProtocol` in
[src/tradingx/portfolio/sleeve_runtime.py:32](/src/tradingx/portfolio/sleeve_runtime.py:32)
that `SleeveRuntimeController` consults but whose concrete
implementation is a no-op stub in tranche 1.4 — into a real
drift-alarm gateway backed by four independent monitors. It
also adds the live active-sleeve attribution infrastructure that
P&L-divergence monitoring and the `RollingWindowSource.LIVE_DAILY_RETURNS`
upgrade both need. Multi-sleeve attribution is deferred with the
rest of the multi-sleeve runtime wiring (§Not in scope).

Scope:

1. **PSI drift on feature distributions.** Population Stability
   Index computed against a frozen reference distribution for
   each monitored feature (regime composite inputs + sleeve
   signal inputs).
2. **KS drift on signal outputs.** Two-sample Kolmogorov–Smirnov
   test comparing live signal-output distributions against the
   frozen reference.
3. **Execution-quality drift.** Realized slippage vs. the
   cost-model's predicted slippage, reusing the replay-slippage
   primitives already at
   [src/tradingx/replay_slippage.py](/src/tradingx/replay_slippage.py).
   The drift monitor layers a rolling-window aggregation + alarm
   threshold on top of the existing per-execution divergence
   ratios.
4. **Live-vs-backtest P&L divergence — active-sleeve only in
   1.5.** Rolling divergence between the live portfolio's
   realized daily returns and the backtest-expected returns from
   the currently-active sleeve-backed strategy. Multi-sleeve
   live P&L divergence is out of scope for 1.5 because the
   runtime today activates a single strategy at a time and
   persists only the aggregate `RuntimePortfolioPlan` (see
   Codex round-1 review note below and §Not in scope).
5. **`DriftAlarmGateway` concrete implementation.** Aggregates
   the four monitors into a single `has_alarm(sleeve_id)` signal.
6. **Active-sleeve attribution record.** A per-trading-day
   `SleeveDailyAttributionRecord` produced by the end-of-session
   automation hook for the **currently-active** sleeve-backed
   strategy only. Daily return is derived from persisted
   portfolio state snapshots + the day's bars — no changes to
   `TradeIntent`, `ExecutionLifecycleRecord`, or
   `ClosedTradeRecord`. Because the runtime is single-active in
   1.5, the active sleeve's live return equals the portfolio's
   live return for that session; the "attribution" step is
   therefore a straight capture of active-strategy identity +
   portfolio return, NOT a multi-sleeve decomposition.
7. **Reference-distribution snapshot artifact.** A frozen
   snapshot captured once at deployment time that both PSI and
   KS compare against. Single-file JSON; versioned; replacement
   requires explicit operator action.
8. **Operator surface.** A new `portfolio_drift_alarm`
   operator-alert category and matching
   `RiskControlEvent.control_type = "portfolio_drift_alarm"`
   emission, plus a dashboard diagnostic row per drift monitor.
   The alert category mirrors the `control_type` string and
   the hard-halt pattern (`portfolio_hard_halt`) so dashboards
   and alert routing can key off one canonical value. Consumes
   the same operator dashboard plumbing shipped by SPEC-0010.
9. **`RollingWindowSource.LIVE_DAILY_RETURNS` implementation.**
   The `NotImplementedError` guardrail shipped in 1.4 is
   replaced with a reader that consumes
   `SleeveDailyAttributionRecord` rows. Default remains
   `TRIAL_SUMMARY` for backwards compatibility; operators opt
   into `LIVE_DAILY_RETURNS` via blueprint configuration.

**Not in scope** (deferred explicitly):

- **Multi-sleeve live runtime wiring** — *added in Codex
  round-1 review.* The current runtime activates one
  `strategy_id` at a time via
  [runtime_strategy_registry.py](/src/tradingx/runtime_strategy_registry.py),
  builds a single aggregate
  [`RuntimePortfolioPlan`](/src/tradingx/runtime_portfolio.py:65),
  and the service loop persists only that aggregate at
  [service.py:206](/src/tradingx/service.py:206). There is no
  persisted per-sleeve target-weight stream during live sessions,
  and no multi-sleeve co-execution path. Shipping that wiring
  (sleeve-aware portfolio plan + per-sleeve persistence + a
  multi-strategy activation gateway) is Gate-4-enablement work
  sized outside this sub-tranche. 1.5 explicitly narrows its
  live-attribution surface to the **currently-active** sleeve-
  backed strategy and treats multi-sleeve attribution as a
  dependency of a future sub-tranche. When that wiring lands,
  `SleeveDailyAttributionRecord` gains a proper decomposition
  step and the P&L divergence monitor expands from "active
  sleeve only" to "per-sleeve" without changes to the drift
  package's public API.
- Auto-halt on drift. 1.5 emits alarms; interpretation and
  action remain with the operator. Auto-halt wiring is a
  tranche-2+ decision; until then, the drift alarm flows into
  `SleeveRuntimeController` per §W6 precedence (operator halt >
  drift alarm > trial-summary Sharpe gate) but does not
  automatically cause new termination actions beyond what W6
  already specifies.
- Real-time / in-loop drift computation. 1.5 uses end-of-session
  batch computation driven by the market-day automation loop at
  [src/tradingx/automation.py](/src/tradingx/automation.py).
- HMM / Markov-switching regime-drift detection — deferred per
  [FFL-0001-07](/docs/roadmap/future-features-ledger.md).
- CPCV/PBO — deferred per
  [FFL-0001-06](/docs/roadmap/future-features-ledger.md). 1.5's
  drift stack does not couple with CPCV; they ship independently.
- Changes to the five Gate 1 criteria. Gate 1 remains at
  GATES-0001 v1.2.0; drift alarms are paper-monitoring signals
  for the operator, not gate criteria.
- New runtime execution pathways. 1.5 reads persisted live data
  and computes drift statistics; it does not change how orders
  flow through the runtime host.
- Persisted live feature-observation or signal-observation
  streams. Feature values and signal outputs are **recomputed**
  from persisted bars + regime/signal logic at monitor-refresh
  time (§P1 below). 1.5 does not introduce a new service-cycle
  writer for feature/signal observations.

## Prerequisites

- `main` at or beyond the tranche-1.4 merge (`02a3c97`). Brings
  the portfolio package, `PortfolioBlueprint`, the throttles,
  `PortfolioHardHaltController`, `SleeveRuntimeController` with
  the `DriftAlarmGatewayProtocol` stub, the marginal-contribution
  Gate 1 criterion, and GATES-0001 v1.2.0.
- `main` at or beyond the tranche-1.1 merge: trials ledger +
  `EvaluationEvidencePack`.
- `main` at or beyond the tranche-1.2 merge: regime composite.
- **All BRIEF-0002 D1–D5 resolutions remain locked.** 1.5 does
  not re-open any of them.
- Existing replay-slippage infrastructure at
  [src/tradingx/replay_slippage.py](/src/tradingx/replay_slippage.py)
  is the base for the execution-quality drift monitor. 1.5 adds
  rolling aggregation + alarming; it does NOT reimplement the
  per-execution slippage comparison.

## Design principles (pre-empt Codex P1 patterns)

Carried forward from DESIGN-0015 §Design principles. Repeated
here because each applies to 1.5 as well.

### P1 — No new execution model; drift reads persisted records OR recomputes from bars

Codex's round-1 review correctly pointed out that the current
runtime does NOT persist a feature-observation stream, a
signal-output stream, or a per-sleeve target-weight history.
The persisted live-runtime surface stops at: market bars
(`AlpacaMarketDataGateway` cache), `RuntimePortfolioPlan`
(aggregate), `ExecutionLifecycleRecord`, `ClosedTradeRecord`,
`ReplaySlippageRecord`, `ReconciliationSnapshot`, portfolio
state snapshots, and the new 1.5 `SleeveDailyAttributionRecord`
(active-sleeve only).

The principle therefore has two branches:

- **Reads persisted records.** Execution drift consumes
  `ReplaySlippageRecord`; P&L divergence consumes
  `SleeveDailyAttributionRecord` + the backtest-reference-
  returns artifact; attribution consumes portfolio state
  snapshots + bars. No monitor re-runs the backtest engine,
  re-fetches broker state, or simulates fills.
- **Recomputes from bars (feature + signal monitors).** PSI and
  KS monitors take live SAMPLES that are computed ON-DEMAND
  from persisted bars + the regime-classification logic
  ([features/regime.py](/src/tradingx/features/regime.py)) and
  the sleeve signal logic ([signals/trend.py](/src/tradingx/signals/trend.py),
  [signals/vol_target_spy.py](/src/tradingx/signals/vol_target_spy.py)).
  Recomputation is cheap (pure functions over a bounded window)
  and keeps 1.5 from introducing a new service-cycle writer.
  The readers codify this recomputation path explicitly in §W8.

The `SleeveDailyAttributionRecord` writer introduced in §W6
**derives** the active sleeve's daily P&L from portfolio state
snapshots + the day's bars; it does NOT add a parallel
execution path.

### P2 — New fields / records on both emission and consumption

New persisted records (`SleeveDailyAttributionRecord`, the
feature-distribution reference snapshot, drift-alarm events)
carry every field that downstream consumers need, including the
`sleeve_id` / `alarm_id` / `trading_day` keys required for
joining across session boundaries. Optional fields default to
`None` so legacy records deserialize unchanged.

### P3 — Alarms are observable events, not log lines

Every drift-monitor verdict emits a first-class event:

- Below-threshold verdicts produce a
  `RiskControlEvent(control_type="portfolio_drift_alarm",
  severity="info", blocked=False)` — useful for the operator
  dashboard's trend chart but NOT an alarm.
- At-or-above-threshold verdicts produce a
  `RiskControlEvent(control_type="portfolio_drift_alarm",
  severity="warning"|"critical", blocked=False)` AND an
  `OperatorAlert(category="portfolio_drift_alarm")`. `blocked`
  is always False: 1.5 emits evidence, not trade blocks.

No drift monitor silently skips a session. If inputs are
insufficient (e.g., < 30 days of live data), the monitor emits
an `info` event with `status="pending"` so the absence of a
verdict is itself observable.

### P4 — Dimensional correctness

- **PSI** is dimensionless (`[0, +∞)`; typical thresholds at
  0.1 moderate / 0.25 significant).
- **KS statistic** is a probability-space scalar in `[0, 1]`;
  the associated **p-value** is also in `[0, 1]`.
- **Execution-quality drift ratio** is a dimensionless ratio
  (realized slippage bps / predicted slippage bps); thresholds
  at 1.5× warning, 2.0× critical (matches Gate 3 `<= 1.5x`
  realized-slippage criterion).
- **P&L divergence** is either an **absolute-return delta**
  (daily return units) or a **Sharpe delta** (dimensionless
  ratio of Sharpes). The blueprint stores both thresholds; the
  monitor reports both values so the operator can disambiguate.
- **Returns** throughout are `Decimal` at module boundaries,
  `float` only inside pandas/numpy computations (consistent
  with backtest.py conventions).

### P5 — Single source of truth

- **Reference distribution:** ONE snapshot artifact per feature
  / signal, identified by `reference_snapshot_id`. PSI and KS
  both read the same artifact. Replacement is an explicit
  operator action (new `recalibrate_drift_reference` operator
  command) recorded in the audit log.
- **Threshold values:** stored on `DriftMonitorBlueprint`.
  Never duplicated inline in a monitor module.
- **Alarm aggregation:** `DriftAlarmGateway.has_alarm(sleeve_id)`
  is the ONLY consumer-facing aggregation. Individual monitor
  outputs are public (readable for the dashboard) but not
  consumed by `SleeveRuntimeController`.

## Drift-monitor taxonomy (summary)

| Monitor | Feeds | Metric | Threshold source | Alarm severity |
|---|---|---|---|---|
| PSI (features) | Feature values vs frozen reference distribution | Population Stability Index | `blueprint.psi_warning`, `blueprint.psi_critical` | warning if ≥ warning; critical if ≥ critical |
| KS (signals) | Signal outputs vs frozen reference | KS statistic + p-value | `blueprint.ks_p_value_critical` | critical if p < threshold |
| Execution drift | `ReplaySlippageRecord.divergence_ratio` rolling window | Mean abs divergence ratio | `blueprint.execution_drift_warning`, `blueprint.execution_drift_critical` | warning if ≥ 1.5×; critical if ≥ 2.0× |
| P&L divergence | Live active-sleeve daily return series (from `SleeveDailyAttributionRecord`) vs backtest-expected series for that sleeve | Absolute delta + Sharpe delta | `blueprint.pnl_absolute_warning`, `blueprint.pnl_sharpe_warning`, same for `_critical` | composite (either metric breaching) |

Monitors run at different scopes:

- **PSI** — portfolio-level per feature (features are shared
  across sleeves). A critical PSI verdict on a feature that
  both shipped sleeves consume raises `has_alarm` for both.
- **KS** — per shipped sleeve, computed by recomputing each
  sleeve's signal on the live bar window (§P1). A critical KS
  verdict for sleeve X raises `has_alarm(X)` only.
- **Execution drift** — per symbol, aggregated across the
  rolling window of `ReplaySlippageRecord` entries.
  `has_alarm(sleeve_id)` is True if ANY symbol the sleeve
  touches has a critical execution-drift verdict.
- **P&L divergence** — active-sleeve only in 1.5 (§Not in
  scope). When the currently-active strategy is sleeve-backed,
  its P&L-divergence verdict is computed; all other sleeves
  skip P&L divergence for the session.

## Architecture overview

### New modules

1. **`src/tradingx/drift/__init__.py`** — package init.
2. **`src/tradingx/drift/blueprint.py`** —
   `DriftMonitorBlueprint` + `DriftThresholds` carrying all
   threshold constants.
3. **`src/tradingx/drift/reference.py`** —
   `ReferenceDistributionSnapshot` dataclass,
   `build_reference_distribution_snapshot(...)`,
   `load_reference_distribution_snapshot(...)`,
   `write_reference_distribution_snapshot(...)`.
4. **`src/tradingx/drift/psi.py`** —
   `compute_population_stability_index(...)`.
5. **`src/tradingx/drift/ks.py`** —
   `compute_kolmogorov_smirnov(...)` returning
   `KSResult(statistic, p_value)`.
6. **`src/tradingx/drift/execution.py`** —
   `compute_execution_drift_ratio(...)` over a rolling window
   of `ReplaySlippageRecord` entries.
7. **`src/tradingx/drift/attribution.py`** —
   `SleeveAttributionRecorder` (active-sleeve-only per §W6),
   `build_sleeve_daily_attribution_record(...)`.
8. **`src/tradingx/drift/pnl_divergence.py`** —
   `compute_live_vs_backtest_pnl_divergence(...)` over a rolling
   window.
9. **`src/tradingx/drift/gateway.py`** — `DriftAlarmGateway`
   concrete class implementing
   `DriftAlarmGatewayProtocol`.
10. **`src/tradingx/drift/live_returns_source.py`** — the
    `LIVE_DAILY_RETURNS` reader consumed by
    `SleeveRuntimeController` when its config's
    `rolling_window_source` is `LIVE_DAILY_RETURNS`.

### New dataclasses (see §W1 for full shapes)

- `DriftMonitorBlueprint`, `DriftThresholds`.
- `ReferenceDistributionSnapshot` (frozen).
- `KSResult` (frozen).
- `SleeveDailyAttributionRecord` (frozen).
- `DriftMonitorVerdict` (frozen) — per-monitor output carrying
  the computed metric + threshold + severity + details.

### Modified files

- `src/tradingx/types.py` — add
  `SleeveDailyAttributionRecord`.
  `RiskControlEvent.control_type` is a string; no schema change
  needed (the new value `"portfolio_drift_alarm"` is an
  additional constant documented in §W8). Add it to the
  `control_type` constants module if one exists; otherwise
  document the string as load-bearing via a Final in
  `tradingx/drift/gateway.py`.
- `src/tradingx/persistence.py` —
  `write_sleeve_daily_attribution_record`,
  `list_sleeve_daily_attribution_records`. Mirror the existing
  `write_operator_alert` / `list_*` patterns.
- `src/tradingx/portfolio/sleeve_runtime.py` — remove the
  `NotImplementedError` raise in the
  `rolling_window_source == LIVE_DAILY_RETURNS` branch; inject
  a new optional `live_returns_reader` protocol that the
  controller calls instead of the trials ledger when
  `LIVE_DAILY_RETURNS` is selected.
- `src/tradingx/operator_control.py` — add
  `recalibrate_drift_reference(snapshot_id)` operator action
  that records an audit entry; the actual snapshot replacement
  happens via the `drift/reference.py` writer.
- `docs/validation/acceptance_gates.md` — no schema change;
  add a note in Gate 3's primary-evidence block that
  `ExecutionQualityDriftMonitor` alarms are surfaced on the
  operator dashboard and contribute to Gate 3's "realized
  slippage ≤ 1.5× backtest assumption" evidence.
- New tests under `tests/unit/test_drift_*.py` and one
  integration test
  `tests/integration/test_drift_end_to_end.py`.

### Untouched (intentional)

- `src/tradingx/replay_slippage.py` — the per-execution
  slippage comparison is unchanged; `drift/execution.py` layers
  on top, it does NOT rewrite.
- `src/tradingx/portfolio_construction.py` (the legacy
  candidate-weight path) — same rationale as 1.4: legacy path
  still supports the baseline and mean-reversion candidates.
- `src/tradingx/validation.py` — Gate 1 / Gate 2 validation
  flows are untouched. Drift alarms are paper-monitoring
  signals, not gate criteria.
- `src/tradingx/runtime_host.py` — the hard-halt path is the
  only tranche-1 runtime-state transition; drift alarms do not
  trigger hard halts in 1.5.
- `src/tradingx/backtest.py`, `src/tradingx/costs.py` — engine
  and cost primitives unchanged.

## Work items

### W1 — `DriftMonitorBlueprint` + `DriftThresholds`

**Files:**
- Create: `src/tradingx/drift/__init__.py`
- Create: `src/tradingx/drift/blueprint.py`
- Create: `tests/unit/test_drift_blueprint.py`

**Contract:**

```python
# src/tradingx/drift/blueprint.py

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DriftThresholds:
    """Per-monitor threshold configuration.

    All thresholds are Decimals at module boundaries; monitors
    convert to float internally for numpy / pandas work.
    """

    psi_warning: Decimal = Decimal("0.10")
    psi_critical: Decimal = Decimal("0.25")
    ks_p_value_critical: Decimal = Decimal("0.05")
    execution_drift_warning: Decimal = Decimal("1.5")
    execution_drift_critical: Decimal = Decimal("2.0")
    pnl_absolute_warning: Decimal = Decimal("0.02")   # 2% daily return delta
    pnl_absolute_critical: Decimal = Decimal("0.04")  # 4% daily return delta
    pnl_sharpe_warning: Decimal = Decimal("0.30")     # 30% Sharpe degradation
    pnl_sharpe_critical: Decimal = Decimal("0.50")    # 50% Sharpe degradation


@dataclass(frozen=True)
class DriftMonitorBlueprint:
    blueprint_id: str
    thresholds: DriftThresholds = DriftThresholds()
    feature_monitor_names: tuple[str, ...] = (
        "spy_close_over_sma_200",
        "vix_level",
        "yield_curve_spread_bps",
        "trend_signal_strength",
        "vol_forecast_ewma",
    )
    signal_monitor_sleeve_ids: tuple[str, ...] = (
        "trend-following-v1",
        "vol-target-v1",
    )
    execution_drift_rolling_window_days: int = 30
    pnl_divergence_rolling_window_days: int = 60
    minimum_live_days_for_alarm: int = 30
```

**Why these defaults:**

- PSI 0.10 / 0.25: industry-standard thresholds (Siddiqi 2006).
- KS p < 0.05: standard statistical-significance threshold.
- Execution drift 1.5× / 2.0×: consistent with
  [GATES-0001 Gate 3](/docs/validation/acceptance_gates.md)
  "realized slippage ≤ 1.5× backtest assumption" — warning at
  the Gate 3 threshold itself, critical at 2.0× (the
  replay-vs-paper divergence threshold also in Gate 3).
- P&L absolute deltas: 2% / 4% roughly bracket one / two sigma
  of a 12%-annualized-vol sleeve at daily resolution.
- P&L Sharpe deltas: 30% matches the Gate 1
  `out_of_sample_profile` tolerance and the FFL-0001-01
  Kelly-switch gate's live-vs-backtest Sharpe rule.
- Minimum live days = 30: below this, monitors emit `pending`
  rather than a verdict (per §P3).

**Tests cover:**

- Blueprint accepts custom thresholds; default thresholds match
  the constants above.
- Frozen-dataclass semantics; round-trip equality.
- Empty feature_monitor_names is accepted (no PSI monitors run).
- Empty signal_monitor_sleeve_ids is accepted (no KS monitors
  run).
- `rolling_window_days` fields must be > 0 (`ValueError`
  otherwise via `__post_init__`).

### W2 — Reference-distribution snapshot

**Files:**
- Create: `src/tradingx/drift/reference.py`
- Create: `tests/unit/test_drift_reference_snapshot.py`

**Contract:**

```python
# src/tradingx/drift/reference.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]


@dataclass(frozen=True)
class FeatureDistribution:
    feature_name: str
    bin_edges: tuple[Decimal, ...]         # quantile edges, len = n_bins + 1
    bin_proportions: tuple[Decimal, ...]   # len = n_bins, sums to 1.0
    observation_count: int


@dataclass(frozen=True)
class SignalDistribution:
    sleeve_id: str
    observed_samples: tuple[Decimal, ...]  # empirical CDF for KS test
    observation_count: int


@dataclass(frozen=True)
class ReferenceDistributionSnapshot:
    reference_snapshot_id: str
    generated_at_utc: datetime
    blueprint_id: str
    feature_distributions: tuple[FeatureDistribution, ...]
    signal_distributions: tuple[SignalDistribution, ...]
    reference_window_start_utc: datetime
    reference_window_end_utc: datetime


def build_reference_distribution_snapshot(
    *,
    reference_snapshot_id: str,
    blueprint_id: str,
    feature_samples_by_name: dict[str, pd.Series],
    signal_samples_by_sleeve_id: dict[str, pd.Series],
    reference_window_start_utc: datetime,
    reference_window_end_utc: datetime,
    n_bins: int = 10,
) -> ReferenceDistributionSnapshot:
    """Build a frozen reference distribution from historical
    samples. Uses quantile-based binning (decile-by-default)
    for PSI computation; preserves the raw sample series for
    KS computation.

    Pure function: no I/O; deterministic on inputs.
    """


def write_reference_distribution_snapshot(
    path: Path,
    snapshot: ReferenceDistributionSnapshot,
) -> Path:
    """Serialize to JSON. Path is operator-supplied."""


def load_reference_distribution_snapshot(
    path: Path,
) -> ReferenceDistributionSnapshot:
    """Deserialize from JSON. Raises FileNotFoundError if absent."""
```

**Replacement semantics.** The snapshot is replaced only by an
explicit operator action. `operator_control.recalibrate_drift_reference(
snapshot_id)` records an audit entry; the new snapshot file must
be written by the operator (or by a scheduled recalibration
script — future work) to a well-known path. Accidental
replacement is prevented by the audit trail, not by file
immutability.

**Tests cover:**

- Building a snapshot from canned samples produces deterministic
  bin edges (quantile-based; specific values).
- Bin proportions sum to 1.0 within rounding.
- Observation count matches sample length.
- Serialization round-trip preserves every field.
- `load_reference_distribution_snapshot(nonexistent_path)`
  raises `FileNotFoundError` — no silent empty snapshot.
- Two snapshots with the same inputs but different
  `reference_snapshot_id` are non-equal (identity is separate
  from content).

### W3 — PSI computation

**Files:**
- Create: `src/tradingx/drift/psi.py`
- Create: `tests/unit/test_drift_psi.py`

**Contract:**

```python
def compute_population_stability_index(
    *,
    reference_distribution: FeatureDistribution,
    live_samples: pd.Series,
    epsilon: float = 1e-6,
) -> Decimal:
    """Compute PSI using the reference's bin edges.

    PSI = sum over bins of
              (live_prop - ref_prop) * log(live_prop / ref_prop)

    With bins clamped at `epsilon` to avoid log(0); this is the
    standard convention (Siddiqi 2006) and produces finite PSI
    when a live distribution contains bins the reference missed.

    Pure function; returns Decimal via Decimal(str(float_result)).
    """
```

**Dimensional note.** PSI values are non-negative. Higher =
more drift. Interpretation bands (industry standard):

- PSI < 0.10: insignificant drift.
- 0.10 ≤ PSI < 0.25: moderate drift.
- PSI ≥ 0.25: significant drift.

These match `DriftThresholds.psi_warning / psi_critical`.

**Tests cover:**

- Identical distributions → PSI = 0 (within epsilon).
- Significant shift (live distribution bimodal, ref unimodal) →
  PSI > 0.25 threshold.
- Empty live_samples raises `ValueError`.
- Live samples outside the reference bin range are assigned to
  the nearest bin (clipping semantics); explicit regression test.
- Zero-proportion live bins are handled via epsilon (no
  `log(0)` errors).

### W4 — KS computation

**Files:**
- Create: `src/tradingx/drift/ks.py`
- Create: `tests/unit/test_drift_ks.py`

**Contract:**

```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class KSResult:
    statistic: Decimal  # [0, 1]
    p_value: Decimal    # [0, 1]


def compute_kolmogorov_smirnov(
    *,
    reference_samples: tuple[Decimal, ...],
    live_samples: pd.Series,
) -> KSResult:
    """Two-sample KS test. Uses scipy.stats.ks_2samp under the
    hood; returns Decimal-wrapped statistic and p-value.

    Pure function.
    """
```

**Tests cover:**

- Identical distributions → p-value ≈ 1.0, statistic ≈ 0.
- Different distributions (shifted mean) → p-value < 0.05.
- Empty live_samples raises `ValueError`.
- Empty reference_samples raises `ValueError`.
- Statistic and p-value both in `[0, 1]`.

### W5 — Execution-quality drift

**Files:**
- Create: `src/tradingx/drift/execution.py`
- Create: `tests/unit/test_drift_execution.py`

**Contract:**

```python
def compute_execution_drift_ratio(
    *,
    replay_records: tuple[ReplaySlippageRecord, ...],
    symbol: str | None = None,
    rolling_window_days: int = 30,
) -> Decimal:
    """Compute the mean absolute divergence ratio over the
    rolling window.

    For each ReplaySlippageRecord r:
        per_record_ratio = abs(r.divergence_ratio)
    Returns mean over the last `rolling_window_days` of records.

    If `symbol` is provided, filters to records whose symbol
    matches; otherwise aggregates across all symbols.

    If fewer than `rolling_window_days` records exist (or zero
    records after filtering), returns Decimal('0') AND the
    gateway treats the verdict as `pending` via the
    minimum-live-days check (see §W9).
    """
```

**Threshold matches Gate 3.** Warning at 1.5× (the Gate 3 limit
itself), critical at 2.0× (the replay-vs-paper divergence
threshold in Gate 3). When execution drift goes critical on a
symbol the sleeve touches, the sleeve's drift alarm becomes
True and `SleeveRuntimeController` terminates (per §W6
precedence: operator halt > drift alarm > Sharpe gate).

**Tests cover:**

- Empty record tuple → `Decimal("0")`.
- Records within window contribute; older records excluded.
- Symbol filter narrows correctly.
- Computed mean matches manual expectation on canned data.

### W6 — Active-sleeve daily attribution

**Files:**
- Create: `src/tradingx/drift/attribution.py`
- Modify: `src/tradingx/types.py` (add
  `SleeveDailyAttributionRecord`).
- Modify: `src/tradingx/persistence.py` (add writer + reader).
- Create: `tests/unit/test_drift_attribution.py`

**Scope narrowing (Codex round-1 P1).** The 1.5 runtime is
single-active-strategy. The aggregate `RuntimePortfolioPlan` is
the only live target-weight artifact the service loop persists,
and the active `strategy_id` on `ApprovedWeightSnapshot` and
`StrategyActivationRecord` identifies which sleeve-backed
candidate — if any — is live. 1.5 therefore scopes
`SleeveDailyAttributionRecord` to the **currently-active
sleeve-backed strategy**. For any session where the active
strategy's candidate has `sleeve_class_path is not None`, we
write exactly one record; for sessions where the active
strategy is non-sleeve (today: `baseline-long-only-v1` or
`mean-reversion-v1`), we write no record. Multi-sleeve
attribution is the Gate-4-enablement expansion called out in
§Not in scope.

**Contract:**

```python
# src/tradingx/types.py (addition)

@dataclass(frozen=True)
class SleeveDailyAttributionRecord:
    attribution_id: str
    sleeve_id: str                  # == active strategy_id; sleeve_class_path resolved
    trading_day: str                # YYYY-MM-DD in exchange calendar
    recorded_at_utc: datetime
    starting_equity: Decimal        # portfolio equity at session open
    ending_equity: Decimal          # portfolio equity at session close
    daily_return: Decimal           # (ending - starting) / starting
    per_symbol_open_weight: tuple[tuple[str, Decimal], ...]   # from portfolio state at open
    per_symbol_close_weight: tuple[tuple[str, Decimal], ...]  # from portfolio state at close
```

```python
# src/tradingx/drift/attribution.py

def build_sleeve_daily_attribution_record(
    *,
    attribution_id: str,
    trading_day: str,
    active_sleeve_id: str,
    open_portfolio_state: PortfolioState,
    close_portfolio_state: PortfolioState,
    recorded_at_utc: datetime,
) -> SleeveDailyAttributionRecord:
    """Capture the active sleeve's session P&L from portfolio
    state snapshots the runtime already persists.

    Because the 1.5 runtime activates a single strategy at a
    time, the live portfolio's daily return IS the active
    sleeve's daily return. The "attribution" step is therefore
    a straight capture: identify the active sleeve_id from the
    current activation record, compute daily_return from
    equity snapshots, record per-symbol open/close weights for
    downstream reconciliation.

    Pure function; no I/O. The caller — an end-of-session
    hook in automation.py — persists the result via
    SleeveDailyAttributionRecordStore.

    When multi-sleeve live wiring lands in a future sub-tranche,
    this function's signature expands (one record per active
    sleeve, with a decomposition step) without changing its
    name or the downstream consumer surface in §W7.
    """


class SleeveAttributionRecorder:
    """End-of-session hook. Reads the current activation record
    + open/close portfolio state snapshots, builds the active
    sleeve's SleeveDailyAttributionRecord, persists it.

    Skips the write when the active strategy has
    sleeve_class_path=None (non-sleeve candidate) — attribution
    for non-sleeve strategies is out of scope in 1.5.
    """

    def __init__(
        self,
        *,
        activation_gateway: "ActivationGatewayProtocol",
        attribution_store: "SleeveDailyAttributionRecordStore",
        now_provider: Callable[[], datetime],
    ) -> None:
        ...

    def record_session(
        self,
        *,
        trading_day: str,
        open_portfolio_state: PortfolioState,
        close_portfolio_state: PortfolioState,
    ) -> SleeveDailyAttributionRecord | None:
        """Returns None when the active strategy is non-sleeve."""
```

**Why NOT threading `sleeve_id` through the intent chain.**
Changing `TradeIntent`, `ExecutionLifecycleRecord`, and
`ClosedTradeRecord` to carry `sleeve_id` would be a cross-
cutting refactor touching the order-emission layer, operator
dashboards, and Gate 3 evidence. The active-sleeve-capture
model above avoids every one of those touchpoints by reading
only the pieces already persisted: activation records +
portfolio-state snapshots. Multi-sleeve wiring will need its
own dedicated tranche anyway (see §Not in scope); no reason to
make 1.5 pay that tax early.

**Tests cover:**

- Active strategy with `sleeve_class_path` set → record is
  written with `sleeve_id` == activation's `strategy_id` and
  `daily_return` == `(close_equity - open_equity) / open_equity`.
- Active strategy with `sleeve_class_path=None` → `record_session`
  returns None and no artifact is written.
- `open_equity == 0` → raises `ValueError` (invalid session).
- Per-symbol open/close weights are captured from
  `PortfolioState.positions` (price × quantity / equity).
- Record writer + reader round-trip preserves every field;
  ordering by `(sleeve_id, trading_day)` descending on read.

### W7 — Live-vs-backtest P&L divergence

**Files:**
- Create: `src/tradingx/drift/pnl_divergence.py`
- Create: `tests/unit/test_drift_pnl_divergence.py`

**Contract:**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PnlDivergenceVerdict:
    sleeve_id: str
    live_daily_return_series: tuple[Decimal, ...]
    backtest_daily_return_series: tuple[Decimal, ...]
    absolute_delta: Decimal  # mean(|live - backtest|) over window
    sharpe_delta_ratio: Decimal  # (live_sharpe - backtest_sharpe) / max(|backtest_sharpe|, floor)
    severity: str  # "info" | "warning" | "critical"


def compute_live_vs_backtest_pnl_divergence(
    *,
    sleeve_id: str,
    live_attribution_records: tuple[SleeveDailyAttributionRecord, ...],
    backtest_returns_series: tuple[Decimal, ...],
    rolling_window_days: int = 60,
    minimum_live_days: int = 30,
    thresholds: DriftThresholds,
) -> PnlDivergenceVerdict:
    """Compare realized live returns to backtest-expected
    returns over a rolling window.

    If fewer than `minimum_live_days` of live records exist,
    returns a verdict with severity='pending'.

    Absolute delta = mean over window of |live_i - backtest_i|
    Sharpe delta ratio = (live_sharpe - backtest_sharpe) /
                         max(|backtest_sharpe|, Decimal('0.3'))
        (the 0.3 floor matches Gate 1's out-of-sample-profile
         denominator convention)

    Severity is the worst of:
    - absolute_delta >= pnl_absolute_critical → critical
    - else absolute_delta >= pnl_absolute_warning → warning
    - abs(sharpe_delta_ratio) >= pnl_sharpe_critical → critical
    - else abs(sharpe_delta_ratio) >= pnl_sharpe_warning → warning
    - otherwise → info.

    Pure function.
    """
```

**Backtest-reference series source (Codex round-1 P2 fix).**
For the 2 shipped sleeves (`trend-following-v1`,
`vol-target-v1`), the backtest-expected series is produced by
the same pass-1 evaluation path that Gate 1 runs —
`_candidate_returns(candidate, ...)` in
[src/tradingx/validation.py:493](/src/tradingx/validation.py:493).
The persisted artifact lives under the **runtime artifact tree**,
not `config/strategy/*`:

```
{config.runtime.artifact_root}/drift/backtest_reference_returns/<sleeve_id>.json
```

Runtime-generated drift evidence belongs under
`config.runtime.artifact_root` alongside other runtime artifacts
(journal, operator store, drill records). The `config/strategy/*`
tree is reserved for operator-reviewed offline configuration
per
[ApprovedWeightSnapshot](/src/tradingx/types.py:648) +
[ApprovedWeightSnapshotStore](/src/tradingx/weights.py:14) —
runtime regeneration of artifacts in that tree would violate
that boundary.

**Artifact writer.** Generated by an end-of-session / activation-
change hook (runs once when a new strategy activation lands;
can also be invoked on operator command via
`operator_control.recalibrate_drift_reference`). The writer
uses `FilesystemArtifactStore` conventions to place the JSON
under the runtime tree with stable naming. The drift monitor
reads this artifact; it does NOT re-run the backtest in the
drift hot path (§P1).

**Live series source.** 1.5's attribution captures only the
active sleeve (§W6). For the currently-active sleeve-backed
strategy, the live daily-return series is built from
`SleeveDailyAttributionRecord.daily_return` values. When the
active strategy changes mid-window, the monitor computes over
the contiguous tail of records for the now-active sleeve only
(there is no cross-sleeve stitching — that would confuse the
"live vs backtest for THIS sleeve" semantics).

**Scope narrowing.** P&L divergence monitoring is
active-sleeve-only in 1.5. A sleeve that is never activated
gets no P&L-divergence verdict, only
PSI/KS/execution-drift verdicts where applicable. This matches
the §Purpose narrowing and the §Not in scope multi-sleeve
deferral.

**Tests cover:**

- Identical live and backtest series → severity='info',
  deltas near zero.
- Live series shifted up by 2% → absolute_delta ≈ 0.02,
  severity depends on threshold (warning at default).
- Live series shifted up by 5% → severity='critical'.
- Sharpe degradation of 40% → severity='warning'.
- Sharpe degradation of 60% → severity='critical'.
- Fewer than minimum_live_days records → severity='pending'.
- Backtest sharpe near zero (use the 0.3 floor in denominator).

### W8 — `DriftAlarmGateway` concrete implementation

**Files:**
- Create: `src/tradingx/drift/gateway.py`
- Create: `tests/unit/test_drift_gateway.py`

**Contract:**

```python
# src/tradingx/drift/gateway.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tradingx.drift.blueprint import DriftMonitorBlueprint
from tradingx.drift.reference import ReferenceDistributionSnapshot
from tradingx.portfolio.sleeve_runtime import DriftAlarmGatewayProtocol
from tradingx.types import (
    OperatorAlert,
    ReplaySlippageRecord,
    RiskControlEvent,
    SleeveDailyAttributionRecord,
)


DRIFT_ALARM_CONTROL_TYPE: Final[str] = "portfolio_drift_alarm"


@dataclass(frozen=True)
class DriftMonitorVerdict:
    monitor_id: str
    sleeve_id: str | None     # None for portfolio-level monitors
    severity: str              # "info" | "warning" | "critical" | "pending"
    metric_value: Decimal | None
    threshold_value: Decimal | None
    details: str


class BacktestReferenceReturnsReaderProtocol(Protocol):
    """Reads the backtest-reference-returns artifact written by
    the §W7 end-of-activation hook. Artifact path is
    {config.runtime.artifact_root}/drift/backtest_reference_returns/<sleeve_id>.json
    — runtime tree, not config tree.
    """

    def returns_for_sleeve(
        self, sleeve_id: str
    ) -> tuple[Decimal, ...]: ...


class FeatureSampleReaderProtocol(Protocol):
    """Recomputes live feature samples from persisted bars +
    regime-classification logic. There is NO persisted live
    feature-observation stream (Codex round-1 P1 fix). The
    concrete implementation in §Architecture overview's
    `drift/gateway.py` evaluates
    `features.regime.classify_regime` plus the other feature
    extractors on the persisted bar history for the requested
    window and returns the resulting series.

    Pure function over bars; deterministic and idempotent;
    cost is bounded by `window_days` of bars.
    """

    def live_samples(
        self, feature_name: str, *, window_days: int
    ) -> pd.Series: ...


class SignalSampleReaderProtocol(Protocol):
    """Recomputes live signal samples by evaluating the sleeve's
    signal logic on persisted bars. There is NO persisted
    live signal-observation stream (Codex round-1 P1 fix).

    KS runs per SHIPPED sleeve (both `trend-following-v1` and
    `vol-target-v1`), not only the currently-active one. The
    concrete implementation in `drift/gateway.py` resolves each
    `sleeve_id` to its `StrategyCandidate` by looking it up in
    `build_mandatory_candidate_registry()` by `candidate_id`
    (=== `sleeve_id`), then calls
    `build_sleeve_from_candidate(candidate)` and runs the
    sleeve's signal path on the bar window — the same code
    path the backtest uses, producing an apples-to-apples
    comparison against the backtest reference series. This
    works whether the sleeve is the currently-active strategy
    or not.

    If a sleeve_id is not present in the mandatory registry or
    its candidate has `sleeve_class_path=None`, the reader
    raises `LookupError` and the gateway records a pending
    verdict for that sleeve's KS monitor per §P3.

    Pure function over bars + sleeve logic.
    """

    def live_samples(
        self, sleeve_id: str, *, window_days: int
    ) -> pd.Series: ...


class DriftAlarmGateway:
    """Concrete DriftAlarmGatewayProtocol implementation.

    On construction, loads the reference-distribution snapshot.
    On each has_alarm call, runs all four monitors against
    the most recent live data and aggregates.

    Per §P5: `has_alarm(sleeve_id)` is the ONLY consumer-facing
    aggregation. The individual monitor verdicts are exposed
    via `latest_verdicts()` for the operator dashboard.
    """

    def __init__(
        self,
        *,
        blueprint: DriftMonitorBlueprint,
        reference_snapshot: ReferenceDistributionSnapshot,
        feature_sample_reader: FeatureSampleReaderProtocol,
        signal_sample_reader: SignalSampleReaderProtocol,
        replay_records_reader: "ReplayRecordsReaderProtocol",
        attribution_records_reader: "AttributionRecordsReaderProtocol",
        backtest_reference_returns_reader: BacktestReferenceReturnsReaderProtocol,
        risk_control_event_sink: "RiskControlEventSinkProtocol",
        alert_gateway: "OperatorAlertGatewayProtocol",
    ) -> None:
        ...

    def has_alarm(self, *, sleeve_id: str) -> bool:
        """Returns True if ANY monitor targeting the sleeve has
        severity 'critical'. Warning severity does NOT trigger
        has_alarm; it is surfaced via the dashboard and the
        RiskControlEvent log only.
        """

    def refresh(self) -> tuple[DriftMonitorVerdict, ...]:
        """Run all monitors, emit RiskControlEvents + (if
        warning/critical) OperatorAlerts, cache the verdicts.
        Called by the market-day automation at end of session.
        Returns the verdict tuple so callers can render dashboards.
        """

    def latest_verdicts(self) -> tuple[DriftMonitorVerdict, ...]:
        """Read cached verdicts from the last refresh()."""
```

**Event emission (per §P3):**

- Every verdict → one `RiskControlEvent` with
  `control_type="portfolio_drift_alarm"`, severity matching the
  verdict, `blocked=False`.
- `warning` or `critical` verdicts → additionally emit one
  `OperatorAlert` with `category="portfolio_drift_alarm"` and
  the same severity. `delivery_targets=("operator_dashboard",)`
  consistent with the hard-halt alert pattern.
- `pending` verdicts → `RiskControlEvent` with `severity="info"`
  (absence of evidence is observable) but NO `OperatorAlert`
  (pending is not an actionable state for the operator).
- `has_alarm(sleeve_id)` returns True only when a CRITICAL
  verdict targets the sleeve (by `sleeve_id` OR, for
  portfolio-level monitors like PSI, when the monitor is
  critical and the sleeve consumes that feature).

**Tests cover:**

- `has_alarm` False when all monitors are info or pending.
- `has_alarm` False when only warnings fire.
- `has_alarm` True when any critical monitor targets the sleeve.
- `refresh()` emits exactly one RiskControlEvent per verdict.
- `refresh()` emits OperatorAlerts only for warning + critical.
- Pending monitors emit info-severity RiskControlEvents only
  (no OperatorAlert).
- Portfolio-level PSI critical fires has_alarm for both shipped
  sleeves (they both consume the regime composite).
- Per-sleeve KS critical only fires has_alarm for that sleeve.
- Execution drift critical on a symbol the sleeve touches fires
  has_alarm; critical on a symbol the sleeve doesn't touch does
  NOT fire has_alarm for that sleeve.
- Cached verdicts accessible via `latest_verdicts()` after
  `refresh()`.

### W9 — `LIVE_DAILY_RETURNS` implementation

**Files:**
- Modify: `src/tradingx/portfolio/sleeve_runtime.py`
- Create: `src/tradingx/drift/live_returns_source.py`
- Modify: `tests/unit/test_sleeve_runtime_controller.py`
- Create: `tests/unit/test_drift_live_returns_source.py`

**`LIVE_DAILY_RETURNS` is now implementable because
`SleeveDailyAttributionRecord` exists (§W6).**

**Contract changes in `sleeve_runtime.py`:**

```python
class LiveDailyReturnsSourceProtocol(Protocol):
    def live_daily_returns(
        self, *, sleeve_id: str, window_days: int
    ) -> tuple[Decimal, ...]: ...


class SleeveRuntimeController:
    def __init__(
        self,
        *,
        wrapped_sleeve: SleeveProtocol,
        operator_halt_store: SleeveOperatorHaltStoreProtocol,
        drift_alarm_gateway: DriftAlarmGatewayProtocol | None,
        trials_ledger: TrialsLedgerReadProtocol | None,
        config: SleeveRuntimeConfig,
        live_daily_returns_source: LiveDailyReturnsSourceProtocol | None = None,
    ) -> None:
        ...

    def plan_for_bar(self, context: SleeveContext) -> tuple[SleeveTrade, ...]:
        # Behavior when config.rolling_window_source is:
        # - TRIAL_SUMMARY: existing path (1.4).
        # - LIVE_DAILY_RETURNS: query live_daily_returns_source
        #   for the series, compute rolling Sharpe, compare to
        #   floor. If source is None, raise ValueError (misconfiguration,
        #   not NotImplementedError — 1.5 implements it).
```

**`live_returns_source.py`:**

```python
class SleeveDailyReturnsReader:
    """Reads SleeveDailyAttributionRecord rows and produces
    tuple[Decimal, ...] series for the SleeveRuntimeController's
    LIVE_DAILY_RETURNS path.
    """

    def __init__(
        self,
        *,
        attribution_records_reader: "AttributionRecordsReaderProtocol",
    ) -> None:
        ...

    def live_daily_returns(
        self, *, sleeve_id: str, window_days: int
    ) -> tuple[Decimal, ...]:
        """Read the last `window_days` SleeveDailyAttributionRecord
        rows for sleeve_id, sort by trading_day ascending, return
        the daily_return tuple. If fewer than window_days records
        exist, returns the shorter tuple; the caller handles the
        insufficient-evidence case.
        """
```

**Default remains TRIAL_SUMMARY.** Operators opt into
`LIVE_DAILY_RETURNS` by setting it on the
`SleeveRuntimeConfig`. This preserves backwards compatibility
with existing tests and deployments. A future tranche-2 change
can flip the default after enough live evidence accumulates;
the switch is an ADR-level decision, not a 1.5 decision.

**Tests cover:**

- Existing TRIAL_SUMMARY tests continue to pass unchanged.
- LIVE_DAILY_RETURNS path reads from
  `SleeveDailyReturnsReader` and computes rolling Sharpe.
- LIVE_DAILY_RETURNS selected but source=None raises
  `ValueError` (misconfiguration).
- Fewer than lookback window_days records → gate skipped
  (pending), same semantics as TRIAL_SUMMARY with insufficient
  trials.

### W10 — Integration + operator surface + closing pass

**Files:**
- Modify: `src/tradingx/operator_control.py` (add
  `recalibrate_drift_reference` action).
- Modify: `src/tradingx/automation.py` (wire
  `DriftAlarmGateway.refresh()` into the end-of-session hook).
- Modify: `docs/INDEX.md` — register DESIGN-0016.
- Modify: `docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md`
  — mark 1.5 as NEXT → SHIPPED after merge; bump BRIEF-0002.
- Modify: `docs/validation/acceptance_gates.md` — note in Gate 3
  primary evidence that ExecutionQualityDriftMonitor feeds the
  slippage criterion; GATES-0001 patch bump (1.2.0 → 1.2.1),
  no criterion change.
- Create/modify: dashboard diagnostic row(s) — exact touchpoints
  depend on existing dashboard layout; the diagnostic is a
  single `PerformanceDiagnostic` with one row per drift
  monitor, severity mapped from the latest `DriftMonitorVerdict`.

Standard closing pass. `uv run pytest -q`, `uv run mypy src/tradingx`,
`uv run ruff check`, `python3 scripts/check_index.py`,
`./scripts/validate`.

## Testing approach

Standard TDD. Each work item produces unit tests before
implementation. Integration coverage:

- `tests/integration/test_drift_end_to_end.py` (new): a canned
  200-session sequence with known PSI / KS / execution-drift /
  P&L-divergence outcomes; verifies that:
  - `DriftAlarmGateway.refresh()` emits exactly
    `N_monitors` RiskControlEvents (one per monitor per call).
  - OperatorAlert count equals count(warning) + count(critical).
  - `has_alarm(sleeve_id)` agrees with the expected verdicts.
  - Regression: with `rolling_window_source=LIVE_DAILY_RETURNS`
    and attribution records preloaded, the Sharpe gate fires
    consistent with the Sharpe of the live series.

- Regression: existing `test_sleeve_runtime_controller.py` tests
  continue to pass (TRIAL_SUMMARY path unchanged).

## Acceptance criteria

Sub-tranche 1.5 is complete when:

1. `DriftMonitorBlueprint` + `DriftThresholds` ship with the
   default thresholds in §W1.
2. `ReferenceDistributionSnapshot` is build-and-load round-trip
   stable; replacement is gated behind
   `operator_control.recalibrate_drift_reference(...)`.
3. `compute_population_stability_index`,
   `compute_kolmogorov_smirnov`,
   `compute_execution_drift_ratio`, and
   `compute_live_vs_backtest_pnl_divergence` are pure functions
   with unit-test coverage of their boundary cases.
4. `SleeveDailyAttributionRecord` is persisted each session via
   the end-of-session automation hook **when the currently-
   active strategy is sleeve-backed** (`sleeve_class_path is
   not None`). Non-sleeve active strategies produce no
   record (§W6). Daily return is captured from portfolio-state
   equity snapshots, not reconstructed from a multi-sleeve
   decomposition.
5. `DriftAlarmGateway.has_alarm(sleeve_id)` returns True iff a
   CRITICAL-severity verdict targets the sleeve. Warning and
   info verdicts do NOT trigger has_alarm.
6. `refresh()` emits one `RiskControlEvent(control_type=
   "portfolio_drift_alarm")` per verdict and one
   `OperatorAlert(category="portfolio_drift_alarm")` per
   warning/critical verdict — per §P3.
7. `SleeveRuntimeController` accepts a
   `live_daily_returns_source` parameter and implements
   `RollingWindowSource.LIVE_DAILY_RETURNS` via the new reader;
   the `NotImplementedError` guardrail is gone.
8. Existing tranche-1.1 through tranche-1.4 tests remain green
   (no regression).
9. `uv run pytest -q`, `uv run mypy src/tradingx`,
   `uv run ruff check`, `python3 scripts/check_index.py`, and
   `./scripts/validate` all pass.
10. BRIEF-0002 sub-tranche table updated (1.4 shipped; 1.5 next
    at merge time, flipped to shipped in-cycle or by the
    implementation-plan housekeeping commit); INDEX bumped;
    GATES-0001 patch-bumped with the Gate 3 evidence note.

## Tranche-1 completion

With 1.5 merged and [BRIEF-0002 v1.2.0](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)'s
narrowing of criterion 5 to "P&L divergence for the currently-
active sleeve-backed strategy," all six tranche-1 completion
criteria are satisfied at the scope BRIEF-0002 now defines:

1. Trend sleeve and vol-managed beta sleeve running in paper
   against the three-tier benchmark stack. ✅ (1.3 + 1.4)
2. Portfolio risk budgets and drawdown throttles enforced at
   runtime, including the 25% MDD hard halt. ✅ (1.4)
3. Sleeve-level cost-aware evaluation. ✅ (1.1)
4. Validation stack with purged/embargoed k-fold CV + trials
   ledger; DSR wired into `evaluate_candidate`. ✅ (1.1)
5. Live drift diagnostics emit alarms across PSI, KS,
   execution-quality, and (active-sleeve) P&L divergence.
   ✅ (1.5 — this tranche, at the scope BRIEF-0002 v1.2.0
   narrows criterion 5 to).
6. Marginal-portfolio-contribution criterion wired into Gate 1.
   ✅ (1.4)

**What is NOT closed by 1.5.** Multi-sleeve P&L divergence
alarms require the live multi-sleeve runtime wiring deferred in
§Not in scope — sleeve-aware `RuntimePortfolioPlan`, per-sleeve
target-weight persistence during service cycles, and a multi-
strategy activation gateway. BRIEF-0002 v1.2.0 relocates that
expansion out of tranche-1's acceptance bar and into Gate-4-
enablement work. Tranche-1 closure in this spec reflects the
narrowed BRIEF-0002 scope, not the original 1.1.1 wording.

**Next**: the Gate 4 readiness discussion becomes a live option,
subject to the BRIEF-0002 v1.2.0 completion clause:

> "When all six are shipped and green in paper for at least
> one full session, tranche 1 closes and we can open the
> Gate 4 readiness discussion."

Tranche-1 closure is an operator decision, not a spec action.
1.5's scope ends at shipping the sixth criterion at the
narrowed scope BRIEF-0002 v1.2.0 defines.

## Decisions resolved (no open items)

All D1–D5 resolutions from BRIEF-0002 remain load-bearing. 1.5
introduces no new D-level decisions.

Implementation-level judgment calls for Codex review:

1. **Feature-monitor name list.** W1 defaults to five feature
   names (`spy_close_over_sma_200`, `vix_level`,
   `yield_curve_spread_bps`, `trend_signal_strength`,
   `vol_forecast_ewma`). If Codex sees a cleaner mapping against
   the regime composite and sleeve signal extraction code
   already in `src/tradingx/features/`, a rename is low-risk;
   flag in review.
2. **Active-sleeve attribution (resolved in round-1
   amendment).** §W6's original proposal was multi-sleeve
   proportional attribution, but Codex's round-1 review
   correctly flagged that the runtime is single-active-strategy
   and no per-sleeve target-weight history is persisted. §W6
   now scopes attribution to the currently-active sleeve only;
   multi-sleeve attribution is a future expansion tied to live
   multi-sleeve wiring (§Not in scope). The function signature
   preserves `sleeve_id` so the record type does not change
   when the expansion lands.
3. **Backtest-reference returns artifact path (resolved in
   round-1 amendment).** §W7 places the artifact under
   `{config.runtime.artifact_root}/drift/backtest_reference_returns/<sleeve_id>.json`
   — the runtime tree, not `config/strategy/*`. Runtime-
   generated evidence belongs under the runtime artifact tree
   alongside the journal, operator store, and drill records;
   `config/strategy/*` is operator-reviewed offline config
   (ApprovedWeightSnapshot et al.) and runtime regeneration
   there would violate that boundary.
4. **Default `rolling_window_source` toggle.** 1.5 keeps
   TRIAL_SUMMARY as the default to preserve backwards
   compatibility. Flipping the default is deferred to a
   tranche-2 ADR once live evidence is available. If Codex
   thinks the flip should happen in 1.5 (i.e., every sleeve
   runtime gets LIVE_DAILY_RETURNS by default), flag it — the
   change would be one line of config plus test updates.

## Governance impact

- **Register DESIGN-0016 in INDEX.** Adds a row to INDEX-0001's
  Design documents table. Bumps INDEX-0001 patch.
- **BRIEF-0002 amended (housekeeping).** The sub-tranche-
  sequence table gets 1.4 flipped to SHIPPED and 1.5 marked as
  NEXT with a link to DESIGN-0016. Patch bump (1.1.1 → 1.1.2).
  No scope changes.
- **GATES-0001 amendment (Gate 3 evidence note).** A note is
  added in Gate 3's primary-evidence block that
  ExecutionQualityDriftMonitor feeds the slippage criterion.
  The criterion itself (`realized slippage ≤ 1.5x backtest
  assumption`) is unchanged. Patch bump (1.2.0 → 1.2.1).
- **ADR impact: none.** Drift monitoring is evidence-gathering
  infrastructure; no new architectural decision warrants an
  ADR. The downstream auto-halt decision (if any) is a tranche
  2+ ADR.
- **FFL-0001 impact: none.** No deferrals move into scope in
  1.5; no new deferrals added. FFL-0001-01's Kelly-switch gate
  lists live-drift-green as a precondition — 1.5 makes that
  precondition observable.
- **CONST-0001 impact: none.** Gate 4 discipline unchanged.

## References

### Repo documents

- [BRIEF-0002 Tranche 1 planning brief](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
- [FFL-0001 Future features ledger](/docs/roadmap/future-features-ledger.md)
- [SPEC-0013 Capital growth landscape](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [ADR-0021 Benchmark stack](/docs/adrs/ADR-0021-benchmark-stack.md)
- [ADR-0022 Gate 1 reframe](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
- [GATES-0001 Acceptance gates v1.2.0](/docs/validation/acceptance_gates.md)
- [DESIGN-0011 Tranche 1.1 validation infrastructure](/docs/superpowers/specs/2026-04-21-tranche-1-1-validation-infrastructure-design.md)
- [DESIGN-0013 Tranche 1.2 market-state features](/docs/superpowers/specs/2026-04-21-tranche-1-2-market-state-features-design.md)
- [DESIGN-0014 Tranche 1.3 sleeves](/docs/superpowers/specs/2026-04-21-tranche-1-3-sleeves-design.md)
- [DESIGN-0015 Tranche 1.4 portfolio construction and drawdown defense](/docs/superpowers/specs/2026-04-21-tranche-1-4-portfolio-construction-and-drawdown-defense-design.md)

### Existing source files

- [src/tradingx/portfolio/sleeve_runtime.py](/src/tradingx/portfolio/sleeve_runtime.py)
  — `DriftAlarmGatewayProtocol` stub; `RollingWindowSource`.
- [src/tradingx/replay_slippage.py](/src/tradingx/replay_slippage.py)
  — per-execution slippage comparison.
- [src/tradingx/types.py](/src/tradingx/types.py) —
  `ReplaySlippageRecord`, `ReplaySlippageSummary`,
  `RiskControlEvent`, `OperatorAlert`, `RegimeSnapshot`.
- [src/tradingx/validation.py](/src/tradingx/validation.py) —
  `_candidate_returns` for backtest-reference-returns
  regeneration.
- [src/tradingx/portfolio/construction.py](/src/tradingx/portfolio/construction.py)
  — `PortfolioSimulationResult.combined_target_weights` carries
  the portfolio target-weight history needed for attribution.
- [src/tradingx/automation.py](/src/tradingx/automation.py) —
  market-day automation loop; end-of-session hook for
  `DriftAlarmGateway.refresh()`.
- [src/tradingx/operator_control.py](/src/tradingx/operator_control.py)
  — operator action surface; `recalibrate_drift_reference`
  lands here.

### External references

- Siddiqi, N. (2006). *Credit Risk Scorecards: Developing and
  Implementing Intelligent Credit Scoring.* Wiley. — PSI
  interpretation bands.
- Smirnov, N. V. (1948). "Table for Estimating the Goodness of
  Fit of Empirical Distributions." *Annals of Mathematical
  Statistics.*
- Grinold, R. C. & Kahn, R. N. (1999). *Active Portfolio
  Management.* McGraw-Hill — per-strategy attribution
  principles; 1.5 uses the single-strategy case only (§W6)
  and reserves the multi-strategy decomposition for the
  tranche that adds live multi-sleeve wiring.
