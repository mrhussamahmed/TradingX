# Implementation Plan: TradingX Tier0 Decision and Cleaning

## 1. Source Plan

- Source plan path: `/Users/ahmedabd/Desktop/AI Projects/TradingX/docs/superpowers/plans/2026-04-27-tradingx-tier0-decision-and-cleaning-plan.md`
- Generated timestamp: `2026-04-28T07:44:03Z`
- Current branch: `main`
- Current commit SHA: `b0154070c802feeb99a22d288258cbe55eb12627`
- Working tree status summary: dirty before this implementation plan was created. Existing status included modified `webapp/src/control-center/flavors/EvidenceTimeline.tsx`, modified `webapp/src/control-center/flavors/__tests__/EvidenceTimeline.test.tsx`, and untracked planning/assets including the source plan itself. This file is the only planned filesystem change for this planning task.
- Source plan read successfully: Yes.
- Repository scanned successfully: Yes.

## 2. Plan Summary

This plan is trying to make TradingX answer one narrow question:

Does the current TradingX system deserve more engineering work after its already-advertised behavior is made real and measured honestly?

It is not a plan to add new strategies, new alpha, new models, new allocators, or new optimizers. Tier 0 is only allowed to measure the current system, fix measurement correctness issues, and apply small safety controls needed to run paper/live-shadow evaluation without avoidable operator-control risk.

The core idea is to compare two versions of TradingX:

1. As-Is TradingX
   The current executable behavior before Tier 0 fixes.

2. Cleaned Advertised TradingX
   The same system after only narrow fixes that make existing declared behavior real, such as event-clock enforcement, proper VIX/2s10s regime input wiring, real SMA(200) history requirements, DSR unit consistency, and benchmark evidence harness fixes.

Both versions must be measured using the same accepted harness, same data manifests, same cost model, same shared calendar, same uncertainty method, and same benchmark stack. Any comparison using different measurement logic is invalid.

Tier 0A is the decision gate. It produces a benchmark report and decision memo. The cleaned system must beat the active benchmark policy, especially cash and monthly 60/40 SPY/AGG, under strict drawdown, CDaR, out-of-sample, uncertainty, stress-window, and cost-stress requirements. Only a clean `go` decision allows Tier 1 work.

Tier 0B is the measurement and safety prerequisite work. It makes the evidence trustworthy and prevents unsafe paper/live-shadow order submission. It includes event-clock/look-ahead enforcement, FRED VIX and 2s10s wiring, SMA(200) minimum history, DSR unit cleanup, safety controls, hard-halt wiring if runtime continues, and a reproducible benchmark evidence harness.

Tier 1 starts only after Tier 0A returns `go`. It wires additional foundation safety items such as sleeve attribution fixes, pre-trade enforcement, and hard-halt runtime integration if they were not already required during Tier 0.

Tier 2 and Tier 3 are explicitly out of scope for Tier 0. They include fidelity improvements, operational robustness, new allocators, crisis overlays, HMM, HRP, ML meta-labeling, and other research bets.

The plan’s main guardrail is scope control. Any AI agent implementing this must not invent missing strategy logic, widen the plan, improve alpha, or treat a passing backtest as production approval. If a contradiction or ambiguity appears, the agent must stop and write a short blocker or clarification note instead of assuming permission.

The final output must be a controlled decision:

`go`
TradingX passed the strict benchmark evidence and Tier 1 may start.

`stop_or_refocus`
TradingX was measurable but failed the hurdle.

`blocked_remediation_required`
A bounded Tier 0B defect blocked a fair result and must be fixed before rerun.

`blocked_measurement_untrusted`
The evidence cannot be trusted.

`blocked_insufficient_history`
There is not enough common data history.

`blocked_as_is_unreproducible`
The pre-fix As-Is system cannot be replayed through the accepted harness.

`blocked_stress_coverage_missing`
Required stress-window coverage is missing.

Only `go` unlocks Tier 1.

## 3. Current Repository State

Relevant modules/files already implemented:

- `src/tradingx/features/regime.py`: existing rule classifier accepts `vix_close` and `yield_curve_spread_bps`, with VIX 25/35 thresholds and 2s10s inversion behavior.
- `src/tradingx/runtime_portfolio.py`: runtime portfolio planner builds regime snapshots, but currently uses `rolling(200, min_periods=1)` and passes `vix_close=None` / `yield_curve_spread_bps=None`.
- `src/tradingx/validation.py`: Gate 1 validation and sleeve replay path exists, but default regime snapshots use the same short-window SMA and missing macro inputs.
- `src/tradingx/sleeves/evaluation.py`: sleeve-to-backtest bridge exists, but `SleeveContext.bars_by_symbol` includes bars through the current bar, allowing a sleeve to inspect the execution-session close.
- `src/tradingx/backtest.py`: daily-bar next-open style engine exists and models open/close phases plus costs.
- `src/tradingx/risk_free.py`: DGS3MO risk-free cache exists, and DGS2/DGS10 treasury yield cache plus `spread_2s10s_bps` already exist. No VIXCLS cache path exists.
- `src/tradingx/drift/gateway.py`: drift sample reader exists; `vix_level` currently returns an empty series, yield curve reads the Treasury cache, and SMA sample uses `min_periods=1`.
- `src/tradingx/benchmark_stack.py`: cash hurdle and monthly 60/40 SPY/AGG benchmark stack exists with 15% MDD / 8% CDaR / 25% hard-halt metadata.
- `src/tradingx/stats.py`: Lo-adjusted Sharpe, max drawdown, CDaR, DSR primitives, stationary bootstrap, and paired benchmark uncertainty helpers exist. Current paired uncertainty is arithmetic paired-difference HAC, not the Tier 0A geometric log-relative-return hard hurdle.
- `src/tradingx/evaluation.py`, `src/tradingx/trials.py`: DSR is wired through candidate evaluation/trials, but annualized Sharpe values are passed/stored at boundaries that the source plan says must use a consistent per-period convention.
- `src/tradingx/service.py`, `src/tradingx/controller.py`, `src/tradingx/operator_control.py`, `src/tradingx/risk.py`: paper runtime, operator control, and risk checks exist. Kill is honored at service cycle boundary, not as an in-cycle live control input before order submission. Operator halt currently blocks `trade_intent.side == "buy"` only.
- `src/tradingx/portfolio/hard_halt.py`: `PortfolioHardHaltController` exists and has unit tests. It is not wired into the service runtime path.
- `src/tradingx/automation.py`, `src/tradingx/persistence/__init__.py`: `SessionOpenPortfolioStateRecord` write/read exists and automation pre-open/close uses it. The service/controller daily PnL path still keeps `_session_start_equity` in memory and does not restore it on restart.
- `src/tradingx/__main__.py`: CLI subcommands exist for benchmark stack preparation, gate reports, statistical reports, dataset manifests, cost reports, and related evidence. There is no dedicated Tier 0A As-Is vs Cleaned decision harness command or report writer.

What already satisfies the plan:

- The classifier already declares the VIX and yield-curve branches the plan wants wired.
- DGS3MO, DGS2, and DGS10 FRED cache semantics partially exist.
- Cash and monthly 60/40 SPY/AGG benchmark primitives exist.
- Max drawdown and CDaR primitives exist.
- Next-open daily-bar backtest semantics partially exist and are tested.
- Hard-halt controller exists as a reusable component, though not runtime-integrated.
- Session-open portfolio state artifact type and persistence exist.
- Existing test coverage includes relevant unit/integration tests for regime, risk-free data, backtest, benchmark stack, validation, stats, evaluation, trials, service, controller, risk, and hard halt.

What partially satisfies the plan:

- Event-clock: backtest execution is next-open, but sleeve decisions can see the current bar and there is no shared event-clock contract enforcement across validation/runtime planning.
- Macro data: DGS2/DGS10 exists, but VIXCLS does not; runtime and validation ignore both VIX and 2s10s.
- SMA(200): helper locations compute a 200-day rolling value, but use `min_periods=1`, which violates the plan.
- DSR: primitives and evidence-pack field exist, but unit convention is mixed and not explicit.
- Benchmark evidence: Gate 1 criteria exist, but Tier 0A requires a stricter two-variant, same-harness benchmark report with manifests, stress windows, capital scenarios, geometric uncertainty, concentration, and controlled decision logic.
- Cost stress: 1x/2x/4x stress reruns exist as Gate 2-style profitability checks, but not the Tier 0A lower-bound active CAGR / relative terminal wealth tests by capital scenario.
- Safety: runtime has basic risk checks and promotion route guards, but not the exact in-cycle kill, exposure-aware operator halt, pre-trade enforcer controls, persisted session equity restore, or hard-halt service wiring required when order submission continues.

What is missing:

- As-Is preservation mechanism that can replay pre-fix behavior through the accepted post-Tier-0B harness.
- A Tier 0A-specific evidence harness/report/memo that compares `as_is_tradingx`, `cleaned_advertised_tradingx`, cash, monthly 60/40 SPY/AGG, and diagnostic baselines under one calendar, one manifest set, one cost model, one uncertainty method, and one benchmark stack.
- VIXCLS local CSV cache, FRED availability-lag lookup, and stale macro fail-closed logic.
- Shared calendar logic that excludes first 199 SMA warm-up observations for every variant and baseline.
- Required fixed stress-window replay protocol and blocked state for missing stress coverage.
- Return-accounting versus executable-price/cost data manifest evidence with content hashes for every decision-critical series.
- Tier 0A capital scenarios and capital-tier cost/capacity sensitivity.
- Controlled final decision mapping for Tier 0A.

What conflicts with the plan:

- `runtime_portfolio._build_regime_snapshots` and `validation._build_default_regime_snapshots` hardcode `vix_close=None` and `yield_curve_spread_bps=None`.
- `runtime_portfolio.py`, `validation.py`, `drift/gateway.py`, and integration test helpers use `rolling(200, min_periods=1)`.
- `sleeves/evaluation.py` passes `bars.iloc[: position + 1]` into sleeve decisions, exposing the current bar.
- `drift.gateway.MarketDataFeatureSampleReader.live_samples("vix_level")` returns an empty series.
- `evaluation.py` passes annualized Sharpe into `deflated_sharpe_ratio`, while `stats.expected_max_sharpe` converts variance by periods/year and may add it to annualized `mean_trial_sharpe`.
- `controller.py` operator halt branch checks only `trade_intent.side == "buy"`.
- `service.py` honors `kill_requested` only at cycle boundary.
- `docs/validation/acceptance_gates.md` says hard-halt runtime enforcement exists, but repo wiring appears limited to the controller component and tests, not service runtime integration.
- Existing paired benchmark uncertainty uses arithmetic return differences; Tier 0A hard hurdle requires paired log-relative returns or stationary block bootstrap on paired returns.

