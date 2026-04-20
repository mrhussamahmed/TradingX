---
id: PLAN-0011
title: TradingX operator platform redesign implementation plan
version: 1.0.0
status: active
created: 2026-04-20
last_amended: 2026-04-20
supersedes: null
superseded_by: null
author_session: SESS-2026-04-20-OPR
---

# Implementation Plan: TradingX operator platform redesign

**Branch**: `011-operator-platform-redesign` | **Date**: 2026-04-20 | **Spec**: `docs/superpowers/specs/2026-04-20-operator-platform-redesign-design.md`
**Input**: Design specification from `/docs/superpowers/specs/2026-04-20-operator-platform-redesign-design.md`

## Summary

Rebuild the current local operator platform into a professional,
truthful, darker Carbon/Steel control surface with three distinct
workspaces:

- Mission Control
- Portfolio
- Research

The redesign will not be implemented as incremental feature sprawl
inside the current monolithic frontend. Instead, the work will establish
a modular React workspace architecture, introduce workspace-oriented
backend read models, and migrate the app page by page so the operator
experience becomes clearer, more honest, and more professionally usable.

The plan deliberately separates live operations, performance judgment,
and replay/diagnostics. It also removes misleading analytics behavior by
enforcing real-data-only portfolio surfaces and explicit
available/partial/stale/unavailable states.

## Technical Context

**Language/Version**: Python 3.11 backend, TypeScript/React frontend  
**Primary Dependencies**: `fastapi`, `pydantic`, `uvicorn`, `react`,
`vite`, `vitest`, current local web tooling; likely one richer
charting/runtime query layer added during implementation if justified  
**Storage**: existing artifacts under `artifacts/`, runtime logs under
`data/`, docs under `docs/`, current SPA assets under `webapp/`  
**Testing**: `pytest`, FastAPI contract tests, frontend unit tests,
targeted browser validation, `ruff`, `mypy --strict` where applicable,
`black`, `npm run build`, repo validation scripts  
**Target Platform**: local browser against the existing FastAPI server
bound to `127.0.0.1` by default  
**Project Type**: one Python backend plus one local React SPA  
**Constraints**: local-only, no live-trading enablement, no fake
portfolio analytics, read/write safety controls preserved, migration
must coexist with in-progress operator platform work  
**Scale/Scope**: one operator, one paper-first control surface, one
modular redesign of the current product

## Constitution Check

- `PASS` Principle I: the redesign increases operational clarity without
  weakening existing safety controls.
- `PASS` Principle II: benchmark-relative truth and evidence-first
  reasoning are strengthened rather than softened.
- `PASS` Principle III: the redesign will proceed with failing tests for
  backend contracts, UI states, and chart/interaction behavior.
- `PASS` Principle IV: authoritative state remains artifact- and
  readmodel-backed, while the UI becomes more explicit about freshness
  and completeness.
- `PASS` Principle V: this remains a single local app plus single local
  SPA rather than a duplicated UI stack.
- `PASS` Principle VI and VII: the redesign does not add manual trading
  or self-modifying control paths.
- `PASS` Principle VIII through X: new artifacts remain versioned, the
  plan stays aligned with the approved design spec, and work remains
  inside the local operator platform scope.

## Project Structure

### Documentation

```text
specs/011-operator-platform-redesign/
└── plan.md

docs/superpowers/specs/
└── 2026-04-20-operator-platform-redesign-design.md
```

### Target Source Structure

```text
src/tradingx/web/
├── app.py
├── readmodels.py
├── runtime.py
├── ...

webapp/src/
├── app/
├── design-system/
├── charts/
├── data/
├── features/
├── workspaces/
│   ├── mission-control/
│   ├── portfolio/
│   └── research/
├── api.ts
├── types.ts
└── ...
```

### Migration Boundary

The current implementation in `webapp/src/App.tsx` and `webapp/src/App.css`
will be treated as a migration source, not the permanent end state.

Refactoring target:

- move layout/state orchestration out of the monolithic app file
- isolate workspace-specific components and routes
- centralize design-system primitives
- centralize data-adapter logic for freshness/completeness handling
- centralize chart primitives and tooltip/crosshair behavior

