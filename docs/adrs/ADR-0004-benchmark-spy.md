---
id: ADR-0004
title: Use SPY as the Stage 1 and Stage 2 benchmark
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-001
---

# ADR-0004: Use SPY as the Stage 1 and Stage 2 benchmark

## Status

Accepted.

## Context

- `.specify/memory/constitution.md` sets SPY as the primary benchmark
  for Stage 1 and Stage 2.
- `docs/archive/project_brief.md` defines success in benchmark-relative,
  risk-adjusted terms rather than raw return alone.
- `docs/archive/implementation_constraints.md` repeats SPY as the pinned
  benchmark and requires dividend-adjusted comparisons.

## Decision

Use SPY as the primary benchmark for Stage 1 and Stage 2 analysis,
reporting, and validation artifacts.

## Consequences

- Validation outputs must include SPY-relative metrics.
- Phase 1 strategy evaluation compares candidates against SPY on a
  risk-adjusted basis, not only on absolute return.
- A future benchmark change requires a superseding ADR.