Existing tests related to the plan:

- Unit: `tests/unit/test_regime.py`, `tests/unit/test_risk_free.py`, `tests/unit/test_benchmark_stack.py`, `tests/unit/test_backtest.py`, `tests/unit/test_stats.py`, `tests/unit/test_evaluation.py`, `tests/unit/test_trials.py`, `tests/unit/test_validation.py`, `tests/unit/test_controller.py`, `tests/unit/test_service.py`, `tests/unit/test_risk.py`, `tests/unit/test_portfolio_hard_halt.py`, `tests/unit/test_runtime_portfolio.py`, `tests/unit/test_main.py`.
- Integration: `tests/integration/test_sleeves_end_to_end.py`, `tests/integration/test_gate_validation_pipeline.py`, `tests/integration/test_cpcv_pbo_pipeline.py`.

Existing CLI commands or harnesses related to the plan:

- `tradingx prepare-benchmark-closes` / `tradingx prepare-benchmark-stack`
- `tradingx gate-report`
- `tradingx statistical-report`
- `tradingx dataset-manifest`
- `tradingx cost-model-report`
- `tradingx capacity-curve`
- `scripts/run_backtest.py`
- `scripts/validate`

Current behavior that must be preserved:

- Existing classifier thresholds and semantics. Wire inputs; do not change thresholds.
- Daily-bar next-open execution convention unless only documenting/enforcing the existing next-session equivalent.
- Existing cash and 60/40 benchmark policy; do not substitute weaker diagnostics.
- Existing fail-closed runtime defaults and live-trading disable controls.
- Existing DSR worked-example tests.
- Existing promotion/governance safety artifacts outside the exact Tier 0 changes.

## 4. Scope Lock

Tier 0A decision-gate work explicitly allowed:

- Preserve/replay As-Is TradingX and Cleaned Advertised TradingX through the same accepted measurement harness.
- Materialize cash `cash_tbill_dgs3mo` and monthly `monthly_60_40_spy_agg`.
- Include diagnostic SPY, quarterly SPY/TLT, and VIX/GLD overlay baselines only as diagnostics.
- Evaluate required horizon, shared calendar, fixed stress windows, rolling 63-day diagnostics, data integrity, capital scenarios, cost stresses, required metrics, geometric uncertainty, concentration, OOS, drawdown, CDaR, and final decision mapping.
- Produce `docs/reports/tradingx_tier0a_benchmark_decision_report.md` and `docs/reports/tradingx_tier0a_benchmark_metrics.json`.

Tier 0B measurement/safety prerequisite work explicitly allowed:

- Event-clock/look-ahead contract enforcement.
- FRED VIXCLS and DGS2/DGS10 2s10s point-in-time wiring with the source-plan lag rule.
- SMA(200) minimum history enforcement and shared warm-up exclusion.
- DSR unit convention cleanup, reported-only for Tier 0.
- Benchmark evidence harness hardening.
- If runtime order submission continues during Tier 0A: in-cycle kill switch, session-open equity persistence, minimal pre-trade enforcer, and hard-halt runtime wiring.
- Produce `docs/reports/tradingx_tier0b_measurement_safety_report.md`.

Tier 1 work allowed only after `go`:

- Sleeve attribution legacy fallback.
- Minimal pre-trade enforcer only if paper/live-shadow order submission was paused during Tier 0A.
- Portfolio hard-halt runtime wiring only if runtime execution was paused during Tier 0A.
- Produce `docs/reports/tradingx_tier1_foundation_wiring_report.md` only after `go`.

Tier 2/Tier 3 out of scope:

- Tier 2 fidelity/operational robustness items and any new allocator/strategy breadth.
- Tier 3 research bets.

## 5. Out of Scope

Forbidden work:

- New strategies.
- New alpha.
- New models.
- New allocators.
- New optimizers.
- HMM.
- HRP.
- ML meta-labeling.
- Crisis overlays.
- Production approval.
- Broad refactoring.
- Research bets.
- Intraday engine or broker-clock synchronization.
- Intraday VIX, VIX futures term structure, alternate macro vendors, or vendor comparisons.
- Threshold optimization.
- PBO/CPCV redesign, Harvey-Liu effective N redesign, or full trial-zoo accounting in Tier 0B.
- Shorts, margin, locate enforcement, cancel-on-disconnect, self-trade prevention, or duplicate-prevention redesign inside the minimal pre-trade enforcer.
- Auto-flatten as part of hard halt.
- Any scope not traceable to the source plan.

## 6. Source-of-Truth Mapping

| Plan Section | Requirement / Decision | Existing Code? Yes/No/Partial | Repo Location | Implementation Action | Notes / Ambiguity |
|---|---|---|---|---|---|
| Non-Negotiable Rule | Tier 0 measures current system, fixes measurement correctness, and only small runtime safety if needed | Partial | Whole repo; docs | Add guardrails to Tier 0 report/harness and reject untraceable behavior | No new alpha or strategy logic |
| Definitions: As-Is TradingX | Preserve pre-fix behavior and replay through accepted harness | No | Git history; future Tier 0 harness | Create immutable behavior artifact before fixes: commit SHA plus dirty executable diffs, sealed worktree hash, fixture hash, or explicit adapter hash | Must define preserved pre-fix decisions after excluding legacy look-ahead-only evidence |
| Definitions: Cleaned Advertised TradingX | Include only fixes making declared behavior real | Partial | `features/regime.py`, validation/runtime docs | Wire exact advertised behavior only | No HMM/HRP/overlay/optimization |
| 0A.1 | Evaluate `as_is_tradingx` and `cleaned_advertised_tradingx` with same harness | No | `validation.py`, `backtest.py`, new Tier 0 harness/report module | Build two-variant harness with shared measurement components | Block as `blocked_as_is_unreproducible` if As-Is cannot replay |
| 0A.2 | Cash DGS3MO benchmark | Yes/Partial | `risk_free.py`, `benchmark_stack.py` | Reuse DGS3MO cache and include as hard hurdle | Need manifests/hashes |
| 0A.2 | Monthly 60/40 SPY/AGG benchmark | Yes/Partial | `benchmark_stack.py` | Reuse monthly rebalance logic; enforce next-session execution/event-clock semantics plus shared calendar/cost policy | Current implementation uses closes only; Tier 0 needs manifest/cost/fill alignment |
| 0A.2 | Diagnostic SPY, quarterly SPY/TLT, VIX/GLD overlay | No/Partial | `benchmark_stack.py` or Tier 0 harness | Add diagnostics only if traceable and clearly non-hard | Must not weaken active stack |
| 0A.3 | Five-year default, longest common >=3 years, stress windows | No | Tier 0 harness | Add horizon/window resolver and blocked decisions | No alternate vendor downloads |
| 0A.3 | Shared evaluation calendar and 199 SMA warm-up exclusion | No/Partial | `validation.py`, `runtime_portfolio.py`, Tier 0 harness | Enforce common calendar after all inputs valid | Missing post-start inputs block decision |
| 0A.4 | Return accounting vs executable-price/cost data separation | Partial | `data_fingerprint.py`, `costs.py`, schemas, Tier 0 harness | Require manifests and block if missing critical evidence | Do not use adjusted bars as fills without documented reversible model |
| 0A.4 | Capital scenarios and one cost model with 1x/2x/4x stress | Partial | `costs.py`, `evaluation.py`, Tier 0 harness | Add scenario inputs and active lower-bound cost-stress evidence | Existing cost sensitivity is not sufficient |
| 0A.5/0A.6 | Required metrics and formulas | Partial | `stats.py`, `validation.py`, Tier 0 harness | Split mandatory hurdle metrics from non-hurdle report metrics; mandatory hurdle metrics block if missing, while non-hurdle metrics may be `not_available_existing_path` | Avoid new analytics framework beyond required harness |
| 0A.6 | Paired log-relative-return or stationary bootstrap uncertainty | Partial | `stats.py` | Add geometric hard-hurdle uncertainty path | Existing arithmetic HAC is diagnostic only |
| 0A.7 | Decision hurdle and final result rules | Partial | `validation.py`, new Tier 0 decision module | Implement controlled decision mapping | Only `go` unlocks Tier 1 |
| 0A.7 / GATES-0001 | PBO/CPCV readiness and hard-gate handling | Partial | `validation.py`, `pbo.py`, CPCV tests | Carry active GATES-0001 readiness rules into Tier 0A; `pending` allowed only before readiness, PBO payload failure blocks `go` | Harness must not bypass active Gate 1 |
| 0A.7 / GATES-0001 | Marginal portfolio contribution for sleeve-backed candidates | Partial | `validation.py`, sleeve replay path | Require portfolio Sharpe and Calmar improvement and no CDaR@95 worsening when evidence is required | Missing or failing evidence prevents `go` |
| 0A.8 | Memo answers before final run | No | Tier 0 report/memo | Add required input capture to report | Requires operator/user input before final run |
| 0B.1 | Event-clock contract and look-ahead enforcement | Partial | `sleeves/evaluation.py`, `backtest.py`, `runtime_portfolio.py`, `validation.py` | Enforce invariant: target-weight row for execution session `E` may depend only on bars/macros eligible through previous session `D`; it is filled at open `E` | Current sleeve context exposes current bar |
| 0B.2 | FRED VIXCLS and 2s10s PIT data wiring | Partial | `risk_free.py`, `runtime_portfolio.py`, `validation.py`, `drift/gateway.py`, `features/regime.py` | Add VIX cache/lookup, availability lag, staleness, regime wiring | FRED only; no threshold changes |
| 0B.3 | SMA(200) minimum history | Partial | `runtime_portfolio.py`, `validation.py`, `drift/gateway.py`, tests | Use `min_periods=200` equivalent and treat first 199 rows as insufficient | Shared calendar excludes warm-up for all |
| 0B.4 | DSR unit convention | Partial | `stats.py`, `evaluation.py`, `trials.py`, `validation.py` | Rename parameters, convert before DSR, preserve examples | DSR reported-only |
| 0B.5 | In-cycle kill switch and side-string fix | Partial | `service.py`, `controller.py`, `operator_control.py` | Re-read kill before order submit; block exposure increases on operator halt | Reductions allowed unless explicit kill stops all |
| 0B.6 | Session equity persistence if runtime continues | Partial | `service.py`, `controller.py`, `automation.py`, `persistence/__init__.py` | Restore true session-open equity after restart | Conditional on order submission continuing |
| 0B.7 | Minimal pre-trade enforcer if runtime continues | Partial | `risk.py`, `execution.py`, `controller.py`, `live_probe_governance.py`, `promotion.py` | Add notional/share/collar/rate/open-order rejects with reason codes | No broader pre-trade redesign |
| 0B.8 | Hard-halt runtime wiring if runtime continues | Partial | `portfolio/hard_halt.py`, `runtime_host.py`, `service.py`, `portfolio/blueprint.py` | Wire drawdown check to runtime host stop/alert/latch | No auto-flatten |
| 0B.9 | Reproducible benchmark evidence harness | Partial | `validation.py`, `benchmark_stack.py`, `backtest.py`, `costs.py`, `stats.py`, data manifest helpers | Build Tier 0A harness and tests for blocked states | Core sequential integration point |
| Tier 1 | Sleeve attribution fallback after `go` only | Partial | `drift/attribution.py`, `drift/sleeve_ledger.py` | Do not implement during Tier 0 | Out of scope before `go` |
| Tier 2/Tier 3 | Research and fidelity queues | No/Partial | Various | Do not implement | Explicitly forbidden during Tier 0 |

