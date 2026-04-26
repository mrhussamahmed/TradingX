# Wave 6 Loop 1 Fix Report

| Finding | Disposition | Resolution |
|---|---|---|
| A.C1 / B.C1 (Wave 6 artifacts not required) | Rejected with documented rationale (residual risk #1 in implementation report) — same trade-off as Wave 5 C2. |
| A.C2 / B.M1 (assert_sizing_monotonicity dead code; missing sizing_decision schema) | Deferred to Wave 8 / Wave 9 with documented rationale (residual risk #2). |
| B.C1 (Milestone 7 amendment missing) | Fixed | Added `forecast_model_hash`, `feature_manifest_hash`, `sizing_policy_hash` to `experiment_registration.schema.json` and the existing fixture. |
| A.H1 / A.H2 (Required baseline silent omission) | Fixed | Builder and evaluator now require *every* `REQUIRED_BASELINES` baseline to be in `tested_baselines` or in `excluded_baselines` with an approved exclusion. Test parametrized in loop 2. |
| A.H3 / B.H3 (tail_risk evaluator whitelist drift) | Fixed | Evaluator now requires intersection with the same `_TAIL_RISK_TERMS` whitelist as the builder. |
| A.H4 (forecast utility lower CI) | Deferred — schema would need a new `oos_utility_lower_ci_after_costs` field. The current point-estimate comparison plus calibration enforcement is the minimal viable Wave 6 slice; lower-CI hardening is a future enhancement. |
| A.H5 (sleeve_cap, net_exposure_cap, drawdown_budget caps) | Fixed | Builder and evaluator now reject zero/negative values for all eight cap fields. New test `test_evaluator_re_derives_drawdown_budget_missing`. |
| A.H6 / B.M5 (kelly_disabled fail-open) | Fixed | Evaluator now defaults missing `kelly_disabled` to `False` (fail-closed). New test `test_kelly_enabled_evaluator_fails_closed_on_missing_field`. |
| A.H7 (feature_timestamp_unauditable cap) | Deferred — `paper_shadow` cap is consistent with other Wave 6 codes; reclassifying to `RESEARCH_ONLY` is a future audit decision and would require updating the registry coverage matrix. |
| A.M1 (lambda_justification_refs in evaluator) | Fixed | Evaluator now flags `optimizer_or_sizing_lockbox_missing` when `lambda_justification_refs` is an empty mapping. |
| A.M2 / B.H1 (cost_capacity_report_refs and fallback re-derivation) | Fixed | Evaluator now flags `execution_semantics_incomplete` when `cost_capacity_report_refs` is missing/non-list/empty (loop 2 strengthened). Fallback record evaluator flags missing `static_blueprint_ref` and `operator_alert_ref`. |
| A.M3 (perturbation granularity) | Deferred — schema currently uses single string status; granular boolean fields are a future enhancement. |
| A.M4 (no_alpha_pipeline `not_run` doesn't block) | Fixed | Both builder and evaluator now treat anything other than `null_passed` as `no_alpha_pipeline_edge`. New test `test_no_alpha_pipeline_non_passed_states_block`. |
| A.M5 (expected_return_status whitelist) | Fixed | Evaluator now whitelists `{promotion_valid, uncertainty_penalized}`; everything else fires `expected_return_not_promotion_valid`. |
| B.H2 (turnover not numerically re-derived) | Fixed | Evaluator now compares `Decimal(observed_adjacent_turnover)` against `Decimal(max_adjacent_decision_turnover)` independently of the string status. New test `test_evaluator_re_derives_turnover_cap_from_decimals`. |
| B.H4 (fallback enforcement) | Partial — fallback record blockers now re-derive missing refs. Cross-bundle "fallback occurred but no record" is deferred. |
| B.M2 (tests assert builder output) | Fixed | Loop 2 added evaluator-path tests for cost-capacity refs, baseline omission, tail-risk whitelist, turnover, kelly fail-closed, drawdown budget, no-alpha not_run. |
| B.M3 (forecast_model_manifest empty refs in evaluator) | Fixed | Evaluator now flags `feature_timestamp_unauditable` when `feature_manifest_ref` or `label_definition_ref` is empty. |
| B.M4 (cross-validate forecast_model_ref) | Deferred — cross-bundle validation is a future hardening pass. |
| L1-L5 / m1-m5 | Deferred or noted as future enhancements. |

## Validation after fixes

Before loop 2:

- Wave 6 tests: passed.
- Affected suite: passed.
- Full suite: 1099 passed.
- ruff/mypy/black/check_index: clean.
