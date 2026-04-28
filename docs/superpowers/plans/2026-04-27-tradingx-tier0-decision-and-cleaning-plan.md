# TradingX Tier 0 Decision And Cleaning Plan

Status: implementation-ready after adversarial review amendments
Date: 2026-04-27
Owner: CIO / Head of Quant Research review lane
Repository: `/Users/ahmedabd/Desktop/AI Projects/TradingX`

This plan converts the 7-agent brainstorm synthesis and subsequent
adversarial review into an execution-ready program. It is intentionally
narrow. Its job is to let future AI agents run the right work without
re-auditing the entire repository, inventing strategy changes, or
silently widening scope.

## Non-Negotiable Rule

Tier 0 answers one question:

> Does TradingX, after making already-advertised behavior real, deserve
> more engineering work?

Tier 0 must not add new alpha. It may only:

1. measure the current executable system;
2. make existing declared behavior real enough to measure honestly; and
3. apply small safety fixes required to run paper evaluation without
   avoidable operator-control risk.

If an agent cannot classify a proposed change under this rule, the agent
must stop and ask for review. Do not infer permission from nearby code.

## Authority And Inputs

Primary source reports:

- `brainstorm/backtesting-infrastructure-agent.md`
- `brainstorm/execution-microstructure-agent.md`
- `brainstorm/math-statistics-agent.md`
- `brainstorm/ml-rl-agent.md`
- `brainstorm/portfolio-allocation-agent.md`
- `brainstorm/quantitative-strategy-agent.md`
- `brainstorm/risk-management-agent.md`

Canonical hardening roadmap:

- `docs/roadmap/tradingx_quant_hardening_execution_plan.md`

Active benchmark and gate policy:

- `docs/adrs/ADR-0021-benchmark-stack.md`
- `docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md`
- `docs/validation/acceptance_gates.md`

This plan supersedes only the prioritization/order from the brainstorm
synthesis. It does not supersede existing safety, governance, promotion,
or fail-closed rules in the canonical roadmap.

Tier 0 `go` must not be easier to satisfy than the active benchmark and
Gate 1 policy. If this plan conflicts with ADR-0021, ADR-0022, or
GATES-0001, the stricter active policy controls unless the CIO writes a
separate ADR amendment first.

## Agent Operating Instructions

Use this section as the first checklist for every downstream agent.

1. Do not re-run the full brainstorm synthesis unless the user asks.
2. Do not search the whole repo for broad strategy ideas. Use the file
   pointers in each task first.
3. Do not implement Tier 1, Tier 2, or Tier 3 work until Tier 0A has a
   written `go` decision.
4. Do not add a strategy, model class, allocator, optimizer, or signal
   during Tier 0.
5. Do not change live-trading defaults. All new runtime behavior must
   remain fail-closed unless explicitly activated through existing
   controls.
6. Do not treat a passing backtest as production approval. Tier 0 is a
   capital-allocation decision input, not a promotion gate.
7. If implementation exposes a contradiction with this plan, stop and
   write a short contradiction note. Do not resolve by assumption.
8. Keep investigation bounded. If a referenced symbol has moved, use
   `rg` to locate it and continue. If the semantic owner cannot be found
   within 20 minutes, record the blocker and stop that task.

## Definitions

### As-Is TradingX

The current executable system with no Tier 0B fixes applied. This is the
baseline for measuring how much current runtime behavior differs from
advertised behavior.

As-Is TradingX is a preserved strategy/runtime behavior definition, not a
license to use old or untrusted measurement code. Final Tier 0A decision
metrics for As-Is TradingX must be produced by the same post-Tier-0B
measurement harness used for Cleaned Advertised TradingX. Metrics computed
before the harness is hardened may be exploratory only and must not appear
as decision evidence.

### Cleaned Advertised TradingX

TradingX after only those fixes that make existing declared behavior
real. A fix qualifies only if the behavior is already present in code,
schemas, governance artifacts, naming, or documented gates.

Cleaned Advertised TradingX must not include new alpha.

### New Alpha

Any new strategy, new model class, new allocator, new learned model, new
regime model, new instrument sleeve, new parameter optimization, or new
execution alpha not already declared as active behavior.

### Measurement Fix

A correction needed for Tier 0A results to mean what the current system
claims they mean. Examples: event-clock enforcement, VIX input wiring for
the existing regime classifier, SMA(200) minimum history, DSR unit
convention.

### Safety Prerequisite

A low-complexity runtime safety fix required if paper trading or live
shadowing continues during Tier 0. Examples: in-cycle kill-switch wiring
session-start equity persistence, minimal pre-trade rejection, and
hard-halt runtime wiring.

## Cleaned Bucket Inclusion Test

A change may enter the Cleaned Advertised TradingX bucket only when all
four conditions are true:

1. Existing code or docs already advertise the behavior.
2. The change makes that existing behavior real or correctly measured.
3. The change does not add a new signal, strategy, model class, or
   optimizer.
4. The change has a bounded acceptance test.

Classification table:

| Change | Cleaned bucket? | Reason |
|---|---:|---|
| Wire `vix_close` into `classify_regime` | Yes | `classify_regime` already accepts VIX and declares `risk_off` / `stressed` branches; runtime hardcodes `None`. |
| Wire 2s10s into `classify_regime` | Yes | `classify_regime` already accepts `yield_curve_spread_bps`; drift feature path already has Treasury cache semantics. |
| Change SMA(200) from `min_periods=1` to `min_periods=200` | Yes | The variable and regime semantics advertise a 200-day SMA. |
| Establish and enforce DSR unit convention | Yes | DSR already exists as a promotion/evaluation statistic but mixes units. |
| Fix legacy sleeve-attribution fallback | Yes | Per-sleeve attribution is advertised; legacy path assigns whole-portfolio return per sleeve. |
| Add HMM regime detection | No | New model class and new sizing semantics. |
| Add crisis overlay sleeve | No | New strategy. |
| Add HRP allocator | No | New allocator. |
| Train meta-labeling model | No | New learned model. |
| Switch GARCH default to EWMA | Borderline | Include only if an existing locked validation artifact explicitly says the advertised estimator policy is "use best validated estimator" and selects EWMA. Otherwise this is model-selection improvement and stays out of Tier 0. |

