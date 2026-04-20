---
id: SPEC-0013
title: Capital growth landscape — v1 strategic roadmap
version: 0.1.0
status: draft
created: 2026-04-20
last_amended: 2026-04-20
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-20
---

# SPEC-0013: Capital Growth Landscape Design

## Status

Draft on 2026-04-20. Pending Hussam approval.

This document is a strategic roadmap, not a settled decision record. It
captures contested assumptions, their resolutions, and the shape of the
first implementation tranche. Once approved, it generates short ADR
follow-ons (`ADR-0021` supersedes `ADR-0004`; `ADR-0022` supersedes
`ADR-0020`), a `GATES-0001` amendment, and the in-flight Stage `0c`
protocol rename.

## Purpose

When future work touches strategy design, portfolio construction, risk
budgeting, or drawdown defense — start here. This document:

1. States the operating goal in a form that does not silently reward
   overbetting.
2. Resolves contested assumptions inherited from prior repo research
   and from the 2026-04-20 independent review.
3. Decomposes "grow capital" into six subsystems with explicit
   dependencies.
4. Scopes a concrete first tranche (two sleeves + validation + drift
   monitoring + cost model).
5. Lists decisions still open for Hussam.
6. Maps downstream governance work (ADR follow-ons, gate amendments,
   source-code reframes).

## Authority order

1. [constitution](/.specify/memory/constitution.md)
2. [docs/INDEX.md](/docs/INDEX.md)
3. This document (SPEC-0013), once approved
4. ADR-0021 (pending; supersedes ADR-0004)
5. ADR-0022 (pending; supersedes ADR-0020)
6. [CURRENT_ARCHITECTURE.md](/docs/architecture/CURRENT_ARCHITECTURE.md)
7. Tranche-specific specs (pending)

## Decisions resolved in this document

- **Benchmark stack**: three-tier (cash hurdle, 60/40 opportunity cost,
  rolling MDD + CDaR operating constraint). See §2.
- **Drawdown budget**: 15% design target, 25% hard-halt threshold. See
  §2.3.
- **PBO as tranche-1 gate**: deferred to tranche 2. Tranche 1 uses
  purged/embargoed k-fold CV + trials ledger only. See §4.E and §7.
- **Stage 0c protocol rename**: `RuntimeStrategyResolver` →
  `SleevePlannerProtocol`; `ActivatedRuntimePlanner` →
  `ActivatedSleevePlanner`. See Appendix A.

## Decisions still open

See §8.

---

## 1. Goal

> Maximize durable geometric growth net of costs, cash drag, and
> eventually taxes, subject to explicit drawdown, liquidity, and
> model-risk budgets, using sleeves that survive leak-free validation
> and live drift monitoring.

Four deliberate word choices:

- **Durable geometric growth** — compounding with survival, not raw
  return. This framing refuses to reward strategies that win in
  expectation while risking ruin.
- **Net of costs, cash drag, and eventually taxes** — cost is a
  first-class citizen in evaluation, not a post-hoc footnote. The
  *eventually taxes* clause admits that a taxable-live trajectory is
  assumed; turnover discipline is therefore non-negotiable.
- **Subject to explicit ... budgets** — drawdown, liquidity, and
  model-risk are hard constraints, not soft preferences.
- **Sleeves that survive leak-free validation and live drift
  monitoring** — *best-in-class* is defined operationally. A strategy
  is not in-class until it survives both the evaluation harness and a
  live drift check.

## 2. Benchmark stack

Three-tier. Replaces SPY-as-only-benchmark.

### 2.1 Hurdle: T-bill yield

**Source:** the repo's existing DGS3MO risk-free-rate cache in
[src/tradingx/risk_free.py](/src/tradingx/risk_free.py:1) and
[src/tradingx/backtest.py:132](/src/tradingx/backtest.py:132).

**Rationale:** any strategy that cannot beat cash net of costs is
failing its minimum job. This test is currently implicit in the repo's
Lo-adjusted Sharpe computation but not explicit as a hurdle. Making it
explicit removes a class of false promotions in the current high-rate
regime.

### 2.2 Opportunity cost: 60/40 blend

**Composition:** 60% SPY + 40% AGG, rebalanced monthly.

