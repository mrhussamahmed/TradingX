---
id: PLAN-0010
title: TradingX operator control plane implementation plan
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-026
---

# Implementation Plan: TradingX operator control plane

**Branch**: `codex/tel-001-sup-001` | **Date**: 2026-04-19 | **Spec**:
`specs/010-operator-control-plane/spec.md`
**Input**: TEL-001 and SUP-001 for week-1 paper operation.

## Summary

Add a minimal local operator control plane above the week-1 safety pack:
one supervisor owns the long-running child scheduler/runtime, while a
single-authorized-chat Telegram polling surface and CLI fallback can
inspect state and request halt, resume, flatten, and kill actions.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: existing `alpaca-py`, `httpx`, `sqlite3`,
`multiprocessing`, `fastapi`, React app unchanged  
**Storage**: `data/control/`, `data/journal.db`,
`artifacts/operator_platform/supervisor/`, existing artifact roots  
**Testing**: `pytest`, `./scripts/validate`,
`python3 scripts/check_index.py`  
**Target Platform**: one local machine, one paper account, one operator  
**Constraints**: local-only, week-1 dry-run defaults remain
authoritative, Telegram is optional, no live trading enablement

## Constitution Check

- `PASS` Principle I and II: TEL/SUP improves operator control without
  relaxing paper-only or dry-run-first safety.
- `PASS` Principle III: command routing, authorization, and child
  lifecycle will be added test-first.
- `PASS` Principle IV: the supervisor reuses persisted journal and
  artifact state rather than in-memory-only control.
- `PASS` Principle VIII through X: the phase adds versioned artifacts,
  stays local-only, and preserves explicit operator authority.

## Delivery

1. Add the governed artifact chain for TEL/SUP.
2. Add failing tests for control state, Telegram authorization/dispatch,
   and supervisor child lifecycle.
3. Implement file-backed operator control state and today-summary
   helpers.
4. Implement the Telegram polling/command plane.
5. Implement the supervisor with child start/stop/restart and flatten
   actions.
6. Wire new CLI entrypoints and week-1 docs, then validate and promote.
