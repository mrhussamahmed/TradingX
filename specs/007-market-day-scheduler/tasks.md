---
id: TASKS-0007
title: TradingX recurring market-day scheduler task list
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-020
---

# Tasks: TradingX recurring market-day scheduler

**Input**: Design documents from `/specs/007-market-day-scheduler/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`

## Phase 1: Artifact chain and failing tests

- [ ] T001 Add the recurring scheduler artifact chain and update index tracking
- [ ] T002 [P] Add failing type and persistence tests for market-day schedule records
- [ ] T003 [P] Add failing scheduler and calendar tests for next-session lookup and duplicate prevention
- [ ] T004 [P] Add failing CLI parser, API-contract, and web-runtime tests for scheduler state and actions
- [ ] T005 [P] Add failing frontend tests for scheduler status and start/stop controls

## Phase 2: Scheduler core

- [ ] T006 Extend the regular-hours calendar with current-or-next-session lookup
- [ ] T007 Implement scheduler types and persistence helpers
- [ ] T008 Implement the recurring market-day scheduler and bounded CLI command
- [ ] T009 Implement duplicate same-day prevention from persisted schedule records

## Phase 3: Website integration

- [ ] T010 Implement scheduler runtime manager support and web actions
- [ ] T011 Implement scheduler read models and FastAPI routes
- [ ] T012 Implement scheduler controls and status cards in the React app

## Phase 4: Validation and delivery

- [ ] T013 Update README and quickstart documentation for unattended scheduler workflows
- [ ] T014 Run backend tests, frontend tests, build verification, and full repo validation
- [ ] T015 Update state, index, and session handover artifacts for the completed phase