## 7. Current State vs Plan Intent

| Area | Current Repo Behavior | Plan-Required Behavior | Gap | Implementation Needed? | Risk If Wrong |
|---|---|---|---|---|---|
| event-clock/look-ahead enforcement | Backtest applies `target_weights.iloc[t]` at that row's open, while sleeve contexts include current bar through `position + 1` | For execution row/session `E`, `target_weights[E]` may depend only on bars and macro observations eligible through prior decision session `D`; no OHLCV or macro first available during/after `E` | Exact index invariant is currently unenforced | Yes | False evidence and invalid `go` |
| FRED VIX wiring | Classifier accepts VIX; runtime/validation pass `None`; drift VIX sample empty | FRED `VIXCLS` local CSV with PIT lag and stale-missing fail-closed wiring | Advertised VIX branches never fire | Yes | Cleaned system not actually advertised behavior |
| FRED 2s10s wiring | DGS2/DGS10 cache exists; runtime/validation pass `None` | `DGS10 - DGS2` bps with PIT lag and stale-missing fail-closed wiring | Yield inversion cannot affect regime | Yes | Stressed regime evidence is false |
| SMA(200) minimum history | Uses `rolling(200, min_periods=1)` | Require 200 eligible observations; first 199 excluded for all variants/baselines | Warm-up uses short SMA | Yes | Biased early-window decisions |
| DSR unit consistency | Annualized values pass into DSR path; expected max Sharpe mixes units | DSR boundary uses one explicit convention, preferred per-period | Reported DSR may be numerically invalid | Yes | Misleading reported-only statistic |
| benchmark evidence harness | Gate reports exist, not Tier 0A two-variant same-harness report | One accepted harness for As-Is, Cleaned, baselines, manifests, costs, calendar, uncertainty | Missing Tier 0A decision harness | Yes | Invalid comparison |
| cash benchmark | DGS3MO cache and cash hurdle exist | Include `cash_tbill_dgs3mo` as hard hurdle with manifests | Needs Tier 0 manifest/calendar integration | Yes | Cash hurdle could be inconsistent |
| monthly 60/40 SPY/AGG benchmark | Monthly blend exists | Hard comparator under same calendar/cost/data policies | Needs Tier 0 cost/data/evidence integration | Yes | Opportunity-cost edge could be invalid |
| drawdown/CDaR gates | Max drawdown/CDaR criteria exist | Hard Tier 0A operating constraint: MDD <=15%, CDaR@95 <=8% | Mostly present but must be included in Tier 0A decision mapping | Yes | Risk gate omitted or weakened |
| out-of-sample requirements | Gate 1 OOS criterion exists | >=756 OOS days and 30% denominator rule per active GATES-0001 | Needs Tier 0A exact evidence and blocker handling | Yes | Overfitted or insufficient evidence |
| PBO/CPCV readiness | PBO/CPCV machinery exists with pending/hard-gate behavior in validation paths | Tier 0A `go` must honor active GATES-0001 readiness and hard pass/fail rules | Tier 0A harness does not yet explicitly require it | Yes | `go` could bypass active Gate 1 |
| marginal portfolio contribution | Two-sleeve marginal contribution path exists in validation | Sleeve-backed candidates must improve portfolio Sharpe and Calmar and not worsen CDaR@95 when evidence is required | Tier 0A harness does not yet explicitly require it | Yes | `go` could ignore portfolio-level harm |
| uncertainty method | Stationary bootstrap and arithmetic paired HAC exist | Paired log-relative lower bound or paired stationary bootstrap with >=2,000 resamples | Existing hard path not geometric; bootstrap default 500 | Yes | Point estimate can masquerade as edge |
| stress-window coverage | No dedicated Tier 0 stress replay protocol found | Fixed COVID and 2022 windows plus rolling 63-day diagnostics using warm-up replay | Missing | Yes | `go` without crisis coverage |
| cost-stress requirements | Cost model and 1x/2x/4x style checks exist | Capital-scenario 1x/2x/4x active CAGR and lower-bound evidence versus 60/40 | Existing check only requires positive total return under stresses | Yes | Cost fragility hidden |
| capital-tier decision rule | Capital/capacity tools exist, but Tier 0A selected-tier mapping is absent | Evidence required for `paper_only`, `up_to_50k`, `50k_to_1m`, `above_1m`; selected tier and every predeclared plausible next-higher tier must pass | Selected/next-tier `go` rule missing | Yes | `go` for an infeasible capital trajectory |
| As-Is reproducibility | No preserved As-Is replay mechanism found | Pre-fix behavior replayed through accepted harness or controlled blocked state | Missing | Yes | Invalid As-Is vs Cleaned delta |
| paper/live-shadow safety controls | Basic risk and operator controls exist | If runtime continues: in-cycle kill, session equity restore, minimal pre-trade enforcer, hard halt wiring before order submission | Conditional missing/partial | Yes, conditional | Unsafe order submission during evaluation |
| hard-halt wiring if runtime continues | Controller exists; acceptance gates claim runtime enforcement; service integration not evident | On MDD breach call runtime host hard halt, stop service, alert, latch, no flatten | Missing integration | Yes, conditional | Drawdown breach may not stop runtime |

## 8. Clarification Questions Before Implementation

| Question | Related plan section | Related repo area | Why it matters | Coding decision depends on it | Risk if guessed | Blocks implementation |
|---|---|---|---|---|---|---|
| Will any paper/live-shadow order submission continue during the Tier 0A window, or will it be fully paused? | Tier 0B.5-0B.8, Execution Order step 2 | `service.py`, `controller.py`, `risk.py`, `portfolio/hard_halt.py`, `runtime_host.py`, `automation.py` | Determines whether safety prerequisites are Tier 0B-before-order-submit or deferred to Tier 1/post-`go` | Whether Wave 4 must be implemented before Tier 0A execution and before any further order submission | Guessing "paused" could allow unsafe orders; guessing "continues" could expand Tier 0B beyond required runtime scope | Yes, blocks conditional runtime-safety implementation and any order submission decision |
| What are the required memo inputs: 12-month capital trajectory, operator model, shorting policy, preference, and benchmark hurdle? | 0A.8 Decision Memo Required Answers | Tier 0A report/memo | These are required before the final benchmark run starts | Final report input schema and final run metadata | Final memo could be incomplete or use unapproved assumptions | No for harness coding; yes before final Tier 0A run |
| Is there a repository policy preference for preserving As-Is behavior by tag, branch, fixture, isolated worktree, or explicit adapter? | 0A.1, Tier 0B preamble, Execution Order step 1 | Git/worktree plus Tier 0 harness | Plan allows several mechanisms; repo may prefer one | Exact preservation artifact creation | Poor reproducibility or unwanted git refs | No; implementer may choose an allowed mechanism if not clarified |

## 9. Implementation Principles

- The source plan and active ADR/GATES policy control required behavior and scope; this implementation plan is an execution map.
- If this implementation plan is incomplete, ambiguous, or weaker than the source plan or active ADR/GATES policy, the stricter source-plan or active-policy requirement controls.
- The repo informs implementation location only.
- No new alpha, strategies, models, optimizers, allocators, or research bets.
- No hidden assumptions.
- No production approval from a passing backtest.
- Preserve existing behavior unless the plan explicitly changes it.
- Keep changes small and reviewable.
- Every task must map to a plan requirement and repo location.
- Every behavior change must have tests.
- If ambiguity appears during coding, stop and document it.
- Scientific, mathematical, statistical, or benchmark logic must not be guessed.

## 10. Parallelization Strategy

Parallel work can proceed only after Wave 0 preserves As-Is behavior or explicitly records a reproducibility blocker and completes the runtime order-submission preflight. If any paper/live-shadow order-submission path is active and Tier 0B.5-0B.8 safety controls are not already accepted, the orchestrator must either create a verified pause/disable artifact before any other wave continues or implement and accept Wave 4 first. Waves 1, 2, and 3 are the main parallel-safe measurement prerequisite waves because they own mostly distinct domains. Wave 4 is conditional runtime safety: if order submission is paused, Wave 4 may be deferred; if order submission continues, Wave 4 must complete before Waves 1-3 proceed. Wave 5 must be sequential because it integrates the accepted harness and scientific/statistical decision logic. Wave 6 must be last because it regenerates evidence and confirms one shared measurement method.

Waves that can run in parallel:

- Wave 1 Event-Clock and SMA Minimum History Core.
- Wave 2 FRED Macro PIT Wiring.
- Wave 3 DSR Unit Convention.
- Wave 4 Runtime Safety Prerequisites, only after the runtime preflight; if runtime order submission continues, this wave is blocking before Waves 1-3 and needs exclusive runtime-file ownership.

Waves that must be sequential:

- Wave 0 As-Is Preservation and Inputs, before measurement code edits.
- Wave 5 Benchmark Evidence Harness and Controlled Decision Logic, after Waves 1-3 and after Wave 4 if runtime continues.
- Wave 6 Integration, Full Regression, and Tier 0A Evidence Generation, after Wave 5.

Dependency and merge-conflict controls:

- `src/tradingx/validation.py` is a high-conflict file. Wave 1 may add event-clock/SMA hooks, Wave 3 may touch DSR reporting, and Wave 5 will integrate harness logic. Use a single integration owner for final `validation.py` merges.
- `src/tradingx/runtime_portfolio.py` is shared by Wave 1 and Wave 2; Wave 1 should own history/calendar semantics, Wave 2 should create macro lookup helpers, and integration into runtime snapshots should occur through a controlled handoff.
- `src/tradingx/stats.py` is shared by Wave 3 and Wave 5. Wave 3 owns DSR units; Wave 5 owns geometric Tier 0A uncertainty.
- `src/tradingx/service.py` and `src/tradingx/controller.py` must have exclusive ownership if Wave 4 runs.
- No two agents should modify the same core harness logic at the same time.

Safe for independent AI agents:

- Wave 2 is safe as an independent macro-data worker.
- Wave 3 is safe as an independent statistics-unit worker.
- Wave 1 is safe if it avoids Wave 2 macro wiring internals and documents integration points.
- Wave 4 is safe only as one exclusive runtime-safety worker.

