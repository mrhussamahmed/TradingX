---
id: ADR-0011
title: Use a normalized operator event timeline with polling refresh for the operator platform
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-014
---

# ADR-0011: Use a normalized operator event timeline with polling refresh for the operator platform

## Status

Accepted

## Context

The existing local website can read high-level snapshots, but the next
phase needs replay, trade explainability, incident timelines, research
drill-downs, and richer day-operations views. Those features all depend
on a coherent chronological model of what happened across service runs,
trade decisions, risk events, reconciliations, alerts, validation
artifacts, and operator actions.

The operator platform is local-only and single-user. It does not need
internet-scale fan-out or multi-user collaboration, but it does need
stable, low-complexity refresh behavior and one consistent event model.

## Decision

TradingX will:

- build a normalized operator event timeline from existing persisted
  artifacts and future operator-platform artifacts
- expose chart-ready and timeline-ready read models through FastAPI
- use short-interval polling from the local React SPA instead of adding
  a websocket or separate realtime service

## Consequences

### Positive

- replay, incident investigation, trade explainability, and artifact
  browsing can share one backend model
- local polling is simpler to test, easier to recover, and aligned with
  the repo's bias toward low operational complexity
- the browser stays a client of backend truth rather than inventing its
  own state model

### Negative

- updates are near-real-time rather than push-driven
- some timeline stitching logic becomes backend code that must be
  maintained carefully

## Alternatives considered

- `Websocket streaming`: rejected because it adds complexity without a
  demonstrated local-only need
- `Frontend-only aggregation`: rejected because it would duplicate
  backend truth and weaken replay/audit consistency
