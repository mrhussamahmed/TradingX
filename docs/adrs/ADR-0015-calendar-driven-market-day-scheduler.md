---
id: ADR-0015
title: Use a calendar-driven recurring scheduler above the bounded market-day runner
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-020
---

# ADR-0015: Use a calendar-driven recurring scheduler above the bounded market-day runner

## Status

Accepted

## Context

TradingX now has a bounded market-day automation runner, but the
operator still has to launch it manually. That leaves the most important
Gate 3 evidence loop dependent on human timing even though the workflow
itself is already automatable.

The remaining gap is recurrence: deciding when a trading day starts,
preventing duplicate launches for the same day, and recovering
gracefully if the scheduler process restarts mid-session.

## Decision

Introduce a dedicated recurring scheduler layer that sits above the
existing market-day runner and uses Alpaca's regular-hours calendar to
decide when to launch.

The scheduler will:

- launch the bounded market-day runner at most once per trading day
- persist one schedule artifact per scheduled trading day
- expose live scheduler state plus latest schedule history through CLI
  and the local web app
- keep recurrence logic out of the browser and out of the bounded
  market-day runner

## Consequences

### Positive

- The repo gains one authoritative recurring automation flow for Gate 3
  evidence collection.
- Restarts can detect that today's trading day already ran and avoid
  duplicate launches.
- Operators can see next-run timing and latest scheduled-day outcome in
  the website.

### Negative

- The backend gains another long-running runtime path to test and
  maintain.
- The local web runtime now manages both service threads and scheduler
  threads.
- Scheduler state combines persisted records with live in-memory state,
  which increases read-model complexity.

## Rejected alternatives

- Rebuild recurrence outside the repo in desktop automations only:
  rejected because the repo still needs its own authoritative scheduler
  behavior and audit trail.
- Add recurrence directly into `MarketDayAutomationRunner`: rejected
  because that would blur the boundary between one-day orchestration and
  multi-day scheduling.
- Use fixed weekday wall-clock logic without a market calendar:
  rejected because the project already has an Alpaca-backed regular
  session calendar and should reuse it for more trustworthy scheduling.