Borderline changes require a written two-sentence justification before
entry into Tier 0. Lack of objection is not approval.

Important distinction: "cleaned bucket eligible" does not mean "Tier 0B
required." Tier 0B includes only the tasks listed in `Tier 0B Exact
Scope`. Eligible cleaned fixes outside that list remain Tier 1 unless
Tier 0A cannot compute its required whole-portfolio benchmark metrics
without them. If that happens, stop and write a scope note before moving
the fix into Tier 0B.

## Tier Structure

### Tier 0A - Decision Gate

Purpose: decide whether TradingX deserves more work.

Outputs:

- benchmark report comparing As-Is TradingX and Cleaned Advertised
  TradingX against fixed baselines;
- decision memo using one of the exact decision values in
  `Final Decision Logic`;
- locked answers to capital trajectory, shorting policy, operator model,
  and hurdle rate.

Tier 0A is a research/evidence lane. It can run in parallel with Tier 0B
only for non-decision exploration. Final Tier 0A decision metrics must be
run after the Tier 0B measurement harness is accepted, using one harness
for As-Is TradingX, Cleaned Advertised TradingX, and all baselines.

### Tier 0B - Measurement And Safety Prerequisites

Purpose: make Tier 0A honest and safe to run.

Outputs:

- small code changes and tests;
- no new strategy behavior beyond existing advertised claims;
- no live enablement.

If paper trading or live shadowing continues during Tier 0A, Tier 0B also
includes every runtime safety prerequisite named in this plan: in-cycle
kill switch, session-open equity persistence, minimal pre-trade enforcer,
and hard-halt runtime wiring. If those controls are not implemented and
accepted first, paper/live-shadow order submission must be paused for the
Tier 0A window.

### Tier 1 - Land Only If Tier 0A Vindicates Edge

Purpose: wire high-value existing runtime safeguards after the CIO
decision says the bot is worth hardening.

### Tier 2 - Fidelity And Operational Robustness

Purpose: improve measurement fidelity, broker robustness, portfolio
monitoring, and allocator/strategy breadth after Tier 1.

### Tier 3 - Research Bets

Purpose: speculative alpha or advanced portfolio construction. No Tier 3
work starts before Tier 0A and Tier 1.

## Tier 0A Exact Scope

### 0A.1 Benchmarked Variants

Run exactly these TradingX variants:

1. `as_is_tradingx`: current executable behavior, no Tier 0B fixes.
2. `cleaned_advertised_tradingx`: current declared behavior after Tier
   0B measurement fixes only.

Both variants must be evaluated by the same accepted measurement harness.
The implementation may preserve As-Is behavior through a branch, tag,
fixture, isolated worktree, or explicit behavior adapter, but it must not
compare metrics generated by different analytics code, different data
manifests, different cost engines, or different uncertainty routines. If
As-Is behavior cannot be replayed through the accepted harness, the memo
decision is `blocked_as_is_unreproducible`.

As-Is must preserve pre-fix strategy/runtime decisions where they are
measurable without violating the accepted event-clock contract. Any legacy
metric that depends on look-ahead-only behavior or pre-hardening
measurement semantics is diagnostic only and must not be used as Tier 0A
decision evidence.

The cleaned variant must not include HMM, crisis overlay, HRP, ML
meta-labeling, new sleeves, new instruments beyond those required for
the fixed baselines, or any optimized parameter changes.

### 0A.2 Baselines

Run the active benchmark stack from ADR-0021 / ADR-0022 / GATES-0001 as
the hard decision benchmark:

1. `cash_tbill_dgs3mo`: daily cash return from the existing FRED DGS3MO
   risk-free cache semantics in `src/tradingx/risk_free.py`.
2. `monthly_60_40_spy_agg`: 60 percent SPY, 40 percent AGG, monthly
   rebalance, next-session execution under the same event-clock contract.
3. `operating_constraint`: Cleaned Advertised TradingX max drawdown must
   be no greater than 15 percent and CDaR@95 must be no greater than 8
   percent.
4. `out_of_sample_profile`: at least 756 trading days of out-of-sample
   data with Sharpe, CAGR, and max drawdown within 30 percent of the
   in-sample profile, using the active GATES-0001 denominator rule.

Run these diagnostics, but do not let them weaken or replace the active
benchmark stack:

1. `spy_buy_and_hold`: 100 percent SPY.
2. `quarterly_60_40_spy_tlt`: 60 percent SPY, 40 percent TLT, quarterly
   rebalance.
3. `quarterly_60_40_vix_gld_overlay`: base 60 percent SPY, 40 percent
   TLT. If prior available `VIXCLS` close is greater than 25, next
   session target is 54 percent SPY, 36 percent TLT, 10 percent GLD. If
   prior available `VIXCLS` close is less than or equal to 25, next
   session target is 60 percent SPY, 40 percent TLT, 0 percent GLD. No
   threshold optimization. This overlay is a stress diagnostic only; it
   is not a hard comparator unless a separate pre-existing ADR documents
   its economic thesis, lock date, threshold, weight, and rebalance
   policy.

Baselines must use the same date range, cost assumptions where
applicable, bar alignment, data adjustment policy, and risk-free source
as the TradingX variants.

### 0A.3 Horizon

Default horizon is five full calendar years ending at the most recent
fully available completed trading day in the local data cache.

If the local data cache cannot support five years for all required
symbols and macro series, use the longest common complete window of at
least three years. If fewer than three years are available, Tier 0A is
blocked and must report `blocked_insufficient_history`.

Recent-window evidence is not enough for `go` unless fixed crisis-regime
coverage is also present. The Tier 0A memo must report fixed stress
diagnostics for every fixed stress window covered by the local data cache,
including at minimum:

- COVID crash: 2020-02-19 through 2020-03-23;
- 2022 rate-shock equity drawdown: 2022-01-03 through 2022-10-12;
- every rolling 63-trading-day window in the shared evaluation calendar.

Fixed stress diagnostics may be computed as side-window diagnostics
outside the default five-year decision horizon when the local cache
contains the required data. Do not shorten away COVID merely because the
current five-year horizon starts after the COVID crash.

Each fixed stress diagnostic must be produced by replaying from a
predeclared warm-up period, then reporting only the fixed stress-window
slice. The warm-up period must be long enough to initialize SMA(200),
regime state, portfolio positions, order/cost state, and point-in-time
macro inputs before the first stress-window decision. Use the same
accepted harness, data manifests, cost model, capital scenarios, and
event-clock rules as the default evaluation. Do not seed stress-window
positions or regime state from future information. If the required warm-up
history or manifests are unavailable, Tier 0A must report
`blocked_stress_coverage_missing`.

If local data exists for a required fixed stress window but a required
symbol, risk-free series, macro series, cost input, or manifest hash is
missing for that window, Tier 0A must report
`blocked_stress_coverage_missing`. If no required fixed stress window can
be covered from the local cache, Tier 0A must also report
`blocked_stress_coverage_missing`. Rolling 63-day stress windows are
diagnostics and cannot by themselves permit `go`.

All Tier 0A metrics must use one shared evaluation calendar across
As-Is TradingX, Cleaned Advertised TradingX, and every baseline. The
calendar begins only after all of the following are true:

- required bar data exists for every traded or benchmark symbol;
- required risk-free data exists;
- required macro data exists under the Tier 0B availability-lag rule;
- Cleaned Advertised TradingX has enough eligible prior history for its
  SMA(200) regime input.

The first 199 SMA warm-up observations are excluded from the shared
evaluation calendar for all variants and baselines. Do not report
decision metrics over a calendar where the cleaned variant starts later
than the baselines or As-Is TradingX.

After the shared evaluation calendar starts, any missing required bar,
risk-free, or macro input blocks the Tier 0A decision with
`blocked_measurement_untrusted`. Do not exclude those days from only one
variant, and do not splice a non-contiguous calendar to rescue the
benchmark.

Do not download alternative vendors to extend the window during Tier 0A.
Data-source selection is a Tier 0B decision.

### 0A.4 Data Integrity, Execution Data, Capital, And Cost Policy

Tier 0A must separate return-accounting data from executable-price and
cost data.

Return accounting policy:

- equity and ETF return series for SPY, AGG, TLT, GLD, and TradingX
  instruments must be split- and dividend-adjusted total-return data, or
  the report must prove equivalent cash-distribution treatment;
- corporate-action semantics must be stated for each symbol;
- every raw and normalized data file used for return accounting must have
  a content hash, source name, retrieval timestamp, coverage window, and
  adjustment policy in a manifest linked from the Tier 0A report;
- mutable local cache paths are not sufficient evidence unless the
  manifest records the exact content hashes used for the run;
- commands that materialized or read the data must be listed.

Execution and cost policy:

- execution opens, closes used as execution proxies, spreads, volume,
  slippage, market impact, financing, and capacity must use raw
  executable-price/volume series where available;
- if only adjusted bars are available for an execution or cost input, the
  report must document a reversible adjustment model that maps adjusted
  prices and volumes back to executable semantics for that date;
- do not use total-return adjusted prices directly as fill prices, spread
  bases, volume bases, or impact bases without that reversible model;
- every execution/cost series must have the same manifest fields required
  for return series.

If adjusted-return evidence, executable-price evidence, corporate-action
evidence, manifest evidence, or cache-hash evidence is missing for a
decision-critical series, the memo decision must be
`blocked_measurement_untrusted`.

Capital tier is a pre-evaluation input scenario, not only a memo answer.
Before running Tier 0A metrics, define cost/capacity scenarios for:

- `paper_only`;
- `up_to_50k`;
- `50k_to_1m`;
- `above_1m`.

Each scenario must specify starting capital, maximum notional, leverage
assumption, turnover/notional scaling, commission, spread, slippage,
market-impact, financing, and capacity assumptions. The final memo may
select one 12-month capital trajectory answer, but the benchmark evidence
must show sensitivity across the scenario set. If the selected or any
plausible next-higher capital tier fails cost/capacity evidence, Tier 0A
cannot issue `go` for that capital trajectory.

Tier 0A must use one declared cost model across TradingX variants and all
applicable baselines within each capital scenario. Cleaned Advertised
TradingX must be evaluated under 1x, 2x, and 4x cost stress for each
decision-relevant capital scenario. If the existing cost path cannot
produce those stress results, the memo decision must be
`blocked_measurement_untrusted`.

### 0A.5 Required Metrics

Report these metrics for every variant and baseline:

- CAGR;
- annualized volatility;
- Lo-adjusted Sharpe;
- max drawdown;
- Calmar;
- CDaR 95;
- annualized turnover;
- estimated annualized cost drag;
- active return versus each baseline;
- active Lo-adjusted Sharpe versus each baseline;
- monthly hit rate versus `monthly_60_40_spy_agg`;
- worst rolling 63-trading-day return;
- fraction of days invested in cash or residual reserve;
- largest single calendar-quarter contribution to total active return
  versus `monthly_60_40_spy_agg`;
- paired log-relative-return or stationary-block-bootstrap confidence
  interval for active CAGR / relative terminal wealth versus
  `monthly_60_40_spy_agg`;
- 1x, 2x, and 4x cost-stress active CAGR and lower-bound active CAGR /
  relative terminal wealth versus `monthly_60_40_spy_agg` for every
  decision-relevant capital scenario;
- fixed stress-window return, max drawdown, and active return for every
  covered stress window.

If a metric cannot be produced by existing code within the investigation
budget, mark it `not_available_existing_path` and continue. Do not write
a new analytics framework inside Tier 0A.

Exception: decision-hurdle metrics are mandatory. If active CAGR,
Lo-adjusted Sharpe, max drawdown, calendar-quarter active-return
concentration, cash hurdle clearance, 60/40 opportunity-cost edge, CDaR
95, OOS profile, uncertainty lower bound, cost-stress lower bound, or
stress-window diagnostics is unavailable, the memo decision must be
`blocked_measurement_untrusted`. Do not issue `go` or `stop_or_refocus`
from incomplete hurdle metrics.

### 0A.6 Metric Formulas

Use these formulas unless an active ADR/Gate defines a stricter one:

- daily active return versus a baseline is `strategy_daily_return -
  baseline_daily_return`;
- active CAGR for hurdle purposes is `strategy_CAGR - baseline_CAGR`;
- cumulative active return is relative wealth:
  `prod(1 + strategy_daily_return) / prod(1 + baseline_daily_return) - 1`;
- active Lo-adjusted Sharpe is the Lo-adjusted Sharpe of daily active
  returns with zero risk-free rate because the series is self-financing;
- max drawdown and CDaR are computed on the strategy equity curve, not on
  the active-return spread;
- Calmar is `CAGR / abs(max_drawdown)`, reported as `not_meaningful` if
  max drawdown is zero;
- monthly hit rate is the fraction of calendar months where strategy
  compounded monthly return exceeds the baseline compounded monthly
  return;
- largest single-quarter contribution is the largest positive calendar
  quarter active return divided by the sum of positive calendar-quarter
  active returns. If the denominator is zero, the edge condition fails and
  the concentration metric is `not_meaningful_fail`.

Uncertainty requirement:

- hard-hurdle primary method: paired log relative returns,
  `log1p(strategy_daily_return) - log1p(baseline_daily_return)`, with a
  95 percent lower confidence bound converted to active CAGR over the
  shared evaluation calendar;
- acceptable alternative: stationary block bootstrap on paired daily
  strategy/baseline returns with a documented block-length rule and at
  least 2,000 resamples, reporting the lower 95 percent bound on relative
  terminal wealth and active CAGR;
- arithmetic daily active-return HAC may be reported as a diagnostic, but
  it cannot satisfy the hard lower-bound hurdle because the decision
  hurdle is geometric;
- if extra variants, candidate families, optimized thresholds, or
  unplanned comparison baselines are evaluated, the report must include a
  multiple-testing adjustment using the existing trials ledger, PBO/CPCV
  readiness state, or a written effective-trials calculation. Otherwise
  the memo decision is `blocked_measurement_untrusted`.

### 0A.7 Decision Hurdle

Tier 0A vindicates edge only if Cleaned Advertised TradingX satisfies all
conditions:

1. `hurdle_clearance`: cumulative return exceeds the DGS3MO cash hurdle
   cumulative return over the shared evaluation calendar;
2. `opportunity_cost_edge`: CAGR exceeds `monthly_60_40_spy_agg` CAGR by
   at least 2 percent absolute after modeled 1x costs;
3. `operating_constraint`: max drawdown is no greater than 15 percent and
   CDaR@95 is no greater than 8 percent;
4. `out_of_sample_profile`: at least 756 trading days of OOS data exist,
   and OOS Sharpe, CAGR, and max drawdown remain within 30 percent of the
   in-sample profile using the active GATES-0001 formula;
5. the paired log-relative-return or stationary-block-bootstrap lower 95
   percent bound on active CAGR / relative terminal wealth versus
   `monthly_60_40_spy_agg` is greater than zero;
6. active CAGR versus `monthly_60_40_spy_agg` remains positive under 1x,
   2x, and 4x cost stress for every decision-relevant capital scenario,
   and the 4x lower-bound active CAGR / relative terminal wealth is
   greater than zero;
7. results are not driven by one calendar quarter contributing more than
   60 percent of positive calendar-quarter active return;
8. required fixed stress diagnostics are present. For each covered fixed
   stress window, active return versus `monthly_60_40_spy_agg` must be
   non-negative. Rolling 63-trading-day stress diagnostics are required
   diagnostics but cannot replace fixed stress coverage for `go`;
9. As-Is TradingX was reproducibly measured from the preserved pre-fix
   commit, branch, or tag through the same accepted measurement harness as
   Cleaned Advertised TradingX.

PBO/CPCV and marginal-portfolio-contribution criteria must follow the
active GATES-0001 readiness rules without weakening them. For
sleeve-backed candidates, marginal portfolio contribution is hard-pass:
adding the candidate to the mandatory sleeve-backed reference book must
strictly improve portfolio Sharpe and Calmar and must not worsen
portfolio CDaR@95. If that evidence is unavailable or fails, Tier 0A
cannot issue `go`.

PBO remains governed by the active GATES-0001 readiness gates. Before
those readiness gates clear, PBO may be reported as `pending` exactly as
GATES-0001 allows. Once a PBO payload exists for the Gate 1 run, PBO is a
hard pass/fail gate and a failure blocks `go`.

The active hard-halt policy in GATES-0001 is not optional. If runtime
execution continues during Tier 0A, hard-halt runtime wiring must be a
Tier 0B safety prerequisite. If runtime execution is paused during Tier
0A, the Tier 0A memo must still state that hard-halt wiring is required
before any post-`go` paper/live-shadow order submission.

If these conditions are measured cleanly and fail, the recommendation is
`stop_or_refocus`. If they cannot be measured cleanly, use the applicable
blocked state in `Final Decision Logic`. The team may still choose to
continue, but the decision memo must say that the benchmark evidence did
not vindicate the current bot.

### 0A.8 Decision Memo Required Answers

These questions must be answered before the final benchmark run starts
and repeated in the memo:

1. Capital trajectory: maximum expected live capital over the next 12
   months: `paper_only`, `up_to_50k`, `50k_to_1m`, or `above_1m`.
2. Operator model: `solo_operator` or `multi_operator`.
3. Shorting policy: `not_in_12_months`, `research_only`, `paper_in_12_months`,
   or `live_in_12_months`.
4. Preference: `safety_first`, `alpha_first`, or `balanced`.
5. Benchmark hurdle: keep the default hurdle above or replace it with a
   stricter written hurdle.

The memo must include the exact commit SHA, dirty-worktree status, data
window, data sources, data manifest hashes, cost model, cost-stress
results by capital scenario, uncertainty method, stress-window coverage,
and commands used.

## Tier 0B Exact Scope

Tier 0B can proceed in parallel with Tier 0A only when it does not
contaminate the As-Is TradingX measurement. Agents must preserve a way
to replay the as-is behavior from the pre-fix commit, a clearly named
branch/tag, a fixture, or an isolated worktree through the same accepted
measurement harness used for the cleaned variant.

### 0B.1 Event-Clock Contract And Look-Ahead Enforcement

Objective:

Define and enforce the event-clock contract for daily-bar research and
runtime planning.

Contract:

- A decision for session `T+1` may use bars and macro observations whose
  availability timestamp is at or before the close of session `T`.
- A decision must not use the close, high, low, volume, fill, or macro
  value first available during or after session `T+1`.
- Backtest execution for a decision computed at `T` occurs at the next
  session open, or at the existing execution price convention if the
  backtest engine has a documented next-session equivalent.

Primary files:

- `src/tradingx/sleeves/evaluation.py`
- `src/tradingx/backtest.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/validation.py`

Required tests:

- perturb the current execution-session close and assert the current
  decision is unchanged;
- verify first eligible trade occurs only after enough prior data exists;
- verify no sleeve can access the execution-session close through
  `SleeveContext.bars_by_symbol`.

Acceptance:

- a short doc section or code comment names the event-clock contract;
- tests fail before the enforcement change and pass after;
- no existing sleeve silently switches from next-session to same-session
  decision semantics.

Non-goals:

- no intraday engine;
- no broker-clock synchronization work;
- no new strategy.

### 0B.2 VIX/2s10s PIT Data Wiring

Objective:

Make the existing regime classifier's advertised VIX and yield-curve
inputs real for Tier 0A cleaned measurement.

Source decision:

Use FRED daily data for Tier 0B. Do not revisit this source during Tier
0B.

- VIX series: `VIXCLS`
- Treasury spread: existing `DGS2` and `DGS10` path in
  `src/tradingx/risk_free.py`; spread is `DGS10 - DGS2` in basis points.

Bounded data requirements:

- daily close only;
- local CSV cache only;
- source name, pull timestamp, observation date, and availability policy
  captured in the cache or manifest;
- point-in-time lookup uses a conservative one-business-day availability
  lag: a decision for session `T+1` may use only FRED observations with
  `observation_date <= previous_business_day(T)`, where `T` is the
  decision session. A stored release timestamp may prove earlier
  availability, but absent that timestamp the one-business-day lag is
  mandatory;
- if the latest eligible FRED observation is older than five NYSE
  trading sessions, the macro input is missing for that decision date;
- missing macro values fail closed for the whole shared Tier 0A
  evaluation calendar. They must not be excluded from only the cleaned
  comparison.

Primary files:

- `src/tradingx/features/regime.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/validation.py`
- `src/tradingx/risk_free.py`
- `src/tradingx/drift/gateway.py`

Known current issues:

- `runtime_portfolio._build_regime_snapshots` hardcodes
  `vix_close=None` and `yield_curve_spread_bps=None`.
- `validation._build_default_regime_snapshots` hardcodes the same.
- `drift.gateway.MarketDataFeatureSampleReader.live_samples("vix_level")`
  returns an empty series.

Acceptance:

- historical replay can produce `risk_off` due to VIX > 25 and
  `stressed` due to VIX >= 35 without changing classifier thresholds;
- 2s10s inversion can contribute to `stressed` exactly as
  `classify_regime` already defines;
- Tier 0A report states FRED `VIXCLS`, `DGS2`, and `DGS10` date coverage;
- no intraday VIX, VIX futures curve, term structure, or vendor
  comparison is added.

### 0B.3 SMA(200) Minimum History Fix

Objective:

Ensure a 200-day SMA uses 200 observations.

Primary files:

- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/validation.py`
- any helper introduced by 0B.1 or 0B.2 to avoid duplicate regime logic.

