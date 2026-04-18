---
id: TASKS-0006
title: TradingX market-day automation task list
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-018
---

# Tasks: TradingX market-day automation

**Input**: Design documents from `/specs/006-market-day-automation/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`

## Phase 1: Artifact chain and failing tests

- [ ] T001 Add the market-day automation artifact chain and update index tracking
- [ ] T002 [P] Add failing type and persistence tests for market-automation run records
- [ ] T003 [P] Add failing automation-runner and CLI parser tests
- [ ] T004 [P] Add failing API-contract and web-runtime tests for automation reads and actions
- [ ] T005 [P] Add failing frontend tests for the automation controls and status surface

## Phase 2: Core automation runner

- [ ] T006 Implement market-automation types and persistence helpers
- [ ] T007 Implement the dedicated automation runner and bounded run result
- [ ] T008 Implement CLI market-day automation entry points
- [ ] T009 Upgrade session actions to execute the real automation steps

## Phase 3: Website integration

- [ ] T010 Implement automation read models and FastAPI routes
- [ ] T011 Implement bounded web actions for full market-day automation runs
- [ ] T012 Implement automation status, history, and controls in the React app

## Phase 4: Validation and delivery

- [ ] T013 Update README and quickstart documentation for automation workflows
- [ ] T014 Run backend tests, frontend tests, build verification, and full repo validation
- [ ] T015 Update state, index, and session handover artifacts for the completed phase