**Rationale:** any sleeve or portfolio that cannot beat a passive 60/40
over a reasonable holding period fails the *why not just buy the blend?*
test. 60/40 is chosen over SPY-alone because:

1. The repo's current universe (SPY/QQQ/IWM/XLE/XLF/XLK/EEM/TLT)
   already includes TLT; crediting a strategy for riding TLT in a bond
   rally requires a benchmark that already holds bonds.
2. SPY-alone is bull-biased; in high-rate regimes, it is a weak
   honesty test.
3. 60/40 is the standard retail passive alternative; it matches the
   real decision a retail allocator would otherwise make.

### 2.3 Operating constraint: rolling MDD + CDaR

**Drawdown budget:**

- Design target: **maximum drawdown ≤ 15%**, rolling over the prior
  252 trading days.
- Hard halt threshold: **maximum drawdown ≤ 25%**. Breach forces a
  stop-trading + operator-clearance cycle.

**CDaR (conditional drawdown-at-risk, Chekhlov-Uryasev-Zabarankin 2005)**
provides a softer throttling signal before the hard halt fires. When
CDaR at 5% confidence deteriorates beyond a calibrated threshold, sleeve
exposure de-risks proportionally. Calibration details land in the
tranche-1 spec.

### 2.4 Supersession impact

This stack supersedes
[ADR-0004](/docs/adrs/ADR-0004-benchmark-spy.md:1). Follow-on work:
`ADR-0021` records this decision formally;
[validation.py:144](/src/tradingx/validation.py:144)'s SPY-relative
hardcode is reframed as part of the same ADR's implementation.

## 3. Contested assumptions

Both prior repo research and the 2026-04-20 independent review made
claims. This section records each, its origin, and its resolution.

| # | Claim | Origin | Resolution | Rationale |
|---|-------|--------|------------|-----------|
| 1 | SPY is the sole benchmark | [ADR-0004](/docs/adrs/ADR-0004-benchmark-spy.md:1) | Superseded | Decision: three-tier stack replaces SPY-only |
| 2 | Meta-labeling is production-ready at retail scale | Independent review | Deferred | 8 daily ETFs × ~10y bars has insufficient degrees of freedom for a secondary GBM; returns in tranche 2+ when universe expands |
| 3 | GARCH is the correct vol-forecasting default | [strategy.py:34](/src/tradingx/strategy.py:34) candidate defaults | Modified | [features/volatility.py:24](/src/tradingx/features/volatility.py:24) already supports `realized`/`ewma`/`garch`; add HAR-RV, pick empirically; don't assume GARCH wins |
| 4 | Max drawdown ≤ 10% achievable single-sleeve | [ADR-0020](/docs/adrs/ADR-0020-gate1-statistical-criteria.md:1) draft | Reset | Decision: 15%/25% realistic for tranche 1's two-sleeve scope |
| 5 | Institutional cost modeling (Almgren-Chriss) is high priority | [COMBINED_PAPER_REVIEW](/docs/research/papers/COMBINED_PAPER_REVIEW.md:1) | Modified | Alpaca $0-commission + retail scale means spread + slippage + turnover drag dominate; Almgren-Chriss becomes relevant only when AUM starts moving the book |
| 6 | Drift detection absent from production-shell list | Independent review | Accepted | Added as subsystem F; mandatory before any live enablement |
| 7 | Structural alpha (VRP, index rebalance, carry) unconsidered | Independent review + paper-review silence | Deferred | Research lane; returns in tranche 3+ |
| 8 | Options-based tail hedging needed for drawdown defense | Independent review | Deferred | Options stack (chain data, greeks, assignment, margin) is a full subsystem; out of v1 unless D2 reopens the question |
| 9 | 8-ETF universe is adequate | [strategy.py:21](/src/tradingx/strategy.py:21) `CANONICAL_STAGE1_UNIVERSE` | Flagged as constraint | Drives mean-reversion deferral; universe expansion is tranche 3+ work |
| 10 | Gate 1 evaluates standalone sleeve Sharpe | [ADR-0020](/docs/adrs/ADR-0020-gate1-statistical-criteria.md:1) draft | Reframed | The gated object is "marginal portfolio contribution + robustness," not "standalone Sharpe" |
| 11 | After-tax compounding is irrelevant to goal | Goal omission | Corrected | Goal now explicitly includes *eventually taxes*; turnover tolerance becomes an open decision |
| 12 | ADR-0020's PBO/CPCV/trials-ledger is currently load-bearing | [ADR-0020](/docs/adrs/ADR-0020-gate1-statistical-criteria.md:1) status | Acknowledged | Parts are planned, not yet load-bearing; Decision defers PBO from tranche 1 to tranche 2 hardening |

