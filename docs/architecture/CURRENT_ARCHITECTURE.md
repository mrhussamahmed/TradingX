---
id: ARCHMAP-0001
title: Current architecture map
version: 1.4.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: ARCHMAP-0001@1.3.0
superseded_by: null
author_session: SESS-2026-04-19-026
---

# Current Architecture Map

This document is the one-page pointer for future TradingX development.
Use it to find the canonical files for runtime and appliance work
without guessing across older specs or implementation phases.

## Purpose

When future work touches runtime startup, strategy activation, first-run
selection, learning proposals, scheduler interaction, or the local
website's bot controls, start here first.

This file is a pointer, not a replacement for the governing artifacts.
If anything here conflicts with a higher-authority artifact, the
higher-authority artifact wins and this file MUST be updated in the same
session.

## Authority Order

For runtime and appliance work, read in this order:

1. [`.specify/memory/constitution.md`](</Users/ahmedabd/Desktop/AI Projects/TradingX/.specify/memory/constitution.md:1>)
2. [docs/INDEX.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/INDEX.md:1)
3. [docs/handover/STATE.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/handover/STATE.md:1)
4. [ADR-0016](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/adrs/ADR-0016-local-trading-appliance-runtime-host.md:1)
5. [SPEC-0008](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/008-local-trading-appliance/spec.md:1)
6. [PLAN-0008](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/008-local-trading-appliance/plan.md:1)
7. [TASKS-0008](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/008-local-trading-appliance/tasks.md:1)
8. [ADR-0017](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/adrs/ADR-0017-week1-dry-run-safety-control-plane.md:1)
9. [SPEC-0009](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/009-week1-dry-run-controls/spec.md:1)
10. [PLAN-0009](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/009-week1-dry-run-controls/plan.md:1)
11. [TASKS-0009](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/009-week1-dry-run-controls/tasks.md:1)
12. [ADR-0018](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/adrs/ADR-0018-telegram-operator-supervisor-control-plane.md:1)
13. [SPEC-0010](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/010-operator-control-plane/spec.md:1)
14. [PLAN-0010](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/010-operator-control-plane/plan.md:1)
15. [TASKS-0010](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/010-operator-control-plane/tasks.md:1)
16. [DATAMODEL-0008](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/008-local-trading-appliance/data-model.md:1)
17. [DATAMODEL-0009](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/009-week1-dry-run-controls/data-model.md:1)
18. [DATAMODEL-0010](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/010-operator-control-plane/data-model.md:1)
19. [CONTRACT-0009](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/008-local-trading-appliance/contracts/local_trading_appliance_api.md:1)
20. [CONTRACT-0010](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/009-week1-dry-run-controls/contracts/week1_dry_run_controls.md:1)
21. [CONTRACT-0011](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/010-operator-control-plane/contracts/operator_control_plane.md:1)
22. [RUNBOOK-0003](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/operations/operator_manual.md:1)

## Canonical Runtime Model

TradingX currently operates as a local supervised trading appliance with
these core runtime responsibilities:

- `Runtime Host` owns startup, shutdown, readiness state, and fail-closed
  transitions.
- `Strategy Activation` decides which strategy and weight snapshot are
  allowed to drive live paper behavior.
- `Historical Warmup` prepares benchmark-relative readiness for the
  configured universe before the appliance can trade.
- `Opportunity Selection` ranks the current universe deterministically
  and may legally return `no_trade`.
- `Learning` is proposal-only. It can emit candidate model-weight
  proposals but cannot mutate the active runtime automatically.
- `Week-1 Safety Control Plane` stamps immutable policy snapshots,
  decision snapshots, and append-only OMS journal events before the
  broker path or `dry_run` simulation.
- `Operator Supervisor` owns the week-1 child lifecycle, persistent halt
  and kill requests, and optional Telegram command polling.
- `Website Control` is the preferred operator entry point and remains
  read-only unless write mode is explicitly enabled.

## Canonical Implementation Files

These files are the source of truth for appliance/runtime behavior:

- Runtime host lifecycle:
  [src/tradingx/runtime_host.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/runtime_host.py:1)
- Activation and approved weight loading:
  [src/tradingx/activation.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/activation.py:1)
