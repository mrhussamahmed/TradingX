---
id: PLAN-0003
title: TradingX operator platform implementation plan
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-014
---

# Implementation Plan: TradingX operator platform

**Branch**: `003-operator-platform` | **Date**: 2026-04-18 | **Spec**: `specs/003-operator-platform/spec.md`
**Input**: Feature specification from `/specs/003-operator-platform/spec.md`

## Summary

Upgrade the local control website into a production-grade local operator
platform. The backend will add richer read models, a normalized
operator-event timeline, replay and incident services, and bounded daily
session orchestration. The frontend will become a multi-view React
workspace with a command center, trade intelligence, research studio,
incident center, replay lab, and records explorer, while preserving the
local-only and read-only-by-default safety model.

## Technical Context

**Language/Version**: Python 3.11 for backend, TypeScript/React for frontend  
**Primary Dependencies**: `fastapi`, `pydantic`, `uvicorn`, `react`,
`vite`, `vitest`  
**Storage**: Existing artifact directories under `artifacts/`, new
operator-platform artifacts under `artifacts/operator_platform/`, docs
under `docs/`, config proposals under `config/proposals/`  
**Testing**: `pytest`, FastAPI contract tests, frontend tests,
`mypy --strict`, `ruff`, `black`, `./scripts/validate`  
**Target Platform**: Local machine or trusted local browser against a
FastAPI server bound to `127.0.0.1` by default  
**Project Type**: Single Python backend plus one local React SPA  
**Constraints**: local-only, read-only by default, no live trading,
polling-based refresh, no duplicate business logic in the browser  
**Scale/Scope**: One operator, one paper account, one local operator
surface

## Constitution Check

- `PASS` Principle I: the work adds visibility and bounded operator
  workflows without weakening risk controls.
- `PASS` Principle II: research and gate surfaces remain evidence-first
  and benchmark-relative.
- `PASS` Principle III: new backend and frontend behavior will be built
  through failing tests first.
- `PASS` Principle IV: errors stay fail-visible, secrets stay
  sanitized, and authoritative state remains repo/artifact backed.
- `PASS` Principle V: one local app plus one local SPA remain the
  simplest architecture that satisfies the request.
- `PASS` Principle VI and VII: no runtime self-modification and no live
  trading enablement paths are introduced.
- `PASS` Principle VIII through X: the new artifact chain is versioned,
  plan/spec separation remains clean, and the interface stays within the
  constitution’s local-web-app scope.

## Project Structure

### Documentation

```text
specs/003-operator-platform/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── operator_platform_api.md
└── tasks.md
```

### Source Code

```text
src/tradingx/
├── reporting.py
├── web/
│   ├── app.py
│   ├── readmodels.py
│   ├── runtime.py
│   ├── events.py
│   ├── sessions.py
│   └── replay.py
└── ...

webapp/src/
├── App.tsx
├── App.css
├── api.ts
├── types.ts
└── ...
```

## Delivery Phases

### Phase 2 — Operator-platform artifacts and backend contracts

- Add the spec chain, ADR, and API contract.
- Extend backend types for command-center, research, incident, replay,
  and session-digest payloads.
- Add failing tests for the new read models and endpoints.

### Phase 3 — Event, replay, and operations backend

- Build the normalized operator event timeline.
- Add session digest generation and incident acknowledgment persistence.
- Expose backend endpoints for command center, research, replay,
  incidents, explorer, and bounded daily actions.

### Phase 4 — Multi-view frontend workspace

- Replace the single-page dashboard with a multi-view operator workspace
  using richer charts and dense card layouts.
- Add polling refresh, search, filters, keyboard-first navigation, and
  action result feedback.

### Phase 5 — Validation, polish, and operator docs

- Expand automated tests across backend and frontend.
- Refresh docs, quickstarts, and state/index artifacts.
- Run full repo validation and verify the platform locally.
