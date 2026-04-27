# Wave 8 Adversarial Review — Loop 1 (Combined A + B)

A single combined adversarial reviewer ran both lenses (blocker
semantics + schemas/tests).

## Top findings (paraphrased)

- **Critical**: `post_probe_recertification_missing` is registered but
  no evaluator path emits it (dead code).
- **Critical**: `manual_exception_disabled_core_control` only fires on
  the explicit `disabled_controls_requested` array — a forged
  `action="disable_kill_switch"` slips through.
- **Critical**: `live_probe_run_record` with `status="pass"` and
  `minimum_activity_met=False` was accepted without surfacing
  `live_probe_inconclusive`.
- **High**: `status="fail"` / `"rolled_back"` emitted no blocker.
- **High**: recertification report has no freshness window.
- **High**: many decimal fields lack `format: "decimal-string"`.
- **High**: status fields on recertification lack schema enums.
- **Medium-Low**: max-exception-duration unused, idempotency policy
  empty allowed, self-trade-prevention disabled allowed, missing
  scrub coverage, etc.

## Disposition

See `wave8_live_probe_operational_safety_review_loop1_fix_report.md`.

A truly clean reviewer session was not available; reviewer was spawned
with minimal context.
