---
id: PLAN-0008
title: TradingX local trading appliance implementation plan
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-022
---

# Implementation Plan: TradingX local trading appliance

**Branch**: `codex/local-trading-appliance` | **Date**: 2026-04-19 | **Spec**: `specs/008-local-trading-appliance/spec.md`
**Input**: Feature specification from `/specs/008-local-trading-appliance/spec.md`

## Summary

Implement a supervised local trading appliance above the existing
TradingX runtime. Add a runtime-host state machine, governed activation
records, historical warmup, deterministic opportunity selection,
statistical learning proposals, and a website control surface that can
start and stop the bot safely.

## Technical Context

**Language/Version**: Python 3.11 for backend, TypeScript/React for frontend
**Primary Dependencies**: existing `alpaca-py`, `fastapi`, `uvicorn`,
`react`, `vite`, `vitest`; no new framework dependency required
**Storage**: existing artifact store under `artifacts/`, extended with
`operator_platform/runtime_host/`, `operator_platform/activations/`,
`operator_platform/model_snapshots/`, `operator_platform/model_weight_proposals/`,
and `operator_platform/opportunity_selections/`
**Testing**: `pytest`, FastAPI contract tests, frontend tests,
`mypy --strict`, `ruff`, `black`, `./scripts/validate`
**Target Platform**: Local machine and local browser only
**Project Type**: Single Python backend plus one local React SPA with a
supervised local runtime host
**Constraints**: local-only, read-only by default, no live trading,
fail-closed startup, no runtime self-modification, deterministic
selection and artifact trail
**Scale/Scope**: One operator, one paper account, one supervised local
trading runtime

## Constitution Check

- `PASS` Principle I: the phase strengthens startup safety,
  activation governance, and fail-closed behavior.
- `PASS` Principle II: learning remains proposal-only and does not claim
  edge without artifacts.
- `PASS` Principle III: runtime host, warmup, ranking, learning, API,
  and UI behavior will be added through failing tests first.
- `PASS` Principle IV: startup state, activation, ranking, and proposal
  artifacts make reasoning explicit and auditable.
- `PASS` Principle V: the design reuses the existing Alpaca, service,
  web, and artifact infrastructure instead of introducing external
  orchestration.
- `PASS` Principle VI and VII: no self-modifying live behavior and no
  live trading enablement are introduced.
- `PASS` Principle VIII through X: the phase is fully artifact-backed,
  local-only, and within existing interface bounds.

## Project Structure

### Documentation

```text
specs/008-local-trading-appliance/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── local_trading_appliance_api.md
└── tasks.md
```

### Source Code

```text
src/tradingx/
├── __main__.py
├── config.py
├── controller.py
├── persistence.py
├── service.py
├── types.py
├── runtime_host.py
├── opportunity.py
├── learning.py
├── quant.py
├── historical.py
├── activation.py
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

### Phase 1 — Artifact chain and failing tests

- Add the local trading appliance artifact chain and ADR.
- Add failing tests for new types, persistence, and runtime-host state
  transitions.
- Add failing tests for historical warmup, opportunity selection, and
  learning proposals.
- Add failing API, web-runtime, and frontend tests for runtime-host
  state and controls.

### Phase 2 — Governed runtime core

- Implement activation records, model snapshots, and deterministic
  fallback behavior.
- Implement the historical warmup service and quant helpers.
- Implement deterministic opportunity ranking and selection artifacts.
- Implement the runtime host and CLI entry point.

### Phase 3 — Website operator surface

- Extend the web runtime with a runtime-host manager.
- Expose runtime-host, warmup, activation, selection, and proposal
  read/write routes.
- Add the runtime-host panel to the website.

### Phase 4 — Learning and delivery

- Implement post-trade learning proposals from closed-trade artifacts.
- Update README and operator manual for the new primary workflow.
- Run repo validation, update state/index/handover artifacts, and
  prepare promotion into `main`.
