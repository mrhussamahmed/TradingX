# Wave 2 Mandate And Allocation Governance Fix Report

Review addressed: `docs/reports/wave2_mandate_allocation_review_report.md`

Findings fixed:

- `W2-R1` blocker: mandate authority metadata is no longer ceremonial. Wave 2 mandate artifacts now verify semantic payload hash, ledger sequence, authority ref, mandate approval refs, approval signatures, and retained replay input refs before satisfying required mandate artifact checks.
- `W2-R2` blocker: taxable live/probe/production promotion now requires after-tax lower-bound net edge evidence unless the mandate hard-caps below live use. Missing or pre-tax-only evidence emits `after_tax_edge_missing_for_taxable_account`; below-threshold evidence emits `net_edge_lower_bound_below_threshold`.
- `W2-R3` high: mandate semantics are enforced for inactive and research-only capital roles, non-ex-ante benchmarks, and jurisdiction/instrument promotion ceilings.
- `W2-R4` high: allocation policy limits are enforced in the promotion evaluator and exposed through portfolio blueprint/construction allocation-limit validation hooks.
- `W2-R5` high: lower-bound net edge specs now receive semantic validation for confidence bounds, positive effective sample size, benchmark pairing, serial-dependence correction, fat-tail treatment, stress inputs, and Bayesian prior sensitivity.
- `W2-R6` medium: `tests/fixtures/mandate/` now contains replayable signed authority bundles with manifest, trust root, CAS payloads, replay inputs, approvals, and ledger records.

Files changed by fixes:

- `src/tradingx/promotion.py`
- `src/tradingx/portfolio/blueprint.py`
- `src/tradingx/portfolio/construction.py`
- `src/tradingx/portfolio/__init__.py`
- `schemas/quant/content_addressed_artifact.schema.json`
- `tests/fixtures/mandate/`
- `tests/unit/test_promotion.py`
- `tests/unit/test_main.py`
- `tests/unit/test_portfolio_blueprint.py`
- `tests/unit/test_portfolio_construction.py`

Tests added or updated:

- Mandate authority tamper tests for wrong payload hash, wrong ledger sequence, missing approval ref, missing replay input, and wrong authority ref.
- Taxable expected-wealth tests for missing after-tax evidence, pre-tax-only evidence, and below-threshold evidence.
- Semantic mandate tests for inactive/research-only capital roles, non-ex-ante benchmark policy, policy ceilings, allocation-limit breach, and invalid lower-bound spec math.
- Fixture replay tests for signed Wave 2 mandate bundles.
- CLI fixture replay test for `tests/fixtures/mandate/external_capital_unknown`.
- Portfolio blueprint and construction tests for allocation policy limit refusal.

Validation commands run:

- `.venv/bin/python -m pytest tests/unit/test_promotion.py::test_mandate_artifact_wrong_payload_hash_fails_authority tests/unit/test_promotion.py::test_mandate_artifact_wrong_sequence_approval_replay_or_authority_ref_fails tests/unit/test_promotion.py::test_taxable_production_without_after_tax_edge_evidence_caps_at_paper_trading tests/unit/test_promotion.py::test_taxable_production_with_pretax_only_edge_evidence_is_not_live_capable tests/unit/test_promotion.py::test_taxable_production_with_negative_lower_bound_fails_expected_wealth tests/unit/test_promotion.py::test_inactive_and_research_only_capital_roles_block_capital_promotion tests/unit/test_promotion.py::test_non_ex_ante_benchmark_policy_blocks_capital_promotion tests/unit/test_promotion.py::test_mandate_policy_ceiling_below_request_blocks_capital_promotion tests/unit/test_promotion.py::test_allocation_policy_limit_exceeded_caps_at_paper_shadow tests/unit/test_promotion.py::test_invalid_lower_bound_spec_math_blocks_statistical_authority`
- `.venv/bin/python -m pytest tests/unit/test_promotion.py::test_wave2_fixture_bundles_replay_from_disk`
- `.venv/bin/python -m pytest tests/unit/test_promotion.py tests/unit/test_main.py::test_promotion_check_replays_wave2_mandate_fixture_bundle tests/unit/test_blocker_registry.py`
- `.venv/bin/python -m pytest tests/unit/test_portfolio_blueprint.py::test_blueprint_allocation_policy_limit_rejects_excess_strategy_budget tests/unit/test_portfolio_construction.py::test_combine_sleeve_weights_rejects_mandate_allocation_limit_breach`
- `.venv/bin/python -m pytest tests/unit/test_promotion.py tests/unit/test_main.py tests/unit/test_reporting.py tests/unit/test_blocker_registry.py tests/unit/test_portfolio_blueprint.py tests/unit/test_portfolio_construction.py`
- `.venv/bin/python -m pytest tests/unit/test_authority.py tests/unit/test_activation.py tests/unit/test_activation_snapshot_payloads.py tests/unit/test_blueprint_activation_gateway.py tests/unit/test_execution_authority.py tests/unit/test_execution.py tests/integration/test_promotion_activation.py tests/unit/test_service.py tests/unit/test_web_runtime.py tests/unit/test_main.py tests/unit/test_reporting.py tests/unit/test_promotion.py tests/unit/test_blocker_registry.py tests/unit/test_portfolio_blueprint.py tests/unit/test_portfolio_construction.py tests/unit/test_portfolio_live_construction.py`
- `.venv/bin/python -m ruff check .`
- `.venv/bin/python -m mypy src/tradingx`
- `.venv/bin/python -m pytest tests/unit tests/integration`

Validation results:

- Focused first-review fix tests passed: `10 passed`.
- Wave 2 fixture replay test passed: `1 passed`.
- Promotion, CLI fixture replay, and blocker registry passed: `49 passed`.
- Portfolio allocation-limit tests passed: `2 passed`.
- Expanded Wave 2, CLI, reporting, blocker registry, and portfolio slice passed: `113 passed`.
- Authority/activation/execution/web/runtime/portfolio regression slice passed: `193 passed`.
- `.venv/bin/python -m ruff check .` passed.
- `.venv/bin/python -m mypy src/tradingx` passed with no issues in 110 source files.
- `.venv/bin/python -m pytest tests/unit tests/integration` passed: `967 passed, 98 skipped, 2 warnings in 293.52s`.

Remaining risks:

- Full regression still reports two existing `httpx` deprecation warnings from `tests/unit/test_web_app.py`.
- Allocation limits are now enforceable through promotion evaluation and portfolio construction hooks; future waves that add optimizer/sizing authority should pass signed allocation limits through those hooks rather than duplicating policy logic.