If multiple AI agents/subagents are used:

- Each subagent must use ChatGPT 5.5 medium effort or higher.
- No subagent may use a weaker model.
- Each subagent must receive the source plan path, this implementation plan path, its assigned wave only, strict scope guardrails, and the required traceability rule.
- Each subagent must produce changed files summary, tests run, evidence generated, unresolved ambiguity list, and confirmation that no out-of-scope work was added.

Main orchestrator responsibilities:

- Assign non-overlapping waves where possible.
- Prevent two agents from editing the same files at the same time unless unavoidable.
- Review all subagent outputs before integration.
- Run full regression after merging parallel work.
- Reject any subagent work that adds untraceable behavior.
- Stop if agents disagree on scientific, statistical, or benchmark interpretation.

## 11. Work Breakdown: Parallel-Capable Waves

### Wave 0: As-Is Preservation and Tier 0 Inputs

Status:
- Sequential / first / requires orchestrator ownership

Goal:
Preserve replayable As-Is TradingX behavior before Tier 0B fixes and capture required Tier 0A run inputs.

Related plan sections:
- Definitions: As-Is TradingX
- 0A.1 Benchmarked Variants
- 0A.8 Decision Memo Required Answers
- Execution Order steps 1-2

Repo locations:
- Git/worktree state
- future Tier 0 harness metadata
- `docs/reports/`

Files likely to change:
- Implementation-time only: a preservation artifact, metadata file, or report reference chosen by the coding agent.
- No source files should change in this wave unless a replay adapter is chosen and explicitly traced.

Files that must not be changed:
- Source plan file.
- Strategy logic.
- Benchmark formulas.

Can run in parallel with:
- None.

Must run after:
- None.

Assigned agent profile:
- ChatGPT 5.5 medium effort or higher

Tasks:
- Preserve current executable behavior through one allowed immutable behavior artifact: branch/tag plus commit SHA and dirty executable diffs, sealed isolated worktree with hash, fixture bundle with content hash, or explicit behavior adapter with content hash.
- Record commit SHA, dirty-worktree status, preservation mechanism, artifact hash, and exact files/diffs included in the As-Is executable behavior definition.
- Define which pre-fix strategy/runtime decisions are preserved for same-harness replay after excluding legacy look-ahead-only metrics from decision evidence.
- Define the replay contract that the future accepted post-Tier-0B harness must use to invoke the As-Is artifact without using old measurement code.
- Run an immediate runtime order-submission preflight before any Wave 1-3 work starts: determine whether any paper/live-shadow service, scheduler, runtime PID, or order-submit path is currently active.
- If any order-submission path is active and Tier 0B.5-0B.8 safety controls are not already accepted, either pause/disable the service and scheduler and verify no runtime PID/order-submit path remains active, or route to Wave 4 first and accept the safety controls before Waves 1-3 proceed.
- If neither verified pause nor accepted safety controls can be produced, stop implementation and document `blocked_measurement_untrusted` risk rather than allowing unsafe evaluation work to proceed.
- Ask/record whether paper/live-shadow order submission is intended to continue during Tier 0A after the immediate preflight state is made safe.
- Ask/record capital trajectory, operator model, shorting policy, preference, and hurdle policy before final benchmark run.

Tests:
- A preservation validation that the As-Is artifact is addressable by immutable reference and includes all executable diffs or fixture/adapter hashes needed by the replay contract.
- A replay-contract validation that records the expected entrypoint, inputs, and preserved decision outputs without requiring the Wave 5 accepted harness to exist yet.
- A runtime preflight validation that records current service/scheduler/runtime PID/order-submit state and proves either verified pause/disable or accepted Tier 0 runtime safety before Waves 1-3 begin.

Validation evidence:
- Preservation artifact reference and content hash.
- Commit SHA, dirty-worktree status, and included executable diffs or sealed worktree/fixture hash.
- Preserved-behavior note that identifies pre-fix decisions retained and legacy look-ahead-only evidence excluded.
- Replay-contract note consumed by Wave 5/6 same-harness replay proof.
- Runtime preflight artifact with pause/disable evidence or accepted safety-control evidence before any non-runtime wave starts.
- Captured Tier 0A input answers or blocker notes.

Scientific/statistical review needed:
- No.

Risks:
- If skipped, final decision may become `blocked_as_is_unreproducible`.

Dependencies:
- None.

Merge-conflict risk:
- Low if no source changes.

Exit criteria:
- As-Is immutable behavior artifact and replay contract exist, or the artifact cannot be preserved and `blocked_as_is_unreproducible` is documented.
- Same-harness replay proof is explicitly deferred to Wave 5/6 after the accepted harness exists.
- Runtime order-submission preflight is complete: either order submission is verified paused/disabled, or Wave 4 safety controls are accepted before order submission continues.
- Runtime continuation decision is documented after the preflight state is safe, or Wave 4 remains blocked and Waves 1-3 do not proceed.

### Wave 1: Event-Clock and SMA Minimum History Core

Status:
- Parallel-safe after Wave 0 / controlled integration with Wave 2 and Wave 5

Goal:
Enforce daily-bar event-clock behavior and SMA(200) minimum-history semantics without adding strategy behavior.

Related plan sections:
- 0B.1 Event-Clock Contract And Look-Ahead Enforcement
- 0B.3 SMA(200) Minimum History Fix
- 0A.3 shared evaluation calendar warm-up rule

Repo locations:
- `src/tradingx/sleeves/evaluation.py`
- `src/tradingx/backtest.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/validation.py`
- `src/tradingx/drift/gateway.py`
- tests under `tests/unit/` and `tests/integration/`

Files likely to change:
- `src/tradingx/sleeves/evaluation.py`
- `src/tradingx/backtest.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/validation.py`
- `src/tradingx/drift/gateway.py`
- `tests/unit/test_backtest.py`
- `tests/unit/test_runtime_portfolio.py`
- `tests/unit/test_validation.py`
- `tests/integration/test_sleeves_end_to_end.py`

Files that must not be changed:
- Strategy sleeve alpha logic.
- Classifier thresholds.
- Source plan.

Can run in parallel with:
- Wave 2, Wave 3, and conditional Wave 4.

Must run after:
- Wave 0.

Assigned agent profile:
- ChatGPT 5.5 medium effort or higher

Tasks:
- Name the event-clock contract and the exact index invariant in code/doc comment.
- Enforce this invariant: for execution session/index `E`, `target_weights.loc[E]` is filled at `open[E]` and may depend only on bars whose timestamps are strictly before `E` plus macro observations eligible as of the prior decision session `D`; it must not depend on `close/high/low/volume/open/fill` from `E`.
- Ensure sleeve decisions cannot inspect execution-session close/high/low/volume/open/fill data through `SleeveContext.bars_by_symbol` or any equivalent runtime/validation context.
- Preserve next-session execution semantics by shifting decisions or target-weight rows as needed; do not reinterpret same-row target weights as close-to-close decisions.
- Replace `min_periods=1` SMA(200) behavior with minimum 200 eligible observations.
- Ensure insufficient SMA history yields no valid cleaned regime decision and is available to shared-calendar logic.
- Enforce the executable-row warm-up boundary: the first executable target row `E` must have at least 200 prior eligible observations available at decision session `D`, not merely 200 rows including `E`.

Tests:
- Perturb execution-session close and assert current decision is unchanged.
- Perturb execution-session open/high/low/volume and assert the decision for that same execution row is unchanged when those fields are unavailable at decision time.
- Verify first eligible trade occurs only after enough prior data.
- Verify `SleeveContext.bars_by_symbol` does not expose execution-session close.
- Verify `target_weights[E]` depends on data through `D` and is applied at `open[E]`.
- Cover 199-row, 200-row, and first-executable-row SMA boundaries, including the off-by-one case where row `E` would be the 200th observation but is not yet eligible because the decision at `D` has only 199 prior observations.

Validation evidence:
- Failing-before/passing-after style tests.
- Event-clock contract comment/doc section.

Scientific/statistical review needed:
- Yes, for event-clock and warm-up semantics.

Risks:
- A partial fix could silently change same-session behavior or preserve look-ahead leakage.

Dependencies:
- Wave 0.

Merge-conflict risk:
- Medium/high in `validation.py` and `runtime_portfolio.py`.

Exit criteria:
- Event-clock tests pass.
- SMA warm-up behavior is explicit and test-covered.

### Wave 2: FRED Macro PIT Wiring

Status:
- Parallel-safe after Wave 0 / controlled runtime-validation integration

Goal:
Wire existing regime classifier VIX and 2s10s inputs using FRED-only local CSV caches and conservative PIT availability rules.

Related plan sections:
- 0B.2 VIX/2s10s PIT Data Wiring
- 0A.3 macro availability shared-calendar rules

Repo locations:
- `src/tradingx/features/regime.py`
- `src/tradingx/risk_free.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/validation.py`
- `src/tradingx/drift/gateway.py`
- `tests/unit/test_regime.py`
- `tests/unit/test_risk_free.py`

Files likely to change:
- `src/tradingx/risk_free.py` or a narrowly named FRED macro helper.
- `src/tradingx/drift/gateway.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/validation.py`
- `tests/unit/test_risk_free.py`
- `tests/unit/test_regime.py`
- runtime/validation tests for macro-backed snapshots.

Files that must not be changed:
- Classifier thresholds.
- Strategy logic.
- Vendor selection beyond FRED.

Can run in parallel with:
- Wave 1 and Wave 3 if integration touchpoints are coordinated.

Must run after:
- Wave 0.

Assigned agent profile:
- ChatGPT 5.5 medium effort or higher

Tasks:
- Add/extend local CSV cache support for FRED `VIXCLS`.
- Reuse existing DGS2/DGS10 spread where possible.
- Implement PIT lookup with one-business-day availability lag unless a stored release timestamp proves earlier availability.
- Treat macro observations older than five NYSE trading sessions as missing.
- Wire macro values into runtime and validation regime snapshots.
- Update drift `vix_level` sample reader.

Tests:
- Historical replay produces `risk_off` from VIX > 25.
- Historical replay produces `stressed` from VIX >= 35.
- 2s10s inversion contributes to `stressed` exactly as `classify_regime` defines.
- Missing/stale macro values fail closed for shared evaluation.

Validation evidence:
- FRED `VIXCLS`, `DGS2`, and `DGS10` coverage reported by Tier 0A harness.
- Unit tests for lag and staleness.

Scientific/statistical review needed:
- Yes, for PIT availability lag and stale-missing behavior.

Risks:
- Observation-date look-ahead leakage.
- Accidental vendor expansion.

Dependencies:
- Wave 0.

