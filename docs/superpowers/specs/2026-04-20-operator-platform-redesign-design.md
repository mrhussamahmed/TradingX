---
id: DESIGN-0012
title: TradingX operator platform redesign
version: 1.0.0
status: active
created: 2026-04-20
last_amended: 2026-04-21
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-21
---

# TradingX Operator Platform Redesign

Date: 2026-04-20
Status: Proposed
Author: Codex

## 1. Product Goal

Redesign the current TradingX web app into a professional dark-theme operator platform that supports three distinct jobs without blending them into one overloaded dashboard:

1. Operate the bot safely during market hours.
2. Judge whether the bot is achieving its portfolio objective.
3. Investigate what happened and why when behavior, performance, or system health looks wrong.

The redesigned product must feel like one coherent platform, but with three genuinely distinct workspaces:

- Mission Control
- Portfolio
- Research

This is a redesign of the existing React/FastAPI control center, not a second parallel UI stack.

## 2. Core Design Decisions

### 2.1 Workspace Model

The app will have one global shell with one navigation model, one permission model, one design system, and one data layer. Inside that shell, the user can switch between three distinct workspaces:

- Mission Control: live operations and intervention
- Portfolio: performance, benchmarking, attribution, and improvement insights
- Research: replay, evidence, diagnostics, and technical investigation

These are not light theme/layout variations. Each workspace has its own:

- home screen
- page structure
- default panel density
- primary controls
- language and interpretation style

### 2.2 Data Truthfulness

The UI must not show synthetic or fake portfolio analytics to make screens look complete.

Each metric or chart must explicitly fall into one of four states:

- available
- partial
- stale
- unavailable

Rules:

- Mission Control may show missing/stale status when the absence is operationally important.
- Portfolio hides or clearly marks metrics that are not backed by sufficient real evidence.
- Research may expose partial/stale inputs more often because diagnosis sometimes depends on degraded inputs.

### 2.3 Visual Direction

The platform retains a dark theme, but shifts to a darker Carbon/Steel palette and abandons the current cyan/gold emphasis.

Primary visual direction:

- background: near-black carbon
- panels: deep graphite
- primary accent: restrained steel/cobalt blue
- positive: muted green
- negative: muted red
- neutral data/gridlines: soft gray-blue

Visual goals:

- darker overall tone
- thinner chart lines
- reduced glow and ornament
- restrained use of color
- stronger information hierarchy
- more institutional, less “dashboard demo”

### 2.4 Control Boundaries

The app should support “Operator Plus” controls, not become a full trading terminal.

Allowed:

- pause/resume bot
- retry broker/feed sync
- run bounded recovery
- re-run bounded workflows
- acknowledge alerts
- switch performance/research views and filters

Not allowed in the main UI:

- manual order entry
- discretionary trade placement
- broad raw config mutation
- terminal-replacement behavior

## 3. Information Architecture

### 3.1 Global Shell

Global shell elements:

- workspace switcher
- command palette
- global search
- global data availability/freshness indicators
- settings
- permissions and control posture

Global items must stay small and stable. Workspace-specific content should not leak into the global shell.

### 3.2 Workspaces

#### Mission Control

Purpose: Run the bot safely during market hours.

Pages:

- Market Desk
- Execution Queue
- Exposure & Guardrails
- Live Book
- Operator Alerts

#### Portfolio

Purpose: Determine whether the bot is creating worthwhile value relative to risk and passive alternatives.

Pages:

- Performance Summary
- Benchmark Comparison
- Strategy Comparison
- Drawdowns
- Performance Diagnostics

#### Research

Purpose: Understand what happened and why.

Pages:

- Replay & Diagnostics Hub
- Replay Trace
- Evidence Explorer
- System Diagnostics
- Saved Layouts

## 4. Workspace Layouts

### 4.1 Mission Control

Mission Control is the default workspace during active operations.

Its home page must prioritize:

- bot state
- broker/feed health
- heartbeat age
- current alerts
- risk budget usage
- gross/net exposure
- open orders requiring attention
- positions with active risk
- last successful sync state
- operator-plus actions

