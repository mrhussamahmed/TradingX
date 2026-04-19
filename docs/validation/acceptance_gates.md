---
id: GATES-0001
title: Stage 1 acceptance gates
version: 1.0.1
status: active
created: 2026-04-17
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-004
---

# Stage 1 acceptance gates

## Purpose

Translate the constitution's Stage 1 gate language into one operational
reference that later validation reports can cite.

## Scope

- This document defines the gate criteria and required evidence.
- It does not record the current gate status. Current status lives in
  handovers and future validation reports.
- Live trading remains disabled regardless of any gate state until Gate 4
  sign-off explicitly says otherwise.

## Gate 0 — Repo hygiene

**Pass criteria**

- `./scripts/validate` passes.
- Coverage on `src/` is at least 80%.
- No unresolved `TODO`, `FIXME`, `XXX`, or `HACK` markers remain in
  production code.
- Index validation passes and authoritative documents remain synchronized.

**Primary evidence**

- `./scripts/validate`
- `scripts/check_index.py`
- CI results in `.github/workflows/ci.yml`

## Gate 0.5 — Walking skeleton

**Pass criteria**

- The bot authenticates to Alpaca paper.
- The bot fetches real market data.
- The bot places a real paper order.
- The bot receives a fill, closes the position, reconciles the final
  state, and writes evidence artifacts.

**Primary evidence**

- `tests/smoke/test_alpaca_paper_roundtrip.py`
- Artifacts under `artifacts/smoke/`
- Session handover documenting the real paper result

## Gate 1 — Backtest acceptability

**Pass criteria**

- Net CAGR > SPY CAGR + 2% absolute OR Sharpe >= 1.0 and >= 1.3x SPY
  Sharpe over the same window.
- Max drawdown <= 15%.
- Calmar >= 0.5.
- At least 3 years of out-of-sample data with metrics within 30% of the
  in-sample profile.
- Benchmark comparison uses dividend-adjusted SPY returns over the
  identical window with identical cost assumptions.

**Primary evidence**

- Candidate evidence packs
- Strategy-selection ADRs
- Future Gate 1 validation report

## Gate 2 — Robustness

**Pass criteria**

- Strategy remains net profitable at 2x slippage and 2x fees.
- +/-20% parameter perturbation does not degrade Sharpe by more than 30%.
- Every rolling walk-forward window of at least 1 year keeps Sharpe >=
  0.5.

**Primary evidence**

- Candidate evidence packs
- Sensitivity and walk-forward artifacts
- Future Gate 2 validation report

## Gate 3 — Paper trading

**Pass criteria**

- At least 180 calendar days or 100 closed trades, whichever comes first.
- No P1 incidents caused by bugs.
- Realized slippage <= 1.5x the backtest assumption.
- Realized hit rate stays within 20% of backtest expectation.
- Realized Sharpe >= 0.5x the backtest Sharpe.
- Restart and recovery scenarios are exercised.
- Initial SMTP emergency round trip passes.
- Replay-simulator slippage does not diverge from Alpaca paper slippage
  by more than 2x.

**Primary evidence**

- Paper-trading logs and reconciliations
- Monitoring and alert evidence
- Recovery drills
- Future Gate 3 validation report

## Gate 4 — Live enablement

**Pass criteria**

- Gates 0, 0.5, 1, 2, and 3 have already passed.
- The operator signs off on the live-enablement checklist.
- Starting live capital is <= 10% of the paper-traded notional.
- Kill switch is tested in live-paper within 7 days.
- Monitoring is confirmed for at least 7 days.
- A fresh SMTP emergency round trip passes within 7 days of the Gate 4
  decision.
- Web write endpoints require request signing plus idempotency keys before
  any live-control environment variable is accepted.
- Live-control flags remain fail-closed in code until Gate 4-specific
  enablement work lands.

**Primary evidence**

- Future live-enablement checklist
- Future Gate 4 validation package

## Sources

- `.specify/memory/constitution.md` (CONST-0001 v3.0.1)
- `docs/archive/implementation_constraints.md` (CONSTRAINTS-0001 v1.0.0)
