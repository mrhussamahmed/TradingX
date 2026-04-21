---
id: ADR-0021
title: Adopt three-tier benchmark stack in place of SPY-only benchmarking
version: 1.0.0
status: accepted
created: 2026-04-21
last_amended: 2026-04-21
supersedes: ADR-0004
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# ADR-0021: Adopt three-tier benchmark stack in place of SPY-only benchmarking

## Status

Accepted on 2026-04-21. Operationally load-bearing as of commit
`c6fbcec` on `main`.

## Context

- [ADR-0004](/docs/adrs/ADR-0004-benchmark-spy.md) set SPY as the
  primary benchmark for Stage 1 and Stage 2.
- The
  [2026-04-20 capital-growth landscape review](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
  (SPEC-0013) established that SPY alone is insufficient for the goal
  of durable geometric growth. SPY is bull-biased in high-rate regimes
  and does not cover the *why not just buy the passive blend* test for
  a universe that already holds TLT.
- The benchmark-stack implementation was merged on 2026-04-21 at
  commit `c6fbcec` via the `feat/benchmark-stack-validation-reframe`
  branch (17 task-aligned commits plus 4 post-hoc fixes).

## Decision

The primary benchmark for Stage 1 and Stage 2 analysis is a
three-tier stack.

### Tier 1 — Hurdle (must-beat floor)

T-bill daily yield from the existing DGS3MO cache, materialized by
`CachedRiskFreeSeries` at
[src/tradingx/risk_free.py:36](/src/tradingx/risk_free.py:36) and
`build_default_risk_free_series` at
[:108](/src/tradingx/risk_free.py:108).

Strategy requirement: cumulative return over the validation window
must exceed the cumulative cash hurdle over the same window. Enforced
by the `hurdle_clearance` criterion at
[src/tradingx/validation.py:136](/src/tradingx/validation.py:136).

### Tier 2 — Opportunity cost (passive alternative)

60% SPY + 40% AGG, rebalanced monthly. Implemented by
`PassiveOpportunityCost` at
[src/tradingx/benchmark_stack.py:56](/src/tradingx/benchmark_stack.py:56).
AGG daily closes are sourced through the existing
`AlpacaMarketDataGateway.get_daily_close_series`.

Strategy requirement: CAGR must exceed the 60/40 blend CAGR by 2%
absolute over the validation window. Enforced by the
`opportunity_cost_edge` criterion at
[src/tradingx/validation.py:157](/src/tradingx/validation.py:157)
using the constant `GATE1_MIN_CAGR_EDGE = 0.02` at
[:42](/src/tradingx/validation.py:42).

### Tier 3 — Operating constraint (risk ceiling)

Rolling maximum drawdown and Conditional Drawdown-at-Risk (CDaR),
per Chekhlov-Uryasev-Zabarankin (2005):

- Design target: MDD ≤ 15%.
- Hard halt threshold: MDD ≤ 25%. Breach forces a stop-trading +
  operator-clearance cycle.
- CDaR threshold: ≤ 8% at 95% confidence.

Implemented by `OperatingConstraintBudget` in
[src/tradingx/types.py](/src/tradingx/types.py) and evaluated by
`evaluate_operating_constraint` at
[src/tradingx/validation.py:189](/src/tradingx/validation.py:189)
using `max_drawdown` and `conditional_drawdown_at_risk` at
[src/tradingx/stats.py:174](/src/tradingx/stats.py:174) onward.

### Composition

The three tiers are composed by `BenchmarkStack` at
[src/tradingx/benchmark_stack.py:134](/src/tradingx/benchmark_stack.py:134)
and exposed as `BenchmarkStackPayload` via the `materialize(...)`
method. The default factory `build_default_benchmark_stack` at
[src/tradingx/benchmark_stack.py:181](/src/tradingx/benchmark_stack.py:181)
wires all three tiers with the standard 60/40 weights and the
15%/25%/0.08/0.95 budget.

## Consequences

### Positive

- Evaluation is honest in high-rate regimes: strategies that ride
  beta must clear cash first and beat 60/40 second.
- Drawdown discipline is explicit: a 15% design target keeps the
  system defensive; a 25% hard halt ensures termination before
  capital-level damage.
- 60/40 as opportunity cost matches the realistic passive
  alternative and prevents a strategy from being credited for
  bond-rally beta that SPY alone would overlook.

### Negative

- A strategy that passed the SPY-relative gate may fail the
  three-tier stack in a high-rate regime. This is intentional: those
  strategies were false passes.
- AGG daily closes must now be fetched through Alpaca, adding one
  extra symbol to the data path.
- Legacy on-disk reports produced under the SPY-only regime are not
  directly comparable to new reports.
  [src/tradingx/web/readmodels.py](/src/tradingx/web/readmodels.py)
  maintains a transitional fallback for backward compatibility.

## Alternatives considered

- **Keep SPY as the sole benchmark.** Rejected because it fails the
  *why not just buy the passive blend* test and is bull-biased.
- **Use SPY as opportunity cost with cash as hurdle (no 60/40).**
  Rejected because the universe already includes TLT; crediting TLT
  beta without a bond-holding benchmark over-rewards beta exposure.
- **Use Calmar or Sortino as the hurdle instead of cash return.**
  Rejected because cash is the most universally comparable hurdle;
  Calmar and Sortino are derived metrics of the candidate series,
  not independent comparators.

## Supersedes

- [ADR-0004](/docs/adrs/ADR-0004-benchmark-spy.md) — SPY as the
  Stage 1 and Stage 2 benchmark.

## Sources

- SPEC-0013 Capital growth landscape
  ([docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)).
- Chekhlov, A., Uryasev, S., & Zabarankin, M. (2005).
  "Drawdown Measure in Portfolio Optimization."
- Moreira, A., & Muir, T. (2017). "Volatility-Managed Portfolios."
  *Journal of Finance.* https://www.nber.org/papers/w22208
- Implementation merged at commit `c6fbcec` on 2026-04-21.
