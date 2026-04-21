---
id: DESIGN-0010
title: TradingX runtime intelligence design
version: 1.0.0
status: active
created: 2026-04-20
last_amended: 2026-04-21
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-21
---

# Runtime Intelligence Design

Date: 2026-04-20
Status: Proposed
Scope: Mission Control enhancement for runtime clarity during supervised dry-run operation

## Purpose

This feature adds a new `Runtime Intelligence` section to the Mission
Control workspace so the operator can immediately answer:

- Is the bot actually active or idle?
- Why did it trade or not trade?
- What is happening for each monitored symbol?
- What should I do next, if anything?

The design is intentionally operator-first. It must reduce ambiguity in
multi-symbol dry-run sessions such as `SPY,QQQ,IWM` without turning
Mission Control into a research terminal.

## Problem

The current Mission Control experience still compresses too much state
into one bot-level summary.

That causes four usability problems:

1. The operator cannot quickly tell whether a `no_trade` result came
   from one symbol, all symbols, or a blocked symbol.
2. The runtime can appear quiet without clearly explaining whether it is
   `idle`, actively evaluating, waiting for the next cycle, or holding
   a position.
3. The operator does not have a clear symbol-by-symbol explanation of
   readiness, score, and threshold gap.
4. The UI does not produce a concise recommended next action plus a
   brief explanation.

## Chosen Direction

Use the `Balanced Operator Intelligence` layout.

This keeps one top-level runtime heartbeat for fast scanning, then adds
symbol-specific truth and a compact explanation layer below it.

The section will contain four blocks in this order:

1. `Bot Heartbeat`
2. `Runtime Truth`
3. `Symbol Heartbeat`
4. `Decision Ladder` and `Operator Guidance`

## Information Architecture

### 1. Bot Heartbeat

This remains a bot-level summary rather than splitting into separate
symbol heartbeats at the top.

It shows:

- current runtime state
- last decision
- current exposure
- cadence
- next evaluation timestamp
- live countdown clock
- last evaluation timestamp

This block answers: `What is the bot doing right now?`

### 2. Runtime Truth

This is a compact operational truth panel with facts that should not be
inferred from surrounding UI.

It shows:

- market open/closed posture
- paper vs live mode
- runtime active vs idle
- open positions count
- pending orders count
- freshness of the latest evaluation

This block answers: `Is the runtime truly active, and what is the
current operating envelope?`

### 3. Symbol Heartbeat

This is a row-based panel with one row per configured symbol in the
active universe.

For `SPY,QQQ,IWM`, each row shows:

- symbol
- status
- latest score
- threshold gap
- short reason
- warmup state
- exposure state

Supported statuses:

- `Ready`
- `Below threshold`
- `Blocked`
- `Selected`
- `In position`

Reason examples:

- `Score below deploy threshold`
- `Warmup incomplete`
- `Already held in portfolio`
- `Selected for deployment`

This block answers: `What is happening per symbol?`

### 4. Decision Ladder

This is the compact explanation panel for the current ranking.

For each ranked symbol, show:

- rank
- symbol
- final score
- deploy threshold
- threshold gap
- primary penalty driver
- selected / not selected

This block answers: `Why did the bot choose this outcome?`

### 5. Operator Guidance

This block uses the user-selected guidance style: `Both`.

That means it shows:

- a direct recommendation first
- a short analytical explanation underneath

Example:

- `No action needed`
- `All three symbols were evaluated. SPY ranked highest but remained
  below threshold; IWM is still blocked by warmup.`

Supported recommendation states:

- `No action needed`
- `Monitor next cycle`
- `Investigate warmup failure`
- `Review runtime blocker`
- `Pause bot and inspect`
- `Watch active position`

This block answers: `What should I do next, and why?`

## Data Sources

All values must be derived from existing runtime evidence. No mock or
invented symbol states are allowed.

Primary inputs:

- runtime host state
- latest opportunity selection
- latest historical warmup
- latest strategy activation
- latest completed service cycle
- current service/runtime cadence from config
- current open positions from latest service evidence

## Behavioral Rules

### Runtime-level truth

- `Waiting for next evaluation` must only appear when the runtime is
  actually active.
- If the runtime is `idle`, the heartbeat must explicitly say `Idle`
  and the next evaluation must not be shown as scheduled.
- If the runtime is blocked or halted, the top block must surface that
  before any symbol-level interpretation.

### Symbol-level truth

- Symbol rows must be built from the latest selection and warmup data.
- A symbol cannot appear `Ready` if warmup marks it blocked.
- A symbol cannot appear `Selected` unless it is the current selected
  symbol in the latest selection artifact.
- A symbol in an open position should surface `In position`, even if the
  latest score is below threshold.

### Guidance

- Guidance must be deterministic and rules-based.
- Guidance should not invent operational urgency.
- Guidance should only recommend an action when the evidence supports it.

## UI Requirements

- Preserve the current dark theme and overall Mission Control visual
  language.
- Add the new section without making the page feel like an analyst
  workbook.
- Optimize for fast scan first, explanation second.
- Use tables, cards, and badges rather than dense prose.
- Keep the symbol table legible on normal laptop widths.
- Keep the countdown visibly live while the runtime is active.

## Implementation Notes

Backend work:

- extend the runtime heartbeat read model to expose runtime truth,
  symbol heartbeat rows, decision ladder rows, and guidance payload
- add any missing endpoint fields needed by Mission Control

Frontend work:

- add a new `Runtime Intelligence` section inside Mission Control
- render the four blocks in the chosen order
- keep the existing top heartbeat but make it the entry point into the
  new richer section
- update the countdown so it ticks locally without requiring a full page
  reload

Testing:

- unit tests for runtime-intelligence read model derivation
- contract coverage for any new API payload fields
- Mission Control UI tests for idle, waiting, blocked, and multi-symbol
  states

## Out of Scope

This feature does not include:

- a separate page for per-symbol analytics
- full historical per-symbol trend charts
- strategy research expansion
- benchmark analytics changes
- trade replay redesign

Those can come later if the operator needs a deeper analyst workflow.

## Acceptance Criteria

The feature is complete when:

1. Mission Control clearly distinguishes `Idle`, `Evaluating`,
   `Waiting for next evaluation`, `Active position`, and `Blocked`.
2. A configured universe such as `SPY,QQQ,IWM` shows one row per symbol
   with real status, score, and reason.
3. The operator can tell why the bot stayed flat without opening raw
   artifacts.
4. The operator guidance block provides a concise recommendation plus an
   explanation.
5. No fake timers or fake symbol states appear when the runtime is not
   active.
