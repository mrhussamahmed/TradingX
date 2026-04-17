---
id: PLAN-0002
title: TradingX local control web app implementation plan
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-013
---

# Implementation Plan: TradingX local control web app

**Branch**: `002-local-control-web-app` | **Date**: 2026-04-17 | **Spec**: `specs/002-local-control-web-app/spec.md`
**Input**: Feature specification from `/specs/002-local-control-web-app/spec.md`

## Summary

Add a local-only website for TradingX using FastAPI plus a minimal React
SPA. The backend will expose read models over the existing artifact and
controller layers, plus a bounded set of write-mode actions. The
frontend will provide a polished operator cockpit with dashboards,
history browsers, gate/report tooling, and a config-proposal workspace.

## Technical Context

**Language/Version**: Python 3.11 for backend, TypeScript/React for frontend  
**Primary Dependencies**: `fastapi`, `uvicorn`, `pydantic`, `react`, `vite`, `vitest`, `playwright`  
**Storage**: Existing local artifact stores under `artifacts/`, docs under `docs/`, config proposals under `config/proposals/`, frontend static assets built into the repo workspace  
**Testing**: `pytest`, browser/API tests, frontend unit tests, `mypy --strict`, `ruff`, `black`, `./scripts/validate`  
**Target Platform**: Local machine or private-network browser against a FastAPI server bound to `127.0.0.1` by default  
**Project Type**: Python backend plus local React SPA served by the same app  
**Constraints**: Read-only by default, write actions opt-in via config flag, no live-trading enablement, no direct runtime risk-limit mutation, local-only binding, no public cloud hosting  
**Scale/Scope**: One operator, one local site, one bounded backend process, no multi-user auth model

## Constitution Check

- `PASS` Principle I: no risk controls are weakened, and dangerous
  mutations remain out of scope.
- `PASS` Principle II: the website surfaces evidence; it does not invent
  success claims.
- `PASS` Principle III: backend routes, action guards, and UI behavior
  will be implemented with TDD.
- `PASS` Principle IV: the site is artifact-driven, fail-visible, and
  bounded by existing repo truths.
- `PASS` Principle V: one local app and one local SPA are justified by
  the operator request and the constitution's local-web-app allowance.
- `PASS` Principle VI and VII: the UI cannot self-modify the bot or
  enable live trading.
- `PASS` Principle VIII through X: the work adds versioned artifacts,
  stays within local-web-app scope, and leaves Telegram/Grafana roles
  intact.

## Project Structure

### Documentation

```text
specs/002-local-control-web-app/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── web_app_api.md
└── tasks.md
```

### Source Code

```text
src/tradingx/
├── web/
│   ├── __init__.py
│   ├── app.py
│   ├── api.py
│   ├── actions.py
│   ├── readmodels.py
│   ├── service_manager.py
│   └── config_workspace.py
├── reporting.py
└── ...

webapp/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api.ts
│   ├── theme.css
│   ├── components/
│   └── views/
└── tests/
```

## Delivery Phases

### Phase 2 — Web foundations

- Add backend web config, API schemas, read models, and service-manager
  boundaries.
- Add frontend toolchain, shared API client, and base shell.

### Phase 3 — Read-only operator cockpit

- Build overview dashboard, evidence browser, gate browser, and project
  record browser.
- Serve the SPA through FastAPI and provide local dev/build commands.

### Phase 4 — Bounded write actions

- Add write-mode guardrails and safe action endpoints for paper-service
  control, recovery, benchmark prep, gate reports, and decision reports.
- Add config-proposal composition without live mutation.

### Phase 5 — Validation and polish

- Add browser tests, responsive checks, docs, CI/validation integration,
  and operator quickstart verification.
