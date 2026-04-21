---
id: BRIEF-0002
title: Tranche 1 planning brief
version: 1.1.2
status: active
created: 2026-04-21
last_amended: 2026-04-21
supersedes: BRIEF-0002@1.1.1
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# BRIEF-0002: Tranche 1 planning brief

## Purpose

Lock the decomposition, sequence, and completion criteria for tranche 1
in a single short document so no sub-tranche drifts from the overall
arc. Intentionally thin: no deep design inside this document. Each
sub-tranche gets its own spec when its turn comes.

## Authority order

1. [constitution](/.specify/memory/constitution.md)
2. [SPEC-0013 Capital growth landscape](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
3. [ADR-0021 Three-tier benchmark stack](/docs/adrs/ADR-0021-benchmark-stack.md)
4. [ADR-0022 Gate 1 reframe](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
5. [GATES-0001 Stage 1 acceptance gates](/docs/validation/acceptance_gates.md) v1.1.0
6. This brief (BRIEF-0002)
7. Sub-tranche specs (pending)

## Tranche 1 completion criteria

Tranche 1 is complete when **all** of the following are operational:

1. Trend sleeve and vol-managed beta sleeve running in paper against
   the three-tier benchmark stack.
2. Portfolio risk budgets and drawdown throttles enforced at runtime,
   including the 25% MDD hard halt that is currently documented but
   not yet wired (per the P1 gap surfaced in the ADR review).
3. Sleeve-level cost-aware evaluation: candidate metrics are net of
   `estimate_trade_costs` aggregated over the backtest window.
4. Validation stack with purged/embargoed k-fold CV and a trials
   ledger; Deflated Sharpe Ratio wired into `evaluate_candidate` and
   carried in `EvaluationEvidencePack`.
5. Live drift diagnostics (PSI on features, KS on signal outputs,
   execution-quality drift, live-vs-backtest P&L divergence) emit
   alarms against calibrated thresholds.
6. Marginal-portfolio-contribution criterion wired into Gate 1
   evaluation once portfolio construction lands (ships in 1.4).

When all six are shipped and green in paper for at least one full
session, tranche 1 closes and we can open the Gate 4 readiness
discussion.

## Sub-tranche sequence

| # | Sub-tranche | Scope | Hard dependencies | Blocks | Status (2026-04-21) |
|---|-------------|-------|-------------------|--------|---------------------|
| 1.1 | Validation infrastructure | Purged/embargoed k-fold CV; trials ledger; DSR wiring into `evaluate_candidate` + evidence pack; sleeve-level cost model integration via existing `costs.py` primitives | None — can start immediately on top of `main` at `c6fbcec` | Sleeves (1.3), portfolio construction (1.4); any honest candidate evaluation | **SHIPPED** — merged to `main` |
| 1.2 | Market-state features | HAR-RV volatility estimator; rule-based regime composite (200d SMA / VIX level / yield-curve shape); empirical comparison of vol estimators with candidate-default tune if HAR-RV or EWMA beats `garch` | 1.1 scope stable (can start research in parallel; governance merges sequentially) | Sleeves (1.3) consume feature inputs | **SHIPPED** — merged to `main` |
| 1.3 | Sleeves | Trend sleeve (TSMOM per Moskowitz-Ooi-Pedersen 2012) productionized from existing `signals/trend.py`; vol-managed beta sleeve (Moreira-Muir 2017) productionized from existing `signals/vol_target_spy.py` | 1.1 merged; 1.2 merged; **Hussam decisions on D1–D4 resolved** | Portfolio construction (1.4) needs sleeve outputs | **SHIPPED** — merged to `main` at `e953b7e` |
| 1.4 | Portfolio construction + drawdown defense | Per-sleeve risk budgets; correlation caps; MDD throttle at 15% design (proportional exposure reduction); CDaR soft-throttle; **25% MDD runtime hard halt wired to the existing operator-clearance flow**; sleeve termination rules; marginal-portfolio-contribution criterion wired into Gate 1 | 1.3 merged (needs at least one sleeve live) | Live monitoring (1.5) observes portfolio state | **SHIPPED** — merged to `main` at `02a3c97` |
| 1.5 | Live drift monitoring | PSI on feature distributions; KS tests on signal outputs; execution-quality drift (realized slippage vs modeled); live-vs-backtest per-sleeve P&L divergence alarms | 1.4 merged (needs runtime state) | Gate 4 readiness discussion | **NEXT** — spec drafted as [DESIGN-0016](/docs/superpowers/specs/2026-04-21-tranche-1-5-live-drift-monitoring-design.md) on `docs/tranche-1-5-planning` |

## Research vs governance lanes

Parallelizable:

- **1.2 research** (empirical vol-estimator comparison on in-repo bars)
  can run in parallel with 1.1 implementation. Governance merges for
  1.2 follow 1.1 to avoid cross-PR conflict.
- **1.5 scoping** (which drift metrics, what thresholds) can start
  once 1.3 is in flight.

Strict-sequential:

- 1.1 → 1.3 (sleeves need validation infra)
- 1.3 → 1.4 (portfolio construction needs sleeves)
- 1.4 → 1.5 (drift monitoring needs runtime state)

## Resolved decisions (2026-04-21)

Hussam's resolutions for D1–D5 are captured below with the full
conversation context so implementers (Codex, future sessions) don't
have to re-derive them. Each subsection records the resolution, the
reasoning, and any follow-on work.

### D1 — Capital-at-risk and sizing philosophy

**Resolved:** **Vol-targeted sizing for tranche 1 (option B).** The
goal is fractional Kelly (option C) once the edge estimate is
trustworthy enough to support it.

**Reasoning.** Vol-targeted sizing is consistent with the
Moreira-Muir sleeve already in tranche 1.3 scope. Fixed notional
(option A) was rejected as too naive — it doesn't shrink in vol
spikes. Full Kelly was rejected for tranche 1 because edge
estimates from backtests are biased upward and Kelly is extremely
sensitive to edge-estimate errors; even fractional Kelly requires
live-paper evidence before it can be trusted.

**Path to fractional Kelly (future).** Ten concrete criteria that
must all hold before switching. Documented in
[FFL-0001-01](/docs/roadmap/future-features-ledger.md). Summary:
tranche 1 complete, ≥ 200 closed paper trades per sleeve, live
drift green for ≥ 6 months, stable per-sleeve edge, bootstrap
Sharpe CI above zero, DSR ≥ 0.95, PBO ≤ 0.30, live-vs-backtest
Sharpe within 30%, plus **two independent sizing controls that
both apply simultaneously**: (a) a Kelly fraction multiplier
(start at 0.25 × `f*`, progress to 0.5 × `f*` only after another
6 months, full Kelly never adopted), AND (b) a sleeve-allocation
capital cap at 50% of the portfolio MDD budget — currently 7.5%
of portfolio equity per sleeve given ADR-0021's 15% design target.
The capital cap and the Kelly multiplier are **different
controls** and both enforce.

**When triggered:** **ADR-0023** opens to formalize the switch.
Never automatic; operator sign-off mirrors Gate 4 protocol.

### D2 — Instrument scope for v1

**Resolved:** **ETFs only (option A) for tranche 1.** Options
expansion is future work, **durably documented** so it isn't lost.

**Reasoning.** Options add a full subsystem (chain data, Greeks,
assignment, margin, pin risk, expiry management) that would
materially delay tranche 1. Hussam explicitly flagged that the
future plan must be captured somewhere durable to prevent
accidental drop.

**Where documented:** [FFL-0001-02](/docs/roadmap/future-features-ledger.md)
records the full scope when options are brought back (chain data,
tail-hedging sleeves, volatility risk premium, margin math,
Greeks-aware controls).

**Bring-back condition:** operator explicitly opens the options
tranche. No implicit trigger.

### D3 — Turnover tolerance

**Resolved:** **Moderate (option B).** Approximately 100–300%
annualized turnover target.

**Reasoning.** Low turnover would prevent honest regime-flip exits
in the trend sleeve. High turnover is only justifiable for
high-edge strategies we don't yet have. Moderate lets trend-
following flip when signals flip and vol-managed beta retreat in
vol spikes, with tax drag becoming a ~0.5–1.5% annual bleed that
the cost-drag report (shipped 1.1) makes visible.

### D4 — Cash-drag policy

**Resolved:** **Flat acceptable, but not preferred (option A with
critical nuance).**

**Hussam's nuance — codified as a design principle:**

> **Cash is a consequence, not a goal.** The bot holds cash only
> when an honest assessment says no sleeve has edge right now or
> that portfolio risk exceeds the budget. Flat is never a default
> posture, never a comfort zone, and never a substitute for
> capital growth. Sleeves actively seek exposure when signals,
> regime, and risk envelope permit. Cash held idle earns the
> hurdle T-bill yield only — it counts as underperformance versus
> the 60/40 opportunity cost, and that trade-off is made
> deliberately when the alternative is exposure the risk stack
> can't honestly support.

**Implementation consequences for tranche 1.3 and beyond:**

- **Vol-managed beta:** exposure floor is 0% **only when the
  regime composite classifies the current state as `stressed`**
  (the most severe of the four states shipped in tranche 1.2 per
  [DESIGN-0013 §W3](/docs/superpowers/specs/2026-04-21-tranche-1-2-market-state-features-design.md)
  and [features/regime.py](/src/tradingx/features/regime.py)).
  In the other three states (`risk_on`, `neutral`, `risk_off`),
  the sleeve runs at or near 100% of its budget, scaled by its
  own vol target. **The 1.3 spec MUST codify the exact
  regime → exposure-floor mapping for each sleeve** so trend and
  vol-managed beta apply the same mapping logic and no future
  sleeve spec is free to reinterpret "extreme vol regime."
- **Trend sleeve:** entries fire immediately when signal fires.
  No "flat discipline" delay, no confirmation-holding periods
  beyond what the signal itself requires. The trend sleeve is
  also regime-aware: in `stressed` it defers new entries (it does
  not force liquidation of existing positions, but does not open
  new ones).
- **No portfolio-level minimum cash buffer.** Cash is what's left
  after risk gating, not what's reserved first.
- **Reporting surface (1.4 + 1.5):** the operator dashboard
  surfaces "time in cash" as a warning metric. If the bot is flat
  more than 30% of sessions, that's a signal that either signals
  are too restrictive or the risk envelope is too tight — not a
  sign of prudent behavior.

### D5 — Timeline for first live enablement

**Resolved:** **Option A — ~3-month working target.**

**What this means in plain terms.** We work toward a rough
3-month deadline for first live enablement. To hit it without
cutting corners, **the research and spec phase** of tranche-2
hardening (CPCV, PBO) runs in parallel with tranche 1.5 rather
than strictly after. Faster than option B (strict sequential,
open-ended), but requires coordination to avoid cross-tranche
conflict.

**Two-stage trigger for CPCV/PBO.** Per
[FFL-0001-06](/docs/roadmap/future-features-ledger.md) the
tranche-2 hardening is split into two triggers so this brief and
the ledger don't contradict each other:

- **Stage 1 (now, unblocked by D5):** design + spec may start in
  parallel with tranche 1.5. Pure design work; no runtime
  behavior change.
- **Stage 2 (later, requires tranche 1 complete + ≥ 6 months of
  trials-ledger evidence):** activation as a Gate 1 hard
  criterion. Flips PBO from reported-only to pass/fail. Requires
  operator sign-off.

"Unblocked in parallel with 1.5" refers to Stage 1 only; Stage 2
timing is independent of the 3-month first-live target.

**"Working target" qualifier.** The 3-month date is a planning
anchor, not a promise. If validation evidence accumulates slower
than expected, or if the Kelly-switch gate (FFL-0001-01) needs
more paper-trade history, the date shifts. Target-date discipline
is "plan backward from the target and see what has to happen;
re-plan when evidence disagrees with the plan."

**Scope impact on tranche 1.3.** Tranche-2 scoping (CPCV
infrastructure, PBO computation, live-vs-backtest divergence
hardening) is unblocked to start research in parallel with
tranche 1.5 implementation. Governance merges for tranche 2 still
sequence after 1.5 to avoid PR conflict.

## Future features ledger reference

All tranche-1 deferrals (including the D1/D2 future paths above)
are captured in **[FFL-0001 Future features ledger](/docs/roadmap/future-features-ledger.md)**
— the single durable record of deliberately-deferred capabilities.
Each entry carries a bring-back condition. When a deferral moves
into scope, both FFL-0001 and the picking-up spec are amended in
the same session.

## Anti-drift rules

Update this brief in the same session that:

- adds, removes, reorders, or re-scopes a sub-tranche.
- changes the tranche-1 completion criteria.
- changes a sub-tranche's hard dependencies.
- amends any of the D1–D5 resolutions.
- adds or removes a Future features ledger entry that affects
  tranche-1 scope.

If a sub-tranche spec contradicts this brief, the brief is updated in
the same commit so the contract stays visible.
