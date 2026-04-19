---
id: ADR-0009
title: Use Nautilus Trader as the backtest engine
version: 1.0.0
status: superseded
created: 2026-04-17
last_amended: 2026-04-19
supersedes: null
superseded_by: ADR-0019
author_session: SESS-2026-04-19-028
---

# ADR-0009: Use Nautilus Trader as the backtest engine

## Status

Superseded on 2026-04-19 by `ADR-0019`.

## Context

`implementation_constraints.md` allows exactly two backtest-engine
choices for this project: Nautilus Trader or VectorBT PRO. Phase 1 must
select one in an ADR before later implementation phases depend on it.

TradingX needs more than fast research. The chosen engine must fit a
repo-first project that values deterministic, auditable movement from
research through paper execution and, only much later, possible live
readiness.

## Decision

Use Nautilus Trader as the project's backtest and replay engine.

## Rationale

Nautilus Trader's official documentation emphasizes the same event-
driven architecture for backtesting and live deployment, plus official
Python 3.11 through 3.13 support in the current installation guide. That
lines up with the repo's Python baseline and with the constitution's
desire to minimize divergence between research, paper execution, and any
future live-readiness work.

VectorBT PRO's official materials present a strong, high-performance
research environment, but they also frame the product around proprietary
subscriber access and vectorized research workflows. That is useful, but
it is a weaker fit for TradingX's current priority: research-to-paper
parity inside a versioned, auditable codebase.

This recommendation is an inference from the official materials, not a
claim that VectorBT PRO is generally inferior.

## Consequences

### Positive

- The project gets one primary engine whose official positioning favors
  backtest-to-live parity.
- The choice stays compatible with the repo's Python 3.11 baseline.
- Future replay, execution-model, and state-reconciliation work can use
  one consistent event-driven abstraction.

### Negative

- Nautilus Trader introduces a larger platform surface than a purely
  vectorized research library.
- The team will need to learn Nautilus-specific configuration and data
  catalog patterns before Phase 5.

## Alternatives considered

### VectorBT PRO

Rejected as the primary engine because the official materials emphasize
proprietary, research-first workflows more than research-to-live parity.

### Build a custom backtest engine

Rejected by the implementation constraints unless the approved engines
prove inadequate.

## Sources

- Nautilus Trader overview:
  [https://nautilustrader.io/docs/latest/](https://nautilustrader.io/docs/latest/)
  (retrieved 2026-04-17)
- Nautilus Trader installation guide:
  [https://nautilustrader.io/docs/latest/getting_started/installation](https://nautilustrader.io/docs/latest/getting_started/installation)
  (retrieved 2026-04-17)
- Nautilus Trader live-trading concept:
  [https://nautilustrader.io/docs/latest/concepts/live/](https://nautilustrader.io/docs/latest/concepts/live/)
  (retrieved 2026-04-17)
- VectorBT PRO getting started:
  [https://vectorbt.pro/](https://vectorbt.pro/) (retrieved 2026-04-17)
- VectorBT PRO portfolio features:
  [https://vectorbt.pro/features/portfolio/](https://vectorbt.pro/features/portfolio/)
  (retrieved 2026-04-17)
