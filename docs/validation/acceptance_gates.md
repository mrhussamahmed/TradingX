---
id: GATES-0001
title: Stage 1 acceptance gates
version: 1.3.1
status: active
created: 2026-04-17
last_amended: 2026-04-23
supersedes: GATES-0001@1.3.0
superseded_by: null
author_session: gpt-5-codex-2026-04-23
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

## Paper-Only Trial Posture

TradingX may report `paper_trading` for strategies approved for local paper trials.
This state permits paper-only observation and iteration. It does not permit live
trading, broker live mode, or live order submission.

Live trading remains fail-closed until Gate 4 explicitly enables all live-control
layers and the operator performs live sign-off.

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

Pass criteria are evaluated against the three-tier benchmark stack
defined in [ADR-0021](/docs/adrs/ADR-0021-benchmark-stack.md) and the
reframed gate logic in
[ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md).

**Pass criteria (hard-pass, all required)**

- `hurdle_clearance`: candidate cumulative return exceeds the cash
  hurdle cumulative return (T-bill yield via DGS3MO) over the
  validation window.
- `opportunity_cost_edge`: candidate CAGR exceeds the 60% SPY + 40%
  AGG passive blend CAGR by at least 2% absolute (constant
  `GATE1_MIN_CAGR_EDGE = 0.02`). The 60/40 blend is rebalanced
  monthly.
- `operating_constraint`: maximum drawdown <= 15% design target AND
  CDaR@95% confidence <= 8% threshold. Both are enforced as pass/fail
  criteria by `evaluate_operating_constraint` at validation time. The
  25% maximum-drawdown hard-halt threshold is also enforced at runtime
  by `PortfolioHardHaltController`, which triggers
  `LocalRuntimeHostManager.trigger_hard_halt(...)`, stops the service,
  transitions the host to `recovery_required`, and requires operator
  clearance before restart.
- `out_of_sample_profile`: at least 756 trading days (three years)
  of out-of-sample data with metrics remaining within 30% of the
  in-sample profile on Sharpe, CAGR, and MaxDD
  (`|metric_OOS - metric_IS| / max(|metric_IS|, 0.3) <= 0.30`).
- `pbo_overfitting`: evaluation-level PBO from the current CPCV cohort
  must be <= 0.30 once the Stage 2 readiness gates clear. Readiness
  means:
  - at least one CPCV cohort is mature enough that
    `earliest_recorded_at_utc <= now - 182 days`
  - the current evaluation's `cohort_window_id` has
    `strategy_config_count >= 50`
  - the current evaluation's `cohort_window_id` has exactly 45 CPCV
    paths (`C(10, 2)`)
  Before those readiness gates clear, `pbo_overfitting` remains
  `pending` rather than failed. Once a PBO payload exists for the
  Gate 1 run, the criterion becomes a hard pass/fail gate.
- `marginal_portfolio_contribution`: for each sleeve-backed candidate,
  adding the candidate to the reference book of mandatory sleeve-backed
  candidates must strictly improve portfolio Sharpe AND Calmar AND not
  worsen portfolio CDaR@95%. For tranche 1.4, the reference book is the
  registry-pinned sibling — the other mandatory sleeve-backed candidate
  from `build_mandatory_candidate_registry()` with
  `sleeve_class_path is not None`, independent of the sibling's own Gate 1
  outcome. Generalization for 3+ sleeve-backed candidates is deferred to
  the tranche that introduces a third sleeve-backed candidate.

**Deferred to tranche 1 hardening**

- Deflated Sharpe Ratio: the primitive exists in `stats.py` but is
  not yet invoked by `evaluate_candidate` and the evidence pack has
  no DSR field. Wiring DSR into the candidate evaluation pipeline
  and adding it to the evidence pack ship with tranche-1 hardening.
  When wired, DSR remains reported rather than pass/fail.
- North-star Sharpe (>= 1.3): not currently recorded on evidence
  packs. Scheduled to ship alongside the DSR wiring as
  preference-ranking data among surviving candidates. Not pass/fail.

**Benchmark comparison**

All benchmarking uses the three-tier benchmark stack materialized by
`BenchmarkStack.materialize(...)` in
[src/tradingx/benchmark_stack.py](/src/tradingx/benchmark_stack.py)
over the identical window as the candidate series with identical cost
assumptions. The 60/40 opportunity-cost tier uses dividend-adjusted
SPY and AGG closes sourced through `AlpacaMarketDataGateway`.

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
- `ExecutionQualityDriftMonitor` evidence from `RiskControlEvent`
  artifacts with `control_type = "portfolio_drift_alarm"` and
  paired `OperatorAlert` artifacts with
  `category = "portfolio_drift_alarm"`
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
- Live-enable code remains fail-closed unless the broker mode, config
  layer, process-env layer, write-signing control, and operator
  sign-off posture are all intentionally satisfied.

**Primary evidence**

- Future live-enablement checklist
- Future Gate 4 validation package

## Sources

- `.specify/memory/constitution.md` (CONST-0001 v3.0.1)
- `docs/archive/implementation_constraints.md` (CONSTRAINTS-0001 v1.0.0)
- [ADR-0021](/docs/adrs/ADR-0021-benchmark-stack.md) — three-tier
  benchmark stack (supersedes ADR-0004)
- [ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
  — Gate 1 reframe with benchmark-stack criteria and robustness
  (supersedes ADR-0020)
- [ADR-0024](/docs/adrs/ADR-0024-gate1-pbo-activation.md) —
  Gate 1 PBO activation from CPCV cohort readiness
- [ADR-0025](/docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md) —
  Gate 4 live-enablement control plane and signed web writes
- [SPEC-0013](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
  — Capital growth landscape
