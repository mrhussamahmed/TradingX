# Wave 8 Loop 1 Fix Report

| ID | Finding | Disposition | Resolution |
|---|---|---|---|
| #1 | `post_probe_recertification_missing` dead code | Fixed | Cross-bundle check: when `live_probe_run_record` is bundled without a `live_probe_recertification_report`, evaluator emits `post_probe_recertification_missing`. Test: `test_run_record_without_recertification_blocks_production`. |
| #2 | Override `action`-verb bypass | Fixed | Added `_CORE_CONTROL_DISABLE_VERBS` set in builder; evaluator inlines the same set. Both fire `manual_exception_disabled_core_control` when `action` matches. Test: `test_runtime_override_with_disable_action_blocks`. |
| #3 | `status="pass"` with `min_activity=false` bypass | Fixed | Evaluator now emits `live_probe_inconclusive` whenever `min_activity_met=False`, regardless of self-asserted status. Test: `test_run_record_with_status_pass_but_min_activity_unmet_blocks`. |
| #4 | `status="fail"`/"rolled_back" no blocker | Fixed | Evaluator now treats `{inconclusive, fail, rolled_back}` as `live_probe_inconclusive`. Test: `test_run_record_with_status_fail_blocks`. |
| #5 | Recertification freshness window | Deferred (residual risk #2). |
| #6 | Decimal-string format completeness | Partial — Wave 7's lesson (canonical-decimal strict check) limited applicability. Builder produces deterministic strings. |
| #7 | Schema enums on status fields | Deferred (residual risk #3). |
| #8 | `max_exception_duration_seconds` unused | Deferred. |
| #9 | `idempotency_key_policy` content unchecked | Deferred. |
| #10 | `self_trade_prevention="disabled"` accepted | Deferred. |
| #11 | Runtime-execution red tests | Acknowledged out of scope; deferred to runtime wiring wave. |
| #12 | Adversarial scrub gaps | Partially addressed — added scrub tests for authority, pre-trade, drill, status-pass-with-min-activity-unmet, and run-without-recertification. |
| #13-#15 | Minor | Deferred. |

## Validation after fixes

Before loop 2:

- Wave 8 focused tests: 21 passed.
- Affected suite: passed.
- Full suite: 1151 passed.
- ruff/mypy/black/check_index: clean.