Required change:

- replace `rolling(200, min_periods=1)` with behavior equivalent to
  `rolling(200, min_periods=200)`;
- days with fewer than 200 prior/eligible observations must be treated
  as insufficient regime history, not as a valid short-window SMA;
- Tier 0A must exclude those warm-up dates from the shared evaluation
  calendar for all variants and baselines. Do not hold only the cleaned
  variant in cash during warm-up, and do not include warm-up returns for
  As-Is TradingX or baselines in decision-hurdle metrics.

Acceptance:

- first 199 observations do not produce a valid SMA(200)-based regime
  decision for cleaned measurement;
- Tier 0A metrics start on the same post-warm-up date for As-Is
  TradingX, Cleaned Advertised TradingX, and all baselines;
- tests cover a 199-row input and a 200-row input.

### 0B.4 DSR Unit Convention

Objective:

Replace implicit Sharpe-unit mixing with an explicit convention for DSR
inputs and trial statistics. DSR is reported-only for Tier 0 and must not
be used as a Tier 0A pass/fail criterion unless a separate ADR/GATES
amendment first makes DSR trust-critical and this task is expanded to fix
trial-universe `n_trials` semantics.

Primary files:

- `src/tradingx/stats.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/trials.py`
- `src/tradingx/validation.py`
- `tests/unit/test_stats.py`
- `tests/unit/test_evaluation.py`
- `tests/unit/test_trials.py`

