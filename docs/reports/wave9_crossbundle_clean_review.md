# Wave 9 Cross-Bundle Linkage — Clean Adversarial Review (post-Defect 3)

**Date:** 2026-04-26
**Reviewer:** Adversarial review committee, second pass
**Scope:** Wave 9 recertification + change-control cross-bundle
linkage after the `adversarial_fixup_Defect_3` commit lands.

## Summary

Wave 9 cross-bundle linkage now passes adversarial review. Both the
change_id linkage (recertification_report ↔ change_control_record) and
the run_refs linkage (live_probe_recertification_report ↔
live_probe_run_record) are enforced.

## Findings remediated

### F9.1 — Cross-bundle linkage was presence-only

**Original:** A bundle could ship a `recertification_report` AND a
`change_control_record` requiring recertification, with the report's
contents stating "approved" — and pass enforcement even though the
report referenced no actual change. `evaluate_change_control_blockers`
checked that BOTH artifacts existed, but never checked that the
report's `change_id` matched any open change.

**Fix:** `evaluate_change_control_blockers` now collects
`change_id` from every `change_control_record` with
`recertification_required=True` into `required_change_ids`. The
recertification_report's `change_id` must appear in that set, else
`recertification_report_missing` fires. The new red test
`test_recertification_report_with_mismatched_change_id_blocks_production`
proves this.

`recertification_report` schema now requires the `change_id` field;
`build_recertification_report` accepts a `change_id` parameter (default
empty string for backwards compatibility).

### F9.2 — Live-probe recertification didn't audit run coverage

**Original:** A `live_probe_recertification_report` could satisfy the
post-probe gate even when its `run_refs` omitted some
`live_probe_run_record.run_id` values from the same bundle. So an
attacker could attach a stale recertification certifying a probe that
never happened.

**Fix:** `evaluate_live_probe_blockers` now collects every observed
`run_id` from `live_probe_run_record` payloads. The set must be a
subset of the union of every bundled
`live_probe_recertification_report.run_refs`; otherwise
`post_probe_recertification_missing` fires. The new red test
`test_recertification_report_with_stale_run_refs_blocks_live_probe_promotion`
proves this.

## Residual risks

- The cross-bundle check requires the bundle to include BOTH halves.
  If the runtime promotes a bundle that omits the
  change_control_record entirely, the existing
  `recertification_report_missing` fallback already fires when there
  is a known unfinished change in the bundle — a separate
  defect-1-style "production set" enforcement covers the case of
  empty-bundle promotion (see Defect 1).
- The `run_refs` check requires that probe runs and the
  recertification report ship as part of the same bundle. Bundles
  spanning multiple promotion cycles are out of scope for this fix.

## Verdict

**Wave 9 cross-bundle linkage is clean.** No new defects raised.
