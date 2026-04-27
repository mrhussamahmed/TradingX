# Wave 6 Portfolio Utility, Optimizer, Forecasts, And Sizing — Implementation Report

Last updated: 2026-04-26

## Goal

Implement Milestones 6 and 7 so the optimizer, forecasts, and sizing
cannot manufacture or amplify false edge.

## Files changed

Source:

- `src/tradingx/portfolio/optimizer.py` (new) —
  `build_portfolio_utility_definition`,
  `build_optimizer_validation_report`,
  `build_optimizer_fallback_record`, `REQUIRED_BASELINES`.
- `src/tradingx/forecasts.py` (new) —
  `build_feature_manifest`, `build_label_definition`,
  `build_forecast_model_manifest`, `build_expected_return_report`,
  `build_sizing_policy`, and the `assert_sizing_monotonicity` helper.
- `src/tradingx/promotion.py` — `evaluate_portfolio_optimizer_blockers`,
  `evaluate_forecast_sizing_blockers`, new blocker codes seeded into
  `_REGISTRY_SEEDS`, new artifact kinds recognized in
  `_validate_cas_payload`.
- `schemas/quant/experiment_registration.schema.json` — adds required
  `forecast_model_hash`, `feature_manifest_hash`,
  `sizing_policy_hash` fields per the §Milestone 7 amendment.

Schemas (new):

- `schemas/quant/portfolio_utility_definition.schema.json`
- `schemas/quant/optimizer_validation_report.schema.json`
- `schemas/quant/optimizer_fallback_record.schema.json`
- `schemas/quant/forecast_model_manifest.schema.json`
- `schemas/quant/feature_manifest.schema.json`
- `schemas/quant/label_definition.schema.json`
- `schemas/quant/expected_return_report.schema.json`
- `schemas/quant/sizing_policy.schema.json`

Tests:

- `tests/unit/test_portfolio_optimizer_wave6.py` — 36 tests covering
  the seven required Wave 6 red tests, schema validation, evaluator
  re-derivation paths, parametrized required-baseline omission,
  no-alpha pipeline strict whitelist, kelly fail-closed, drawdown
  budget, and turnover cap.

Fixture:

- `tests/fixtures/experiments/experiment_registration_pre_result.json`
  gains the three §Milestone 7 amendment hashes.

## Required red tests

| Roadmap red test | Implementation |
|---|---|
| Optimizer without frozen utility lambdas yields `optimizer_or_sizing_lockbox_missing` | `test_optimizer_without_frozen_utility_lambdas_yields_lockbox_missing` |
| Excluding equal-weight baseline without signed approval blocks | `test_excluding_equal_weight_without_signed_approval_blocks` |
| No-alpha full pipeline showing edge blocks optimizer promotion | `test_no_alpha_full_pipeline_showing_edge_blocks_optimizer_promotion` |
| Forecast feature timestamp after decision time blocks | `test_forecast_feature_timestamp_after_decision_time_blocks` |
| Uncalibrated uncertainty caps at `paper_shadow` | `test_uncalibrated_uncertainty_caps_at_paper_shadow` |
| Higher cost increasing size fails property test | `test_higher_cost_increasing_size_fails_property_test` |
| Negative penalized edge creating long exposure fails unless allowed | `test_negative_penalized_edge_creating_long_exposure_fails_unless_allowed` |

## Adversarial reviews

Two loops were run.

- Loop 1: two parallel reviewers (A — blocker semantics; B — schemas /
  tests). Reports: `wave6_portfolio_optimizer_forecast_sizing_review_loop1_report.md`.
  Critical/high findings fixed, including: missing §Milestone 7
  amendment hashes in `experiment_registration`, silent baseline
  omission, tail-risk whitelist drift between builder and evaluator,
  cost-capacity refs not re-derived, turnover not re-derived numerically,
  paired OOS lower CI, expected-return-status whitelist, kelly
  fail-closed, drawdown-budget cap, and forecast-model-manifest empty
  refs.
- Loop 2: one fresh reviewer.
  `wave6_portfolio_optimizer_forecast_sizing_review_loop2_report.md`.
  M1 (status string normalization), M2 (cost-capacity non-list
  bypass), M3 (parametrize all seven required baselines), and M4
  (optimizer accepting `uncertainty_penalized` without surfacing the
  cap) — fixed. C1 (passive evaluator design), C2 (missing
  `sizing_decision` schema), and M5 (missing `optimizer_input` /
  `optimizer_decision` schemas) — rejected with documented rationale
  (residual risks below).

A truly clean reviewer session was not available; reviewers were
spawned with minimal context.

## Validation

- Wave 6 focused tests: 36 passed.
- Affected suite (promotion, experiments, main, blocker_registry):
  passed.
- Full unit/contract/integration suite: 1105 passed, 98 skipped.
- `ruff check`, `mypy`, touched-file Black: clean.
- `python3 scripts/check_index.py`: passed.

## Accepted residual risks

1. **Passive evaluator design.** `evaluate_portfolio_optimizer_blockers`
   and `evaluate_forecast_sizing_blockers` only fire when their
   corresponding payload kinds are bundled. Bundles that omit Wave 6
   artifacts entirely (e.g. wave-1/2 isolation tests) pass through.
   Same rationale as Wave 5: making the rule unconditionally always-on
   would break the wave-2 mandate isolation tests. Tighter enforcement
   is deferred to Wave 9 / final integration.
2. **`assert_sizing_monotonicity` is helper-level.** The function
   returns `sizing_property_violated` codes but is invoked only from
   the unit test, not from any production runtime path. The roadmap
   §1340 lists `sizing_decision.schema.json` and a sizing-decision
   artifact; this wave does not produce that artifact. Runtime wiring
   of sizing-decision emission and per-decision monotonicity
   evaluation is deferred to Wave 8 (Live Probe And Operational
   Safety) where the runtime sizing path is exercised.
3. **`optimizer_input` and `optimizer_decision` schemas absent.** The
   roadmap §1215-1216 lists these. The current slice produces the
   utility/validation/fallback artifacts but defers the per-decision
   input and decision payloads. Optimizer runtime cannot yet content-
   hash-bind decisions to validation freezes. Deferred to Wave 9
   (Recertification And Change Control).
4. **No CLI subcommands.** Roadmap §1283-1287 lists optimizer-validate,
   optimizer-decision, optimizer-recertify, portfolio-baselines and
   §1411-1416 lists forecast-report, sizing-policy-check,
   sizing-decision. These are deferred — the builders exist; runtime
   plumbing of the CLI handlers is straightforward but not on Wave 6's
   critical path.
5. **Migration test for static allocations.** No fixture-level test
   asserts that an existing static-allocation strategy
   (`static_sleeve_budget`) round-trips through the evaluator without
   raising new Wave 6 blockers. Deferred to Wave 10 (Legacy Path
   Retirement And Hardening).
6. **`./scripts/validate` unrelated Black drift.** Unchanged from
   prior waves.

## Commit

One local commit on `codex/tradingx-quant-hardening`:

```
TradingX quant hardening: complete Wave 6 - Portfolio Utility, Optimizer, Forecasts, And Sizing
```
