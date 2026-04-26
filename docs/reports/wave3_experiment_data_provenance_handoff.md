# Wave 3 Experiment Registration And Data Provenance Handoff

Wave completed: Wave 3 - Experiment Registration And Data Provenance

Files changed:

- `schemas/quant/experiment_registration.schema.json`
- `schemas/quant/experiment_run_record.schema.json`
- `schemas/quant/experiment_amendment_record.schema.json`
- `schemas/quant/trial_universe_manifest.schema.json`
- `schemas/quant/dataset_manifest.schema.json`
- `schemas/quant/data_restatement_report.schema.json`
- `schemas/quant/evidence_dependency_index.schema.json`
- `schemas/quant/evidence_invalidation_report.schema.json`
- `src/tradingx/experiments.py`
- `src/tradingx/data_fingerprint.py`
- `src/tradingx/persistence/__init__.py`
- `src/tradingx/types.py`
- `src/tradingx/trials.py`
- `src/tradingx/validation.py`
- `src/tradingx/controller.py`
- `src/tradingx/__main__.py`
- `src/tradingx/runtime_logging.py`
- `src/tradingx/promotion.py`
- `src/tradingx/web/app.py`
- `src/tradingx/web/runtime.py`
- `src/tradingx/web/readmodels.py`
- `tests/fixtures/experiments/`
- `tests/fixtures/data_fingerprints/`
- `tests/unit/test_experiments.py`
- `tests/unit/test_data_fingerprint.py`
- `tests/unit/test_trials.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_controller_generate_gate_report_cpcv.py`
- `tests/unit/test_main.py`
- `tests/unit/test_promotion.py`
- `tests/unit/test_web_readmodels.py`
- `tests/unit/test_web_runtime.py`
- `docs/reports/tradingx_quant_hardening_execution_tracker.md`
- `docs/reports/wave3_experiment_data_provenance_implementation_report.md`
- `docs/reports/wave3_experiment_data_provenance_review_report.md`
- `docs/reports/wave3_experiment_data_provenance_fix_report.md`

Tests added or updated:

- `tests/unit/test_experiments.py`
- `tests/unit/test_data_fingerprint.py`
- `tests/unit/test_trials.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_controller_generate_gate_report_cpcv.py`
- `tests/unit/test_main.py`
- `tests/unit/test_promotion.py`
- `tests/unit/test_web_readmodels.py`
- `tests/unit/test_web_runtime.py`

Validation commands passed:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_experiments.py tests/unit/test_data_fingerprint.py tests/unit/test_main.py::test_gate_report_cli_threads_registered_metric_visibility_context tests/unit/test_main.py::test_gate_report_cli_fake_metric_context_fails_closed tests/unit/test_main.py::test_compare_dataset_cli_marks_manual_review_when_old_raw_unavailable tests/unit/test_main.py::test_experiment_run_cli_appends_started_then_completed_lifecycle tests/unit/test_validation.py::test_promotion_valid_gate_report_ignores_legacy_trials_ledger tests/unit/test_web_runtime.py::test_local_web_action_runner_fake_metric_context_fails_closed tests/unit/test_web_runtime.py::test_local_web_action_runner_resolves_released_metric_context`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_experiments.py tests/unit/test_data_fingerprint.py tests/unit/test_main.py tests/unit/test_validation.py tests/unit/test_web_runtime.py tests/unit/test_web_readmodels.py tests/unit/test_controller_generate_gate_report_cpcv.py tests/unit/test_controller.py tests/unit/test_promotion.py tests/unit/test_trials.py`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit tests/contract tests/integration`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/tradingx`
- `UV_CACHE_DIR=/tmp/uv-cache uv run black --check $(git diff --name-only -- '*.py')`
- `python3 scripts/check_index.py`

Validation command with known non-Wave-3 failure:

- `UV_CACHE_DIR=/tmp/uv-cache ./scripts/validate` passed artifact index and Ruff, then failed at repository-wide Black on 24 files outside the Wave 3 touched-file set.

Final review result:

- `docs/reports/wave3_experiment_data_provenance_review_report.md` produced findings before adversarial reviews were disabled.
- `docs/reports/wave3_experiment_data_provenance_fix_report.md` documents fixes for all findings.
- No further adversarial reviews were run after user instruction.

Accepted risks:

- Repository-wide `./scripts/validate` remains blocked by unrelated pre-existing Black formatting drift outside Wave 3 files.

