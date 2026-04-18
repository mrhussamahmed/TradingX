---
id: PLAN-0004
title: TradingX Gate 3 operations and evidence implementation plan
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-016
---

# Implementation Plan: TradingX Gate 3 operations and evidence

**Branch**: `004-gate3-operations-evidence` | **Date**: 2026-04-18 | **Spec**: `specs/004-gate3-operations-evidence/spec.md`  
**Input**: Feature specification from `/specs/004-gate3-operations-evidence/spec.md`

## Summary

Add the operational evidence layer required for Gate 3. The backend
will persist execution-lifecycle, closed-trade, drill, and market
session artifacts; compute Gate 3 readiness and promotion packages; and
expose those capabilities through CLI and FastAPI. The operator
platform will gain a dedicated readiness surface and daily-operations
panel that stays truthful when evidence is incomplete.

## Technical Context

**Language/Version**: Python 3.11 for backend, TypeScript/React for frontend  
**Primary Dependencies**: existing `fastapi`, `pydantic`, `uvicorn`,
`react`, `vite`, `vitest`; no new framework dependency required  
**Storage**: existing artifact directories under `artifacts/`, plus new
paper-loop and operator-platform subdirectories for Gate 3 evidence  
**Testing**: `pytest`, FastAPI contract tests, frontend tests,
`mypy --strict`, `ruff`, `black`, `./scripts/validate`  
**Target Platform**: Local machine and local browser only  
**Project Type**: Single Python backend plus one local React SPA  
**Constraints**: local-only, read-only by default, no live trading,
explicit evidence artifacts, bounded actions only  
**Scale/Scope**: One operator, one paper account, one local evidence
surface

## Constitution Check

- `PASS` Principle I: the phase hardens paper operations and evidence
  without weakening live-disable protections.
- `PASS` Principle II: readiness stays evidence-first and benchmark or
  expectation relative where reference data exists.
- `PASS` Principle III: backend, API, and UI work will be added through
  failing tests first.
- `PASS` Principle IV: missing evidence becomes explicit `pending`
  state, not silent inference.
- `PASS` Principle V: the implementation extends existing persistence,
  CLI, and web layers instead of adding another service.
- `PASS` Principle VI and VII: no self-modifying logic and no live
  trading enablement are introduced.
- `PASS` Principle VIII through X: the feature is fully versioned,
  artifact-backed, and documented with spec, plan, contracts, and
  handover updates.

## Project Structure

### Documentation

```text
specs/004-gate3-operations-evidence/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── gate3_operations_api.md
└── tasks.md
```

### Source Code

```text
src/tradingx/
├── gate3.py
├── controller.py
├── persistence.py
├── types.py
├── web/
│   ├── app.py
│   ├── readmodels.py
│   └── runtime.py
└── ...

webapp/src/
├── App.tsx
├── api.ts
├── types.ts
└── ...
```

## Delivery Phases

### Phase 2 — Artifact chain and failing tests

- Add the Gate 3 artifact chain and ADR.
- Add failing backend tests for new types, persistence, and readiness
  rollups.
- Add failing API and frontend tests for readiness and day-operations
  flows.

### Phase 3 — Core Gate 3 evidence engine

- Persist execution-lifecycle, closed-trade, drill, and market-session
  artifacts.
- Implement Gate 3 readiness and promotion-package builders.
- Add CLI commands for report generation and drills.

### Phase 4 — Web readiness surface

- Expose new FastAPI endpoints and write-mode actions.
- Add Gate 3 readiness, drill history, and daily-operations cards to
  the operator platform.

### Phase 5 — Validation and delivery

- Update docs and quickstarts.
- Run repo validation and browser-facing checks.
- Update state, index, and session handover artifacts.
