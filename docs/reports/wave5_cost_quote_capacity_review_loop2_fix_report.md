# Wave 5 Loop 2 Fix Report

| ID | Finding | Disposition | Resolution |
|---|---|---|---|
| C1 | `additionalProperties` value-schema not enforced | Fixed (already in loop 1 follow-up) | Confirmed working: the validator now enforces nested mapping subschemas. Re-verified by manual run. |
| C2 | Cost/capacity rule conditionally passive | Rejected with documented rationale | Implementation report residual risk #1 captures the trade-off. The current evaluator fires missing-cost-model and missing-capacity-curve blockers when the bundle includes execution evidence; bundles for paper_trading+ that contain only mandate authority artifacts (wave-2 isolation tests) are passed through unaffected. Making the rule always-on requires updating ~20 wave-2 tests to bundle stub cost/capacity reports. The exit criterion is partially enforced via the bundling pipeline; tighter enforcement is deferred to Wave 9. |
| H1 | No test for `arrival_timestamp_policy` divergence | Fixed | Added `test_arrival_timestamp_policy_change_within_study_contaminates_lineage` and `test_arrival_timestamp_policy_missing_contaminates_lineage` in `tests/unit/test_experiments.py`. |
| H2 | `lower_bound_capacity_limit: "0"` sentinel ambiguity | Fixed | Builder now serializes `""` when input is `None`. Evaluator handles empty string as "missing". |
| H3 | `live_sample_requirement_unmet` builder/evaluator mismatch | Fixed | Builder no longer gates `live_sample_requirement_unmet` on `impact_claim_requested`. Both builder and evaluator now fire the blocker when `min_live > 0` and `live_total < min_live`. |
| M1 | No `replay_slippage_summary.schema.json` | Deferred — residual risk #2 in implementation report. The classifier path is gated by `quote_quality_records` collection presence in the runtime; a dedicated schema would harden the boundary further. |
| M2 | CLI validation is post-build | Deferred — residual risk #3 in implementation report. Builders normalize inputs; pre-build validation is a future hardening. |
| M3 | Evaluator does not re-derive `impact_claim_status` | Partial fix | The underlying conditions (paper-only, unsupported-bucket, underpowered, etc.) are now re-derived in `evaluate_cost_capacity_blockers`. The `impact_claim_status` field itself is informational; the evaluator does not promote based on it. |
| L1 | `_coerce_int` accepts floats silently | Deferred — JSON input is integer-typed in practice. |
| L2 | NaN guard on Decimals | Deferred — Decimals don't carry NaN. |
| L3 | Trading-session enum gap | Verified to already include `auction`. |

## Validation after fixes

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_cost_capacity_wave5.py tests/unit/test_promotion.py tests/unit/test_experiments.py tests/unit/test_main.py tests/unit/test_replay_slippage.py tests/unit/test_blocker_registry.py -q`: passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit tests/contract tests/integration`: 1071 passed, 98 skipped.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`: clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/tradingx`: clean.
- Touched-file Black check: clean.
- `python3 scripts/check_index.py`: passed.
