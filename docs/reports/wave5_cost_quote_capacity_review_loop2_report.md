# Wave 5 Adversarial Review — Loop 2

A fresh adversarial reviewer was spawned with minimal context after
loop-1 fixes were applied and the test suite was green.

## Top findings (paraphrased)

- **C1 (Critical)**: `additionalProperties` value-schema still not
  enforced for nested mapping properties (note: at the time of loop-2 the
  validator extension was being tested; the fix was confirmed and
  re-verified after loop-2).
- **C2 (Critical)**: cost/capacity bundle requirement is gated on
  `has_execution_observation`. Reviewer argues the rule should be
  always-on at paper_trading+.
- **H1 (High)**: `arrival_timestamp_policy` divergence rule has no
  test.
- **H2 (High)**: `lower_bound_capacity_limit` returns `"0"` sentinel
  when `None` was input; downstream consumers cannot distinguish
  zero-set from missing.
- **H3 (High)**: builder vs evaluator semantics for
  `live_sample_requirement_unmet` are inconsistent.
- **M1 (Medium)**: no dedicated `replay_slippage_summary` schema.
- **M2 (Medium)**: CLI validation is post-build, only catches builder
  regressions, not malformed input.
- **M3 (Medium)**: evaluator does not re-derive `impact_claim_status`
  from raw fields.
- **L1, L2, L3**: minor.

## Disposition

See `wave5_cost_quote_capacity_review_loop2_fix_report.md` for the
finding-by-finding disposition.

## Reviewer-context caveat

A truly clean reviewer session was not available. The loop-2 reviewer
was spawned with the smallest possible context and explicit
instructions to ignore the coding agent's assumptions and review from
first principles. This caveat is documented in the implementation
report.