## 4. Subsystem decomposition

Six subsystems plus a zeroth *mandates* tier.

### 0. Mandates

Fixed inputs that constrain every downstream subsystem. **Source:** this
document and follow-on ADRs. **Contents:** benchmark stack, drawdown
budget, capital-at-risk, universe/instrument scope, turnover tolerance,
timeline expectations.

### A. Market-state features

Feature computation for vol, regime, and rates.

- **Volatility estimation**: realized vol, EWMA, HAR-RV (Corsi 2009).
  Existing [features/volatility.py](/src/tradingx/features/volatility.py:1)
  covers `realized`/`ewma`/`garch`; add HAR-RV and test against the
  current default empirically.
- **Regime detection**: rule-based composite (200-day SMA position,
  VIX level, yield-curve shape). No HMMs or Markov-switching in v1 —
  they overfit at this universe size.
- **Risk-free rate**: existing DGS3MO cache.
- **Implied vol overlay** (optional, tranche 2+): IV surface data when
  an options chain is accessible.

### B. Sleeve design

The atomic unit of capability. Each sleeve owns: signal generation,
sizing, regime filter, allowed instruments, failure rules.

**Tranche 1 sleeves:**

- **Trend**: time-series momentum following Moskowitz-Ooi-Pedersen
  (2012). Existing scaffold:
  [signals/trend.py](/src/tradingx/signals/trend.py:1).
- **Vol-managed beta**: dynamically-scaled equity exposure following
  Moreira-Muir (2017). Existing scaffold:
  [signals/vol_target_spy.py](/src/tradingx/signals/vol_target_spy.py:1).

**Deferred:**

- Mean-reversion — until universe expansion.
- Carry / term-structure — tranche 3+.
- Cross-sectional — tranche 3+, conditional on universe size ≥ 50.

### C. Portfolio construction and risk budgeting

Combines sleeve outputs into an executable target book.

- Per-sleeve risk budgets (volatility contribution capped).
- Gross exposure cap ≤ 100% for v1; no leverage.
- Net exposure control: long-only for v1.
- Correlation caps between sleeves (new sleeves must demonstrate
  correlation below a calibrated threshold vs. the existing book).
- Single-name concentration cap: retain current
  [risk.py:19](/src/tradingx/risk.py:19) 20% limit.

**Implementation foundation:**
[portfolio_construction.py](/src/tradingx/portfolio_construction.py:1)
(16KB, already present).

### D. Drawdown defense

Active response to portfolio-level stress.

- Rolling MDD throttle — reduces exposure proportionally as DD
  approaches the 15% design target.
- CDaR-triggered de-risking — before hard halt.
- Hard halt at 25% MDD with operator-clearance cycle. Existing
  [runtime_host.py](/src/tradingx/runtime_host.py:1) supports the
  clearance state flow.
- Termination rules for individual sleeves (e.g., 3-month live Sharpe
  below a threshold → retire sleeve).
- Event-risk calendar (FOMC, CPI, NFP, OPEX) — reduce gross exposure
  around known events.

Options-based tail hedging is deferred (see §9 and D2 in §8).

### E. Validation and model selection

Pre-promotion evaluation of sleeves.

**Tranche 1 scope:**

- Purged/embargoed k-fold cross-validation.
- Trials ledger — every hypothesis test recorded, including discarded
  runs.
- Walk-forward stability — rolling 1-year OOS Sharpe ≥ 0.8.
- Profile tolerance —
  `|metric_OOS − metric_IS| / max(|metric_IS|, 0.3) ≤ 0.30` across
  Sharpe, CAGR, MDD.
- Deflated Sharpe Ratio — computed and reported, but not a hard gate
  in tranche 1.

**Tranche 2+ additions:**

- Full CPCV (combinatorial purged cross-validation, de Prado).
- PBO (probability of backtest overfitting) as a hard gate.
- Meta-labeling when universe and data regime justify it.