Current issue:

- `evaluation.py` passes annualized observed Sharpe into
  `deflated_sharpe_ratio`.
- `trials.py` stores and summarizes annualized trial Sharpe.
- `stats.expected_max_sharpe` converts variance by `periods_per_year`
  but adds it to `mean_trial_sharpe`, which may still be annualized.

Required design decision:

Use one convention across the DSR call chain. Preferred convention:
DSR functions accept per-period Sharpe inputs only. Annualized values may
exist in reports, but conversion must happen before calling DSR helpers.

Implementation requirements:

- name helper parameters with unit-bearing names such as
  `observed_sharpe_per_period` and `mean_trial_sharpe_per_period`;
- migrate callers explicitly;
- add tests that fail if annualized Sharpe is passed where per-period is
  required;
- preserve the Bailey/Lopez de Prado worked-example tests.

Acceptance:

- no DSR helper adds annualized and per-period quantities;
- trial mean, trial variance, observed Sharpe, and benchmark Sharpe are
  in the same units at the DSR boundary;
- existing DSR worked examples still pass;
- Tier 0A reports DSR, if present, as `reported_only`;
- Tier 0A does not block, `go`, or `stop_or_refocus` on DSR unless an
  explicit policy amendment also defines the trial universe and fixes
  `n_trials`.

