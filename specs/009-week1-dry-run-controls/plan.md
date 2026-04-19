---
id: PLAN-0009
title: TradingX week-1 dry-run controls implementation plan
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-024
---

# Implementation Plan: TradingX week-1 dry-run controls

**Branch**: `codex/week1-safety-pack` | **Date**: 2026-04-19 | **Spec**: `specs/009-week1-dry-run-controls/spec.md`
**Input**: Operator-locked Sunday pack for week-1 paper safety.

## Summary

Implement the minimum production-grade week-1 control plane above the
existing local trading appliance: explicit session policy, decision
snapshots, append-only OMS journaling, deterministic submit behavior,
two-tier reconciliation, dry-run mode, watchdogs, and Sunday/Tuesday
operational gate artifacts.

## Technical Context

**Language/Version**: Python 3.11 backend, existing React/FastAPI surface  
**Primary Dependencies**: existing `alpaca-py`, `fastapi`, `uvicorn`,
`react`, `vite`, plus `exchange_calendars` and `sqlite3` from stdlib  
**Storage**: `artifacts/` for existing evidence, new `data/journal.db`,
`data/snapshots/`, and `data/policy/` for control-plane state  
**Testing**: `pytest`, contract tests, property-like adversarial tests,
frontend tests where needed, `./scripts/validate`,
`python3 scripts/check_index.py`  
**Target Platform**: one local machine, one paper account, one operator  
**Constraints**: Monday is `dry_run`, zero overnight week 1, no hot
config reload, journal is append-only, no live trading enablement

## Constitution Check

- `PASS` Principle I: the phase adds harder caps, halts, close ladder,
  reconciliation, and no-overnight posture.
- `PASS` Principle II: Monday remains dry-run and Tuesday gating is
  evidence-backed.
- `PASS` Principle III: policy, snapshot, journal, reconciliation, and
  watchdog behavior will be added test-first.
- `PASS` Principle IV: the phase centers evidence and explicit journal
  history over in-memory assumptions.
- `PASS` Principle VI and VII: no live trading enablement and no
  research-driven self-mutation are introduced.
- `PASS` Principle VIII through X: the phase is governed by versioned
  artifacts, is local-only, and preserves operator control.

## Delivery Streams

### Stream A — Policy, snapshots, and OMS path

1. `POL-001` execution policy service and snapshot persistence
2. `CAL-001` session authority with exchange calendar semantics
3. `SNAP-001` decision snapshot v1 and content-addressed store
4. `OMS-002` deterministic idempotent submit contract
5. `OMS-003` order mechanics and sizing rules
6. `DRY-001` Monday dry-run submit bypass and report plumbing

### Stream B — Journal, observability, and safety

1. `OBS-001` structured logging and veto observability
2. `OMS-001` SQLite WAL journal and single-writer lock
3. `REC-001` two-tier reconciliation and recovery state flow
4. `OUT-001` broker/data watchdogs and cycle budget handling

### Convergence

`RUN-001` runs after both streams converge and owns the Sunday rehearsal,
synthetic drills, premortem artifact, Tuesday gates, and reproducibility
audit.
