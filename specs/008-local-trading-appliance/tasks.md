---
id: TASKS-0008
title: TradingX local trading appliance task list
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-022
---

# Tasks: TradingX local trading appliance

**Input**: Design documents from `/specs/008-local-trading-appliance/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`

## Phase 1: Artifact chain and failing tests

- [ ] T001 Add the local trading appliance artifact chain and update index tracking
- [ ] T002 [P] Add failing type and persistence tests for warmup, activation, selection, snapshot, and proposal records
- [ ] T003 [P] Add failing tests for runtime-host startup states and fail-closed transitions
- [ ] T004 [P] Add failing tests for deterministic opportunity ranking, threshold handling, and tie-breaks
- [ ] T005 [P] Add failing tests for learning proposal significance gating
- [ ] T006 [P] Add failing API, web-runtime, and frontend tests for runtime-host state and actions

## Phase 2: Runtime and intelligence slice

- [ ] T007 Implement activation, snapshot, and proposal types plus persistence helpers
- [ ] T008 Implement quant helpers and historical warmup service
- [ ] T009 Implement deterministic opportunity ranking and persisted selection records
- [ ] T010 Implement runtime host start/stop/state transitions and CLI entry points
- [ ] T011 Implement learning proposal generation from closed-trade artifacts

## Phase 3: Website integration

- [ ] T012 Implement runtime-host manager support and web actions
- [ ] T013 Implement runtime-host read models and FastAPI routes
- [ ] T014 Implement runtime-host controls, summaries, and intelligence cards in the React app

## Phase 4: Validation and delivery

- [ ] T015 Update README, operator manual, and quickstart documentation for the appliance workflow
- [ ] T016 Run backend tests, frontend tests, build verification, and full repo validation
- [ ] T017 Update state, index, and session handover artifacts, then promote the branch into `main`
