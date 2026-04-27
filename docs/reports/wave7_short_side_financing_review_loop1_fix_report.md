# Wave 7 Loop 1 Fix Report

| ID | Finding | Disposition | Resolution |
|---|---|---|---|
| A1 | Manifest cannot unlock negative weights | Fixed | Added `_has_short_authority` helper that recognises both legacy `short_capability_package` and the new `short_capability_manifest` (with `short_runtime_supported=True`). |
| A2 | Live-probe enforcement misfires when no risk report exists | Fixed | Evaluator now tracks `manifest_requires_probe`; if a manifest demands probe and no risk report carries non-empty refs, `live_probe_short_evidence_missing` fires. |
| B1 | Decimal-string formats missing | Partial | Scalar bps fields on `borrow_availability_snapshot` and `short_financing_model` got `format: "decimal-string"`. Map-value normalization (`borrow_fee_curve`, `exposure_caps`) was reverted in loop 2 because the custom validator's canonical check rejects non-canonical strings (e.g. "1.0"). |
| B2 | `locate_expiry_utc` empty-string escape hatch | Deferred (residual risk #3). |
| A3 | Case sensitivity drift | Acknowledged — schema enum rejects mismatched case first; evaluator's `_normal_form` provides defense-in-depth. |
| A4 | Scrubbing tests | Fixed | Added evaluator-path scrubbing tests for `paper_live_short_semantics_mismatch`, `legacy_short_evidence`, `live_probe_short_evidence_missing`, `locate_documentation_missing`, `short_legal_mechanics_missing`, `broker_initiated_cover_unreconciled`. |
| B3 | Registry seeds owning_wave + fixtures | Deferred (residual risk #1). |
| B4 | `paper_live_short_semantics_mismatch` cap | Acknowledged — cap of `paper_shadow` is consistent with roadmap. |
| A5, A6, B5, B6 | Minor | Documented or deferred. |

## Validation after fixes

Before loop 2:

- Wave 7 focused tests: 19 passed.
- Affected suite: passed.
- Full suite: 1124 passed.
- ruff/mypy/black: clean.