## Delivery Strategy

The redesign will be executed in layered phases. Each phase must leave
the local app in a working state and avoid half-migrated operator
surfaces that mix the old and new paradigms unpredictably.

### Phase 2 — Shell and design-system foundation

Goals:

- establish the new Carbon/Steel token system
- build the global shell and workspace switcher
- define reusable primitives for status chips, metric cards, tables,
  panels, drawers, empty states, stale/unavailable states, and action
  rails
- create chart primitives capable of axes, legends, tooltips, and
  crosshair behavior

Work:

- introduce `design-system/` and `charts/` structure in `webapp/src/`
- split the current shell/navigation logic out of `App.tsx`
- create shared app-level routing/state orchestration in `app/`
- implement data-state display components for `available`, `partial`,
  `stale`, and `unavailable`
- replace cyan/gold styling with the approved Carbon/Steel palette

Exit criteria:

- the app boots with the new shell
- the global workspace switcher exists
- shared primitives are available for the later workspace migrations
- charts can render thin institutional-style lines with labeled axes and
  value tooltips

### Phase 3 — Mission Control rebuild

Goals:

- make Mission Control the professional live-ops default workspace
- remove irrelevant research/performance clutter from the operating
  surface
- preserve Operator Plus controls with bounded safety

Work:

- implement `Mission Control` workspace pages:
  - Market Desk
  - Execution Queue
  - Exposure & Guardrails
  - Live Book
  - Operator Alerts
- migrate runtime state, alerts, positions, orders, and risk surfaces
  into the new layout
- redesign action affordances around pause/resume, sync retry,
  recovery, reruns, and acknowledge actions
- tighten alert language so every surfaced issue implies a concrete
  operator meaning

Backend work:

- add or reshape mission-control-oriented snapshots where the current
  operator snapshot is too mixed or insufficiently explicit
- expose freshness and unavailable reasons where operationally useful

Exit criteria:

- Mission Control is usable as a standalone market-hours cockpit
- it answers what is happening, whether intervention is needed, and what
  to do next
- no benchmark or replay-heavy content dominates this workspace

### Phase 4 — Portfolio Guided mode and real-data truth layer

Goals:

- rebuild Portfolio as the performance judgment workspace
- enforce real-data-only analytics behavior
- ship the default Guided reading mode before denser analyst behavior

Work:

- implement `Portfolio` pages:
  - Performance Summary
  - Benchmark Comparison
  - Strategy Comparison
  - Drawdowns
  - Performance Diagnostics
- add KPI interpretation cards/drawers
- add benchmark comparison charts and tables
- add explicit controls:
  - Benchmark Selector
  - Strategy Filter
  - Metric View
  - Compare Against
  - date window selector
- replace any synthetic/fallback runtime analytics with honest
  unavailable/partial states

Backend work:

- split current broad performance snapshot toward:
  - portfolio summary snapshot
  - benchmark comparison snapshot
  - strategy comparison snapshot
  - performance diagnostics snapshot
- include completeness/freshness/unavailable reason fields explicitly

Exit criteria:

- Portfolio default mode answers whether the bot is achieving its goal
- every major metric explains whether the current state is good, bad, or
  mixed for the bot objective
- fake analytics no longer appear in runtime UI

### Phase 5 — Portfolio Analyst mode and advanced comparison depth

Goals:

- add a deliberate density toggle for expert review without making the
  default workflow overwhelming

Work:

- implement `Guided / Analyst` toggle inside Portfolio
- expand benchmark comparison depth:
  - rolling ratios
  - multi-benchmark compare
  - period-by-period outperformance
  - richer drawdown comparisons
- expand strategy comparison depth:
  - denser tables
  - regime and symbol drilldowns
  - contribution to drawdown and risk consumption

Exit criteria:

- Guided mode remains clean and interpretable
- Analyst mode adds depth without inventing a second mental model
- metric explanations remain accessible from dense views

### Phase 6 — Research rebuild

Goals:

- turn Research into a real replay-and-diagnostics workspace
- move technical investigation and audit trails out of the operating
  surface

