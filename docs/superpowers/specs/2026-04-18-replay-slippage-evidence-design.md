---
id: DESIGN-0003
title: TradingX replay-slippage evidence design
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# TradingX replay-slippage evidence design

## Intent

Close the remaining Gate 3 slippage gap by generating a deterministic
replay-simulator cross-check from persisted paper execution context.

## Chosen approach

The phase keeps the replay model local and artifact-driven instead of
introducing a second simulator service. The system records enough market
context at execution time to replay expected fill quality later:

- reference price
- bid and ask quote
- 30-day average daily volume
- filled quantity and side

That persisted context feeds a deterministic replay-slippage engine that
writes trade-level replay artifacts plus a summary artifact used by Gate
3 reporting and the operator platform.

## Architecture

The backend remains one local Python service and one React SPA. The new
phase adds:

- richer execution-lifecycle persistence
- a replay-slippage engine and summary builder
- CLI and web actions for replay-slippage generation
- Gate 3 readiness integration for the replay-divergence criterion
- operator-platform cards for replay status and divergence details

## Evidence model

The new evidence chain is:

- `execution_lifecycles` with quote and liquidity context
- `replay_slippage_records` with paper-vs-replay execution comparisons
- `replay_slippage_summaries` with matched count, mean slippage values,
  and divergence ratio

Replay evidence is derived, persisted, and reusable. Gate 3 reporting
reads the latest summary instead of recalculating only in memory.

## Safety model

- replay generation stays local-only and does not touch live trading
- missing execution context degrades to explicit `pending`
- write-mode still gates website-triggered replay generation
- replay errors are sanitized and artifact-backed

## Testing shape

- backend unit tests for replay types, persistence, and divergence
  calculations
- API and runtime tests for replay generation and reporting endpoints
- frontend tests for the replay-slippage status surface
- full repo validation through `./scripts/validate`
