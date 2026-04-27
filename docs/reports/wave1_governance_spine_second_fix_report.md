# Wave 1 Round 2 Fix Report - Governance Spine First Slice

Review report fixed:

- `docs/reports/wave1_governance_spine_rereview_report.md`

Findings fixed:

- `W1-R2-001`: blocker coverage no longer accepts fabricated references. Registry rows now use explicit `not_runtime_applicable` markers or validated references to evaluator functions, red tests, fixtures, CLI fields, web/report fields, and runtime enforcement points. Coverage scans `src`, `tests`, `schemas`, `config`, `docs/roadmap`, and `docs/reports` for blocker emissions.
- `W1-R2-002`: authority path now validates promotion manifests, trust roots, ledger records, promotion-decision payloads, content-addressed artifacts, approval records, ledger key policy artifacts, and state-action contract artifacts against checked-in quant schemas before they can affect a decision. Promotion fixtures were regenerated as schema-valid authority bundles.
- `W1-R2-003`: state-action contract artifacts are now part of the promotion authority bundle. Promotion decisions without a valid contract receive `state_action_contract_missing`; activation and order-route guards validate contracts before allowing use.
- `W1-R2-004`: approval records now require operator identity, role registry ref, authority boundary ref, risk acceptance, signed timestamp, and expiry. Promotion and ledger verification bind required scope to `promotion_decision` independent of the approval payload and reject expired approvals.
- `W1-R2-005`: `promotion-check` now resolves default per-strategy artifacts from `config/strategy/promotion`, fails closed on strategy-id mismatch, and the default `trend-following-v1` artifact bundle returns a `research_only` decision with `utility_definition_missing` and `instrument_package_missing`.
- `W1-R2-006`: activation and order-route refusal messages now include blocker codes and safe artifact refs for reproducible operator diagnosis.
- `W1-R2-007`: dashboard snapshots now expose `gate_authority_statuses` and `recommendation_authority_statuses` next to raw legacy values, and Gate 3 operator action text is explicitly non-authority.

Tests added or updated:

- Registry tests for missing evaluator, missing red test, missing CLI output, missing fixture, and discovered unregistered blocker codes.
- Fixture-wide schema validation for promotion manifests, trust roots, ledger records, CAS payloads, approval records, and state-action contracts.
- Promotion tests for wrong-scope approval, expired approval, missing state-action contract, default CLI research blockers, and wrong-strategy artifact mismatch.
- Activation tests for malformed state-action contracts and successful activation with valid contracts.
- Order-route tests for invalid state-action contracts and refusal messages with safe artifact refs.
- Web/read-model tests for direct authority classifications next to gate statuses and recommendations.

Validation commands run:

- `.venv/bin/python -m pytest tests/unit/test_authority.py tests/unit/test_blocker_registry.py tests/unit/test_promotion.py tests/unit/test_execution_authority.py tests/integration/test_promotion_activation.py tests/unit/test_main.py::test_promotion_check_reports_blockers_from_fixture_artifacts tests/unit/test_main.py::test_promotion_check_summary_format_reports_state_and_blockers tests/unit/test_main.py::test_promotion_check_default_artifact_root_reports_research_blockers tests/unit/test_main.py::test_promotion_check_wrong_strategy_artifact_fails_closed tests/unit/test_web_readmodels.py::test_local_web_read_model_builds_dashboard_from_artifacts_and_docs tests/unit/test_gate3.py tests/unit/test_reporting.py`
- `.venv/bin/python -m ruff check .`
- `.venv/bin/python -m mypy src/tradingx`
- `.venv/bin/python -m pytest tests/unit/test_authority.py tests/unit/test_blocker_registry.py tests/unit/test_promotion.py tests/unit/test_execution_authority.py tests/unit/test_execution.py tests/unit/test_activation.py tests/unit/test_activation_snapshot_payloads.py tests/unit/test_blueprint_activation_gateway.py tests/integration/test_promotion_activation.py tests/unit/test_main.py tests/unit/test_service.py tests/unit/test_web_runtime.py tests/unit/test_web_readmodels.py tests/unit/test_gate3.py tests/unit/test_reporting.py tests/integration/test_fallback_drill.py tests/unit/test_drift_artifact_regeneration.py`
- `.venv/bin/python -m pytest tests/unit tests/integration`

Validation results:

- Focused round-2 fix suite: 65 passed.
- Ruff: all checks passed.
- Mypy: success, no issues in 110 source files.
- Affected regression group: 161 passed.
- Full unit and integration suite: 931 passed, 98 skipped, 2 warnings in 318.14 seconds.

Unresolved risks:

- The state-action contract is now enforced locally, but later waves still need richer production role/custody workflows and live-probe action tokens.
- The default `config/strategy/promotion/trend-following-v1` bundle is intentionally blocked at `research_only`; it is not production authority.

