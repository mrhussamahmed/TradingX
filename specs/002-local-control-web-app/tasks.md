---
id: TASKS-0002
title: TradingX local control web app task list
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-013
---

# Tasks: TradingX local control web app

**Input**: Design documents from `/specs/002-local-control-web-app/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`

## Phase 1: Foundations

- [ ] T001 Add web backend and frontend dependencies in `pyproject.toml`, new frontend package files, and validation support
- [ ] T002 [P] Add failing backend web-config and type tests in `tests/unit/test_config.py` and `tests/unit/test_types.py`
- [ ] T003 [P] Add failing API-contract and reporting tests in `tests/contract/test_local_web_app_api_contract.py` and `tests/unit/test_reporting.py`
- [ ] T004 Create backend web module shells in `src/tradingx/web/` and route entrypoints in `src/tradingx/__main__.py`
- [ ] T005 Create frontend app shell in `webapp/` with React, Vite, and base views

## Phase 2: Read-only cockpit

- [ ] T006 [P] Add failing backend read-model tests in `tests/unit/test_web_readmodels.py`
- [ ] T007 [P] Add failing frontend view tests in `webapp/src/**/*.test.tsx`
- [ ] T008 Implement dashboard, evidence, gate, config-summary, and document read models in `src/tradingx/web/readmodels.py` and `src/tradingx/reporting.py`
- [ ] T009 Implement FastAPI read routes in `src/tradingx/web/api.py` and `src/tradingx/web/app.py`
- [ ] T010 Implement SPA shell, navigation, overview dashboard, evidence browser, gate browser, and docs browser in `webapp/src/`

## Phase 3: Bounded controls

- [ ] T011 [P] Add failing action-guard and service-manager tests in `tests/unit/test_web_actions.py` and `tests/unit/test_service.py`
- [ ] T012 [P] Add failing browser-flow tests for bounded actions in local web UI tests
- [ ] T013 Implement web write-mode config and action guards in `src/tradingx/config.py` and `src/tradingx/web/actions.py`
- [ ] T014 Implement local paper-service manager and bounded action orchestration in `src/tradingx/web/service_manager.py` and `src/tradingx/service.py`
- [ ] T015 Implement config proposal composer in `src/tradingx/web/config_workspace.py`
- [ ] T016 Implement frontend action center, service controls, benchmark prep, gate/decision report controls, and config proposal workspace in `webapp/src/`

## Phase 4: Integration and polish

- [ ] T017 [P] Add browser smoke coverage for the local website in new UI/browser tests
- [ ] T018 Wire FastAPI static serving for the SPA build and add `tradingx web` command in `src/tradingx/__main__.py` and `src/tradingx/web/app.py`
- [ ] T019 Update CI, Docker, and `scripts/validate` for frontend build and tests
- [ ] T020 Refresh operator docs in `README.md` and `specs/002-local-control-web-app/quickstart.md`
- [ ] T021 Run the documented local website flow and capture follow-up edits in the docs
