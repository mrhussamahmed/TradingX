---
id: DESIGN-0007
title: TradingX week-1 dry-run controls design
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-024
---

# TradingX week-1 dry-run controls design

## Goal

Make TradingX safe and boring for paper week 1 by adding an explicit
execution policy layer, deterministic decision snapshots, an append-only
OMS journal, two-tier reconciliation, and a hard Monday `dry_run`
posture with Tuesday go-live gates.

## Scope

This phase intentionally prioritizes operational control over new
strategy sophistication. It focuses on:

- policy snapshots with hard numeric defaults
- decision snapshots persisted before submit
- deterministic `client_order_id` derivation
- append-only SQLite journaling with WAL mode
- lightweight and full reconciliation tiers
- `dry_run`, watchdog, and close-window semantics
- rehearsal, premortem, and Tuesday gate artifacts

This phase defers deeper research orchestration, model registry
promotion, regime classification, and richer website surface expansion.

## Core runtime rules

- Monday, 2026-04-20 runs in `dry_run`.
- Tuesday, 2026-04-21 is the earliest submit date and only if all
  Tuesday gates pass.
- Week 1 trades `SPY` only.
- Entry size is `$500`, rounded down to whole shares.
- New entries halt after 3 entries/day, 2 concurrent positions, 1 entry
  per symbol per day, or any sticky daily-drawdown halt.
- The close ladder is policy data:
  - `T-15m`: stop new entries and cancel working entry orders
  - `T-10m`: marketable-limit flatten with replace loop
  - `T-5m`: escalate to IOC
  - `T-2m`: escalate to market
  - `T-0`: any open position is a critical incident

## Snapshot and journal model

Every decision cycle persists a `DecisionSnapshot` v1 before OMS submit.
The snapshot includes schema version, git SHA, dry-run posture, policy
hash, session-start equity, and every considered symbol with its terminal
reason. OMS derives `client_order_id` from the snapshot id and retry
sequence. The SQLite journal then records every order-state event as a
new row; it never rewrites history.

## Recovery model

Reconciliation runs:

- at startup
- at every cycle in lightweight form
- after every order-state transition
- at session boundaries
- after any divergence, watchdog trip, or operator clearance request in
  full form

Any unresolved divergence enters `recovery_required`, blocks new
entries, emits a critical alert, and requires operator clearance plus a
fresh reconciliation pass before return to nominal state.

## Testing and readiness

This phase requires:

- property tests for policy invariants
- adversarial scenario tests for caps, sticky halts, and lock rejection
- synthetic HALT, REJECT, and RECOVERY drills
- a Sunday rehearsal checklist artifact
- a Monday dry-run report artifact
- a Tuesday go-live gate artifact
