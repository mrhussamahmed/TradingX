---
id: ADR-0013
title: Use persisted execution context to generate replay-slippage cross-check evidence
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# ADR-0013: Use persisted execution context to generate replay-slippage cross-check evidence

## Status

Accepted

## Context

Gate 3 requires a replay-simulator cross-check so Alpaca paper fills can
be compared against a quantity-aware slippage model. The repository now
persists paper execution-lifecycle records, but the replay-slippage
criterion remains pending because no replay evidence is generated from
those records yet.

TradingX already has the key market inputs at execution time:

- reference price
- bid and ask quote
- 30-day average daily volume
- filled quantity

Building a replay cross-check by fetching historical intraday market
data for every paper execution would add a more fragile and network-heavy
path than the current local artifact model needs.

## Decision

TradingX will:

- extend execution-lifecycle artifacts with the quote and liquidity
  inputs needed for replay
- generate replay-slippage records from persisted execution context
  using a deterministic quantity-aware model
- persist replay summaries as validation artifacts
- evaluate the Gate 3 replay-divergence criterion from those persisted
  replay summaries
- expose replay-slippage generation and status through the CLI and local
  website

## Consequences

### Positive

- replay-slippage evidence becomes reproducible from repo artifacts
- Gate 3 can evaluate the replay-divergence criterion without another
  external service
- the local website can show paper-vs-replay slippage directly

### Negative

- execution artifacts become richer and must remain backward-compatible
- older executions that lack quote or liquidity fields may still leave
  the replay criterion pending until newer evidence exists

## Alternatives considered

- `Fetch historical intraday data per execution`: rejected because it
  adds a heavier external dependency path and weaker reproducibility
- `Compute divergence only from paper fills`: rejected because it does
  not satisfy the replay-simulator requirement
- `Run replay logic only in the UI`: rejected because it would weaken
  auditability and create a second source of truth