What does not belong prominently here:

- alpha
- beta
- long benchmark narratives
- dense attribution tables
- replay-heavy content

### 4.2 Portfolio

Portfolio is the performance judgment workspace.

It has two internal reading modes:

- Guided
- Analyst

Guided mode:

- fewer metrics
- stronger interpretation
- clear “good / bad / mixed” judgment
- “what to inspect next” prompts

Analyst mode:

- denser tables
- richer ratios
- deeper breakdowns
- multi-compare views
- interpretation still available, but not forced into the primary reading flow

### 4.3 Research

Research combines replay and technical diagnostics.

The home page should highlight:

- recent replayable events
- evidence most relevant to current alerts or weak performance
- open diagnostics threads
- stale feeds / lag / drift / model freshness issues

It is not a generic “studio.” Its language must explicitly reflect its function:

- replay
- evidence
- diagnostics
- audit
- saved review layouts

## 5. Metric Catalog

### 5.1 Mission Control Metrics

Mission Control metrics answer: can the bot continue safely right now?

Required metrics:

- Bot State
- Broker Connectivity
- Feed Health
- Heartbeat Age
- Open Orders Requiring Attention
- Open Positions Count
- Gross Exposure
- Net Exposure
- Daily Risk Budget Used
- Weekly Risk Budget Used
- Single-Name Concentration Usage
- Overnight Exposure
- Current Alerts Count by severity
- Last Successful Broker Sync
- Last Successful Feed Sync
- Execution Latency p50 / p95 / p99 when real data exists
- Slippage Guardrail Status
- Last Operator Action

Interpretation rule:

- explain degraded states, risk breaches, and action-required conditions
- do not over-annotate every operational KPI

### 5.2 Portfolio Metrics

Portfolio metrics answer: is the bot producing worthwhile value beyond passive alternatives and justified complexity?

Top-line:

- Net Liquidation Value
- Daily P&L
- Weekly P&L
- Monthly P&L
- YTD P&L
- Total Return
- Net Return After Fees
- Unrealized P&L
- Realized P&L

Benchmark-relative:

- Return vs S&P 500
- Return vs Nasdaq 100
- Return vs Custom Benchmark
- Excess Return
- Alpha
- Beta
- Tracking Error
- Information Ratio
- Up-Capture
- Down-Capture
- Relative Drawdown
- Recovery Speed vs Benchmark

Risk-adjusted:

- Sharpe
- Sortino
- Calmar
- Max Drawdown
- Ulcer Index
- Recovery Factor
- Volatility
- Hit Ratio by Period

Strategy attribution:

- P&L by Strategy
- Contribution to Total P&L
- Contribution to Drawdown
- Contribution to Risk Consumption
- Win Rate by Strategy
- Profit Factor by Strategy
- Expectancy
- Average Win
- Average Loss
- Average Holding Time
- Stability Score
- Recent Degradation Score
- Regime-Specific Performance

Interpretation rule for important portfolio KPIs:

Every key KPI must expose:

- what the metric is
- what the current value means for the bot’s goal
- whether the current state is good, bad, or mixed
- why that judgment applies
- what to inspect next

Example interpretation:

- Excess Return: -1.1%
- Meaning: bad for the bot goal
- Why: the bot is lagging passive exposure over the selected window, so complexity is not currently justified
- Inspect next: strategy contribution, execution drag, regime mismatch

### 5.3 Research Metrics

Research metrics answer: what happened, why did it happen, and where is the failure or weakness?

Replay metrics:

- Decision Timestamp
- Signal Snapshot
- Selected Strategy
- Selected Symbol
- Selection Score
- Risk Gate Result
- Execution Path
- Fill Price vs Expected
- Slippage vs Expected
- Trade Outcome
- Exit Reason
- Post-Trade P&L

System diagnostics:

