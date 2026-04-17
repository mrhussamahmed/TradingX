---
id: ADR-0002
title: Use uv as the package manager
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-001
---

# ADR-0002: Use uv as the package manager

## Status

Accepted.

## Context

- `docs/archive/implementation_constraints.md` requires choosing either
  `uv` or `poetry` in Phase 0 and forbids mixing package managers.
- Phase 0 needs a fast way to install lint, type-check, test, and Alpaca
  dependencies for both local execution and CI.
- `uv` is available in the local environment in this session.

## Decision

Use `uv` as the sole Python package manager for dependency resolution,
tool execution, and environment synchronization.

## Consequences

- Project commands in CI, validation scripts, and documentation use `uv`.
- `poetry` files are intentionally absent unless a future ADR supersedes
  this decision.
- Dependency changes will be expressed through `pyproject.toml` and `uv`.
