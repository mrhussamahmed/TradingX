# TradingX Tier 0 Wave 3 DSR Unit Convention Evidence

Date: 2026-04-28

## Scope

Wave 3 was limited to DSR unit convention cleanup in:

- `src/tradingx/stats.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/trials.py`
- `tests/unit/test_stats.py`
- `tests/unit/test_evaluation.py`
- `tests/unit/test_trials.py`

No PBO/CPCV redesign, Tier 0A hurdle logic, strategy behavior, validation harness,
macro/event-clock, or runtime changes were added.

## Evidence

- DSR public boundary now requires unit-bearing per-period Sharpe inputs.
- Annualized Sharpe callers convert through explicit helper names before DSR.
- Trials ledger keeps the legacy annualized summary method and adds a
  per-period summary method for DSR callers.
- Evaluation converts observed annualized Lo Sharpe to per-period before DSR.
- Trial mean, trial variance, observed Sharpe, and expected-max benchmark Sharpe
  are per-period at the DSR boundary.
- Evaluation evidence assumptions mark DSR as `reported_only` for Tier 0.

## Verification

- `uv run pytest tests/unit/test_stats.py tests/unit/test_trials.py tests/unit/test_evaluation.py -q`
  passed: 55 tests.
- `uv run ruff check src/tradingx/stats.py src/tradingx/evaluation.py src/tradingx/trials.py tests/unit/test_evaluation.py tests/unit/test_trials.py`
  passed.
- `uv run mypy src/tradingx/stats.py src/tradingx/evaluation.py src/tradingx/trials.py`
  passed.
- `uv run pytest tests/unit -q` was attempted; it failed in
  `tests/unit/test_portfolio_live_construction.py::test_cycle_and_batch_parity_element_wise`,
  outside Wave 3 ownership.
