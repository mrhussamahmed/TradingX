# Wave 6 Portfolio Utility, Optimizer, Forecasts, And Sizing — Handoff

Wave completed: yes

## Files changed

Source:

- `src/tradingx/portfolio/optimizer.py` (new)
- `src/tradingx/forecasts.py` (new)
- `src/tradingx/promotion.py`
- `schemas/quant/experiment_registration.schema.json`

Schemas (new):

- `portfolio_utility_definition`, `optimizer_validation_report`,
  `optimizer_fallback_record`, `forecast_model_manifest`,
  `feature_manifest`, `label_definition`, `expected_return_report`,
  `sizing_policy`.

Tests:

- `tests/unit/test_portfolio_optimizer_wave6.py`
- `tests/unit/test_experiments.py` (helper update)

Fixture updates:

- `tests/fixtures/experiments/experiment_registration_pre_result.json`

Reports:

- `docs/reports/wave6_portfolio_optimizer_forecast_sizing_implementation_report.md`
- `docs/reports/wave6_portfolio_optimizer_forecast_sizing_review_loop1_report.md`
- `docs/reports/wave6_portfolio_optimizer_forecast_sizing_review_loop1_fix_report.md`
- `docs/reports/wave6_portfolio_optimizer_forecast_sizing_review_loop2_report.md`
- `docs/reports/wave6_portfolio_optimizer_forecast_sizing_review_loop2_fix_report.md`
- `docs/reports/wave6_portfolio_optimizer_forecast_sizing_handoff.md`

## Validation commands passed

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_portfolio_optimizer_wave6.py -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_promotion.py tests/unit/test_experiments.py tests/unit/test_main.py tests/unit/test_blocker_registry.py -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit tests/contract tests/integration -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/tradingx`
- `UV_CACHE_DIR=/tmp/uv-cache uv run black --check <touched files>`
- `python3 scripts/check_index.py`

## Reviews

Two adversarial review loops were completed.

- Loop 1 (two parallel reviewers): all critical/high findings fixed
  except passive evaluator (rejected with rationale) and
  `assert_sizing_monotonicity` (deferred).
- Loop 2 (one fresh reviewer): all major findings fixed except passive
  evaluator and missing `optimizer_input`/`optimizer_decision`
  schemas (deferred).

A truly clean reviewer session was not available; reviewers were
spawned with minimal context.

## Accepted residual risks

See `wave6_portfolio_optimizer_forecast_sizing_implementation_report.md`
section "Accepted residual risks". Key items:

- `evaluate_portfolio_optimizer_blockers` and
  `evaluate_forecast_sizing_blockers` are conditionally passive —
  bundles without Wave 6 artifacts are not penalized.
- `assert_sizing_monotonicity` is helper-level (not wired to runtime).
- `optimizer_input` / `optimizer_decision` / `sizing_decision` schemas
  deferred.
- No CLI subcommands yet for optimizer/forecast/sizing reports.
- `./scripts/validate` continues to fail on unrelated repo-wide Black
  drift (24 files).
