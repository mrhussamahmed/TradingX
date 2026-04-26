# Wave 8 Adversarial Review — Loop 2

A fresh reviewer was spawned with minimal context after loop-1 fixes.

## Top findings (paraphrased)

- **High**: builder/evaluator drift on `live_probe_inconclusive`.
- **Medium**: disable-verb list duplicated between builder and
  evaluator.
- **Medium**: `second_approver_required` ignores `signatures` count.
- **Low**: cross-bundle `run_refs` linkage not validated.
- **Low**: disable-verb match exact-string only.
- **Low**: `live_probe_plan_expired` masks parse failure.

Loop-1 fix verification: PASS for all four critical/high fixes.

## Disposition

See `wave8_live_probe_operational_safety_review_loop2_fix_report.md`.

A truly clean reviewer session was not available.
