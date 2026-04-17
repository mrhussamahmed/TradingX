---
id: SPEC-0003
title: TradingX operator platform specification
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-014
---

# Feature Specification: TradingX Operator Platform

**Feature Branch**: `003-operator-platform`  
**Created**: 2026-04-18  
**Status**: Active  
**Input**: Operator request to turn the local website into a
production-ready, visually polished operator platform with richer
dashboards, trade explainability, research tooling, incident handling,
replay, and workflow acceleration.

## User Scenarios & Testing

### User Story 1 - Supervise The Bot From One Market-Day Command Center (Priority: P1)

As the operator, I want a command center that stays fresh throughout the
trading day so I can understand account state, exposure, drawdown,
service health, session posture, and recommended next actions from one
screen.

**Independent Test**: Open the local site, let it refresh, and verify
that the command center shows current service state, account/equity
cards, exposure charts, market session posture, and a digest of current
incidents and operator recommendations.

### User Story 2 - Explain Every Trade And Incident (Priority: P1)

As the operator, I want a detailed trade-intelligence and incident
surface so I can see why the bot entered, held, exited, blocked, or
recovered, and I can connect alerts to the exact underlying evidence.

**Independent Test**: Select a symbol or incident in the website and
verify that the decision trace, risk controls, order state,
reconciliation, related alerts, and replay timeline render from
persisted artifacts.

### User Story 3 - Review Research And Gate Evidence Visually (Priority: P1)

As the operator, I want a research studio that compares strategy
candidates, shows benchmark-relative metrics, and surfaces Gate 1 and
Gate 2 evidence so I can review promotion decisions without raw JSON or
CLI-only workflows.

**Independent Test**: Load evaluation evidence and validation artifacts
into the site and verify that the research studio shows candidate cards,
metric comparisons, gate summaries, and decision context.

### User Story 4 - Run Daily Operator Workflows Safely (Priority: P2)

As the operator, I want the website to support bounded day-operations
flows such as pre-open checks, intraday heartbeat capture, incident
acknowledgment, replay, recovery, and end-of-day digest generation so I
can manage the bot from one local surface without bypassing safety
rules.

**Independent Test**: Enable write mode, trigger the bounded day
operations from the site, and verify that each action uses the same
backend services or new bounded orchestration services, persists
artifacts, and returns structured UI feedback.

### User Story 5 - Browse Records And Artifacts Like A Product, Not A Folder (Priority: P2)

As the operator, I want searchable records, filters, and drill-downs
for documents and artifacts so I can move quickly between sessions,
alerts, reports, cycles, and proposals.

**Independent Test**: Use search and filters in the site to narrow the
records view and open evidence across multiple categories without
leaving the browser.

## Edge Cases

- The platform starts before any paper-service cycle or validation
  artifact exists.
- Market hours are closed and the session posture is idle.
- Validation artifacts exist for one gate but not the other.
- An incident is acknowledged, but new related evidence arrives later.
- Replay is requested for a symbol with partial artifacts.
- Write-mode actions are requested while write mode is disabled.
- Config proposals or daily digests fail because input artifacts are
  missing or inconsistent.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST provide a multi-view local operator
  platform bound to `localhost` by default.
- **FR-002**: The system MUST provide a command center with current
  account state, equity history, exposure distribution, service health,
  market session posture, and operator recommendations.
- **FR-003**: The system MUST refresh operator data automatically on a
  bounded polling interval without requiring manual browser refresh.
- **FR-004**: The system MUST provide trade-intelligence views that join
  trade intents, orders, risk events, reconciliations, and related
  alerts into one explainability surface.
- **FR-005**: The system MUST provide an incident center with severity,
  status, acknowledgment state, evidence links, and a chronological
  incident timeline.
- **FR-006**: The system MUST provide a replay lab that reconstructs
  historical timelines for service cycles, blocked trades, recoveries,
  and validation milestones from persisted artifacts.
- **FR-007**: The system MUST provide a research studio for candidate
  comparisons, benchmark-relative metrics, robustness summaries, gate
  summaries, and decision context.
- **FR-008**: The system MUST provide a searchable artifact and records
  explorer for docs, reports, alerts, cycles, proposals, and evidence.
- **FR-009**: The system MUST remain read-only by default and MUST gate
  all write actions behind the dedicated web write-mode flag.
- **FR-010**: The system MUST support bounded day-operations actions for
  pre-open checks, intraday heartbeat capture, end-of-day digest
  generation, incident acknowledgment, recovery, benchmark preparation,
  gate reporting, decision reporting, and paper-service control when
  write mode is enabled.
- **FR-011**: The system MUST persist operator-platform artifacts for
  session digests, acknowledgments, and replayable action traces behind
  the existing persistence boundary.
- **FR-012**: The system MUST use backend read models and orchestration
  services rather than duplicating business logic in the browser.
- **FR-013**: The system MUST surface explicit, sanitized degraded-state
  messages for missing artifacts, closed markets, invalid inputs, and
  failed actions.
- **FR-014**: The system MUST remain usable on desktop and mobile-width
  local browsers.
- **FR-015**: The system MUST provide a more premium visual design than
  the current dashboard through stronger hierarchy, richer charts,
  keyboard-first workflow affordances, and intentional operator-focused
  styling.

### Key Entities

- **Command Center Snapshot**: One chart-ready summary of runtime,
  account, exposure, service history, session posture, and gate health.
- **Operator Timeline Event**: A normalized event built from service
  cycles, trade intents, orders, risk events, reconciliations, alerts,
  validation reports, and operator actions.
- **Incident Record**: An operator-visible alert cluster with severity,
  status, acknowledgment metadata, related evidence, and suggested
  action.
- **Replay Session**: A reconstructed historical narrative for one
  symbol, service cycle, or incident.
- **Research Candidate Summary**: A UI-friendly comparison payload for
  one evaluated candidate.
- **Daily Session Digest**: A persisted summary of the day’s posture,
  incidents, cycles, and recommended next actions.

## Success Criteria

- **SC-001**: The operator can understand current bot posture,
  incidents, exposure, and recommended next actions from the command
  center within 30 seconds.
- **SC-002**: The operator can trace any displayed trade or blocked
  action back to its underlying evidence without leaving the website.
- **SC-003**: The operator can review Gate 1 and Gate 2 evidence
  visually through the research studio.
- **SC-004**: Every write-mode workflow remains blocked when write mode
  is disabled and leaves auditable evidence when enabled.
- **SC-005**: The operator platform passes automated backend tests,
  frontend tests, build verification, and the repo validation gate.