Non-goal:

- do not redesign PBO, CPCV, Harvey-Liu effective N, or full trial-zoo
  accounting in Tier 0B. Those remain Tier 2 because DSR is not
  trust-critical in Tier 0A.

### 0B.5 Operator Kill-Switch In-Cycle And Side-String Fix

Objective:

Close cheap operator-control safety holes while paper evaluation may be
running.

Primary files:

- `src/tradingx/service.py`
- `src/tradingx/controller.py`
- `src/tradingx/operator_control.py`
- `tests/unit/test_service.py`
- `tests/unit/test_controller.py`

Current issues:

- `service.py` honors `kill_requested` at cycle boundary.
- `controller.py` operator halt branch checks `trade_intent.side == "buy"`.
- in-cycle risk evaluation does not receive `kill_requested` as a live
  control input.

Acceptance:

- if `kill_requested` is set after cycle start but before order submit,
  no new order is submitted;
- operator halt blocks any intent that increases absolute exposure, not
  only side string `buy`;
- reductions that decrease absolute exposure remain allowed unless the
  explicit kill switch requires all order submission to stop.

Non-goal:

- no Telegram, HMAC, two-approver, or supervisor-command redesign.

### 0B.6 Session Equity Persistence

Condition:

Do this in Tier 0B only if paper trading or live shadowing continues
during Tier 0A. If no runtime loop runs during Tier 0A, defer to Tier 1.