### F. Live monitoring and drift

Observer over the entire stack; operates on live-vs-backtest divergence.

- PSI (population stability index) on feature distributions.
- KS tests on signal output distributions.
- Execution-quality drift — realized slippage vs. modeled slippage
  over rolling windows.
- Live-vs-backtest divergence alarms on per-sleeve P&L curves.
- Sleeve-termination triggers feeding subsystem D.

**This subsystem is mandatory before any live enablement.** It is
explicitly not a *nice to have*.

## 5. Dependency graph

```
  0. Mandates
    │
    ├───► A. Market-state features ─────────┐
    │                                         │
    └───► E. Validation & model selection ───┤
                                              │
                                              ▼
                                     B. Sleeve design
                                              │
                                              ▼
                                     C. Portfolio construction
                                              │
                                              ▼
                                     D. Drawdown defense
                                              │
                                              ▼
  A + B + C + D ──────────────────────► F. Live monitoring
```

**Read:** mandates constrain A and E. A and E together enable B. B
feeds C; C feeds D. F observes A through D together.

## 6. Gate reframe

### 6.1 Current gate (ADR-0020 draft)

Each candidate sleeve is gated on its own standalone Sharpe ≥ 1.0 net
of costs, DSR ≥ 0.95, PBO ≤ 0.30, MDD ≤ 10%.

### 6.2 Problem

Standalone Sharpe is the wrong gated object. Consider two candidate
sleeves:

- **Sleeve X:** Sharpe 1.2, correlation with existing book = 0.9.
- **Sleeve Y:** Sharpe 0.8, correlation with existing book = 0.0.

Under the current gate, only X passes. But Y is more valuable to the
portfolio — it improves portfolio Sharpe more than X does, because it
diversifies. **Gating on standalone Sharpe selects for adding more of
what you already have.** That is exactly backwards for a capital-growth
goal.

### 6.3 Reframed gate

A sleeve is evaluated in context:

- **Marginal portfolio contribution** (required) — does adding this
  sleeve improve the portfolio's Sharpe, Calmar, and CDaR after cost
  and correlation accounting?
- **Robustness** (required) — walk-forward stability (per §4.E),
  trials-ledger discipline, regime-subperiod splits, profile
  tolerance.

### 6.4 Implementation impact

Lands as `ADR-0022` (supersedes `ADR-0020`) after this spec is
approved. The validation engine in
[validation.py](/src/tradingx/validation.py:1) must add:

- A current-portfolio comparator (sleeve vs. `book + sleeve`).
- A CDaR computation.
- Regime-subperiod metric splits (bull / bear / chop).

## 7. First tranche scope

Concrete scope for the first post-refactor implementation sprint.
Everything below is in scope; everything in §9 is explicitly out.

### 7.1 What ships

1. **Benchmark stack infrastructure** (§2): hurdle, opportunity-cost,
   operating-constraint plumbing in validation and reporting.
2. **Trend sleeve** (§4.B): productionized from existing
   [signals/trend.py](/src/tradingx/signals/trend.py:1) scaffold.
3. **Vol-managed beta sleeve** (§4.B): productionized from existing
   [signals/vol_target_spy.py](/src/tradingx/signals/vol_target_spy.py:1)
   scaffold.
4. **Portfolio risk budgets and DD throttles** (§4.C, §4.D): sleeve
   budgets, gross/net caps, MDD throttle at 15% design / 25% halt,
   CDaR soft-throttle.
5. **Validation stack** (§4.E): purged/embargoed k-fold CV, trials
   ledger, walk-forward, profile tolerance. No CPCV. No PBO gate.
6. **Sleeve-level empirical cost model**: spread + half-spread
   slippage + overnight-gap allowance + turnover drag. Simple;
   calibrated on accumulated paper-trading evidence.
7. **Live drift diagnostics** (§4.F): PSI, KS, execution-quality
   drift, live-vs-backtest P&L divergence alarms. **Required before
   any live-enablement discussion.**

### 7.2 Correlation honesty

Tranche 1's trend + vol-managed-beta pair is not two uncorrelated
sleeves. Both are long-equity-biased; Moreira-Muir at low realized vol
holds ~100% SPY, and trend at low vol is also long. They diversify each
other during volatility spikes (when vol-managed de-risks and trend may
or may not have flipped regime), not in calm markets.

