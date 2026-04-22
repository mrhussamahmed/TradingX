---
id: BRIEF-0003
title: Tranche 2 planning brief
version: 1.0.0
status: active
created: 2026-04-22
last_amended: 2026-04-22
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-22
---

# BRIEF-0003: Tranche 2 planning brief

## Purpose

Scope the hardening work that sits between tranche-1 shipped
([BRIEF-0002 v1.2.0](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
completion criteria all met at `main` @ `075ca73`) and Gate 4
live enablement. Tranche 2 is not a "new strategy development"
arc — the two sleeves shipped in 1.3 are what goes live. Tranche
2 closes the engineering gaps that were legitimately deferred
from 1.4/1.5 to keep those tranches shippable.

Same governance shape as BRIEF-0002: thin document, no deep
design inside, each sub-tranche gets its own spec when its
turn comes.

## Authority order

1. [constitution](/.specify/memory/constitution.md)
2. [SPEC-0013 Capital growth landscape](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
3. [ADR-0021 Three-tier benchmark stack](/docs/adrs/ADR-0021-benchmark-stack.md)
4. [ADR-0022 Gate 1 reframe](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
5. [GATES-0001 Stage 1 acceptance gates](/docs/validation/acceptance_gates.md) v1.2.1
6. [BRIEF-0002 Tranche 1 planning brief](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md) v1.2.0
7. This brief (BRIEF-0003)
8. Sub-tranche specs (DESIGN-0017 onward)

## Relationship to tranche 1

BRIEF-0002 v1.2.0 narrowed tranche 1's criterion 5 to "live-vs-
backtest P&L divergence for the currently-active sleeve-backed
strategy" and relocated multi-sleeve P&L divergence — and the
live multi-sleeve runtime wiring it depends on — to Gate-4-
enablement work. That relocation IS tranche 2. BRIEF-0003 is
the governance artifact that picks up what BRIEF-0002 put down.

Tranche 1 closure (one full paper session green across all six
BRIEF-0002 v1.2.0 criteria) is an operator decision, not a
tranche-2 prerequisite. Per D8 below, paper-session validation
runs in parallel with tranche 2.1 implementation.

## Tranche 2 completion criteria

Tranche 2 is complete when **all** of the following are
operational:

1. Multi-sleeve live runtime wiring shipped and green in paper:
   sleeve-aware `RuntimePortfolioPlan`, per-sleeve target-weight
   persistence during service cycles, blueprint-based activation
   gateway, per-sleeve attribution **fractions** (not a single
   primary label) threaded through `TradeIntent` +
   `ExecutionLifecycleRecord` + `ClosedTradeRecord`. (2.1)
2. Multi-sleeve P&L divergence monitor activated — the
   `pending` semantics 1.5 shipped for non-active sleeves flip
   to real verdicts once live attribution exists for both
   shipped sleeves. (2.1 Stage 2)
3. Blueprint activation artifact shipped. A single
   `BlueprintActivationRecord` is the source of truth for
   "which blueprint is live right now": blueprint_id,
   constituent sleeve_ids, referenced `ApprovedWeightSnapshot`
   ids, activation status, operator-approval timestamp. (2.1)
4. Artifact regeneration wired to activation-change and
   operator-recalibration triggers. The 1.5 drift-reference
   snapshot and backtest-reference returns artifacts are
   rebuilt when a new blueprint activates or when the operator
   invokes `recalibrate_drift_reference`. (2.1; closes the P3
   nit flagged in the 1.5 code review.)
5. Single-sleeve fallback / rollback path verified as an
   operational requirement: if one sleeve fails due to a
   **structural** termination — operator halt via
   `halt_sleeve`, critical drift alarm, or trial-summary
   Sharpe gate firing (the three triggers the shipped
   `SleeveRuntimeController` actually terminates on) — the
   other sleeve continues to run under a narrowed blueprint
   without requiring a full halt. Regime-stressed zero
   exposure is explicitly NOT a narrowing trigger — per
   [BRIEF-0002 D4](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md),
   it is an intentional "cash is a consequence" state. See
   [DESIGN-0017 §W7](/docs/superpowers/specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md)
   for the exact trigger list. Evidence: an operator-exercised
   rollback drill persisted as an artifact. (2.1)
6. Operator dashboard surfaces both sleeves side-by-side —
   per-sleeve exposure, P&L, drift verdicts, activation state,
   halt state. (2.1)
7. CPCV + PBO research + spec complete (2.2 — research lane
   per D5 of BRIEF-0002). Design-only; no runtime behavior
   change. Activates the PBO Gate-1 hard-gate criterion in a
   future sub-tranche after evidence accumulates.
8. Gate 2 robustness evidence produced against the shipped
   sleeves (2.3 — evidence lane). Uses the already-shipped
   adversarial harness; no new development.

When all eight are complete and tranche 1 paper-session closure
has happened, the Gate 4 live-enablement checklist becomes the
next governance step.

## Sub-tranche sequence

| # | Sub-tranche | Scope | Hard dependencies | Blocks | Status |
|---|-------------|-------|-------------------|--------|--------|
| 2.1 | Multi-sleeve live runtime wiring | Sleeve-aware `RuntimePortfolioPlan`; blueprint-based activation with `BlueprintActivationRecord`; `sleeve_id` threaded through `TradeIntent` + execution records; per-sleeve live target-weight persistence; live portfolio construction per-cycle; two-stage drift multi-sleeve monitor activation; artifact regeneration on activation change / recalibration; operator dashboard two-sleeve view; single-sleeve fallback / rollback drill | BRIEF-0002 tranche-1 complete at merge-level (paper-session closure can run in parallel per D8) | Gate 3 evidence under the real two-sleeve architecture; Gate 4 live enablement | **NEXT** — spec drafted as [DESIGN-0017](/docs/superpowers/specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md) on `docs/tranche-2-1-planning` |
| 2.2 | CPCV + PBO research + spec (parallel research lane) | Design CPCV topology; write tranche-2-hardening spec; scope PBO computation; draft implementation plan. No runtime behavior change. Activating PBO as a Gate 1 hard-gate is a separate future sub-tranche after ≥ 6 months of trials-ledger evidence per [FFL-0001-06](/docs/roadmap/future-features-ledger.md) Stage 2 | None (parallel research) | Future PBO Gate-1 hard-gate activation | Unblocked (research lane) |
| 2.3 | Gate 2 robustness evidence (parallel evidence lane) | Run cost-stress + parameter-perturbation + walk-forward checks against `trend-following-v1` + `vol-target-v1` using the already-shipped adversarial harness at [validation.py](/src/tradingx/validation.py); produce Gate 2 validation report | Tranche 1 merged (already true) | Gate 4 live enablement | Unblocked (evidence lane; no development) |

Anti-scope creep note: CPCV/PBO implementation activation and
Gate 2 evidence production are explicitly **not folded into
BRIEF-0003's core 2.1 work**. They are parallel lanes with
their own completion criteria and their own future specs.
Treating them as out-of-scope keeps 2.1 sized like 1.4 rather
than bloating it into a multi-month tranche.

## Research vs governance lanes

Parallelizable:

- **Paper-session validation of tranche 1** — runs on current
  `main`; gathers BRIEF-0002 closure evidence + early Gate 3
  evidence. Independent of BRIEF-0003.
- **2.2 CPCV + PBO research + spec** — unblocked per BRIEF-0002
  D5 Stage 1. Pure design work.
- **2.3 Gate 2 robustness evidence** — uses existing adversarial
  harness; no development. Can produce the Gate 2 validation
  report any time.

Strict-sequential:

- 2.1 → Gate 3 under two-sleeve paper trading (paper calendar
  time accumulates after 2.1 ships live-wiring).
- 2.1 → Gate 4 enablement (Gate 4 checklist can't be signed
  against single-active-strategy evidence).

## Resolved decisions (2026-04-22)

Hussam's resolutions for tranche 2.1 are captured below. Each
decision is load-bearing for [DESIGN-0017](/docs/superpowers/specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md)
and cannot be re-opened without a new BRIEF amendment.

### D1 — Activation authority unit

**Resolved:** **Blueprint-as-a-unit; the blueprint artifact
carries the strategy bindings directly** (Codex round-2 P1 fix).
The operator signs off on a single `PortfolioBlueprint` file
that names its constituent sleeves **and** the strategy_id
each sleeve is bound to. The 1.4 `SleeveRiskBudget` dataclass
gains an additive `strategy_id: str | None = None` field
(defaults to `sleeve_id` when omitted, preserving existing
single-strategy deployments). Approval of the blueprint file
is approval of those bindings — there is no separate bindings
artifact to sign off on.

Concretely: `PortfolioBlueprint.sleeve_budgets: tuple[SleeveRiskBudget, ...]`
is the only artifact the operator reviews. Each `SleeveRiskBudget`
now records `(sleeve_id, strategy_id, budget_fraction, max_corr)`.
Activation reads the effective `strategy_id` (either the
explicit field or `sleeve_id` as fallback), resolves it through
`ApprovedWeightSnapshotStore.load_by_strategy_id(...)`, and
captures the resulting `snapshot_id` on the activation record.
The activation call site at W2 takes the blueprint alone — no
companion bindings argument.

**Per-sleeve overrides remain available** via the existing
`OperatorControlStore.halt_sleeve(sleeve_id, reason)` action —
the operator can halt one sleeve inside a running blueprint
without tearing the whole blueprint down. That preserves
operational flexibility while keeping activation authority
cleanly scoped.

**Rejected alternatives:**
- Per-sleeve activation with the blueprint layered on top →
  two activation records per running blueprint; duplicate
  audit paths.
- A separate `BlueprintActivationSpec` artifact that bundles
  blueprint + bindings → reopens the authority boundary
  (operator now signs off on two artifacts to activate one
  thing); the round-1 draft's `sleeve_to_strategy_bindings`
  activation argument was this pattern in disguise. The
  shipped blueprint file IS the signed-off unit.

### D2 — Hard halt scope

**Resolved:** **Keep tranche 1.4's portfolio-aggregate MDD as
the sole auto-halt trigger.** The 25% portfolio-aggregate hard
halt stays in its current form. No per-sleeve auto-halt MDD
threshold is introduced.

Per-sleeve halts remain **operator-initiated only** via
`OperatorControlStore.halt_sleeve`. This preserves the single
halt-authority boundary: one trigger, one operator clearance
cycle.

**Rejected alternative:** per-sleeve auto-halt MDD thresholds
layered on top. Would create two orthogonal halt ladders and
ambiguous clearance semantics.

### D3 — ApprovedWeightSnapshot reshape

**Resolved:** **Blueprint references N existing
`ApprovedWeightSnapshot`s by `strategy_id`** (Codex round-1 P1
fix + round-2 P2 API-naming fix). Each sleeve keeps its own
`ApprovedWeightSnapshot` at the existing path
[`config/strategy/weights/<strategy_id>.yaml`](/src/tradingx/weights.py:22).
Per D1 above, the blueprint file carries the `(sleeve_id,
strategy_id)` binding directly on each `SleeveRiskBudget` row
— no new artifact. Lookup is via the already-shipped
`ApprovedWeightSnapshotStore.load_by_strategy_id(strategy_id)`
method — no new indexing artifact, no change to the
committed-YAML storage contract. The existing offline
operator-review workflow is untouched: the operator reviews
and approves per-strategy YAML files; a blueprint is a pure
composition artifact that bundles references to those files.

**Audit capture of snapshot identity at activation time.**
At the moment a blueprint activates, the gateway reads each
bound strategy's current approved snapshot via
`ApprovedWeightSnapshotStore.load_by_strategy_id(strategy_id)`,
captures the resolved `ApprovedWeightSnapshot.snapshot_id`,
and persists both `strategy_id` (for future lookup) and
`captured_snapshot_id` (for audit/reproducibility) on the
`BlueprintActivationRecord`. Subsequent snapshot updates to
the same strategy_id do not retroactively rewrite active
activation records — the captured snapshot_id pins what was
approved when. The activation's identity (`activation_id`)
changes whenever bindings OR captured snapshot identities
change, which is what W6's regeneration trigger keys on.

**Rejected alternatives:**
- A new `PortfolioWeightSnapshot` type bundling multiple
  snapshots into one → splits operator review between two
  artifact types; requires migration of existing single-
  strategy deployments.
- Adding a standalone `snapshot_id`-keyed lookup / index
  artifact to the weights store → new storage-contract
  surface with no operator-facing benefit; the
  strategy_id + captured-at-activation audit gives the same
  reproducibility with zero new storage primitives.

### D4 — Attribution upgrade timing

**Resolved:** **Ship per-sleeve attribution fractions on
`TradeIntent` + `ExecutionLifecycleRecord` + `ClosedTradeRecord`
in tranche 2.1.** This is the whole point of "live multi-sleeve"
— Gate 3 evidence and operator attribution become sleeve-
resolved instead of aggregate-only.

**Fractions, not a single winner-take-all label.** For overlap
symbols like SPY (which both shipped sleeves touch), a single
primary `sleeve_id` would erase the minority sleeve's share
from the execution chain. Tranche 2.1 therefore records
`sleeve_attributions: tuple[(sleeve_id, fraction), ...]` — the
full decomposition of who contributed to each fill. Fractions
sum to 1.0 (within rounding tolerance) for blueprint-based
intents; empty tuple for legacy / baseline intents. See
[DESIGN-0017 §W5](/docs/superpowers/specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md)
for the exact shape, the normalization rule, and the Gate 3
per-sleeve evidence reader that consumes it.

The 1.5 proportional-attribution workaround (via
`SleeveDailyAttributionRecord` computed from portfolio-state
equity deltas) **stays in place** for live per-sleeve daily
P&L tracking; the attribution-fraction thread through
executions is complementary (fill-level attribution vs. daily
P&L; different consumers).

**Rejected alternatives:**
- Defer the threading to a later cleanup → leaves Gate 3 with
  aggregate-only fill evidence.
- Single `sleeve_id` with majority attribution → primary label
  only, not true fill-level evidence for overlap symbols.
- Split overlapping-symbol intents by sleeve (one intent per
  `(symbol, sleeve_id)` pair) → changes the one-intent-per-
  symbol invariant the current runtime and broker routing
  depend on; higher blast radius for negligible benefit over
  fractions.

### D5 — Rollout ordering

**Resolved:** **Two-stage rollout.** Stage 1: implement + merge
the multi-sleeve live runtime wiring, `BlueprintActivationRecord`,
`sleeve_id` threading, per-sleeve persistence, single-sleeve
fallback, dashboard view. Stage 2: a small follow-up commit
flips 1.5's drift `pnl::<sleeve_id>` monitor from `pending` to
active for both shipped sleeves (recalibrates thresholds
against the new multi-sleeve baseline).

The two-stage gating keeps rollback cheap: if Stage 1 surfaces
a latent issue during paper validation, Stage 2 is not already
committed to the shipped configuration.

**Rejected alternative:** atomic rollout. Simpler governance
but larger blast radius if the multi-sleeve wiring has a bug
— the drift monitor would immediately start producing noisy
verdicts against still-uncalibrated live data.

### D8 — Paper validation timing (sequencing with tranche 2.1)

**Resolved:** **Run in parallel.** Tranche-1 paper-session
validation of the single-active-strategy runtime runs against
current `main` @ `075ca73` while tranche 2.1 drafting +
implementation proceed. Both activities unblock different
things: paper validation produces BRIEF-0002 closure evidence
+ early Gate 3 evidence; 2.1 produces the infrastructure
needed for Gate 3 under two-sleeve architecture.

This pins the sequencing claim so 2.1 doesn't accidentally
become a tranche-1-closure dependency.

**Rejected alternatives:** (a) run paper validation first →
close tranche 1 → start 2.1 (sequential; slower to Gate 4); or
(b) start 2.1 first → run paper validation under two-sleeve
(wastes tranche-1 closure opportunity on current architecture).

## Future features ledger reference

Tranche 2.1 does not move any [FFL-0001](/docs/roadmap/future-features-ledger.md)
entries into scope. The ledger remains untouched. FFL-0001-06
(CPCV/PBO) is the target of sub-tranche 2.2 but only at Stage 1
(research + spec); Stage 2 activation remains deferred per
BRIEF-0002 D5.

## Anti-drift rules

Update this brief in the same session that:

- Adds, removes, or re-scopes a sub-tranche.
- Changes a tranche-2 completion criterion.
- Amends any D1–D5 or D8 resolution.
- Promotes a parallel lane (2.2 research, 2.3 evidence) to a
  dedicated sub-tranche requiring its own spec.

If a sub-tranche spec contradicts this brief, the brief is
updated in the same commit so the contract stays visible —
same rule as BRIEF-0002.
