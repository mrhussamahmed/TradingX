# Wave 2 Mandate And Allocation Governance Final Fix Report

Wave: Wave 2 - Mandate And Allocation Governance

Review loop status: third review reached the user-capped maximum of 3 review iterations. No fourth reviewer was spawned. The remaining third-review findings were fixed deterministically and validated.

## Findings Fixed

### W2-FR1 - Signed Allocation Limits Not Reaching Runtime

Severity: high

Required fix: derive runtime allocation limits from verified signed `capital_allocation_policy` authority and fail closed when runtime construction lacks a matching verified limit.

Fix evidence:

- `PromotionDecision.strategy_allocation_limits` now carries verified allocation limits extracted from signed mandate authority.
- `src/tradingx/promotion.py` derives `max_strategy_allocation` from verified `capital_allocation_policy`.
- `src/tradingx/activation.py` converts promotion-decision allocation limits into `StrategyAllocationLimit` records and fails closed with `allocation_policy_limit_exceeded` if a promoted blueprint strategy has no matching verified limit.
- `src/tradingx/runtime_portfolio.py` passes activation-provided allocation limits into live portfolio cycle construction.
- `tests/unit/test_promotion.py::test_signed_capital_allocation_policy_exports_runtime_limit` proves signed policy extraction.
- `tests/unit/test_activation.py::test_local_activation_gateway_derives_verified_allocation_limits` proves activation conversion.
- `tests/unit/test_runtime_portfolio.py::test_runtime_portfolio_planner_enforces_activation_allocation_limits` proves runtime fails when a signed 5% cap meets a 10% blueprint budget with no blueprint-local duplicate limit.

### W2-FR2 - Lower-Bound Report Could Pass Without Spec Binding

Severity: blocker

Required fix: require lower-bound report metadata, report-to-spec binding, estimator/confidence/horizon/benchmark consistency, stress coverage including slippage, tax-status consistency, effective-sample metadata, and threshold matching before live/probe/production promotion.

Fix evidence:

- `schemas/quant/content_addressed_artifact.schema.json` now permits lower-bound report metadata fields needed for semantic validation.
- `src/tradingx/promotion.py` now requires lower-bound reports to bind to the verified `lower_bound_net_edge_spec` by artifact URI and payload hash.
- The lower-bound semantic validator compares estimator family, confidence level, horizon, benchmark pairing, serial-dependence correction, fat-tail treatment, pass threshold, effective sample size, tax status, edge basis, and required stress inputs.
- Required stress inputs now include `cost`, `slippage`, `tax`, `financing`, and `capacity`.
- `tests/unit/test_promotion.py::test_lower_bound_report_missing_spec_binding_is_not_live_capable` proves a bare positive scalar report cannot authorize production.
- `tests/unit/test_promotion.py::test_lower_bound_report_must_match_signed_spec_and_friction_fields` proves mismatched/missing spec binding, estimator, confidence, benchmark, slippage, and effective-sample metadata are blocked.
- `tests/fixtures/mandate/` was regenerated so fixture lower-bound reports bind to finalized signed spec hashes.

## Files Changed By Final Fix

- `schemas/quant/content_addressed_artifact.schema.json`
- `src/tradingx/activation.py`
- `src/tradingx/promotion.py`
- `src/tradingx/runtime_portfolio.py`
- `tests/unit/test_activation.py`
- `tests/unit/test_promotion.py`
- `tests/unit/test_runtime_portfolio.py`
- `tests/fixtures/mandate/`

## Validation Commands Run

- `.venv/bin/python -m pytest tests/unit/test_promotion.py::test_signed_capital_allocation_policy_exports_runtime_limit tests/unit/test_activation.py::test_local_activation_gateway_derives_verified_allocation_limits tests/unit/test_promotion.py::test_lower_bound_report_missing_spec_binding_is_not_live_capable tests/unit/test_promotion.py::test_lower_bound_report_must_match_signed_spec_and_friction_fields tests/unit/test_runtime_portfolio.py::test_runtime_portfolio_planner_enforces_activation_allocation_limits`
  - Result: `5 passed in 1.57s`
- `.venv/bin/python -m pytest tests/unit/test_promotion.py tests/unit/test_activation.py tests/unit/test_runtime_portfolio.py`
  - Result: `60 passed in 2.68s`
- `.venv/bin/python -m pytest tests/unit/test_promotion.py tests/unit/test_activation.py tests/unit/test_main.py tests/unit/test_reporting.py tests/unit/test_blocker_registry.py tests/unit/test_portfolio_blueprint.py tests/unit/test_portfolio_construction.py tests/unit/test_portfolio_live_construction.py tests/unit/test_runtime_portfolio.py`
  - Result: `138 passed in 11.78s`
- `.venv/bin/python -m json.tool schemas/quant/content_addressed_artifact.schema.json >/dev/null`
  - Result: passed
- `.venv/bin/python -m ruff check .`
  - Result: passed
- `.venv/bin/python -m mypy src/tradingx`
  - Result: passed; `Success: no issues found in 110 source files`
- `.venv/bin/python -m black --check <Wave 2 touched Python files>`
  - Result: passed; `18 files would be left unchanged`
- `python3 scripts/check_index.py`
  - Result: `INDEX validation passed.`
- `.venv/bin/python -m pytest tests/unit tests/contract tests/integration`
  - Result: `991 passed, 98 skipped, 13 warnings in 290.89s`
- `UV_CACHE_DIR=/tmp/uv-cache ./scripts/validate`
  - Result: failed at repository-wide Black check. The listed files were 25 pre-existing formatting drifts outside the Wave 2 touched files. The script passed `check_index` and `ruff` before stopping at Black.

## Failures Found And Fixed

- Initial focused tests failed because lower-bound report metadata was still optional and allocation limits were not passed into runtime construction. Fixed with promotion/activation/runtime plumbing and semantic validator.
- Running Black on the JSON schema rewrote it as invalid JSON. Fixed by restoring valid JSON and validating with `json.tool`.
- The repository-wide validation script initially failed before real checks because `uv` could not initialize `/Users/ahmedabd/.cache/uv` in the sandbox. Re-run with `UV_CACHE_DIR=/tmp/uv-cache`.

## Assumptions

- The repository-wide Black drift reported by `./scripts/validate` is outside Wave 2 scope because none of the 25 files listed in the final validation failure were touched by this wave.
- Per user instruction, no fourth Wave 2 adversarial review was spawned after the third review findings were fixed.

## Unresolved Risks

- `./scripts/validate` does not complete in the current working tree because of pre-existing Black formatting drift outside Wave 2 files.

## Commit Hash

Not committed yet at report creation time.
