---
id: PLAN-0006
title: TradingX market-day automation implementation plan
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-018
---

# Implementation Plan: TradingX market-day automation

**Branch**: `006-market-day-automation` | **Date**: 2026-04-18 | **Spec**: `specs/006-market-day-automation/spec.md`  
**Input**: Feature specification from `/specs/006-market-day-automation/spec.md`

## Summary

Add a dedicated market-day automation runner that orchestrates the
existing paper service, replay-slippage refresh, Gate 3 reporting, and
daily digests into one bounded workflow. The backend will persist
automation-run artifacts and expose the workflow through CLI and web
actions. The operator platform will gain an automation surface that
shows run status, checkpoints, and evidence freshness.

## Technical Context

**Language/Version**: Python 3.11 for backend, TypeScript/React for frontend  
**Primary Dependencies**: existing `fastapi`, `pydantic`, `uvicorn`,
`react`, `vite`, `vitest`; no new framework dependency required  
**Storage**: existing artifact directories under `artifacts/`, plus new
`operator_platform/market_automation_runs/` records  
**Testing**: `pytest`, FastAPI contract tests, frontend tests,
`mypy --strict`, `ruff`, `black`, `./scripts/validate`  
**Target Platform**: Local machine and local browser only  
**Project Type**: Single Python backend plus one local React SPA  
**Constraints**: local-only, read-only by default, no live trading,
explicit evidence artifacts, bounded actions only  
**Scale/Scope**: One operator, one paper account, one local automation
workflow

## Constitution Check

- `PASS` Principle I: the phase improves operational discipline without
  weakening paper-only controls.
- `PASS` Principle II: automation writes evidence and reports current
  readiness; it does not claim readiness without artifacts.
- `PASS` Principle III: orchestration, API, and UI behavior will be
  added through failing tests first.
- `PASS` Principle IV: market-closed and insufficient-evidence cases are
  explicit statuses, not silent success.
- `PASS` Principle V: the design reuses existing service, replay, Gate
  3, and web layers instead of adding another app or daemon framework.
- `PASS` Principle VI and VII: no self-modifying behavior and no live
  trading enablement are introduced.
- `PASS` Principle VIII through X: the feature remains fully versioned,
  artifact-backed, local-only, and within the current interface bounds.

## Project Structure

### Documentation

```text
specs/006-market-day-automation/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── market_day_automation_api.md
└── tasks.md
```

### Source Code

```text
src/tradingx/
├── automation.py
├── __main__.py
├── config.py
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

- Add the market-day automation artifact chain and ADR.
- Add failing backend tests for automation run records and
  orchestration.
- Add failing API and frontend tests for automation read/write flows.

### Phase 3 — Core automation runner

- Implement the market-day automation runner and persisted run
  artifacts.
- Add CLI entry points for bounded full-run automation.
- Upgrade session actions to use the real automation runner.

### Phase 4 — Website automation surface

- Expose automation read models and write-mode actions.
- Add automation status, history, and controls to the operator
  platform.

### Phase 5 — Validation and delivery

- Update docs and quickstarts.
- Run repo validation and browser-facing checks.
- Update state, index, and session handover artifacts.
