# Wave 2 Mandate And Allocation Governance Implementation Report

Wave name: Wave 2 - Mandate And Allocation Governance

Roadmap requirements covered:

- Added authority-bearing Milestone 0 artifact schemas for investment mandate, benchmark policy, jurisdiction/account-use manifest, instrument support package, strategy capital role, wealth thesis, capital allocation policy, lower-bound net edge spec, and strategy materiality policy.
- Promotion evaluation now requires signed authority-metadata-bearing mandate artifacts outside test fixture roots and recomputes mandate blockers from retained CAS artifacts.
- Capital-bearing promotion is blocked without an investment mandate, benchmark policy, capital role, wealth thesis, allocation policy, lower-bound net edge spec, jurisdiction/account-use manifest, instrument support package, and materiality policy.
- Tax/modeling, jurisdiction/account-use, external-capital/advice compliance, simple-equity instrument support, and materiality blockers are emitted separately from statistical blockers.
- CLI JSON and summary output now include mandate/statistical/authority blocker groupings.
- Existing activation records and approved weight snapshots are classified as legacy non-authority artifacts through an explicit migration helper.
- Test-only fixture authority markers in approval identity, role registry, or authority boundary refs are rejected outside fixture roots.
- Opportunity-cost reports remain diagnostic and cannot override mandate blockers.

Files changed:

- `src/tradingx/promotion.py`
- `src/tradingx/__main__.py`
- `src/tradingx/reporting.py`
- `schemas/quant/investment_mandate.schema.json`
- `schemas/quant/benchmark_policy.schema.json`
- `schemas/quant/jurisdiction_account_use_manifest.schema.json`
- `schemas/quant/instrument_support_package.schema.json`
- `schemas/quant/strategy_capital_role.schema.json`
- `schemas/quant/wealth_thesis.schema.json`
- `schemas/quant/capital_allocation_policy.schema.json`
- `schemas/quant/lower_bound_net_edge_spec.schema.json`
- `schemas/quant/strategy_materiality_policy.schema.json`
- `tests/fixtures/mandate/valid/README.md`
- `tests/fixtures/mandate/external_capital_unknown/README.md`
- `tests/fixtures/mandate/materiality_policy_missing/README.md`
- `tests/unit/test_promotion.py`
- `tests/unit/test_main.py`
- `tests/unit/test_reporting.py`

Tests added or updated:

- Promotion tests for missing investment mandate, tax/account financing unspecified, unknown jurisdiction/account use, unknown external-capital compliance, missing simple-equity instrument support package, missing strategy materiality policy, opportunity-cost non-override, fixture role registry refusal outside fixture roots, blocker category JSON, legacy operator artifact classification, and Wave 2 schema validation.
- CLI tests for mandate/statistical blocker output in JSON and summary formats.
- Reporting test for promotion blocker report grouping.

Validation commands run:

