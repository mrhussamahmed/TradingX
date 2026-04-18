---
id: PLAN-0007
title: TradingX recurring market-day scheduler implementation plan
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-020
---

# Implementation Plan: TradingX recurring market-day scheduler

**Branch**: `007-market-day-scheduler` | **Date**: 2026-04-18 | **Spec**: `specs/007-market-day-scheduler/spec.md`
**Input**: Feature specification from `/specs/007-market-day-scheduler/spec.md`

## Summary

Add a recurring scheduler that uses the Alpaca regular-hours calendar to
launch the existing market-day runner automatically on each trading day.
The backend will persist schedule records, compute next-run timing,
prevent duplicate same-day launches, and expose scheduler controls
through CLI and the local website.

## Technical Context

**Language/Version**: Python 3.11 for backend, TypeScript/React for frontend
**Primary Dependencies**: existing `alpaca-py`, `fastapi`, `pydantic`,
`uvicorn`, `react`, `vite`, `vitest`; no new framework dependency
required
**Storage**: existing artifact directories under `artifacts/`, plus new
`operator_platform/market_day_schedules/` records
**Testing**: `pytest`, FastAPI contract tests, frontend tests,
`mypy --strict`, `ruff`, `black`, `./scripts/validate`
**Target Platform**: Local machine and local browser only
**Project Type**: Single Python backend plus one local React SPA
**Constraints**: local-only, read-only by default, no live trading,
calendar-driven scheduling, persisted audit trail, bounded web actions
only
**Scale/Scope**: One operator, one paper account, one recurring
scheduler for the existing market-day runner

## Constitution Check

- `PASS` Principle I: the phase adds operational discipline without
  weakening paper-only or risk controls.
- `PASS` Principle II: scheduling only automates evidence generation; it
  does not claim readiness without artifacts.
- `PASS` Principle III: scheduler behavior, persistence, API, and UI
  flows will be added through failing tests first.
- `PASS` Principle IV: schedule records will make waiting, running,
  duplicate prevention, and failures explicit.
- `PASS` Principle V: the design reuses the existing calendar,
  automation runner, CLI, and web runtime instead of adding an external
  scheduler dependency.
- `PASS` Principle VI and VII: no self-modifying behavior and no live
  trading enablement are introduced.
- `PASS` Principle VIII through X: the phase remains versioned,
  artifact-backed, local-only, and within current interface bounds.

## Project Structure

### Documentation

```text
specs/007-market-day-scheduler/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── market_day_scheduler_api.md
└── tasks.md
```

### Source Code

```text
src/tradingx/
├── scheduler.py
├── __main__.py
├── config.py
├── data.py
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

- Add the recurring scheduler artifact chain and ADR.
- Add failing type, persistence, and scheduler unit tests.
- Add failing API, web-runtime, and frontend tests for scheduler state
  and start/stop flows.

### Phase 3 — Calendar-driven scheduler core

- Extend the regular-hours calendar with current-or-next-session lookup.
- Implement the recurring scheduler and schedule-record persistence.
- Add CLI entry points for bounded and long-running scheduler usage.

### Phase 4 — Website scheduler surface

- Add runtime manager support for background scheduler control.
- Expose scheduler state and latest schedule history through FastAPI
  routes.
- Add scheduler cards and controls to the `Gate 3 Ops` view.

### Phase 5 — Validation and delivery

- Update README and quickstart docs for unattended scheduling.
- Run repo validation and browser-facing checks.
- Update state, index, and session handover artifacts.
