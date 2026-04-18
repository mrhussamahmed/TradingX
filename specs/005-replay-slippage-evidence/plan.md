---
id: PLAN-0005
title: TradingX replay-slippage evidence implementation plan
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# Implementation Plan: TradingX replay-slippage evidence

**Branch**: `005-replay-slippage-evidence` | **Date**: 2026-04-18 | **Spec**: `specs/005-replay-slippage-evidence/spec.md`  
**Input**: Feature specification from `/specs/005-replay-slippage-evidence/spec.md`

## Summary

Add the replay-slippage evidence layer required to close the final Gate
3 slippage criterion. The backend will enrich execution artifacts with
quote and liquidity context, generate deterministic replay-slippage
records and summary artifacts, wire the result into Gate 3 readiness,
and expose replay status and generation controls through the CLI and
website.

## Technical Context

**Language/Version**: Python 3.11 for backend, TypeScript/React for frontend  
**Primary Dependencies**: existing `fastapi`, `pydantic`, `uvicorn`,
`react`, `vite`, `vitest`; no new framework dependency required  
**Storage**: existing artifact directories under `artifacts/`, plus new
validation artifacts for replay-slippage records and summaries  
**Testing**: `pytest`, FastAPI contract tests, frontend tests,
`mypy --strict`, `ruff`, `black`, `./scripts/validate`  
**Target Platform**: Local machine and local browser only  
**Project Type**: Single Python backend plus one local React SPA  
**Constraints**: local-only, read-only by default, no live trading,
artifact-backed truth, bounded actions only  
**Scale/Scope**: One operator, one paper account, one replay evidence
set derived from paper executions

## Constitution Check

- `PASS` Principle I: the phase strengthens paper-trading validation
  without weakening live-disable protections.
- `PASS` Principle II: replay status remains evidence-first and fails
  closed to `pending` when execution context is insufficient.
- `PASS` Principle III: backend, API, and UI work will be added through
  failing tests first.
- `PASS` Principle IV: the replay engine is deterministic, local, and
  explicit about missing data instead of inventing a result.
- `PASS` Principle V: the implementation extends the current artifact
  model and website rather than adding another service.
- `PASS` Principle VI and VII: no self-modifying logic and no live
  trading enablement are introduced.
- `PASS` Principle VIII through X: the phase is fully versioned,
  documented, and compatible with the current artifact chain.

## Project Structure

### Documentation

```text
specs/005-replay-slippage-evidence/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── replay_slippage_api.md
└── tasks.md
```

### Source Code

```text
src/tradingx/
├── replay_slippage.py
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

- Add the replay-slippage artifact chain and ADR.
- Add failing backend tests for new types, persistence, and replay
  divergence logic.
- Add failing API, runtime, and frontend tests for replay generation and
  replay status rendering.

### Phase 3 — Replay evidence engine

- Enrich execution-lifecycle records with quote and liquidity context.
- Implement replay-slippage record and summary generation.
- Add the CLI workflow and Gate 3 readiness integration.

### Phase 4 — Website integration

- Expose replay-slippage reads and write actions through FastAPI.
- Add replay-slippage status and refresh controls to the Gate 3 website
  surface.

### Phase 5 — Validation and delivery

- Update docs and quickstarts.
- Run repo validation and browser-facing checks.
- Update state, index, and session handover artifacts.