Real diversification begins when a third, structurally-different sleeve
lands (carry, cross-asset, or volatility risk premium in tranche 3+).
Tranche 1 should be framed — internally and in reporting — as "one
equity sleeve with a vol overlay that diversifies it in specific
regimes," not "two uncorrelated sleeves." This spec states that
explicitly so the framing is not misread later.

## 8. Decisions still open

The three decisions resolved in drafting this spec closed the most
impactful cascade. Remaining open decisions for Hussam; none block
drafting this spec but should be resolved before tranche-1
implementation planning:

- **D1. Capital-at-risk and sizing philosophy**: fixed notional per
  trade (current baseline)? Vol-targeted position sizing (aligns with
  vol-managed sleeve)? Fractional Kelly (aggressive but theoretically
  optimal)?
- **D2. Instrument scope for v1**: ETFs only (default), or ETFs +
  options? Opting in to options expands §4.D (options-based tail
  hedging) and adds a full options data/execution stack.
- **D3. Turnover tolerance**: what annualized turnover is *too high*
  given a taxable-live trajectory? Constrains sleeve design directly
  (for example, mean-reversion is turnover-heavy by nature).
- **D4. Cash-drag policy**: when the bot is flat, does that count as
  underperformance vs. the benchmark stack, or is flat acceptable?
  Material for vol-managed-beta design specifically.
- **D5. Timeline expectation**: rough target date for first live
  enablement? Affects how aggressively tranche 1 vs. tranche 2 are
  scoped.

## 9. Deferred explicitly

Not in tranche 1. Each entry includes the condition that brings it back
in.

| Item | Condition to bring back |
|------|-------------------------|
| Mean-reversion sleeve | Universe expands to ≥ 50 liquid names |
| Meta-labeling layer | Universe + data depth support a secondary GBM without overfitting; likely tranche 3+ |
| Options / tail hedges | D2 resolved in favor of ETFs + options |
| Structural alpha (VRP, index rebalance, carry) | Tranche 3+ research lane |
| CPCV as a hard gate | Tranche 2 hardening |
| PBO as a hard gate | Tranche 2 hardening |
| Full Almgren-Chriss execution modeling | AUM approaches the level where book moves the market |
| HMM / Markov-switching regime models | Universe and data regime support it; not at current scale |
| Multi-account / multi-strategy concurrent execution | Architectural future tranche |

## 10. Governance impact

This spec produces downstream work for Codex after Hussam approval.

### 10.1 ADR follow-ons

- **ADR-0021** (new): supersedes
  [ADR-0004](/docs/adrs/ADR-0004-benchmark-spy.md:1). Records the
  three-tier benchmark stack (cash hurdle, 60/40 opportunity cost,
  MDD/CDaR operating constraint).
- **ADR-0022** (new): supersedes
  [ADR-0020](/docs/adrs/ADR-0020-gate1-statistical-criteria.md:1).
  Records the reframed gate criterion (marginal portfolio contribution
  + robustness) and the tranche-1 vs. tranche-2 split on CPCV/PBO.

### 10.2 Gate artifact amendment

- **GATES-0001 amendment**: incorporate the new gate criterion, the
  15%/25% DD budget, and the removal of the PBO requirement from
  tranche 1.

### 10.3 Source code amendments

- [validation.py:144](/src/tradingx/validation.py:144): remove the
  SPY-relative hardcode; add a 60/40 benchmark comparator; thread CDaR
  into the DD-throttle path.
- [strategy.py:34](/src/tradingx/strategy.py:34) candidate defaults:
  after empirical comparison (§3 row 3), update the default vol
  estimator away from `garch` if HAR-RV or EWMA wins on the in-repo
  evaluation set.

### 10.4 In-flight refactor alignment (Stage 0c)

- `RuntimeStrategyResolver` → `SleevePlannerProtocol`.
- `ActivatedRuntimePlanner` → `ActivatedSleevePlanner`.
- File rename: `src/tradingx/runtime_strategy_registry.py` →
  `src/tradingx/sleeve_registry.py`.

Rationale for the rename: see Appendix A.

