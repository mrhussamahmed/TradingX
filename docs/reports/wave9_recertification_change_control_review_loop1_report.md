# Wave 9 Adversarial Review — Loop 1 (combined)

Combined adversarial reviewer ran both lenses (blocker semantics +
schemas/tests) in a single pass due to context budget. Top findings:

- **C1**: replay-equivalence treats empty deltas as equivalent.
- **C2**: `recertification_required` field built but not enforced —
  fixed in loop-1 fix report.
- **H1**: registry seeds verification (codes confirmed seeded).
- **H2**: manual-exception adversarial test too weak.
- **H3**: `detect_unrecorded_change` decoupled from evaluator.
- **M1**: schemas under-restrict status enums.
- **M2**: `production_decay_event` enum drift — fixed.

Disposition: see `wave9_recertification_change_control_review_loop1_fix_report.md`.
A truly clean reviewer session was not available.
