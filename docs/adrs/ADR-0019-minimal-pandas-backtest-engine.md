---
id: ADR-0019
title: Use a minimal pandas plus empyrical-reloaded backtest engine for Gate 1 research
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: ADR-0009
superseded_by: null
author_session: SESS-2026-04-19-028
---

# ADR-0019: Use a minimal pandas plus empyrical-reloaded backtest engine for Gate 1 research

## Status

Accepted on 2026-04-19.

## Context

The 2026-04-19 external quant review found that TradingX's strategy and
evaluation layer is not producing real evidence:

- `src/tradingx/strategy.py` synthesizes candidate returns by scaling
  `SPY` instead of running named strategies.
- `src/tradingx/evaluation.py` exposes a `NautilusReplayEvaluationAdapter`
  that never imports or calls Nautilus Trader.
- The current Gate 1 evaluation path operates on hand-shaped return
  tuples instead of a real backtest ledger.

`ADR-0009` selected Nautilus Trader on 2026-04-17 because backtest to
live parity sounded attractive. The repository has since demonstrated
that this direction is aspirational rather than implemented.

The constitution's Principle V requires the simplest approach that meets
requirements. For Gate 1 and Gate 2, the immediate requirements are:

- deterministic, leakage-aware daily-bar research
- cost-aware portfolio return generation
- auditable metric computation and stress tests
- benchmark-relative smoke checks that can fail loudly

The project does not yet need backtest/live code-path parity to satisfy
those requirements.

## Decision

Use a minimal event-driven backtest engine built on `pandas`,
`numpy`, and `empyrical-reloaded` for the Gate 1 and Gate 2 research
pipeline.

The engine will:

- operate on daily OHLCV bars with explicit timestamps
- consume signal series that only use information available through
  `t-1`
- apply portfolio construction, sizing, and cost models explicitly
- emit dated return series and trade ledgers that downstream statistics
  and evidence-pack builders can inspect directly
- support a benchmark-relative smoke gate where `SPY` buy-and-hold
  against `SPY` produces near-zero active return and the benchmark's
  actual drawdown over the same window

The engine is intentionally narrow. It is a research and validation
engine, not a live trading runtime.

## Consequences

### Positive

- The repo can replace synthetic candidate returns with real strategy
  outputs quickly.
- Risk, cost, and statistical calculations can share one dated return
  surface instead of reconstructing state from detached tuples.
- The implementation surface stays small enough to audit under the
  constitution's evidence-first standard.

### Negative

- Backtest and live paths will diverge structurally for now.
- A later stage may still choose to adopt a richer simulator once the
  strategy layer is real and paper trading produces trustworthy
  reference behavior.
- The repo must define its own minimal ledger and portfolio accounting
  conventions rather than inheriting them from a larger framework.

## Rejected alternatives

- Keep `ADR-0009` and finish wiring Nautilus now:
  rejected because the repo already shows that the dependency is not
  integrated, and finishing that integration would slow down the urgent
  work of restoring honest Gate 1 evidence.
- Continue with tuple-based synthetic evaluation:
  rejected because it cannot support real out-of-sample, cost, or regime
  analysis honestly.
- Jump directly to a live-parity framework before real strategies
  exist:
  rejected because that adds platform complexity ahead of the actual
  statistical bottleneck.

## Sources

- `.specify/memory/constitution.md` (CONST-0001 v3.0.1), especially
  Principle II, Principle III, and Principle V.
- `docs/adrs/ADR-0009-backtest-engine-nautilus-trader.md`
- `src/tradingx/strategy.py`
- `src/tradingx/evaluation.py`
- [empyrical-reloaded on PyPI](https://pypi.org/project/empyrical-reloaded/)
  (retrieved 2026-04-19)
