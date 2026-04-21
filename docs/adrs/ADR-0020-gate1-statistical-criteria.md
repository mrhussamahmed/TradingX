---
id: ADR-0020
title: Tighten Gate 1 statistical criteria around deflated Sharpe and overfitting controls
version: 1.0.1
status: superseded
created: 2026-04-19
last_amended: 2026-04-21
supersedes: null
superseded_by: ADR-0022
author_session: SESS-2026-04-19-028
---

# ADR-0020: Tighten Gate 1 statistical criteria around deflated Sharpe and overfitting controls

## Status

Superseded on 2026-04-21 by
[ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md).
This ADR was never activated; the proposed criteria it contains were
reframed before taking effect in response to the
[2026-04-20 capital-growth landscape review](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md).
Key changes in ADR-0022 relative to this draft:

- Benchmarking is now three-tier (cash + 60/40 + operating constraint)
  per [ADR-0021](/docs/adrs/ADR-0021-benchmark-stack.md).
- The drawdown budget is reset to 15% design / 25% halt (was 10%/15%).
- PBO and CPCV are deferred from tranche 1 to tranche 2 hardening.
- A marginal-portfolio-contribution criterion is added for tranche 1's
  portfolio-construction milestone.

This ADR remains in the record for historical context only.

## Context

The 2026-04-19 external quant review found that the current Gate 1
criteria are too weak to distinguish real edge from backtest luck:

- a point Sharpe threshold by itself is vulnerable to noise and serial
  correlation
- multiple candidate families increase the chance of false positives
- the current repo has no formal probability-of-overfitting control
- walk-forward and profile-stability requirements need to stay tied to
  dated, leak-free return series

The codebase now has Lo-adjusted excess Sharpe, a real `DGS3MO`
risk-free cache, and the beginnings of a real daily-bar backtest path.
Gate 1 should graduate from raw point estimates to a statistical
standard that penalizes multiple testing and weak out-of-sample
behavior.

## Proposed decision

Until superseded, Gate 1 will require all of the following once the
validation pipeline is wired to the real backtest engine:

- point Sharpe `>= 1.0` net of costs as the hard pass threshold
- point Sharpe `>= 1.3` recorded separately as `north_star_met`, used
  for promotion preference rather than pass/fail
- Deflated Sharpe Ratio `>= 0.95`
- Probability of Backtest Overfitting `<= 0.30`
- max drawdown `<= 10%` design target and `<= 15%` hard live-halt
  threshold
- every rolling 1-year walk-forward window must keep Sharpe `>= 0.8`
  once the walk-forward implementation lands
- the settled profile-tolerance rule must pass separately on Sharpe,
  CAGR, and max drawdown:
  `|metric_OOS - metric_IS| / max(|metric_IS|, 0.3) <= 0.30`

During the transition, the existing Gate 1 criteria in `GATES-0001`
remain in force alongside these tighter criteria. A candidate passes
only if it passes both sets until this ADR is marked active and the
acceptance-gates artifact is amended.

## Consequences

### Positive

- Gate 1 shifts from "high backtest Sharpe" toward "high confidence that
  the Sharpe is real."
- Multiple testing becomes explicit instead of being hidden behind a
  nominal candidate count.
- A strategy can survive with `Sharpe >= 1.0` if the overfitting and
  walk-forward evidence is strong, while the `1.3` north-star still
  ranks preferred survivors.

### Negative

- The validation pipeline must add a trials ledger, PBO computation,
  walk-forward evaluation, and updated evidence artifacts before this
  ADR can be activated.
- Some strategies that pass the old point-threshold gate will fail the
  stronger statistical gate.
- The repo must track effective trial counts honestly, including failed
  and discarded runs.

## Alternatives considered

- Keep `Sharpe >= 1.3` as the hard pass threshold:
  rejected for now because once DSR, PBO, and walk-forward are in the
  gate, a weaker point threshold plus stronger statistical controls is a
  cleaner separation between acceptance and promotion preference.
- Keep the existing Gate 1 criteria unchanged:
  rejected because they do not account adequately for serial
  correlation, multiple testing, or overfitting.

## Sources

- `.specify/memory/constitution.md` (CONST-0001 v3.0.1), especially
  Principle II and Principle III.
- `docs/validation/acceptance_gates.md`
- [Lo, "The Statistics of Sharpe Ratios" (2002)](https://alo.mit.edu/topic/hedge-funds-and-asset-market-dynamics/page/3/)
  (retrieved 2026-04-19).
- [Bailey and López de Prado, "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality" (2014)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
  (retrieved 2026-04-19).
- [Bailey, Borwein, López de Prado, and Zhu, "The Probability of Backtest Overfitting" (2015)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
  (retrieved 2026-04-19).
