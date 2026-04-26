# Wave 2 Mandate And Allocation Governance Second Fix Report

Review addressed: `docs/reports/wave2_mandate_allocation_rereview_report.md`

Findings fixed:

- `W2-R1` blocker: mandate artifacts with empty `approval_record_refs` now fail authority verification. Mandate approval records with empty operator identity, role registry, or authority boundary refs also fail.
- `W2-R3` high: mandate semantic evaluation now reads only authority-verified mandate payloads. Unsigned duplicate mandate artifacts no longer mask signed semantics, and conflicting duplicate signed mandate artifacts fail closed.
- `W2-R4` high: portfolio live construction now uses allocation limits carried on the `PortfolioBlueprint`, and construction helpers resolve blueprint-backed limits when no explicit override is supplied.
- `W2-R7` blocker: lower-bound net edge evidence is now required for all live/probe/production capital-bearing promotion. Taxable accounts still require after-tax evidence; tax-exempt/non-taxable accounts still require complete lower-bound evidence after costs, tax status, financing, capacity, and benchmark stress inputs.

Files changed by fixes:

- `src/tradingx/promotion.py`
- `src/tradingx/portfolio/blueprint.py`
- `src/tradingx/portfolio/construction.py`
- `src/tradingx/portfolio/live_construction.py`
- `src/tradingx/portfolio/__init__.py`
- `tests/fixtures/mandate/`
- `tests/unit/test_promotion.py`
- `tests/unit/test_portfolio_live_construction.py`

Tests added or updated:

- Mandate authority tests for empty mandate approval refs and empty approval identity fields.
- Duplicate mandate artifact tests for unsigned permissive duplicates and conflicting signed duplicates.
- Tax-exempt expected-wealth tests for missing lower-bound report, incomplete stress inputs, and complete positive lower-bound evidence.
- Live portfolio construction test proving blueprint-backed allocation limits are enforced without manually supplying limits to the live construction call.
- Fixture replay expectations for empty approval refs, unsigned duplicate role, signed duplicate conflict, and tax-exempt missing-edge fixtures.

Validation commands run:

- `.venv/bin/python -m pytest tests/unit/test_promotion.py::test_mandate_artifact_wrong_sequence_approval_replay_or_authority_ref_fails tests/unit/test_promotion.py::test_unverified_duplicate_mandate_artifact_cannot_mask_signed_role tests/unit/test_promotion.py::test_conflicting_signed_duplicate_mandate_artifacts_fail_closed tests/unit/test_promotion.py::test_tax_exempt_production_without_lower_bound_report_is_not_live_capable tests/unit/test_promotion.py::test_tax_exempt_production_requires_complete_lower_bound_stress_inputs tests/unit/test_promotion.py::test_tax_exempt_production_with_complete_lower_bound_report_can_pass tests/unit/test_portfolio_live_construction.py::test_live_cycle_uses_blueprint_allocation_limits`
- `.venv/bin/python -m pytest tests/unit/test_promotion.py tests/unit/test_main.py tests/unit/test_reporting.py tests/unit/test_blocker_registry.py tests/unit/test_portfolio_blueprint.py tests/unit/test_portfolio_construction.py tests/unit/test_portfolio_live_construction.py`
- `.venv/bin/python -m ruff check .`
- `.venv/bin/python -m mypy src/tradingx`
- `.venv/bin/python -m pytest tests/unit/test_authority.py tests/unit/test_activation.py tests/unit/test_activation_snapshot_payloads.py tests/unit/test_blueprint_activation_gateway.py tests/unit/test_execution_authority.py tests/unit/test_execution.py tests/integration/test_promotion_activation.py tests/unit/test_service.py tests/unit/test_web_runtime.py tests/unit/test_main.py tests/unit/test_reporting.py tests/unit/test_promotion.py tests/unit/test_blocker_registry.py tests/unit/test_portfolio_blueprint.py tests/unit/test_portfolio_construction.py tests/unit/test_portfolio_live_construction.py`
- `.venv/bin/python -m pytest tests/unit tests/integration`

Validation results:

- Focused round-2 fix tests passed: `7 passed`.
- Expanded Wave 2/portfolio slice passed: `123 passed`.
- `.venv/bin/python -m ruff check .` passed.
- `.venv/bin/python -m mypy src/tradingx` passed with no issues in 110 source files.
- Broad authority/activation/execution/web/runtime/portfolio regression slice passed: `199 passed`.
- `.venv/bin/python -m pytest tests/unit tests/integration` passed: `973 passed, 98 skipped, 2 warnings in 292.90s`.

Remaining risks:

- Full regression still reports two existing `httpx` deprecation warnings from `tests/unit/test_web_app.py`.
- Review loops for Wave 2 are capped at three by user instruction. The next review is round 3 and no fourth review will be spawned for this wave.
