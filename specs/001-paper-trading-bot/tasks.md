---
id: TASKS-0001
title: TradingX Stage 1 paper trading bot task list
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-005
---

# Tasks: TradingX Stage 1 paper trading bot

**Input**: Design documents from `/specs/001-paper-trading-bot/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`

**Tests**: Tests are required for this feature because the constitution
mandates TDD for production code.

**Organization**: Tasks are grouped by user story so each story can be
implemented and validated independently once the shared foundation is in
place.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on
  incomplete tasks)
- **[Story]**: Which user story this task belongs to (`US1`, `US2`,
  `US3`)
- Every task includes the exact file path it changes

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the missing Stage 1 dependencies and module entry
points before deeper implementation work starts.

- [ ] T001 Update Stage 1 dependencies in `pyproject.toml` and `uv.lock`
- [ ] T002 [P] Create Stage 1 module shells in `src/tradingx/strategy.py`, `src/tradingx/evaluation.py`, `src/tradingx/alerts.py`, `src/tradingx/monitoring.py`, and `src/tradingx/persistence.py`
- [ ] T003 [P] Create matching unit-test shells in `tests/unit/test_strategy.py`, `tests/unit/test_evaluation.py`, `tests/unit/test_alerts.py`, `tests/unit/test_monitoring.py`, and `tests/unit/test_persistence.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared types, persistence, monitoring, and runtime plumbing
that every user story depends on.

**⚠️ CRITICAL**: No user story work should begin until this phase is
complete.

- [ ] T004 [P] Add failing tests for shared Stage 1 domain records in `tests/unit/test_types.py`
- [ ] T005 Extend shared Stage 1 records in `src/tradingx/types.py`
- [ ] T006 [P] Add failing tests for filesystem evidence repositories in `tests/unit/test_persistence.py`
- [ ] T007 Implement filesystem evidence repositories in `src/tradingx/persistence.py`
- [ ] T008 [P] Add failing tests for metrics and event recording in `tests/unit/test_monitoring.py`
- [ ] T009 Implement metrics and event recording in `src/tradingx/monitoring.py`
- [ ] T010 [P] Extend failing runtime-configuration tests in `tests/unit/test_config.py`
- [ ] T011 Extend paper-loop and evidence configuration in `src/tradingx/config.py`
- [ ] T012 Implement Stage 1 CLI entrypoints in `src/tradingx/__main__.py`

**Checkpoint**: Shared foundations are ready; user stories can now be
implemented independently.

---

## Phase 3: User Story 1 - Run A Safe Paper Trading Bot (Priority: P1) 🎯 MVP

**Goal**: Execute a deterministic paper-only trading loop that turns
market observations into reconciled trades or recorded blocked-trade
outcomes.

**Independent Test**: Run the bot in paper mode during regular market
hours and confirm that valid trade intents reconcile successfully while
unsafe situations are blocked and recorded.

### Tests for User Story 1

- [ ] T013 [P] [US1] Add failing unit tests for trade-intent generation and risk event decisions in `tests/unit/test_strategy.py` and `tests/unit/test_risk.py`
- [ ] T014 [P] [US1] Add a failing trading-loop contract test in `tests/contract/test_trading_loop_contract.py`
- [ ] T015 [P] [US1] Add a failing paper-loop integration test in `tests/integration/test_paper_trading_loop.py`
- [ ] T016 [P] [US1] Add a failing recovery and idempotency integration test in `tests/integration/test_recovery_reconciliation.py`

### Implementation for User Story 1

- [ ] T017 [P] [US1] Implement deterministic baseline signal generation in `src/tradingx/strategy.py`
- [ ] T018 [US1] Extend market and account snapshots in `src/tradingx/data.py` and `src/tradingx/portfolio.py`
- [ ] T019 [US1] Refactor hard pre-trade checks to emit auditable risk decisions in `src/tradingx/risk.py`
- [ ] T020 [US1] Attach trade-intent, order-record, and reconciliation persistence to the paper loop in `src/tradingx/execution.py` and `src/tradingx/controller.py`
- [ ] T021 [US1] Wire the regular-hours paper loop and restart reconciliation flow in `src/tradingx/__main__.py` and `src/tradingx/controller.py`

**Checkpoint**: User Story 1 is independently functional as the MVP
paper bot.

---

## Phase 4: User Story 2 - Evaluate Strategy Candidates Honestly (Priority: P2)

**Goal**: Evaluate the mandatory Stage 1 candidates under one shared,
benchmark-relative adversarial methodology and persist clear evidence
packs.

**Independent Test**: Run the candidate-evaluation pipeline and confirm
that every mandatory candidate produces a benchmark-relative evidence
pack with a keep/reject/research-further recommendation.

### Tests for User Story 2

- [ ] T022 [P] [US2] Add failing unit tests for candidate definitions and evaluation metrics in `tests/unit/test_strategy.py` and `tests/unit/test_evaluation.py`
- [ ] T023 [P] [US2] Add a failing evaluation contract test in `tests/contract/test_strategy_evaluation_contract.py`
- [ ] T024 [P] [US2] Add a failing evaluation-pipeline integration test in `tests/integration/test_strategy_evaluation_pipeline.py`

### Implementation for User Story 2

- [ ] T025 [US2] Implement the mandatory candidate registry and deterministic strategy builders in `src/tradingx/strategy.py`
- [ ] T026 [US2] Implement benchmark-relative metrics and adversarial checks in `src/tradingx/evaluation.py`
- [ ] T027 [US2] Add the Nautilus Trader evaluation adapter and replay entrypoints in `src/tradingx/evaluation.py` and `src/tradingx/data.py`
- [ ] T028 [US2] Persist evaluation evidence packs and recommendations in `src/tradingx/persistence.py` and `src/tradingx/controller.py`

**Checkpoint**: User Story 2 produces evidence-backed candidate outputs
without depending on User Story 3.

---

## Phase 5: User Story 3 - Stay Informed Without Watching Markets (Priority: P3)

**Goal**: Emit bounded operator alerts, auditable evidence views, and
live-disable visibility so the operator can supervise the bot without
continuous market watching.

**Independent Test**: Trigger material events such as blocked trades or
gate updates and confirm that the operator can inspect clear evidence
without enabling live trading.

### Tests for User Story 3

- [ ] T029 [P] [US3] Add failing unit tests for alert payloads and metrics fan-out in `tests/unit/test_alerts.py` and `tests/unit/test_monitoring.py`
- [ ] T030 [P] [US3] Add a failing operator-evidence contract test in `tests/contract/test_operator_evidence_contract.py`
- [ ] T031 [P] [US3] Add a failing operator-alert integration test in `tests/integration/test_operator_alerts.py`

### Implementation for User Story 3

- [ ] T032 [US3] Implement operator alert payload builders and transport adapters in `src/tradingx/alerts.py`
- [ ] T033 [US3] Extend evidence and freshness metrics in `src/tradingx/monitoring.py` and `src/tradingx/controller.py`
- [ ] T034 [US3] Implement manual-halt visibility and live-disable reporting in `src/tradingx/config.py`, `src/tradingx/risk.py`, and `src/tradingx/alerts.py`
- [ ] T035 [US3] Add operator-facing evidence and report commands in `src/tradingx/__main__.py` and `src/tradingx/persistence.py`

**Checkpoint**: User Story 3 provides bounded operator oversight without
changing the behavior of the other stories.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Finalize validation coverage and refresh the operator-facing
runbooks after the three user stories land.

- [ ] T036 [P] Update end-to-end validation coverage in `scripts/validate` and `tests/smoke/test_alpaca_paper_roundtrip.py`
- [ ] T037 [P] Refresh operator and developer runbooks in `README.md` and `specs/001-paper-trading-bot/quickstart.md`
- [ ] T038 Run the quickstart flow documented in `specs/001-paper-trading-bot/quickstart.md` and capture any required follow-up edits in that file

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Can start immediately
- **Foundational (Phase 2)**: Depends on Setup and blocks all user
  stories
- **User Stories (Phases 3-5)**: Depend on Foundational completion
- **Polish (Phase 6)**: Depends on the desired user stories being
  complete

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Phase 2 and defines the MVP
- **User Story 2 (P2)**: Starts after Phase 2; it may reuse User Story 1
  persistence and data plumbing but remains independently testable
- **User Story 3 (P3)**: Starts after Phase 2; it may consume User Story
  1 and 2 evidence but remains independently testable

### Within Each User Story

- Tests must be written and observed failing before implementation
- Domain and data-model work comes before orchestration
- Persistence and controller wiring come after the underlying modules
- A story should be validated independently before moving to the next
  priority

### Parallel Opportunities

- T002 and T003 can run in parallel
- T004/T006/T008/T010 can run in parallel before their paired
  implementation tasks
- Within each story, the test tasks marked `[P]` can run in parallel
- User Story phases can be staffed in parallel once Phase 2 is complete,
  though the recommended delivery order is P1 → P2 → P3

---

## Parallel Example: User Story 1

```bash
# Launch the failing tests for US1 together:
Task: "Extend tests/unit/test_strategy.py and tests/unit/test_risk.py"
Task: "Add tests/contract/test_trading_loop_contract.py"
Task: "Add tests/integration/test_paper_trading_loop.py"
Task: "Add tests/integration/test_recovery_reconciliation.py"

# Then implement independent module work in parallel where possible:
Task: "Implement src/tradingx/strategy.py"
Task: "Extend src/tradingx/data.py and src/tradingx/portfolio.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1
4. Validate the paper bot independently with the story-specific tests and
   `./scripts/validate`
5. Demo or review the MVP before taking on evaluation and alerting

### Incremental Delivery

1. Foundation first
2. Deliver User Story 1 as the MVP paper bot
3. Add User Story 2 for evidence-backed strategy evaluation
4. Add User Story 3 for operator oversight and alerting
5. Finish with polish and full validation coverage

### Suggested MVP Scope

The recommended MVP is **Phase 1 + Phase 2 + User Story 1**. That is the
smallest slice that produces a safe, auditable Stage 1 paper bot.

---

## Notes

- Every task assumes TDD and repo-first artifact updates.
- `[P]` tasks should avoid writing the same file concurrently.
- Do not start live-trading work; all tasks remain within Stage 1 paper
  scope.
