---
id: DESIGN-0006
title: TradingX local trading appliance design
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-022
---

# TradingX local trading appliance design

## Goal

Turn TradingX from a collection of local commands into a supervised
local trading appliance with:

- one operator-facing start/stop surface in the website
- an explicit runtime-host state machine
- deterministic first-run symbol selection across the configured
  universe
- governed strategy/model activation instead of a hard-coded live
  strategy binding
- asynchronous warmup, analytics, and learning that do not sit on the
  latency-critical path

## Phase scope

This phase does **not** physically rewrite TradingX into Rust or
independent daemons. It codifies the production architecture contract
and implements a Python reference slice that matches it closely enough
to make the system safer, more governable, and more operator-friendly
today.

The hot path remains local and in-process. Logical service ownership,
runtime states, and activation rules become explicit artifacts and code
contracts now, while future physical split points remain clear.

## Runtime topology

TradingX is modeled as four local runtimes:

- `Runtime Host`: supervision, startup sequencing, health, and operator
  actions
- `Execution Kernel`: market ingress, feature preparation, signal
  generation, opportunity ranking, risk, OMS, and broker execution
- `Intelligence Runtime`: historical warmup, post-trade analytics,
  statistical learning, and proposal generation
- `Operator Runtime`: FastAPI plus the local website and read models

For this phase, the `Runtime Host`, `Execution Kernel`, and
`Intelligence Runtime` are implemented inside the existing Python
process family with strict contracts and explicit ownership boundaries.
The website continues to be the single operator surface.

## Hard ownership rules

- The browser never talks to Alpaca or order state directly.
- Only the runtime host may start, stop, or transition the bot between
  runtime states.
- Only the OMS/execution path may mutate order lifecycle state.
- Only the portfolio gateway may declare canonical local account state.
- Only governance may activate a strategy or model-weight snapshot.
- Learning may propose snapshots; it may not self-deploy them.
- Hot-path decisioning must not synchronously wait on learning or report
  generation.

## Startup state machine

The runtime host owns these explicit states:

- `idle`
- `bootstrapping`
- `historical_warmup`
- `broker_sync`
- `feature_ready`
- `strategy_ready`
- `trading_ready`
- `degraded`
- `halted`
- `stopping`

The bot may submit paper orders only from `trading_ready`.

To reach `trading_ready`, all of the following must be true:

- real paper credentials are loaded
- broker/account state can be read
- regular-hours session awareness is available
- warmup history exists for the active universe
- an active strategy activation record exists
- an approved model-weight snapshot exists or the activation record
  explicitly declares a deterministic fallback
- no unresolved stale-state or kill-switch failure is present

If any prerequisite fails, the runtime host fails closed into
`halted` or `degraded`.

## First-run opportunity selection

The first action on a fresh runtime must be deterministic and auditable.

1. Load the configured symbol universe.
2. Pull warmup history for each symbol and the benchmark.
3. Build feature windows and liquidity/spread statistics.
4. Filter out ineligible symbols:
   - stale data
   - insufficient warmup bars
   - price below floor
   - spread too wide
   - liquidity below the hard floor
5. Score each remaining symbol with the active strategy runtime.
6. Apply model/regime/liquidity weights.
7. Rank opportunities.
8. Pass the top ranked candidate through risk approval.
9. If no candidate clears the deploy threshold, emit `NO_TRADE`.
10. Otherwise send one bounded order intent to the current loop
    controller.

Tie-breaks are deterministic:

- higher liquidity wins
- then lower spread
- then lower portfolio overlap
- then lexical symbol order

## Strategy and model governance

Live paper execution no longer relies on a hidden hard-coded strategy
binding. It relies on two explicit records:

- `StrategyActivationRecord`
- `ModelWeightSnapshot`

The activation record declares:

- active strategy id and version
- approved universe
- deploy threshold
- fallback behavior if no learned snapshot is approved
- activation status

The model-weight snapshot declares:

- immutable weights for signal, regime, liquidity, spread, volatility,
  portfolio overlap, and execution cost terms
- minimum supporting sample size
- approval status

Learning produces **proposals**, not live mutations. Governance accepts
or rejects those proposals, then the runtime host loads the approved
snapshot at a safe boundary.

## Quant and learning model

This phase introduces a tighter split:

- `Quant Kernel`: deterministic math used by warmup, scoring, and
  analytics
- `Learning Service`: asynchronous post-trade scoring and weight
  proposal generation

The learning output is intentionally modest and governed:

- build labels from closed trades and market movement
- calculate directional hit rate, edge capture, and slippage-adjusted
  quality
- propose adjusted weights only when the sample is large enough and the
  improvement is statistically meaningful
- never auto-activate a proposal

## Operator experience

The website gains a runtime-host control surface that can:

- show appliance state and readiness reason
- start the bot
- stop the bot
- surface the active strategy activation record
- surface the active model-weight snapshot
- show the latest opportunity-ranking decision
- show the latest learning proposal

The existing paper-service and scheduler controls remain available, but
the local trading appliance becomes the primary operator workflow.

## Testing shape

- unit tests for runtime-state transitions and fail-closed behavior
- unit tests for historical warmup summary building
- unit tests for deterministic opportunity ranking and tie-breaks
- unit tests for model-weight proposal significance gating
- unit tests for activation-record loading and fallback behavior
- API and runtime-manager tests for start/stop/state flows
- frontend tests for the runtime-host panel and readiness states

