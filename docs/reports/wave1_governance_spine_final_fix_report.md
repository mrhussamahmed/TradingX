# Wave 1 Governance Spine Final Fix Report

Wave: Wave 1 - Governance Spine First Slice

Review source: `docs/reports/wave1_governance_spine_final_review_report.md`

Review cap status: the user capped review loops at three iterations per wave. The third Wave 1 review produced findings, so this report records deterministic fixes and validation. No fourth Wave 1 reviewer was spawned.

## Findings Fixed

- `W1-R3-001`: Promotion evaluation now recomputes first-slice blockers from artifacts, independent of the ledger payload's declared `blocker_codes`. The evaluator requires capability, promotion evidence, placeholder mandate, benchmark, wealth-thesis, utility, allocation, tax/account, jurisdiction/account-use, instrument-package, key policy, retained replay, approval, and state-action contract artifacts before `paper_shadow` can be reached.
- `W1-R3-002`: Fixture trust roots are accepted only under `tests/fixtures`. The checked-in default `config/strategy/promotion/trend-following-v1` bundle now uses a non-fixture `hmac:` signature and `fixture_root: false`.
- `W1-R3-003`: Registry validation rejects synthetic `not_runtime_applicable` coverage for emitted blockers. Real evaluator, red test, fixture, CLI, web/report, and runtime mappings were added for emitted Wave 1 blocker codes including `utility_definition_missing`, `instrument_package_missing`, `tax_account_financing_unspecified`, `jurisdiction_account_use_unknown`, and `state_action_contract_missing`.
- `W1-R3-004`: State-action contracts now model and validate data access, broker access, order permission, capital ceiling, short permission, required runtime controls, route constraints, and disallowed actions for every promotion state. Activation and order-route guards consume the validated contract from the promotion decision unless a test explicitly injects one.
- `W1-R3-005`: Verified ledger reads now schema-validate approval records and enforce `signed_at_utc`, UTC timestamp validity, signed-before-expiry, trust-root validity bounds, and no future signed timestamp relative to verification time.

## Files Changed

- `src/tradingx/authority.py`
- `src/tradingx/promotion.py`
- `src/tradingx/activation.py`
- `src/tradingx/execution.py`
- `schemas/quant/content_addressed_artifact.schema.json`
- `schemas/quant/promotion_evidence.schema.json`
- `schemas/quant/state_action_contract.schema.json`
- `schemas/quant/strategy_capability_manifest.schema.json`
- `config/strategy/capabilities/trend-following-v1.json`
- `config/strategy/promotion/trend-following-v1/**`
- `tests/fixtures/promotion/**`
- `tests/unit/test_authority.py`
- `tests/unit/test_blocker_registry.py`
- `tests/unit/test_execution_authority.py`
- `tests/unit/test_main.py`
- `tests/unit/test_promotion.py`
- `tests/integration/test_promotion_activation.py`

## Tests Added Or Updated

- Added artifact-derived blocker tests for missing first-slice evidence.
- Added fixture-signature path-scope tests.
- Added registry tests proving emitted blockers cannot use synthetic coverage.
- Added state-action contract semantic and route-constraint tests.
- Added approval `signed_at_utc` negative tests for missing, non-UTC, after-expiry, outside trust-root validity, and future signed timestamps.

## Validation Commands Run

- `.venv/bin/python -m pytest tests/unit/test_promotion.py::test_missing_first_slice_evidence_recomputes_blockers_from_artifacts tests/unit/test_promotion.py::test_fixture_signature_outside_test_fixture_root_fails_closed tests/unit/test_promotion.py::test_state_action_contract_requires_roadmap_runtime_semantics tests/unit/test_blocker_registry.py::test_registry_coverage_rejects_not_runtime_for_emitted_blocker_fields tests/unit/test_execution_authority.py::test_order_route_guard_rejects_disallowed_contract_route tests/unit/test_authority.py::test_verified_ledger_read_rejects_invalid_approval_signed_at`
- `.venv/bin/python -m pytest tests/unit/test_promotion.py tests/unit/test_main.py::test_promotion_check_default_artifact_root_reports_research_blockers tests/unit/test_main.py::test_promotion_check_summary_format_reports_state_and_blockers tests/unit/test_main.py::test_promotion_check_reports_blockers_from_fixture_artifacts tests/unit/test_blocker_registry.py`
- `.venv/bin/python -m pytest tests/unit/test_authority.py tests/unit/test_activation.py tests/unit/test_activation_snapshot_payloads.py tests/unit/test_blueprint_activation_gateway.py tests/unit/test_execution_authority.py tests/unit/test_execution.py tests/integration/test_promotion_activation.py tests/unit/test_service.py tests/unit/test_web_runtime.py tests/unit/test_main.py`
- `.venv/bin/python -m pytest tests/unit/test_authority.py tests/unit/test_promotion.py tests/unit/test_blocker_registry.py tests/unit/test_activation.py tests/unit/test_activation_snapshot_payloads.py tests/unit/test_blueprint_activation_gateway.py tests/unit/test_drift_artifact_regeneration.py tests/unit/test_execution.py tests/unit/test_execution_authority.py tests/unit/test_main.py tests/unit/test_portfolio_live_construction.py tests/unit/test_reporting.py tests/unit/test_service.py tests/unit/test_web_readmodels.py tests/unit/test_web_runtime.py tests/integration/test_fallback_drill.py tests/integration/test_promotion_activation.py`
- `.venv/bin/python -m ruff check .`
- `.venv/bin/python -m mypy src/tradingx`
- `.venv/bin/python -m pytest tests/unit tests/integration`

## Validation Results

- Focused third-review red tests: failed before production fixes, then passed.
- Promotion/CLI/registry focused suite: `29 passed`.
- Activation/execution/authority/web-runtime focused suite: `115 passed`.
- Wave 1 regression slice: `166 passed`.
- Ruff: all checks passed.
- Mypy: success, no issues in 110 source files.
- Full unit/integration suite: `941 passed, 98 skipped, 2 warnings in 292.95s`.

Warnings were the existing `httpx` deprecation warnings from `tests/unit/test_web_app.py`.

## Failures Found And Fixed

- The first focused run failed 9 expected red cases, proving the tests caught missing behavior.
- Schema and fixture updates initially exposed outdated canonical sample tests and CLI blocker expectations; these were updated to the stricter artifact-derived blocker semantics.
- Ruff found line-length/import-order issues after the production fixes; these were corrected.

## Assumptions Made

- `hmac:` signatures are valid non-fixture local signatures for Wave 1's filesystem-only authority bundle because `verify_approval_signature` verifies their digest against an explicit trust root.
- First-slice placeholder artifacts may support `paper_shadow` only when they are signed, content-addressed, ledger-referenced, strategy-scoped, and descriptive.
- `config/strategy/promotion/trend-following-v1` remains a local default diagnostic authority bundle capped by missing first-slice artifacts at `research_only`.

## Unresolved Risks

- No unresolved Wave 1 review findings remain unaddressed in code/tests, but there was no fourth reviewer because of the user-imposed review-loop cap.

## Commit Hash

Pending at report creation time; this report is included in the Wave 1 local commit.
