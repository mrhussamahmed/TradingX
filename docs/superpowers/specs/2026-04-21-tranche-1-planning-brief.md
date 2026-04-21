---
id: BRIEF-0001
title: Tranche 1 planning brief
version: 1.0.0
status: active
created: 2026-04-21
last_amended: 2026-04-21
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# BRIEF-0001: Tranche 1 planning brief

## Purpose

Lock the decomposition, sequence, and completion criteria for tranche 1
in a single short document so no sub-tranche drifts from the overall
arc. Intentionally thin: no deep design inside this document. Each
sub-tranche gets its own spec when its turn comes.

## Authority order

1. [constitution](/.specify/memory/constitution.md)
2. [SPEC-0013 Capital growth landscape](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
3. [ADR-0021 Three-tier benchmark stack](/docs/adrs/ADR-0021-benchmark-stack.md)
4. [ADR-0022 Gate 1 reframe](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
5. [GATES-0001 Stage 1 acceptance gates](/docs/validation/acceptance_gates.md) v1.1.0
6. This brief (BRIEF-0001)
7. Sub-tranche specs (pending)

## Tranche 1 completion criteria

Tranche 1 is complete when **all** of the following are operational:

1. Trend sleeve and vol-managed beta sleeve running in paper against
   the three-tier benchmark stack.
2. Portfolio risk budgets and drawdown throttles enforced at runtime,
   including the 25% MDD hard halt that is currently documented but
   not yet wired (per the P1 gap surfaced in the ADR review).
3. Sleeve-level cost-aware evaluation: candidate metrics are net of
   `estimate_trade_costs` aggregated over the backtest window.
4. Validation stack with purged/embargoed k-fold CV and a trials
   ledger; Deflated Sharpe Ratio wired into `evaluate_candidate` and
   carried in `EvaluationEvidencePack`.
5. Live drift diagnostics (PSI on features, KS on signal outputs,
   execution-quality drift, live-vs-backtest P&L divergence) emit
   alarms against calibrated thresholds.
6. Marginal-portfolio-contribution criterion wired into Gate 1
   evaluation once portfolio construction lands (ships in 1.4).

When all six are shipped and green in paper for at least one full
session, tranche 1 closes and we can open the Gate 4 readiness
discussion.

## Sub-tranche sequence

| # | Sub-tranche | Scope | Hard dependencies | Blocks |
|---|-------------|-------|-------------------|--------|
| 1.1 | Validation infrastructure | Purged/embargoed k-fold CV; trials ledger; DSR wiring into `evaluate_candidate` + evidence pack; sleeve-level cost model integration via existing `costs.py` primitives | None — can start immediately on top of `main` at `c6fbcec` | Sleeves (1.3), portfolio construction (1.4); any honest candidate evaluation |
| 1.2 | Market-state features | HAR-RV volatility estimator; rule-based regime composite (200d SMA / VIX level / yield-curve shape); empirical comparison of vol estimators with candidate-default tune if HAR-RV or EWMA beats `garch` | 1.1 scope stable (can start research in parallel; governance merges sequentially) | Sleeves (1.3) consume feature inputs |
| 1.3 | Sleeves | Trend sleeve (TSMOM per Moskowitz-Ooi-Pedersen 2012) productionized from existing `signals/trend.py`; vol-managed beta sleeve (Moreira-Muir 2017) productionized from existing `signals/vol_target_spy.py` | 1.1 merged; 1.2 merged; **Hussam decisions on D1–D4 resolved** | Portfolio construction (1.4) needs sleeve outputs |
| 1.4 | Portfolio construction + drawdown defense | Per-sleeve risk budgets; correlation caps; MDD throttle at 15% design (proportional exposure reduction); CDaR soft-throttle; **25% MDD runtime hard halt wired to the existing operator-clearance flow**; sleeve termination rules; marginal-portfolio-contribution criterion wired into Gate 1 | 1.3 merged (needs at least one sleeve live) | Live monitoring (1.5) observes portfolio state |
| 1.5 | Live drift monitoring | PSI on feature distributions; KS tests on signal outputs; execution-quality drift (realized slippage vs modeled); live-vs-backtest per-sleeve P&L divergence alarms | 1.4 merged (needs runtime state) | Gate 4 readiness discussion |

## Research vs governance lanes

Parallelizable:

- **1.2 research** (empirical vol-estimator comparison on in-repo bars)
  can run in parallel with 1.1 implementation. Governance merges for
  1.2 follow 1.1 to avoid cross-PR conflict.
- **1.5 scoping** (which drift metrics, what thresholds) can start
  once 1.3 is in flight.

Strict-sequential:

- 1.1 → 1.3 (sleeves need validation infra)
- 1.3 → 1.4 (portfolio construction needs sleeves)
- 1.4 → 1.5 (drift monitoring needs runtime state)

## Deferred Hussam decisions (gate: sub-tranche 1.3)

These block 1.3. They do not block 1.1 or 1.2. Explicit ask happens
when 1.3 opens.

| # | Decision | Codex's default prior | Will confirm at 1.3 |
|---|----------|-----------------------|---------------------|
| D1 | Capital-at-risk and sizing philosophy | Vol-targeted sizing (not fixed notional, not Kelly for tranche 1) | Yes |
| D2 | Instrument scope | ETFs only | Yes |
| D3 | Turnover tolerance | Moderate | Yes |
| D4 | Cash-drag policy | Flat acceptable when risk-state says no edge | Yes |

Additional open items from SPEC-0013 §8 not yet scheduled:

- **D5** — timeline expectation for first live enablement. Affects
  whether tranche-2 hardening (CPCV / PBO) runs in parallel with
  tranche 1 or strictly after. Not blocking any sub-tranche here;
  surface before 1.4 closes.

## Anti-drift rules

Update this brief in the same session that:

- adds, removes, reorders, or re-scopes a sub-tranche.
- changes the tranche-1 completion criteria.
- changes a sub-tranche's hard dependencies.
- resolves any of the D1–D4 decisions before 1.3 opens.

If a sub-tranche spec contradicts this brief, the brief is updated in
the same commit so the contract stays visible.