Merge-conflict risk:
- Medium in `runtime_portfolio.py` and `validation.py`.

Exit criteria:
- Regime snapshots use actual FRED macro inputs under the required lag rule.
- Missing macro handling is explicit and tested.

### Wave 3: DSR Unit Convention

Status:
- Parallel-safe after Wave 0 / avoid concurrent `stats.py` edits with Wave 5

Goal:
Make DSR input units explicit and internally consistent while preserving reported-only status for Tier 0.

Related plan sections:
- 0B.4 DSR Unit Convention
- 0A.7 DSR reported-only rule

Repo locations:
- `src/tradingx/stats.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/trials.py`
- `src/tradingx/validation.py`
- `tests/unit/test_stats.py`
- `tests/unit/test_evaluation.py`
- `tests/unit/test_trials.py`

Files likely to change:
- `src/tradingx/stats.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/trials.py`
- `tests/unit/test_stats.py`
- `tests/unit/test_evaluation.py`
- `tests/unit/test_trials.py`

Files that must not be changed:
- DSR worked-example expected semantics except for explicit unit naming.
- PBO/CPCV redesign areas.

Can run in parallel with:
- Wave 1 and Wave 2.

Must run after:
- Wave 0.

Assigned agent profile:
- ChatGPT 5.5 medium effort or higher

Tasks:
- Rename DSR helper parameters to unit-bearing names.
- Make the DSR boundary mechanically unit-aware: either introduce a small unit-bearing value type/dataclass for per-period Sharpe inputs, or make DSR helpers private and force all callers through explicit conversion helpers whose names include annualized-to-per-period semantics.
- Convert annualized Sharpe to per-period before DSR helper boundaries if using preferred convention.
- Forbid direct evaluation/trials calls that pass raw annualized float Sharpe values into the per-period DSR boundary.
- Ensure trial mean, variance, observed Sharpe, and benchmark Sharpe are same units at DSR boundary.
- Ensure Tier 0A reports DSR, if present, as `reported_only`.

Tests:
- Existing Bailey/Lopez de Prado worked examples still pass.
- Regression tests with known annualized-vs-per-period Sharpe values prove the conversion changes the DSR result in the expected direction and prevents the old annualized-input path.
- New tests fail if evaluation/trials bypass the unit-bearing boundary or explicit conversion helper.
- Evaluation/trials tests assert explicit conversion.

Validation evidence:
- Unit test output.
- Short note in Tier 0B implementation report.

Scientific/statistical review needed:
- Yes.

Risks:
- Silently changing DSR value without preserving formula intent.

Dependencies:
- Wave 0.

Merge-conflict risk:
- Medium in `stats.py`; low elsewhere.

Exit criteria:
- No DSR helper adds annualized and per-period quantities.
- DSR remains reported-only.

### Wave 4: Runtime Safety Prerequisites If Order Submission Continues

Status:
- Conditional / Parallel-safe only with exclusive runtime ownership / blocked until Clarification Q1 is answered

Goal:
If paper/live-shadow order submission continues during Tier 0A, accept the required runtime safety prerequisites before any further order submission.

Related plan sections:
- 0B.5 Operator Kill-Switch In-Cycle And Side-String Fix
- 0B.6 Session Equity Persistence
- 0B.7 Minimal Pre-Trade Enforcer Safety Prerequisite
- 0B.8 Portfolio Hard Halt Runtime Wiring Safety Prerequisite
- 0A.7 hard-halt policy

Repo locations:
- `src/tradingx/service.py`
- `src/tradingx/controller.py`
- `src/tradingx/operator_control.py`
- `src/tradingx/risk.py`
- `src/tradingx/execution.py`
- `src/tradingx/live_probe_governance.py`
- `src/tradingx/promotion.py`
- `src/tradingx/automation.py`
- `src/tradingx/persistence/__init__.py`
- `src/tradingx/portfolio/hard_halt.py`
- `src/tradingx/runtime_host.py`
- `src/tradingx/portfolio/blueprint.py`

Files likely to change:
- `src/tradingx/service.py`
- `src/tradingx/controller.py`
- `src/tradingx/risk.py`
- `src/tradingx/portfolio/hard_halt.py`
- `tests/unit/test_service.py`
- `tests/unit/test_controller.py`
- `tests/unit/test_risk.py`
- `tests/unit/test_portfolio_hard_halt.py`

Files that must not be changed:
- Telegram/HMAC/two-approver/supervisor redesign.
- Shorts/margin/locate expansion.
- Auto-flatten paths.

Can run in parallel with:
- Waves 1-3 only if one agent owns all runtime files above.

Must run after:
- Wave 0 and answered Clarification Q1.

Assigned agent profile:
- ChatGPT 5.5 medium effort or higher

Tasks:
- Re-read `kill_requested` after cycle start and before broker submit; block all order submission on explicit kill.
- Change operator halt from side-string buy check to exposure-increase check; allow reductions unless explicit kill stops all orders.
- Persist/restore true session-open equity for daily PnL/drawdown after restart.
- Add minimal pre-trade checks: notional limit, share limit, price collar, order rate per minute, max open orders.
- Wire portfolio hard halt to service/runtime host stop/alert/latch without flattening.
- If runtime order submission is paused instead, create an explicit pause/disable artifact and do not implement this wave: stop or disable the paper/live-shadow service and scheduler, verify no runtime PID or order-submit path is active, record the pause window and verification command/output summary, and state in the Tier 0A memo that runtime safety work is deferred to Tier 1/post-`go`.
- If order submission continues during Tier 0A without accepted safety prerequisites or a verified pause artifact, Tier 0A must return `blocked_measurement_untrusted`.

Tests:
- In-cycle kill set after cycle start blocks before submit.
- Operator halt blocks exposure increases, not only `buy`, and allows exposure reductions unless kill.
- Restart restores session-open equity.
- Notional/share/collar/rate/open-order rejections occur before broker submit with structured reason codes.
- Synthetic hard-halt breach stops runtime host, sends critical alert, latches, and does not flatten.
- If runtime is paused, pause verification proves the service/scheduler/order-submit path is inactive for the Tier 0A window.

Validation evidence:
- Runtime safety test suite.
- Tier 0B report section with either accepted runtime safety tests or a pause/disable artifact including pause window, disabled service/scheduler state, runtime PID/order-submit verification, and commands used.

Scientific/statistical review needed:
- No, but safety review required.

Risks:
- Unsafe order path if incomplete.
- Scope creep into broader pre-trade controls.

Dependencies:
- Clarification Q1.

Merge-conflict risk:
- High in `service.py` and `controller.py`; requires exclusive ownership.

Exit criteria:
- Either runtime order submission is paused with a verified pause artifact, or all required safety controls are implemented and accepted before order submission.

### Wave 5: Benchmark Evidence Harness and Controlled Decision Logic

Status:
- Sequential / Depends on Waves 1-3 and Wave 4 if runtime continues / requires core harness ownership

Goal:
Build the accepted Tier 0A evidence harness that compares As-Is, Cleaned, and baselines under one measurement method and emits controlled decisions.

Related plan sections:
- 0A.1 through 0A.8
- 0B.9 Benchmark Evidence Harness
- Final Decision Logic
- Required Artifact Names

Repo locations:
- `src/tradingx/validation.py`
- `src/tradingx/benchmark_stack.py`
- `src/tradingx/backtest.py`
- `src/tradingx/costs.py`
- `src/tradingx/stats.py`
- `src/tradingx/__main__.py`
- data manifest/fingerprint helpers
- `docs/reports/`

Files likely to change:
- Existing harness modules above and/or a new narrowly scoped Tier 0 module under `src/tradingx/`.
- Tests under `tests/unit/test_validation.py`, `tests/unit/test_benchmark_stack.py`, `tests/unit/test_stats.py`, `tests/unit/test_main.py`, plus integration tests.

Files that must not be changed:
- Strategy logic.
- Source plan.
- Tier 1/Tier 2/Tier 3 modules except as read-only context.

Can run in parallel with:
- None.

Must run after:
- Waves 1-3.
- Wave 4 if order submission continues.
- Wave 0 As-Is preservation.

Assigned agent profile:
- ChatGPT 5.5 medium effort or higher

Tasks:
- Implement two-variant same-harness orchestration for As-Is and Cleaned.
- Enforce same data manifests, cost model, shared calendar, uncertainty method, and benchmark stack.
- Materialize hard baselines and diagnostic baselines with labels. The hard `monthly_60_40_spy_agg` comparator must rebalance by producing a target for execution session `E` from information eligible through the prior decision session `D` and filling at `open[E]` or an explicitly documented next-session equivalent; close-to-close or same-session rebalance accounting cannot satisfy the hard comparator. Diagnostic baselines must also respect event-clock timing, including the VIX/GLD overlay's prior-available `VIXCLS` threshold and next-session target timing.
- Add horizon/common-window resolver and blocked decisions.
- Split metrics into mandatory decision-hurdle metrics and non-hurdle report metrics before implementation. Mandatory hurdle metrics must be produced or the decision must be blocked; non-hurdle report metrics may use existing code paths and may be marked `not_available_existing_path` as the source plan allows. Do not build a broad analytics framework solely to fill non-hurdle optional metrics.
- Add active GATES-0001 PBO/CPCV readiness handling: before readiness clears, PBO may be reported only as `pending` exactly as GATES-0001 allows; once a PBO payload exists for the Gate 1 run, PBO is hard pass/fail and failure blocks `go`; if readiness requires PBO and evidence is missing, decision is `blocked_measurement_untrusted`.
- Add marginal portfolio contribution enforcement for sleeve-backed candidates whenever active GATES-0001 requires it: adding the candidate to the mandatory sleeve-backed reference book must strictly improve portfolio Sharpe and Calmar and must not worsen portfolio CDaR@95; missing or failing evidence blocks `go`.
- Use the source-plan-allowed stationary block bootstrap as the default hard-hurdle uncertainty method unless a separate explicit CIO/scientific approval note authorizes a different paired log-relative confidence estimator before coding. For shared daily returns `r_s[i]` and `r_b[i]`, compute paired log-relative rows `x[i] = log1p(r_s[i]) - log1p(r_b[i])`; resample paired daily return rows, compute log-relative terminal wealth and annualized log-relative growth per resample, and require the 5th percentile lower bound used for the decision to be greater than zero.
- Predeclare and record the stationary-bootstrap block-length rule, random seed, resample count, confidence percentile, and paired-row resampling policy. Use at least 2,000 resamples. If no predeclared scientifically approved block-length rule exists, mark the uncertainty hurdle unavailable and return `blocked_measurement_untrusted` rather than guessing.
- Do not implement a Newey-West/HAC hard-hurdle path unless the explicit approval note names the estimator, lag rule, kernel, finite-sample behavior, and fallback policy. Arithmetic active-return HAC remains diagnostic only and cannot satisfy the Tier 0A hard uncertainty hurdle.
- Treat missing, non-finite, or return values below `-1` as `blocked_measurement_untrusted`; treat an exact `-1` return as a total-loss observation that makes the geometric lower-bound hurdle fail rather than silently dropping the row. Zero returns are valid and use `log1p(0) = 0`.
- Add capital scenarios for all four required tiers: `paper_only`, `up_to_50k`, `50k_to_1m`, and `above_1m`.
- Add selected-tier and plausible-next-tier decision mapping: the memo must predeclare the selected 12-month capital tier and which higher tiers are plausible before the run; the selected tier and every predeclared plausible next-higher tier must pass cost/capacity and 1x/2x/4x lower-bound evidence, or Tier 0A cannot issue `go`.
- Add 1x/2x/4x cost-stress lower-bound evidence for each decision-relevant capital scenario.
- Add fixed stress-window replay protocol and rolling 63-day diagnostics.
- Add manifest evidence requirements for return accounting and executable/cost data.
- Emit controlled decisions only from the source-plan mapping.
- Emit required artifacts: `docs/reports/tradingx_tier0a_benchmark_decision_report.md`, `docs/reports/tradingx_tier0a_benchmark_metrics.json`, and `docs/reports/tradingx_tier0b_measurement_safety_report.md`.

