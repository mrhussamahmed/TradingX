---
id: FFL-0001
title: Future features ledger
version: 1.0.0
status: active
created: 2026-04-21
last_amended: 2026-04-21
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# FFL-0001: Future features ledger

## Purpose

Single durable record of features and capabilities that are
**deliberately deferred** — not rejected, not forgotten, not
unplanned. Every entry captures:

- What the feature is
- Why it's deferred
- The concrete condition that brings it back in
- Cross-references to governed artifacts that scoped the deferral

When a deferred feature moves out of the ledger, this file is
amended in the same session the feature's in-scope spec is approved.

This ledger is the growing list the team uses to prevent
accidentally-dropped scope. It supplements — does not replace —
the per-spec "Deferred explicitly" tables (e.g., SPEC-0013 §9),
which remain the local authority for tranche-scoped deferrals.

## Authority

This is a governance ledger. It records deferrals, not decisions
about architecture or gates. For those, see ADR-NNNN and
GATES-0001.

## How to read each entry

| Field | Meaning |
|---|---|
| **ID** | `FFL-NNNN-NN` — global ledger ID, stable across renames |
| **Item** | One-line title of the deferred capability |
| **Deferred from** | Which tranche / decision scoped the deferral |
| **Why deferred** | One-paragraph honest reason |
| **Bring-back condition** | Concrete, measurable trigger |
| **When triggered** | What happens next (spec, ADR, or direct implementation) |
| **Cross-references** | Links to the source artifacts |

---

## Ledger

### FFL-0001-01 — Fractional Kelly sizing (D1 → C)

**Deferred from:** BRIEF-0002 D1 resolution (2026-04-21). Tranche 1
uses vol-targeted sizing (D1 = B).

**Why deferred:** Kelly is extremely sensitive to edge-estimate
errors. Small overstatement of edge produces disproportionate
overbetting and deep drawdowns. Backtest-derived edge estimates
are almost always biased upward. Live paper evidence is required
before the edge estimate can be trusted enough for Kelly-based
sizing.

**Bring-back condition — all ten must hold:**

1. Tranche 1 complete (all sleeves, portfolio risk, drift
   monitoring live in paper).
2. ≥ 200 closed paper trades per sleeve under the Kelly
   candidate's configuration.
3. Live drift diagnostics green for ≥ 6 months (no PSI or KS
   alarms on feature distributions; live-vs-backtest P&L
   divergence within calibrated bounds).
4. Per-sleeve edge stable across two rolling 6-month windows.
   Last 6-month Sharpe ≥ 70% of prior 6-month Sharpe.
5. Bootstrap 95% confidence interval on per-sleeve Sharpe
   entirely above zero.
6. Deflated Sharpe Ratio ≥ 0.95.
7. PBO ≤ 0.30 (requires tranche-2 CPCV infrastructure).
8. Live vs backtest Sharpe within 30% per profile-tolerance rule.
9. Fractional Kelly only — start at 1/4-Kelly, progress to
   1/2-Kelly only after another 6 months of stable live
   evidence. Full Kelly is never adopted.
10. Hard cap on per-sleeve Kelly fraction at 0.5 × portfolio
    MDD budget (currently 7.5% given ADR-0021's 15% design
    target).

**When triggered:** open **ADR-0023: Switch from vol-targeted to
fractional Kelly sizing** with the passing gate evidence attached.
Operator sign-off required, same protocol as Gate 4 live
enablement. Never automatic.

**Operational accommodations already shipped (2026-04-21):**

- Trials ledger in tranche 1.1 records Sharpe and cost drag per
  evaluation; tranche 2 extends it to carry live-trade P&L.
- Live drift diagnostics ship in tranche 1.5.
- A future `evaluate_kelly_switch_gate` function in
  `src/tradingx/validation.py` (not yet implemented) will run all
  ten checks and return a single verdict.

**Cross-references:**