- Historical warmup:
  [src/tradingx/historical.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/historical.py:1)
- Deterministic ranking and first-run selection:
  [src/tradingx/opportunity.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/opportunity.py:1)
- Learning proposals:
  [src/tradingx/learning.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/learning.py:1)
- Week-1 policy and close-ladder defaults:
  [src/tradingx/policy.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/policy.py:1)
- Decision snapshot v1 persistence:
  [src/tradingx/snapshots.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/snapshots.py:1)
- Append-only OMS journal:
  [src/tradingx/journal.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/journal.py:1)
- File-backed operator control state:
  [src/tradingx/operator_control.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/operator_control.py:1)
- Week-1 Telegram command plane:
  [src/tradingx/telegram_operator.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/telegram_operator.py:1)
- Operator supervisor and child lifecycle:
  [src/tradingx/supervisor.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/supervisor.py:1)
- Single-writer runtime lock:
  [src/tradingx/process_lock.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/process_lock.py:1)
- Exchange-calendar-backed session authority:
  [src/tradingx/data.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/data.py:1)
- Explicit marketable-limit order mechanics:
  [src/tradingx/execution.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/execution.py:1)
  [src/tradingx/controller.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/controller.py:1)
- Shared appliance math:
  [src/tradingx/quant.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/quant.py:1)
- Runtime-aware service orchestration:
  [src/tradingx/service.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/service.py:1)
- Dry-run reporting and Tuesday gate evaluation:
  [src/tradingx/dry_run_report.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/dry_run_report.py:1)
  [src/tradingx/week1_drills.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/week1_drills.py:1)
  [src/tradingx/week1_readiness.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/week1_readiness.py:1)
- CLI appliance entry point:
  [src/tradingx/__main__.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/__main__.py:1)
- API surface and local website orchestration:
  [src/tradingx/web/app.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/web/app.py:1)
  [src/tradingx/web/runtime.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/web/runtime.py:1)
  [src/tradingx/web/readmodels.py](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/src/tradingx/web/readmodels.py:1)
  [webapp/src/App.tsx](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/webapp/src/App.tsx:1)

## What Is Historical Context, Not Primary Runtime Truth

These artifacts still matter, but they are not the first place to look
for appliance/runtime behavior:

- [SPEC-0001](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/001-paper-trading-bot/spec.md:1)
  defines the Stage 1 product baseline and acceptance intent.
- [SPEC-0003](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/003-operator-platform/spec.md:1)
  defines the operator-platform expansion.
- [SPEC-0004](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/004-gate3-operations-evidence/spec.md:1),
  [SPEC-0005](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/005-replay-slippage-evidence/spec.md:1),
  [SPEC-0006](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/006-market-day-automation/spec.md:1),
  and [SPEC-0007](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/specs/007-market-day-scheduler/spec.md:1)
  remain authoritative for their own bounded flows, but runtime-appliance
  control now anchors on `ADR-0016` and the `0008` artifact chain.

## Non-Canonical Inputs To Ignore Unless Explicitly Adopted

- Untracked notes are not governed artifacts.
- In particular,
  [docs/strategy_evaluation_2026-04-18.md](</Users/ahmedabd/Desktop/AI Projects/TradingX/docs/strategy_evaluation_2026-04-18.md:1>)
  is not part of the indexed architecture contract.

## Anti-Drift Update Rules

If future work changes any of these, update this file in the same
session:

- runtime-host states or startup sequence
- activation-record or model-snapshot behavior
- first-run selection or ranking/tie-break rules
- learning proposal behavior or its safety boundaries
- week-1 policy defaults, decision snapshot schema, or OMS journal rules
- operator supervisor state, Telegram command semantics, or control-file
  behavior
- website runtime-host controls or API endpoints
- the canonical authority order for runtime/appliance work

Also update the companion governed artifacts when relevant:

- runtime behavior changes: `SPEC-0008`, `PLAN-0008`, `TASKS-0008`
- contract or payload changes: `DATAMODEL-0008`, `CONTRACT-0009`
- operator flow changes: `RUNBOOK-0003`
- project-wide current-state changes: `STATE.md`
