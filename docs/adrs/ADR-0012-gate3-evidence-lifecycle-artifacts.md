---
id: ADR-0012
title: Use persisted trade lifecycle and drill artifacts as the Gate 3 evidence source
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-016
---

# ADR-0012: Use persisted trade lifecycle and drill artifacts as the Gate 3 evidence source

## Status

Accepted

## Context

Gate 3 requires paper-trading evidence that is more specific than the
current Stage 1 artifact set. The repository already records service
cycles, trade intents, orders, reconciliations, alerts, and validation
reports, but Gate 3 needs durable answers to additional questions:

- what slippage actually occurred on filled paper executions
- which trades closed profitably or unsuccessfully
- whether restart and recovery drills were exercised
- whether emergency alert drills succeeded
- whether the operator has enough evidence to promote or reject the
  paper bot

Trying to infer those answers only from service-cycle summaries would
produce a fragile and partially implicit report.

## Decision

TradingX will:

- persist execution-lifecycle records with reference price, fill price,
  and slippage
- persist closed-trade records with realized return and outcome
- persist explicit recovery-drill and alert-drill artifacts
- persist Gate 3 readiness reports and promotion packages as first-class
  evidence artifacts
- drive the website, CLI, and future automation from those persisted
  artifacts rather than from ephemeral runtime state

## Consequences

### Positive

- Gate 3 reporting becomes evidence-first rather than inference-heavy
- the operator platform can display truthful readiness state and drill
  history
- recovery and alert exercises become auditable project records

### Negative

- the paper-loop controller and persistence layer gain more artifact
  types that must stay consistent
- some Gate 3 criteria may remain `pending` until reference expectations
  or enough paper evidence exist

## Alternatives considered

- `Report only from service-cycle summaries`: rejected because it hides
  trade-level slippage and closed-trade outcomes
- `Compute readiness only in the UI`: rejected because it would create a
  second source of truth and weaken auditability
