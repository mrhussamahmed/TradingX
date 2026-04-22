---
id: DESIGN-0017
title: Tranche 2.1 multi-sleeve live runtime wiring
version: 0.1.0
status: draft
created: 2026-04-22
last_amended: 2026-04-22
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-22
---

# DESIGN-0017: Tranche 2.1 multi-sleeve live runtime wiring

## Status

Draft on 2026-04-22. First sub-tranche under
[BRIEF-0003](/docs/superpowers/specs/2026-04-22-tranche-2-planning-brief.md).
Pending Hussam approval and Codex peer review.

## Purpose

Close the live-runtime gap that
[BRIEF-0002 v1.2.0](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
relocated out of tranche 1. The current runtime activates one
`strategy_id` at a time via
[runtime_strategy_registry.py:54](/src/tradingx/runtime_strategy_registry.py:54),
builds a single aggregate
[`RuntimePortfolioPlan`](/src/tradingx/runtime_portfolio.py:65),
and persists only that aggregate at
[service.py:206](/src/tradingx/service.py:206). Tranche 1.4's
portfolio-construction machinery (`PortfolioBlueprint`,
per-sleeve risk budgets, correlation caps, gross/net caps, MDD
throttles, hard halt) was built in backtest-space only — it
has never run live. Tranche 1.5's drift monitors are narrowed
to the currently-active single sleeve for the same reason.

2.1 wires the blueprint into live execution so both shipped
sleeves (`trend-following-v1`, `vol-target-v1`) run
concurrently in paper under a single blueprint, with operator
sign-off at the blueprint level, per-sleeve target-weight
persistence, `sleeve_id`-tagged executions, artifact
regeneration on activation change, single-sleeve
fallback/rollback, and a two-sleeve operator dashboard.

Scope:

1. **Sleeve-aware `RuntimePortfolioPlan`.** The aggregate plan
   gains a `per_sleeve_target_weights: tuple[SleeveTargetWeights, ...]`
   decomposition recording which sleeve contributed what at
   each cycle. The aggregate remains the authoritative execution
   input; the decomposition is persistable evidence that enables
   per-sleeve attribution and drift monitoring.
2. **`BlueprintActivationRecord` artifact.** Per BRIEF-0003 D1:
   blueprint-as-a-unit activation. This record is the single
   source of truth for "which blueprint is live right now":
   blueprint_id, constituent sleeve_ids, referenced
   `ApprovedWeightSnapshot` IDs, activation status,
   operator-approval timestamp, source blueprint file.
3. **Multi-strategy activation gateway.** `LocalActivationGateway`
   gains a `load_or_activate_blueprint(...)` path that replaces
   (for blueprint-based activations) the existing per-strategy
   `load_or_create_active_records(...)`. The per-strategy path
   remains for the legacy baseline and mean-reversion candidates.
4. **Live portfolio construction per-cycle.** 1.4's
   `build_portfolio_target_weight_history` (batch, backtest-shaped)
   gets a per-cycle counterpart `build_portfolio_cycle_target_weights`
   that the service loop invokes each tick to produce the
   combined target-weight vector. Both call into the same
   composition primitive (per-sleeve budget scaling +
   correlation cap + gross/net cap) so backtest and live see
   identical math.
5. **Per-sleeve target-weight persistence.** The service loop's
   existing aggregate plan write at
   [service.py:206](/src/tradingx/service.py:206) is extended
   with a sidecar write of the sleeve decomposition artifact.
   1.5's `SleeveDailyAttributionRecord` writer is updated to
   read from the decomposition artifact when both sleeves are
   live (supplements, does not replace, the portfolio-state
   equity delta attribution).
6. **`sleeve_id` threading through intents + executions.** Per
   BRIEF-0003 D4: `TradeIntent`, `ExecutionLifecycleRecord`,
   and `ClosedTradeRecord` each gain `sleeve_id: str | None`.
   Default `None` preserves deserialization of existing
   persisted payloads. Blueprint-based execution paths populate
   the field; the legacy baseline path leaves it `None`.
7. **Artifact regeneration on activation change.** When a new
   blueprint activates, the 1.5 drift-reference snapshot and
   backtest-reference returns artifacts are rebuilt. Also
   triggers on operator command via the already-shipped
   `OperatorControlStore.recalibrate_drift_reference`.
   Closes the P3 nit from the 1.5 code review.
8. **Single-sleeve fallback / rollback path.** If one sleeve
   fails (operator halt, critical drift alarm, regime-stressed
   liquidation that persists), the other sleeve continues
   running under a **narrowed blueprint**. The narrowed
   blueprint is a new `BlueprintActivationRecord` with one
   sleeve; the original blueprint's activation record is
   updated with `status="superseded"`. Explicit operator drill
   documented as an operational requirement.
9. **Operator dashboard two-sleeve view.** Both sleeves shown
   side-by-side: per-sleeve exposure, daily return, drift
   verdicts (from `DriftAlarmGateway.latest_verdicts`),
   activation state, halt state.
10. **Stage 2 — drift P&L-divergence activation.** A follow-up
    commit (not part of Stage 1 implementation) flips 1.5's
    `pnl::<sleeve_id>` monitor from `pending` semantics (for
    non-active sleeves) to real verdicts now that both sleeves
    have live attribution records. Two-stage rollout per
    BRIEF-0003 D5.

**Not in scope** (deferred explicitly):

- CPCV + PBO Gate 1 hard-gate activation — BRIEF-0003 2.2
  research + spec lane only. Implementation + activation
  remains deferred per
  [FFL-0001-06](/docs/roadmap/future-features-ledger.md) Stage 2.
- Gate 2 robustness evidence runs — BRIEF-0003 2.3 parallel
  evidence lane; uses existing adversarial harness.
- Fractional Kelly sizing — FFL-0001-01 remains load-bearing
  (tranche-2.1 does not change the sizing regime).
- Options scope (FFL-0001-02), mean-reversion sleeve
  (FFL-0001-03), meta-labeling (FFL-0001-04), structural alpha
  sources (FFL-0001-05), HMM regime (FFL-0001-07), IV overlay
  (FFL-0001-08), multi-account (FFL-0001-09), Almgren-Chriss
  (FFL-0001-10) — all stay deferred.
- Per-sleeve auto-halt MDD thresholds — BRIEF-0003 D2 rejected
  this; portfolio-aggregate halt stays the sole auto-trigger.
- New gate criteria — GATES-0001 v1.2.1 unchanged. Drift
  alarms remain paper-evidence, not gate pass/fail.
- Multi-account or concurrent multi-blueprint execution —
  operator activates one blueprint at a time; switching is
  the rollback-then-activate flow.

## Prerequisites

- `main` at or beyond tranche-1.5 merge (`075ca73`). Brings the
  drift package, `SleeveDailyAttributionRecord`,
  `DriftAlarmGateway`, `LIVE_DAILY_RETURNS` live-Sharpe gate,
  `recalibrate_drift_reference`, automation-hook integration.
- `main` at or beyond tranche-1.4 merge. Brings
  `PortfolioBlueprint`, `SleeveRiskBudget`,
  `build_portfolio_target_weight_history`,
  `simulate_portfolio_returns`, drawdown throttle helpers,
  `PortfolioHardHaltController`, `SleeveRuntimeController`.
- **All BRIEF-0003 D1–D5 + D8 resolutions locked.** 2.1
  implements them; it does not re-open them.

## Design principles (pre-empt Codex P1 patterns)

Carried forward from DESIGN-0015 / DESIGN-0016. Each still
applies; this section narrows each to 2.1's shape.

### P1 — Single composition engine; live uses the same primitive as backtest

Live portfolio construction MUST call the same composition
primitive 1.4's backtest path uses. Concretely:
`build_portfolio_target_weight_history` (batch) and the new
`build_portfolio_cycle_target_weights` (streaming) both delegate
to a shared `_combine_sleeve_weights` helper that handles
budget scaling, correlation caps, and gross/net caps. Live
cannot diverge from backtest; 1.4's test that asserts
element-wise equality between `simulate_portfolio_returns` and
a direct `run_daily_bar_backtest` call MUST continue to pass
unchanged.

### P2 — Field propagation on both ends of the thread

`sleeve_id` threading is not a one-site change. `TradeIntent`
gets the field AND `ExecutionLifecycleRecord` gets it AND
`ClosedTradeRecord` gets it. Persistence writers +
deserializers + operator-dashboard consumers MUST all be
updated. Field defaults to `None` so existing persisted
payloads deserialize without migration.

### P3 — No silent skips; single-sleeve fallback is an observable event

When the blueprint narrows from two-sleeve to single-sleeve
(fallback), the transition MUST emit:

- A `RiskControlEvent(control_type="blueprint_narrowed", severity="warning", blocked=False)`
  with `operator_visible=True`.
- An `OperatorAlert(category="blueprint_narrowed", severity="warning")`
  whose summary names the removed sleeve and the trigger
  (operator halt / drift critical / regime stressed).
- A new `BlueprintActivationRecord` with the narrowed
  blueprint; the prior record transitions to `status="superseded"`.

Silent narrowing (just dropping a sleeve's contributions
without emitting events) is forbidden by this principle.

### P4 — Dimensional correctness across the blueprint seam

Three weight spaces coexist and must stay distinct:

- **Sleeve target weights** in `[0, 1]` of each sleeve's
  budget (same as 1.3/1.4).
- **Portfolio target weights** in `[0, 1]` of portfolio equity
  (produced by the composition primitive).
- **Runtime execution weights** — what
  `RuntimePortfolioPlan.trades` quantities resolve to — are
  portfolio-equity weights filtered through broker quantization.

The per-sleeve decomposition on the new `RuntimePortfolioPlan`
records portfolio-equity-space contributions (not budget-space
intents), because downstream attribution reads them as "what
this sleeve contributed to the actual portfolio." Contributions
from each sleeve for each symbol sum (within rounding) to the
aggregate target weight for that symbol on that cycle.

### P5 — Single source of truth for blueprint activation state

`BlueprintActivationRecord` is the ONLY artifact that
authoritatively says "this blueprint is live right now."
`ApprovedWeightSnapshot`s stay per-strategy (D3); the
blueprint record composes them by ID. Any consumer that needs
to know the current active blueprint reads the latest
non-superseded `BlueprintActivationRecord` via
`LocalActivationGateway.get_active_blueprint_activation()`.

Legacy per-strategy `StrategyActivationRecord` writers remain
for non-blueprint paths (baseline, mean-reversion). When a
blueprint is active, the gateway exposes both surfaces; when
a legacy single-strategy activation is active, the blueprint
surface returns `None`.

## Architecture overview

### New modules

1. **`src/tradingx/portfolio/live_construction.py`** —
   `build_portfolio_cycle_target_weights` + the shared
   `_combine_sleeve_weights` helper (extracted from 1.4's
   `build_portfolio_target_weight_history` so batch + live
   share one implementation).
2. **`src/tradingx/portfolio/blueprint_activation.py`** —
   `BlueprintActivationRecord` dataclass (on `types.py`;
   this module holds the reader/writer helpers).
3. **`src/tradingx/portfolio/fallback.py`** —
   `narrow_blueprint_on_sleeve_failure(...)`, the
   single-sleeve fallback primitive invoked by the service
   loop when a sleeve transitions into a terminal failure.

### New dataclasses (on `types.py`)

- `SleeveTargetWeights` — per-sleeve contribution at a given
  cycle; `(sleeve_id, target_weights_by_symbol)`.
- `BlueprintActivationRecord` — the activation artifact.
- `SleeveDecompositionRecord` — the persistence sidecar for
  the per-cycle sleeve decomposition, written alongside the
  aggregate `RuntimePortfolioPlan`.

### New fields on existing dataclasses

- `TradeIntent.sleeve_id: str | None = None`
- `ExecutionLifecycleRecord.sleeve_id: str | None = None`
- `ClosedTradeRecord.sleeve_id: str | None = None`
- `RuntimePortfolioPlan.per_sleeve_target_weights: tuple[SleeveTargetWeights, ...] = ()`

Default values preserve backwards compatibility for
persisted payloads predating 2.1.

### Modified files

- `src/tradingx/types.py` — three new dataclasses; four
  fields on existing records (defaults preserve compat).
- `src/tradingx/runtime_portfolio.py` — `RuntimePortfolioPlanner`
  emits sleeve decomposition when given a blueprint; the
  legacy single-strategy path still emits the aggregate only.
- `src/tradingx/portfolio/construction.py` — extract
  `_combine_sleeve_weights` so the new per-cycle builder can
  share it.
- `src/tradingx/activation.py` — add
  `load_or_activate_blueprint(...)` +
  `get_active_blueprint_activation()`; preserve existing
  per-strategy API for legacy paths.
- `src/tradingx/service.py` — per-cycle call to the new
  `build_portfolio_cycle_target_weights` when a blueprint is
  active; persist the decomposition sidecar; tag intents with
  `sleeve_id` from the decomposition.
- `src/tradingx/persistence.py` — writers + readers for
  `BlueprintActivationRecord` and `SleeveDecompositionRecord`;
  update intent + execution + closed-trade writers to accept
  the new `sleeve_id` field.
- `src/tradingx/drift/attribution.py` — when a
  `SleeveDecompositionRecord` exists for the session's
  trading day, prefer decomposition-based attribution over
  portfolio-state equity-delta attribution (decomposition
  gives per-sleeve P&L directly instead of inferring it).
- `src/tradingx/drift/gateway.py` — Stage 2 only: flip
  `pnl::<sleeve_id>` monitor from `pending` to active for
  both sleeves. No code change in Stage 1.
- `src/tradingx/automation.py` — extend
  `build_default_market_day_automation_runner` to pick up
  blueprint activation when present; recalibrate drift
  reference + backtest-reference artifacts on activation
  change (currently only on first boot).
- `src/tradingx/operator_control.py` — no change to the
  `halt_sleeve` / `recalibrate_drift_reference` API; add a
  read-only `get_active_blueprint_record()` accessor for the
  dashboard.
- Operator dashboard modules (`portfolio.py`,
  `performance.py`, or the relevant operator-platform surface
  — exact files depend on the existing layout) — add
  per-sleeve rows / cards.
- Tests covering every surface change + integration tests
  for blueprint activation, fallback drill, two-sleeve paper
  cycle, artifact regeneration.

### Untouched (intentional)

- `src/tradingx/portfolio/hard_halt.py` — the 25% MDD hard
  halt is portfolio-aggregate (D2); no change.
- `src/tradingx/portfolio/sleeve_runtime.py` — the
  `SleeveRuntimeController` continues to wrap each sleeve
  with operator halt + drift alarm + Sharpe gate semantics
  unchanged; when blueprint-activated, one controller per
  sleeve co-exists.
- `src/tradingx/portfolio/throttle.py` — MDD + CDaR throttle
  helpers are per-portfolio; no change.
- `src/tradingx/validation.py` — Gate 1 logic unchanged.
- `src/tradingx/backtest.py`, `src/tradingx/costs.py`,
  `src/tradingx/sleeves/*` — engine + cost primitives +
  sleeve definitions all unchanged.
- `config/strategy/weights/<strategy_id>/` — per-strategy
  snapshots (D3) untouched; operator review flow unchanged.

## Work items

### W1 — `RuntimePortfolioPlan` sleeve decomposition

**Files:**
- Modify: `src/tradingx/types.py` (add `SleeveTargetWeights` +
  `per_sleeve_target_weights` field on
  `RuntimePortfolioPlan`).
- Modify: `src/tradingx/runtime_portfolio.py`
  (`RuntimePortfolioPlanner.plan` emits the decomposition
  when blueprint-driven).
- Modify: `tests/unit/test_runtime_portfolio.py` (regression).
- Create: `tests/unit/test_sleeve_decomposition.py`.

**Contract:**

```python
# src/tradingx/types.py (addition)

@dataclass(frozen=True)
class SleeveTargetWeights:
    sleeve_id: str
    # Portfolio-equity-space weights per symbol this sleeve
    # contributed at the cycle (post-budget-scaling,
    # post-throttle).
    target_weights_by_symbol: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True)
class RuntimePortfolioPlan:
    # ...existing fields unchanged...
    per_sleeve_target_weights: tuple[SleeveTargetWeights, ...] = ()
```

**Aggregate invariant (regression test):**

For each symbol s in the plan:
    aggregate_weight[s] ≈ sum over sleeves of sleeve_weight[s]

Tolerance: `Decimal("1e-9")` (rounding from float operations
during composition). The regression test exercises this with
both sleeves live and with the single-sleeve fallback path
(where only one sleeve contributes).

**Why portfolio-equity-space on the decomposition.** Per §P4,
downstream attribution reads these weights as "what this
sleeve contributed to the actual portfolio." Recording them
in sleeve-budget-space would require downstream consumers to
reapply budget scaling on every read — error-prone and easy
to drift out of sync.

**Tests cover:**

- Two sleeves live → decomposition has two entries; each
  entry's weights-by-symbol subset of the aggregate.
- Aggregate invariant holds within tolerance.
- Single-sleeve plan → decomposition has one entry.
- Legacy single-strategy plan (no blueprint) →
  decomposition is an empty tuple; aggregate unchanged.
- Round-trip serialization preserves decomposition ordering
  (sorted by sleeve_id for determinism).

### W2 — `BlueprintActivationRecord` + activation gateway

**Files:**
- Modify: `src/tradingx/types.py` (add
  `BlueprintActivationRecord`).
- Create: `src/tradingx/portfolio/blueprint_activation.py`
  (reader/writer helpers + the blueprint-activation path on
  `LocalActivationGateway` — implementation lives here,
  `activation.py` just re-exports).
- Modify: `src/tradingx/activation.py` (re-export +
  delegation).
- Modify: `src/tradingx/persistence.py` (writer + reader).
- Create: `tests/unit/test_blueprint_activation.py`.

**Contract:**

```python
# src/tradingx/types.py (addition)

@dataclass(frozen=True)
class BlueprintActivationRecord:
    activation_id: str
    blueprint_id: str
    # Constituent sleeves + the snapshot each should use.
    # Preserves D3: the blueprint references N snapshots by ID;
    # no bundled snapshot type.
    sleeve_activation_bindings: tuple[
        tuple[str, str],  # (sleeve_id, snapshot_id)
        ...,
    ]
    status: str  # "active" | "superseded" | "halted"
    approved_at_utc: datetime
    approved_by: str  # operator identifier / audit tag
    source_blueprint_path: Path
    # Populated when status transitions to "superseded"
    # (W7 fallback path).
    superseded_at_utc: datetime | None = None
    supersedes_activation_id: str | None = None
```

**`LocalActivationGateway` additions:**

```python
class LocalActivationGateway:
    # ...existing methods unchanged...

    def load_or_activate_blueprint(
        self,
        *,
        blueprint: PortfolioBlueprint,
        operator_identifier: str,
        source_blueprint_path: Path,
    ) -> BlueprintActivationRecord:
        """Load the latest non-superseded blueprint record if
        present; otherwise create one by validating that each
        sleeve's ApprovedWeightSnapshot exists for the bound
        snapshot_id, then persisting.
        """

    def get_active_blueprint_activation(
        self,
    ) -> BlueprintActivationRecord | None:
        """Return the latest BlueprintActivationRecord whose
        status == 'active'. None if no blueprint is active
        (legacy single-strategy mode).
        """

    def supersede_active_blueprint(
        self,
        *,
        new_activation: BlueprintActivationRecord,
        now: datetime,
    ) -> BlueprintActivationRecord:
        """Atomically transition the current active blueprint
        to 'superseded' and record the new activation.
        Returns the updated predecessor record.
        """
```

**Validation on load_or_activate_blueprint:** each sleeve in
`blueprint.sleeve_budgets` must have a matching binding in
`sleeve_activation_bindings`, and each referenced snapshot_id
must resolve via `ApprovedWeightSnapshotStore` before
persistence commits. Validation failure raises
`BlueprintActivationValidationError`.

**Tests cover:**

- Activating a fresh blueprint from `PortfolioBlueprint` +
  two snapshot IDs → record persisted with status="active".
- Activating when already active (same blueprint_id + same
  sleeve_activation_bindings) → returns the existing record
  unchanged (idempotent).
- Activating a blueprint whose referenced snapshot_id doesn't
  exist → raises `BlueprintActivationValidationError` and no
  record persisted.
- `get_active_blueprint_activation` returns the latest active
  record; returns None after supersession with no replacement.
- `supersede_active_blueprint` atomically writes the new
  record + updates the predecessor (same-session rollback test).

### W3 — Live portfolio construction per-cycle

**Files:**
- Create: `src/tradingx/portfolio/live_construction.py`
- Modify: `src/tradingx/portfolio/construction.py` (extract
  shared `_combine_sleeve_weights` helper).
- Create: `tests/unit/test_portfolio_live_construction.py`.

**Contract:**

```python
# src/tradingx/portfolio/construction.py (extraction)

def _combine_sleeve_weights(
    sleeve_contributions: dict[str, dict[str, Decimal]],
    *,
    blueprint: PortfolioBlueprint,
) -> dict[str, Decimal]:
    """Apply budget scaling + correlation cap + gross/net cap
    to per-sleeve contributions and return aggregate
    portfolio-equity-space weights by symbol.

    Extracted from build_portfolio_target_weight_history so
    batch and streaming call sites share one implementation.
    """


# src/tradingx/portfolio/live_construction.py (new)

def build_portfolio_cycle_target_weights(
    *,
    blueprint: PortfolioBlueprint,
    sleeves_by_id: dict[str, SleeveProtocol],
    context_by_sleeve_id: dict[str, SleeveContext],
) -> tuple[dict[str, Decimal], tuple[SleeveTargetWeights, ...]]:
    """For a single cycle, invoke each sleeve's plan_for_bar
    to get target weights, then combine via
    _combine_sleeve_weights.

    Returns (aggregate_weights, per_sleeve_decomposition).
    The aggregate is what the service loop executes; the
    decomposition is persisted as a SleeveDecompositionRecord
    sidecar (W4).
    """
```

**Live-vs-batch parity.** A regression test calls both the
new `build_portfolio_cycle_target_weights` per-bar across a
canned window AND 1.4's `build_portfolio_target_weight_history`
over the same window; the resulting DataFrames MUST match
element-wise (modulo numerical tolerance). This pins §P1 —
live and backtest see identical composition math.

**Tests cover:**

- Two-sleeve cycle with both sleeves contributing → aggregate
  matches sum of (sleeve_contribution × budget_fraction)
  within correlation + gross caps.
- Single-sleeve cycle → aggregate = (sleeve_contribution ×
  budget_fraction) capped.
- `_combine_sleeve_weights` produces identical output when
  called in batch form (across N bars) or streaming form
  (one bar at a time): element-wise equality regression.
- Empty contributions → aggregate is `{}` (no positions).
- Regime-stressed sleeve returns all-zero weights →
  decomposition records a zero entry (not a missing entry);
  aggregate drops to the other sleeve only.

### W4 — Per-sleeve target-weight persistence in the service loop

**Files:**
- Modify: `src/tradingx/service.py` (per-cycle
  decomposition write + aggregate unchanged).
- Modify: `src/tradingx/persistence.py` (writer + reader
  for `SleeveDecompositionRecord`).
- Modify: `src/tradingx/types.py` (add
  `SleeveDecompositionRecord`).
- Modify: `tests/unit/test_service.py`.

**Contract:**

```python
# src/tradingx/types.py (addition)

@dataclass(frozen=True)
class SleeveDecompositionRecord:
    decomposition_id: str
    cycle_id: str  # matches the RuntimePortfolioPlan for this cycle
    trading_day: str
    recorded_at_utc: datetime
    blueprint_activation_id: str  # links to BlueprintActivationRecord
    per_sleeve_target_weights: tuple[SleeveTargetWeights, ...]
```

**Service loop addition.** When a blueprint is active (per
`LocalActivationGateway.get_active_blueprint_activation()`),
the service loop's existing per-cycle pattern — call
`RuntimePortfolioPlanner.plan(...)`, write the aggregate plan —
is extended: the planner's response now includes the
`per_sleeve_target_weights` decomposition (W1), and the
service loop writes a `SleeveDecompositionRecord` sidecar
with the same `cycle_id` that the aggregate plan uses.

When no blueprint is active (legacy single-strategy mode),
the decomposition is empty and no sidecar is written.

**Tests cover:**

- Blueprint active, two-sleeve cycle → one
  `SleeveDecompositionRecord` per cycle with both sleeves'
  entries.
- Blueprint active, single-sleeve (post-fallback) cycle →
  decomposition has one entry.
- No blueprint (legacy) → no decomposition artifact written.
- Record's `cycle_id` matches the sibling
  `RuntimePortfolioPlan.cycle_id`.
- Writer + reader round-trip preserves every field.

### W5 — `sleeve_id` threading through intents + executions

**Files:**
- Modify: `src/tradingx/types.py` (add `sleeve_id` to
  `TradeIntent`, `ExecutionLifecycleRecord`,
  `ClosedTradeRecord`).
- Modify: `src/tradingx/persistence.py` (writers +
  deserializers handle the new field; default `None`).
- Modify: `src/tradingx/runtime_portfolio.py`
  (`_trade_intent_for_plan_item` populates `sleeve_id` from
  the decomposition).
- Modify: `src/tradingx/execution.py` (execution path
  propagates `sleeve_id` from intent → lifecycle record).
- Modify: `src/tradingx/lifecycle.py` or equivalent —
  closed-trade aggregation path propagates `sleeve_id` from
  the matching entry/exit intents.
- Update: all call sites + tests.

**Contract:**

```python
@dataclass(frozen=True)
class TradeIntent:
    # ...existing fields unchanged...
    sleeve_id: str | None = None


@dataclass(frozen=True)
class ExecutionLifecycleRecord:
    # ...existing fields unchanged...
    sleeve_id: str | None = None


@dataclass(frozen=True)
class ClosedTradeRecord:
    # ...existing fields unchanged...
    sleeve_id: str | None = None
```

**Population rules:**

- Blueprint-based plan items → `sleeve_id` populated from the
  `SleeveTargetWeights` entry that contributed the majority of
  the intent's symbol weight. For a symbol that two sleeves
  both contribute to (SPY, for both shipped sleeves), majority
  wins; ties break by registry order (`trend-following-v1`
  first). Rationale: one intent, one primary attribution;
  minority attribution is preserved on `SleeveDecompositionRecord`
  for secondary analysis.
- Legacy single-strategy plans → `sleeve_id = None`.
- Baseline candidate intents → `sleeve_id = None`.

**Tests cover:**

- Blueprint-based intent for a symbol held only by
  `trend-following-v1` → `sleeve_id = "trend-following-v1"`.
- Blueprint-based intent for SPY held by both sleeves,
  60% trend + 40% vol-target budget contribution → primary
  attribution "trend-following-v1".
- Tie-breaking: 50/50 → "trend-following-v1" (registry order).
- Legacy single-strategy → `sleeve_id = None`.
- Deserializing a pre-2.1 `ClosedTradeRecord` payload (no
  `sleeve_id` field on disk) → `sleeve_id = None`.
- `sleeve_id` propagates through the
  `TradeIntent → ExecutionLifecycleRecord → ClosedTradeRecord`
  chain; the downstream records preserve the intent's value.

### W6 — Artifact regeneration on activation change / recalibration

**Files:**
- Modify: `src/tradingx/automation.py` (activation-change
  detection; regeneration trigger).
- Modify: `src/tradingx/operator_control.py`
  (`recalibrate_drift_reference` trigger integrates with the
  regeneration path).
- Modify: `src/tradingx/drift/reference.py` (add a
  `force_rebuild` path for existing snapshots).
- Modify: `src/tradingx/drift/backtest_reference.py` (add a
  `force_rebuild` parameter to the writer helpers).
- Create: `tests/unit/test_drift_artifact_regeneration.py`.

**Activation-change detection.** The automation runner at
`build_default_market_day_automation_runner` gains a small
"last seen blueprint_id" state. On each runner build, compare
the current `BlueprintActivationRecord.blueprint_id` to the
recorded previous value (persisted at
`{artifact_root}/drift/last_activation_blueprint.json`). If
different, invoke:

- `_load_or_build_reference_snapshot(..., force_rebuild=True)`
  — rebuild the drift reference distribution against the
  new blueprint's sleeve set.
- `_ensure_backtest_reference_returns(..., force_rebuild=True)`
  — regenerate per-sleeve backtest reference returns.

**Recalibration-trigger integration.** When
`OperatorControlStore.recalibrate_drift_reference(snapshot_id)`
writes the audit marker, a companion file
`{artifact_root}/drift/pending_recalibration.json` is written.
The next automation-runner build reads the pending file,
treats it as an activation-change signal (same regeneration
path), then deletes the pending file.

**Tests cover:**

- Build → blueprint_id==A → build-time generates reference
  + backtest artifacts + writes last_activation.
- Subsequent build → blueprint_id==A → no regeneration (idempotent).
- Subsequent build → blueprint_id==B → regeneration triggered;
  old artifacts overwritten; last_activation updated.
- `recalibrate_drift_reference` called → pending file written
  → next build regenerates → pending file deleted.

### W7 — Single-sleeve fallback / rollback path

**Files:**
- Create: `src/tradingx/portfolio/fallback.py`
  (`narrow_blueprint_on_sleeve_failure`).
- Modify: `src/tradingx/service.py` (invoke narrowing when a
  sleeve's runtime state transitions into a terminal failure).
- Modify: `src/tradingx/activation.py`
  (`supersede_active_blueprint` from W2 is the commit point).
- Create: `tests/unit/test_blueprint_fallback.py`.
- Create: `tests/integration/test_fallback_drill.py`.

**Contract:**

```python
# src/tradingx/portfolio/fallback.py

def narrow_blueprint_on_sleeve_failure(
    *,
    active_blueprint: PortfolioBlueprint,
    active_activation: BlueprintActivationRecord,
    failed_sleeve_id: str,
    failure_reason: str,  # from SleeveFailureReason
    operator_identifier: str,
    now: datetime,
    activation_gateway: ActivationGatewayProtocol,
    risk_control_event_sink: RiskControlEventSinkProtocol,
    alert_gateway: OperatorAlertGatewayProtocol,
) -> tuple[PortfolioBlueprint, BlueprintActivationRecord]:
    """Produce a narrowed blueprint with the failed sleeve
    removed, supersede the active activation record, emit the
    observable events required by §P3 (RiskControlEvent +
    OperatorAlert for 'blueprint_narrowed'), and return the
    new (blueprint, activation) pair for the service loop to
    use going forward.

    The narrowed blueprint preserves the surviving sleeve's
    budget allocation; the failed sleeve's budget becomes
    residual cash (per D4 "cash is a consequence, not a goal",
    inherited from BRIEF-0002). No budget redistribution —
    consistent with the 1.4 D4 ruling.

    If the narrowed blueprint would have zero sleeves, the
    function raises BlueprintExhaustionError and the caller
    (service loop) transitions to a full operator-clearance
    halt. Running with zero sleeves is not a fallback path;
    it is a halt.
    """
```

**Fallback triggers (service-loop side):**

The service loop's existing per-cycle sleeve-runtime evaluation
already produces a `SleeveFailureReason` when a sleeve
terminates (operator halt, drift-alarm critical, regime
stressed with persistent liquidation, trial-summary Sharpe
below floor). When a sleeve's termination persists across
`N` consecutive cycles (default: N=3), the service loop
invokes `narrow_blueprint_on_sleeve_failure`. Transient
single-cycle terminations (e.g., a single regime-stressed bar
that clears the next cycle) do NOT trigger narrowing —
narrowing is for sustained failure only.

**Rollback drill (integration test):**

- Start blueprint with both sleeves.
- Operator invokes `halt_sleeve(sleeve_id="vol-target-v1", ...)`
- Wait 3 cycles.
- Assert the narrowing fires: new `BlueprintActivationRecord`
  is active with only `trend-following-v1`; original record
  transitioned to `superseded`; `RiskControlEvent` +
  `OperatorAlert` both emitted with `category="blueprint_narrowed"`.
- Operator invokes `resume_sleeve(sleeve_id="vol-target-v1")`
  + reactivates the original blueprint.
- Assert: original blueprint re-activated; vol-target-v1
  resumes running on subsequent cycles.

**Tests cover:**

- Unit: `narrow_blueprint_on_sleeve_failure` produces the
  correctly narrowed blueprint + supersedes the record +
  emits both event types.
- Unit: `BlueprintExhaustionError` raised when narrowing
  would leave zero sleeves.
- Unit: budget of removed sleeve becomes residual cash
  (surviving sleeve keeps its original budget; no
  redistribution).
- Integration: the rollback drill described above.
- Regression: single-cycle terminations do NOT trigger
  narrowing (3-cycle persistence threshold).

### W8 — Operator dashboard two-sleeve view

**Files:**
- Modify: operator-platform dashboard modules (exact files
  depend on existing layout; likely
  `src/tradingx/portfolio.py` for the portfolio workspace
  surface + the performance analytics snapshot builder).
- Modify: relevant test files.

**Dashboard surface additions:**

- Per-sleeve exposure row under the existing positions
  panel: sleeve_id, current budget fraction, current gross
  exposure, current net exposure.
- Per-sleeve daily return card: sleeve_id, today's
  `SleeveDailyAttributionRecord.daily_return` if present
  (else "pending"), rolling 30-day Sharpe annualized.
- Per-sleeve drift verdicts: for each sleeve, the latest
  `DriftMonitorVerdict` for `ks::<sleeve_id>` and
  `pnl::<sleeve_id>`. Portfolio-level PSI verdicts surfaced
  at the top of the drift section (not per-sleeve).
- Per-sleeve halt state: pulled from
  `OperatorControlStore.is_sleeve_halted(sleeve_id)`.
- Current `BlueprintActivationRecord` header at the top of
  the dashboard: blueprint_id, constituent sleeves,
  activation timestamp, operator identifier. If no blueprint
  is active (legacy mode), the header shows the legacy
  `StrategyActivationRecord` summary and a note indicating
  single-strategy mode.

**Tests cover:**

- Two-sleeve blueprint active → dashboard snapshot includes
  two-sleeve rows in each section.
- Single-sleeve fallback active → dashboard shows only the
  surviving sleeve with a banner noting the narrowing.
- Legacy single-strategy mode → dashboard has the pre-2.1
  single-strategy layout (no per-sleeve rows).
- Drift-verdict mapping: a critical `ks::trend-following-v1`
  verdict surfaces on the trend-following-v1 row as a
  warning/critical indicator.

### W9 — Closing pass + Stage 1 rollout

Standard closing pass:

- `uv run pytest -q` (with existing `--deselect` pattern).
- `uv run mypy src/tradingx`.
- `uv run ruff check src/tradingx tests`.
- `python3 scripts/check_index.py`.
- `./scripts/validate`.

**Stage 1 merge commit.** W1–W8 land as a single mergeable PR.
BRIEF-0003 completion criteria 1, 3, 4, 5, 6 are satisfied
on merge; criteria 2 (drift P&L-divergence monitor
activation) is Stage 2 and ships in a follow-up commit
— see W10.

**INDEX bump.** Register DESIGN-0017 + BRIEF-0003; bump
INDEX version; BRIEF-0002 status unchanged (tranche 1 closure
is an operator action, not a governance update).

### W10 — Stage 2 drift P&L-divergence activation (follow-up commit)

**Files:**
- Modify: `src/tradingx/drift/gateway.py` (tighten the
  `_pnl_verdicts` loop — no change to the pending-semantics
  branch, which already correctly handles sleeves without
  attribution records; the activation is simply "both sleeves
  now produce records, so both produce real verdicts instead
  of pending").
- Modify: test fixtures that previously pinned pending
  verdicts for non-active sleeves to now pin real verdicts.

**Why this is a separate commit.** Per BRIEF-0003 D5 two-stage
rollout: if W1–W8 Stage 1 surfaces a latent issue during
paper validation (unexpected decomposition math, fallback
edge case, blueprint-activation race), Stage 2 is not already
committed. Rollback = revert Stage 2 commit only. Stage 1
provides a week-ish of paper-session data under the real
two-sleeve wiring before Stage 2 calibrates thresholds
against it.

**What actually changes in Stage 2.** Very little code. The
gateway's `_pnl_verdicts` loop at
[drift/gateway.py:505](/src/tradingx/drift/gateway.py:505)
already iterates over both sleeves; it was producing
`pending` for non-active sleeves because the attribution
reader returned empty. With Stage 1 shipped, the attribution
reader returns records for both sleeves (via the
`SleeveDecompositionRecord` decomposition path added to
`drift/attribution.py`). Stage 2 is the first automation
cycle where both sleeves produce real verdicts; the commit
is the fixture + threshold recalibration.

## Testing approach

Standard TDD per repo convention. Each work item produces
unit tests before implementation. Additional integration
coverage:

- `tests/integration/test_two_sleeve_paper_cycle.py` (new):
  full blueprint-based paper cycle end-to-end — activate
  blueprint, run service cycle, assert aggregate plan +
  decomposition sidecar persisted, assert intents carry
  `sleeve_id`, assert `SleeveDailyAttributionRecord`
  populates for both sleeves.
- `tests/integration/test_fallback_drill.py` (W7) — the
  rollback drill described above.
- `tests/integration/test_activation_change_regeneration.py`
  (W6) — blueprint switch → artifact regeneration happens.

## Acceptance criteria

Sub-tranche 2.1 Stage 1 is complete when:

1. `RuntimePortfolioPlan.per_sleeve_target_weights` populated
   when blueprint-active; the aggregate invariant regression
   test passes.
2. `BlueprintActivationRecord` persisted and read via the
   activation gateway; validation catches missing snapshot IDs.
3. `build_portfolio_cycle_target_weights` shares
   `_combine_sleeve_weights` with 1.4's batch path;
   element-wise regression test passes.
4. Service loop writes `SleeveDecompositionRecord` sidecar
   per cycle when blueprint is active.
5. `sleeve_id` threads through `TradeIntent`,
   `ExecutionLifecycleRecord`, `ClosedTradeRecord`; all three
   default to `None` for backwards compatibility; blueprint-
   based paths populate.
6. Artifact regeneration triggers on both activation change
   (blueprint_id differs from last-seen) AND operator
   recalibration (pending file written by
   `recalibrate_drift_reference`).
7. `narrow_blueprint_on_sleeve_failure` produces the narrowed
   blueprint + supersedes the record + emits
   `RiskControlEvent(control_type="blueprint_narrowed")` +
   `OperatorAlert(category="blueprint_narrowed")`. The
   integration rollback drill passes.
8. Operator dashboard surfaces per-sleeve rows when a
   blueprint is active; pre-2.1 layout preserved when legacy
   single-strategy mode is active.
9. `uv run pytest -q`, `uv run mypy src/tradingx`,
   `uv run ruff check`, `python3 scripts/check_index.py`,
   `./scripts/validate` all pass.
10. `SleeveAttributionRecorder` now reads from the
    decomposition sidecar when present (both sleeves
    attributed); portfolio-state equity-delta fallback
    remains for legacy mode.

Stage 2 adds:

11. `drift/gateway.py` `_pnl_verdicts` produces real verdicts
    (not pending) for both shipped sleeves once attribution
    records for both accumulate.

## Decisions resolved (no open items)

All BRIEF-0003 D1–D5 + D8 resolutions are implemented here.
No new D-level decisions introduced.

Implementation-level judgment calls for Codex review:

1. **Majority-attribution tie-breaking** (W5). The plan
   breaks ties by registry order (`trend-following-v1`
   first). Alternative: by sleeve with the larger budget
   fraction. Flag if the alternative feels cleaner.
2. **Fallback persistence-threshold** (W7). 3 consecutive
   cycles before narrowing. Flag if a different threshold
   (e.g., 1-cycle immediate, or a time-based 15-minute
   window) better matches operational reality.
3. **Dashboard surface exact files** (W8). The plan points
   at `portfolio.py` + performance analytics; the actual
   operator-platform layout may differ. Match existing
   convention.
4. **`BlueprintExhaustionError` handling** (W7). Plan says
   the service loop transitions to full operator-clearance
   halt. Alternative: auto-supersede to the legacy
   single-strategy path for the baseline candidate. The
   halt option is more conservative; flag if a different
   degradation is preferred.

## Governance impact

- **Register DESIGN-0017 + BRIEF-0003 in INDEX.** Both new
  artifacts; both added to INDEX-0001 with a patch bump.
- **BRIEF-0002 unchanged.** Tranche 1 closure is an operator
  paper-session action, not a governance update. No BRIEF-0002
  amendment shipped from this tranche.
- **GATES-0001 unchanged.** No new gate criteria in 2.1.
  Drift alarms remain paper-evidence only.
- **FFL-0001 unchanged.** No deferrals move in or out.
- **ADR impact: none.** 2.1 implements decisions locked in
  BRIEF-0003 D1–D5 + D8; no ADR-level architectural decisions
  introduced.
- **CONST-0001 unchanged.**

## References

### Repo documents

- [BRIEF-0003 Tranche 2 planning brief](/docs/superpowers/specs/2026-04-22-tranche-2-planning-brief.md)
  — scope + D1–D5 + D8 resolutions.
- [BRIEF-0002 Tranche 1 planning brief v1.2.0](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
  — the closure clause that paper validation consumes.
- [DESIGN-0015 Tranche 1.4 portfolio construction and drawdown defense](/docs/superpowers/specs/2026-04-21-tranche-1-4-portfolio-construction-and-drawdown-defense-design.md)
  — `PortfolioBlueprint`, `build_portfolio_target_weight_history`,
  `_combine_sleeve_weights` extraction target.
- [DESIGN-0016 Tranche 1.5 live drift monitoring](/docs/superpowers/specs/2026-04-21-tranche-1-5-live-drift-monitoring-design.md)
  — `DriftAlarmGateway`, `SleeveDailyAttributionRecord`,
  `recalibrate_drift_reference`, pending semantics that
  Stage 2 flips.
- [GATES-0001 Acceptance gates v1.2.1](/docs/validation/acceptance_gates.md)
  — Gate 3 evidence surface (drift events); Gate 4 checklist.
- [FFL-0001 Future features ledger](/docs/roadmap/future-features-ledger.md)
  — unchanged; deferrals remain.

### Existing source files

- [src/tradingx/runtime_portfolio.py](/src/tradingx/runtime_portfolio.py)
  — `RuntimePortfolioPlan`, `RuntimePortfolioPlanner`,
  `_trade_intent_for_plan_item`.
- [src/tradingx/portfolio/construction.py](/src/tradingx/portfolio/construction.py)
  — batch composition path; source of `_combine_sleeve_weights`
  extraction.
- [src/tradingx/portfolio/blueprint.py](/src/tradingx/portfolio/blueprint.py)
  — `PortfolioBlueprint`, `SleeveRiskBudget`.
- [src/tradingx/activation.py](/src/tradingx/activation.py)
  — `LocalActivationGateway`; the gateway that gains
  blueprint-activation methods.
- [src/tradingx/service.py](/src/tradingx/service.py) —
  service loop; the per-cycle plan/persist seam.
- [src/tradingx/drift/attribution.py](/src/tradingx/drift/attribution.py)
  — `SleeveAttributionRecorder`; source of the
  decomposition-based upgrade path.
- [src/tradingx/drift/gateway.py](/src/tradingx/drift/gateway.py)
  — Stage 2 target (`_pnl_verdicts`).
- [src/tradingx/automation.py](/src/tradingx/automation.py)
  — `build_default_market_day_automation_runner`;
  activation-change detection seam.
