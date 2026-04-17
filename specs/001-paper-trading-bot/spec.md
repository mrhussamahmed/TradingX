---
id: SPEC-0001
title: TradingX Stage 1 paper trading bot specification
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-004
---

# Feature Specification: TradingX Stage 1 Paper Trading Bot

**Feature Branch**: `001-paper-trading-bot`  
**Created**: 2026-04-17  
**Status**: Active  
**Input**: User description: "Create the Phase 1 specification for TradingX: one autonomous AI-assisted trading bot that begins with Stage 1 paper trading of US equities against a large-cap benchmark, pursues benchmark-beating risk-adjusted returns, preserves capital through non-negotiable risk controls, operates during regular US market hours without constant operator monitoring, evaluates mandatory strategy candidates under a shared adversarial methodology, and remains paper-only until all acceptance gates are passed."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run A Safe Paper Trading Bot (Priority: P1)

As the operator, I want one autonomous bot to ingest market state,
decide whether to trade, place paper orders only when all risk controls
allow it, and reconcile the resulting account state so I can observe a
real end-to-end trading loop without risking live capital.

**Why this priority**: This is the minimum valuable slice of the
product. Without a safe, autonomous paper loop, there is no trustworthy
foundation for strategy evaluation or later live deployment decisions.

**Independent Test**: Can be fully tested by running the bot in paper
mode during regular market hours and confirming that eligible trade
opportunities produce reconciled paper trades while unsafe situations
produce blocked trades with recorded evidence.

**Acceptance Scenarios**:

1. **Given** the bot is in Stage 1 paper mode and all hard risk checks
   pass, **When** a selected strategy produces a valid trade intent,
   **Then** the bot records the decision, submits a paper order, tracks
   the outcome, and reconciles cash, positions, and exposure afterward.
2. **Given** the bot is in Stage 1 paper mode and any hard risk check
   fails, **When** the strategy produces a trade intent, **Then** the
   trade is blocked, no order is submitted, and the block is recorded as
   an operator-visible safety event.
3. **Given** the bot restarts while paper positions or orders exist,
   **When** it resumes operation, **Then** it restores the latest known
   state, reconciles with the broker state, and does not create a
   duplicate order as part of recovery.

---

### User Story 2 - Evaluate Strategy Candidates Honestly (Priority: P2)

As the operator, I want the mandatory Stage 1 strategy candidates
evaluated under one shared adversarial methodology so I can decide which
approach, if any, deserves further implementation and paper-validation
focus.

**Why this priority**: The project exists to beat the benchmark on a
risk-adjusted basis. Honest candidate evaluation is the first proof that
the bot is pursuing real edge instead of just automating trades.

**Independent Test**: Can be fully tested by producing evaluation
artifacts for each mandatory strategy candidate, confirming that each
candidate receives the same benchmark comparison and adversarial checks,
and confirming that the output includes a clear keep/reject/research-
further recommendation.

**Acceptance Scenarios**:

1. **Given** the mandatory Stage 1 candidate list, **When** a candidate
   is evaluated, **Then** the system records benchmark-relative results,
   adversarial checks, assumptions, and a recommendation in a
   candidate-specific evidence artifact.
2. **Given** a candidate performs well only under favorable assumptions,
   **When** out-of-sample, cost sensitivity, or parameter sensitivity
   checks are applied, **Then** the candidate is flagged as not ready for
   promotion even if its optimistic results looked strong.
3. **Given** optional strategy candidates exist, **When** mandatory
   candidate evaluation is incomplete, **Then** optional candidates are
   not allowed to displace the mandatory evaluation sequence.

---

### User Story 3 - Stay Informed Without Watching Markets (Priority: P3)

As the operator, I want the bot to escalate material events, provide
auditable status and performance evidence, and keep live trading
disabled by default so I can supervise the system without needing to
watch markets in real time.

**Why this priority**: The bot is meant to reduce monitoring burden, not
create another screen the operator must babysit. Oversight and safe
defaults are what make autonomy usable.

**Independent Test**: Can be fully tested by triggering material events
such as a blocked trade, broker-state mismatch, or manual halt and
confirming that the operator receives a clear escalation and can inspect
the resulting evidence without enabling live trading.

**Acceptance Scenarios**:

1. **Given** a material safety or operational event occurs, **When** the
   bot identifies it, **Then** the operator receives an alert through the
   approved escalation path and the event is recorded for later review.
2. **Given** the operator reviews the bot's output, **When** they inspect
   trade history, benchmark-relative reporting, and validation evidence,
   **Then** they can understand what the bot did, why it did it, and
   whether the system is ready to advance.
3. **Given** the bot is operating in Stage 1, **When** any workflow would
   otherwise cross into live trading, **Then** the action is blocked by
   default and the system remains paper-only until formal gate approval.

### Edge Cases

- Market data is delayed, stale, or incomplete while the strategy
  produces an otherwise valid signal.
- Broker state, open orders, or position state cannot be reconciled
  cleanly after a restart or partial fill.
- A strategy candidate appears attractive before costs but fails under
  out-of-sample, regime, or sensitivity analysis.
- An operator escalation path is unavailable at the same moment a
  high-severity bot event occurs.
- A symbol passes signal logic but fails the liquidity floor, price
  floor, concentration limit, or intraday risk budget.
- The same market event could trigger repeated submissions unless the
  system proves idempotent order handling.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST operate as one autonomous trading bot that
  matures through sequential stages, with the current release limited to
  Stage 1 paper trading.