Tests:
- Fixture beating 60/40 by less than 2% cannot produce `go`.
- Hard `monthly_60_40_spy_agg` fixture proves monthly rebalance targets are generated from prior eligible information and filled next session; a close-to-close or same-session rebalance implementation fails.
- Diagnostic VIX/GLD overlay fixture proves prior-available `VIXCLS`, fixed threshold 25, and next-session target timing.
- Non-hurdle report metric unavailable via existing code path is recorded as `not_available_existing_path`; missing decision-hurdle metric still blocks.
- Fixture with PBO readiness cleared and missing PBO payload produces `blocked_measurement_untrusted`.
- Fixture with PBO payload above the active threshold cannot produce `go`.
- Fixture where marginal portfolio contribution worsens CDaR@95, or fails to improve Sharpe/Calmar, cannot produce `go`.
- Positive point active CAGR with non-positive geometric lower bound cannot produce `go`.
- Geometric uncertainty fixture asserts the exact `log1p` paired-return conversion, stationary-bootstrap paired-row resampling, seed/block-length/resample/percentile metadata, lower-bound relative terminal wealth, and annualized log-relative growth formula.
- HAC/Newey-West cannot be used as the hard-hurdle uncertainty method without explicit statistical approval evidence.
- Missing, non-finite, below-`-1`, and exact-`-1` return fixtures produce the required blocked or non-`go` outcome.
- Missing adjusted-price/cache-hash evidence cannot produce `go`.
- Missing raw executable-price/volume evidence without reversible model cannot produce `go`.
- Selected capital tier passing but predeclared plausible next-higher tier failing cost/capacity evidence cannot produce `go`.
- 1x pass but 4x lower-bound failure cannot produce `go`.
- Rolling-only stress coverage produces `blocked_stress_coverage_missing`.
- COVID stress-window fixture proves fixed-window diagnostics can be replayed from predeclared warm-up even when COVID sits outside the default five-year decision horizon.
- Missing required symbol, macro, risk-free, cost input, or manifest hash inside a locally covered fixed stress window produces `blocked_stress_coverage_missing`.
- Stress-window warm-up fixture proves initial state is not seeded from future information.
- Different As-Is harness metrics cannot produce `go`.

Validation evidence:
- Generated fixture reports and JSON metrics.
- Command list and manifest references.

Scientific/statistical review needed:
- Yes, mandatory.

Risks:
- Mixing old and new measurement logic.
- Reimplementing broad analytics beyond required Tier 0 metrics.

Dependencies:
- Waves 0-3; Wave 4 if runtime continues.

Merge-conflict risk:
- High in `validation.py`, `stats.py`, `benchmark_stack.py`.

Exit criteria:
- Harness can produce one allowed decision or a correct blocked state with evidence.

### Wave 6: Integration, Regression, and Tier 0A Evidence Generation

Status:
- Sequential / final integration owner

Goal:
Merge parallel outputs, run full regression, regenerate Tier 0 evidence, and prepare for adversarial review.

Related plan sections:
- Execution Order steps 4-7
- Required Artifact Names
- Adversarial Review Checklist
- Final Decision Logic

Repo locations:
- Entire Tier 0 touched surface.
- `docs/reports/`

Files likely to change:
- Reports only, plus final integration fixes traceable to prior waves.

Files that must not be changed:
- Source plan.
- Out-of-scope strategy/research code.

Can run in parallel with:
- None.

Must run after:
- Wave 5.

Assigned agent profile:
- ChatGPT 5.5 medium effort or higher

Tasks:
- Review all wave outputs for traceability.
- Resolve conflicts without weakening scientific logic.
- Run full regression command sequence.
- Regenerate As-Is, Cleaned, benchmarks, manifests, costs, uncertainty, and stress evidence.
- Confirm one shared harness/cost/model/calendar/uncertainty stack.
- Produce final Tier 0A decision memo and metrics JSON.

Tests:
- Full targeted Tier 0 suite.
- Full project regression if feasible.

Validation evidence:
- Test logs.
- Generated reports.
- Metrics JSON.
- Traceability checklist.

Scientific/statistical review needed:
- Yes, mandatory before accepting `go`.

Risks:
- Integration accidentally diverges variant measurement paths.

Dependencies:
- All prior required waves.

Merge-conflict risk:
- Medium/high.

Exit criteria:
- Evidence package is ready for adversarial technical/scientific review.
- Final decision is exactly one allowed value.

## 12. Integration Plan After Parallel Work

Merge order:

1. Wave 0 preservation metadata.
2. Wave 1 event-clock/SMA core.
3. Wave 2 FRED macro helpers.
4. Wave 3 DSR units.
5. Wave 4 runtime safety if it is required for continued order submission.
6. Wave 5 benchmark evidence harness.
7. Wave 6 reports/evidence.

Conflict-resolution rules:

- The stricter source-plan behavior wins over current repo behavior.
- Do not resolve statistical, event-clock, or benchmark conflicts by assumption.
- If Wave 1 and Wave 2 conflict in `runtime_portfolio.py` or `validation.py`, preserve Wave 1 event-clock/SMA semantics and integrate Wave 2 macro inputs through the same eligible-date interface.
- If Wave 3 and Wave 5 conflict in `stats.py`, preserve Wave 3 DSR unit convention and add Wave 5 geometric uncertainty as separate Tier 0A decision logic.
- Reject any change that alters classifier thresholds, adds alpha, changes strategy parameters, or substitutes diagnostic baselines for hard baselines.

Full test command sequence:

- `uv run pytest tests/unit/test_regime.py tests/unit/test_risk_free.py tests/unit/test_backtest.py tests/unit/test_runtime_portfolio.py tests/unit/test_validation.py tests/unit/test_benchmark_stack.py tests/unit/test_stats.py tests/unit/test_evaluation.py tests/unit/test_trials.py`
- If Wave 4 runs: `uv run pytest tests/unit/test_service.py tests/unit/test_controller.py tests/unit/test_risk.py tests/unit/test_portfolio_hard_halt.py`
- CLI coverage: `uv run pytest tests/unit/test_main.py tests/integration/test_gate_validation_pipeline.py`
- Final regression: `uv run pytest`
- Repository gate: `./scripts/validate`
- If `./scripts/validate` cannot be run because of documented local environment limits, the Tier 0B/Tier 0A report must list the skipped gate steps, the exact reason for each skip, and the narrower commands run instead. A `go` decision must not rely on undocumented validation skips.

Evidence regeneration steps:

- Refresh or verify local FRED DGS3MO, DGS2, DGS10, and VIXCLS caches.
- Build data manifests with source, adjustment policy, corporate-action policy, retrieval timestamp, coverage window, and content hashes.
- Materialize shared evaluation calendar after all required inputs and SMA warm-up eligibility.
- Run As-Is replay through accepted harness.
- Run Cleaned Advertised replay through accepted harness.
- Run cash and monthly 60/40 SPY/AGG through same calendar and data policy.
- Run diagnostics without allowing them to replace hard benchmarks.
- Run capital scenarios and 1x/2x/4x cost stress.
- Run fixed stress windows from predeclared warm-up periods and rolling 63-day diagnostics.
- Generate `docs/reports/tradingx_tier0a_benchmark_metrics.json`.
- Generate `docs/reports/tradingx_tier0a_benchmark_decision_report.md`.

How to compare As-Is vs Cleaned:

- Both variants must use the same accepted post-Tier-0B harness.
- As-Is preserves pre-fix strategy/runtime decisions where measurable without violating the event-clock contract.
- Legacy look-ahead-only metrics are diagnostic only.
- If As-Is cannot be replayed through the accepted harness, final decision is `blocked_as_is_unreproducible`.

Consistency confirmation:

- Assert one shared data manifest set.
- Assert one shared cost model per capital scenario.
- Assert one shared evaluation calendar.
- Assert one uncertainty method for hard lower-bound evidence.
- Assert same benchmark stack labels and returns.
- Assert identical decision-hurdle metric formulas across variants and baselines.

## 13. Data / Schema / API Changes

Changes explicitly required by the source plan:

- Data artifact changes: add or extend local FRED macro cache support for `VIXCLS`; reuse DGS2/DGS10 for `spread_2s10s_bps`; add/record source name, pull timestamp, observation date, availability policy, coverage window, and content hashes for Tier 0A decision-critical series.
- Report artifact changes: generate `docs/reports/tradingx_tier0a_benchmark_decision_report.md`, `docs/reports/tradingx_tier0a_benchmark_metrics.json`, and `docs/reports/tradingx_tier0b_measurement_safety_report.md`.
- Harness/report schema changes: only as needed to represent the source-plan-required controlled decision, capital scenarios, stress-window coverage, manifests, cost stresses, and uncertainty evidence.

No production API changes are explicitly required by the source plan. No database schema change is explicitly required; use existing file artifacts/persistence where possible unless implementation proves a bounded artifact-schema addition is necessary for a source-plan requirement.

## 14. Test Plan

