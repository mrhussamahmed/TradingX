# Wave 7 Adversarial Review — Loop 1 (Combined A + B)

A single combined adversarial reviewer ran both lenses (blocker
semantics + schemas/tests) in one pass.

## Top findings (paraphrased)

- **A1 (High)**: New `short_capability_manifest` cannot unlock negative
  weights — gate keys on the obsolete `short_capability_package` kind.
- **A2 (High)**: `live_probe_short_evidence_missing` only fires from
  inside `short_risk_report` branch; manifest demands not enforced
  cross-bundle.
- **B1 (High)**: numeric-string fields (`borrow_rate_bps`, financing
  bps fields, `exposure_caps`) lack `format: "decimal-string"`.
- **B2 (High)**: `locate_expiry_utc` empty-string is a schema escape
  hatch.
- **A3 (High)**: case sensitivity — schema enums are case-sensitive but
  evaluator uses `_normal_form`.
- **A4 (High)**: scrubbing tests cover only 3 of 7 new codes.
- **B3 (High)**: registry seeds for new codes default to
  `legacy_inventory`/`NOT_RUNTIME_APPLICABLE`; no `tests/fixtures/short_side/`.
- **B4 (Medium)**: `paper_live_short_semantics_mismatch` cap rationale.
- **A5, A6, B5, B6 (Medium)**: minor.

## Disposition

See `wave7_short_side_financing_review_loop1_fix_report.md`.
