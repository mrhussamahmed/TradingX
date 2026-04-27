# Wave 9 Loop 1 Fix Report

| ID | Finding | Disposition | Resolution |
|---|---|---|---|
| C1 | Empty-deltas treated as equivalent | Deferred (residual risk #3). |
| C2 | `recertification_required` not enforced | Fixed | Cross-bundle check: `change_control_record` with `recertification_required=True` requires a paired `recertification_report`. |
| H1 | Registry seeds | Verified | All new codes (`production_approval_expired`, `next_review_due_passed`, `recertification_report_missing`) seeded. Pre-existing codes (`dependency_scope_unresolved`, `unrecorded_material_change`, `authority_boundary_missing`) confirmed in registry from earlier waves. |
| H2 | Adversarial test for forged expiry | Deferred (residual risk #2 in implementation report). |
| H3 | `detect_unrecorded_change` runtime wiring | Deferred (residual risk #1). |
| M1 | Status field enums | Deferred (residual risk #2). |
| M2 | `production_decay_event` enum drift | Fixed | Evaluator now treats any `previous_state != new_state` as `production_approval_expired`, matching builder. |

## Validation after fixes

- Wave 9 focused tests: 18 passed.
- Full unit/contract/integration: 1169 passed, 98 skipped.
- ruff/mypy/black/check_index: clean.
