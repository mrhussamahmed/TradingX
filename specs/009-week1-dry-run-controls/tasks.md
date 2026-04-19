---
id: TASKS-0009
title: TradingX week-1 dry-run controls task list
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-024
---

# Tasks: TradingX week-1 dry-run controls

**Input**: Design and spec documents from `/specs/009-week1-dry-run-controls/`

## Stream A — Policy, snapshots, and order path

- [ ] T001 `POL-001` Add execution policy snapshot defaults, close ladder,
      and adversarial tests
- [ ] T002 `CAL-001` Add exchange-calendar-backed session authority and
      pre-market wait semantics
- [ ] T003 `SNAP-001` Add decision snapshot v1 schema and
      content-addressed snapshot persistence
- [ ] T004 `OMS-002` Add deterministic `client_order_id` generation and
      query-before-resubmit behavior
- [ ] T005 `OMS-003` Add explicit order mechanics, quote sanity, and
      whole-share sizing rules
- [ ] T006 `DRY-001` Wire Monday `dry_run` through the OMS and generate
      the dry-run report artifact

## Stream B — Journal, observability, and safety

- [ ] T007 `OBS-001` Add structured JSON logging, veto reason counters,
      and cycle correlation tagging
- [ ] T008 `OMS-001` Add SQLite WAL journal, append-only event schema,
      and single-writer lock
- [ ] T009 `REC-001` Add lightweight/full reconciliation tiers and the
      `recovery_required -> clearance_requested -> reconciling` state
      flow
- [ ] T010 `OUT-001` Add broker/data watchdogs, cycle budget handling,
      and `cycle_overrun` events

## Convergence

- [ ] T011 `RUN-001` Add Sunday rehearsal, HALT/REJECT/RECOVERY drills,
      Monday replay reproducibility, and Tuesday go-live gates
- [ ] T012 Update docs, state, architecture map, and operator manual
- [ ] T013 Run `./scripts/validate`, `python3 scripts/check_index.py`,
      and reproducibility audit commands
