# Wave 5 Cost, Quote Quality, And Capacity Handoff

Wave completed: yes

## Files changed

Source:

- `src/tradingx/costs.py`
- `src/tradingx/replay_slippage.py`
- `src/tradingx/promotion.py`
- `src/tradingx/__main__.py`
- `src/tradingx/types.py`
- `src/tradingx/experiments.py`
- `src/tradingx/web/readmodels.py`
- `src/tradingx/authority.py`

Schemas:

- `schemas/quant/quote_quality_record.schema.json` (new)
- `schemas/quant/execution_cost_observation.schema.json` (new)
- `schemas/quant/cost_model_report.schema.json` (new)
- `schemas/quant/capacity_curve_report.schema.json` (new)
- `schemas/quant/experiment_registration.schema.json` (added required
  `arrival_timestamp_policy` enum)

Fixtures:

- `tests/fixtures/cost_capacity/quote_quality_inputs.json`
- `tests/fixtures/cost_capacity/cost_model_report_inputs.json`
- `tests/fixtures/cost_capacity/capacity_curve_inputs.json`
- `tests/fixtures/experiments/experiment_registration_pre_result.json`
  (added field)

Tests:

- `tests/unit/test_cost_capacity_wave5.py` (new)
- `tests/unit/test_experiments.py` (helper + two new tests)

Reports:

- `docs/reports/wave5_cost_quote_capacity_implementation_report.md`
- `docs/reports/wave5_cost_quote_capacity_review_loop1_report.md`
- `docs/reports/wave5_cost_quote_capacity_review_loop1_fix_report.md`
- `docs/reports/wave5_cost_quote_capacity_review_loop2_report.md`
- `docs/reports/wave5_cost_quote_capacity_review_loop2_fix_report.md`
- `docs/reports/wave5_cost_quote_capacity_handoff.md`

## Tests added or updated

- `tests/unit/test_cost_capacity_wave5.py` — 24 tests covering all six
  required red tests plus schema validation, evaluator gating,
  attacker-payload re-derivation, replay-summary defaults, and session
  parametrization.
- `tests/unit/test_experiments.py` — added two tests for the
  `arrival_timestamp_policy` divergence and missing-flag rules; updated
  the `_registration` helper to include the new field.

## Validation commands passed

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_cost_capacity_wave5.py -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_promotion.py tests/unit/test_experiments.py tests/unit/test_main.py tests/unit/test_replay_slippage.py tests/unit/test_blocker_registry.py -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit tests/contract tests/integration -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/tradingx`
- `UV_CACHE_DIR=/tmp/uv-cache uv run black --check <touched files>`
- `python3 scripts/check_index.py`

## Reviews

Two adversarial review loops were completed per user instruction:

- Loop 1: two parallel reviewers (A and B). All critical/high findings
  fixed; medium/low findings deferred with documented rationale.
- Loop 2: one fresh reviewer. C2 (always-on cost/capacity rule)
  rejected with rationale. H1, H2, H3 fixed. Other findings deferred.

A clean reviewer session was not available; reviewers were spawned
with minimal context and explicit instructions to review from first
principles. Documented in the implementation report.

## Accepted residual risks

See `wave5_cost_quote_capacity_implementation_report.md` for the
"Accepted residual risks" section. Key items:

- `evaluate_cost_capacity_blockers` is conditionally passive (rejected
  loop-2 C2).
- No dedicated `replay_slippage_summary` schema (loop-2 M1).
- CLI validates emitted artifacts but not raw inputs (loop-2 M2).
- Roadmap write-scope items `execution.py`, `backtest.py`,
  `validation.py`, `data.py` not modified — runtime-side wiring of
  Wave 5 evidence is deferred to Wave 6 / Wave 8.
- `./scripts/validate` still fails on unrelated repo-wide Black
  formatting drift outside Wave 5 files.
