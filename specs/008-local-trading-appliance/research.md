---
id: RESEARCH-0008
title: TradingX local trading appliance research
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-022
---

# Research: TradingX local trading appliance

## Existing repo capabilities reused

- `AlpacaMarketDataGateway` already provides latest snapshots and daily
  bars from Alpaca.
- `PaperTradingLoopController` already owns the validated risk and
  execution path for one symbol.
- `PaperTradingService` already runs bounded service cycles across a
  universe.
- `LocalServiceManager` and `LocalSchedulerManager` already provide the
  local website pattern for background runtime control.
- Closed-trade, replay, and Gate 3 artifacts already exist and provide
  the raw material for post-trade analytics.

## Decision

Implement the local trading appliance as a supervised Python reference
slice that:

- formalizes runtime states
- adds governed activation and learning artifacts
- adds deterministic universe ranking before the existing loop
  controller
- exposes the new runtime through the existing website

This gives TradingX a production-grade operating model now without
pretending that a full physical microservice split can be delivered in
one session safely.

## Non-goals

- physical decomposition into Rust daemons in this phase
- cloud deployment or remote service discovery
- live trading enablement
- runtime auto-promotion of learned weights
- browser-owned trading decisions