- **FR-002**: The system MUST keep live trading disabled by default and
  MUST block any transition to live capital until all formal acceptance
  gates and operator approvals are satisfied.
- **FR-003**: The system MUST evaluate the mandatory Stage 1 strategy
  candidates: trend following or time-series momentum, volatility-
  targeted allocation, and simple mean reversion.
- **FR-004**: The system MUST apply one shared adversarial evaluation
  methodology to every strategy candidate so no candidate receives a
  lighter standard of proof.
- **FR-005**: The system MUST compare candidate and realized performance
  against a large-cap US equity benchmark using risk-adjusted outcomes,
  not raw return alone.
- **FR-006**: The system MUST reject or flag any candidate whose
  performance fails honest out-of-sample, walk-forward, cost-sensitivity,
  parameter-sensitivity, or regime-behavior checks.
- **FR-007**: The system MUST restrict Stage 1 execution to regular US
  equity market hours only.
- **FR-008**: The system MUST ingest market state, validate its freshness
  and integrity, and block trading when required market or broker state
  cannot be trusted.
- **FR-009**: The system MUST enforce hard pre-trade constraints before
  every order decision, including liquidity eligibility, price-floor
  eligibility, concentration control, intraday risk budget, stale-data
  checks, stale-state checks, kill-switch status, and live-mode
  prevention.
- **FR-010**: The system MUST limit the Stage 1 tradable universe to
  liquid US equities or ETFs that satisfy the governance-imposed
  eligibility rules.
- **FR-011**: The system MUST convert trade intent into paper orders only
  and MUST reconcile order, fill, position, cash, and exposure state
  after each trading action.
- **FR-012**: The system MUST prevent duplicate or ambiguous order
  outcomes across retries, reconnects, and restarts.
- **FR-013**: The system MUST support both manual and automated trading
  halts and MUST fail closed whenever a required safety decision cannot
  be made confidently.
- **FR-014**: The system MUST produce auditable records for strategy
  evaluations, trade decisions, blocked trades, submitted paper orders,
  fills, reconciliations, benchmark comparisons, and validation results.
- **FR-015**: The system MUST notify the operator when a material safety,
  operational, or phase-advancement decision requires human attention.
- **FR-016**: The system MUST provide enough evidence for the operator to
  make an informed go or no-go decision on future live-capital
  deployment.
- **FR-017**: The system MUST keep Stage 3 crypto trading, derivatives,
  extended-hours trading, high-frequency trading, market-making, public
  control planes, and native mobile or desktop apps out of scope for this
  feature.
- **FR-018**: The system MUST keep trade decisioning auditable and MUST
  NOT depend on nondeterministic generative-AI prompts in any paper or
  live trading loop.

### Key Entities *(include if feature involves data)*

- **Strategy Candidate**: A proposed trading approach under evaluation,
  including its objective, assumptions, benchmark-relative results, and
  promotion recommendation.
- **Evaluation Evidence Pack**: The complete record of adversarial checks,
  benchmark comparison, pass or fail conclusions, and operator-facing
  rationale for one strategy candidate.
- **Trade Intent**: A proposed action to enter, exit, hold, reduce, or
  skip exposure based on the chosen strategy logic and current market
  state.
- **Paper Order Record**: The auditable record of a paper-trading action,
  including submission outcome, fills, cancellations, reconciled position
  impact, and related evidence.
- **Portfolio State**: The current view of cash, equity, positions, open
  orders, and exposure that must stay consistent with broker-reported
  state.
- **Risk Control Event**: A blocked trade, halt, stale-data condition,
  reconciliation failure, or other safety event that prevents normal
  trading flow.
- **Operator Escalation**: A message or decision request generated when
  the system detects a material event or reaches a gate that requires
  human approval.
- **Stage Promotion Decision**: The operator-facing record of whether the
  system is ready to remain in paper mode, return to design, or advance
  only after future gate satisfaction.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All three mandatory Stage 1 strategy candidates receive a
  completed evidence pack with the same adversarial evaluation checklist
  before any strategy is recommended for further implementation focus.
- **SC-002**: During paper operation, 100% of trading decisions end in one
  of two auditable states: a reconciled paper-trade outcome or a recorded
  blocked-trade outcome with an explicit safety reason.
- **SC-003**: During Stage 1 validation, 0 live-capital orders are
  created or routed by the system.
- **SC-004**: Every candidate and realized-performance report includes
  benchmark-relative, cost-aware, and risk-adjusted results for the same
  observation window.
- **SC-005**: The operator can review one complete paper-trading evidence
  trail, from market state through decision, order outcome, reconciliation,
  and benchmark context, for any observed trade in the validation period.
- **SC-006**: Before any Phase 1 strategy recommendation is considered
  complete, the operator has enough evidence to choose one of three
  actions with confidence: continue paper validation, return to design, or
  reject the candidate set.

## Assumptions

- Stage 1 is the only active scope for this feature; future stages remain
  deferred until their gate and governance prerequisites are met.
- The bot has access to a broker-supported paper trading environment and
  to the market data needed to evaluate and execute Stage 1 paper trades.
- A single human operator is the final decision-maker for phase
  advancement, strategy acceptance, and any move toward live capital.
- The large-cap benchmark, paper-trading capital policy, and hard safety
  policies are governed outside this specification and are treated as
  already-approved inputs.
- The operator values honest evidence and capital preservation over
  keeping weak strategy candidates alive for the sake of progress.