- `.venv/bin/python -m pytest tests/unit/test_promotion.py::test_missing_investment_mandate_blocks_capital_bearing_promotion tests/unit/test_promotion.py::test_tax_account_financing_unspecified_caps_at_paper_shadow tests/unit/test_promotion.py::test_unknown_jurisdiction_or_account_use_caps_live_at_paper_trading tests/unit/test_promotion.py::test_external_capital_unknown_disables_promotion tests/unit/test_promotion.py::test_missing_simple_equity_instrument_support_package_blocks_promotion tests/unit/test_promotion.py::test_opportunity_cost_report_cannot_override_mandate_blocker tests/unit/test_promotion.py::test_fixture_role_registry_ref_outside_fixture_root_fails_closed tests/unit/test_promotion.py::test_promotion_decision_json_separates_mandate_and_statistical_blockers tests/unit/test_promotion.py::test_legacy_operator_artifacts_are_classified_non_v5_authority tests/unit/test_promotion.py::test_wave2_mandate_schemas_validate_minimal_authority_artifacts tests/unit/test_main.py::test_promotion_check_summary_format_reports_state_and_blockers tests/unit/test_main.py::test_promotion_check_default_artifact_root_reports_research_blockers`
- `.venv/bin/python -m pytest tests/unit/test_promotion.py tests/unit/test_blocker_registry.py tests/unit/test_main.py tests/unit/test_reporting.py tests/unit/test_blueprint_activation_gateway.py tests/unit/test_portfolio_live_construction.py`
- `.venv/bin/python -m ruff check src/tradingx/promotion.py src/tradingx/__main__.py src/tradingx/reporting.py tests/unit/test_promotion.py tests/unit/test_main.py tests/unit/test_reporting.py`
- `.venv/bin/python -m mypy src/tradingx`
- `.venv/bin/python -m pytest tests/unit/test_authority.py tests/unit/test_activation.py tests/unit/test_activation_snapshot_payloads.py tests/unit/test_blueprint_activation_gateway.py tests/unit/test_execution_authority.py tests/unit/test_execution.py tests/integration/test_promotion_activation.py tests/unit/test_service.py tests/unit/test_web_runtime.py tests/unit/test_main.py tests/unit/test_reporting.py tests/unit/test_promotion.py tests/unit/test_blocker_registry.py`
- `.venv/bin/python -m tradingx promotion-check --strategy-id trend-following-v1 --format json`
- `.venv/bin/python -m ruff check .`
- `.venv/bin/python -m mypy src/tradingx`
- `.venv/bin/python -m pytest tests/unit tests/integration`

Validation results:

- Focused Wave 2 red suite initially failed before implementation with missing schema files, missing classification helper, missing mandate/statistical CLI fields, and missing mandate blocker semantics.
- Focused Wave 2 suite passed after implementation: `13 passed`.
- Promotion/blocker/CLI/reporting/portfolio-adjacent regression passed: `91 passed`.
- Activation/execution/authority/web-runtime regression slice passed: `157 passed`.
- `promotion-check` default strategy output reports max state `research_only` with mandate blockers `utility_definition_missing`, `tax_account_financing_unspecified`, `jurisdiction_account_use_unknown`, `instrument_package_missing`, and `strategy_materiality_policy_missing`.
- `.venv/bin/python -m ruff check .` passed.
- `.venv/bin/python -m mypy src/tradingx` passed with no issues in 110 source files.
- `.venv/bin/python -m pytest tests/unit tests/integration` passed: `953 passed, 98 skipped, 2 warnings in 301.45s`.

Failures found and fixed:

- Initial Wave 2 tests failed because new schemas and mandate evaluator behavior did not exist.
- Legacy Wave 1 fixture artifacts with `benchmark_policy` and `wealth_thesis` kinds initially failed strict Wave 2 schema routing; fixed by validating Wave 2 schemas only when authority metadata fields are present and preserving legacy placeholder fixture semantics under explicit fixture roots.
- Full promotion regression initially failed because the fixture schema test treated legacy fixture policies as Wave 2 authority artifacts; fixed the test selection to require authority metadata before applying Wave 2 schemas.
- Ruff line-length failures in new mandate helper code were fixed.

Assumptions made:

- Wave 2 authority artifacts are considered authority-bearing when they include the Milestone 0 common authority metadata fields and are referenced from the signed promotion ledger record.
- Existing Wave 1 paper-shadow placeholder fixtures remain valid only under `tests/fixtures` as test fixture authority; non-fixture production roots require the new mandate artifacts.
- Taxable live capital without modeled after-tax status is conservatively capped by `tax_account_financing_unspecified` in this wave; later statistical evidence waves will own lower-bound edge proof quality.

Unresolved risks:

- The new schemas are closed-world but intentionally use the repository's small schema validator subset, not full JSON Schema semantics.
- Wave 2 does not implement the future statistical proof that lower-bound net edge exceeds threshold; it only requires the predeclared lower-bound net edge spec and blocker grouping.
- Full regression still reports two existing `httpx` deprecation warnings from `tests/unit/test_web_app.py`.

Commit hash:

- Not committed yet.
