---
id: SPEC-0002
title: TradingX local control web app specification
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-013
---

# Feature Specification: TradingX Local Control Web App

**Feature Branch**: `002-local-control-web-app`  
**Created**: 2026-04-17  
**Status**: Active  
**Input**: Operator request to brainstorm, architect, plan, task, and implement a fully functioning local website for interacting with TradingX within the repo and constitution rules.

## User Scenarios & Testing

### User Story 1 - Monitor Bot State From One Local Dashboard (Priority: P1)

As the operator, I want a local website that summarizes the bot's
current status, paper-account state, alerts, evidence, and gate health
so I can understand what the bot is doing without stitching together
multiple CLI commands and raw artifact folders.

**Independent Test**: Start the local site, open the dashboard, and
verify that the overview cards, positions, alerts, evidence counts,
service status, and gate summaries render from the current local
artifacts and runtime state.

### User Story 2 - Run Safe, Bounded Local Actions (Priority: P1)

As the operator, I want to trigger safe, constitution-compliant local
actions such as paper recovery, benchmark preparation, gate reporting,
decision-report refresh, and paper-service lifecycle control from the
website so I can interact with the bot without bypassing safety rules.

**Independent Test**: Enable web write mode, trigger each bounded action
from the website, and verify that it uses the same backend services as
the CLI, returns structured results, and persists the expected evidence
artifacts.

### User Story 3 - Review Evidence, History, and Project Records (Priority: P2)

As the operator, I want to browse trade history, blocked trades,
reconciliation records, evaluation evidence, gate reports, decision
briefs, handovers, and the session log in one place so I can review the
bot's behavior and project state without leaving the website.

**Independent Test**: Use the website to filter and inspect persisted
records from each evidence category and confirm that document and
artifact drill-downs stay readable and linked to the underlying files.

### User Story 4 - Compose Config Proposals Safely (Priority: P2)

As the operator, I want a bounded config workspace that lets me stage
proposed config changes as diffs on disk rather than mutating live
settings so I can prepare operational changes safely.

**Independent Test**: With web write mode enabled, open the config
workspace, create a proposal for runtime settings, preview the diff, and
confirm that a proposal file is written without changing the running bot
configuration.

### Edge Cases

- The site starts when no paper-service artifacts exist yet.
- The site is opened while regular US market hours are closed and the
  service is idle.
- Write-mode actions are requested while web write mode is disabled.
- A backend action fails because credentials, market state, or runtime
  evidence are incomplete.
- Validation artifacts exist for one gate but not another.
- Config proposal input is invalid or incomplete.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST provide a local-only web application bound
  to `localhost` by default.
- **FR-002**: The system MUST expose a dashboard summarizing bot state,
  portfolio state, alerts, evidence counts, and gate status.
- **FR-003**: The system MUST show paper-account cash, equity, buying
  power, open positions, and recent service-cycle outcomes.
- **FR-004**: The system MUST provide browsable views for trade intents,
  orders, risk events, reconciliations, evaluation evidence, operator
  alerts, validation reports, and gate assessments.
- **FR-005**: The system MUST provide a browsable view of handover
  documents, session log entries, and project state artifacts.
- **FR-006**: The system MUST remain read-only by default.
- **FR-007**: The system MUST gate write actions behind a dedicated web
  write-mode flag that is disabled by default.
- **FR-008**: The system MUST support bounded website actions for paper
  recovery, benchmark-close preparation, Gate 1/2 report generation,
  decision-report refresh, and paper-service start/stop when write mode
  is enabled.
- **FR-009**: The system MUST ensure website actions call the same
  backend services or domain logic used by the CLI rather than
  re-implementing trading logic in the browser.
- **FR-010**: The system MUST support a bounded config workspace that
  creates proposal artifacts or diffs on disk without mutating live
  configuration directly.
- **FR-011**: The system MUST NOT enable live trading, modify runtime
  risk limits directly, mutate the constitution or ADRs, or bypass the
  config-commit-reload safety path.
- **FR-012**: The system MUST present action failures explicitly in the
  UI and MUST NOT silently swallow backend errors.
- **FR-013**: The system MUST remain usable on both desktop and mobile
  browsers on the local machine or local private network.
- **FR-014**: The system MUST remain visually dense, legible, and
  operator-oriented rather than a generic admin scaffold.

### Key Entities

- **Dashboard Snapshot**: A combined read model of runtime, portfolio,
  evidence, and gate status for the main overview page.
- **Web Action Request**: A bounded action submitted from the local web
  app to backend services, including guard checks and operator feedback.
- **Config Proposal**: A staged configuration change stored on disk for
  later review and commit.
- **Document Record**: A browsable handover, session-log, or state file
  surfaced in the website.

## Success Criteria

- **SC-001**: The operator can open one local URL and understand current
  bot status, account state, alerts, and gate posture within 30 seconds.
- **SC-002**: Every bounded write action available in the website is
  blocked when web write mode is off and succeeds only through the same
  backend paths used elsewhere in the repo.
- **SC-003**: The operator can review one complete evidence trail, from
  trade intent through gate decision, entirely from the local web app.
- **SC-004**: The website renders and remains usable on a narrow mobile
  viewport and a standard desktop viewport.
- **SC-005**: The local site passes automated backend tests and browser
  tests and is included in `./scripts/validate`.
