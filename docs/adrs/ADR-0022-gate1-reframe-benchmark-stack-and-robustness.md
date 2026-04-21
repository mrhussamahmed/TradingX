---
id: ADR-0022
title: Reframe Gate 1 from standalone sleeve Sharpe to benchmark-stack criteria and robustness
version: 1.0.0
status: accepted
created: 2026-04-21
last_amended: 2026-04-21
supersedes: ADR-0020
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# ADR-0022: Reframe Gate 1 from standalone sleeve Sharpe to benchmark-stack criteria and robustness

## Status

Accepted on 2026-04-21. The operationally-active criteria below are
load-bearing as of commit `c6fbcec` on `main`. The criterion reserved
for tranche 1 ships when portfolio construction lands.

## Context

- [ADR-0020](/docs/adrs/ADR-0020-gate1-statistical-criteria.md)
  (draft) proposed tightening Gate 1 with Deflated Sharpe Ratio
  (DSR), Probability of Backtest Overfitting (PBO), and a
  10% design / 15% halt max-drawdown budget.
- The
  [2026-04-20 capital-growth landscape review](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
  (SPEC-0013) changed three things:
  1. The benchmark is no longer SPY; it is the three-tier stack
     defined by [ADR-0021](/docs/adrs/ADR-0021-benchmark-stack.md).
  2. The drawdown budget is reset to 15% design / 25% halt because
     tranche 1's two-sleeve architecture (trend + vol-managed beta)
     cannot realistically achieve ≤ 10% single-sleeve without
     over-throttling.
  3. The appropriate gated object is not a sleeve's standalone
     Sharpe but its marginal portfolio contribution plus
     robustness — a sleeve with Sharpe 0.8 and zero correlation to
     the existing book can improve the portfolio more than one with
     Sharpe 1.2 and 0.9 correlation.
- The benchmark-stack implementation (merged at commit `c6fbcec`)
  makes items (1) and (2) immediately operational. Item (3) requires
  portfolio-construction machinery that ships in tranche 1.

## Decision

### Operationally active today (commit `c6fbcec`)

Four hard-pass criteria, composed in
`evaluate_gate1_benchmark_criteria` at
[src/tradingx/validation.py:223](/src/tradingx/validation.py:223) and
the surrounding candidate-evaluation pipeline:

1. **`hurdle_clearance`** — cumulative return must exceed the cash
   hurdle cumulative return over the validation window.
2. **`opportunity_cost_edge`** — CAGR must exceed the 60/40 blend
   CAGR by 2% absolute (`GATE1_MIN_CAGR_EDGE = 0.02`).
3. **`operating_constraint`** — max drawdown ≤ 15% design AND
   CDaR@95% ≤ 8% threshold.
4. **`out_of_sample_profile`** — 756-day out-of-sample metrics
   remain within 30% of the in-sample profile on Sharpe, CAGR, and
   MaxDD. Constant `GATE1_MIN_OUT_OF_SAMPLE_DAYS = 756` at
   [src/tradingx/validation.py:44](/src/tradingx/validation.py:44).

### Computed and reported today, but not a hard gate

- **Deflated Sharpe Ratio** — computed and recorded on every
  candidate evidence pack for trend tracking.
- **North-star Sharpe threshold** — a point Sharpe ≥ 1.3 is recorded
  as preference-ranking data when choosing among surviving
  candidates. It is not pass/fail.

### Deferred to tranche 2 hardening

- **PBO as a hard gate** — requires combinatorial purged
  cross-validation (CPCV) infrastructure that ships in tranche 2.
- **CPCV as the validation topology** — tranche 1 uses
  purged/embargoed k-fold + trials ledger as the hard floor. CPCV
  replaces k-fold once the trials ledger has accumulated enough
  history to make CPCV fair.

### Deferred to tranche 1 hardening (ships with portfolio construction)

- **Marginal portfolio contribution** as a Gate 1 criterion — a
  sleeve that individually passes the four operational criteria
  above must also improve the portfolio's Sharpe, Calmar, and CDaR
  when added to the existing book, with cost and correlation
  accounted for. This supplements the current criteria; it does not
  replace them.

## Consequences

### Positive

- Gate 1 is load-bearing now: the four operational criteria are all
  enforced by the validation engine at
  [src/tradingx/validation.py](/src/tradingx/validation.py).
- The drawdown budget is achievable under tranche 1's sleeve count,
  so Gate 1 failures represent real edge problems rather than
  aspirational throttling targets.
- The gate is honest about what the validation pipeline can prove
  today versus what requires tranche 1+ infrastructure.

### Negative

- Candidates that would have passed ADR-0020's draft criteria may
  fail ADR-0022's criteria in a high-rate regime, because
  opportunity cost is 60/40 rather than SPY.
- The deferred marginal-portfolio-contribution criterion creates a
  known transitional period: tranche-1 sleeves can pass Gate 1
  before that criterion is operational. Mitigation: when tranche 1
  ships, the first two sleeves are re-evaluated under the full gate
  before any live-enablement discussion.

## Alternatives considered

- **Keep ADR-0020's PBO/CPCV/10%-MDD criteria as drafted.** Rejected
  because (a) PBO requires CPCV, which is not yet load-bearing, so
  enforcing it would gate on aspirational infrastructure; (b) 10%
  MDD is infeasible for tranche 1's two-sleeve scope without
  over-throttling.
- **Make marginal-portfolio-contribution a hard gate today using a
  stub portfolio.** Rejected because a stub either passes everything
  (false positives) or fails everything (false negatives); a real
  portfolio must exist before the criterion is meaningful.
- **Retain SPY-relative `benchmark_edge` alongside the new 60/40
  criterion.** Rejected because it adds a duplicate criterion with
  weaker semantics; the 60/40 edge subsumes the SPY edge.

## Supersedes

- [ADR-0020](/docs/adrs/ADR-0020-gate1-statistical-criteria.md) —
  Gate 1 statistical criteria around Deflated Sharpe and overfitting
  controls.

## Sources

- SPEC-0013 Capital growth landscape
  ([docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)).
- [ADR-0021](/docs/adrs/ADR-0021-benchmark-stack.md) — Three-tier
  benchmark stack.
- Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe
  Ratio."
- Bailey, D. H., Borwein, J. M., López de Prado, M., & Zhu, Q. J.
  (2015). "The Probability of Backtest Overfitting."
- Implementation merged at commit `c6fbcec` on 2026-04-21.