Objective:

Prevent daemon restart from resetting day-start equity used by daily PnL
and drawdown controls.

Primary files:

- `src/tradingx/service.py`
- `src/tradingx/controller.py`
- `src/tradingx/automation.py`
- persistence store that already writes
  `SessionOpenPortfolioStateRecord`

Acceptance:

- restart after session open restores the true session-open equity for
  that trading day;
- daily PnL and daily drawdown calculations do not reset to post-restart
  equity;
- if no session-open record exists, behavior is explicit and logged.

### 0B.7 Minimal Pre-Trade Enforcer Safety Prerequisite

Condition:

Do this in Tier 0B if any paper trading or live shadowing can submit
orders during Tier 0A. If all paper/live-shadow order submission is
paused for the full Tier 0A window, this remains Tier 1 work.

Objective:

Prevent avoidable order-entry failures while the benchmark decision is
being prepared.

Controls included:

1. fat-finger notional limit;
2. fat-finger share limit;
3. price collar versus last trade or arrival reference;
4. max order rate per minute and max open orders.

Acceptance:

- order exceeding notional limit is rejected before broker submit;
- order exceeding share limit is rejected before broker submit;
- order outside collar is rejected before broker submit;
- open-order and order-rate limits reject before broker submit;
- rejection records include structured reason codes.

### 0B.8 Portfolio Hard Halt Runtime Wiring Safety Prerequisite

Condition:

Do this in Tier 0B if paper trading or live shadowing can continue during
Tier 0A. If runtime execution is paused for Tier 0A, this remains a
post-`go` prerequisite before any further paper/live-shadow order
submission.

Objective:

Make the active GATES-0001 hard-halt runtime policy true without adding
auto-flatten semantics.

Required behavior:

- measure trailing portfolio drawdown against
  `PortfolioBlueprint.mdd_hard_halt`;
- on breach, call `runtime_host.trigger_hard_halt`;
- stop service, alert operator, latch recovery-required state;
- do not call `flatten_all` as part of this task.

Acceptance:

- a synthetic equity curve breaching the hard-halt threshold stops the
  runtime host and publishes a critical alert;
- repeated checks after latch do not spam halt requests;
- no auto-flatten path is introduced.

### 0B.9 Benchmark Evidence Harness

Objective:

Make Tier 0A's active benchmark-stack, uncertainty, data-manifest, and
cost-stress evidence reproducible without adding alpha.

Primary files:

- `src/tradingx/validation.py`
- `src/tradingx/benchmark_stack.py`
- `src/tradingx/backtest.py`
- `src/tradingx/costs.py`
- `src/tradingx/stats.py`
- any existing data-manifest or fingerprint helper used by the validation
  path.

Required behavior:

