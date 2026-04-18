---
id: SPEC-0007
title: TradingX recurring market-day scheduler specification
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-020
---

# Feature Specification: TradingX recurring market-day scheduler

**Feature Branch**: `007-market-day-scheduler`
**Created**: 2026-04-18
**Status**: Active
**Input**: Operator request to build the next production-quality phase:
recurring market-day scheduling and unattended end-of-day Gate 3
evidence generation.

## User Scenarios & Testing

### User Story 1 - Launch Market-Day Automation Automatically (Priority: P1)

As the operator, I want a recurring scheduler that starts the bounded
market-day workflow on each trading day so I do not have to manually
start the bot every morning.

**Independent Test**: Start the scheduler in a bounded test mode,
simulate a regular session, and verify that it launches one market-day
automation run and writes one schedule artifact.

### User Story 2 - Avoid Duplicate Daily Runs (Priority: P1)

As the operator, I want restarts to be safe so the scheduler does not
launch the same trading day twice if the local process restarts or the
website reloads midday.

**Independent Test**: Seed a completed schedule record for a trading day
and verify that the scheduler computes the next session instead of
launching the same day again.

### User Story 3 - Operate The Scheduler From The Website (Priority: P1)

As the operator, I want the website to show scheduler state and expose
bounded start/stop actions so unattended automation can still be
inspected and controlled locally.

**Independent Test**: Start the scheduler from the website in write
mode, verify that live scheduler state appears, then stop it and verify
the UI updates to the stopped state.

## Edge Cases

- Scheduler starts before the next session opens.
- Scheduler starts during an active session and should launch
  immediately.
- Scheduler restarts after a completed schedule record already exists for
  the same trading day.
- The market-day runner fails partway through a scheduled launch.
- The scheduler is asked to stop while idle or while waiting for the
  next session.
- The website is open in read-only mode when a scheduler action is
  requested.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST expose a recurring scheduler that launches
  the bounded market-day runner automatically on trading days.
- **FR-002**: The scheduler MUST use the regular-hours market calendar
  rather than fixed weekday wall-clock assumptions alone.
- **FR-003**: The scheduler MUST persist one schedule record per
  scheduled trading day.
- **FR-004**: Schedule records MUST capture the trading day, scheduled
  session open, actual launch time, completion time, status, summary,
  and evidence references.
- **FR-005**: The scheduler MUST NOT launch more than once for the same
  trading day when a completed schedule record already exists.
- **FR-006**: If the scheduler starts while a session is already open
  and today's run has not been scheduled, it MUST launch immediately.
- **FR-007**: The CLI MUST expose a recurring scheduler command.
- **FR-008**: The local website MUST expose scheduler state, latest
  schedule history, and bounded start/stop actions.
- **FR-009**: End-of-day Gate 3 evidence generation MUST remain fully
  automatic through the scheduled market-day close step.
- **FR-010**: Scheduler state and artifacts MUST keep secrets out of
  logs, UI responses, and persisted files.

### Key Entities

- **Market Day Schedule Record**: One persisted record for one scheduled
  trading day launch.
- **Scheduler State**: The current runtime posture of the recurring
  scheduler, including next-run timing and any error state.
- **Session Window**: The open and close times for the current or next
  regular trading day as reported by the calendar layer.

## Success Criteria

- **SC-001**: The operator can run a recurring scheduler from CLI or the
  website without manually launching the market-day workflow each day.
- **SC-002**: The scheduler does not duplicate a trading day launch when
  a completed schedule record already exists.
- **SC-003**: The website presents a first-class scheduler status and
  control surface.
- **SC-004**: The repo passes backend tests, frontend tests, build
  verification, and `./scripts/validate` after the feature lands.