| Test Area | Plan Requirement | Repo Location | Test Type | Required Evidence |
|---|---|---|---|---|
| Event-clock index invariant | 0B.1 target row `E` filled at open `E` depends only on data through prior decision session `D` | `tests/unit/test_backtest.py`, `tests/unit/test_validation.py`, `tests/integration/test_sleeves_end_to_end.py` | Unit/integration/negative | Perturb execution-row open/high/low/close/volume; decision/target row for `E` unchanged |
| Sleeve context data visibility | 0B.1 no sleeve can access execution-session OHLCV/fill data | `tests/unit/test_validation.py`, `tests/integration/test_sleeves_end_to_end.py` | Negative | `SleeveContext.bars_by_symbol` excludes execution-session bar for target row `E` |
| First eligible trade | 0B.1 and 0B.3 enough prior data | `tests/unit/test_runtime_portfolio.py`, `tests/unit/test_validation.py` | Edge-case | First executable target row has at least 200 prior eligible observations available at prior decision session `D` |
| SMA executable-row boundary | 0B.3 SMA(200) minimum history | `tests/unit/test_validation.py`, `tests/unit/test_runtime_portfolio.py`, `tests/unit/test_risk_free.py` | Unit/edge-case | 199 prior rows invalid; 200 prior rows valid; row `E` cannot count itself toward the 200 prior observations needed for a fill at `open[E]` |
| FRED VIX risk_off/stressed | 0B.2 VIXCLS wiring | `tests/unit/test_regime.py`, `tests/unit/test_risk_free.py`, runtime/validation tests | Unit/integration | VIX >25 risk_off; VIX >=35 stressed |
| FRED 2s10s inversion | 0B.2 spread wiring | `tests/unit/test_risk_free.py`, validation/runtime tests | Unit/integration | Inversion contributes to stressed per classifier |
| Macro PIT lag/stale missing | 0B.2 one-business-day lag and five-session staleness | Macro helper tests | Negative/edge-case | Observation too new or stale blocks/missing |
| DSR units | 0B.4 consistent per-period convention | `tests/unit/test_stats.py`, `tests/unit/test_evaluation.py`, `tests/unit/test_trials.py` | Unit/negative | Unit-bearing boundary or explicit conversion helper prevents annualized raw-float bypass; worked examples pass |
| Cash benchmark | 0A.2 hard cash hurdle | `tests/unit/test_benchmark_stack.py`, Tier 0 harness tests | Unit/integration | DGS3MO returns included and aligned |
| Monthly 60/40 | 0A.2 active opportunity cost | `tests/unit/test_benchmark_stack.py`, Tier 0 harness tests | Unit/integration | Monthly rebalance, SPY/AGG weights, shared calendar, and next-session execution under the event-clock contract; close-to-close or same-session rebalance accounting fails |
| Diagnostic VIX/GLD overlay | 0A.2 diagnostic baseline only | Tier 0 harness tests | Unit/integration | Uses prior-available `VIXCLS`, fixed threshold 25, and next-session target timing; remains diagnostic-only |
| Drawdown/CDaR gates | 0A.7 operating constraint | `tests/unit/test_validation.py`, Tier 0 harness tests | Unit | MDD >15 or CDaR >8 blocks `go` |
| OOS profile | 0A.7 >=756 OOS and 30% rule | `tests/unit/test_validation.py` | Unit/edge-case | Insufficient/failing OOS blocks `go` |
| PBO/CPCV readiness | 0A.7 and active GATES-0001 | `tests/unit/test_validation.py`, PBO/CPCV tests, Tier 0 harness tests | Unit/negative | Readiness-cleared missing PBO blocks; PBO failure blocks `go`; pre-readiness pending does not become pass |
| Marginal portfolio contribution | 0A.7 and active GATES-0001 | `tests/unit/test_validation.py`, Tier 0 harness tests | Unit/negative | Failure to improve Sharpe/Calmar or CDaR worsening blocks `go` |
| Metric availability split | 0A.5 mandatory hurdle vs non-hurdle metrics | Tier 0 harness tests | Unit/negative | Non-hurdle metric unavailable via existing path is `not_available_existing_path`; missing decision-hurdle metric blocks |
| Geometric uncertainty | 0A.6/0A.7 lower 95% bound | `tests/unit/test_stats.py`, Tier 0 harness tests | Unit/negative | Exact `log1p` formula, stationary-bootstrap paired-row resampling, seed/block/resample/percentile metadata, and lower-bound conversion tested; positive point CAGR with non-positive lower bound cannot `go`; HAC hard-hurdle path requires explicit approval evidence |
| Cost stress | 0A.4/0A.7 1x/2x/4x by capital scenario | `tests/unit/test_evaluation.py`, Tier 0 harness tests | Unit/negative | 4x lower-bound failure cannot `go` |
| Capital-tier rule | 0A.4 selected and plausible next-higher capital scenarios | Tier 0 harness tests | Unit/negative | Selected tier and every predeclared plausible next-higher tier must pass or `go` is impossible |
| Stress coverage | 0A.3 fixed stress windows | Tier 0 harness tests | Integration/negative | Rolling-only coverage returns `blocked_stress_coverage_missing`; COVID can be replayed from predeclared warm-up even outside the default five-year horizon; missing covered-window data/manifests block; warm-up state is not seeded from future information |
| Data manifests | 0A.4 manifests and hashes | Tier 0 harness tests | Negative/reproducibility | Missing adjusted/raw/hash evidence cannot `go` |
| As-Is reproducibility | 0A.1 same harness replay | Tier 0 harness tests | Reproducibility/negative | Immutable As-Is artifact hash is replayed by accepted harness; different harness or missing replay returns blocked state |
| In-cycle kill | 0B.5 safety if runtime continues | `tests/unit/test_service.py`, `tests/unit/test_controller.py` | Unit/negative | Kill after cycle start blocks before submit |
| Exposure-aware halt | 0B.5 side-string fix | `tests/unit/test_controller.py` | Unit/edge-case | Halt blocks exposure increase; reduction allowed unless kill |
| Session equity restore | 0B.6 if runtime continues | `tests/unit/test_service.py`, automation/persistence tests | Unit/integration | Restart restores true session-open equity |
| Minimal pre-trade enforcer | 0B.7 if runtime continues | `tests/unit/test_risk.py`, `tests/unit/test_controller.py` | Unit/negative | Notional/share/collar/rate/open-order rejects before broker submit |
| Hard halt runtime wiring | 0B.8 if runtime continues | `tests/unit/test_portfolio_hard_halt.py`, `tests/unit/test_service.py` | Unit/integration | Breach stops host, alerts, latches, no flatten |

## 15. Validation Plan

Commands to run:

- `uv run pytest tests/unit/test_regime.py tests/unit/test_risk_free.py tests/unit/test_backtest.py tests/unit/test_runtime_portfolio.py tests/unit/test_validation.py tests/unit/test_benchmark_stack.py tests/unit/test_stats.py tests/unit/test_evaluation.py tests/unit/test_trials.py`
- If runtime safety is required: `uv run pytest tests/unit/test_service.py tests/unit/test_controller.py tests/unit/test_risk.py tests/unit/test_portfolio_hard_halt.py`
- `uv run pytest tests/unit/test_main.py tests/integration/test_gate_validation_pipeline.py tests/integration/test_sleeves_end_to_end.py`
- `uv run pytest`
- `./scripts/validate`
- Tier 0A harness command to be added by Wave 5 or documented as the accepted invocation.
- Any skipped `./scripts/validate` step must be documented with exact reason and replacement evidence.

Expected outputs:

- Passing targeted and regression tests.
- Passing `./scripts/validate`, or explicit documented skips with replacement evidence.
- Tier 0B implementation/safety report.
- Tier 0A metrics JSON.
- Tier 0A benchmark decision report.
- Manifest files or linked manifest evidence with content hashes.

Generated reports:

- `docs/reports/tradingx_tier0b_measurement_safety_report.md`
- `docs/reports/tradingx_tier0a_benchmark_metrics.json`
- `docs/reports/tradingx_tier0a_benchmark_decision_report.md`

Generated evidence files:

- Data manifest(s) for return-accounting series.
- Data manifest(s) for executable-price/cost series.
- Macro cache coverage evidence for VIXCLS, DGS2, DGS10.
- Cost model/capital scenario evidence.
- PBO/CPCV readiness and marginal portfolio contribution evidence.
- Uncertainty evidence.
- Stress-window coverage evidence.
- As-Is preservation/replay evidence.
- Runtime safety acceptance evidence or verified runtime pause/disable artifact if order submission is paused.

Acceptance criteria:

- As-Is replay is possible through the accepted harness, or the decision is correctly `blocked_as_is_unreproducible`.
- Cleaned Advertised TradingX uses only allowed Tier 0 fixes.
- Both versions use the same accepted harness.
- Cash and monthly 60/40 SPY/AGG are included.
- Drawdown, CDaR, OOS, PBO/CPCV readiness, marginal portfolio contribution, geometric uncertainty, stress, and cost-stress gates are evaluated.
- The selected 12-month capital tier and every predeclared plausible next-higher tier pass cost/capacity and 1x/2x/4x lower-bound evidence before any `go`.
- Required fixed stress windows are covered or correctly blocked.
- Final decision is exactly one of: `go`, `stop_or_refocus`, `blocked_remediation_required`, `blocked_measurement_untrusted`, `blocked_insufficient_history`, `blocked_as_is_unreproducible`, `blocked_stress_coverage_missing`.

Failure criteria:

- Any decision-hurdle metric unavailable without a blocked decision.
- PBO readiness, required PBO payload, or marginal portfolio contribution evidence missing without a blocked decision.
- Different measurement logic between As-Is and Cleaned.
- Missing manifests/hashes for decision-critical series.
- Missing raw executable-price/volume evidence without reversible adjustment model.
- Runtime order submission continued without required safety prerequisites.
- Any new alpha, strategy, model, allocator, optimizer, or research bet appears in cleaned results.

## 16. Risk Register