- [BRIEF-0002 §Decisions resolved](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
- [SPEC-0013 §9 Deferred explicitly](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [ADR-0022 §Deferred to tranche 2 hardening](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)

---

### FFL-0001-02 — Options scope expansion (D2 → B)

**Deferred from:** BRIEF-0002 D2 resolution (2026-04-21). Tranche
1 is ETFs only (D2 = A).

**Why deferred:** Options add an entirely new subsystem that would
materially delay tranche 1: chain data, Greeks, implied-vol
surface, assignment risk, expiry management, margin math under
Reg T and portfolio margin. Also introduces a new family of
sleeves (tail hedging, volatility risk premium) that each need
their own design + validation cycle.

**Scope when brought back:**

- **Chain data integration** — strikes, expiries, IV surface
  fetched from a suitable provider (Alpaca options API or
  alternative).
- **Tail-hedging sleeves** — protective puts, put-spread collars,
  VIX call overlay as drawdown-defense mechanisms.
- **Volatility risk premium sleeves** — short realized vol
  (systematic put-writing or VXX-short) as a structural-alpha
  source.
- **Assignment and margin complexity** — early-exercise handling,
  margin requirement calculation, collateral tracking.
- **Greeks-aware risk controls** — position sizing by delta,
  gamma risk limits, vega exposure caps, pin-risk management at
  expiry.
- **New validation criteria** specific to options (Greeks-based
  exposure gates, expiry-management tests).

**Bring-back condition:** operator explicitly opens the options
tranche. No implicit trigger.

**When triggered:** new planning brief (`BRIEF-NNNN`) scoping the
options expansion as a multi-sub-tranche effort. Almost certainly
its own arc, not folded into a later tranche of the current
stock/ETF roadmap.

**Cross-references:**

- [BRIEF-0002 §Decisions resolved](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
- [SPEC-0013 §9 Deferred explicitly](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)

---

### FFL-0001-03 — Mean-reversion sleeve

**Deferred from:** BRIEF-0002 (sub-tranche 1.3 scope). SPEC-0013
§9 also documents.

**Why deferred:** The canonical 8-ETF universe is too narrow for
cross-sectional mean-reversion to have a real edge. Mean-reversion
typically needs 50+ liquid names to generate enough pair
dispersion and diversify idiosyncratic noise.

**Bring-back condition:** universe expands to ≥ 50 liquid names
with acceptable data quality and cost profile.

**When triggered:** per-family vol-estimator comparison against
the mean-reversion sizing path (currently deferred per DESIGN-0013
W4 scope correction), followed by a proper sleeve spec.

**Cross-references:**

- [BRIEF-0002](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
- [SPEC-0013 §9](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [DESIGN-0013 §W4 scope correction](/docs/superpowers/specs/2026-04-21-tranche-1-2-market-state-features-design.md)

---

### FFL-0001-04 — Meta-labeling layer

**Deferred from:** SPEC-0013 §9.

**Why deferred:** Meta-labeling (de Prado 2018) wraps a primary
signal with a secondary ML model that decides whether to *act* on
each candidate trade. On the current 8-ETF daily-bar universe, the
degrees of freedom required for a secondary GBM exceed what the
data supports — the secondary model would overfit.

**Bring-back condition:** universe expansion (FFL-0001-03) AND
sufficient live-paper evidence to train a secondary model without
overfitting; likely tranche 3+.

**When triggered:** research-lane spec covering meta-labeling as a
post-tranche-2 hardening enhancement.

**Cross-references:**

- [SPEC-0013 §9](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [ADR-0022 §Deferred to tranche 1 hardening](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)

---

### FFL-0001-05 — Structural alpha sources (VRP, index rebalance, carry, ETF arbitrage)

**Deferred from:** SPEC-0013 §3 row 7 + §9.

**Why deferred:** Structural alpha sources are retail-accessible
but each one is its own research lane. Volatility risk premium
requires options (FFL-0001-02). Index rebalance requires corporate
action calendars. Carry (VIX term structure) requires options
chain data. ETF creation/redemption arbitrage requires authorized
participant data and is likely out of scope permanently for a
retail account.

**Bring-back condition:** tranche 3+ research lane; each source
gets its own scoping decision.

**When triggered:** per-source research spec after tranche 2
hardening completes.

**Cross-references:**

- [SPEC-0013 §3 + §9](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)

---

### FFL-0001-06 — CPCV and PBO as hard gates

**Deferred from:** ADR-0022 (Gate 1 reframe). Tranche 2 hardening.

**Why deferred:** CPCV (combinatorial purged cross-validation) is
needed to compute PBO (probability of backtest overfitting) at
honest scale. Both are tranche-2 work; tranche 1 uses
purged/embargoed k-fold CV + trials ledger only (shipped in 1.1).

**Bring-back condition:** tranche 1 complete, ≥ 6 months of
accumulated trials ledger evidence, operator approves tranche-2
start.

**When triggered:** tranche-2 hardening spec.

**Cross-references:**

- [ADR-0022 §Deferred to tranche 2 hardening](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
- [BRIEF-0002 D5 resolution](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)

---

### FFL-0001-07 — HMM / Markov-switching regime models

**Deferred from:** SPEC-0013 §4.A. Tranche 1 uses rule-based
regime composite (shipped in DESIGN-0013).

**Why deferred:** At current universe size, HMMs overfit. Rule-
based composites (SMA-200, VIX, yield curve) are transparent,
auditable, and empirically sufficient for tranche-1 regime gating.

**Bring-back condition:** universe expansion + richer market-state
data (intraday bars, options-implied signals) justifying a
stateful regime model.

**When triggered:** dedicated research spec in tranche 3+.

**Cross-references:**

- [SPEC-0013 §4.A](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [DESIGN-0013 §W3](/docs/superpowers/specs/2026-04-21-tranche-1-2-market-state-features-design.md)

---

### FFL-0001-08 — Implied volatility overlay

**Deferred from:** SPEC-0013 §4.A.

**Why deferred:** Requires options chain data, which is gated by
FFL-0001-02 (options scope expansion).

**Bring-back condition:** FFL-0001-02 brought back.

**When triggered:** alongside options expansion.

**Cross-references:**

- [SPEC-0013 §4.A](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)

---

### FFL-0001-09 — Multi-account and multi-strategy concurrent execution

**Deferred from:** SPEC-0013 §9.

**Why deferred:** Architectural expansion. Current runtime is
single-account single-strategy by design. Supporting multiple
accounts (or multiple strategies running live in parallel)
requires changes to the supervisor, operator controls, journal
layout, and activation semantics.

**Bring-back condition:** operator explicitly requests; not a
near-term item.

**When triggered:** dedicated architectural tranche and ADR
sequence.

**Cross-references:**

- [SPEC-0013 §9](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [ADR-0016 Runtime host](/docs/adrs/ADR-0016-local-trading-appliance-runtime-host.md)

---

### FFL-0001-10 — Full Almgren-Chriss execution modeling

**Deferred from:** SPEC-0013 §3 row 5 and §9. Tranche 1 uses the
simpler empirical cost model wired in `costs.py` + `backtest.py`.

**Why deferred:** Almgren-Chriss was built for institutional flow.
At current retail-scale AUM, spread + slippage + turnover drag
(already modeled) dominate. Full impact modeling becomes relevant
only when order size approaches meaningful percentages of daily
volume.

**Bring-back condition:** AUM and per-order sizes approach a level
where the book moves the market. Specifically: when median order
size exceeds 1% of 20-day ADV for the traded symbol.

**When triggered:** dedicated execution-modeling spec.

**Cross-references:**

- [SPEC-0013 §9](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)

---

## Anti-drift rules

Update this ledger in the same session that:

- A deferred feature moves into a tranche scope (delete the entry
  and cross-reference the spec that picked it up).
- A new feature is explicitly deferred by a governed artifact (add
  an entry with bring-back condition).
- A bring-back condition changes (amend the entry, bump the
  ledger version).

If an entry is deleted, record the deletion commit SHA in a
terminal `## History` section (not yet created; add on first
deletion).

## Sources

- [BRIEF-0002 Tranche 1 planning brief](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
- [SPEC-0013 Capital growth landscape](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [DESIGN-0013 Tranche 1.2 market-state features](/docs/superpowers/specs/2026-04-21-tranche-1-2-market-state-features-design.md)
- [ADR-0021 Benchmark stack](/docs/adrs/ADR-0021-benchmark-stack.md)
- [ADR-0022 Gate 1 reframe](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
