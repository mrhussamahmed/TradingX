---
id: ADR-0016
title: Use a supervised local trading appliance runtime with governed activation records
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-022
---

# ADR-0016: Use a supervised local trading appliance runtime with governed activation records

## Context

TradingX has grown into a capable local trading system, but its main
runtime posture is still command-centric:

- the live paper strategy binding is implicit
- strategy selection across the universe is not formalized
- startup readiness is not modeled as a state machine
- post-trade learning does not feed a governed activation workflow
- the website can operate subsystems, but not a single supervised bot
  runtime

The operator requires a local-first architecture that:

- hides operational complexity behind the website
- keeps latency-sensitive logic local and tight
- supports historical warmup, statistics, and learning
- prevents unsafe runtime self-mutation

## Decision

Adopt a supervised local trading appliance model with:

- a `Runtime Host` as the only controller for runtime state
- a logical `Execution Kernel` for hot-path decisioning
- explicit `StrategyActivationRecord` and `ModelWeightSnapshot`
  artifacts
- deterministic opportunity ranking across the configured universe
- asynchronous post-trade learning that produces governed proposals
  instead of live self-modification

## Consequences

### Positive

- The bot gains a precise startup/readiness model.
- Strategy and model selection become explicit artifacts instead of
  hidden in-process choices.
- First-run symbol selection becomes deterministic and reviewable.
- The website can offer a true start/stop appliance workflow.
- Learning can improve future decisions without mutating live behavior
  mid-session.

### Negative

- More artifacts and types must be maintained.
- Runtime host, activation, and learning surfaces add implementation
  complexity to the local system.
- The current phase remains a Python reference slice rather than a full
  physical split into separate runtimes.

## Alternatives considered

- Keep the current controller-centric design and only add more UI.
  Rejected because it does not solve governance or startup ambiguity.
- Fully rewrite the runtime into many local daemons immediately.
  Rejected for this phase because it would add large migration risk and
  delay operator value.