- materialize `cash_tbill_dgs3mo` and `monthly_60_40_spy_agg` through the
  active benchmark-stack semantics;
- compute the Tier 0A formula-defined active-return, log-relative
  uncertainty, concentration, OOS-profile, CDaR, capital-scenario, and
  cost-stress fields;
- run As-Is TradingX and Cleaned Advertised TradingX through the same
  accepted harness and data/cost manifests;
- write or link a manifest containing data source, adjustment policy,
  corporate-action policy, execution-data policy, retrieval timestamp,
  coverage window, and content hash for every decision-critical series;
- preserve the diagnostic SPY, SPY/TLT, and VIX/GLD overlay baselines as
  diagnostics only.

Acceptance:

- a fixture where TradingX beats `monthly_60_40_spy_agg` by less than 2
  percent absolute CAGR cannot produce `go`;
- a fixture with positive point active CAGR but non-positive geometric
  lower 95 percent active-CAGR / relative-terminal-wealth bound cannot
  produce `go`;
- a fixture with missing adjusted-price or cache-hash evidence cannot
  produce `go`;
- a fixture with missing raw executable-price/volume evidence and no
  reversible adjustment model cannot produce `go`;
- a fixture that passes at 1x costs but fails 4x lower-bound active CAGR /
  relative terminal wealth for a decision-relevant capital scenario cannot
  produce `go`;
- a fixture with rolling stress coverage but no fixed stress coverage
  produces `blocked_stress_coverage_missing`;
- a fixture whose As-Is metrics were produced by a different measurement
  harness cannot produce `go`.

## Tier 1 Exact Scope

Tier 1 starts only after Tier 0A produces a written `go` decision.

### 1.1 Sleeve Attribution Legacy Fallback

Objective:

Remove the broken legacy fallback that assigns whole-portfolio daily
return to every sleeve.

Primary files:

- `src/tradingx/drift/attribution.py`
- `src/tradingx/drift/sleeve_ledger.py`

Acceptance:

- fallback path computes sleeve returns from sleeve-specific open/close
  exposure and prices;
- per-sleeve ending equity reconciles to portfolio equity within a
  documented tolerance;
- no sleeve receives `daily_return=portfolio_daily_return` merely
  because blueprint activation is absent.

### 1.2 Minimal Pre-Trade Enforcer

This is Tier 1 only if paper/live-shadow order submission was paused
during Tier 0A. If any paper/live-shadow order path runs during Tier 0A,
the same work is promoted to Tier 0B.7 and must be accepted before order
submission continues.

Objective:

Enforce the four Knight-Capital-shape controls in the live/paper order
path.

Controls included:

1. fat-finger notional limit;
2. fat-finger share limit;
3. price collar versus last trade or arrival reference;
4. max order rate per minute and max open orders.

Primary files:

- `src/tradingx/execution.py`
- `src/tradingx/controller.py`
- `src/tradingx/live_probe_governance.py`
- `src/tradingx/promotion.py`

Explicit exclusions:

- buying-power precheck unless existing risk path is proven absent;
- margin precheck unless shorts are in scope;
- locate precheck unless shorts are in scope;
- cancel-on-disconnect;
- self-trade prevention;
- duplicate prevention beyond existing deterministic client order IDs.

Acceptance:

- order exceeding notional limit is rejected before broker submit;
- order exceeding share limit is rejected before broker submit;
- order outside collar is rejected before broker submit;
- open-order and order-rate limits reject before broker submit;
- rejection records include structured reason codes.

### 1.3 Portfolio Hard Halt Stop/Alert/Latch Wiring

This is Tier 1 only if runtime execution was paused during Tier 0A. If
paper/live-shadow execution continues during Tier 0A, the same work is
promoted to Tier 0B.8 and must be accepted before execution continues.

Objective:

Wire the existing hard-halt controller into runtime without introducing
auto-flatten semantics.

Primary files:

- `src/tradingx/portfolio/hard_halt.py`
- `src/tradingx/runtime_host.py`
- `src/tradingx/service.py`
- `src/tradingx/portfolio/blueprint.py`

Required behavior:

- measure trailing portfolio drawdown against
  `PortfolioBlueprint.mdd_hard_halt`;
- on breach, call `runtime_host.trigger_hard_halt`;
- stop service, alert operator, latch recovery-required state;
- do not call `flatten_all` as part of this task.

Acceptance:

- a synthetic equity curve breaching the hard-halt threshold stops the
  runtime host and publishes a critical alert;
- repeated checks after latch do not spam halt requests;
- no auto-flatten path is introduced.

## Tier 2 Queue

These items are intentionally not Tier 0 or Tier 1:

- TCA observation wiring and impact calibration;
- cross-sleeve correlation monitor;
- equal-vol allocator;
- crisis overlay sleeve;
- broker-write circuit breaker;
- decision-equivalence harness between paper and backtest;
- scheduler launching record before `run_market_day`;
- no-action streak counter;
- fingerprint provenance schema split between refs and hashes;
- borrow accrual, margin, and locate enforcement unless shorting policy
  moves shorts into the 12-month roadmap.

Each Tier 2 item needs its own small plan before implementation.

## Tier 3 Queue

These are research bets and must not appear in Tier 0 cleaned results:

- HMM regime detection;
- HRP allocator;
- ML meta-labeling;
- intraday opening-range breakout;
- pairs / cointegration;
- treasury carry;
- VRP harvesting;
- PEAD;
- A/B candidate routing.

## Execution Order

Recommended parallelization:

1. Create a branch, tag, fixture, or isolated worktree that preserves
   As-Is TradingX behavior for replay.
2. Decide whether paper trading or live shadowing will continue during
   Tier 0A. If yes, implement and accept Tier 0B.5, 0B.6, 0B.7, and 0B.8
   before any further order submission. If no, pause runtime execution for
   the Tier 0A window and record that in the memo.
