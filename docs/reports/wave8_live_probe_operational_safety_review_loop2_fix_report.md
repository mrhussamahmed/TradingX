# Wave 8 Loop 2 Fix Report

| ID | Finding | Disposition | Resolution |
|---|---|---|---|
| H | Builder/evaluator drift on `live_probe_inconclusive` | Fixed | Builder now appends `live_probe_inconclusive` for `status in {inconclusive, fail, rolled_back}` and when `minimum_activity_met=False`. Mirrors evaluator. |
| M | Disable-verb list duplicated | Acknowledged | Both inline copies match exactly; full deduplication via shared module export deferred (residual risk #4). |
| M | `second_approver_required` ignores `signatures` | Fixed | Builder and evaluator now require `len(approvers) >= 2` AND `len(signatures) >= 2` when `second_approver_required=True`. |
| L | Cross-bundle `run_refs` linkage | Deferred (residual risk #5). |
| L | Disable-verb fuzzy match | Deferred. |
| L | `live_probe_plan_expired` masks parse failure | Deferred. |

## Validation after fixes

- Wave 8 focused tests: 21 passed.
- Full unit/contract/integration suite: 1151 passed, 98 skipped.
- ruff/mypy/black/check_index: clean.
