---
id: PLAN-0001
title: TradingX Stage 1 paper trading bot implementation plan
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-004
---

# Implementation Plan: TradingX Stage 1 paper trading bot

**Branch**: `001-paper-trading-bot` | **Date**: 2026-04-17 | **Spec**: `specs/001-paper-trading-bot/spec.md`
**Input**: Feature specification from `/specs/001-paper-trading-bot/spec.md`

## Summary

Extend the Phase 0 Alpaca paper-trading skeleton into a Stage 1 paper
bot that can evaluate mandatory strategy candidates honestly, execute a
deterministic paper-only trading loop with fail-closed risk controls,
and produce operator-facing evidence for benchmark-relative gate
decisions. The implementation stays inside one Python service, keeps
live trading disabled at every layer, and adds contract-first records
for trade decisions, blocked trades, alerts, and phase-advance evidence.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: `alpaca-py`, `python-dotenv`, `pytest`, `ruff`, `black`, `mypy`, `nautilus_trader`, `prometheus-client`, `python-telegram-bot`
**Storage**: Versioned repository artifacts plus local runtime files under `artifacts/`; persistence sits behind an explicit boundary so the storage engine can be selected later without touching strategy or risk logic
**Testing**: `pytest`, smoke tests against Alpaca paper, `mypy --strict`, `ruff`, `black`, `./scripts/validate`
**Target Platform**: Linux (Ubuntu LTS) for CI/runtime; macOS for local development
**Project Type**: Single-project Python trading service with a narrow CLI entrypoint and local-only operator surfaces
**Performance Goals**: Block stale market data older than 60 seconds, block stale broker state older than 5 minutes, reconcile every paper trade into an auditable terminal state, and keep the smoke round trip inside the existing test timeout budget
**Constraints**: UTC timestamps only, `Decimal` for order economics, live trading disabled at four layers, regular US market hours only, liquidity floor at 30-day ADV >= 1,000,000 shares, price floor >= $5.00, max single-symbol concentration 20%, no generative-AI prompt in any trading loop
**Scale/Scope**: One bot, one paper account, liquid US equities or ETFs, max 10 open positions, mandatory evaluation of the three Stage 1 baseline strategy families before any optional candidate can displace them

## Constitution Check

*GATE: Must pass before implementation tasks are generated. Re-check after design artifacts land.*

- `PASS` Principle I: the plan keeps hard pre-trade controls at the risk
  boundary, treats unsafe conditions as fail-closed, and preserves paper-
  only execution.
- `PASS` Principle II: candidate evaluation is evidence-first and
  benchmark-relative; no strategy may be promoted from backtests or paper
  anecdotes alone.
- `PASS` Principle III: the implementation path preserves the existing
  RED -> GREEN -> REFACTOR workflow and keeps `./scripts/validate` as the
  required gate.
- `PASS` Principle IV: audit artifacts, gate documents, and ADRs remain
  repo-first, sourced, and explicit; no new authoritative document is
  left unversioned.
- `PASS` Principle V: the architecture stays single-service and
  module-oriented; no avoidable process or deployment complexity is
  introduced.
- `PASS` Principle VI and VII: runtime self-modification is out of scope,
  and no new path may enable live trading.
- `PASS` Principle VIII, IX, and X: this plan and its companion artifacts
  carry front-matter, keep spec and plan concerns separated, and maintain
  bounded operator interfaces.

## Project Structure

### Documentation (this feature)

```text
specs/001-paper-trading-bot/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── operator_evidence.md
│   └── trading_loop.md
└── tasks.md
```

### Source Code (repository root)

```text
src/tradingx/
├── __main__.py
├── alerts.py
├── config.py
├── controller.py
├── data.py
├── evaluation.py
├── execution.py
├── monitoring.py
├── persistence.py
├── portfolio.py
├── risk.py
├── strategy.py
└── types.py

tests/
├── contract/
├── integration/
├── smoke/
└── unit/
```

**Structure Decision**: Keep one Python package rooted at `src/tradingx/`
and extend the existing flat Phase 0 skeleton with a small number of
focused modules. This preserves the current repo shape, keeps reasoning
local, and avoids premature subpackage or multi-service complexity.

## Delivery Phases

### Phase 2 — Architecture and evidence contracts

- Formalize the data model and internal contracts for strategy
  evaluation, trading-loop state, operator alerts, and gate evidence.
- Promote the Stage 1 acceptance gates from constitution text into an
  explicit validation document used by later reports.
- Freeze the backtest-engine choice via ADR-0009 so later execution work
  is not blocked by tool ambiguity.

### Phase 3 — Scaffolding and operator boundaries

- Add module stubs and tests for `strategy`, `evaluation`, `alerts`,
  `monitoring`, and `persistence`.
- Keep the local interface read-only and the operator channel narrow.
- Wire Prometheus metrics and alert-event fan-out without exposing a
  public control plane.

### Phase 4 through Phase 8 — Trading-system completion

- Build the market-data and feature foundation, including benchmark-
  aligned data handling and evidence capture.
- Implement the chosen backtest engine adapter and candidate-evaluation
  pipeline before strategy promotion.
- Expand paper execution, reconciliation, persistence, monitoring, and
  emergency alerting until the Gate 3 evidence trail is complete.

### Phase 9 — Validation and live-readiness packaging

- Produce gate reports against `docs/validation/acceptance_gates.md`.
- Keep live trading disabled unless and until Gate 4 operator sign-off
  occurs through the separate live-enablement workflow.

## Complexity Tracking

No constitution exceptions or complexity justifications are required by
this plan.