3. Implement Tier 0B.1, 0B.2, 0B.3, 0B.4, and 0B.9. Tier 0B.2 must use
   FRED only.
4. Accept the Tier 0B measurement harness. Do not use metrics generated
   before this point as final Tier 0A decision evidence.
5. Run As-Is TradingX, Cleaned Advertised TradingX, and all baselines
   through the same accepted harness, data manifests, cost model, capital
   scenarios, stress-window protocol, and uncertainty method.
6. Write Tier 0A decision memo.
7. Only if memo is `go`, start remaining Tier 1 work.

Do not run Tier 1 before the Tier 0A decision memo.

## Required Artifact Names

Use these exact artifact names unless the user explicitly changes them:

- Tier 0A report:
  `docs/reports/tradingx_tier0a_benchmark_decision_report.md`
- Tier 0A raw metrics:
  `docs/reports/tradingx_tier0a_benchmark_metrics.json`
- Tier 0B implementation report:
  `docs/reports/tradingx_tier0b_measurement_safety_report.md`
- Tier 1 implementation report:
  `docs/reports/tradingx_tier1_foundation_wiring_report.md`

If implementation produces additional artifacts, link them from the
report. Do not replace these names.

## Adversarial Review Checklist

Reviewers should reject the work if any item is true:

1. Cleaned TradingX includes a new strategy, model class, allocator, or
   optimized parameter not present in advertised behavior.
2. VIX wiring uses intraday VIX, futures curve, or a second vendor in
   Tier 0B.
3. Macro inputs use observation-date values without the required
   one-business-day FRED availability lag or stored release timestamps.
4. Baselines use a different shared evaluation calendar, data source
   policy, or cost policy than TradingX.
5. Missing post-start macro, risk-free, or bar inputs are excluded from
   only one variant instead of blocking the decision.
6. Any decision-hurdle metric is unavailable and the memo decision is
   not `blocked_measurement_untrusted`.
7. Tier 0A uses quarterly SPY/TLT, SPY-only, or the VIX/GLD overlay as a
   substitute for the active cash plus monthly 60/40 SPY/AGG benchmark
   stack.
8. A `go` is issued without passing active Gate 1 benchmark-stack
   criteria, including cash hurdle, 2 percent absolute CAGR edge over
   monthly SPY/AGG, max drawdown, CDaR@95, and OOS profile.
9. A `go` is issued without adjusted-price/corporate-action policy,
   replayable data manifests, and content hashes for every
   decision-critical series.
10. A `go` is issued from point estimates only, without paired
   log-relative-return or stationary-block-bootstrap lower-bound evidence
   on active CAGR / relative terminal wealth.
11. A `go` is issued without capital-scenario inputs and 1x, 2x, and 4x
   cost-stress evidence for decision-relevant capital scenarios.
12. A `go` is issued without required fixed stress-regime diagnostics,
   from a shared calendar with rolling-only stress coverage, or from fixed
   stress diagnostics that did not replay from a predeclared warm-up
   period.
13. As-Is TradingX is not reproducibly measured from the preserved
   pre-fix commit, branch, or tag through the same accepted measurement
   harness as Cleaned Advertised TradingX, or legacy look-ahead-only
   metrics are used as decision evidence.
14. DSR is used as a Tier 0 pass/fail criterion without a policy amendment
   and a trustworthy trial-universe / `n_trials` definition.
15. Event-clock tests can be bypassed by a sleeve reading the current
   execution-session close.
16. Hard halt task introduces auto-flatten.
17. Paper/live-shadow order submission continues during Tier 0A before
   the kill switch, session-equity persistence, minimal pre-trade
   enforcer, and hard-halt runtime wiring are accepted.
18. Pre-trade enforcer expands to shorts, margin, cancel-on-disconnect,
   self-trade prevention, or duplicate-prevention redesign in Tier 0B or
   Tier 1.
19. Tier 1 starts without a Tier 0A decision memo whose decision is
   `go`.
20. `blocked_remediation_required` is treated as permission to start
   Tier 1 before rerun and successful `go` decision.
21. Any report omits commit SHA, dirty-worktree status, data window, data
   manifest hashes, raw execution/cost data policy, capital scenarios,
   cost assumptions, uncertainty method, stress coverage, and commands
   run.
22. An agent marks a blocked metric or task as passed without evidence.

## Final Decision Logic

Use this exact decision mapping in the Tier 0A memo:

| Evidence state | Memo decision |
|---|---|
| Cleaned Advertised TradingX satisfies all hurdle conditions | `go` |
| Cleaned Advertised TradingX fails only because of a documented Tier 0B implementation defect with a bounded fix | `blocked_remediation_required` |
| Cleaned Advertised TradingX fails hurdle conditions without a bounded implementation defect | `stop_or_refocus` |
| Common data window is less than three years | `blocked_insufficient_history` |
| Any decision-hurdle metric is unavailable | `blocked_measurement_untrusted` |
| As-Is TradingX cannot be reproduced from the preserved pre-fix commit, branch, tag, fixture, or isolated worktree through the accepted measurement harness | `blocked_as_is_unreproducible` |
| Active benchmark-stack, same-engine As-Is/Cleaned comparison, event-clock, macro PIT wiring, shared evaluation calendar, data integrity, executable-price/cost data, capital scenarios, cost stress, or geometric uncertainty evidence cannot be made trustworthy | `blocked_measurement_untrusted` |
| Required stress-regime coverage is absent | `blocked_stress_coverage_missing` |
| Paper/live-shadow order submission continued during Tier 0A without accepted Tier 0 runtime safety prerequisites | `blocked_measurement_untrusted` |

Only `go` unlocks Tier 1. `blocked_remediation_required` requires
applying the bounded remediation, rerunning the cleaned benchmark, and
issuing a new Tier 0A memo before Tier 1 can start.
