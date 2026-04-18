---
id: SPEC-0004
title: TradingX Gate 3 operations and evidence specification
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-016
---

# Feature Specification: TradingX Gate 3 operations and evidence

**Feature Branch**: `004-gate3-operations-evidence`  
**Created**: 2026-04-18  
**Status**: Active  
**Input**: Operator request to build the next production-quality phase:
Gate 3 operations, evidence, readiness, and promotion packaging on top
of the existing bot and operator platform.

## User Scenarios & Testing

### User Story 1 - Run A Market Day Safely (Priority: P1)

As the operator, I want pre-open, intraday, close, and recovery-aware
session orchestration so I can run the paper bot through a trading day
with auditable checkpoints and bounded controls.

**Independent Test**: Trigger the session actions through the CLI or the
website and verify that session records are written with current service
state, evidence references, and clear operator messages.

### User Story 2 - Accumulate Truthful Gate 3 Evidence (Priority: P1)

As the operator, I want durable trade-lifecycle, drill, and readiness
artifacts so I can inspect real slippage, closed-trade outcomes,
recovery exercises, and emergency-alert exercises instead of relying on
manual notes.

**Independent Test**: Execute fills, recovery drills, and alert drills
and verify that execution-lifecycle records, closed-trade records,
drill records, and readiness reports are persisted and queryable.

### User Story 3 - See Gate 3 Readiness In The Website (Priority: P1)

As the operator, I want a first-class Gate 3 readiness surface in the
website so I can see criterion-by-criterion pass, pending, or fail
status, drill history, and promotion recommendations without opening raw
JSON.

**Independent Test**: Load the operator platform and verify that the
readiness panel shows headline status, criteria detail, drill summaries,
and promotion workflow actions from persisted evidence.

### User Story 4 - Produce A Promotion Package (Priority: P2)

As the operator, I want one bounded workflow that turns accumulated Gate
3 evidence into a promotion or rejection package so I can review
advancement decisions with the same discipline as earlier gates.

**Independent Test**: Generate a Gate 3 readiness report and promotion
package, then verify that both artifacts contain criteria outcomes,
evidence references, and the next required operator action.

## Edge Cases

- The bot has no closed trades yet.
- The operator has service-cycle evidence but no drill artifacts.
- Alerting is not configured, so an SMTP drill cannot run.
- Recovery is invoked when no matching trade intent exists.
- The website is in read-only mode and the operator requests a drill.
- The readiness report has enough trade count but no reference
  expectation for hit rate or Sharpe.
- Service state records an error while the latest daily session record
  says the system is idle.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST persist execution-lifecycle records for
  every filled paper order with a reference price, fill price, filled
  quantity, and slippage measurement.
- **FR-002**: The system MUST persist closed-trade records when a paper
  position is exited and a realized trade outcome can be determined.
- **FR-003**: The system MUST persist explicit recovery-drill records
  and alert-drill records.
- **FR-004**: The system MUST persist market-session records for
  pre-open, intraday heartbeat, close, and comparable operator
  checkpoints.
- **FR-005**: The system MUST generate a Gate 3 readiness report from
  persisted evidence and mark every criterion as `pass`, `pending`, or
  `fail`.
- **FR-006**: The readiness report MUST include trade-count or elapsed
  day progress, incident summary, realized slippage summary, closed
  trade hit rate, realized Sharpe, drill status, and promotion guidance.
- **FR-007**: The system MUST generate a Gate 3 promotion package from
  the latest readiness report.
- **FR-008**: The system MUST expose CLI commands for Gate 3 reporting,
  promotion packaging, recovery drills, and alert drills.
- **FR-009**: The local website MUST expose Gate 3 readiness and
  day-operations controls through new read endpoints and bounded
  write-mode actions.
- **FR-010**: The website MUST remain read-only by default and MUST
  reject all Gate 3 write actions when web write mode is disabled.
- **FR-011**: The readiness engine MUST degrade honestly when reference
  expectation data is missing instead of inventing a pass state.
- **FR-012**: The implementation MUST keep secrets out of persisted
  errors, UI responses, and logs.

### Key Entities

- **Execution Lifecycle Record**: One filled paper execution with
  expected price, fill price, slippage, and related identifiers.
- **Closed Trade Record**: One completed entry-exit trade with realized
  return, gross PnL, holding interval, and outcome.
- **Recovery Drill Record**: Evidence that restart or reconciliation
  recovery was exercised.
- **Alert Drill Record**: Evidence that an emergency-alert channel was
  exercised.
- **Market Session Record**: One pre-open, intraday, or close snapshot
  for the operating day.
- **Gate 3 Readiness Report**: The criterion-level assessment and
  operator summary for Gate 3.
- **Gate 3 Promotion Package**: A bounded package derived from the
  latest readiness report for operator review.

## Success Criteria

- **SC-001**: The operator can generate a Gate 3 readiness report from
  repo evidence alone.
- **SC-002**: The operator platform shows Gate 3 criterion status and
  drill history without requiring raw artifact inspection.
- **SC-003**: Recovery and alert exercises leave durable artifacts and
  surface immediately in the readiness view.
- **SC-004**: The repo passes automated backend tests, frontend tests,
  build verification, and `./scripts/validate` after the feature lands.
