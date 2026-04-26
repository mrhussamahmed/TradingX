# Wave 1 Implementation Report - Governance Spine First Slice

Wave name: Wave 1 - Governance Spine First Slice.

Roadmap requirements covered:

- Wave 1A: blocker registry, generated coverage rows, canonical JSON hashing, closed-world schema strategy, and filesystem content-addressed artifact storage.
- Wave 1B: append-only authority ledger, process-safe append lock, ledger reader validation, signature verification, trust roots, key scopes, revocation, validity bounds, and fixture-root rejection rules.
- Wave 1C: deterministic blocker evaluation, strictest state cap, state-action contract enforcement, `promotion-check` JSON output, `promotion-check --format summary`, and golden promotion fixtures.
- Wave 1D: activation refusal, projection-drift detection, deny-by-default order-route guard, long-only negative sleeve target rejection, and legacy non-authority web labeling.

Review packages:

- `docs/reports/wave1a_governance_spine_review_package.md`
- `docs/reports/wave1b_governance_spine_review_package.md`
- `docs/reports/wave1c_governance_spine_review_package.md`
- `docs/reports/wave1d_governance_spine_review_package.md`

Files changed:

- Added `src/tradingx/authority.py`.
- Added `src/tradingx/promotion.py`.
- Updated `src/tradingx/__main__.py`.
- Updated `src/tradingx/activation.py`.
- Updated `src/tradingx/execution.py`.
- Updated `src/tradingx/portfolio/live_construction.py`.
- Updated `src/tradingx/web/readmodels.py`.
- Added `schemas/quant/blocker_registry.schema.json`.
- Added `schemas/quant/promotion_manifest.schema.json`.
- Added `schemas/quant/trust_root.schema.json`.
- Added promotion fixtures under `tests/fixtures/promotion/`.
- Added `tests/unit/test_authority.py`.
- Added `tests/unit/test_blocker_registry.py`.
- Added `tests/unit/test_promotion.py`.
- Added `tests/unit/test_execution_authority.py`.
- Added `tests/integration/test_promotion_activation.py`.
- Updated `tests/unit/test_main.py`.
- Updated `tests/unit/test_portfolio_live_construction.py`.
- Updated `tests/unit/test_web_readmodels.py`.
- Added this report and Wave 1A through Wave 1D review package files under `docs/reports/`.

Tests added or updated:

- Authority tests for canonical hashing, content-addressed store verification, schema validation, ledger append/reader invariants, corrupt tail fail-closed behavior, and signature rejection.
- Blocker registry tests for required roadmap blockers and generated coverage completeness.
- Promotion tests for missing key policy, missing replay input, unsupported short side, paper-shadow fixture loading, projection drift, state-action contract rejection, missing projection authority, and fixture inventory.
- Execution authority tests for non-V5 legacy paper gateways and guarded route denial.
- Promotion activation integration tests for capped promotion refusal, projection-drift refusal, and default legacy compatibility.
- Portfolio construction test for negative sleeve targets failing before aggregation.
- CLI tests for JSON and human-readable `promotion-check` output.
- Web read model test for `legacy_non_authority` labeling.

Validation commands run:

- `uv run pytest tests/unit/test_main.py::test_promotion_check_summary_format_reports_state_and_blockers tests/unit/test_authority.py::test_schema_validator_rejects_version_drift_refs_and_bad_decimal_format tests/unit/test_authority.py::test_append_only_ledger_rejects_missing_artifact_approval_and_replay_refs tests/unit/test_authority.py::test_ledger_partial_tail_record_fails_closed tests/unit/test_promotion.py::test_wave1_golden_fixture_inventory_is_present`
- `uv run pytest tests/unit/test_authority.py::test_ledger_reader_rejects_stored_sequence_gap_and_payload_hash_mismatch`
- `uv run pytest tests/unit/test_authority.py tests/unit/test_blocker_registry.py tests/unit/test_promotion.py tests/unit/test_execution_authority.py tests/unit/test_portfolio_live_construction.py tests/integration/test_promotion_activation.py tests/unit/test_main.py::test_promotion_check_reports_blockers_from_fixture_artifacts tests/unit/test_main.py::test_promotion_check_summary_format_reports_state_and_blockers tests/unit/test_web_readmodels.py::test_local_web_read_model_builds_dashboard_from_artifacts_and_docs`
- `uv run ruff check .`
- `uv run mypy src/tradingx`
- `uv run pytest tests/unit tests/integration`

Validation results:

- New self-audit tests: 5 passed after fixes.
- Stored-ledger tamper test: 1 passed after reader invariant fix.
- Wave 1 targeted tests before adversarial review: 33 passed.
- Wave 1 targeted tests after round-1 fixes: 56 passed.
- Affected regression group after round-1 fixes: 152 passed.
- Focused tests after round-2 fixes: 65 passed.
- Affected regression group after round-2 fixes: 161 passed.
- Ruff: all checks passed.
- Mypy: success, no issues in 110 source files.
- Full unit and integration suite before adversarial review: 908 passed, 98 skipped, 2 warnings in 290.34 seconds.
- Full unit and integration suite after round-1 fixes: 922 passed, 98 skipped, 2 warnings in 302.38 seconds.
- Full unit and integration suite after round-2 fixes: 931 passed, 98 skipped, 2 warnings in 318.14 seconds.

Failures found and fixed:

- Red tests initially failed because authority and promotion modules did not exist.
- `tests/unit/test_execution_authority.py` initially imported another test module through `tests.*`; it was made self-contained.
- Negative sleeve target test initially omitted required `SleeveTrade` fields; the test fixture was corrected.
- Ruff found import ordering, long-line, `StrEnum`, and encoding cleanup issues; all were fixed.
- Mypy found authority JSON typing gaps and `__main__.py` local variable type collisions; all were fixed.
- Self-audit red tests found missing `promotion-check --format summary`, missing decimal-string format enforcement, missing ledger artifact/approval ref checks, and missing Wave 1 golden fixture directories; all were fixed.
- A stored-ledger tamper red test found the ledger reader did not validate sequence and payload-hash invariants after recomputing ledger hashes; `_read_records` now validates stored chain invariants and refs.

Assumptions made:

- The roadmap allows the no-new-dependency path for schema validation, so Wave 1 uses a closed-world typed-artifact validator with explicit supported keywords and formats.
- Default activation remains legacy-compatible when no promotion decision provider is configured; configured V5 promotion enforcement fails closed.
- Wave 1 does not grant production/live authority. Full live-probe authority tokens remain deferred to the roadmap's later live-probe wave.

Unresolved risks:

- The first-slice promotion evaluator covers the Wave 1 fixture/blocker surface and is intentionally conservative; later waves still need richer evidence ingestion.
- Signature verification uses local fixture-compatible HMAC references for deterministic tests; production key custody and live authority token flows remain future-wave work.

Commit hash:

- Not committed yet. Wave 1 will be committed after fresh adversarial review and required fixes.