## Appendix A — Sleeve protocol naming

### A.1 Current Stage 0c plan

Stage 0c (in-flight) introduces `RuntimeStrategyResolver` as the
protocol each registered strategy implements. The resolver exposes
`plan_for_service(...)` — a planning seam. The registry maps
`strategy_id` → resolver factory.

### A.2 Renamed to `SleevePlannerProtocol`

Renamed because the architectural atomic unit of this platform is the
sleeve, not the signal. Today's protocol is a planning seam only. When
sleeves gain richer shape in later tranches (first-class regime
filters, failure rules, allowed-instrument declarations), the protocol
evolves but the name stays honest.

### A.3 Why rename now rather than later

Protocols with 30+ consumers are painful to rename. Only 4
`strategy_id`s exist today; the rename is near-free. Renaming after
tranche 1 ships means touching every sleeve implementation and every
test that references the protocol — much higher cost.

### A.4 Terminology going forward

After this spec is approved:

- **Sleeve** — a production unit that implements
  `SleevePlannerProtocol` and has its own signal, sizing, regime
  filter, and failure rules.
- **Signal** — the raw output of an indicator or model (e.g., a 200d
  SMA crossover, a vol forecast). A signal becomes part of a sleeve
  when it is wrapped with sizing, regime filter, and failure rules.
- **Strategy** — historical repo terminology retained for backward
  compatibility in file and type names (e.g.,
  `StrategyActivationRecord`). Prefer *sleeve* in new code and
  documents.

## References

### Repo documents

- [constitution](/.specify/memory/constitution.md)
- [CURRENT_ARCHITECTURE.md](/docs/architecture/CURRENT_ARCHITECTURE.md)
- [ADR-0004](/docs/adrs/ADR-0004-benchmark-spy.md) — SPY as benchmark
  (to be superseded)
- [ADR-0020](/docs/adrs/ADR-0020-gate1-statistical-criteria.md) —
  Gate 1 statistical criteria (to be superseded)
- [COMBINED_PAPER_REVIEW.md](/docs/research/papers/COMBINED_PAPER_REVIEW.md)

### Repo source files (anchors for governance impact §10)

- [src/tradingx/validation.py](/src/tradingx/validation.py:1)
- [src/tradingx/strategy.py](/src/tradingx/strategy.py:1)
- [src/tradingx/signals/trend.py](/src/tradingx/signals/trend.py:1)
- [src/tradingx/signals/vol_target_spy.py](/src/tradingx/signals/vol_target_spy.py:1)
- [src/tradingx/features/volatility.py](/src/tradingx/features/volatility.py:1)
- [src/tradingx/portfolio_construction.py](/src/tradingx/portfolio_construction.py:1)
- [src/tradingx/risk.py](/src/tradingx/risk.py:1)
- [src/tradingx/runtime_host.py](/src/tradingx/runtime_host.py:1)
- [src/tradingx/backtest.py](/src/tradingx/backtest.py:1)
- [src/tradingx/risk_free.py](/src/tradingx/risk_free.py:1)

### External references

- Moreira, A., & Muir, T. (2017). "Volatility-Managed Portfolios."
  *Journal of Finance.* <https://www.nber.org/papers/w22208>
- Moskowitz, T., Ooi, Y. H., & Pedersen, L. H. (2012). "Time Series
  Momentum." *Journal of Financial Economics.*
- Corsi, F. (2009). "A Simple Approximate Long-Memory Model of
  Realized Volatility." *Journal of Financial Econometrics.*
  <https://ideas.repec.org/a/oup/jfinec/v7y2009i2p174-196.html>
- Daniel, K., & Moskowitz, T. (2014). "Momentum Crashes."
  *Journal of Financial Economics.*
  <https://www.nber.org/papers/w20439>
- Chekhlov, A., Uryasev, S., & Zabarankin, M. (2005). "Drawdown
  Measure in Portfolio Optimization."
- López de Prado, M. (2018). *Advances in Financial Machine Learning.*
- Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe
  Ratio: Correcting for Selection Bias, Backtest Overfitting, and
  Non-Normality." <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551>
- Bailey, D. H., Borwein, J. M., López de Prado, M., & Zhu, Q. J.
  (2015). "The Probability of Backtest Overfitting."
  <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253>
