# Wave 7 Loop 2 Fix Report

| ID | Finding | Disposition | Resolution |
|---|---|---|---|
| H1 | Wave 7 codes synthetic in registry | Deferred (residual risk #1). |
| H2 | `tests/fixtures/short_side/` missing | Partially fixed — one happy-path fixture (`short_capability_manifest_complete.json`) committed; full per-blocker fixture set deferred to Wave 9 / Wave 10. |
| H3 | Empty-string ref bypass | Fixed | Evaluator now requires at least one non-empty `live_probe_evidence_refs` entry. |
| H4 | `paper_live_match_status="unverified"` slips through | Fixed | Both manifest and risk-report branches now treat `unverified` as `paper_live_short_semantics_mismatch`. |
| M1 | `_has_short_authority` permissiveness | Acknowledged — `evaluate_short_blockers` re-derivation provides defense-in-depth. |
| M2 | Map-value decimal-string format | Partial fix — scalar fields keep `decimal-string`; map-value enforcement rejected because canonical form (e.g. "1.0" → "1") would force builder canonicalization. |
| M3 | Broker-mode coupling | Fixed | Evaluator now treats `broker_mode in {"live","live_probe"}` as forcing `manifest_requires_probe=True` regardless of the self-asserted flag. |
| M4 | `locate_expiry_utc` empty-string | Deferred (residual risk #3). |
| L1-L4 | Minor | Documented. |

## Validation after fixes

- Wave 7 focused tests: 25 passed.
- Affected suite: passed.
- Full unit/contract/integration suite: 1130 passed, 98 skipped.
- `ruff check`: clean.
- `mypy src/tradingx`: clean.
- Touched-file Black: clean.
- `python3 scripts/check_index.py`: passed.
