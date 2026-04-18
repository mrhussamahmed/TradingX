---
id: SPEC-0008
title: TradingX local trading appliance specification
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-022
---

# Feature Specification: TradingX local trading appliance

**Feature Branch**: `codex/local-trading-appliance`
**Created**: 2026-04-19
**Status**: Active
**Input**: Operator request to formalize and implement a
production-grade local microservice-style architecture with one-click
website control, deterministic first-run selection, governed
strategy/model activation, historical warmup, and learning proposals.

## User Scenarios & Testing

### User Story 1 - Start The Bot From The Website (Priority: P1)

As the operator, I want the website to start and stop the bot through a
single runtime host so I do not need to manually compose multiple
commands or reason about internal subsystem order.

**Independent Test**: Start the runtime host from the website, verify
the state machine advances through warmup and readiness, then stop it
and verify the runtime returns to a safe terminal state.

### User Story 2 - Select The First Opportunity Deterministically (Priority: P1)

As the operator, I want the bot's first trade candidate to be ranked
from the configured universe through explicit scoring and tie-break
rules so the first action is explainable and reproducible.

**Independent Test**: Seed warmup and market snapshots for multiple
symbols, verify the opportunity selector returns either the single
highest-ranked candidate or `NO_TRADE` when thresholds are not met.

### User Story 3 - Govern Which Strategy And Weights Are Live (Priority: P1)

As the operator, I want an explicit activation record and approved
weight snapshot so live paper behavior is controlled by versioned
artifacts rather than hidden code defaults.

**Independent Test**: Load an activation record and approved snapshot,
verify the runtime uses them; remove approval and verify the runtime
halts or falls back only when the activation record explicitly allows
it.

### User Story 4 - Learn Safely From Closed Trades (Priority: P2)

As the operator, I want post-trade analytics and statistical learning to
propose better weights without mutating the live runtime automatically.

**Independent Test**: Feed closed-trade records into the learning
service, verify it writes a proposal only when the supporting sample
size and improvement threshold are met, and verify that the active
snapshot does not change automatically.

## Edge Cases

- Warmup history is missing for one or more symbols.
- Real paper credentials are absent or placeholder values remain.
- Market data is stale for the highest-ranked candidate.
- No candidate clears the deploy threshold on first run.
- A model-weight proposal improves one metric but worsens another beyond
  its safety bound.
- The runtime is started while the scheduler is already active.
- The operator attempts a write action while the website is in read-only
  mode.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST expose a runtime-host state machine for
  the local trading appliance.
- **FR-002**: The runtime host MUST fail closed when credentials,
  warmup data, activation records, or broker state are missing or
  invalid.
- **FR-003**: The system MUST persist a historical warmup summary for
  the configured universe and benchmark.
- **FR-004**: The system MUST persist the latest opportunity-selection
  decision, including ranking inputs and the selected symbol or
  `no_trade`.
- **FR-005**: The live paper runtime MUST read an explicit
  `StrategyActivationRecord`.
- **FR-006**: The live paper runtime MUST read an approved
  `ModelWeightSnapshot`, or use an explicit deterministic fallback only
  when the activation record allows it.
- **FR-007**: The system MUST provide a learning service that consumes
  persisted closed-trade records and writes governed weight proposals.
- **FR-008**: Learning MUST NOT auto-activate strategies or model
  weights.
- **FR-009**: The website MUST show runtime-host state, activation
  status, latest warmup summary, latest opportunity-selection result,
  and latest learning proposal.
- **FR-010**: The website MUST expose bounded start and stop actions for
  the runtime host behind write mode.
- **FR-011**: The system MUST preserve the existing paper-only safety
  posture and leave live trading disabled at all four layers.
- **FR-012**: All runtime, proposal, and selection artifacts MUST keep
  secrets out of logs, UI payloads, and persisted files.

### Key Entities

- **Runtime Host State**: the explicit lifecycle state of the local
  appliance runtime.
- **Historical Warmup Record**: summary of the warmup data used to make
  the runtime decisionable.
- **Strategy Activation Record**: versioned approval for which strategy
  may drive live paper decisions.
- **Model Weight Snapshot**: immutable approved weights used by scoring.
- **Model Weight Proposal**: non-active learning output with evidence
  and significance metadata.
- **Opportunity Selection Record**: ranked opportunity set plus selected
  candidate or `no_trade`.

## Success Criteria

- **SC-001**: The operator can start and stop the bot from the website
  using one runtime-host control surface.
- **SC-002**: The runtime transitions through explicit readiness states
  and fails closed when prerequisites are missing.
- **SC-003**: The first trade candidate is selected through deterministic
  ranking rules and persisted evidence.
- **SC-004**: Strategy and model activation are governed by explicit
  artifacts.
- **SC-005**: Learning produces proposals without mutating the active
  runtime automatically.
- **SC-006**: Backend tests, frontend tests, build verification, and
  `./scripts/validate` pass after the feature lands.
