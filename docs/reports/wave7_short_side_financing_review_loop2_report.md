# Wave 7 Adversarial Review — Loop 2

A fresh reviewer was spawned with minimal context after loop-1 fixes.

## Top findings (paraphrased)

- **H1**: New wave_7 codes still default to `legacy_inventory` /
  `NOT_RUNTIME_APPLICABLE` in registry coverage matrix.
- **H2**: `tests/fixtures/short_side/` directory does not exist.
- **H3**: Empty-string ref in `live_probe_evidence_refs` counts as
  non-empty.
- **H4**: `paper_live_match_status="unverified"` slips through with no
  cap.
- **M1**: `_has_short_authority` is permissive (doesn't re-derive
  manifest blockers).
- **M2**: `borrow_fee_curve` and `exposure_caps` map values lack
  decimal-string format.
- **M3**: `live_probe_required` should be coupled to `broker_mode`.
- **M4**: `locate_expiry_utc` empty-string oversight.

## Disposition

- **Fixed**: H3 (empty-ref check), H4 (`unverified` now blocks via
  `paper_live_short_semantics_mismatch`), M3 (broker_mode triggers
  `manifest_requires_probe`).
- **Partially fixed**: M2 — scalar bps fields keep decimal-string;
  map-value format requires canonical decimals (rejected because
  builders don't currently produce canonical form, e.g. "1.0").
- **Deferred / residual**: H1, H2 (tracker entry: Wave 9), M1 (gate
  permissiveness — re-derivation continues at evaluator), M4
  (locate_expiry empty-string).
- **One fixture committed**: `short_capability_manifest_complete.json`.

A truly clean reviewer session was not available; reviewer was
spawned with minimal context.
