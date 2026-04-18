---
id: RESEARCH-0005
title: TradingX replay-slippage evidence research
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# Research: TradingX replay-slippage evidence

## Decision

Generate replay-slippage evidence from persisted execution context
rather than from a new network-backed replay service.

## Why this approach

- the paper loop already has the quote and liquidity context needed for
  a bounded replay approximation
- persisted inputs make replay evidence reproducible and auditable
- the website and Gate 3 readiness can reuse persisted replay summaries
  instead of re-running logic ad hoc

## Rejected alternatives

### Historical intraday fetch per execution

Rejected because it would make replay evidence more dependent on
external API availability and historical lookup paths than the current
artifact-first repo model requires.

### UI-only replay calculation

Rejected because it would weaken auditability and create a second source
of truth.

## Implementation notes

- replay should use signed slippage per side but assess divergence from
  absolute slippage magnitudes
- replay evidence should be idempotent for the same execution inputs
- older executions without required context should degrade to `pending`
  rather than being backfilled with guessed quote data
