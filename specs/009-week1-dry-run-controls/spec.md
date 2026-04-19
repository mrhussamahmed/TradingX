---
id: SPEC-0009
title: TradingX week-1 dry-run controls specification
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-024
---

# Feature Specification: TradingX week-1 dry-run controls

**Feature Branch**: `codex/week1-safety-pack`
**Created**: 2026-04-19
**Status**: Active
**Input**: Operator-directed Sunday safety pack for Monday dry-run and
Tuesday go-live gating.

## User Scenarios & Testing

### User Story 1 - Run Monday In Controlled Dry-Run (Priority: P1)

As the operator, I want Monday's paper session to collect full decision,
policy, and simulated OMS evidence without placing any real broker
orders so I can validate the trading loop safely before Tuesday submit
is even considered.

**Independent Test**: Start the runtime in `dry_run`, verify that
decision snapshots and OMS journal rows are written, and verify that no
broker submit call occurs.

### User Story 2 - Block Unsafe Trading Through Explicit Policy (Priority: P1)

As the operator, I want hard entry caps, session windows, close ladder,
sticky drawdown halts, and zero-overnight policy to be encoded in a
versioned policy artifact rather than hidden in code so every decision
is auditable.

**Independent Test**: Feed adversarial scenarios into the policy engine
and verify that the runtime never exceeds daily caps, never re-enters a
symbol in the same session, and always escalates the close ladder on
time.

### User Story 3 - Guarantee Idempotent Order Tracking And Recovery (Priority: P1)

As the operator, I want a deterministic, append-only OMS journal plus
two-tier reconciliation so restarts, retries, and broker divergences do
not result in duplicate orders or silent state drift.

**Independent Test**: Simulate submit retry, partial fill, and broker
divergence; verify the journal remains append-only, retries query by
deterministic `client_order_id`, and divergence enters
`recovery_required`.

### User Story 4 - Decide Tuesday Go-Live From Artifacts, Not Vibes (Priority: P1)

As the operator, I want Sunday drills, Monday dry-run report artifacts,
and Tuesday gates to be explicit runtime outputs so go-live is a yes/no
artifact-backed decision rather than a judgment call.

**Independent Test**: Run the scripted HALT, REJECT, and RECOVERY
drills plus the go-live gate check and verify the expected artifacts are
emitted.

## Edge Cases

- Runtime starts before regular hours and must wait until the first
  legal entry window without churning broker calls.
- Decision cycle exceeds 30 seconds and must abort with
  `cycle_overrun`.
- Broker reports a position or order the journal does not know about.
- Broker rejects an order due to insufficient buying power.
- Entry receives a partial fill and the remainder must be canceled.
- Close ladder reaches market-close with a still-open position.
- Two processes start against the same data directory.
- Telegram controls are unavailable and the CLI/file-based fallback must
  still support week-1 operation.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST stamp a `PolicySnapshot` into every
  decision.
- **FR-002**: The policy snapshot MUST include week-1 numeric defaults
  for entries, exposure, cooldowns, quote sanity, drawdown halts, and
  close-window escalation.
- **FR-003**: The system MUST persist a versioned `DecisionSnapshot` v1
  before any OMS submit path is invoked.
- **FR-004**: The decision snapshot MUST include `schema_version`,
  `git_sha`, `dry_run`, `strategy_config_hash`, and
  `session_start_equity`.
- **FR-005**: The OMS MUST use an append-only SQLite journal in WAL mode
  and MUST NOT mutate or delete prior journal rows.
- **FR-006**: The OMS MUST derive deterministic `client_order_id`
  values from `decision_snapshot_id`, symbol, side, and retry
  sequence.
- **FR-007**: The OMS MUST query Alpaca by `client_order_id` before
  resubmitting after a retryable failure.
- **FR-008**: The system MUST support lightweight per-cycle
  reconciliation and full startup/boundary/error reconciliation.
- **FR-009**: Any unresolved divergence MUST enter
  `recovery_required`, block new entries, and require operator
  clearance plus fresh reconciliation before nominal trading resumes.
- **FR-010**: Monday sessions MUST run in `dry_run` and MUST NOT submit
  broker orders.
- **FR-011**: The system MUST emit structured JSON logs and enumerated
  veto reasons for blocked intents and `no_trade` outcomes.
- **FR-012**: The system MUST expose dry-run report and Tuesday gate
  artifacts suitable for operator review.

### Key Entities

- **PolicySnapshot**: immutable session policy artifact containing caps,
  windows, halts, and close ladder defaults.
- **DecisionSnapshotV1**: full per-cycle decision record persisted
  before submit.
- **OmsJournalEvent**: one append-only OMS or reconciliation event row.
- **RecoveryState**: explicit runtime state progression for
  `recovery_required`, operator clearance request, reconciliation, and
  nominal resumption.
- **DryRunReport**: Monday post-close report summarizing cycles,
  simulated orders, anomalies, and veto reasons.
- **GoLiveGateResult**: Tuesday startup verdict based on week-1
  readiness checks.

## Success Criteria

- **SC-001**: Monday can run end to end in `dry_run` without broker
  submits while still producing full decision and OMS artifacts.
- **SC-002**: Policy caps, sticky halts, close ladder, and zero
  overnight posture are enforced by tests and artifacts.
- **SC-003**: Duplicate-submit risk is reduced through deterministic
  `client_order_id` and journal-driven retry behavior.
- **SC-004**: Reconciliation divergence moves the runtime into a
  blocked recovery state instead of allowing silent drift.
- **SC-005**: Sunday drills and Tuesday gate artifacts are generated
  through executable code paths.
- **SC-006**: `./scripts/validate` and `python3 scripts/check_index.py`
  pass after the phase lands.
