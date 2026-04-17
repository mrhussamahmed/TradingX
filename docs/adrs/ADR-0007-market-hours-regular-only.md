---
id: ADR-0007
title: Restrict Stage 1 and Stage 2 trading to regular market hours
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-001
---

# ADR-0007: Restrict Stage 1 and Stage 2 trading to regular market hours

## Status

Accepted.

## Context

- `.specify/memory/constitution.md` makes regular US equity market hours
  the only supported trading window for Stage 1 and Stage 2.
- `docs/archive/implementation_constraints.md` explicitly excludes
  pre-market and after-hours trading.
- Extended-hours trading introduces thinner liquidity and wider spreads,
  which conflicts with the Phase 0 paper-first walking skeleton scope.

## Decision

Restrict Stage 1 and Stage 2 trading logic to regular US equity market
hours only. Extended-hours trading remains out of scope unless a future
ADR explicitly enables it.

## Consequences

- Phase 0 smoke tests and controller logic use regular-hours settings only.
- No extended-hours order flags are introduced into the initial code path.
- Any future expansion into extended-hours trading requires a superseding ADR.
