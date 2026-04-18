---
id: SPEC-0005
title: TradingX replay-slippage evidence specification
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# Feature Specification: TradingX replay-slippage evidence

**Feature Branch**: `005-replay-slippage-evidence`  
**Created**: 2026-04-18  
**Status**: Active  
**Input**: Operator request to promote Gate 3 and proceed with the next
production-quality gap: replay-simulator slippage evidence and website
visibility.

## User Scenarios & Testing

### User Story 1 - Generate Replay Evidence From Paper Executions (Priority: P1)

As the operator, I want replay-slippage records generated from persisted
paper executions so I can compare Alpaca paper fill quality with a
quantity-aware replay model.

**Independent Test**: Run the replay-slippage workflow and verify that
trade-level replay records and a summary artifact are persisted from
existing execution-lifecycle artifacts.

### User Story 2 - Close The Gate 3 Replay Criterion Truthfully (Priority: P1)

As the operator, I want Gate 3 readiness to use replay-slippage
evidence so the replay-divergence criterion becomes pass, fail, or
pending from evidence instead of a hard-coded placeholder.

**Independent Test**: Generate replay evidence for representative paper
executions and verify that the Gate 3 readiness report consumes the
latest replay summary when evaluating replay divergence.

### User Story 3 - Inspect Replay Divergence In The Website (Priority: P1)

As the operator, I want the local website to show replay-slippage status
and divergence details so I can inspect slippage mismatch without
opening raw JSON.

**Independent Test**: Load the operator platform and verify that the
Gate 3 surface shows replay matched count, paper mean slippage, replay
mean slippage, divergence ratio, and the latest generation time.

## Edge Cases

- Execution artifacts predate the replay phase and do not contain bid,
  ask, or average-daily-volume fields.
- Only buy executions or only sell executions exist.
- Paper slippage is zero or near zero while replay slippage is nonzero.
- Replay generation is requested when there are no execution artifacts.
- The website is in read-only mode and replay generation is requested.
- Replay generation runs twice over the same executions.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST persist enough execution context to replay
  expected fill quality from completed paper executions.
- **FR-002**: The system MUST generate replay-slippage records from
  persisted execution context without requiring live market access at
  generation time.
- **FR-003**: Every replay-slippage record MUST identify the related
  paper execution, simulated fill price, simulated slippage, paper
  slippage, and divergence ratio.
- **FR-004**: The system MUST persist replay-slippage summary artifacts
  that include matched execution count, paper mean slippage, replay mean
  slippage, and overall divergence ratio.
- **FR-005**: Gate 3 readiness MUST evaluate the replay-divergence
  criterion from persisted replay evidence when that evidence exists.
- **FR-006**: The readiness engine MUST mark the replay-divergence
  criterion as `pending` when replay evidence is absent or insufficient.
- **FR-007**: The CLI MUST expose a bounded replay-slippage generation
  command.
- **FR-008**: The local website MUST expose replay-slippage status and a
  bounded write-mode action to refresh replay evidence.
- **FR-009**: Replay generation MUST be idempotent for the same
  execution inputs and MUST not duplicate equivalent replay records.
- **FR-010**: The implementation MUST keep secrets out of replay
  artifacts, UI responses, and logs.

### Key Entities

- **Replay Slippage Record**: One replay-simulated comparison against a
  persisted paper execution.
- **Replay Slippage Summary**: The aggregate replay-vs-paper slippage
  view for the current evidence set.
- **Replay Generation Result**: The bounded command or web-action result
  that reports written artifacts and status.

## Success Criteria

- **SC-001**: The operator can generate replay-slippage evidence from
  repo artifacts alone.
- **SC-002**: Gate 3 readiness no longer hard-codes the replay
  divergence criterion as always pending.
- **SC-003**: The website shows replay-slippage status and divergence in
  a first-class operator view.
- **SC-004**: The repo passes automated backend tests, frontend tests,
  build verification, and `./scripts/validate` after the feature lands.
