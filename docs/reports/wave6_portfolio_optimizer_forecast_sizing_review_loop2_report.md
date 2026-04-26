# Wave 6 Adversarial Review — Loop 2

A fresh reviewer was spawned with minimal context after loop-1 fixes
were applied and the test suite was green.

## Top findings (paraphrased)

- **C1 (Critical)**: Wave 6 evaluators are passive — bundles without
  the relevant artifact kinds emit zero blockers. (Same theme as
  Wave 5 C2.)
- **C2 (Critical)**: `assert_sizing_monotonicity` is dead code and
  `sizing_decision` schema is absent from this slice.
- **M1 (Major)**: status string fields not normalized — case/whitespace
  drift in `lockbox_status`, `perturbation_status`,
  `covariance_drift_status`, `turnover_status`.
- **M2 (Major)**: `cost_capacity_report_refs` non-list bypass — the
  isinstance guard skipped anything that wasn't a list.
- **M3 (Major)**: required-baseline omission test only covers
  `equal_weight`; should parametrize over all seven baselines.
- **M4 (Major)**: optimizer accepting `expected_return_status =
  "uncertainty_penalized"` without surfacing the uncalibrated cap.
- **M5 (Major)**: `optimizer_input` and `optimizer_decision` schemas
  absent.
- **m1-m5 (Minor)**: missing implementation report, no migration test,
  schema format nits.

## Disposition

See `wave6_portfolio_optimizer_forecast_sizing_review_loop2_fix_report.md`
for the finding-by-finding disposition. Headlines:

- **Fixed**: M1 (`_normal_form` everywhere), M2 (fail-closed for
  non-list refs), M3 (parametrized over all seven baselines), M4
  (evaluator now surfaces `expected_return_uncertainty_uncalibrated`
  whenever optimizer reports `uncertainty_penalized`).
- **Rejected with rationale**: C1, C2 — see implementation report
  residual risks.
- **Deferred**: M5 (`optimizer_input` / `optimizer_decision` schemas
  to Wave 9), migration test (Wave 10).
- **Done as part of writing**: m1 (this report family).

## Reviewer-context caveat

A truly clean reviewer session was not available; reviewer was spawned
with minimal context and explicit instructions to ignore the coding
agent's assumptions.
