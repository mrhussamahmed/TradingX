---
id: TASKS-0003
title: TradingX operator platform task list
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-014
---

# Tasks: TradingX operator platform

**Input**: Design documents from `/specs/003-operator-platform/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`

## Phase 1: Artifact chain and backend contracts

- [ ] T001 Add the operator-platform artifact chain and update index/state tracking
- [ ] T002 [P] Add failing backend type and config tests for operator-platform entities
- [ ] T003 [P] Add failing API-contract tests for the new operator-platform routes
- [ ] T004 [P] Add failing backend read-model tests for command center, incidents, research, replay, and digest flows

## Phase 2: Operator-platform backend

- [ ] T005 Implement operator-platform types and persistence helpers
- [ ] T006 Implement normalized timeline/event builders and explorer queries
- [ ] T007 Implement incident acknowledgment and session-digest services
- [ ] T008 Implement command-center, research, replay, and records read models
- [ ] T009 Implement expanded FastAPI routes and bounded action handlers

## Phase 3: Frontend workspace

- [ ] T010 [P] Add failing frontend tests for the multi-view operator workspace and action flows
- [ ] T011 Implement the command center with charts, exposure cards, and live refresh
- [ ] T012 Implement trade intelligence, incident center, replay lab, and artifact explorer
- [ ] T013 Implement research studio, session actions, keyboard-first navigation, and proposal workflow polish

## Phase 4: Validation and delivery

- [ ] T014 Update docs, README, and quickstart for the operator platform
- [ ] T015 Run frontend build, backend tests, and full repo validation
- [ ] T016 Write the session handover, update project state, and prepare the branch for merge