- Feed Lag
- Stale Feed Detection
- API Error Rate
- Websocket Disconnect Count
- Queue Backlog
- Service Uptime
- Restart Frequency
- Heartbeat Age
- Model Freshness
- Feature Missingness
- Prediction Confidence Decay
- Backtest vs Live Drift
- Regime Classifier Confidence

Interpretation rule:

Research explanations are diagnostic, not PM-summary oriented.

Preferred phrasing:

- likely cause of weak performance
- possible stale-model risk
- potential execution degradation
- worth replay inspection

## 6. Benchmark Comparison Framework

Benchmark comparison is a first-class Portfolio capability, not a side panel.

Core benchmark set:

- S&P 500
- Nasdaq 100
- Dow Jones
- Russell 2000
- Custom benchmark
- Buy-and-hold basket of traded symbols

Required benchmark views:

- Equity vs Benchmark chart
- Excess Return chart
- Drawdown vs Benchmark chart
- Relative Monthly Table
- Rolling Alpha / Beta / Tracking Error
- Up-Market / Down-Market behavior
- Recovery Speed comparison

Controls:

- benchmark selector
- date window selector
- rebased vs absolute return
- net vs gross return when supported
- single benchmark vs multi-benchmark compare

Default question the page should answer immediately:

- Are we beating the benchmark, and if not, why not?

## 7. Strategy Comparison Framework

Strategy comparison belongs on its own Portfolio page.

Questions it must answer:

- Which strategy is making money?
- Which strategy is unstable?
- Which strategy works only in certain regimes?
- Which strategy is leaking through execution, fees, or risk rules?
- Which strategy deserves more capital, less capital, or removal?

Required structure:

- top summary row for selected strategies
- leaderboard table
- contribution chart
- regime-performance view
- drawdown contribution view
- rolling trend view
- symbol-within-strategy drilldown

Required controls:

- Strategy Filter
- Compare Against
- Metric View
- Regime Filter
- Symbol Filter
- date window selector

Explicit naming rule:

Controls must say what they do. Do not use vague labels like “Attribution Language.”

## 8. Visual Mapping

Charts must be chosen by decision-making job, not decoration.

Recommended mappings:

- line charts: equity, rolling performance, benchmark compare
- area charts: excess return, drawdown spread
- grouped bars: period comparisons
- stacked bars: contribution to P&L or drawdown
- heatmaps: regime vs strategy, weekday/hour behavior
- tables: sortable benchmark and strategy comparisons
- replay timelines: causality and execution flow
- KPI cards: only top-level decision metrics

Avoid:

- gratuitous donut charts
- thick presentation-style lines
- charts without axes or values
- decorative glow that adds noise

## 9. Chart Interaction Model

Charts should feel like financial tools.

Required chart behavior:

- visible x-axis labels
- visible y-axis numeric values
- crosshair on hover
- legend
- point-in-time tooltip with actual values
- normalization label when rebased
- explicit date window label
- source/freshness label when relevant

Visual chart rules:

- thinner lines
- muted gridlines
- restrained color use
- less glow
- color must encode meaning, not decoration

Workspace chart emphasis:

- Mission Control: state, latency, exposure, risk consumption
- Portfolio: equity vs benchmarks, excess return, drawdown, rolling ratios, attribution
- Research: replay timelines, lag/drift charts, event overlays, diagnostics

## 10. Interaction Model

### 10.1 KPI Interpretation

Portfolio KPIs must support:

- inline interpretation in Guided mode
- click/expand interpretation drawer in Guided and Analyst modes

### 10.2 Workspace Workflow

Default user path:

1. Open Mission Control during trading hours.
2. Stabilize or inspect immediate state there if something looks wrong.
3. Switch to Portfolio when the question is performance.
4. Switch to Research when the question is causality, replay, or technical diagnosis.

### 10.3 Naming Rule

Labels must say what the thing is or does.

Good:

- Benchmark Selector
- Strategy Filter
- Metric Interpretation
- Contribution View
- Replay Trace
- System Diagnostics

Bad:

- Attribution Language
- Studio
- vague “intelligence” labels when function is unclear

