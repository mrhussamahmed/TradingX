# Wave 6 Adversarial Review — Loop 1

Two reviewers were spawned in parallel.

## Reviewer A (blocker semantics)

Top findings:

- **C1**: Wave 6 evaluators are passive (no required-presence
  enforcement). Mirrors Wave 5 finding.
- **C2**: `assert_sizing_monotonicity` is dead code at runtime.
- **H1**: Equal-weight (and other required-baseline) silent omission
  not blocked.
- **H2**: Re-derivation of `applicable_baseline_excluded` ignores
  `REQUIRED_BASELINES`.
- **H3**: `tail_risk_missing` evaluator accepts non-tail terms.
- **H4**: Forecast utility comparison uses point-estimate, not lower
  CI.
- **H5**: Sizing cap re-derivation misses `sleeve_cap`,
  `net_exposure_cap`, `drawdown_budget`.
- **H6**: `kelly_disabled` default-true is fail-open.
- **H7**: `feature_timestamp_unauditable` cap of `paper_shadow` is
  too lenient for hard look-ahead leakage.
- **M1-M5**: builder/evaluator divergence, fallback enforcement,
  perturbation granularity, `not_run` doesn't block, expected-return
  status whitelist.
- **L1-L3**: minor.

## Reviewer B (schemas, tests)

Top findings:

- **C1**: `experiment_registration` Milestone 7 amendment not
  applied — three required hashes missing.
- **H1**: missing cost/capacity refs not re-derived in evaluator.
- **H2**: turnover not re-derived numerically.
- **H3**: tail-risk evaluator weaker than builder.
- **H4**: fallback enforcement missing.
- **M1**: `assert_sizing_monotonicity` dead code.
- **M2**: red tests assert builder output rather than evaluator
  behaviour.
- **M3**: `forecast_model_manifest` evaluator misses empty refs.
- **M4**: no cross-validation between `expected_return_report` and
  `forecast_model_manifest`.
- **M5**: kelly_disabled fail-open.
- **L1-L5**: minor (evidence_class drift, migration test, schema
  format gaps).

## Disposition

See `wave6_portfolio_optimizer_forecast_sizing_review_loop1_fix_report.md`.

## Reviewer-context caveat

A truly clean reviewer session was not available. Reviewers were
spawned with minimal context.
