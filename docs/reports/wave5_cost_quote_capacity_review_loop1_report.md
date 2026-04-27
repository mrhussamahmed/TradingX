# Wave 5 Adversarial Review — Loop 1

Two parallel adversarial reviewers were spawned with the smallest
practical context per the user-mandated review protocol.

## Reviewer A — blocker semantics, promotion-state caps

Top findings (paraphrased; see fix report for code references):

- **C1**: cost/capacity enforcement is not always-on at paper_trading+.
- **C2**: cost-model report becomes `promotion_valid=true` with zero
  observations.
- **H1**: legacy `replay_slippage_summary` classification dead because
  the on-disk JSON has no `kind` field.
- **H2 / M4**: evaluator trusts payload `blocker_codes` array without
  re-deriving from raw fields; a crafted payload can claim empty
  blockers despite mismatched fields.
- **M2**: `capacity_extrapolation_risk` boolean is set only on
  out-of-validated-range, not when target exceeds
  `lower_bound_capacity_limit`.
- **M3**: paper-only data with `impact_claim_requested=False` falls
  through to `_IMPACT_ALL_EVENTS`, mis-classifying paper-only.
- **L1, L2**: minor (CLI `or None` ambiguity; NaN guard on Decimals).

## Reviewer B — schemas, tests, replayability

Top findings:

- **1 (Critical)**: validator silently ignores
  `additionalProperties: {schema}` value-level constraints. Half of the
  Wave-5 schema surface is unenforced.
- **2 (Critical)**: `replay-slippage-report --include-quote-quality` is
  a hidden bypass — the flag toggles classification without checking
  underlying evidence.
- **3 (High)**: cost-model and capacity-curve CLIs do not validate the
  artifact they emit.
- **4 (High)**: `cost-model-report` and `capacity-curve` CLIs use
  `datetime.now(UTC)` as default — non-deterministic replay.
- **5 (High)**: `ReplaySlippageSummary` round-trip drops new wave-5
  fields when read from disk.
- **6 (Medium)**: `execution_cost_observation.fill_at_utc` accepts empty
  string for non-fills.
- **7 (Medium)**: `quote_quality_record` quality-status logic loses
  combined-flag signal.
- **8 (Medium)**: `participation_rate` computed from `filled_qty`
  understates partial-fill participation.
- **9 (Medium)**: `classify_cost_evidence` is dead code in production
  paths — drift risk vs inline check.
- **10 (Low)**: `evidence_class` enum doesn't include
  `wave5_cost_evidence`.
- **11 (Low)**: `arrival_timestamp_policy` change does not force a new
  `study_id`.

## Disposition

The coding agent treated each finding as a hypothesis. Findings A.C1
and B.2 surfaced design trade-offs that warrant discussion and were
re-examined in loop 2. All critical/high findings that translated to
code defects were fixed and re-tested before loop 2.

See `wave5_cost_quote_capacity_review_loop1_fix_report.md` for the
finding-by-finding disposition.