## 11. Implementation Architecture

### 11.1 Frontend Rebuild Strategy

Do not continue evolving the redesign in the current monolithic `App.tsx` shape.

Rebuild the web app as modular workspace-oriented React code inside the existing web app, not as a separate parallel application.

Target structure:

- `webapp/src/app/`
- `webapp/src/design-system/`
- `webapp/src/charts/`
- `webapp/src/data/`
- `webapp/src/features/`
- `webapp/src/workspaces/mission-control/`
- `webapp/src/workspaces/portfolio/`
- `webapp/src/workspaces/research/`
- `webapp/src/types/`

Responsibility split:

- workspaces: layouts and workflow
- design-system: reusable UI components
- charts: financial chart primitives and hover behavior
- data: API contracts, adapters, freshness/completeness mapping
- features: reusable domain features shared across workspaces

### 11.2 Backend Read Model Direction

Move from broad mixed snapshots toward workspace-oriented read models.

Target API/read model surfaces:

- mission control snapshot
- portfolio summary snapshot
- benchmark comparison snapshot
- strategy comparison snapshot
- replay snapshot
- diagnostics snapshot

Each payload should explicitly communicate:

- freshness
- completeness
- unavailable reason
- evidence coverage

### 11.3 Suggested Libraries

Current recommendation for the redesign:

- React with the existing app setup
- TanStack Query or equivalent query layer if not already present
- a financial-capable charting layer with strong control over axes, tooltips, legends, and crosshair behavior

Selection criteria for charts:

- React compatibility
- institutional-looking output without excessive ornament
- good tooltip/crosshair support
- multi-series comparison support
- overlay/event support
- acceptable rendering performance

### 11.4 Mock Data and Live Integration Rules

For implementation:

- Mission Control may use empty/unavailable states where live data is absent.
- Portfolio must not use fake numbers to populate analytics.
- Research may expose partial data for diagnostics.

Mock/demo payloads may be used only in tests or design scaffolding, never as misleading runtime UI values.

## 12. Implementation Phases

### Phase 1

- establish new shell architecture
- implement Carbon/Steel design system
- add workspace switcher
- rebuild Mission Control home
- remove irrelevant live-ops clutter

### Phase 2

- rebuild Portfolio Guided mode
- benchmark comparison page
- strategy comparison page
- KPI interpretation layer
- strict real-data-only handling

### Phase 3

- add Portfolio Analyst mode
- denser ratios, tables, comparisons, drilldowns

### Phase 4

- rebuild Research workspace
- replay hub
- evidence explorer
- diagnostics pages
- saved review layouts

### Phase 5

- unify command palette, global search, drawers, stale/partial states, and overall interaction polish

## 13. Quality Bar

The redesign is not just additive. It requires removal.

Remove:

- vague labels
- duplicated concepts
- low-value panels
- mixed concerns in the wrong workspace
- fake/default metric fillers
- decorative chart styling with low information value

Success criteria:

- the operator always knows where they are
- the UI never pretends to know more than the data supports
- Mission Control is fast under pressure
- Portfolio is benchmark-aware and attribution-literate
- Research explains behavior and failure without polluting the operating surface

## 14. Future Roadmap

Future additions after the redesign foundation:

- trade replay with deeper event overlays
- scenario analysis
- capital allocation optimizer
- alert acknowledgement workflows with richer state
- more advanced regime diagnostics
- richer model drift and execution-quality analytics
- saved analyst layouts with import/export

## 15. Out of Scope for This Redesign

Not part of the redesign baseline:

- manual order entry terminal
- broad configuration editor for arbitrary runtime mutation
- pretending missing portfolio analytics are available
- shipping all advanced quant metrics in phase one

## 16. Final Product Outcome

TradingX becomes a professional dark-theme operator platform with:

- one shell
- three distinct workspaces
- honest data handling
- better control discipline
- benchmark-aware performance evaluation
- strategy-level attribution
- cleaner replay and diagnostics flow
- materially improved hierarchy, language, and usability
