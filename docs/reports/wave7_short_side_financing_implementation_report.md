# Wave 7 Short-Side Capability And Financing — Implementation Report

Last updated: 2026-04-26

## Goal

Implement Milestone 8 so negative weights cannot masquerade as
executable shorts.

## Files changed

Source:

- `src/tradingx/short_governance.py` (new) — builders for
  `short_capability_manifest`, `borrow_availability_snapshot`,
  `short_financing_model`, `short_risk_report`, `short_runtime_event`.
- `src/tradingx/promotion.py` — `evaluate_short_blockers`, new blocker
  codes, `_has_short_authority` helper that recognises the new manifest
  kind, and the artifact kinds added to `_validate_cas_payload`.

Schemas (new):

- `short_capability_manifest.schema.json`
- `borrow_availability_snapshot.schema.json`
- `short_financing_model.schema.json`
- `short_risk_report.schema.json`
- `short_runtime_event.schema.json`

Tests:

- `tests/unit/test_short_governance_wave7.py` — 25 tests covering all
  six required Wave 7 red tests plus evaluator re-derivation paths and
  the broker-initiated cover reconciliation rule.

Fixture:

- `tests/fixtures/short_side/short_capability_manifest_complete.json`

## Required red tests

| Roadmap red test | Implementation |
|---|---|
| Negative target without manifest is blocked | `test_negative_target_without_manifest_is_blocked` |
| Stale borrow snapshot blocks new shorts | `test_stale_borrow_snapshot_blocks_new_shorts` |
| Missing locate documentation blocks new shorts | `test_missing_locate_documentation_blocks_new_shorts` |
| Threshold-security policy missing yields `short_legal_mechanics_missing` | `test_threshold_security_policy_missing_yields_short_legal_mechanics` |
| Paper/live short semantics mismatch prevents production | `test_paper_live_short_semantics_mismatch_prevents_production` |
| Historical short backtest without borrow path is research-only | `test_historical_short_backtest_without_borrow_path_is_research_only` |

## Adversarial reviews

Two loops were run.

- Loop 1 (combined Reviewer A and B): all critical/high findings
  fixed, including: `_has_short_authority` recognising the manifest
  kind, live-probe enforcement when manifest demands it, decimal-string
  formats on numeric scalar fields, missing scrubbing tests.
- Loop 2 (fresh reviewer): registry override metadata for new wave_7
  codes deferred (residual risk #1 below); H3 (empty-string ref bypass)
  and H4 (unverified status) fixed; M2 partial (scalar fields only —
  map-value normalization caused canonical-decimal regressions and was
  reverted); M3 (broker_mode → live_probe_required coupling) fixed;
  M4 (locate_expiry_utc empty-string oversight) deferred.

## Validation

- Wave 7 focused tests: 25 passed.
- Affected suite (promotion, blocker_registry): passed.
- Full unit/contract/integration suite: 1130 passed, 98 skipped.
- `ruff check`, `mypy`, touched-file Black: clean.
- `python3 scripts/check_index.py`: passed.

## Accepted residual risks

1. **Wave 7 registry seeds use synthetic coverage.** The new blocker
   codes (`borrow_snapshot_stale`, `locate_documentation_missing`,
   `locate_expired`, `paper_live_short_semantics_mismatch`,
   `live_probe_short_evidence_missing`,
   `broker_initiated_cover_unreconciled`, `legacy_short_evidence`) live
   in `_REGISTRY_SEEDS` but do not have wave_7 override entries with
   real fixture/red_test/evaluator pointers. The registry coverage
   matrix reports them as `legacy_inventory` with synthetic fields.
   Wave 9 (Recertification And Change Control) is the natural place to
   fold these into the override loop.
2. **`tests/fixtures/short_side/` has only one fixture.** A complete
   set of failing fixtures (one per blocker code) is deferred to Wave 9
   /  Wave 10.
3. **`locate_expiry_utc` empty-string convention.** When `locate_status
   == "active"`, the schema accepts empty `locate_expiry_utc`. The
   evaluator does not cross-check expiry against `now()`. Future
   hardening.
4. **Map-value `format: "decimal-string"` not enforced.** The custom
   validator's canonical-decimal check is strict (e.g. `"1.0"` is not
   canonical). `borrow_fee_curve` and `exposure_caps` map values stay
   as plain strings to avoid forcing builders to canonicalize.
5. **No CLI subcommands.** `short-capability-check`, `borrow-snapshot`,
   `short-risk-report` are deferred. Builders and evaluator paths are
   ready; CLI handlers are mechanical wiring.
6. **Runtime wiring of the manifest into `risk.py`/`execution.py`/
   `runtime_portfolio.py`.** Roadmap §1459-1470 lists these files in
   write scope. Wave 7 implements the artifact authority surface; the
   live runtime checks (sell-short intent → manifest+borrow snapshot
   lookup) are deferred to Wave 8 (Live Probe And Operational Safety).
7. **`./scripts/validate` Black drift.** Unchanged from prior waves.

## Commit

```
TradingX quant hardening: complete Wave 7 - Short-Side Capability And Financing
```
