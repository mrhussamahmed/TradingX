---
id: TASKS-0005
title: TradingX replay-slippage evidence task list
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# Tasks: TradingX replay-slippage evidence

**Input**: Design documents from `/specs/005-replay-slippage-evidence/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`

## Phase 1: Artifact chain and failing tests

- [ ] T001 Add the replay-slippage artifact chain and update index tracking
- [ ] T002 [P] Add failing type and persistence tests for replay-slippage records and summaries
- [ ] T003 [P] Add failing replay-engine and Gate 3 report tests for replay divergence evaluation
- [ ] T004 [P] Add failing API-contract and web-runtime tests for replay-slippage reads and actions
- [ ] T005 [P] Add failing frontend tests for replay-slippage status in the Gate 3 view

## Phase 2: Core replay evidence engine

- [ ] T006 Enrich execution-lifecycle records with quote and liquidity context
- [ ] T007 Implement replay-slippage types and persistence helpers
- [ ] T008 Implement replay-slippage record and summary generation
- [ ] T009 Implement CLI replay-slippage generation and Gate 3 readiness integration

## Phase 3: Website integration

- [ ] T010 Implement replay-slippage read models and FastAPI routes
- [ ] T011 Implement replay-slippage write-mode web actions
- [ ] T012 Implement replay-slippage status and refresh controls in the React app

## Phase 4: Validation and delivery

- [ ] T013 Update README and quickstart documentation for replay-slippage workflows
- [ ] T014 Run backend tests, frontend tests, build verification, and full repo validation
- [ ] T015 Update state, index, and session handover artifacts for the completed phase
