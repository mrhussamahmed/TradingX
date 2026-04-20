---
id: PLAN-0012
title: TradingX runtime intelligence implementation plan
version: 1.0.0
status: active
created: 2026-04-20
last_amended: 2026-04-20
supersedes: null
superseded_by: null
author_session: SESS-2026-04-20-RTI
---

# Implementation Plan: TradingX runtime intelligence

**Branch**: `main` | **Date**: 2026-04-20 | **Spec**: `docs/superpowers/specs/2026-04-20-runtime-intelligence-design.md`
**Input**: Balanced Mission Control runtime-intelligence design for supervised dry-run operation.

## Summary

Implement a focused `Runtime Intelligence` enhancement inside Mission
Control so the operator can understand, at a glance:

- whether the bot is active or idle
- why it traded or did not trade
- what is happening per symbol in `SPY,QQQ,IWM`
- what the recommended next operator action is

The implementation will extend the existing runtime heartbeat model,
derive symbol-level truth from real artifacts, and add a balanced UI
section that stays operationally clear rather than turning Mission
Control into a research surface.

## Technical Context

**Language/Version**: Python backend, TypeScript/React frontend  
**Primary Dependencies**: existing FastAPI readmodels, existing React
Mission Control workspace, current chart and UI primitives  
**Storage**: runtime host state, warmup artifacts, opportunity
selection artifacts, service cycle artifacts, config summary values  
**Testing**: `pytest`, FastAPI contract tests, `vitest` UI tests,
production frontend build verification  
**Target Platform**: local browser against the current TradingX control
center  
**Constraints**: no fake symbol states, no mock timing, no new control
actions, preserve current dark theme and operator-first language  
**Scope**: Mission Control only

## Constitution Check

- `PASS` Principle I: the feature increases runtime clarity without
  weakening any safety guardrail.
- `PASS` Principle II: every surfaced status remains evidence-backed and
  benchmark-style ambiguity is reduced.
- `PASS` Principle III: runtime state derivation and UI behavior will be
  added test-first.
- `PASS` Principle IV: symbol heartbeat rows are derived from existing
  persisted artifacts rather than inferred by the client.
- `PASS` Principle V: the work stays inside the single local control
  center.
- `PASS` Principle VI and VII: no live enablement and no autonomous
  self-modification are introduced.

## Delivery Strategy

The work will be implemented in three streams with a final convergence
pass.

### Stream A — Runtime intelligence backend model

Goals:

- extend the runtime heartbeat snapshot with structured runtime-truth,
  symbol-heartbeat, decision-ladder, and operator-guidance payloads
- keep all values sourced from current runtime evidence

Work:

1. Expand backend types in `src/tradingx/types.py`
2. Extend `LocalWebReadModel.build_runtime_heartbeat_snapshot()` in
   `src/tradingx/web/readmodels.py`
3. Derive runtime-truth fields from:
   - runtime host state
   - latest service cycle
   - latest selection
   - config cadence
4. Derive per-symbol rows from:
   - configured universe
   - warmup readiness
   - ranked opportunities
   - current open-position symbols
5. Derive guidance from deterministic rules

Exit criteria:

- backend exposes one runtime-intelligence payload with no fake symbol
  rows
- idle, blocked, waiting, active-position, and evaluating states are
  all distinguishable

### Stream B — Mission Control UI section

Goals:

- add the balanced `Runtime Intelligence` section to Mission Control
- preserve fast scan while making the decision logic visible

Work:

1. Add `Runtime Truth` panel
2. Add `Symbol Heartbeat` table
3. Add `Decision Ladder` panel
4. Add `Operator Guidance` panel
5. Keep the top `Bot Heartbeat` and use it as the entry point into the
   richer section
6. Preserve live countdown behavior for the next evaluation clock

Exit criteria:

- Mission Control answers bot-level and symbol-level questions in one
  pass
- the layout remains readable on normal laptop widths

### Stream C — Tests and contract alignment

Goals:

- lock the new runtime-intelligence behavior with backend and frontend
  tests

Work:

1. Add backend unit tests for:
   - idle runtime with stale last decision
   - multi-symbol selection with mixed symbol states
   - active position precedence
   - blocked and warmup-failure states
2. Extend API contract coverage for new heartbeat fields
3. Extend Mission Control UI tests for:
   - bot idle
   - waiting for next evaluation
   - multi-symbol heartbeat rows
   - guidance copy

Exit criteria:

- backend and UI states are regression-protected

## Execution Order

1. Write failing backend tests for the new runtime-intelligence
   snapshot shape and state rules
2. Implement the readmodel/type extensions until those tests pass
3. Write failing UI tests for the new Mission Control sections
4. Implement the balanced runtime-intelligence layout
5. Run final contract, UI, and build verification
6. Verify against the live local control center

## Verification Plan

Required verification:

- `uv run pytest tests/unit/test_web_readmodels.py -q`
- `uv run pytest tests/contract/test_local_web_app_api_contract.py -q`
- `npm --prefix webapp test -- --run src/App.test.tsx`
- `npm --prefix webapp run build`

Live verification:

- restart local control center
- confirm `Mission Control` shows the new section
- confirm symbol rows reflect `SPY,QQQ,IWM`
- confirm `Idle` does not show a fake next timer
- confirm active runtime shows a live countdown and symbol-level status

## Risks

1. The latest selection artifact may be older than the current runtime
   state, which can make symbol rows look stale while the runtime is
   idle.
Mitigation:
surface freshness explicitly and keep `Idle` precedence over stale
waiting language.

2. Symbol-level truth could become misleading if open-position evidence
   and latest selection disagree.
Mitigation:
give open-position state precedence over below-threshold interpretation.

3. The section could grow too dense and drift toward analyst UI.
Mitigation:
keep detailed historical trend work out of scope for this phase.

## Definition of Done

The feature is done when:

1. Mission Control contains the balanced `Runtime Intelligence` section
2. the operator can see bot-level and symbol-level truth without
   opening raw artifacts
3. the guidance block provides both a recommendation and explanation
4. all values come from real current evidence
5. tests and live local verification both pass
