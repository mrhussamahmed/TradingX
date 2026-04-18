---
id: TASKS-0004
title: TradingX Gate 3 operations and evidence task list
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-016
---

# Tasks: TradingX Gate 3 operations and evidence

**Input**: Design documents from `/specs/004-gate3-operations-evidence/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`

## Phase 1: Artifact chain and failing tests

- [ ] T001 Add the Gate 3 artifact chain and update index tracking
- [ ] T002 [P] Add failing type and persistence tests for Gate 3 records
- [ ] T003 [P] Add failing report-builder tests for Gate 3 readiness and promotion packaging
- [ ] T004 [P] Add failing API-contract and web-runtime tests for Gate 3 actions and reads
- [ ] T005 [P] Add failing frontend tests for the Gate 3 readiness surface

## Phase 2: Core evidence engine

- [ ] T006 Implement Gate 3 types and persistence helpers
- [ ] T007 Implement execution-lifecycle and closed-trade recording in the paper loop
- [ ] T008 Implement recovery drills, alert drills, and market-session records
- [ ] T009 Implement the Gate 3 readiness and promotion-package builders
- [ ] T010 Implement CLI commands for Gate 3 report, package, and drills

## Phase 3: Website integration

- [ ] T011 Implement read models and FastAPI routes for Gate 3 readiness and promotion data
- [ ] T012 Implement write-mode web actions for drills and Gate 3 report generation
- [ ] T013 Implement the Gate 3 readiness dashboard and operations panel in the React app

## Phase 4: Validation and delivery

- [ ] T014 Update README and quickstart documentation for Gate 3 workflows
- [ ] T015 Run backend tests, frontend tests, build verification, and full repo validation
- [ ] T016 Update state, index, and session handover artifacts for the completed phase
