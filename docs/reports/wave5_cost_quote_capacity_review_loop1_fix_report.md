# Wave 5 Loop 1 Fix Report

Disposition for each loop-1 finding.

## Reviewer A

| ID | Finding | Disposition | Resolution |
|---|---|---|---|
| A.C1 | Cost/capacity enforcement passive when no execution evidence | Partial accept — see residual risk #1 in implementation report. Always-on enforcement deferred to avoid wide-scope refactor of wave-2 tests. | Documented in implementation report. Loop-2 also re-raised; same disposition. |
| A.C2 | Zero-observation report still promotion-valid | Fixed | `build_cost_model_report` now raises `execution_sample_power_missing` whenever `paper + probe + live <= 0`, and forces `promotion_valid=False` on paper-only impact status regardless of `impact_claim_requested`. New test `test_zero_observation_cost_report_is_not_promotion_valid`. |
| A.H1 | Legacy replay summary classifier dead because on-disk JSON has no `kind` | Fixed | `ReplaySlippageSummary` now has `kind: str = "replay_slippage_summary"` field; persistence layer serializes it; web read model round-trips it. Verified by new test `test_replay_slippage_summary_serialization_round_trips_kind_and_class`. |
| A.H2 / M4 | Evaluator trusts payload-asserted `blocker_codes` | Fixed | `evaluate_cost_capacity_blockers` now re-derives critical blockers from raw fields: `unsupported_buckets` + `sparse_bucket_fallback_policy`, `powered_bucket_coverage`, observation-count totals, live-sample threshold, and `quote_quality_record` quality vs handling policy. New tests `test_evaluator_re_derives_unsupported_cost_bucket_from_raw_fields` and `test_evaluator_re_derives_quote_quality_blocker_from_raw_fields`. |
| A.M2 | Capacity extrapolation boolean misaligned with limit check | Fixed | Builder now sets `extrapolation_risk = out_of_range OR over_lower_bound_limit`. New test `test_capacity_target_above_lower_bound_limit_marks_extrapolation_risk`. |
| A.M3 | Paper-only impact status fall-through | Fixed | Builder unconditionally classifies paper-only as `not_supported_paper_only` and forces a blocker code. |
| A.L1 | CLI `or None` ambiguity | Deferred — minor; downstream behavior unchanged. |
| A.L2 | NaN guard on Decimals | Deferred — Decimals don't carry NaN in this codebase. |

## Reviewer B

| ID | Finding | Disposition | Resolution |
|---|---|---|---|
| B.1 | `additionalProperties: {schema}` not enforced | Fixed | Extended `_validate_against_schema` and `_validate_schema_keywords` in `src/tradingx/authority.py` to recurse into nested mapping schemas. |
| B.2 | `--include-quote-quality` is hidden bypass | Fixed | `generate_replay_slippage_evidence` now requires actual `quote_quality_records` in the validation store before flipping `cost_evidence_class` to `wave5_cost_evidence`. |
| B.3 | CLIs don't validate emitted artifact | Fixed | All three new CLI handlers (`quote-quality-report`, `cost-model-report`, `capacity-curve`) call `validate_quant_artifact` against the right schema before printing/writing. |
| B.4 | `generated_at_utc` non-deterministic | Fixed | Both `cost-model-report` and `capacity-curve` CLIs now pass `generated_at_utc` from inputs JSON if present. |
| B.5 | ReplaySlippageSummary read-model drops fields | Fixed | `web/readmodels.py` now reads `quote_quality_state`, `cost_evidence_class`, and `kind` with safe defaults. |
| B.6 | `fill_at_utc` empty string convention | Deferred — schema accepts string; convention documented in builder. Empty string paired with populated `non_fill_reason` indicates non-fill. |
| B.7 | Quality-status precedence loses signal | Deferred — booleans are persisted; `quality_status` reduces to single bucket. Precedence order chosen: stale → outage_adjacent → bad → degraded → good. |
| B.8 | Participation rate uses filled_qty | Deferred — partial fills can be reconstructed from `filled_qty / interval_volume`; capacity-curve report tracks turnover separately. |
| B.9 | `classify_cost_evidence` dead code drift | Deferred — used by tests today; promotion path uses `evaluate_cost_capacity_blockers`. Unifying these is a future refactor. |
| B.10 | `evidence_class` enum drift | Deferred — `wave5_cost_evidence` is a *classifier* label; the schema enum tracks the *report* status. The two are intentionally distinct. |
| B.11 | `arrival_timestamp_policy` doesn't force new `study_id` | Fixed | `build_trial_universe_manifest` now flags `arrival_timestamp_policy_changed_within_study` when two registrations share `study_id` but disagree on policy. New test in `tests/unit/test_experiments.py`. |

## Validation after fixes

- Wave 5 focused tests: 24 passed.
- Affected suite (`test_promotion`, `test_experiments`, `test_main`,
  `test_replay_slippage`, `test_blocker_registry`): all green.
- Full unit/contract/integration suite: 1071 passed, 98 skipped.
- `ruff check`: clean. `mypy src/tradingx`: clean.
- Touched-file Black check: clean.