| Risk | Plan Reference | Repo Area | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| Scope creep | Non-Negotiable Rule, Out of Scope | Whole repo | Invalid Tier 0 result | Trace every task to plan; reject untraceable work | Orchestrator |
| Benchmark mismatch | 0A.1, 0A.2, 0B.9 | `benchmark_stack.py`, `validation.py` | Invalid comparison | Single harness and shared calendar assertions | Wave 5 owner |
| As-Is unreproducibility | 0A.1 | Git/worktree/harness | `blocked_as_is_unreproducible` | Wave 0 preservation before edits | Orchestrator |
| Insufficient history | 0A.3 | Data cache/manifests | Blocked decision | Longest common complete window resolver | Wave 5 owner |
| Look-ahead leakage | 0B.1 | `sleeves/evaluation.py`, `backtest.py` | False edge | Perturbation and context visibility tests | Wave 1 owner |
| Inconsistent calendars | 0A.3 | Tier 0 harness | False benchmark edge | Shared calendar object and post-start missing-input blocker | Wave 5 owner |
| Inconsistent cost model | 0A.4 | `costs.py`, `backtest.py` | Misstated cost stress | One declared cost model per capital scenario | Wave 5 owner |
| Active Gate 1 bypass | 0A.7, GATES-0001 | `validation.py`, PBO/CPCV, sleeve replay | Invalid `go` despite failing active hard gates | Wave 5 must enforce PBO/CPCV readiness and marginal portfolio contribution before any `go` | Wave 5 owner |
| Event-clock index ambiguity | 0B.1 | `sleeves/evaluation.py`, `backtest.py` | Same-row open fill could depend on same-row data | Enforce `target_weights[E]` depends only on data through prior session `D` | Wave 1 owner |
| Geometric lower-bound formula drift | 0A.6 | `stats.py`, Tier 0 harness | Arithmetic HAC, unapproved estimator choice, or wrong annualization could pass invalid edge | Default to stationary bootstrap with predeclared seed/block/resample metadata; require explicit approval evidence for any HAC/Newey-West hard-hurdle path | Wave 5 owner |
| Capital-tier ambiguity | 0A.4 | Tier 0 harness, `costs.py` | `go` for a capital path that fails next plausible scale | Predeclare selected and plausible higher tiers; all decision-relevant tiers must pass | Wave 5 owner |
| Parallel-agent merge conflicts | Parallelization Strategy | `validation.py`, `runtime_portfolio.py`, `service.py` | Broken integration | Exclusive ownership and merge order | Orchestrator |
| Duplicated logic | 0B.1-0B.3, 0B.9 | regime/calendar helpers | Divergent behavior | Shared helpers only where they reduce real duplication | Wave 1/5 owners |
| Unsafe live-shadow/paper behavior | 0B.5-0B.8 | runtime order path | Orders submit despite kill/halt/drawdown | Clarify runtime status; implement safety or pause order submission | Wave 4 owner |
| Statistical interpretation errors | 0A.6, 0B.4 | `stats.py`, `evaluation.py` | Invalid `go`/`stop` | Mandatory scientific review; no guessed formulas | Wave 3/5 owners |
| Macro PIT leakage | 0B.2 | `risk_free.py`, runtime/validation | Regime look-ahead | One-business-day lag and staleness tests | Wave 2 owner |
| DSR used as pass/fail | 0B.4 | `evaluation.py`, reports | Over-gating or false block | Mark DSR reported-only | Wave 3/5 owners |
| Hard-halt auto-flatten creep | 0B.8 | `portfolio/hard_halt.py`, service | Scope/safety violation | Tests assert no flatten path | Wave 4 owner |

## 17. Adversarial Review Readiness

Assumptions made:

- The repo scan is read-only context; the source plan controls required behavior.
- Existing code is only considered satisfying when it matches source-plan requirements.
- Current branch and SHA at planning time are `main` / `b0154070c802feeb99a22d288258cbe55eb12627`.
- The source plan itself is untracked in the current working tree, but was read successfully.

Assumptions rejected:

- That current hardcoded `None` macro inputs are acceptable because classifier tests pass.
- That `min_periods=1` is acceptable because it avoids missing SMA values.
- That arithmetic paired-difference HAC satisfies the Tier 0A geometric uncertainty hurdle.
- That a passing Gate 1-style validation report is equivalent to Tier 0A approval.
- That hard-halt component tests prove service runtime integration.
- That active Gate 1 can be reduced to only drawdown, CDaR, OOS, uncertainty, stress, and cost stress; PBO/CPCV readiness and marginal portfolio contribution must be handled before any `go`.
- That locating an As-Is branch/tag is sufficient without an immutable behavior artifact and same-harness replay evidence.
- That daily arithmetic paired-return uncertainty can be treated as equivalent to geometric paired log-relative uncertainty.

Unresolved ambiguities:

- Whether runtime order submission continues during Tier 0A.
- Final memo input answers for capital trajectory, operator model, shorting policy, preference, and hurdle policy.
- Optional preference for As-Is preservation mechanism.

Traceability checklist:

- Each implementation task maps to a source-plan section.
- Each source-plan hard requirement maps to repo location or explicit missing state.
- Each behavior change maps to test evidence.
- Each report field maps to Tier 0A required metrics/formulas or final decision logic.
- No task maps only to a repo improvement without source-plan support.

Test traceability checklist:

- Event-clock tests cover look-ahead failures.
- Hard benchmark tests cover monthly 60/40 next-session fill semantics and diagnostic VIX/GLD prior-available VIX timing.
- Macro tests cover VIX, 2s10s, PIT lag, and stale missing values.
- SMA tests cover 199/200 prior-observation boundaries and the first executable target-row off-by-one case.
- DSR tests cover unit convention and worked examples.
- Harness tests cover mandatory-vs-best-effort metric handling, fixed stress-window blocked states, and cannot-`go` fixtures.
- Safety tests cover kill, halt, session equity, pre-trade controls, and hard halt if runtime continues.

Benchmark-method consistency checklist:

- Same harness.
- Same manifests.
- Same cost model.
- Same shared calendar.
- Same uncertainty method.
- Same benchmark stack.
- Same stress-window protocol.
- Same capital scenarios.

Scientific/statistical review areas:

- Geometric uncertainty conversion to active CAGR / relative terminal wealth.
- Stationary-bootstrap lower-bound implementation against the formula in Wave 5.
- Stationary-bootstrap block-length, seed, resample count, paired-row resampling, and percentile policy.
- Any non-bootstrap paired log-relative confidence estimator, including HAC/Newey-West, requires explicit CIO/scientific approval before coding.
- OOS denominator rule.
- PBO/CPCV readiness and hard-gate handling.
- Marginal portfolio contribution metric construction and CDaR comparison.
- Cost-stress lower-bound interpretation.
- Capital-tier selected/plausible-next-higher decision mapping.
- DSR unit convention.
- Stress-window warm-up protocol.

Architecture review areas:

- Shared calendar and event-clock API.
- Macro cache and PIT lookup API.
- Avoiding duplicated regime snapshot logic.
- Tier 0A report/harness module boundaries.
- As-Is adapter/preservation mechanism.

Safety-control review areas:

- In-cycle kill timing.
- Exposure-increase definition under operator halt.
- Session-open equity restore path.
- Pre-trade reason-code structure.
- Hard-halt latch and no-flatten guarantee.

Parallelization risk review:

- `validation.py`, `runtime_portfolio.py`, `stats.py`, `service.py`, and `controller.py` are high-conflict files.
- Runtime safety should have one owner.
- Harness integration should have one owner.

Repo gaps and conflicts:

- No dedicated Tier 0A harness.
- No VIXCLS cache.
- Macro inputs ignored in runtime/validation.
- SMA warm-up rule violated.
- Sleeve context can see current bar.
- DSR unit mix.
- Runtime safety prerequisites incomplete/conditional.
- Hard-halt runtime documentation and code appear inconsistent.

The adversarial reviewer must be able to verify:

- Nothing was added beyond the source plan.
- All work is traceable.
- Measurement is honest.
- Benchmark comparison is valid.
- Final decision logic is controlled and auditable.

## 18. Coder Instructions

- Follow the source plan and active ADR/GATES policy as the authority for required behavior.
- Use this implementation plan as the execution map for wave ordering, ownership, files, and tests.
- If this implementation plan conflicts with, omits, or weakens a source-plan or active ADR/GATES requirement, stop and apply the stricter source-plan or active-policy requirement only after documenting the discrepancy.
- Do not implement anything not traceable to the source plan.
- Do not add strategies, alpha, models, allocators, optimizers, or research logic.
- Do not silently resolve ambiguity.
- If new ambiguity appears, stop and document it.
- Keep changes small and reviewable.
- Every change must map to:
  - source plan requirement
  - implementation wave
  - repo file
  - test evidence
- Do not treat a passing backtest as production approval.
- Only the allowed final decisions may be produced.
- Only `go` unlocks Tier 1.

## 19. Subagent Prompt Template

Use this template only if parallel AI subagents are explicitly used.

```text
You are a coding subagent on TradingX Tier 0. You must use ChatGPT 5.5 medium effort or higher. No weaker model is allowed.

Source plan path:
/Users/ahmedabd/Desktop/AI Projects/TradingX/docs/superpowers/plans/2026-04-27-tradingx-tier0-decision-and-cleaning-plan.md

Implementation plan path:
/Users/ahmedabd/Desktop/AI Projects/TradingX/docs/implementation/2026-04-27-tradingx-tier0-decision-and-cleaning-implementation-plan.md

Assigned wave:
<WAVE NAME AND NUMBER ONLY>

Allowed files:
<EXPLICIT FILE LIST FOR THIS WAVE>

Forbidden files:
<EXPLICIT FILE LIST, INCLUDING SOURCE PLAN AND OUT-OF-WAVE SHARED FILES>

Strict scope guardrails:
- The source plan and active ADR/GATES policy control WHAT to implement and the required decision gates.
- The implementation plan controls wave boundaries, ownership, file scope, and test/evidence sequencing.
- If the implementation plan conflicts with, omits, or weakens the source plan or active ADR/GATES policy, stop and report the discrepancy before coding.
- Do not add strategies, alpha, models, allocators, optimizers, or research logic.
- Do not widen into Tier 1, Tier 2, or Tier 3.
- Do not change classifier thresholds or optimize parameters.
- Do not treat current repo behavior as correct unless it matches the source plan.
- Do not start Wave 1-3 work unless Wave 0 runtime preflight evidence proves order submission is paused/disabled or Wave 4 safety controls have already been accepted.
- Do not use HAC/Newey-West as a Tier 0A hard-hurdle uncertainty method unless explicit CIO/scientific approval evidence is provided.
- Every change must trace to a source-plan requirement, assigned wave, repo file, and test evidence.
- If ambiguity appears, stop and report it instead of guessing.

Tests/evidence required:
<WAVE-SPECIFIC TEST COMMANDS AND REQUIRED ARTIFACTS>

Stop conditions:
- You need to change forbidden files.
- You find a source-plan contradiction.
- You need a scientific/statistical/benchmark interpretation not specified by the source plan, active ADR/GATES policy, or this implementation plan.
- Your task would require adding untraceable behavior.
- Another agent changed a file you own in an incompatible way.

Expected output:
- Changed files summary.
- Tests run.
- Evidence generated.
- Unresolved ambiguity list.
- Confirmation that no out-of-scope work was added.
- Confirmation that every change maps to the source plan and assigned wave.
```

## 20. Completion Checklist

- [x] Source plan read.
- [x] Repo scanned.
- [ ] All tasks traceable to plan.
- [ ] All tasks traceable to repo files.
- [ ] No unapproved features added.
- [ ] No Tier 1/Tier 2/Tier 3 work added before `go`.
- [ ] Clarification questions resolved or documented.
- [ ] Parallel wave dependencies respected.
- [ ] No conflicting agent edits left unresolved.
- [ ] Tests implemented and passing.
- [ ] Regression tests passing.
- [ ] Evidence regenerated.
- [ ] Final decision generated.
- [ ] Adversarial review package ready.
