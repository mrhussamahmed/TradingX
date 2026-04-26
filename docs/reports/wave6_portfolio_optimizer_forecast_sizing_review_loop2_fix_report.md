# Wave 6 Loop 2 Fix Report

| ID | Finding | Disposition | Resolution |
|---|---|---|---|
| C1 | Wave 6 evaluators are passive | Rejected with rationale (residual risk #1 in implementation report). | Documented. |
| C2 | `assert_sizing_monotonicity` dead code; `sizing_decision` schema absent | Deferred (residual risk #2). | Wave 8 will wire runtime sizing decisions; Wave 9 may add the schema. |
| M1 | Status strings not normalized | Fixed | Evaluator now uses `_normal_form` for `lockbox_status`, `perturbation_status`, `covariance_drift_status`, `turnover_status`, `expected_return_status`, `no_alpha_pipeline_status`. Lockbox now whitelists `{frozen, nested_validation}`; everything else is missing. |
| M2 | `cost_capacity_report_refs` non-list bypass | Fixed | Evaluator now treats any value that isn't a non-empty list of strings as missing. |
| M3 | Required-baseline test only covers `equal_weight` | Fixed | `test_silent_baseline_omission_blocks_promotion` parametrized over all seven `REQUIRED_BASELINES`. |
| M4 | Optimizer accepts `uncertainty_penalized` without cap | Fixed | When optimizer report says `expected_return_status = uncertainty_penalized`, evaluator now also emits `expected_return_uncertainty_uncalibrated` so the cap is surfaced even if no `expected_return_report` is bundled. |
| M5 | `optimizer_input` and `optimizer_decision` schemas absent | Deferred to Wave 9 (residual risk #3). |
| m1 | No implementation report | Done — this report family. |
| m2 | No migration test | Deferred to Wave 10. |
| m3 | kelly_disabled fail-closed | Already correct. |
| m4 | Duplicated `_TAIL_RISK_TERMS` constant | Deferred — small drift risk; both copies are short and obvious to maintain together. |
| m5 | Boundary test for `paired_oos_utility_lower_ci == threshold` | Already covered by builder logic (`<=` test); no additional coverage required for Wave 6 minimal viable. |

## Validation after fixes

- Wave 6 focused tests: 36 passed (added parametrized variants).
- Full unit/contract/integration suite: 1105 passed, 98 skipped.
- `ruff check`: clean.
- `mypy src/tradingx`: clean.
- Touched-file Black: clean.
- `python3 scripts/check_index.py`: passed.
