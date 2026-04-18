---
id: SPEC-0006
title: TradingX market-day automation specification
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-018
---

# Feature Specification: TradingX market-day automation

**Feature Branch**: `006-market-day-automation`  
**Created**: 2026-04-18  
**Status**: Active  
**Input**: Operator request to build the next production-quality phase:
automated market-day execution and Gate 3 evidence refresh.

## User Scenarios & Testing

### User Story 1 - Run A Real Market-Day Workflow (Priority: P1)

As the operator, I want one bounded automation workflow that performs
pre-open, intraday heartbeat, and closeout steps so I can run TradingX
through a full market-day process without stitching multiple commands
together manually.

**Independent Test**: Run the market-day automation command with a
bounded heartbeat count and verify that it writes pre-open, heartbeat,
close, and automation-run artifacts.

### User Story 2 - Keep Gate 3 Evidence Fresh Automatically (Priority: P1)

As the operator, I want replay-slippage and Gate 3 readiness refreshed
as part of automation so new paper executions turn into current
readiness evidence without a second manual workflow.

**Independent Test**: Seed paper evidence, run the automation heartbeat,
and verify that replay-slippage summaries and Gate 3 reports are
written automatically.

### User Story 3 - Inspect Automation State In The Website (Priority: P1)

As the operator, I want the website to show the latest automation run,
checkpoint history, and action controls so I can understand the system's
operational posture from one screen.

**Independent Test**: Load the operator platform and verify that the
Gate 3 view shows automation-run status, heartbeat counts, evidence
refs, and the new bounded action controls.

## Edge Cases

- Automation starts while the market is closed.
- The paper service writes no executions during a heartbeat.
- Replay-slippage refresh finds no eligible executions.
- Gate 3 readiness remains pending even after refresh.
- A heartbeat step raises an exception mid-run.
- The operator requests zero heartbeat cycles.
- Web write mode is disabled when automation actions are triggered.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST expose a bounded market-day automation
  workflow that orchestrates pre-open, heartbeat, and close steps.
- **FR-002**: The system MUST expose the pre-open, heartbeat, and close
  steps individually for bounded manual control.
- **FR-003**: Each heartbeat step MUST refresh replay-slippage evidence
  and Gate 3 readiness after any service-cycle attempt.
- **FR-004**: The close step MUST generate a fresh Gate 3 promotion
  package from the latest readiness state.
- **FR-005**: The system MUST persist one automation-run artifact per
  bounded market-day execution.
- **FR-006**: Automation-run artifacts MUST capture timing, heartbeat
  count, status, summary, and evidence references.
- **FR-007**: The CLI MUST expose a bounded market-day automation
  command.
- **FR-008**: The local website MUST expose automation status and
  write-mode actions for pre-open, heartbeat, close, and full bounded
  automation runs.
- **FR-009**: Market-closed periods MUST be represented explicitly in
  automation outputs and MUST NOT be reported as successful heartbeats.
- **FR-010**: Automation actions MUST keep secrets out of artifacts, UI
  responses, and logs.

### Key Entities

- **Market Automation Run**: One bounded orchestration execution that
  records status, timing, heartbeat count, and evidence references.
- **Market Session Record**: One pre-open, heartbeat, or close
  checkpoint written during automation.
- **Daily Session Digest**: The operator-facing summary artifact for a
  checkpoint.

## Success Criteria

- **SC-001**: The operator can run a bounded market-day workflow through
  CLI or the website without chaining multiple manual commands.
- **SC-002**: Gate 3 replay-slippage and readiness evidence refresh
  automatically during automation steps.
- **SC-003**: The website presents a first-class automation history and
  control surface.
- **SC-004**: The repo passes backend tests, frontend tests, build
  verification, and `./scripts/validate` after the feature lands.