Work:

- implement `Research` pages:
  - Replay & Diagnostics Hub
  - Replay Trace
  - Evidence Explorer
  - System Diagnostics
  - Saved Layouts
- redesign replay around causal narrative:
  - signal
  - strategy
  - risk gates
  - order flow
  - fill outcome
  - aftermath
- redesign diagnostics around technical root cause categories:
  - lag
  - feed health
  - drift
  - model freshness
  - queue backlog
  - runtime stability
- introduce saved review layouts here if time allows, not in Mission
  Control

Backend work:

- expose replay- and diagnostics-oriented payloads more explicitly
- unify evidence explorer responses around functional categories rather
  than raw file chaos where needed

Exit criteria:

- Research clearly answers what happened and why
- replay and diagnostics are not mixed into the live ops workspace
- saved layouts, if shipped in this phase, remain bounded to Research

### Phase 7 — Integration, migration cleanup, and polish

Goals:

- remove leftover mixed paradigms
- unify interaction quality across workspaces
- validate the redesigned product end to end

Work:

- remove obsolete views/components/styles from the current monolithic app
- unify command palette, global search, and drawer behavior
- normalize loading, stale, partial, and unavailable states
- tune information density, spacing, chart polish, and copy
- verify keyboard navigation and workflow transitions between workspaces

Exit criteria:

- the old overloaded UI patterns are removed or fully hidden
- the app feels like one professional platform with three distinct jobs
- the workspace transitions are clear and predictable

## Test and Validation Strategy

### Backend

- add failing contract tests for each new workspace-oriented endpoint
- validate freshness/completeness/unavailable fields explicitly
- verify no fake portfolio analytics are emitted in runtime paths

### Frontend

- add failing component/workspace tests for:
  - workspace switching
  - Mission Control action affordances
  - Portfolio Guided vs Analyst toggle
  - KPI interpretation drawers
  - unavailable/partial/stale display states
  - chart legends/axes/tooltips presence where applicable

### UI Validation

- run targeted browser checks on all three workspaces
- verify that charts render with labeled axes and hover values
- verify that Portfolio does not populate unavailable metrics with
  placeholder numbers
- verify that Mission Control remains fast to scan under simulated alert
  conditions

### Quality Gates

Before final merge of the redesign work:

- `pytest` targeted backend suites pass
- frontend tests pass
- `npm run build` passes
- style/lint/type checks pass
- live local validation confirms the three-workspace architecture and
  truthful data behavior

## Risks and Mitigations

### Risk 1 — Monolithic migration drag

The current UI is concentrated in a very large `App.tsx`, so partial
migration could create a confusing hybrid state.

Mitigation:

- migrate through a new shell/workspace boundary first
- move sections into dedicated modules phase by phase
- remove old surfaces as soon as the new one is stable

### Risk 2 — Backend payload ambiguity

Current broad read models make the frontend guess too much about data
truth and completeness.

Mitigation:

- introduce explicit workspace-oriented payloads
- make freshness/completeness first-class response fields

### Risk 3 — Overbuilding charts too early

Chart polish can absorb time before the workspace architecture is sound.

Mitigation:

- establish one capable chart primitive layer in Phase 2
- use it consistently
- defer low-value specialty views until after Guided Portfolio and
  Mission Control are stable

### Risk 4 — Analytics honesty regression

The current pressure to “fill the screen” could lead to misleading
fallbacks.

Mitigation:

- enforce the data-state model in both backend and frontend tests
- treat missing real data as a first-class design case, not a failure to
  hide

## Out of Scope

This plan does not include:

- manual order entry
- discretionary trade placement from the UI
- broad raw config editing in the main operator surface
- pretending unavailable portfolio analytics are real
- shipping every advanced quant metric in the first implementation wave

## Final Outcome

When complete, TradingX will present:

- one product shell
- three distinct professional workspaces
- clearer operator workflows
- benchmark-aware and attribution-literate performance review
- deeper replay and diagnostics without cluttering live operations
- a darker, calmer, more institutional visual system
- an honest relationship between what the UI shows and what the system
  actually knows
