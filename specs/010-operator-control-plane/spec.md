---
id: SPEC-0010
title: TradingX operator control plane specification
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-026
---

# Feature Specification: TradingX operator control plane

**Feature Branch**: `codex/tel-001-sup-001`
**Created**: 2026-04-19
**Status**: Active
**Input**: Operator-requested TEL-001 and SUP-001 for week-1 paper
operation.

## User Scenarios & Testing

### User Story 1 - Control The Week-1 Bot Through Telegram (Priority: P1)

As the single operator, I want a narrow Telegram command surface so I
can inspect state and request halt, resume, flatten, and kill actions
without relying on the website.

**Independent Test**: Feed mocked Telegram updates into the command
plane, verify only the configured chat is authorized, and verify the
expected control files or supervisor actions occur for each command.

### User Story 2 - Supervise The Trading Child Independently (Priority: P1)

As the operator, I want one local supervisor to own the long-running
child process and its state so unattended week-1 operation is still
single-writer, restart-safe, and observable.

**Independent Test**: Start the supervisor with a fake child runner,
verify child lifecycle state is persisted, verify `/kill` stops the
child without flattening, and verify `/resume` can restart the child
after clearing operator flags.

### User Story 3 - Flatten Safely Outside The Trading Loop (Priority: P1)

As the operator, I want `/flatten` to cancel working orders and submit
exit orders independently of the trading child so I can get flat even
when the child is halted or stopped.

**Independent Test**: Simulate open orders and positions, call the
flatten action, and verify cancel + close calls are issued and recorded
in the supervisor response.

## Edge Cases

- Telegram credentials are absent and the supervisor must still run with
  file-based fallback controls.
- Unauthorized Telegram chats send commands.
- `/resume` arrives while the child is already running.
- `/kill` arrives while the child is already stopped.
- `/flatten` runs with no open positions.
- Child exits unexpectedly and restart policy is disabled.
- Child exits unexpectedly and bounded restart policy is enabled.
- Data root is already locked by another TradingX process.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST provide a local operator supervisor entry
  point that owns the week-1 trading child lifecycle.
- **FR-002**: The supervisor MUST persist a state artifact under
  `artifacts/operator_platform/supervisor/`.
- **FR-003**: The supervisor MUST expose file-backed `halt`,
  `clearance`, and `kill` control requests under `data/control/`.
- **FR-004**: The trading child MUST not be controlled directly by
  Telegram or the website.
- **FR-005**: The Telegram command plane MUST support `/status`,
  `/positions`, `/today`, `/halt`, `/resume`, `/flatten`, and `/kill`.
- **FR-006**: The Telegram command plane MUST authorize exactly one
  configured `chat_id`.
- **FR-007**: `/flatten` MUST cancel working orders and then attempt to
  close open positions independently of the child loop.
- **FR-008**: `/kill` MUST stop decisioning without flattening.
- **FR-009**: `/resume` MUST clear operator halt and kill requests and
  record a clearance request before allowing the child to run again.
- **FR-010**: The supervisor MUST support a bounded restart policy for
  unexpected child exits, disabled by default.
- **FR-011**: The repo MUST provide week-1 CLI fallback operator
  controls if Telegram is not configured.

### Key Entities

- **OperatorControlState**: persistent halt, clearance, and kill flag
  state under `data/control/`
- **SupervisorState**: persisted summary of child liveness, restart
  count, control flags, and latest action
- **TelegramCommandResult**: normalized authorized-command outcome
- **TodaySummary**: lightweight summary of today’s cycles, snapshots,
  journal rows, blocked intents, and anomalies

## Success Criteria

- **SC-001**: The operator can halt, resume, flatten, and kill the
  week-1 paper bot without using the website.
- **SC-002**: Telegram command authorization rejects unknown chats.
- **SC-003**: The supervisor persists durable state and owns the child
  lifecycle without bypassing the single-writer guard.
- **SC-004**: `./scripts/validate` and `python3 scripts/check_index.py`
  pass after the phase lands.
