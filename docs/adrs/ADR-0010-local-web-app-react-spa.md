---
id: ADR-0010
title: Use FastAPI plus a minimal React SPA for the local control web app
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-013
---

# ADR-0010: Use FastAPI plus a minimal React SPA for the local control web app

## Context

- `.specify/memory/constitution.md` permits the local control and
  configuration web app to use either `FastAPI + HTMX` or `FastAPI + a
  minimal SPA`, while requiring the app to remain local-only,
  read-only by default, and bounded by the config-commit-reload safety
  path.
- `docs/archive/implementation_constraints.md` pins the selection point
  for the local web app stack to Phase 3 and forbids Electron, Tauri,
  native mobile apps, and cloud-hosted control planes.
- The operator explicitly requested a feature-rich, visually pleasant
  local website with dashboards and controls, which pushes the design
  toward richer client-side state and charting than the current CLI
  surfaces provide.

## Decision

Use a single-process local web application built from:

- `FastAPI` for the HTTP and JSON API layer
- a minimal `React` single-page application for the local browser UI
- static asset serving from the same local FastAPI process in production
- local-only binding (`127.0.0.1` by default)

The React app remains intentionally small: one SPA, one API surface, no
separate auth system, no cloud services, and no client-side logic that
duplicates trading, risk, or gate-evaluation rules.

## Consequences

### Positive

- Supports a denser, more polished operator cockpit with dashboards,
  filters, drill-downs, and bounded controls.
- Keeps all authoritative trading logic on the backend while allowing a
  smoother local UI than a server-rendered control plane alone.
- Cleanly maps to the constitution's three-interface model:
  dashboards stay local, Telegram stays narrow, and no public control
  plane is introduced.

### Negative

- Adds a JavaScript build toolchain and browser-test surface to a repo
  that was previously Python-only.
- Requires CI and validation to cover frontend build, tests, and static
  asset integration.

### Guardrails

- The SPA is read-only by default.
- Write actions are disabled unless the dedicated web write-mode flag is
  enabled.
- The UI never enables live trading, mutates live configuration
  directly, or changes runtime risk limits outside the approved
  config-proposal workflow.
