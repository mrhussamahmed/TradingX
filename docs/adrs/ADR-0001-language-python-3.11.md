---
id: ADR-0001
title: Use Python 3.11 as the baseline runtime
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-001
---

# ADR-0001: Use Python 3.11 as the baseline runtime

## Status

Accepted.

## Context

- `.specify/memory/constitution.md` pins Python 3.11 or later for the
  research, orchestration, and trading code paths.
- `docs/archive/implementation_constraints.md` repeats that constraint
  and requires a single runtime across local development, Docker, and CI.
- Phase 0 needs one baseline runtime for packaging, linting, type
  checking, and the Alpaca paper-trading walking skeleton.

## Decision

The project baseline is Python 3.11. Repository metadata, Docker, CI,
and local commands target Python 3.11 first. Newer Python versions may
be used locally only if they remain compatible with the 3.11 baseline.

## Consequences

- Dependency and typing choices must remain compatible with Python 3.11.
- Docker and GitHub Actions use Python 3.11 images/runtimes.
- Future runtime changes require a superseding ADR plus operator approval.
