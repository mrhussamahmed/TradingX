# TradingX Quant Hardening — Final Integrated Review

Last updated: 2026-04-26

## Scope

Final integrated review of `codex/tradingx-quant-hardening` covering
Waves 0–10. Confirms cross-wave consistency and documents merge
readiness.

## Cross-wave evaluator pipeline

`_evaluate_verified_decision_blockers` in `src/tradingx/promotion.py`
chains, in order:

1. First-slice required-artifact checks
2. Mandate authority blockers (Wave 2)
3. Ledger / state-action contract / replay path checks (Wave 1)
4. `evaluate_provenance_blockers` (Wave 3)
5. `evaluate_statistical_evidence_blockers` (Wave 4)
6. `evaluate_cost_capacity_blockers` (Wave 5)
7. `evaluate_portfolio_optimizer_blockers` (Wave 6)
8. `evaluate_forecast_sizing_blockers` (Wave 6)
9. `evaluate_short_blockers` (Wave 7)
10. `evaluate_live_probe_blockers` (Wave 8)
11. `evaluate_change_control_blockers` (Wave 9)
12. Negative-weight short-authority gate (Wave 1 + Wave 7)
13. Decision-payload-asserted blocker codes

Each evaluator re-derives critical blockers from raw fields. A payload
asserting `blocker_codes=[]` cannot bypass enforcement.

## Cross-wave artifact validation

`_validate_cas_payload` recognizes and schema-validates every Wave-3
through Wave-10 artifact kind. Custom validator was extended in Wave 5
to enforce nested `additionalProperties` value subschemas, which in
turn protected Wave 6/7/8/9/10 schemas with map-typed properties.

## Cross-wave amendments

- `experiment_registration` schema (Wave 3) gained `arrival_timestamp_policy`
  in Wave 5 and `forecast_model_hash` / `feature_manifest_hash` /
  `sizing_policy_hash` in Wave 6. The `_registration` test helper and
  the existing fixture were updated in those waves.
- `ReplaySlippageSummary` dataclass gained `kind`, `quote_quality_state`,
  and `cost_evidence_class` fields in Wave 5. The web read-model
  round-trips them.
- `BLOCKER_REGISTRY` `_REGISTRY_SEEDS` grew across waves; new codes
  for Waves 5–10 retain `legacy_inventory` owning-wave metadata
  (documented residual risk).

## Test counts trajectory

- End of Wave 4: 1064 passed.
- End of Wave 5: 1071 passed.
- End of Wave 6: 1105 passed.
- End of Wave 7: 1130 passed.
- End of Wave 8: 1151 passed.
- End of Wave 9: 1169 passed.
- End of Wave 10: 1178 passed.

98 tests skipped throughout (existing skips, not introduced by Waves
5–10).

## Static analysis

- `ruff check .` clean across all 11 waves.
- `mypy src/tradingx` clean (118 source files at end of Wave 10).
- Touched-file Black checks clean per wave.
- `python3 scripts/check_index.py` clean.

## Known unresolved items

See `tradingx_quant_hardening_final_summary.md` "Accepted residual
risks" and "Final recommended next steps". The most consequential
items: passive-evaluator design, runtime wiring of the new evidence
kinds, deferred Wave 8 runtime red tests, CLI subcommand wiring,
registry override metadata for new wave-5+ codes.

## Adversarial review caveat

Loop-1 and loop-2 adversarial reviews ran for every wave 5–10. For
Wave 9 and Wave 10, context-budget constraints required collapsing
the two loops into a single combined adversarial pass that explicitly
ran both lenses. This is documented in the per-wave fix reports.
A truly clean reviewer session was not available — sub-agents share
the underlying model harness.

## Merge readiness

The branch is local, validated, and self-consistent. All waves are
committed. The branch is **ready for human review** prior to merge,
with the residual-risk list explicitly captured in the final summary.

The orchestrator did not push to a remote and did not merge into
`main`/`master`, per the working-instructions in
`tradingx_quant_hardening_handover.md`.
