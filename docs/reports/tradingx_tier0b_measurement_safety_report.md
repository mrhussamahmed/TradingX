# TradingX Tier 0B Measurement And Safety Report

Generated: 2026-04-28

## Scope

This report covers the Tier 0B implementation pass for measurement prerequisites and the runtime preflight required before parallel work.

No new alpha, strategy, model, allocator, optimizer, classifier threshold, or production approval path was added.

## Wave 0 Preservation And Runtime Preflight

- As-Is preservation artifact: `docs/reports/tradingx_tier0_wave0_as_is_preservation.md`
- Preserved commit: `b0154070c802feeb99a22d288258cbe55eb12627`
- Dirty executable diff hash: `46a41c6d602a37805bb5264a636487462787517df8f0c34a88be2ad28055c0f0`
- Runtime preflight found no active TradingX order-submit process.
- `artifacts/operator_platform/runtime_host/state.json` reported `halted`.
- Wave 4 runtime safety prerequisites remain required before any paper/live-shadow order submission resumes during Tier 0A.

## Wave 1 Event-Clock And SMA(200)

Implemented:

- Sleeve evaluation contexts now expose only bars strictly before execution row `E`.
- Runtime sleeve context hides execution-row bars.
- Runtime and validation regime snapshots use prior close and require 200 prior eligible observations for SMA(200).
- Drift `spy_close_over_sma_200` uses prior 200 observations.

Evidence:

- Event-clock and SMA tests cover same-row visibility, 199/200 prior-observation boundaries, and integration sleeve replay.

## Wave 2 FRED Macro PIT Wiring

Implemented:

- FRED `VIXCLS` local cache support.
- One-NYSE-session default availability lag, optional release timestamp override, and five-session stale-missing behavior.
- Existing DGS2/DGS10 2s10s spread now has PIT lookup with the same stale-missing rule.
- Runtime and validation regime snapshots pass `vix_close` and `yield_curve_spread_bps` into the existing classifier.
- Drift `vix_level` reads the local VIX cache when present.

Evidence:

- Unit tests cover VIX risk-off/stressed branches, 2s10s inversion, PIT lag, release timestamp override, stale macro missing behavior, and drift VIX samples.

## Wave 3 DSR Unit Convention

Implemented:

- DSR helpers now require `SharpePerPeriod` and `SharpeVariancePerPeriod` wrappers.
- Annualized callers convert through explicit annualized-to-per-period helpers.
- Trial statistics expose per-period DSR inputs while preserving existing annualized summaries.
- Evaluation evidence marks DSR as `reported_only` for Tier 0.

Evidence:

- Worked-example DSR tests still pass.
- Regression tests cover annualized-to-per-period conversion and bypass prevention.

## Wave 5 Controlled Decision Harness

Implemented:

- `tradingx.tier0_decision` encodes the allowed Tier 0A decision values.
- Geometric paired uncertainty uses `log1p(strategy_return) - log1p(benchmark_return)` and stationary bootstrap paired-row resampling.
- Missing block-length rule, invalid returns, missing evidence, and total-loss cases fail closed.
- CLI command `tier0a-decision-report` writes:
  - `docs/reports/tradingx_tier0a_benchmark_metrics.json`
  - `docs/reports/tradingx_tier0a_benchmark_decision_report.md`

Current generated decision:

- `blocked_stress_coverage_missing`

Reason:

- Final Tier 0A memo inputs were not supplied.
- Fixed stress-window replay, manifests, hard benchmark returns, cost stress, PBO/CPCV, marginal portfolio contribution, and paired return evidence were not generated in this pass.

## Runtime Safety Status

Order submission was verified inactive during Wave 0. Runtime safety Wave 4 was therefore not implemented as a prerequisite for this implementation pass.

If paper/live-shadow order submission resumes during Tier 0A, the plan still requires in-cycle kill, exposure-aware halt, session-open equity restore, minimal pre-trade enforcer, and hard-halt runtime wiring before order submission continues.
