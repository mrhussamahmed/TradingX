---
id: ADR-0014
title: Use a dedicated market-day automation runner with persisted run artifacts
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-018
---

# ADR-0014: Use a dedicated market-day automation runner with persisted run artifacts

## Status

Accepted

## Context

TradingX already provides bounded paper-service execution, Gate 3
evidence generation, replay-slippage validation, and a local operator
platform. The remaining operational gap is reliable market-day
execution without manual babysitting. The existing website-level
session actions only write digest snapshots; they do not orchestrate
pre-open checks, bounded heartbeats, end-of-day closeout, or automatic
Gate 3 refreshes as one evidence-producing flow.

Gate 3 depends on trustworthy operational history. That means the repo
needs a durable record of what automation ran, which evidence it
generated, and whether the market-day workflow completed cleanly.

## Decision

Introduce a dedicated market-day automation runner in the backend that:

- orchestrates pre-open, heartbeat, and close steps through shared
  domain services rather than browser-owned logic
- persists one market-automation run artifact per bounded execution
- refreshes replay-slippage evidence and Gate 3 reports automatically at
  heartbeat and close checkpoints
- exposes the same orchestration through CLI and local web write-mode
  actions

## Consequences

### Positive

- Market-day execution becomes reproducible and testable.
- Gate 3 evidence generation is tied directly to operational activity.
- The operator platform can show a first-class automation view from
  persisted artifacts instead of transient thread state.
- Later external automation can call one bounded runner rather than
  reconstructing the workflow from multiple commands.

### Negative

- The backend gains another orchestration layer to maintain.
- Additional artifacts increase the amount of persisted local state.
- The website now needs one more set of read/write endpoints and UI
  affordances.

## Rejected alternatives

- Reuse the existing digest-only session actions as-is:
  insufficient because they do not run the paper service or refresh Gate
  3 evidence.
- Implement orchestration only in the browser:
  rejected because operator UIs must not own trading or evidence logic.
- Depend only on external desktop automations:
  rejected because the repo still needs its own authoritative market-day
  workflow and evidence model.
